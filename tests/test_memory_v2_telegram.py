"""Authenticated message admission: original text, quote offsets and retry boundaries."""

from unittest.mock import Mock

import pytest
from services.memory_v2.models import MemoryConflict, MemorySourceConflict, MemoryUnavailable, SourceRef
from services.memory_v2.telegram_ingestion import TelegramMemoryAdmission, source_event


def update(text="I live in Astana.", **changes):
    return {
        "message": {
            "chat": {"id": -100123, "type": "supergroup"},
            "message_id": 42,
            "from": {"id": 7, "is_bot": False},
            "date": 2000000000,
            "text": text,
            **changes,
        }
    }


def test_replied_body_and_media_analysis_never_become_source():
    body = update(reply_to_message={"text": "Bob lives in Paris.", "from": {"id": 8}}, photo=[{"file_id": "synthetic"}])
    source = source_event(body)
    assert source.text == "I live in Astana."
    assert source.actor_user_id == "7"


def test_quote_offsets_convert_utf16_after_emoji():
    source = source_event(
        update("😀 Bob: I use Python. I use Rust.", entities=[{"type": "blockquote", "offset": 3, "length": 18}])
    )
    assert source.text[slice(*source.quoted_spans[0])] == "Bob: I use Python."


def test_invalid_quote_offset_cannot_be_used_as_self_evidence():
    source = source_event(update("😀 I use Python.", entities=[{"type": "blockquote", "offset": 1, "length": 4}]))
    assert source.quoted_spans == ((0, len(source.text)),)


@pytest.mark.parametrize(
    "text,extra",
    [
        ("", {}),
        ("/memory forget me", {}),
        ("I use Python.", {"forward_origin": {"type": "user"}}),
        ("My password is synthetic-secret-123.", {}),
    ],
)
def test_ineligible_edit_still_invalidates_before_any_moderation(text, extra):
    ingestion = Mock()
    admission = TelegramMemoryAdmission(ingestion, update(text, edit_date=2000000001, **extra))
    ingestion.observe.assert_called_once()
    assert not admission.eligible
    assert admission.prepare("classification text", {}) is None
    admission.accept_safe()
    ingestion.prepare.assert_not_called()
    ingestion.accept_safe.assert_not_called()


@pytest.mark.parametrize("error", [MemoryUnavailable, MemorySourceConflict])
def test_stopped_or_definitely_obsolete_source_is_not_a_webhook_failure(error):
    ingestion = Mock()
    ingestion.observe.side_effect = error("synthetic")
    assert not TelegramMemoryAdmission(ingestion, update()).eligible


def test_transaction_conflict_requires_telegram_redelivery():
    ingestion = Mock()
    ingestion.observe.side_effect = MemoryConflict("synthetic CAS race")
    with pytest.raises(MemoryConflict):
        TelegramMemoryAdmission(ingestion, update())


def test_classification_fingerprint_keeps_canonical_original_source_separate():
    from services.memory_v2.ingestion import moderation_input_hash

    ingestion = Mock()
    ref = SourceRef("42", 3, "synthetic-epoch")
    ingestion.prepare.return_value = ref
    admission = TelegramMemoryAdmission(ingestion, update())
    context = {"reply_to_text": "A quoted advertisement"}
    assert admission.prepare("classification plus quote", context) == ref.as_dict()
    event, digest = ingestion.prepare.call_args.args
    assert event.text == "I live in Astana."
    assert digest == moderation_input_hash("classification plus quote", context)
