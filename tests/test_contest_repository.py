"""Contract tests for the DynamoDB contest truth owner."""

from unittest.mock import MagicMock, call

import pytest
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError
from services.repositories.contest import ContestRepository, RegistrationResult


def _repo() -> ContestRepository:
    repo = ContestRepository.__new__(ContestRepository)
    repo.table = MagicMock()
    repo.table.name = "memory-table"
    repo.table_name = "memory-table"
    repo.client = MagicMock()
    repo._serializer = TypeSerializer()
    return repo


def _client_error(code: str, *, cancellation_reasons: list[dict] | None = None) -> ClientError:
    response = {"Error": {"Code": code, "Message": code}}
    if cancellation_reasons is not None:
        response["CancellationReasons"] = cancellation_reasons
    elif code == "TransactionCanceledException":
        response["CancellationReasons"] = [{"Code": "ConditionalCheckFailed"}, {"Code": "None"}]
    return ClientError(response, "operation")


def _deserialize(item: dict) -> dict:
    deserializer = TypeDeserializer()
    return {key: deserializer.deserialize(value) for key, value in item.items()}


def test_create_contest_is_fail_closed_and_idempotent() -> None:
    repo = _repo()

    assert repo.create_contest(
        chat_id=-100123,
        root_message_id=11,
        source_channel_id=-100456,
        source_channel_title="Official",
        source_channel_username="official",
        source_channel_post_id=7,
        created_at=100,
    )

    kwargs = repo.table.put_item.call_args.kwargs
    assert kwargs["ConditionExpression"] == "attribute_not_exists(pk)"
    assert kwargs["Item"] == {
        "pk": "CHAT#-100123",
        "sk": "CONTEST#0000000000011#META",
        "kind": "contest",
        "chat_id": "-100123",
        "root_message_id": 11,
        "source_channel_id": "-100456",
        "source_channel_title": "Official",
        "source_channel_username": "official",
        "source_channel_post_id": 7,
        "status": "CREATING",
        "participant_count": 0,
        "draw_count": 0,
        "winner_user_ids": [],
        "winners": [],
        "created_at": 100,
        "updated_at": 100,
    }

    repo.table.put_item.side_effect = _client_error("ConditionalCheckFailedException")
    assert not repo.create_contest(
        chat_id=-100123,
        root_message_id=11,
        source_channel_id=-100456,
        source_channel_title=None,
        source_channel_username=None,
        source_channel_post_id=None,
        created_at=100,
    )


def test_activate_contest_atomically_attaches_rules_alias() -> None:
    repo = _repo()

    assert repo.activate_contest(-100123, 11, 99, attempt_id="create-a", now=200)

    tx = repo.client.transact_write_items.call_args.kwargs["TransactItems"]
    update = tx[0]["Update"]
    alias = _deserialize(tx[1]["Put"]["Item"])
    assert update["TableName"] == "memory-table"
    assert update["ConditionExpression"] == "#status = :creating AND creation_attempt_id = :attempt"
    assert _deserialize(update["Key"]) == {
        "pk": "CHAT#-100123",
        "sk": "CONTEST#0000000000011#META",
    }
    assert alias["sk"] == "CONTEST_RULE#0000000000099"
    assert alias["root_message_id"] == 11


def test_resolve_contest_by_rules_anchor_uses_strong_alias_lookup() -> None:
    repo = _repo()
    meta = {
        "pk": "CHAT#-100123",
        "sk": "CONTEST#0000000000011#META",
        "root_message_id": 11,
        "status": "OPEN",
    }
    repo.table.get_item.side_effect = [
        {},
        {"Item": {"root_message_id": 11}},
        {"Item": meta},
    ]

    assert repo.resolve_contest_by_anchor(-100123, 99) == meta
    assert repo.table.get_item.call_args_list[1].kwargs == {
        "Key": {"pk": "CHAT#-100123", "sk": "CONTEST_RULE#0000000000099"},
        "ConsistentRead": True,
    }
    assert repo.table.get_item.call_args_list[2].kwargs["ConsistentRead"] is True


def test_registration_transaction_checks_open_and_unique_user() -> None:
    repo = _repo()

    result = repo.register_participant(
        chat_id=-100123,
        root_message_id=11,
        user_id=42,
        entry_message_id=12,
        username="ada",
        first_name="Ada",
        last_name="Lovelace",
        text="Мен қатысамын!",
        accepted_at=300,
    )

    assert result is RegistrationResult.REGISTERED
    tx = repo.client.transact_write_items.call_args.kwargs["TransactItems"]
    counter = tx[0]["Update"]
    participant = _deserialize(tx[1]["Put"]["Item"])
    assert counter["ConditionExpression"] == "#status = :open"
    assert "participant_count = if_not_exists(participant_count, :zero) + :one" in counter["UpdateExpression"]
    assert _deserialize(counter["ExpressionAttributeValues"]) == {
        ":open": "OPEN",
        ":zero": 0,
        ":one": 1,
    }
    assert participant["sk"] == "CONTEST#0000000000011#PARTICIPANT#00000000000000000042"
    assert participant["entry_message_id"] == 12
    assert participant["text"] == "Мен қатысамын!"


def test_registration_preserves_full_telegram_text_limit_for_evidence() -> None:
    repo = _repo()
    text = "x" * (4096 - len("қатысамын")) + "қатысамын"

    assert (
        repo.register_participant(
            chat_id=-100123,
            root_message_id=11,
            user_id=42,
            entry_message_id=12,
            username=None,
            first_name="Ada",
            last_name=None,
            text=text,
            accepted_at=300,
        )
        is RegistrationResult.REGISTERED
    )

    tx = repo.client.transact_write_items.call_args.kwargs["TransactItems"]
    participant = _deserialize(tx[1]["Put"]["Item"])
    assert participant["text"] == text
    assert participant["text"].endswith("қатысамын")


def test_registration_condition_failure_distinguishes_duplicate_closed_and_missing() -> None:
    repo = _repo()
    repo.client.transact_write_items.side_effect = _client_error("TransactionCanceledException")
    args = dict(
        chat_id=-100123,
        root_message_id=11,
        user_id=42,
        entry_message_id=12,
        username=None,
        first_name="Ada",
        last_name=None,
        text="қатысамын",
        accepted_at=300,
    )

    repo.table.get_item.side_effect = [{"Item": {"kind": "contest_participant"}}]
    assert repo.register_participant(**args) is RegistrationResult.DUPLICATE

    repo.table.get_item.side_effect = [{}, {"Item": {"status": "DRAWN"}}]
    assert repo.register_participant(**args) is RegistrationResult.CLOSED

    repo.table.get_item.side_effect = [{}, {}]
    assert repo.register_participant(**args) is RegistrationResult.MISSING


def test_transaction_cancel_without_pure_condition_reason_is_retried_not_misclassified() -> None:
    repo = _repo()
    repo.client.transact_write_items.side_effect = _client_error(
        "TransactionCanceledException",
        cancellation_reasons=[{"Code": "TransactionConflict"}, {"Code": "None"}],
    )

    with pytest.raises(ClientError):
        repo.register_participant(
            chat_id=-100123,
            root_message_id=11,
            user_id=42,
            entry_message_id=12,
            username=None,
            first_name="Ada",
            last_name=None,
            text="қатысамын",
            accepted_at=300,
        )
    repo.table.get_item.assert_not_called()


def test_creation_attempt_lease_guards_activate_and_failure_paths() -> None:
    repo = _repo()

    assert repo.begin_creation_attempt(
        -100123,
        11,
        attempt_id="create-a",
        stale_before=90,
        now=100,
    )
    claim = repo.table.update_item.call_args.kwargs
    assert "attribute_not_exists(creation_attempt_id)" in claim["ConditionExpression"]
    assert claim["ExpressionAttributeValues"][":attempt"] == "create-a"

    assert repo.fail_creation(-100123, 11, attempt_id="create-a", now=101)
    failed = repo.table.update_item.call_args.kwargs
    assert "creation_attempt_id = :attempt" in failed["ConditionExpression"]


def test_iter_participants_reads_every_page_strongly_consistently() -> None:
    repo = _repo()
    repo.table.query.side_effect = [
        {"Items": [{"user_id": "1"}], "LastEvaluatedKey": {"pk": "CHAT#-100123", "sk": "one"}},
        {"Items": [{"user_id": "2"}]},
    ]

    assert [item["user_id"] for item in repo.iter_participants(-100123, 11)] == ["1", "2"]
    assert repo.table.query.call_count == 2
    assert repo.table.query.call_args_list[0].kwargs["ConsistentRead"] is True
    assert repo.table.query.call_args_list[1].kwargs["ExclusiveStartKey"]["sk"] == "one"


def test_first_draw_sets_one_immutable_expiry_and_pending_announcement() -> None:
    repo = _repo()
    participant = {"user_id": "42", "entry_message_id": 12, "text": "қатысамын", "first_name": "Ada"}

    assert repo.begin_first_draw(-100123, 11, attempt_id="draw-a", now=400)
    assert repo.complete_draw(
        -100123,
        11,
        draw_number=1,
        attempt_id="draw-a",
        participant=participant,
        frozen_participant_count=5,
        now=500,
    )

    begin = repo.table.update_item.call_args_list[0].kwargs
    transaction = repo.client.transact_write_items.call_args.kwargs["TransactItems"]
    complete = transaction[0]["Update"]
    outbox = _deserialize(transaction[1]["Put"]["Item"])
    complete_values = _deserialize(complete["ExpressionAttributeValues"])
    assert begin["ConditionExpression"] == "#status = :open AND draw_count = :zero"
    assert begin["ExpressionAttributeValues"][":attempt"] == "draw-a"
    assert "draw_attempt_id = :attempt" in complete["ConditionExpression"]
    assert "participant_count = :count" in complete["ConditionExpression"]
    assert "attribute_not_exists(expires_at)" in complete["ConditionExpression"]
    assert complete_values[":expires"] == 500 + 30 * 24 * 60 * 60
    assert complete_values[":pending"] == "PENDING"
    assert complete_values[":count"] == 5
    assert ":previous" not in complete_values
    assert ":single_winner_id" not in complete_values
    assert outbox == {
        "pk": "CONTEST_TTL_OUTBOX",
        "sk": "CHAT#-100123#ROOT#0000000000011",
        "kind": "contest_ttl_outbox",
        "chat_id": "-100123",
        "root_message_id": 11,
        "expires_at": 500 + 30 * 24 * 60 * 60,
        "created_at": 500,
    }
    assert "ttl" not in outbox


def test_redraw_never_extends_expiry_and_rejects_repeated_winner_at_write_boundary() -> None:
    repo = _repo()
    participant = {"user_id": "43", "entry_message_id": 13, "text": "қатысамын"}

    assert repo.begin_redraw(-100123, 11, expected_draw_count=1, attempt_id="draw-b", now=600)
    assert repo.complete_draw(
        -100123,
        11,
        draw_number=2,
        attempt_id="draw-b",
        participant=participant,
        frozen_participant_count=5,
        now=700,
    )

    begin = repo.table.update_item.call_args_list[0].kwargs
    complete = repo.table.update_item.call_args_list[1].kwargs
    assert "expires_at > :now" in begin["ConditionExpression"]
    assert begin["ExpressionAttributeValues"][":attempt"] == "draw-b"
    assert "draw_attempt_id = :attempt" in complete["ConditionExpression"]
    assert "expires_at" not in complete["UpdateExpression"]
    assert "NOT contains(winner_user_ids, :single_winner_id)" in complete["ConditionExpression"]
    assert "expires_at > :now" in complete["ConditionExpression"]


def test_abort_announcement_and_cancel_transitions_are_guarded() -> None:
    repo = _repo()

    assert repo.abort_draw(-100123, 11, draw_number=2, attempt_id="draw-b", now=710)
    abort = repo.table.update_item.call_args.kwargs
    assert "draw_attempt_id = :attempt" in abort["ConditionExpression"]
    assert abort["ExpressionAttributeValues"][":restore"] == "DRAWN"

    assert repo.mark_announcement_sent(
        -100123,
        11,
        draw_number=2,
        announcement_message_id=901,
        now=720,
    )
    announcement = repo.table.update_item.call_args.kwargs
    assert "announcement_state = :pending" in announcement["ConditionExpression"]
    assert "winners[1].announcement_message_id" in announcement["UpdateExpression"]

    repo.table.get_item.return_value = {
        "Item": {
            "chat_id": "-100123",
            "root_message_id": 11,
            "status": "CANCELLED",
            "expires_at": 730 + 30 * 24 * 60 * 60,
            "ttl_sweep_status": "PENDING",
        }
    }
    cancelled = repo.cancel_contest(-100123, 11, now=730)
    assert cancelled and cancelled["status"] == "CANCELLED"
    cancel_tx = repo.client.transact_write_items.call_args.kwargs["TransactItems"]
    cancel = cancel_tx[0]["Update"]
    cancel_values = _deserialize(cancel["ExpressionAttributeValues"])
    cancel_outbox = _deserialize(cancel_tx[1]["Put"]["Item"])
    assert cancel["ConditionExpression"] == "#status = :open AND attribute_not_exists(expires_at)"
    assert cancel_values[":expires"] == 730 + 30 * 24 * 60 * 60
    assert cancel_outbox["sk"] == "CHAT#-100123#ROOT#0000000000011"


def test_orphan_is_terminal_at_repository_transition() -> None:
    repo = _repo()

    assert repo.mark_orphaned(-100123, 11, draw_number=1, now=800)

    kwargs = repo.table.update_item.call_args.kwargs
    assert kwargs["ExpressionAttributeValues"][":orphaned"] == "ORPHANED"
    assert kwargs["ConditionExpression"] == (
        "#status = :drawn AND draw_count = :draw AND announcement_state = :pending"
    )


def test_ttl_outbox_page_is_global_strong_and_resumable() -> None:
    repo = _repo()
    cursor = {
        "pk": "CONTEST_TTL_OUTBOX",
        "sk": "CHAT#-100123#ROOT#0000000000011",
    }
    marker = {**cursor, "chat_id": "-100123", "root_message_id": 11}
    repo.table.query.return_value = {"Items": [marker], "LastEvaluatedKey": cursor}

    page, next_key = repo.ttl_outbox_page(limit=25, start_key=cursor)

    assert page == [marker]
    assert next_key == cursor
    kwargs = repo.table.query.call_args.kwargs
    assert kwargs["ConsistentRead"] is True
    assert kwargs["Limit"] == 25
    assert kwargs["ExclusiveStartKey"] == cursor


def test_ttl_sweep_is_idempotent_and_completes_alias_before_meta() -> None:
    repo = _repo()
    items = [
        {"pk": "CHAT#-100123", "sk": "CONTEST#0000000000011#PARTICIPANT#00000000000000000042"},
        {"pk": "CHAT#-100123", "sk": "CONTEST#0000000000011#PARTICIPANT#00000000000000000043"},
    ]

    repo.stamp_participant_ttl(items, 999)
    repo.record_ttl_sweep_progress(
        -100123,
        11,
        expected_start_key=None,
        expected_version=0,
        next_start_key={"pk": "CHAT#-100123", "sk": items[-1]["sk"]},
        now=900,
    )
    repo.complete_ttl_sweep(
        -100123,
        11,
        rules_message_id=99,
        expires_at=999,
        expected_start_key={"pk": "CHAT#-100123", "sk": items[-1]["sk"]},
        expected_version=1,
        now=901,
    )

    assert repo.table.update_item.call_args_list[:2] == [
        call(
            Key={"pk": item["pk"], "sk": item["sk"]},
            UpdateExpression="SET expires_at = :expires, #ttl = :expires",
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={":expires": 999},
        )
        for item in items
    ]
    alias_call = repo.table.update_item.call_args_list[-1].kwargs
    sweep_tx = repo.client.transact_write_items.call_args.kwargs["TransactItems"]
    meta_call = sweep_tx[0]["Update"]
    outbox_delete = _deserialize(sweep_tx[1]["Delete"]["Key"])
    assert alias_call["Key"]["sk"] == "CONTEST_RULE#0000000000099"
    assert _deserialize(meta_call["ExpressionAttributeValues"])[":complete"] == "COMPLETE"
    assert "REMOVE ttl_sweep_cursor" in meta_call["UpdateExpression"]
    assert "ttl_sweep_version = :version" in meta_call["ConditionExpression"]
    assert outbox_delete == {
        "pk": "CONTEST_TTL_OUTBOX",
        "sk": "CHAT#-100123#ROOT#0000000000011",
    }


def test_stale_ttl_worker_cannot_move_cursor_or_reopen_complete_sweep() -> None:
    repo = _repo()
    repo.table.update_item.side_effect = _client_error("ConditionalCheckFailedException")

    assert not repo.record_ttl_sweep_progress(
        -100123,
        11,
        expected_start_key={"pk": "CHAT#-100123", "sk": "old"},
        expected_version=1,
        next_start_key={"pk": "CHAT#-100123", "sk": "next"},
    )
    repo.client.transact_write_items.side_effect = _client_error("TransactionCanceledException")
    assert not repo.complete_ttl_sweep(
        -100123,
        11,
        rules_message_id=None,
        expires_at=999,
        expected_start_key={"pk": "CHAT#-100123", "sk": "old"},
        expected_version=1,
    )


def test_logical_expiry_wins_before_physical_ttl_deletion() -> None:
    assert ContestRepository.is_logically_expired({"expires_at": 100}, now=100)
    assert not ContestRepository.is_logically_expired({"expires_at": 101}, now=100)
    assert not ContestRepository.is_logically_expired({}, now=100)
