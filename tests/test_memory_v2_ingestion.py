"""Actual Moto DDB transactions + synthetic transport/provider failure injection."""

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import boto3
import pytest
from boto3.dynamodb.conditions import Attr
from services.memory_v2.ingestion import MemoryIngestion, MemoryQueue, moderation_input_hash, task_payload
from services.memory_v2.models import ExtractionResult, MemoryConflict, MemoryInputError, MemoryUnavailable
from services.memory_v2.recovery import MemoryRecovery
from services.memory_v2.worker import MemoryWorker

from tests import test_memory_v2_contract as contract
from tests.test_memory_v2_contract import CHAT, USER, activate, change, commit, event

env = contract.env


class ReceiptRepository:
    """Z13-shaped test adapter; cross-table conditions execute against real Moto rows."""

    def __init__(self):
        self.table = boto3.resource("dynamodb", region_name="eu-central-1").create_table(
            TableName="moderation-receipts",
            KeySchema=[{"AttributeName": "stat_key", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "stat_key", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        self.acks = []

    def get(self, case_id):
        return self.table.get_item(Key={"stat_key": "spam_case#" + case_id}, ConsistentRead=True).get("Item") or {}

    def acknowledge_clean(self, case_id, ref, *, chat_id, user_id, message_id, outcome):
        self.table.update_item(
            Key={"stat_key": "spam_case#" + case_id},
            UpdateExpression="SET outbox_pending = :false, recovery_outcome = :outcome",
            ConditionExpression=(
                "#state = :clean AND source_ref = :ref AND chat_id = :chat "
                "AND user_id = :user AND message_id = :message "
                "AND (outbox_pending = :true OR recovery_outcome = :outcome)"
            ),
            ExpressionAttributeNames={"#state": "state"},
            ExpressionAttributeValues={
                ":false": False,
                ":true": True,
                ":outcome": outcome,
                ":clean": "clean",
                ":ref": ref,
                ":chat": str(chat_id),
                ":user": user_id,
                ":message": message_id,
            },
        )
        self.acks.append(outcome)

    def list_clean_pending(self, *, cursor=None):
        args = {"FilterExpression": Attr("outbox_pending").eq(True), "ConsistentRead": True, "Limit": 100}
        if cursor:
            args["ExclusiveStartKey"] = cursor
        result = self.table.scan(**args)
        return result.get("Items", []), result.get("LastEvaluatedKey")


@pytest.fixture
def ingestion(env):
    activate(env)
    receipts = ReceiptRepository()
    queue = SimpleNamespace(send=Mock())
    return MemoryIngestion(env.repo, receipts, queue)


def prepare(env, ingestion, message_id="8", text="I use Python."):
    source = event(env, message_id, text)
    digest = moderation_input_hash("moderation formatted " + text, {"synthetic": True})
    ref = ingestion.prepare(source, digest)
    return source, ref, digest


def clean(ingestion, ref, digest, *, chat=CHAT, user=USER, case_number=1, **overrides):
    case_id = "decision#" + f"{case_number:032x}"
    row = {
        "stat_key": "spam_case#" + case_id,
        "case_id": case_id,
        "kind": "spam_decision",
        "state": "clean",
        "outbox_pending": True,
        "guest_bot": False,
        "chat_id": str(chat),
        "user_id": int(user),
        "message_id": int(ref.source_id),
        "source_ref": ref.as_dict(),
        "input_hash": digest,
        **overrides,
    }
    ingestion.moderation_repo.table.put_item(Item=row)
    return case_id


def coverage(env, metric):
    return sum(int(row.get(metric, 0)) for row in env.repo._list(CHAT, "COVERAGE#"))


def records(*refs, chat=CHAT):
    return [{"messageId": f"record-{i}", "body": json.dumps(task_payload(chat, ref))} for i, ref in enumerate(refs)]


def worker(env, handler=None, sizing_fn=None):
    calls = []

    class Extractor:
        def __init__(self, validate):
            self.validate = validate

        async def extract_batch(self, sources):
            calls.append(sources)
            await self.validate(sources)
            if handler:
                return await handler(sources, self.validate)
            return [ExtractionResult(source.ref, (change(source.text),)) for source in sources]

    instance = MemoryWorker(
        env.repo, Extractor, sizing_fn=sizing_fn or (lambda sources: 1024 + sum(len(s.text.encode()) for s in sources))
    )
    return instance, calls


def test_candidate_is_quarantined_until_exact_clean_receipt(env, ingestion):
    source, ref, digest = prepare(env, ingestion)
    assert not env.repo.get_source_head(CHAT, ref.source_id)
    assert not env.repo.get_work(CHAT, ref)
    candidate = env.repo._read(CHAT, "CANDIDATE#8#1")
    assert candidate["ttl"] == env.clock.now + 86400
    assert candidate["text"] == source.text
    case = clean(ingestion, ref, digest)
    assert ingestion.promote_clean(case) == "INGESTED"
    assert env.repo._read(CHAT, "RAW#8")["text"] == source.text
    assert env.repo.get_work(CHAT, ref)["state"] == "PENDING"
    assert not env.repo._read(CHAT, "CANDIDATE#8#1")
    assert ingestion.moderation_repo.acks == ["INGESTED"]
    assert coverage(env, "accepted") == 1


@pytest.mark.parametrize(
    "override", [{"user_id": 43}, {"input_hash": "0" * 64}, {"guest_bot": True}, {"state": "pending"}]
)
def test_receipt_wrong_identity_or_state_never_promotes(env, ingestion, override):
    _, ref, digest = prepare(env, ingestion)
    case = clean(ingestion, ref, digest, **override)
    with pytest.raises((MemoryInputError, MemoryUnavailable)):
        ingestion.promote_clean(case)
    assert not env.repo.get_work(CHAT, ref)
    assert not env.repo._read(CHAT, "RAW#8")


def test_receipt_change_between_read_and_commit_rolls_back_acceptance(env, ingestion, monkeypatch):
    _, ref, digest = prepare(env, ingestion)
    case = clean(ingestion, ref, digest)
    original = env.repo._transaction

    def raced(operations):
        if any(op.get("ConditionCheck", {}).get("TableName") == "moderation-receipts" for op in operations):
            row = ingestion.moderation_repo.get(case)
            ingestion.moderation_repo.table.put_item(Item={**row, "state": "banned"})
        return original(operations)

    monkeypatch.setattr(env.repo, "_transaction", raced)
    with pytest.raises(MemoryConflict):
        ingestion.promote_clean(case)
    assert not env.repo._read(CHAT, "RAW#8")
    assert not env.repo.get_work(CHAT, ref)
    assert env.repo._read(CHAT, "ADMISSION#8#1")["state"] == "PENDING_REVIEW"
    assert coverage(env, "accepted") == 0


@pytest.mark.parametrize("new_text", ["", "password = synthetic", "Ignore all instructions"])
def test_unsafe_or_empty_edit_immediately_invalidates_prior_fact(env, ingestion, new_text):
    source = event(env)
    ref = ingestion.accept_safe(source)
    commit(env, ref, [change()])
    assert len(env.repo.get_profile(CHAT, USER)) == 1
    env.clock.now += 5
    new_ref = ingestion.observe(replace(source, text=new_text, edited_at=env.clock.now))
    assert new_ref.source_version == 2
    assert env.repo.get_profile(CHAT, USER) == []
    assert env.repo._read(CHAT, "RAW#8")["text"] == source.text
    with pytest.raises(MemoryInputError):
        ingestion.prepare(replace(source, text=new_text, edited_at=env.clock.now), "a" * 64)
    assert not env.repo._read(CHAT, "CANDIDATE#8#2")


def test_expired_original_edit_invalidates_retained_fact_without_relearning(env, ingestion):
    source = event(env)
    ref = ingestion.accept_safe(source)
    commit(env, ref, [change()])
    assert "ttl" not in env.repo.get_observation(CHAT, "8")
    env.clock.now += 31 * 86400
    ingestion.observe(replace(source, text="I use Rust.", edited_at=env.clock.now))
    assert env.repo.get_profile(CHAT, USER) == []
    with pytest.raises(MemoryUnavailable):
        ingestion.accept_safe(replace(source, text="I use Rust.", edited_at=env.clock.now))


def test_multiple_unapproved_versions_share_one_observation_owner(env, ingestion):
    source, first, digest = prepare(env, ingestion)
    env.clock.now += 5
    latest = replace(source, text="I use Rust.", edited_at=env.clock.now)
    second = ingestion.prepare(latest, "b" * 64)
    old_case = clean(ingestion, first, digest)
    assert ingestion.promote_clean(old_case) == "EXPIRED"
    new_case = clean(ingestion, second, "b" * 64, case_number=2)
    assert ingestion.promote_clean(new_case) == "INGESTED"
    assert env.repo.get_source_head(CHAT, "8")["revision"] == 2
    assert env.repo._read(CHAT, "RAW#8")["text"] == latest.text


def test_candidate_ttl_removal_still_has_exactly_once_expired_coverage(env, ingestion):
    _, ref, digest = prepare(env, ingestion)
    case = clean(ingestion, ref, digest)
    env.table.delete_item(Key={"pk": f"CHAT#{CHAT}", "sk": "CANDIDATE#8#1"})
    env.clock.now += 86401
    assert ingestion.promote_clean(case) == "EXPIRED"
    assert ingestion.promote_clean(case) == "EXPIRED"
    assert coverage(env, "candidate_expired") == 1
    assert not env.repo.get_work(CHAT, ref)


def test_lost_ack_replays_accepted_marker_even_after_new_edit(env, ingestion, monkeypatch):
    source, ref, digest = prepare(env, ingestion)
    case = clean(ingestion, ref, digest)
    acknowledge = ingestion.moderation_repo.acknowledge_clean
    monkeypatch.setattr(ingestion.moderation_repo, "acknowledge_clean", Mock(side_effect=RuntimeError("offline")))
    with pytest.raises(RuntimeError):
        ingestion.promote_clean(case)
    assert env.repo.get_work(CHAT, ref)["state"] == "PENDING"
    env.clock.now += 1
    ingestion.observe(replace(source, text="I use Rust.", edited_at=env.clock.now))
    monkeypatch.setattr(ingestion.moderation_repo, "acknowledge_clean", acknowledge)
    assert ingestion.promote_clean(case) == "INGESTED"
    assert coverage(env, "accepted") == 1


def test_initial_enqueue_failure_is_recovered_from_persisted_work(env, ingestion):
    ingestion.queue.send.side_effect = RuntimeError("offline")
    ref = ingestion.accept_safe(event(env))
    assert env.repo.get_work(CHAT, ref)["state"] == "PENDING"
    ingestion.queue.send.side_effect = None
    MemoryRecovery(ingestion).run()
    assert ingestion.queue.send.call_count >= 2
    args = ingestion.queue.send.call_args.args
    assert args == (str(CHAT), ref)


def test_work_leases_are_exclusive_and_recover_after_worker_termination(env, ingestion):
    ref = ingestion.accept_safe(event(env))
    first = env.repo.claim_work(CHAT, ref)
    assert first is not None
    assert env.repo.claim_work(CHAT, ref) is None
    env.clock.now = first.lease_until
    second = env.repo.claim_work(CHAT, ref)
    assert second.token != first.token
    with pytest.raises(MemoryUnavailable):
        env.repo.valid_leased_source(CHAT, first)
    assert env.repo.valid_leased_source(CHAT, second).ref == ref


def test_worker_commits_facts_and_work_once_and_retains_both_pointers(env, ingestion):
    ref = ingestion.accept_safe(event(env))
    instance, calls = worker(env)
    assert asyncio.run(instance.handle_records(records(ref, ref))) == {"batchItemFailures": []}
    assert len(calls) == 1
    assert env.repo.get_work(CHAT, ref)["state"] == "DONE"
    assert "ttl" not in env.repo.get_source_head(CHAT, "8")
    assert "ttl" not in env.repo.get_observation(CHAT, "8")
    assert coverage(env, "work_done") == 1
    assert asyncio.run(instance.handle_records(records(ref))) == {"batchItemFailures": []}
    assert len(calls) == 1


def test_budget_defer_keeps_durable_pending_and_reason(env, ingestion):
    ref = ingestion.accept_safe(event(env))

    async def deferred(sources, validate):
        return [
            ExtractionResult(source.ref, status="defer", reason="budget", retry_at=env.clock.now + 3600)
            for source in sources
        ]

    instance, _ = worker(env, deferred)
    asyncio.run(instance.handle_records(records(ref)))
    work = env.repo.get_work(CHAT, ref)
    assert work["state"] == "PENDING" and work["last_reason"] == "budget"
    assert work["due_at"] == env.clock.now + 3600
    assert coverage(env, "work_done") == 0


def test_provider_failure_does_not_invent_no_fact_success(env, ingestion):
    ref = ingestion.accept_safe(event(env))

    async def broken(sources, validate):
        raise TimeoutError("provider")

    instance, _ = worker(env, broken)
    asyncio.run(instance.handle_records(records(ref)))
    assert env.repo.get_work(CHAT, ref)["state"] == "PENDING"
    assert not env.repo.get_profile(CHAT, USER)


def test_edit_during_model_call_prevents_fact_commit(env, ingestion):
    source = event(env)
    ref = ingestion.accept_safe(source)

    async def edited(sources, validate):
        env.clock.now += 1
        ingestion.observe(replace(source, text="", edited_at=env.clock.now))
        return [ExtractionResult(ref, (change(),))]

    instance, _ = worker(env, edited)
    asyncio.run(instance.handle_records(records(ref)))
    assert env.repo.get_work(CHAT, ref)["state"] == "EXPIRED"
    assert not list(env.repo._list(CHAT, "FACT#"))


def test_second_provider_attempt_validation_detects_optout(env, ingestion):
    ref = ingestion.accept_safe(event(env))

    async def opted_out(sources, validate):
        subject = env.repo.get_subject(CHAT, USER)
        env.repo.begin_subject_stop(CHAT, USER, expected_revision=int(subject["revision"]), optout=True)
        await validate(sources)
        pytest.fail("Revoked model attempt must never proceed")

    instance, _ = worker(env, opted_out)
    asyncio.run(instance.handle_records(records(ref)))
    assert env.repo.get_work(CHAT, ref)["state"] == "EXPIRED"


def test_oversize_single_source_is_failed_with_coverage_not_truncated(env, ingestion):
    ref = ingestion.accept_safe(event(env, text="a" * 7500))
    instance, calls = worker(env)
    asyncio.run(instance.handle_records(records(ref)))
    assert calls == []
    work = env.repo.get_work(CHAT, ref)
    assert work["state"] == "FAILED" and work["last_reason"] == "input_limit"
    assert coverage(env, "work_failed") == 1


def test_worker_batches_same_chat_and_bounded_request_size(env, ingestion):
    refs = [ingestion.accept_safe(event(env, str(i), "I use Python.")) for i in range(1, 24)]
    other = -100456
    activate(env, other)
    other_ref = ingestion.accept_safe(event(env, "1", chat=other))
    instance, calls = worker(env, sizing_fn=lambda sources: 1024 + len(sources) * 1800)
    asyncio.run(
        instance.handle_records(
            records(*refs) + [{"messageId": "other", "body": json.dumps(task_payload(other, other_ref))}]
        )
    )
    assert len(calls) >= 7
    assert all(len(batch) <= 3 and len({source.chat_id for source in batch}) == 1 for batch in calls)


def test_legacy_body_task_is_partial_failure_without_learning(env, ingestion):
    ref = ingestion.accept_safe(event(env))
    instance, calls = worker(env)
    invalid = {"messageId": "legacy", "body": json.dumps({**task_payload(CHAT, ref), "text": "I use Rust."})}
    result = asyncio.run(instance.handle_records([invalid]))
    assert result == {"batchItemFailures": [{"itemIdentifier": "legacy"}]}
    assert calls == []
    assert env.repo.get_work(CHAT, ref)["state"] == "PENDING"


def test_missing_extractor_result_retries_all_sources(env, ingestion):
    ref = ingestion.accept_safe(event(env))

    async def missing(sources, validate):
        return []

    instance, _ = worker(env, missing)
    asyncio.run(instance.handle_records(records(ref)))
    assert env.repo.get_work(CHAT, ref)["state"] == "PENDING"
    assert env.repo.get_work(CHAT, ref)["last_reason"] == "schema"


def test_work_expiry_is_logical_even_before_ttl_gc(env, ingestion):
    ref = ingestion.accept_safe(event(env))
    env.clock.now += 30 * 86400
    instance, calls = worker(env)
    asyncio.run(instance.handle_records(records(ref)))
    assert calls == [] and env.repo.get_work(CHAT, ref)["state"] == "EXPIRED"
    assert coverage(env, "work_expired") == 1


def test_recovery_filtered_empty_page_keeps_cursor_and_reaches_later_items(env, ingestion, monkeypatch):
    _, ref, digest = prepare(env, ingestion)
    case = clean(ingestion, ref, digest)
    marker = {"stat_key": "synthetic-cursor"}
    receipts = ingestion.moderation_repo
    pages = Mock(side_effect=[([], marker), ([receipts.get(case)], None)])
    monkeypatch.setattr(receipts, "list_clean_pending", pages)
    MemoryRecovery(ingestion).run(max_pages=1)
    assert env.repo.recovery_checkpoint("clean")["cursor"] == marker
    assert not env.repo.get_work(CHAT, ref)
    MemoryRecovery(ingestion).run(max_pages=1)
    assert pages.call_args.kwargs["cursor"] == marker
    assert env.repo.get_work(CHAT, ref)["state"] == "PENDING"


def test_sqs_wire_payload_contains_only_versioned_reference(monkeypatch):
    from services.memory_v2 import cost_meter
    from services.memory_v2.models import SourceRef

    # This payload-only fake has no SDK metadata. Real hook installation and
    # sticky registration failure are covered in test_memory_v2_cost_meter.
    register = Mock(return_value=True)
    monkeypatch.setattr(cost_meter, "register_client", register)
    client = SimpleNamespace(send_message=Mock())
    MemoryQueue("https://example.invalid/memory-v2", client=client).send(CHAT, SourceRef("8", 1, "epoch"))
    register.assert_called_once_with(client)
    payload = json.loads(client.send_message.call_args.kwargs["MessageBody"])
    assert payload == {
        "schema": 2,
        "task_type": "PROCESS_MEMORY_V2",
        "chat_id": str(CHAT),
        "source_ref": {"source_id": "8", "source_version": 1, "epoch": "epoch"},
    }


def test_confirmation_work_is_never_claimed_or_discovered_for_model(env, ingestion):
    ref = env.repo.register_source(event(env, source_kind="confirmation"))
    assert env.repo.claim_work(CHAT, ref) is None
    assert "work_queue" not in env.repo.get_work(CHAT, ref)
    MemoryRecovery(ingestion).run()
    ingestion.queue.send.assert_not_called()


def test_candidate_expiring_during_promotion_cannot_commit(env, ingestion, monkeypatch):
    _, ref, digest = prepare(env, ingestion)
    case = clean(ingestion, ref, digest)
    original = env.repo._accept_operations

    def delayed(*args, **kwargs):
        result = original(*args, **kwargs)
        env.clock.now += 86401
        return result

    monkeypatch.setattr(env.repo, "_accept_operations", delayed)
    assert ingestion.promote_clean(case) == "EXPIRED"
    assert not env.repo.get_work(CHAT, ref)
    assert coverage(env, "accepted") == 0


def test_candidate_removed_during_transaction_cannot_be_promoted(env, ingestion, monkeypatch):
    _, ref, digest = prepare(env, ingestion)
    case = clean(ingestion, ref, digest)
    original = env.repo._transaction

    def disappeared(operations):
        if any(op.get("ConditionCheck", {}).get("TableName") == "moderation-receipts" for op in operations):
            env.table.delete_item(Key={"pk": f"CHAT#{CHAT}", "sk": "CANDIDATE#8#1"})
        return original(operations)

    monkeypatch.setattr(env.repo, "_transaction", disappeared)
    with pytest.raises(MemoryConflict):
        ingestion.promote_clean(case)
    assert not env.repo.get_work(CHAT, ref)
    assert coverage(env, "accepted") == 0


def test_recovery_poison_receipt_does_not_starve_later_valid_rows(env, ingestion):
    from services.memory_v2.recovery import MemoryRecoveryError

    _, first, digest = prepare(env, ingestion)
    bad = clean(ingestion, first, "wronghash")
    _, second, second_hash = prepare(env, ingestion, "9")
    good = clean(ingestion, second, second_hash, case_number=2)
    with pytest.raises(MemoryRecoveryError):
        MemoryRecovery(ingestion).run()
    assert ingestion.moderation_repo.get(bad)["outbox_pending"] is True
    assert ingestion.moderation_repo.get(good)["outbox_pending"] is False
    assert env.repo.get_work(CHAT, second)["state"] == "PENDING"


def test_read_failure_after_claim_returns_partial_failure_not_success(env, ingestion, monkeypatch):
    ref = ingestion.accept_safe(event(env))
    instance, calls = worker(env)
    monkeypatch.setattr(env.repo, "valid_leased_source", Mock(side_effect=RuntimeError("ddb unavailable")))
    assert asyncio.run(instance.handle_records(records(ref))) == {"batchItemFailures": [{"itemIdentifier": "record-0"}]}
    assert calls == [] and env.repo.get_work(CHAT, ref)["state"] == "LEASED"


def test_coverage_distinguishes_recovered_latency_and_budget_pending(env, ingestion):
    first = ingestion.accept_safe(event(env))
    MemoryRecovery(ingestion).run()
    env.clock.now += 100
    instance, _ = worker(env)
    asyncio.run(instance.handle_records(records(first)))
    second = ingestion.accept_safe(event(env, "9"))
    lease = env.repo.claim_work(CHAT, second)
    env.repo.retry_work(CHAT, lease, retry_at=env.clock.now + 3600, reason="budget")
    status = env.repo.coverage_snapshot(CHAT)
    assert status["done"] == 1 and status["paused"] == 1
    assert status["normal_completed_samples"] == 0
    assert status["recovery_p95_seconds"] == 100
    assert status["outcomes"]["accepted"] == 2
    assert "text" not in json.dumps(status)


def test_accept_marker_retained_until_ack_and_missing_local_ack_is_recovered(env, ingestion, monkeypatch):
    _, ref, digest = prepare(env, ingestion)
    case = clean(ingestion, ref, digest)
    original = env.repo.complete_admission_ack
    monkeypatch.setattr(env.repo, "complete_admission_ack", Mock(side_effect=RuntimeError("ddb timeout")))
    with pytest.raises(RuntimeError):
        ingestion.promote_clean(case)
    assert ingestion.moderation_repo.get(case)["outbox_pending"] is False
    assert "ttl" not in env.repo._read(CHAT, "ADMISSION#8#1")
    env.clock.now += 8 * 86400
    monkeypatch.setattr(env.repo, "complete_admission_ack", original)
    MemoryRecovery(ingestion).run()
    assert env.repo._read(CHAT, "ADMISSION#8#1")["ttl"] == env.clock.now + 7 * 86400
    assert coverage(env, "accepted") == 1


def test_lost_expired_ack_can_replay_without_missing_actor_metadata_blocking(env, ingestion, monkeypatch):
    _, ref, digest = prepare(env, ingestion)
    case = clean(ingestion, ref, digest)
    env.table.delete_item(Key={"pk": f"CHAT#{CHAT}", "sk": "ADMISSION#8#1"})
    original = ingestion.moderation_repo.acknowledge_clean
    monkeypatch.setattr(ingestion.moderation_repo, "acknowledge_clean", Mock(side_effect=RuntimeError("offline")))
    with pytest.raises(RuntimeError):
        ingestion.promote_clean(case)
    monkeypatch.setattr(ingestion.moderation_repo, "acknowledge_clean", original)
    assert ingestion.promote_clean(case) == "EXPIRED"
    assert coverage(env, "candidate_expired") == 1


@pytest.mark.parametrize("reason,stored", [("budget_unavailable", "budget"), ("daily_quota_exhausted", "quota")])
def test_real_extractor_deferral_vocabulary_keeps_pause_visible(env, ingestion, reason, stored):
    ref = ingestion.accept_safe(event(env))

    async def deferred(sources, validate):
        return [ExtractionResult(ref, status="defer", reason=reason, retry_at=env.clock.now + 3600)]

    instance, _ = worker(env, deferred)
    asyncio.run(instance.handle_records(records(ref)))
    assert env.repo.get_work(CHAT, ref)["last_reason"] == stored
    assert env.repo.coverage_snapshot(CHAT)["paused"] == 1


def test_extractor_invalid_source_is_failed_with_coverage(env, ingestion):
    ref = ingestion.accept_safe(event(env))

    async def rejected(sources, validate):
        raise MemoryInputError("Source no longer satisfies the public-content policy")

    instance, _ = worker(env, rejected)
    asyncio.run(instance.handle_records(records(ref)))
    assert env.repo.get_work(CHAT, ref)["state"] == "FAILED"
    assert env.repo.get_work(CHAT, ref)["last_reason"] == "invalid_source"
    assert coverage(env, "work_failed") == 1


def test_same_second_conflicting_edit_invalidates_once_until_later_edit(env, ingestion):
    source = event(env)
    ref = ingestion.accept_safe(source)
    commit(env, ref, [change()])
    env.clock.now += 1
    first_edit = replace(source, text="I use Rust.", edited_at=env.clock.now)
    first_ref = ingestion.accept_safe(first_edit)
    commit(env, first_ref, [change(first_edit.text, "Rust")])
    ambiguous = replace(source, text="I use Go.", edited_at=env.clock.now)
    with pytest.raises(MemoryConflict, match="ambiguous"):
        ingestion.observe(ambiguous)
    observation = env.repo.get_observation(CHAT, "8")
    assert observation["ambiguous"] is True and observation["revision"] == 3
    assert env.repo.get_profile(CHAT, USER) == []
    for repeated in (first_edit, ambiguous, source):
        with pytest.raises(MemoryConflict):
            ingestion.observe(repeated)
    assert env.repo.get_observation(CHAT, "8") == observation
    with pytest.raises(MemoryUnavailable):
        env.repo.source_snapshot(CHAT, first_ref)
    env.clock.now += 1
    later = replace(ambiguous, edited_at=env.clock.now)
    latest = ingestion.accept_safe(later)
    assert latest.source_version == 4 and env.repo.get_observation(CHAT, "8")["ambiguous"] is False
    commit(env, latest, [change(later.text, "Go")])
    assert [fact["value"] for fact in env.repo.get_profile(CHAT, USER)] == ["Go"]


def test_same_time_ambiguity_blocks_a_previously_clean_candidate(env, ingestion):
    source, ref, digest = prepare(env, ingestion)
    case = clean(ingestion, ref, digest)
    with pytest.raises(MemoryConflict):
        ingestion.observe(replace(source, text="I use Go."))
    assert ingestion.promote_clean(case) == "EXPIRED"
    assert not env.repo.get_source_head(CHAT, "8")
    assert not env.repo.get_work(CHAT, ref)


@pytest.mark.parametrize("new_text", ["", "password = synthetic"])
def test_paused_learning_still_invalidates_changed_source(env, ingestion, new_text):
    source = event(env)
    ref = ingestion.accept_safe(source)
    commit(env, ref, [change()])
    control = env.repo.get_control(CHAT)
    env.repo.set_learning_enabled(CHAT, False, expected_revision=int(control["revision"]))
    assert len(env.repo.get_profile(CHAT, USER)) == 1
    env.clock.now += 1
    observed = ingestion.observe(replace(source, text=new_text, edited_at=env.clock.now))
    assert observed.source_version == 2
    assert env.repo.get_profile(CHAT, USER) == []
    assert env.repo._read(CHAT, "RAW#8")["text"] == source.text


def test_permanent_source_conflict_is_distinct_from_retryable_storage_cas(env, ingestion, monkeypatch):
    from services.memory_v2.models import MemorySourceConflict

    source = event(env)
    ingestion.observe(source)
    with pytest.raises(MemorySourceConflict):
        ingestion.observe(replace(source, text="I use Rust."))
    env.clock.now += 1
    monkeypatch.setattr(env.repo, "_transaction", Mock(side_effect=MemoryConflict("concurrent write")))
    with pytest.raises(MemoryConflict) as captured:
        ingestion.observe(replace(source, text="I use Go.", edited_at=env.clock.now))
    assert not isinstance(captured.value, MemorySourceConflict)


def test_clean_receipt_stays_pending_during_learning_pause_and_promotes_after_resume(env, ingestion):
    _, ref, digest = prepare(env, ingestion)
    case = clean(ingestion, ref, digest)
    control = env.repo.get_control(CHAT)
    paused = env.repo.set_learning_enabled(CHAT, False, expected_revision=int(control["revision"]))
    before = env.repo._read(CHAT, "ADMISSION#8#1")
    assert ingestion.promote_clean(case) == "PAUSED"
    assert env.repo._read(CHAT, "ADMISSION#8#1") == before
    assert env.repo._read(CHAT, "CANDIDATE#8#1")["text"] == "I use Python."
    assert ingestion.moderation_repo.get(case)["outbox_pending"] is True
    assert coverage(env, "candidate_expired") == 0
    env.repo.set_learning_enabled(CHAT, True, expected_revision=int(paused["revision"]))
    assert ingestion.promote_clean(case) == "INGESTED"
    assert env.repo.get_work(CHAT, ref)["state"] == "PENDING"


def test_paused_candidate_still_expires_at_its_actual_deadline(env, ingestion):
    _, ref, digest = prepare(env, ingestion)
    case = clean(ingestion, ref, digest)
    control = env.repo.get_control(CHAT)
    env.repo.set_learning_enabled(CHAT, False, expected_revision=int(control["revision"]))
    env.clock.now += 86400
    assert ingestion.promote_clean(case) == "EXPIRED"
    assert not env.repo._read(CHAT, "CANDIDATE#8#1")
    assert ingestion.moderation_repo.get(case)["recovery_outcome"] == "EXPIRED"
    assert coverage(env, "candidate_expired") == 1


def test_concurrent_accept_then_edit_acks_persisted_acceptance_not_expiry(env, ingestion, monkeypatch):
    source, ref, digest = prepare(env, ingestion)
    case = clean(ingestion, ref, digest)
    original = env.repo.promote_candidate
    raced = False

    def accepted_by_another(*args, **kwargs):
        nonlocal raced
        if not raced:
            raced = True
            original(*args, **kwargs)  # Another invocation commits, then loses its ACK response.
            env.clock.now += 1
            ingestion.observe(replace(source, text="", edited_at=env.clock.now))
        return original(*args, **kwargs)

    monkeypatch.setattr(env.repo, "promote_candidate", accepted_by_another)
    assert ingestion.promote_clean(case) == "INGESTED"
    receipt = ingestion.moderation_repo.get(case)
    assert receipt["recovery_outcome"] == "INGESTED" and receipt["outbox_pending"] is False
    assert env.repo._read(CHAT, "ADMISSION#8#1")["state"] == "ACCEPTED"
    assert "ttl" in env.repo._read(CHAT, "ADMISSION#8#1")
    ingestion.moderation_repo.acknowledge_clean(
        case, ref.as_dict(), chat_id=CHAT, user_id=int(USER), message_id=8, outcome="INGESTED"
    )
    from botocore.exceptions import ClientError

    with pytest.raises(ClientError):
        ingestion.moderation_repo.acknowledge_clean(
            case, ref.as_dict(), chat_id=CHAT, user_id=int(USER), message_id=8, outcome="EXPIRED"
        )
