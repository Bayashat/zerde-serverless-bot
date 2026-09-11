"""Exercise the real boto3 resource serializer and moderation transactions."""

from unittest.mock import MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws
from services.repositories import spam
from services.spam.enforcer import SpamEnforcer


@pytest.fixture
def actual_repo(monkeypatch):
    with mock_aws():
        resource = boto3.resource(
            "dynamodb", region_name="eu-central-1", aws_access_key_id="fake", aws_secret_access_key="fake"
        )
        resource.create_table(
            TableName="spam-test-stats",
            KeySchema=[{"AttributeName": "stat_key", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "stat_key", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setattr(spam, "get_dynamodb", lambda: resource)
        monkeypatch.setattr(spam, "STATS_TABLE_NAME", "spam-test-stats")
        yield spam.SpamRepository()


def test_actual_resource_transaction_commits_ban_and_counter_once(actual_repo):
    action = actual_repo.ensure_action(-1001, 42, 10, permanent=True, until_date=0)
    owner, _ = actual_repo.claim(action["case_id"])
    actual_repo.confirm_ban(action["case_id"], owner, -1001)
    assert actual_repo.get(action["case_id"])["state"] == "banned"
    assert actual_repo.table.get_item(Key={"stat_key": "-1001"})["Item"]["spam_bans"] == 1
    with pytest.raises(ClientError):
        actual_repo.confirm_ban(action["case_id"], owner, -1001)
    assert actual_repo.table.get_item(Key={"stat_key": "-1001"})["Item"]["spam_bans"] == 1


def test_actual_resource_replays_enforcement_without_another_ban_or_counter(actual_repo):
    bot = MagicMock()
    bot.get_chat_member.return_value = {"status": "member"}
    enforcer = SpamEnforcer(bot, actual_repo)
    assert enforcer.enforce(-1001, 42, 10, "spam", permanent=True).banned
    assert enforcer.enforce(-1001, 42, 10, "spam", permanent=True).banned
    assert bot.ban_chat_member.call_count == 1
    assert actual_repo.table.get_item(Key={"stat_key": "-1001"})["Item"]["spam_bans"] == 1


def test_actual_clean_outbox_rejects_wrong_revision_scope_and_conflicting_ack(actual_repo):
    ref = {"source_id": "10", "source_version": 1, "epoch": "epoch"}
    case = actual_repo.ensure_case(
        {"chat_id": -1001, "user_id": 42, "message_id": 10, "text": "synthetic", "source_ref": ref}
    )
    owner, case = actual_repo.claim(case["case_id"])
    actual_repo.finish_clean(case, owner)
    actual_repo.release(case["case_id"], owner)
    assert "ttl" not in actual_repo.get(case["case_id"])
    assert len(actual_repo.list_clean_pending()[0]) == 1
    scope = {"chat_id": -1001, "user_id": 42, "message_id": 10, "outcome": "INGESTED"}
    for changed in ({"chat_id": -1002}, {"user_id": 43}, {"message_id": 11}):
        with pytest.raises(ClientError):
            actual_repo.acknowledge_clean(case["case_id"], ref, **{**scope, **changed})
    with pytest.raises(ClientError):
        actual_repo.acknowledge_clean(case["case_id"], {**ref, "source_version": 2}, **scope)
    actual_repo.acknowledge_clean(case["case_id"], ref, **scope)
    actual_repo.acknowledge_clean(case["case_id"], ref, **scope)
    assert actual_repo.list_clean_pending()[0] == []
    assert "ttl" in actual_repo.get(case["case_id"])
    with pytest.raises(ClientError):
        actual_repo.acknowledge_clean(case["case_id"], ref, **{**scope, "outcome": "EXPIRED"})
