"""DynamoDB request contracts for the moderation state owner."""

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from services.repositories.spam import SpamLeaseBusyError, SpamRepository, source_reference


def _repo():
    repo = SpamRepository.__new__(SpamRepository)
    repo.table = MagicMock()
    repo.table.name = "stats-table"
    repo.client = MagicMock()
    return repo


def _body():
    return {
        "chat_id": -1001,
        "user_id": 42,
        "message_id": 10,
        "text": "private source text",
        "source_ref": {"source_id": "10", "source_version": 1, "epoch": "epoch-1"},
    }


def test_case_identity_binds_chat_actor_message_revision_and_input_without_storing_text():
    repo = _repo()
    first = repo.ensure_case(_body())
    assert "private source text" not in str(first)
    assert first["source_ref"] == _body()["source_ref"]
    assert repo.table.put_item.call_args.kwargs["ConditionExpression"] == "attribute_not_exists(stat_key)"
    for changed in (
        {"chat_id": -1002},
        {"user_id": 43},
        {"source_ref": {"source_id": "10", "source_version": 2, "epoch": "epoch-1"}},
        {"text": "edited text"},
    ):
        assert repo.ensure_case({**_body(), **changed})["case_id"] != first["case_id"]


@pytest.mark.parametrize(
    "ref",
    [
        None,
        {},
        {"source_id": "11", "source_version": 1, "epoch": "e"},
        {"source_id": "10", "source_version": True, "epoch": "e"},
        {"source_id": "10", "source_version": "1", "epoch": "e"},
    ],
)
def test_malformed_reference_cannot_be_accepted_as_a_versioned_source(ref):
    if ref is None:
        assert source_reference({**_body(), "source_ref": ref}) is None
    else:
        with pytest.raises(ValueError):
            source_reference({**_body(), "source_ref": ref})


def test_duplicate_creation_strongly_reads_the_existing_receipt():
    repo = _repo()
    repo.table.put_item.side_effect = ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
    repo.table.get_item.return_value = {"Item": {"state": "clean"}}
    assert repo.ensure_case(_body()) == {"state": "clean"}
    assert repo.table.get_item.call_args.kwargs["ConsistentRead"] is True


def test_lease_contention_is_retryable_and_storage_outages_are_not_contention():
    repo = _repo()
    repo.table.update_item.side_effect = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem"
    )
    with pytest.raises(SpamLeaseBusyError):
        repo.claim("decision#test")
    repo.table.update_item.side_effect = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException"}}, "UpdateItem"
    )
    with pytest.raises(ClientError):
        repo.claim("decision#test")


def test_confirmed_ban_and_counter_share_one_conditional_transaction():
    repo = _repo()
    repo.confirm_ban("action#test", "lease-1", -1001)
    transaction = repo.client.transact_write_items.call_args.kwargs["TransactItems"]
    assert len(transaction) == 2
    action, counter = [item["Update"] for item in transaction]
    assert action["Key"] == {"stat_key": "spam_case#action#test"}
    assert action["ConditionExpression"] == "lease_owner = :owner AND #state <> :banned"
    assert counter["Key"] == {"stat_key": "-1001"}
    assert "spam_bans" in counter["UpdateExpression"]
    repo.table.update_item.assert_not_called()


def test_pending_clean_has_no_ttl_and_ack_requires_exact_scope_and_revision():
    repo = _repo()
    case = {"case_id": "decision#test", "source_ref": _body()["source_ref"]}
    repo.finish_clean(case, "lease")
    request = repo.table.update_item.call_args.kwargs
    assert "REMOVE #ttl" in request["UpdateExpression"]
    assert request["ExpressionAttributeNames"]["#ttl"] == "ttl"
    repo.acknowledge_clean(
        "decision#test", _body()["source_ref"], chat_id=-1001, user_id=42, message_id=10, outcome="EXPIRED"
    )
    request = repo.table.update_item.call_args.kwargs
    for field in ("source_ref", "chat_id", "user_id", "message_id", "outbox_pending", "recovery_outcome"):
        assert field in request["ConditionExpression"]
    assert request["ExpressionAttributeValues"][":outcome"] == "EXPIRED"
    assert "#ttl = :ttl" in request["UpdateExpression"]
    assert request["ExpressionAttributeNames"]["#ttl"] == "ttl"


def test_pending_clean_recovery_scan_is_bounded_and_returns_a_cursor():
    repo = _repo()
    cursor = {"stat_key": "next"}
    repo.table.scan.return_value = {"Items": [{"case_id": "clean"}], "LastEvaluatedKey": cursor}
    assert repo.list_clean_pending(limit=10000) == ([{"case_id": "clean"}], cursor)
    assert repo.table.scan.call_args.kwargs["Limit"] == 100
    repo.list_clean_pending(cursor=cursor)
    assert repo.table.scan.call_args.kwargs["ExclusiveStartKey"] == cursor
