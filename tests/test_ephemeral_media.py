"""Actual DynamoDB transactions for ephemeral albums and legacy IO retirement."""

from dataclasses import replace
from unittest.mock import MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError
from services.memory_v2.lifecycle import MemoryLifecycle
from services.memory_v2.media_ephemeral import MEDIA_RETENTION_SECONDS, EphemeralMediaRepository
from services.memory_v2.models import MemoryConflict, MemoryInputError, MemoryUnavailable
from services.repositories import group_memory
from services.repositories.explicit_context_repository import ExplicitContextRepository
from services.telegram_media import detect_media_references

from tests import test_memory_v2_contract as contract
from tests.test_memory_v2_contract import CHAT, USER, activate, event
from tests.test_memory_v2_lifecycle import finish

env = contract.env


def media(message_id="8", *, actor=USER, album="album-1"):
    return {
        "media_type": "photo",
        "file_id": "file-" + message_id,
        "file_unique_id": "unique-" + message_id,
        "mime_type": "image/jpeg",
        "file_size": 123,
        "duration_seconds": 0,
        "source_message_id": int(message_id),
        "source_user_id": actor,
        "media_group_id": album,
        "caption": "A private caption",
        "file_name": "A private filename.jpg",
        "source_username": "private_alias",
        "source_display_name": "Private name",
    }


def store(env, *, message_id="8", actor=USER, album="album-1", chat=CHAT):
    source = event(env, message_id, text="", user=actor, chat=chat)
    ref = env.repo.observe(source)
    EphemeralMediaRepository(env.repo).store(
        chat_id=chat,
        media_group_id=album,
        source_ref=ref,
        actor_user_id=actor,
        created_at=source.original_sent_at,
        media_ref=media(message_id, actor=actor, album=album),
    )
    return source, ref


def album_rows(env):
    return list(env.repo._list(CHAT, "MEDIA_ALBUM#"))


@pytest.fixture
def cached(env):
    activate(env)
    return store(env)


@pytest.fixture
def overlay(env, monkeypatch):
    db = boto3.resource("dynamodb", region_name="eu-central-1")
    legacy = db.create_table(
        TableName="legacy-mixed-table",
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    monkeypatch.setattr(group_memory, "get_dynamodb", lambda: db)
    return ExplicitContextRepository(legacy.name, memory_v2_repo=env.repo)


def test_store_only_one_day_metadata_and_no_raw_work_fact(env, cached):
    source, ref = cached
    row = album_rows(env)[0]
    assert row["ttl"] == source.original_sent_at + MEDIA_RETENTION_SECONDS
    assert row["source_ref"] == ref.as_dict()
    assert row["actor_user_id"] == USER
    assert row["subject_generation"] == env.repo.get_subject(CHAT, USER)["generation"]
    assert not {"caption", "file_name", "source_username", "source_display_name"} & row["media_ref"].keys()
    assert "private" not in str(row).lower()
    assert not list(env.repo._list(CHAT, "RAW#"))
    assert not list(env.repo._list(CHAT, "WORK#"))
    assert not list(env.repo._list(CHAT, "FACT#"))
    refs = EphemeralMediaRepository(env.repo).get_refs(CHAT, "album-1")
    assert refs[0]["ephemeral_source_ref"] == ref.as_dict()
    assert refs[0]["source_message_id"] == 8


def test_replay_retains_original_expiry_and_rejects_metadata_replacement(env, cached):
    source, ref = cached
    before = album_rows(env)
    env.clock.now += 100
    kwargs = dict(
        chat_id=CHAT,
        media_group_id="album-1",
        source_ref=ref,
        actor_user_id=USER,
        created_at=source.original_sent_at,
        media_ref=media(),
    )
    cache = EphemeralMediaRepository(env.repo)
    cache.store(**kwargs)
    assert album_rows(env) == before
    kwargs["media_ref"] = {**media(), "file_id": "different"}
    with pytest.raises(MemoryConflict):
        cache.store(**kwargs)
    assert album_rows(env) == before


def test_sorted_bounded_expansion_preserves_direct_item(env, overlay):
    activate(env)
    for message_id in ["12", "8", "11", "10", "9"]:
        store(env, message_id=message_id)
    assert [r["source_message_id"] for r in overlay.get_media_group_refs(CHAT, "album-1")] == [8, 9, 10, 11]
    refs = detect_media_references(
        {"reply_to_message": {"message_id": 12, "media_group_id": "album-1", "photo": [{"file_id": "file-12"}]}},
        media_group_loader=lambda album: overlay.get_media_group_refs(CHAT, album),
    )
    assert [ref.source_message_id for ref in refs] == [12, 8, 9, 10]


@pytest.mark.parametrize("scope", ["group", "subject", "source"])
def test_deletion_blocks_read_and_store_then_physically_purges(env, cached, scope):
    source, ref = cached
    lifecycle = MemoryLifecycle(env.repo)
    target = USER if scope == "subject" else "8" if scope == "source" else None
    job = lifecycle.begin(CHAT, scope=scope, target=target)
    cache = EphemeralMediaRepository(env.repo)
    with pytest.raises(MemoryUnavailable):
        cache.get_refs(CHAT, "album-1")
    with pytest.raises(MemoryUnavailable):
        cache.store(
            chat_id=CHAT,
            media_group_id="album-1",
            source_ref=ref,
            actor_user_id=USER,
            created_at=source.original_sent_at,
            media_ref=media(),
        )
    finish(lifecycle, job)
    assert not album_rows(env)


def test_optout_then_optin_cannot_revive_old_album(env, cached):
    source, ref = cached
    lifecycle = MemoryLifecycle(env.repo)
    finish(lifecycle, lifecycle.begin(CHAT, scope="subject", target=USER, optout=True))
    env.clock.now += 1
    subject = env.repo.get_subject(CHAT, USER)
    env.repo.opt_in(CHAT, USER, expected_revision=int(subject["revision"]))
    with pytest.raises(MemoryUnavailable):
        EphemeralMediaRepository(env.repo).store(
            chat_id=CHAT,
            media_group_id="album-1",
            source_ref=ref,
            actor_user_id=USER,
            created_at=source.original_sent_at,
            media_ref=media(),
        )
    assert not album_rows(env)


def test_new_epoch_rejects_saved_old_source_and_old_cache_snapshot(env, cached):
    source, ref = cached
    row = album_rows(env)[0]
    lifecycle = MemoryLifecycle(env.repo)
    finish(lifecycle, lifecycle.begin(CHAT, scope="group"))
    activate(env)
    env.table.put_item(Item=row)  # Simulate a delayed stale writer after the cutover.
    cache = EphemeralMediaRepository(env.repo)
    with pytest.raises(MemoryUnavailable):
        cache.get_refs(CHAT, "album-1")
    with pytest.raises(MemoryUnavailable):
        cache.store(
            chat_id=CHAT,
            media_group_id="album-1",
            source_ref=ref,
            actor_user_id=USER,
            created_at=source.original_sent_at,
            media_ref=media(),
        )


@pytest.mark.parametrize("ambiguous", [False, True])
def test_edit_invalidates_even_when_no_raw_or_fact_was_learned(env, cached, ambiguous):
    source, old_ref = cached
    env.clock.now += 1
    edited = replace(source, text="changed", edited_at=0 if ambiguous else env.clock.now)
    if ambiguous:
        with pytest.raises(MemoryConflict):
            env.repo.observe(edited)
    else:
        new_ref = env.repo.observe(edited)
        with pytest.raises(MemoryUnavailable):
            EphemeralMediaRepository(env.repo).store(
                chat_id=CHAT,
                media_group_id="album-1",
                source_ref=new_ref,
                actor_user_id=USER,
                created_at=source.original_sent_at,
                media_ref=media(),
            )
    with pytest.raises(MemoryUnavailable):
        EphemeralMediaRepository(env.repo).get_refs(CHAT, "album-1")


def test_pause_does_not_disable_explicit_ephemeral_media(env, cached):
    control = env.repo.get_control(CHAT)
    env.repo.set_learning_enabled(CHAT, False, expected_revision=int(control["revision"]))
    assert EphemeralMediaRepository(env.repo).get_refs(CHAT, "album-1")


def test_expired_item_is_rejected_before_dynamodb_ttl_deletes_it(env, cached):
    env.clock.now += MEDIA_RETENTION_SECONDS
    assert album_rows(env)
    with pytest.raises(MemoryUnavailable):
        EphemeralMediaRepository(env.repo).get_refs(CHAT, "album-1")


@pytest.mark.parametrize("operation", ["store", "get"])
def test_slow_final_transaction_does_not_return_expired_refs(env, cached, monkeypatch, operation):
    source, ref = cached
    original = env.repo._transaction

    def slow(operations):
        original(operations)
        env.clock.now = source.original_sent_at + MEDIA_RETENTION_SECONDS

    monkeypatch.setattr(env.repo, "_transaction", slow)
    cache = EphemeralMediaRepository(env.repo)
    with pytest.raises(MemoryUnavailable):
        if operation == "get":
            cache.get_refs(CHAT, "album-1")
        else:
            cache.store(
                chat_id=CHAT,
                media_group_id="album-1",
                source_ref=ref,
                actor_user_id=USER,
                created_at=source.original_sent_at,
                media_ref=media(),
            )


@pytest.mark.parametrize("operation", ["store", "get"])
def test_final_transaction_fences_concurrent_optout(env, cached, monkeypatch, operation):
    source, ref = cached
    original = env.repo._transaction
    once = False

    def race(operations):
        nonlocal once
        if not once:
            once = True
            subject = env.repo.get_subject(CHAT, USER)
            env.repo.begin_subject_stop(CHAT, USER, expected_revision=int(subject["revision"]), optout=True)
        return original(operations)

    monkeypatch.setattr(env.repo, "_transaction", race)
    with pytest.raises(MemoryConflict):
        cache = EphemeralMediaRepository(env.repo)
        if operation == "get":
            cache.get_refs(CHAT, "album-1")
        else:
            cache.store(
                chat_id=CHAT,
                media_group_id="album-1",
                source_ref=ref,
                actor_user_id=USER,
                created_at=source.original_sent_at,
                media_ref=media(),
            )


def test_same_album_id_in_different_chat_is_isolated(env, cached):
    other = -100456
    activate(env, other)
    store(env, message_id="77", actor="99", chat=other)
    cache = EphemeralMediaRepository(env.repo)
    assert [r["source_user_id"] for r in cache.get_refs(CHAT, "album-1")] == [USER]
    assert [r["source_user_id"] for r in cache.get_refs(other, "album-1")] == ["99"]


def test_mixed_actor_album_cannot_expand(env, cached):
    store(env, message_id="9", actor="99")
    with pytest.raises(MemoryUnavailable):
        EphemeralMediaRepository(env.repo).get_refs(CHAT, "album-1")


@pytest.mark.parametrize("oversized", [False, True])
def test_bounded_query_does_not_silently_accept_partial_inventory(env, cached, monkeypatch, oversized):
    rows = album_rows(env)
    response = {"Items": rows * 11} if oversized else {"Items": rows, "LastEvaluatedKey": {"pk": "x", "sk": "y"}}
    monkeypatch.setattr(env.repo.table, "query", lambda **kwargs: response)
    with pytest.raises(MemoryUnavailable):
        EphemeralMediaRepository(env.repo).get_refs(CHAT, "album-1")


@pytest.mark.parametrize("mutation", ["actor", "timestamp", "epoch", "source_version", "extra_body"])
def test_tampered_cache_row_fails_closed(env, cached, mutation):
    row = album_rows(env)[0]
    if mutation == "actor":
        row["actor_user_id"] = "99"
    elif mutation == "timestamp":
        row["created_at"] += 1
    elif mutation == "epoch":
        row["epoch"] = "old"
    elif mutation == "source_version":
        row["source_ref"]["source_version"] += 1
    else:
        row["media_ref"]["caption"] = "Must not return"
    env.table.put_item(Item=row)
    with pytest.raises(MemoryUnavailable):
        EphemeralMediaRepository(env.repo).get_refs(CHAT, "album-1")


def test_legacy_reply_calls_do_zero_io_and_settings_keep_working(env, overlay):
    overlay.set_chat_settings(CHAT, memory_enabled=False, agent_enabled=False)
    assert overlay.get_chat_settings(CHAT)["memory_enabled"] is False
    overlay.table = MagicMock()
    overlay.record_agent_reply(chat_id=CHAT, bot_message_id=55, answer_text="old response")
    assert overlay.get_agent_reply_explanation(CHAT, bot_message_id=55) == {}
    assert overlay.get_agent_reply_explanation(CHAT) == {}
    assert overlay.count_recent_agent_replies(CHAT, since_epoch=0) == 0
    assert not overlay.table.mock_calls


def test_overlay_album_writes_only_v2_and_keeps_legacy_business_rows(env, overlay):
    activate(env)
    source = event(env, text="")
    env.repo.observe(source)
    # Album handling cannot delete retired non-memory data as a side effect.
    business = {"pk": f"CHAT#{CHAT}", "sk": "CONTEST#1#META", "kind": "contest", "business": "unchanged"}
    overlay.table.put_item(Item=business)
    overlay.store_media_group_item(
        chat_id=CHAT, media_group_id="album-1", message_id=8, media_ref=media(), created_at=source.original_sent_at
    )
    assert overlay.get_media_group_refs(CHAT, "album-1")[0]["file_id"] == "file-8"
    assert overlay.table.scan()["Items"] == [business]


def test_no_control_or_v2_configuration_uses_direct_media_without_legacy_lookup(env, overlay):
    overlay.table = MagicMock()
    message = {"reply_to_message": {"message_id": 8, "media_group_id": "album-1", "photo": [{"file_id": "direct"}]}}
    for configured in (True, False):
        if not configured:
            overlay.ephemeral_media = None
        refs = detect_media_references(
            message, media_group_loader=lambda album: overlay.get_media_group_refs(CHAT, album)
        )
        assert [ref.file_id for ref in refs] == ["direct"]
        with pytest.raises(MemoryUnavailable):
            overlay.store_media_group_item(
                chat_id=CHAT, media_group_id="album-1", message_id=8, media_ref=media(), created_at=env.clock.now
            )
    assert not overlay.table.mock_calls
    assert not env.repo.get_subject(CHAT, USER)


def test_database_error_propagates_and_never_uses_legacy_album(env, overlay, cached, monkeypatch):
    overlay.table = MagicMock()

    def fail(**kwargs):
        raise ClientError({"Error": {"Code": "InternalServerError"}}, "Query")

    monkeypatch.setattr(env.repo.table, "query", fail)
    with pytest.raises(ClientError):
        overlay.get_media_group_refs(CHAT, "album-1")
    assert not overlay.table.mock_calls


def test_missing_source_does_not_create_subject_or_observation(env, overlay):
    activate(env)
    with pytest.raises(MemoryUnavailable):
        overlay.store_media_group_item(
            chat_id=CHAT, media_group_id="album-1", message_id=8, media_ref=media(), created_at=env.clock.now
        )
    assert not env.repo.get_subject(CHAT, USER)
    assert not env.repo.get_observation(CHAT, "8")


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_user_id", "99"),
        ("source_message_id", 9),
        ("media_group_id", "other"),
        ("file_id", ""),
        ("media_type", "unknown"),
        ("file_size", True),
    ],
)
def test_invalid_input_is_not_written(env, cached, field, value):
    source, ref = cached
    before = album_rows(env)
    with pytest.raises(MemoryInputError):
        EphemeralMediaRepository(env.repo).store(
            chat_id=CHAT,
            media_group_id="album-1",
            source_ref=ref,
            actor_user_id=USER,
            created_at=source.original_sent_at,
            media_ref={**media(), field: value},
        )
    assert album_rows(env) == before
