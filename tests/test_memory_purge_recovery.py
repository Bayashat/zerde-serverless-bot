"""Indexed deletion discovery, bounded progress and failure recovery on real Moto."""

from unittest.mock import Mock

import pytest
from services.memory_v2 import lifecycle as module
from services.memory_v2.lifecycle import PURGE_QUEUE, MemoryLifecycle, MemoryPurgeRecoveryError
from services.memory_v2.models import MemoryConflict

from tests import test_memory_v2_contract as contract
from tests.test_memory_v2_contract import CHAT, USER, activate, commit, event

env = contract.env


def pending(env, *, chat=CHAT, scope="group"):
    activate(env, chat)
    ref = env.repo.register_source(event(env, chat=chat))
    commit(env, ref, chat=chat)
    return MemoryLifecycle(env.repo).begin(chat, scope=scope, target="8" if scope == "source" else None)


def legacy(env, job):
    old = {key: value for key, value in job.items() if key not in {"work_queue", "due_at"}}
    env.table.put_item(Item=old)
    return old


def test_new_purge_is_atomic_indexed_and_finishes_despite_unrelated_scan_pages(env, monkeypatch):
    job = pending(env)
    assert job["work_queue"] == PURGE_QUEUE and job["due_at"] == job["created_at"]
    with env.table.batch_writer() as batch:
        for index in range(1200):
            batch.put_item(Item={"pk": "UNRELATED", "sk": f"{index:04}", "kind": "NOT_A_PURGE"})
        for index in range(150):
            batch.put_item(Item={"pk": f"CHAT#{CHAT}", "sk": f"RAW#synthetic{index:04}", "revision": 1})
    # Discovery cannot rely on a lucky filtered Scan hit near the table start.
    scan = Mock(return_value={"Items": [], "LastEvaluatedKey": {"pk": "UNRELATED", "sk": "0024"}})
    monkeypatch.setattr(env.repo.table, "scan", scan)
    result = MemoryLifecycle(env.repo).recover()
    done = env.repo._read(CHAT, job["sk"])
    assert result["attempted"] == 1
    assert done["state"] == "DONE" and done["deleted_rows"] >= 150
    assert "work_queue" not in done and "due_at" not in done
    assert not list(env.repo._list(CHAT, "RAW#"))
    assert env.table.get_item(Key={"pk": "UNRELATED", "sk": "1199"})["Item"]["kind"] == "NOT_A_PURGE"
    assert scan.call_count == 2
    assert env.repo.recovery_checkpoint("purges")["cursor"] == {"pk": "UNRELATED", "sk": "0024"}


def test_legacy_job_is_backfilled_preserving_identity_cursor_and_fences(env):
    lifecycle = MemoryLifecycle(env.repo, derived_cleaners=[lambda *args: False])
    job = legacy(env, pending(env, scope="source"))
    lifecycle._index_legacy(job)
    indexed = env.repo._read(CHAT, job["sk"])
    assert indexed == {**job, "revision": job["revision"] + 1, "work_queue": PURGE_QUEUE, "due_at": job["created_at"]}
    lifecycle.recover()
    assert env.repo._read(CHAT, job["sk"])["state"] == "DERIVED"
    assert env.repo.get_observation(CHAT, "8")["deleted"]
    assert MemoryLifecycle(env.repo).recover()["attempted"] == 1
    assert env.repo._read(CHAT, job["sk"])["state"] == "DONE"


def test_legacy_filtered_empty_page_continues_and_index_lag_is_not_completion(env, monkeypatch):
    old = legacy(env, pending(env))
    actual_query = env.repo.table.query

    def lagged(**kwargs):
        if "IndexName" in kwargs:
            return {"Items": []}
        return actual_query(**kwargs)

    monkeypatch.setattr(env.repo.table, "query", lagged)
    lifecycle = MemoryLifecycle(env.repo)
    lifecycle.recover()
    indexed = env.repo._read(CHAT, old["sk"])
    assert indexed["work_queue"] == PURGE_QUEUE and indexed["state"] == "WAITING"
    assert env.repo.get_control(CHAT)["state"] == "STOPPING"
    monkeypatch.setattr(env.repo.table, "query", actual_query)
    lifecycle.recover()
    assert env.repo._read(CHAT, old["sk"])["state"] == "DONE"


def test_stale_done_hint_is_strongly_rejected_without_advance(env, monkeypatch):
    job = pending(env)
    lifecycle = MemoryLifecycle(env.repo)
    assert lifecycle.advance(CHAT, job["sk"])["state"] == "DONE"
    advance = Mock(side_effect=AssertionError("stale index entry must not advance"))
    monkeypatch.setattr(lifecycle, "advance", advance)
    assert lifecycle._advance_due(job, deadline=float("inf")) is False
    advance.assert_not_called()


def test_begin_transaction_failure_never_publishes_an_indexed_job(env, monkeypatch):
    activate(env)
    ref = env.repo.register_source(event(env))
    commit(env, ref)
    monkeypatch.setattr(env.repo, "_transaction", Mock(side_effect=RuntimeError("offline")))
    with pytest.raises(RuntimeError):
        MemoryLifecycle(env.repo).begin(CHAT, scope="group")
    assert env.repo.get_control(CHAT)["state"] == "ACTIVE"
    assert not env.repo._read(CHAT, "PURGE#GROUP#GROUP")


def test_done_transaction_failure_keeps_index_and_can_resume(env, monkeypatch):
    job = pending(env)
    lifecycle = MemoryLifecycle(env.repo)
    transaction = env.repo._transaction

    def fail_done(operations):
        if any(op.get("Put", {}).get("Item", {}).get("state") == "DONE" for op in operations):
            raise RuntimeError("offline")
        transaction(operations)

    monkeypatch.setattr(env.repo, "_transaction", fail_done)
    with pytest.raises(MemoryPurgeRecoveryError):
        lifecycle.recover()
    row = env.repo._read(CHAT, job["sk"])
    assert row["state"] == "DERIVED" and row["work_queue"] == PURGE_QUEUE
    assert env.repo.get_control(CHAT)["state"] == "STOPPING"
    monkeypatch.setattr(env.repo, "_transaction", transaction)
    lifecycle.recover()
    assert env.repo._read(CHAT, job["sk"])["state"] == "DONE"


def test_failed_legacy_lane_does_not_block_indexed_job(env, monkeypatch):
    job = pending(env)
    monkeypatch.setattr(env.repo.table, "scan", Mock(side_effect=RuntimeError("scan unavailable")))
    with pytest.raises(MemoryPurgeRecoveryError):
        MemoryLifecycle(env.repo).recover()
    assert env.repo._read(CHAT, job["sk"])["state"] == "DONE"


def test_poison_job_and_index_page_boundary_do_not_starve_later_jobs(env, monkeypatch):
    jobs = [pending(env, chat=CHAT - index) for index in range(12)]
    lifecycle = MemoryLifecycle(env.repo)
    advance = lifecycle.advance
    poison_pk = jobs[0]["pk"]

    def fail_one(chat_id, *args, **kwargs):
        if f"CHAT#{chat_id}" == poison_pk:
            raise RuntimeError("poison")
        return advance(chat_id, *args, **kwargs)

    monkeypatch.setattr(lifecycle, "advance", fail_one)
    with pytest.raises(MemoryPurgeRecoveryError):
        lifecycle.recover()
    assert env.repo._read(CHAT, jobs[0]["sk"])["state"] == "WAITING"
    assert all(env.repo._read(CHAT - index, job["sk"])["state"] == "DONE" for index, job in enumerate(jobs[1:], 1))
    monkeypatch.setattr(lifecycle, "advance", advance)
    lifecycle.recover()
    assert env.repo._read(CHAT, jobs[0]["sk"])["state"] == "DONE"


def test_deadline_mid_page_persists_attempted_hint_so_large_job_cannot_starve_next(env, monkeypatch):
    jobs = [pending(env, chat=CHAT - index) for index in range(2)]
    clock = [100.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    lifecycle = MemoryLifecycle(env.repo)
    original = lifecycle.advance
    seen = []

    def slow(chat_id, key, **kwargs):
        seen.append(str(chat_id))
        if len(seen) == 1:
            clock[0] += 21
            return env.repo._read(chat_id, key)  # Still WAITING; time has expired.
        return original(chat_id, key, **kwargs)

    monkeypatch.setattr(lifecycle, "advance", slow)
    assert lifecycle.recover()["pending"] is True
    cursor = env.repo.recovery_checkpoint("purge_due")["cursor"]
    assert set(cursor) == {"pk", "sk", "work_queue", "due_at"}
    assert cursor["pk"] == f"CHAT#{seen[0]}"
    lifecycle.recover()
    assert len(seen) == 2 and seen[0] != seen[1]
    assert env.repo._read(seen[1], jobs[0]["sk"])["state"] == "DONE"
    lifecycle.recover()  # Cursor wrapped only after the later job got its turn.
    assert env.repo._read(seen[0], jobs[0]["sk"])["state"] == "DONE"


def test_advance_checks_deadline_between_delete_pages(env, monkeypatch):
    job = pending(env)
    lifecycle = MemoryLifecycle(env.repo)
    clock = [1.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    transaction = env.repo._transaction

    def slow_transaction(operations):
        transaction(operations)
        clock[0] += 2

    monkeypatch.setattr(env.repo, "_transaction", slow_transaction)
    result = lifecycle.advance(CHAT, job["sk"], max_pages=20, deadline=2)
    assert result["state"] == "DELETING" and result["deleted_rows"] == 0
    assert env.repo._read(CHAT, "RAW#8")
    assert lifecycle.advance(CHAT, job["sk"], max_pages=20, deadline=50)["state"] == "DONE"


def test_checkpoint_cas_loss_does_not_overwrite_winning_runner(env, monkeypatch):
    job = pending(env)
    original = env.repo.save_recovery_checkpoint

    def conflict(name, previous, cursor):
        if name == "purge_due":
            original(name, previous, {"pk": "winner", "sk": "cursor"})
            raise MemoryConflict("Another runner won")
        return original(name, previous, cursor)

    monkeypatch.setattr(env.repo, "save_recovery_checkpoint", conflict)
    result = MemoryLifecycle(env.repo).recover()
    assert result["pending"] is True
    assert env.repo.recovery_checkpoint("purge_due")["cursor"] == {"pk": "winner", "sk": "cursor"}
    assert env.repo._read(CHAT, job["sk"])["state"] == "DONE"


def test_waiting_lease_remains_pending_until_original_deadline(env):
    from services.memory_v2.leases import AnswerLeaseService

    activate(env)
    ref = env.repo.register_source(event(env))
    commit(env, ref)
    lease = AnswerLeaseService(env.repo).acquire(CHAT, [USER], request_id="synthetic")
    lifecycle = MemoryLifecycle(env.repo)
    job = lifecycle.begin(CHAT, scope="source", target="8")
    assert lifecycle.recover()["pending"] is True
    assert env.repo._read(CHAT, job["sk"])["state"] == "WAITING"
    env.clock.now = lease.lease_until
    lifecycle.recover()
    assert env.repo._read(CHAT, job["sk"])["state"] == "DONE"


def test_legacy_index_cas_cannot_resurrect_concurrently_completed_job(env, monkeypatch):
    job = legacy(env, pending(env))
    lifecycle = MemoryLifecycle(env.repo)
    transaction = env.repo._transaction
    raced = False

    def complete_first(operations):
        nonlocal raced
        if not raced:
            raced = True
            lifecycle.advance(CHAT, job["sk"])
        transaction(operations)

    monkeypatch.setattr(env.repo, "_transaction", complete_first)
    with pytest.raises(MemoryConflict):
        lifecycle._index_legacy(job)
    current = env.repo._read(CHAT, job["sk"])
    assert current["state"] == "DONE" and "work_queue" not in current
    assert env.repo.get_control(CHAT)["state"] == "STOPPED"


def test_deadline_during_lease_inventory_never_permits_deletion(env, monkeypatch):
    job = pending(env)
    clock = [100.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    query = env.repo.table.query

    def slow_query(**kwargs):
        result = query(**kwargs)
        clock[0] += 20
        return result

    monkeypatch.setattr(env.repo.table, "query", slow_query)
    current = MemoryLifecycle(env.repo).advance(CHAT, job["sk"], max_pages=20, deadline=110)
    assert current["state"] == "WAITING"
    assert env.repo._read(CHAT, "RAW#8")
    assert env.repo.get_control(CHAT)["state"] == "STOPPING"


def test_duplicate_index_hint_uses_current_base_state(env, monkeypatch):
    job = pending(env)
    query = env.repo.table.query
    hint = {key: job[key] for key in ("pk", "sk", "work_queue", "due_at")}

    def duplicate(**kwargs):
        if "IndexName" in kwargs:
            return {"Items": [hint, hint]}
        return query(**kwargs)

    monkeypatch.setattr(env.repo.table, "query", duplicate)
    lifecycle = MemoryLifecycle(env.repo)
    advance = Mock(wraps=lifecycle.advance)
    monkeypatch.setattr(lifecycle, "advance", advance)
    lifecycle.recover()
    assert advance.call_count == 1
    assert env.repo._read(CHAT, job["sk"])["state"] == "DONE"


def test_slow_fence_does_not_start_a_delete_page_after_deadline(env, monkeypatch):
    job = pending(env)
    lifecycle = MemoryLifecycle(env.repo)
    assert lifecycle.advance(CHAT, job["sk"], max_pages=1)["state"] == "DELETING"
    clock = [1.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    fence = lifecycle._fence

    def slow_fence(*args):
        result = fence(*args)
        clock[0] += 2
        return result

    monkeypatch.setattr(lifecycle, "_fence", slow_fence)
    query = Mock(wraps=env.repo.table.query)
    monkeypatch.setattr(env.repo.table, "query", query)
    assert lifecycle.advance(CHAT, job["sk"], deadline=2)["state"] == "DELETING"
    query.assert_not_called()


def test_last_delete_page_overruns_budget_leaves_derived_for_next_run(env, monkeypatch):
    job = pending(env)
    lifecycle = MemoryLifecycle(env.repo)
    lifecycle.advance(CHAT, job["sk"], max_pages=1)
    clock = [1.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    transaction = env.repo._transaction

    def slow_transaction(operations):
        transaction(operations)
        clock[0] += 2

    monkeypatch.setattr(env.repo, "_transaction", slow_transaction)
    assert lifecycle.advance(CHAT, job["sk"], deadline=2)["state"] == "DERIVED"
    assert env.repo.get_control(CHAT)["state"] == "STOPPING"
    assert lifecycle.advance(CHAT, job["sk"], deadline=10)["state"] == "DONE"
