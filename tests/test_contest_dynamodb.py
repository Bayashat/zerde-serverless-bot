"""Real SDK serialization + simulated DynamoDB semantics; no AWS/Telegram calls."""

import json

import boto3
import pytest
from moto import mock_aws
from services.repositories.contest import ContestRepository, RegistrationResult


@pytest.fixture
def repo(monkeypatch):
    with mock_aws():
        dynamodb = boto3.resource(
            "dynamodb", region_name="eu-central-1", aws_access_key_id="synthetic", aws_secret_access_key="synthetic"
        )
        dynamodb.create_table(
            TableName="contest-test",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setattr("services.repositories.contest.get_dynamodb", lambda: dynamodb)
        yield ContestRepository("contest-test")


def open_contest(repo, root=11):
    assert repo.create_contest(
        chat_id=-1001,
        root_message_id=root,
        source_channel_id=-2001,
        source_channel_title="Synthetic",
        source_channel_username=None,
        source_channel_post_id=1,
        created_at=100,
    )
    assert repo.begin_creation_attempt(-1001, root, attempt_id="create", now=101, stale_before=1)
    assert repo.activate_contest(-1001, root, 1000 + root, attempt_id="create", now=102)
    assert repo.resolve_contest_by_anchor(-1001, 1000 + root)["root_message_id"] == root


def register(repo, user=42, message=20):
    return repo.register_participant(
        chat_id=-1001,
        root_message_id=11,
        user_id=user,
        entry_message_id=message,
        username=None,
        first_name="Synthetic",
        last_name=None,
        text="қатысамын",
        accepted_at=103,
    )


def test_sdk_serializes_transaction_keys_once_and_alias_activation_is_atomic(repo):
    calls = []
    repo.client.meta.events.register(
        "before-call.dynamodb.TransactWriteItems", lambda params, **kwargs: calls.append(json.loads(params["body"]))
    )
    open_contest(repo)
    assert calls[0]["TransactItems"][0]["Update"]["Key"]["pk"] == {"S": "CHAT#-1001"}
    assert calls[0]["TransactItems"][0]["Update"]["ExpressionAttributeValues"][":rules"] == {"N": "1011"}
    # A lost response replay reports the same anchor, never a different rules message.
    assert repo.activate_contest(-1001, 11, 1011, attempt_id="create", now=104)
    assert not repo.activate_contest(-1001, 11, 9999, attempt_id="wrong", now=104)
    assert not repo.table.get_item(Key={"pk": "CHAT#-1001", "sk": repo._rule_anchor_sk(9999)}).get("Item")


def test_registration_replay_and_duplicate_never_inflate_count(repo):
    open_contest(repo)
    assert register(repo) == RegistrationResult.REGISTERED
    assert register(repo) == RegistrationResult.REPLAY
    assert register(repo, message=21) == RegistrationResult.DUPLICATE
    assert register(repo, user=43, message=22) == RegistrationResult.REGISTERED
    assert repo.get_contest(-1001, 11, consistent=True)["participant_count"] == 2
    assert len(list(repo.iter_participants(-1001, 11))) == 2
    assert repo.begin_first_draw(-1001, 11, attempt_id="draw", now=104)
    assert register(repo, user=44, message=23) == RegistrationResult.CLOSED
    assert repo.get_contest(-1001, 11, consistent=True)["participant_count"] == 2


def test_first_draw_persists_winner_and_outbox_then_ttl_completion_atomically(repo):
    open_contest(repo)
    assert register(repo) == RegistrationResult.REGISTERED
    assert repo.begin_first_draw(-1001, 11, attempt_id="draw", now=104)
    participant = repo.get_participant(-1001, 11, 42, consistent=True)
    args = dict(draw_number=1, attempt_id="draw", participant=participant, frozen_participant_count=1, now=105)
    assert repo.complete_draw(-1001, 11, **args)
    assert not repo.complete_draw(-1001, 11, **args)
    state = repo.get_contest(-1001, 11, consistent=True)
    assert state["winner_user_ids"] == ["42"]
    assert state["announcement_state"] == "PENDING"
    marker = repo.table.get_item(Key=repo._ttl_outbox_key(-1001, 11))["Item"]
    assert marker["expires_at"] == state["expires_at"]
    assert "ttl" not in state and "ttl" not in marker
    repo.stamp_participant_ttl([participant], state["expires_at"])
    args = dict(rules_message_id=1011, expires_at=int(state["expires_at"]), expected_start_key=None, now=106)
    # A stale worker must leave the durable outbox available.
    assert not repo.complete_ttl_sweep(-1001, 11, expected_version=7, **args)
    assert repo.table.get_item(Key=repo._ttl_outbox_key(-1001, 11)).get("Item")
    assert repo.complete_ttl_sweep(-1001, 11, expected_version=0, **args)
    assert not repo.table.get_item(Key=repo._ttl_outbox_key(-1001, 11)).get("Item")
    state = repo.get_contest(-1001, 11, consistent=True)
    assert state["ttl_sweep_status"] == "COMPLETE"
    assert state["ttl"] == state["expires_at"]


def test_cancellation_and_outbox_are_atomic_and_do_not_reopen(repo):
    open_contest(repo)
    state = repo.cancel_contest(-1001, 11, now=104)
    assert state["status"] == "CANCELLED"
    assert repo.cancel_contest(-1001, 11, now=105) is None
    assert register(repo) == RegistrationResult.CLOSED
    marker = repo.table.get_item(Key=repo._ttl_outbox_key(-1001, 11))["Item"]
    assert marker["expires_at"] == state["expires_at"]
    assert "ttl" not in marker
