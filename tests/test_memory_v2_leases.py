"""Real Moto transaction races for answer/send leases, without provider or Telegram."""

from dataclasses import replace

import pytest
from services.memory_v2.leases import ANSWER_LEASE_SECONDS, AnswerLeaseService
from services.memory_v2.models import AdminConfirmation, MemoryConflict, MemoryInputError, MemoryUnavailable

from tests import test_memory_v2_contract as contract
from tests.test_memory_v2_contract import CHAT, USER, activate, change, commit, event

env = contract.env


@pytest.fixture
def answered(env):
    activate(env)
    source = event(env)
    ref = env.repo.register_source(source)
    commit(env, ref)
    leases = AnswerLeaseService(env.repo)
    lease = leases.acquire(CHAT, [USER], request_id="request-1")
    facts = leases.snapshot(lease)
    refs = [{"fact_id": row["fact_id"], "fact_version": int(row["fact_version"])} for row in facts]
    return leases, lease, refs, source


def test_acquire_bind_validate_release_keeps_only_metadata(env, answered):
    leases, lease, refs, _ = answered
    row = env.repo._read(CHAT, lease.lease_id)
    assert row["lease_until"] == env.clock.now + ANSWER_LEASE_SECONDS
    assert row["bound"] is False and row["fact_refs"] == []
    bound = leases.bind(lease, refs)
    assert bound.revision == lease.revision + 1
    leases.validate(bound, refs)
    row = env.repo._read(CHAT, lease.lease_id)
    assert row["evidence_authors"] == [USER]
    assert not any(key in row for key in ("text", "value", "answer", "excerpt", "question"))
    leases.release(lease)  # finally may still hold its pre-bind view, same token.
    leases.release(bound)
    with pytest.raises(MemoryUnavailable):
        leases.validate(bound, refs)
    with pytest.raises(MemoryConflict):
        leases.acquire(CHAT, [USER], request_id="request-1")


def test_unknown_subject_ask_has_no_subject_write(env):
    activate(env)
    with pytest.raises(MemoryUnavailable):
        AnswerLeaseService(env.repo).acquire(CHAT, [USER], request_id="missing")
    assert not env.repo.get_subject(CHAT, USER)
    assert not list(env.repo._list(CHAT, "ANSWER_LEASE#"))


@pytest.mark.parametrize("operation", ["snapshot", "bind", "validate"])
def test_stopping_blocks_new_lease_and_existing_lease_operations(env, answered, operation):
    leases, lease, refs, _ = answered
    if operation == "validate":
        lease = leases.bind(lease, refs)
    subject = env.repo.get_subject(CHAT, USER)
    env.repo.begin_subject_stop(CHAT, USER, expected_revision=int(subject["revision"]), optout=True)
    with pytest.raises(MemoryUnavailable):
        leases.acquire(CHAT, [USER], request_id="new")
    with pytest.raises(MemoryUnavailable):
        getattr(leases, operation)(lease, refs) if operation != "snapshot" else leases.snapshot(lease)


def test_control_stop_between_read_and_acquire_cas_never_registers_lease(env, answered, monkeypatch):
    leases, _, _, _ = answered
    original = env.repo._transaction
    raced = False

    def stop(operations):
        nonlocal raced
        if not raced:
            raced = True
            control = env.repo.get_control(CHAT)
            env.repo.begin_group_stop(CHAT, expected_revision=int(control["revision"]))
        return original(operations)

    monkeypatch.setattr(env.repo, "_transaction", stop)
    with pytest.raises(MemoryConflict):
        leases.acquire(CHAT, [USER], request_id="raced")
    assert len(list(env.repo._list(CHAT, "ANSWER_LEASE#"))) == 1


def test_edit_after_snapshot_cannot_bind_old_facts(env, answered):
    leases, lease, refs, source = answered
    env.clock.now += 1
    env.repo.observe(replace(source, text="", edited_at=env.clock.now))
    with pytest.raises(MemoryUnavailable):
        leases.bind(lease, refs)


def test_edit_after_bound_prevents_send(env, answered):
    leases, lease, refs, source = answered
    bound = leases.bind(lease, refs)
    env.clock.now += 1
    env.repo.observe(replace(source, text="", edited_at=env.clock.now))
    with pytest.raises(MemoryUnavailable):
        leases.validate(bound, refs)


def test_bind_transaction_race_with_forget_is_fenced(env, answered, monkeypatch):
    leases, lease, refs, _ = answered
    original = env.repo._transaction
    raced = False

    def stop(operations):
        nonlocal raced
        if not raced:
            raced = True
            subject = env.repo.get_subject(CHAT, USER)
            env.repo.begin_subject_stop(CHAT, USER, expected_revision=int(subject["revision"]))
        return original(operations)

    monkeypatch.setattr(env.repo, "_transaction", stop)
    with pytest.raises(MemoryConflict):
        leases.bind(lease, refs)
    assert env.repo._read(CHAT, lease.lease_id)["bound"] is False


def test_group_fact_registers_its_evidence_author_and_checks_forget(env):
    activate(env)
    source = event(env, text="Rule: Be kind.", source_kind="confirmation")
    ref = env.repo.register_source(source)
    group = env.repo.ensure_subject(CHAT, "GROUP")
    env.writer.confirm_group_fact(
        CHAT,
        ref,
        expected_subject_revision=int(group["revision"]),
        changes=[change(source.text, "Be kind.", "rule", assertion_kind="admin_confirmed")],
        confirmation=AdminConfirmation(USER, True),
    )
    leases = AnswerLeaseService(env.repo)
    lease = leases.acquire(CHAT, ["GROUP"], request_id="group")
    facts = leases.snapshot(lease)
    refs = [{"fact_id": facts[0]["fact_id"], "fact_version": int(facts[0]["revision"])}]
    bound = leases.bind(lease, refs)
    assert env.repo._read(CHAT, lease.lease_id)["evidence_authors"] == [USER]
    subject = env.repo.get_subject(CHAT, USER)
    env.repo.begin_subject_stop(CHAT, USER, expected_revision=int(subject["revision"]))
    with pytest.raises(MemoryUnavailable):
        leases.validate(bound, refs)


def test_lease_expiry_and_send_margin_are_logical_before_ttl_gc(env, answered):
    leases, lease, refs, _ = answered
    bound = leases.bind(lease, refs)
    env.clock.now = bound.lease_until - 40
    with pytest.raises(MemoryUnavailable, match="Insufficient"):
        leases.validate(bound, refs)
    env.clock.now = bound.lease_until
    with pytest.raises(MemoryUnavailable):
        leases.snapshot(bound)
    assert env.repo._read(CHAT, lease.lease_id)


def test_scope_and_selection_cannot_be_changed_by_caller(env, answered):
    leases, lease, refs, _ = answered
    with pytest.raises(MemoryUnavailable):
        leases.snapshot(replace(lease, subject_ids=("43",)))
    with pytest.raises(MemoryInputError):
        leases.bind(lease, [{**refs[0], "value": "invented"}])
    bound = leases.bind(lease, refs)
    with pytest.raises(MemoryConflict):
        leases.bind(bound, [])
    with pytest.raises(MemoryUnavailable):
        leases.validate(bound, [])


def test_profile_evidence_remains_valid_after_raw_expiry(env, answered):
    leases, lease, refs, _ = answered
    leases.release(lease)
    env.clock.now += 31 * 86400
    fresh = leases.acquire(CHAT, [USER], request_id="after-raw")
    facts = leases.snapshot(fresh)
    assert facts[0]["value"] == "Python"
    bound = leases.bind(fresh, refs)
    leases.validate(bound, refs)


@pytest.mark.parametrize("operation", ["snapshot", "bind", "validate"])
def test_slow_final_transaction_cannot_return_an_expired_send_permit(env, answered, monkeypatch, operation):
    leases, lease, refs, _ = answered
    if operation == "validate":
        lease = leases.bind(lease, refs)
    original = env.repo._transaction

    def slow(operations):
        result = original(operations)
        env.clock.now = lease.lease_until
        return result

    monkeypatch.setattr(env.repo, "_transaction", slow)
    with pytest.raises(MemoryUnavailable):
        getattr(leases, operation)(lease, refs) if operation != "snapshot" else leases.snapshot(lease)


def test_snapshot_fence_limit_is_explicit_and_never_truncated(env):
    leases = AnswerLeaseService(env.repo)
    with pytest.raises(MemoryInputError, match="atomic fence limit"):
        leases._checks([{"pk": "synthetic", "sk": str(index), "revision": 1} for index in range(99)])
