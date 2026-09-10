"""Real transactions protect trend/media sources without shortening fact evidence."""

from dataclasses import replace

import pytest
from services.memory_v2.leases import ANSWER_LEASE_SECONDS, AnswerLeaseService
from services.memory_v2.lifecycle import MemoryLifecycle
from services.memory_v2.models import MemoryConflict, MemoryInputError, MemoryUnavailable, SourceRef

from tests import test_memory_v2_contract as contract
from tests.test_memory_v2_contract import CHAT, USER, activate, commit, event
from tests.test_memory_v2_lifecycle import finish

env = contract.env
ASKER = "99"


def extra(env, *, kind="trend", source_id="8", actor=USER, chat=CHAT):
    source = event(env, source_id, text="We discuss Python.", user=actor, chat=chat)
    ref = env.repo.register_source(source) if kind == "trend" else env.repo.observe(replace(source, text=""))
    return source, ref


def acquire(env, *, subjects=(), request_id="answer"):
    leases = AnswerLeaseService(env.repo)
    lease = leases.acquire(CHAT, list(subjects), request_id=request_id, actor_user_id=ASKER)
    return leases, lease


@pytest.mark.parametrize("kind", ["trend", "media"])
def test_bind_persists_only_exact_source_scope_and_validate_reloads_it(env, kind):
    activate(env)
    _, ref = extra(env, kind=kind)
    leases, lease = acquire(env)
    bound = leases.bind(lease, [], extra_source_refs=[ref], extra_source_kind=kind)
    row = env.repo._read(CHAT, lease.lease_id)
    assert row["source_refs"] == row["extra_source_refs"] == [ref.as_dict()]
    assert row["evidence_authors"] == [USER]
    assert row["extra_source_kind"] == kind
    assert row["extra_source_scopes"] == [
        {
            "source_id": "8",
            "actor_user_id": USER,
            "subject_generation": env.repo.get_subject(CHAT, USER)["generation"],
            "expires_at": env.clock.now + (7 if kind == "trend" else 1) * 86400,
        }
    ]
    assert row["lease_until"] == env.clock.now + ANSWER_LEASE_SECONDS
    assert not {"text", "body", "value", "caption", "file_id", "question"} & row.keys()
    leases.validate(bound, [])  # No optional argument can be forgotten by the send caller.
    assert not env.repo.get_subject(CHAT, ASKER)
    if kind == "media":
        assert not env.repo.get_source_head(CHAT, "8")
        assert not env.repo._read(CHAT, "RAW#8")


def test_media_class_cannot_be_used_for_trend_or_downgrade_bound_lease(env):
    activate(env)
    _, media_ref = extra(env, kind="media")
    leases, lease = acquire(env)
    with pytest.raises(MemoryUnavailable):
        leases.bind(lease, [], extra_source_refs=[media_ref])  # Default is strict trend.
    bound = leases.bind(lease, [], extra_source_refs=[media_ref], extra_source_kind="media")
    with pytest.raises(MemoryConflict):
        leases.bind(bound, [], extra_source_refs=[media_ref], extra_source_kind="trend")
    with pytest.raises(MemoryConflict):
        leases.bind(bound, [])
    assert leases.bind(bound, [], extra_source_refs=[media_ref], extra_source_kind="media") == bound


@pytest.mark.parametrize("kind", ["trend", "media"])
@pytest.mark.parametrize("scope", ["source", "subject", "group"])
def test_deletion_waits_even_when_extra_author_was_not_selected_subject(env, kind, scope):
    activate(env)
    _, ref = extra(env, kind=kind)
    leases, lease = acquire(env)
    bound = leases.bind(lease, [], extra_source_refs=[ref], extra_source_kind=kind)
    lifecycle = MemoryLifecycle(env.repo)
    target = "8" if scope == "source" else USER if scope == "subject" else None
    job = lifecycle.begin(CHAT, scope=scope, target=target)
    assert lifecycle.advance(CHAT, job["sk"])["state"] == "WAITING"
    with pytest.raises(MemoryUnavailable):
        leases.validate(bound, [])
    leases.release(bound)
    assert finish(lifecycle, job)["state"] == "DONE"


def test_optout_revokes_bound_extra_and_old_ref_cannot_reappear_after_optin(env):
    activate(env)
    _, ref = extra(env, kind="media")
    leases, lease = acquire(env)
    bound = leases.bind(lease, [], extra_source_refs=[ref], extra_source_kind="media")
    lifecycle = MemoryLifecycle(env.repo)
    job = lifecycle.begin(CHAT, scope="subject", target=USER, optout=True)
    with pytest.raises(MemoryUnavailable):
        leases.validate(bound, [])
    leases.release(bound)
    finish(lifecycle, job)
    subject = env.repo.get_subject(CHAT, USER)
    env.repo.opt_in(CHAT, USER, expected_revision=int(subject["revision"]))
    leases, new_lease = acquire(env, request_id="after-optin")
    with pytest.raises(MemoryUnavailable):
        leases.bind(new_lease, [], extra_source_refs=[ref], extra_source_kind="media")


@pytest.mark.parametrize("kind", ["trend", "media"])
def test_edit_invalidates_bound_source_and_media_cannot_rebind_edited_obs(env, kind):
    activate(env)
    source, ref = extra(env, kind=kind)
    leases, lease = acquire(env)
    bound = leases.bind(lease, [], extra_source_refs=[ref], extra_source_kind=kind)
    env.clock.now += 1
    edited = replace(source, text="We discuss Rust.", edited_at=env.clock.now)
    updated = env.repo.observe(edited)
    with pytest.raises(MemoryUnavailable):
        leases.validate(bound, [])
    leases, another = acquire(env, request_id="updated")
    with pytest.raises(MemoryUnavailable):
        leases.bind(another, [], extra_source_refs=[updated], extra_source_kind=kind)
    if kind == "trend":
        # A newly accepted version can support a newly computed trend.
        env.repo.register_source(edited, expected_source_version=ref.source_version)
        fresh = leases.bind(another, [], extra_source_refs=[updated], extra_source_kind="trend")
        leases.validate(fresh, [])


def test_cross_group_or_old_epoch_ref_cannot_bind(env):
    activate(env)
    activate(env, -100456)
    _, ref = extra(env, chat=-100456)
    leases, lease = acquire(env)
    with pytest.raises(MemoryUnavailable):
        leases.bind(lease, [], extra_source_refs=[ref])
    _, current = extra(env)
    with pytest.raises(MemoryUnavailable):
        leases.bind(lease, [], extra_source_refs=[replace(current, epoch="old-epoch")])


@pytest.mark.parametrize("pointer", ["HEAD#8", "RAW#8"])
def test_trend_requires_current_accepted_body_at_every_validation(env, pointer):
    activate(env)
    _, ref = extra(env)
    leases, lease = acquire(env)
    bound = leases.bind(lease, [], extra_source_refs=[ref])
    env.table.delete_item(Key={"pk": f"CHAT#{CHAT}", "sk": pointer})
    with pytest.raises(MemoryUnavailable):
        leases.validate(bound, [])


def test_pre_activation_original_time_is_rejected_even_with_current_pointer_version(env):
    activate(env)
    _, ref = extra(env, kind="media")
    observation = env.repo.get_observation(CHAT, "8")
    observation["original_sent_at"] -= 1
    env.table.put_item(Item=observation)
    leases, lease = acquire(env)
    with pytest.raises(MemoryUnavailable):
        leases.bind(lease, [], extra_source_refs=[ref], extra_source_kind="media")


@pytest.mark.parametrize("kind", ["trend", "media"])
def test_source_window_is_logical_not_dependent_on_physical_ttl(env, kind):
    activate(env)
    _, ref = extra(env, kind=kind)
    env.clock.now += (7 if kind == "trend" else 1) * 86400
    assert env.repo.get_observation(CHAT, "8")
    leases, lease = acquire(env)
    with pytest.raises(MemoryUnavailable):
        leases.bind(lease, [], extra_source_refs=[ref], extra_source_kind=kind)


@pytest.mark.parametrize("operation", ["bind", "validate"])
@pytest.mark.parametrize("kind", ["trend", "media"])
def test_slow_final_transaction_rechecks_source_window(env, monkeypatch, operation, kind):
    activate(env)
    _, ref = extra(env, kind=kind)
    env.clock.now += (7 if kind == "trend" else 1) * 86400 - 50
    leases, lease = acquire(env)
    if operation == "validate":
        lease = leases.bind(lease, [], extra_source_refs=[ref], extra_source_kind=kind)
    original = env.repo._transaction

    def slow(operations):
        original(operations)
        env.clock.now += 11 if operation == "validate" else 51

    monkeypatch.setattr(env.repo, "_transaction", slow)
    with pytest.raises(MemoryUnavailable):
        if operation == "bind":
            leases.bind(lease, [], extra_source_refs=[ref], extra_source_kind=kind)
        else:
            leases.validate(lease, [])


@pytest.mark.parametrize("operation", ["bind", "validate"])
def test_final_transaction_checks_observation_and_author_revision(env, monkeypatch, operation):
    activate(env)
    source, ref = extra(env)
    leases, lease = acquire(env)
    if operation == "validate":
        lease = leases.bind(lease, [], extra_source_refs=[ref])
    original = env.repo._transaction
    fired = False

    def edit(operations):
        nonlocal fired
        if not fired:
            fired = True
            env.clock.now += 1
            env.repo.observe(replace(source, text="Edited while reading.", edited_at=env.clock.now))
        return original(operations)

    monkeypatch.setattr(env.repo, "_transaction", edit)
    with pytest.raises(MemoryConflict):
        if operation == "bind":
            leases.bind(lease, [], extra_source_refs=[ref])
        else:
            leases.validate(lease, [])


def test_retained_old_fact_still_works_with_fresh_extra_source(env):
    activate(env)
    fact_source = env.repo.register_source(event(env))
    commit(env, fact_source)
    facts = [
        {"fact_id": row["fact_id"], "fact_version": int(row["fact_version"])}
        for row in env.repo.get_profile(CHAT, USER)
    ]
    env.clock.now += 31 * 86400
    env.table.delete_item(Key={"pk": f"CHAT#{CHAT}", "sk": "RAW#8"})
    _, trend_ref = extra(env, source_id="9", actor="43")
    leases, lease = acquire(env, subjects=[USER])
    bound = leases.bind(lease, facts, extra_source_refs=[trend_ref])
    leases.validate(bound, facts)
    row = env.repo._read(CHAT, bound.lease_id)
    assert row["source_refs"] == [fact_source.as_dict(), trend_ref.as_dict()]
    assert row["evidence_authors"] == [USER, "43"]


def test_shared_fact_and_extra_source_reference_is_deduplicated(env):
    activate(env)
    ref = env.repo.register_source(event(env))
    commit(env, ref)
    facts = [
        {"fact_id": row["fact_id"], "fact_version": int(row["fact_version"])}
        for row in env.repo.get_profile(CHAT, USER)
    ]
    leases, lease = acquire(env, subjects=[USER])
    bound = leases.bind(lease, facts, extra_source_refs=[ref])
    leases.validate(bound, facts)
    assert env.repo._read(CHAT, lease.lease_id)["source_refs"] == [ref.as_dict()]


def test_eight_facts_plus_ten_sources_fit_actual_atomic_transaction(env, monkeypatch):
    activate(env)
    subjects, facts, extras = [], [], []
    for index in range(8):
        actor = str(100 + index)
        ref = env.repo.register_source(event(env, str(200 + index), user=actor))
        commit(env, ref)
        subjects.append(actor)
        facts.extend(
            {"fact_id": row["fact_id"], "fact_version": int(row["fact_version"])}
            for row in env.repo.get_profile(CHAT, actor)
        )
    for index in range(10):
        _, ref = extra(env, source_id=str(300 + index), actor=str(400 + index))
        extras.append(ref)
    leases, lease = acquire(env, subjects=subjects)
    original = env.repo._transaction
    counts = []

    def counted(operations):
        counts.append(len(operations))
        return original(operations)

    monkeypatch.setattr(env.repo, "_transaction", counted)
    bound = leases.bind(lease, facts, extra_source_refs=extras)
    leases.validate(bound, facts)
    assert counts and max(counts) <= 100
    assert len(env.repo._read(CHAT, lease.lease_id)["source_refs"]) == 18


@pytest.mark.parametrize("invalid", ["too_many", "duplicate", "dict", "unknown_class"])
def test_extra_input_limit_is_explicit_and_cannot_be_silently_truncated(env, invalid):
    activate(env)
    _, ref = extra(env)
    leases, lease = acquire(env)
    values, kind = [ref], "trend"
    if invalid == "too_many":
        values = [SourceRef(str(index + 1), 1, ref.epoch) for index in range(11)]
    elif invalid == "duplicate":
        values *= 2
    elif invalid == "dict":
        values = [ref.as_dict()]
    else:
        kind = "fact"
    with pytest.raises(MemoryInputError):
        leases.bind(lease, [], extra_source_refs=values, extra_source_kind=kind)
    assert env.repo._read(CHAT, lease.lease_id)["bound"] is False
