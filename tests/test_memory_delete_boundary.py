"""Legacy deletion contracts using Moto DynamoDB, never live AWS."""

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws
from services.handlers import commands
from services.memory_retrieval import MemoryCandidate, _hydrate_candidate_feedback
from services.repositories import group_memory as repository
from services.vector_memory import memory_vector_key, recover_pending_memory_vector_deletes

CHAT = -100123
OTHER_CHAT = -100456
USER = 42
FACT = "USER_FACT#42#1700000000000#8"


@pytest.fixture
def env(monkeypatch):
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="eu-central-1")
        table = dynamodb.create_table(
            TableName="memory-delete-test",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"} for key in ("pk", "sk")],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setattr(repository, "get_dynamodb", lambda: dynamodb)
        from services import vector_memory

        monkeypatch.setattr(vector_memory, "vector_memory_configured", lambda: True)
        vector = MagicMock()
        vector.delete_vectors.side_effect = lambda keys: len(keys)
        yield SimpleNamespace(repo=repository.GroupMemoryRepository(table.name), table=table, vector=vector)


def put(env, sk, *, chat=CHAT, **fields):
    item = {"pk": f"CHAT#{chat}", "sk": sk, **fields}
    env.table.put_item(Item=item)
    return item


def contents(env):
    response = env.table.scan(ConsistentRead=True)
    return {(item["pk"], item["sk"]): item for item in response["Items"]}


def digest(rows):
    return hashlib.sha256(
        json.dumps(sorted(rows, key=lambda row: (row["pk"], row["sk"])), sort_keys=True, default=str).encode()
    ).hexdigest()


def seed_mixed_partition(env):
    business = [
        put(env, "SETTINGS", user_id=str(USER), style_profile={"tone": "friendly"}),
        put(env, "CONTEST#8#META", message_id=8, user_id=str(USER)),
        put(env, "CONTEST#8#PARTICIPANT#42", message_id=8, user_id=str(USER)),
        put(env, "CONTEST_RULE#8", source_user_id=str(USER)),
        put(env, "CONTEST_TTL_OUTBOX", user_id=str(USER)),
        put(env, "UNKNOWN#8", user_id=str(USER)),
        put(env, "SETTINGS", chat=OTHER_CHAT),
        put(env, FACT, chat=OTHER_CHAT, user_id=str(USER)),
        {"pk": "CONTEST_TTL_OUTBOX", "sk": f"CHAT#{CHAT}#ROOT#8", "user_id": str(USER)},
    ]
    env.table.put_item(Item=business[-1])
    personal = [
        put(env, "USER#42", username="reassigned"),
        put(env, "USERNAME#ada", target_sk="USER#42", user_id="42"),
        put(env, "USERNAME#oldada", target_sk="USER#42"),
        put(env, "MSG#1700000000000#8", user_id="42", message_id=8),
        put(env, "MEDIA_GROUP#album#8", user_id="42", message_id=8),
        put(
            env,
            FACT,
            user_id="42",
            message_id=8,
            summary="I use Python.",
            created_at=1700000000,
            lexical_index_terms=["python"],
        ),
    ]
    lexical = put(env, "TERM#python#1700000000000#" + FACT, source_sk=FACT)
    shared = [
        put(env, "GROUP_FACT#1700000000000#8", user_id="42", message_id=8, summary="The group chose Python."),
        put(env, "DAILY_SUMMARY#2026-09-10", summary="Ada and Grace discussed Python.", user_id="42"),
        put(env, "USER_FACT#99#1700000000000#8", user_id="42", summary="Grace uses Java."),
        put(env, "USERNAME#reassigned", target_sk="USER#99", user_id="99"),
        put(
            env,
            "TERM#java#1700000000000#USER_FACT#99#1700000000000#8",
            source_user_id="42",
            source_sk="USER_FACT#99#1700000000000#8",
        ),
    ]
    return business, personal, lexical, shared


@pytest.mark.parametrize("scope", ["user", "group", "message", "explicit"])
def test_forget_scope_never_changes_business_or_other_chat(env, scope):
    business, personal, lexical, shared = seed_mixed_partition(env)
    initial = contents(env)
    before = digest([initial[(item["pk"], item["sk"])] for item in business])
    if scope == "user":
        assert env.repo.delete_user_memory(CHAT, USER) == 4
    elif scope == "group":
        env.repo.delete_chat_memory(CHAT)
    elif scope == "message":
        env.repo.delete_memory_for_message(CHAT, 8)
    else:
        # Even a forged or stale bot retrieval source cannot delete business rows.
        env.repo.delete_memory_items_by_sks(CHAT, [item["sk"] for item in business] + [FACT])
    after = contents(env)
    assert digest([after[(item["pk"], item["sk"])] for item in business]) == before
    if scope == "user":
        assert all((item["pk"], item["sk"]) not in after for item in personal + [lexical])
        assert all(after[(item["pk"], item["sk"])] == item for item in shared)
    assert env.repo.list_pending_vector_deletes(CHAT)


def test_group_delete_paginates_without_deleting_marker_or_unknown_business(env):
    for index in range(205):
        put(env, f"MSG#{index:013d}#{index}", user_id="42")
    protected = put(env, "CONTEST#late#META")
    put(env, FACT, summary="Python")
    assert env.repo.delete_chat_memory(CHAT) == 206
    assert env.repo.get_memory_item(CHAT, protected["sk"]) == protected
    assert len(env.repo.list_pending_vector_deletes(CHAT)) == 1
    assert env.repo.delete_chat_memory(CHAT) == 0
    assert len(env.repo.list_pending_vector_deletes(CHAT)) == 1


def test_transaction_failure_keeps_source_and_does_not_create_partial_marker(env, monkeypatch):
    item = put(env, FACT, summary="Python")
    real = env.table.meta.client.transact_write_items

    def fail_transaction(**kwargs):
        # A failing condition in the same service transaction verifies rollback.
        kwargs["TransactItems"].append(
            {
                "ConditionCheck": {
                    "TableName": env.table.name,
                    "Key": {"pk": "guard", "sk": "absent"},
                    "ConditionExpression": "attribute_exists(pk)",
                }
            }
        )
        return real(**kwargs)

    monkeypatch.setattr(env.table.meta.client, "transact_write_items", fail_transaction)
    with pytest.raises(ClientError):
        env.repo.delete_memory_items_by_sks(CHAT, [FACT])
    assert env.repo.get_memory_item(CHAT, FACT) == item
    assert env.repo.list_pending_vector_deletes(CHAT) == []


def test_vector_failure_retains_reference_only_work_then_retry_after_source_gone(env):
    put(env, FACT, summary="Private memory text must not enter marker")
    env.repo.delete_memory_items_by_sks(CHAT, [FACT])
    marker = env.repo.list_pending_vector_deletes(CHAT)[0]
    assert set(marker) == {"pk", "sk", "chat_id", "vector_key", "generation", "created_at"}
    assert marker["vector_key"] == memory_vector_key(CHAT, FACT)
    env.vector.delete_vectors.side_effect = RuntimeError("synthetic provider failure")
    with pytest.raises(RuntimeError):
        recover_pending_memory_vector_deletes(CHAT, repo=env.repo, vector_repo=env.vector)
    assert not env.repo.get_memory_item(CHAT, FACT)
    assert env.repo.list_pending_vector_deletes(CHAT) == [marker]
    # Retry works even though repeating the source deletion finds nothing.
    assert env.repo.delete_memory_items_by_sks(CHAT, [FACT]) == []
    env.vector.delete_vectors.side_effect = lambda keys: len(keys)
    assert recover_pending_memory_vector_deletes(CHAT, repo=env.repo, vector_repo=env.vector) == 1
    assert env.repo.list_pending_vector_deletes(CHAT) == []


def test_lost_vector_response_is_safe_to_replay(env):
    put(env, FACT, summary="Python")
    env.repo.delete_memory_items_by_sks(CHAT, [FACT])
    existing = {memory_vector_key(CHAT, FACT)}

    def delete_then_timeout(keys):
        existing.difference_update(keys)
        raise TimeoutError("response lost")

    env.vector.delete_vectors.side_effect = delete_then_timeout
    with pytest.raises(TimeoutError):
        recover_pending_memory_vector_deletes(CHAT, repo=env.repo, vector_repo=env.vector)
    assert existing == set()
    assert env.repo.list_pending_vector_deletes(CHAT)
    env.vector.delete_vectors.side_effect = lambda keys: len(keys)
    assert recover_pending_memory_vector_deletes(CHAT, repo=env.repo, vector_repo=env.vector) == 1


def test_stale_recovery_cannot_ack_a_replacement_marker(env):
    put(env, FACT, summary="Python")
    env.repo.delete_memory_items_by_sks(CHAT, [FACT])
    old = env.repo.list_pending_vector_deletes(CHAT)[0]
    env.table.put_item(Item={**old, "generation": "new-request"})
    assert env.repo.complete_vector_delete(CHAT, old) is False
    assert env.repo.list_pending_vector_deletes(CHAT)[0]["generation"] == "new-request"


def test_disabled_vector_index_never_discards_pending_work(env, monkeypatch):
    from services import vector_memory

    put(env, FACT, summary="Python")
    env.repo.delete_memory_items_by_sks(CHAT, [FACT])
    monkeypatch.setattr(vector_memory, "vector_memory_configured", lambda: False)
    with pytest.raises(RuntimeError, match="configured legacy index"):
        recover_pending_memory_vector_deletes(CHAT, repo=env.repo, vector_repo=env.vector)
    env.vector.delete_vectors.assert_not_called()
    assert env.repo.list_pending_vector_deletes(CHAT)


@pytest.mark.parametrize(
    "source",
    [
        {},
        {"summary": "expired", "ttl": 0},
        {"summary": "invalid", "ttl": "bad"},
        {"summary": "expired", "ttl": 1},
        {"summary": "expired", "expires_at": 1},
        RuntimeError("DDB down"),
    ],
)
def test_orphan_expired_or_unreadable_vector_source_cannot_enter_prompt(env, monkeypatch, source):
    candidate = MemoryCandidate(
        source="semantic",
        source_sk=FACT,
        memory_kind="user_fact",
        text="Stale vector text",
        score=1,
        trust_level=60,
        created_at=None,
        metadata={},
    )
    if isinstance(source, Exception):
        monkeypatch.setattr(env.repo, "get_memory_item", MagicMock(side_effect=source))
    elif source:
        put(env, FACT, **source)
    assert _hydrate_candidate_feedback(env.repo, CHAT, candidate) is None


def test_semantic_candidate_uses_current_source_text(env):
    put(env, FACT, summary="Current Python fact")
    candidate = MemoryCandidate(
        source="semantic",
        source_sk=FACT,
        memory_kind="user_fact",
        text="Stale vector fact",
        score=1,
        trust_level=60,
        created_at=None,
        metadata={},
    )
    assert _hydrate_candidate_feedback(env.repo, CHAT, candidate).text == "Current Python fact"


def test_command_reports_vector_pending_and_retries_after_deletion(env, monkeypatch):
    put(env, FACT, summary="Python")
    ctx = SimpleNamespace(
        memory_repo=env.repo, chat_id=CHAT, user_id=USER, lang_code="en", message_id=100, reply=MagicMock()
    )
    monkeypatch.setattr(commands, "_require_memory_repo", lambda _: True)
    monkeypatch.setattr(
        commands,
        "recover_pending_memory_vector_deletes",
        lambda chat, repo: recover_pending_memory_vector_deletes(chat, repo=repo, vector_repo=env.vector),
    )
    env.vector.delete_vectors.side_effect = RuntimeError("synthetic failure")
    commands.handle_forget_me(ctx)
    assert "Cleanup is incomplete" in ctx.reply.call_args.args[0]
    assert env.repo.list_pending_vector_deletes(CHAT)
    env.vector.delete_vectors.side_effect = lambda keys: len(keys)
    commands.handle_forget_me(ctx)
    assert "Cleanup is incomplete" not in ctx.reply.call_args.args[0]
    assert env.repo.list_pending_vector_deletes(CHAT) == []


def test_lost_outbox_ack_keeps_retryable_marker(env, monkeypatch):
    put(env, FACT, summary="Python")
    env.repo.delete_memory_items_by_sks(CHAT, [FACT])
    complete = env.repo.complete_vector_delete
    monkeypatch.setattr(env.repo, "complete_vector_delete", MagicMock(side_effect=TimeoutError("DDB ack lost")))
    with pytest.raises(TimeoutError):
        recover_pending_memory_vector_deletes(CHAT, repo=env.repo, vector_repo=env.vector)
    assert env.repo.list_pending_vector_deletes(CHAT)
    monkeypatch.setattr(env.repo, "complete_vector_delete", complete)
    assert recover_pending_memory_vector_deletes(CHAT, repo=env.repo, vector_repo=env.vector) == 1


def test_reassigned_alias_is_not_deleted_from_old_snapshot(env, monkeypatch):
    put(env, "USERNAME#ada", target_sk="USER#42", user_id="42")
    original = env.table.meta.client.transact_write_items

    def reassign_then_delete(**kwargs):
        put(env, "USERNAME#ada", target_sk="USER#99", user_id="99")
        return original(**kwargs)

    monkeypatch.setattr(env.table.meta.client, "transact_write_items", reassign_then_delete)
    with pytest.raises(ClientError):
        env.repo.delete_user_memory(CHAT, USER)
    assert env.repo.get_memory_item(CHAT, "USERNAME#ada")["target_sk"] == "USER#99"


def test_user_forget_removes_own_agent_thread_but_not_other_requesters(env):
    put(env, "AGENT_REPLY#1", requester_user_id="42", answer_text="Owned thread")
    other = put(env, "AGENT_REPLY#2", requester_user_id="99", user_id="42", answer_text="Other thread")
    assert env.repo.delete_user_memory(CHAT, USER) == 1
    assert env.repo.get_memory_item(CHAT, "AGENT_REPLY#2") == other


def test_group_forget_can_remove_old_alias_without_target(env):
    put(env, "USERNAME#legacy", user_id="42")
    env.repo.delete_chat_memory(CHAT)
    assert not env.repo.get_memory_item(CHAT, "USERNAME#legacy")


def test_source_metadata_cannot_select_another_vector_key_for_deletion(env):
    other_key = memory_vector_key(OTHER_CHAT, FACT)
    put(env, FACT, summary="Python", vector_key=other_key)
    env.repo.delete_memory_items_by_sks(CHAT, [FACT])
    recover_pending_memory_vector_deletes(CHAT, repo=env.repo, vector_repo=env.vector)
    env.vector.delete_vectors.assert_called_once_with([memory_vector_key(CHAT, FACT)])


def test_unconfirmed_vector_delete_retains_marker(env):
    put(env, FACT, summary="Python")
    env.repo.delete_memory_items_by_sks(CHAT, [FACT])
    env.vector.delete_vectors.side_effect = None
    env.vector.delete_vectors.return_value = 0
    with pytest.raises(RuntimeError, match="not confirmed"):
        recover_pending_memory_vector_deletes(CHAT, repo=env.repo, vector_repo=env.vector)
    assert env.repo.list_pending_vector_deletes(CHAT)
