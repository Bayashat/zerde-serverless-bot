"""Reference linkage diagnostics must not change media delivery or expose content."""

import io
import json
import logging
from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from services import telegram_media as media
from services.handlers import commands
from services.memory_cutover import EXPLICIT_CONTEXT_VERSION
from zerde_common.logger import JSONFormatter, ZerdeLoggerAdapter


def reference(**changes):
    values = {
        "media_type": "photo",
        "file_id": "downloadable-file",
        "file_unique_id": "unique-x",
        "media_group_id": "album-x",
        "source_message_id": 10,
        "source_user_id": 42,
    }
    return values | changes


def digest(ref, chat=-100):
    return media.media_reference_proof_log_extra(chat, ref)["media_reference_proof_digest"]


def native_message(**changes):
    return {
        "chat": {"id": -100},
        "message_id": 10,
        "from": {"id": 42},
        "media_group_id": "album-x",
        "date": 1_700_000_000,
        "photo": [{"file_id": "downloadable-file", "file_unique_id": "unique-x"}],
    } | changes


def test_versioned_canonical_reference_vector_and_integer_string_equivalence():
    expected = "79d2472b388ada58ffbca9b8b8207c968f9f5604deea841a7e54d6e024f53f6b"
    assert digest(reference()) == expected
    assert digest(reference(source_message_id="10", source_user_id="42"), "-100") == expected
    assert digest(media.MediaReference.from_mapping(reference())) == expected
    assert media.media_reference_proof_log_extra(-100, reference()) == {
        "media_reference_proof_version": 1,
        "media_reference_proof_status": "AVAILABLE",
        "media_reference_proof_digest": expected,
    }
    # Content and reusable file identifiers are outside this reference-only proof.
    assert (
        digest(
            reference(
                file_id="different-token",
                caption="different text",
                file_name="private.png",
            )
        )
        == expected
    )


@pytest.mark.parametrize(
    "change",
    [
        {"source_message_id": 11},
        {"source_user_id": 43},
        {"media_type": "video"},
        {"media_group_id": "album-y"},
        {"file_unique_id": "unique-y"},
    ],
)
def test_reference_substitution_changes_digest(change):
    assert digest(reference(**change)) != digest(reference())
    assert digest(reference(), -101) != digest(reference())


@pytest.mark.parametrize("bad", [True, False, None, 0, 1.0, "01", "+1", " 1", "1 ", "١", 10**20, "9" * 21])
def test_ambiguous_ids_are_unavailable_before_and_after_business_conversion(bad):
    assert digest(reference(source_message_id=bad)) is None
    # Do not let existing int() conversion turn a rejected value into a proof.
    converted = media.MediaReference.from_mapping(reference(source_message_id=bad))
    assert digest(converted) is None
    assert digest(reference(source_user_id=bad)) is None
    assert digest(reference(), bad) is None


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "",
        123,
        True,
        [],
        {},
        " x",
        "x ",
        "a\nb",
        "a\x00b",
        "a\u200bb",
        "a\ud800b",
        "x" * 513,
    ],
)
@pytest.mark.parametrize("key", ["media_group_id", "file_unique_id"])
def test_raw_media_identity_is_not_repaired_by_strip_or_string_coercion(key, bad):
    ref = reference(**{key: bad})
    assert digest(ref) is None
    assert digest(media.MediaReference.from_mapping(ref)) is None


def test_truncation_stale_sidecar_and_external_sidecar_cannot_claim_equality():
    long_group = reference(media_group_id="x" * 161)
    assert digest(long_group) is not None  # Valid raw identity, changed by business truncation.
    assert digest(media.MediaReference.from_mapping(long_group)) is None
    ref = media.MediaReference.from_mapping(reference())
    assert digest(replace(ref, file_unique_id="replacement")) is None
    forged = reference(source_message_id=True, _proof_identity=ref._proof_identity)
    assert digest(media.MediaReference.from_mapping(forged)) is None
    unavailable = media.MediaReference.from_mapping(reference(source_message_id=True))
    assert digest(replace(unavailable, source_message_id=10)) is None
    assert digest(media.MediaReference(**reference())) == digest(ref)


@pytest.mark.parametrize(
    "changes",
    [
        {"message_id": True},
        {"message_id": "0010"},
        {"from": {"id": "0042"}},
        {"media_group_id": " album-x "},
        {"media_group_id": "x" * 161},
        {"photo": [{"file_id": "downloadable-file", "file_unique_id": 123}]},
    ],
)
def test_native_selection_remembers_invalid_or_changed_original_identity(changes):
    ref = media.detect_media_reference(native_message(**changes))
    assert ref is not None  # Existing business behavior is retained.
    assert digest(ref) is None
    assert "_proof_identity" not in ref.to_dict()


def test_collection_proof_preserves_order_missing_entries_and_duplicate_rejection():
    one, two = reference(), reference(source_message_id=11, file_unique_id="unique-y")
    proof = media.media_references_proof_log_extra(-100, [one, two])
    assert proof["media_reference_proof_status"] == "AVAILABLE"
    assert proof["media_reference_proof_digests"] == [digest(one), digest(two)]
    reverse = media.media_references_proof_log_extra(-100, [two, one])
    assert reverse["media_reference_proof_digests"] == proof["media_reference_proof_digests"][::-1]
    partial = media.media_references_proof_log_extra(-100, [one, reference(file_unique_id=None)])
    assert partial["media_reference_proof_digests"] == [digest(one), None]
    assert partial["media_reference_proof_requested_count"] == 2
    assert partial["media_reference_proof_proven_count"] == 1
    assert partial["media_reference_proof_status"] == "UNAVAILABLE"
    for refs in (
        [],
        [one, one],
        [reference(source_message_id=i + 1) for i in range(5)],
    ):
        assert media.media_references_proof_log_extra(-100, refs)["media_reference_proof_status"] == "UNAVAILABLE"


def prepared(data=b"x"):
    return media.PreparedMedia(
        media_parts=[{"inline_data": {"mime_type": "image/jpeg", "data": data.hex()}}],
        media_context="unchanged context",
        agent_reply_metadata={"media_type": "photo"},
        downloaded_bytes=len(data),
        content_mode="inline_data",
    )


def test_prepared_references_only_include_success_after_final_byte_limit(monkeypatch):
    monkeypatch.setattr(media, "MULTIMODAL_ENABLED", True)
    monkeypatch.setattr(media, "MULTIMODAL_MAX_DOWNLOAD_BYTES", 2)
    refs = [reference(), reference(source_message_id=11, file_unique_id="second")]
    prepare = MagicMock(side_effect=[prepared(b"x"), prepared(b"xx")])
    monkeypatch.setattr(media, "prepare_media_for_gemini", prepare)
    result = media.prepare_media_collection_for_gemini(MagicMock(), refs)
    assert prepare.call_count == 2
    assert result.requested_count == 2 and result.prepared_count == 1 and result.skipped_count == 1
    assert result.media_parts == prepared().media_parts
    assert result.prepared_refs == (media.MediaReference.from_mapping(refs[0]),)
    proof = media.media_references_proof_log_extra(-100, result.prepared_refs)
    assert proof["media_reference_proof_digests"] == [digest(refs[0])]
    assert "Some related media items could not be analyzed" in result.media_context


def test_invalid_identity_does_not_stop_preparation_or_recover_proof(monkeypatch):
    monkeypatch.setattr(media, "MULTIMODAL_ENABLED", True)
    prepare = MagicMock(return_value=prepared())
    monkeypatch.setattr(media, "prepare_media_for_gemini", prepare)
    result = media.prepare_media_collection_for_gemini(MagicMock(), [reference(source_message_id=True)])
    assert result.media_parts == prepared().media_parts
    assert result.prepared_refs[0].source_message_id == 1  # Existing conversion remains.
    assert digest(result.prepared_refs[0]) is None
    assert "_proof_identity" not in result.agent_reply_metadata


@pytest.mark.parametrize(
    "failure",
    [
        media.MediaTooLargeError("size"),
        media.MediaUnsupportedError("unsupported"),
        media.MediaUnavailableError("missing"),
    ],
)
def test_all_skipped_items_preserve_existing_failure_without_false_prepared_proof(monkeypatch, failure):
    monkeypatch.setattr(media, "MULTIMODAL_ENABLED", True)
    monkeypatch.setattr(media, "prepare_media_for_gemini", MagicMock(side_effect=failure))
    with pytest.raises(type(failure)):
        media.prepare_media_collection_for_gemini(MagicMock(), [reference()])


def test_worker_log_uses_actual_successful_refs_and_provider_arguments_stay_unchanged(
    monkeypatch,
):
    monkeypatch.setattr(media, "MULTIMODAL_ENABLED", True)
    monkeypatch.setattr(media, "MULTIMODAL_MAX_DOWNLOAD_BYTES", 100)
    prepare = MagicMock(side_effect=[media.MediaTooLargeError("skip"), prepared()])
    monkeypatch.setattr(media, "prepare_media_for_gemini", prepare)
    answer, logger = MagicMock(return_value=True), MagicMock()
    monkeypatch.setattr(commands, "answer_group_question", answer)
    monkeypatch.setattr(commands, "logger", logger)
    refs = [reference(), reference(source_message_id=11, file_unique_id="second")]
    commands.process_group_ask_task(
        repo=MagicMock(),
        bot=MagicMock(),
        body={
            "context_version": EXPLICIT_CONTEXT_VERSION,
            "chat_id": -100,
            "reply_to_message_id": 20,
            "user_text": "describe",
            "retrieval_query": "describe",
            "lang": "en",
            "media_refs": refs,
        },
    )
    fields = logger.info.call_args.kwargs["extra"]
    assert fields["media_reference_proof_digests"] == [digest(refs[1])]
    assert fields["media_requested_count"] == 2
    assert fields["media_prepared_count"] == 1 and fields["media_skipped_count"] == 1
    assert answer.call_args.kwargs["media_parts"] == prepared().media_parts
    assert not any("proof" in key for key in answer.call_args.kwargs)
    assert not any("proof" in key for key in answer.call_args.kwargs["media_metadata"])
    assert prepare.call_count == 2


def test_store_detect_prepare_chain_uses_actual_json_redaction_without_changing_persistence(
    monkeypatch,
):
    monkeypatch.setattr(media, "MULTIMODAL_ENABLED", True)
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JSONFormatter())
    logger = logging.Logger("media-proof-test", logging.INFO)
    logger.addHandler(handler)
    adapter = ZerdeLoggerAdapter(logger, {})
    monkeypatch.setattr(media, "logger", adapter)
    monkeypatch.setattr(commands, "logger", adapter)
    message = native_message(caption="private caption", from_user="unused")
    repo = MagicMock()
    media.observe_media_group(repo, {"message": message})
    stored = repo.store_media_group_item.call_args.kwargs["media_ref"]
    assert "_proof_identity" not in stored
    assert stored["file_id"] == "downloadable-file" and stored["caption"] == "private caption"
    ctx = MagicMock()
    ctx.text, ctx.chat_id, ctx.message_id, ctx.update_id = "/ask describe", -100, 20, 30
    ctx.user_id, ctx.username, ctx.user_data, ctx.lang_code = (
        42,
        "actor",
        {"id": 42},
        "en",
    )
    ctx.reply_to_message = message
    ctx.message = {"message_id": 20, "text": ctx.text, "reply_to_message": message}
    ctx.memory_repo.get_media_group_refs.return_value = [stored]
    commands.handle_ask(ctx)
    queued = ctx.sqs_repo.send_group_ask_task.call_args.kwargs["media_refs"]
    assert all("_proof_identity" not in ref for ref in queued)
    monkeypatch.setattr(media, "prepare_media_for_gemini", MagicMock(return_value=prepared()))
    result = media.prepare_media_collection_for_gemini(MagicMock(), queued)
    adapter.info(
        "Prepared proof",
        extra=media.media_references_proof_log_extra(-100, result.prepared_refs),
    )
    records = [json.loads(line) for line in output.getvalue().splitlines()]
    stored_log = next(row for row in records if row["message"] == "Telegram media group item stored")
    detected_log = next(row for row in records if row["message"] == "Explicit ask media detected")
    assert stored_log["media_reference_proof_digest"] == digest(reference())
    assert (
        detected_log["media_reference_proof_digests"]
        == records[-1]["media_reference_proof_digests"]
        == [stored_log["media_reference_proof_digest"]]
    )
    for sensitive in (
        "downloadable-file",
        "unique-x",
        "album-x",
        "private caption",
        "_proof_identity",
    ):
        assert sensitive not in output.getvalue()
    assert stored_log["file_unique_id"] == stored_log["media_group_id"] == "[REDACTED]"
