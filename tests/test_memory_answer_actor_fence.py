"""Requesters remain deletion participants even when asking about another profile."""

from dataclasses import replace

import pytest
from services.memory_v2.leases import AnswerLeaseService
from services.memory_v2.lifecycle import MemoryLifecycle
from services.memory_v2.models import MemoryConflict, MemoryInputError, MemoryUnavailable

from tests import test_memory_v2_contract as contract
from tests.test_memory_v2_contract import CHAT, USER, activate, commit, event

env = contract.env
ACTOR = "43"


def target(env):
    activate(env)
    ref = env.repo.register_source(event(env))
    commit(env, ref)
    return [
        {"fact_id": fact["fact_id"], "fact_version": int(fact["fact_version"])}
        for fact in env.repo.get_profile(CHAT, USER)
    ]


def test_bound_other_person_answer_waits_for_requester_forget(env):
    refs = target(env)
    leases = AnswerLeaseService(env.repo)
    lease = leases.acquire(CHAT, [USER], request_id="ask-other", actor_user_id=ACTOR)
    lease = leases.bind(lease, refs)
    assert not env.repo.get_subject(CHAT, ACTOR)
    lifecycle = MemoryLifecycle(env.repo)
    job = lifecycle.begin(CHAT, scope="subject", target=ACTOR)
    assert lifecycle.advance(CHAT, job["sk"])["state"] == "WAITING"
    with pytest.raises(MemoryUnavailable):
        leases.validate(lease, refs)
    leases.release(lease)
    assert lifecycle.advance(CHAT, job["sk"])["state"] == "DONE"
    assert not env.repo._read(CHAT, lease.lease_id)
    assert env.repo.get_profile(CHAT, USER)


def test_unknown_answer_has_actor_control_lease_without_new_subject(env):
    activate(env)
    leases = AnswerLeaseService(env.repo)
    lease = leases.acquire(CHAT, [], request_id="unknown", actor_user_id=ACTOR)
    assert leases.snapshot(lease) == []
    bound = leases.bind(lease, [])
    leases.validate(bound, [])
    assert not env.repo.get_subject(CHAT, ACTOR)
    assert bound.actor_user_id == ACTOR and bound.subject_ids == ()
    lifecycle = MemoryLifecycle(env.repo)
    job = lifecycle.begin(CHAT, scope="subject", target=ACTOR)
    assert lifecycle.advance(CHAT, job["sk"])["state"] == "WAITING"
    leases.release(bound)
    assert lifecycle.advance(CHAT, job["sk"])["state"] == "DONE"


def test_zero_subject_lease_without_actor_is_not_allowed(env):
    activate(env)
    with pytest.raises(MemoryInputError):
        AnswerLeaseService(env.repo).acquire(CHAT, [], request_id="unattributed")


def test_optout_actor_can_read_others_without_new_learning_state(env):
    refs = target(env)
    lifecycle = MemoryLifecycle(env.repo)
    job = lifecycle.begin(CHAT, scope="subject", target=ACTOR, optout=True)
    assert lifecycle.advance(CHAT, job["sk"])["state"] == "DONE"
    original = env.repo.get_subject(CHAT, ACTOR)
    leases = AnswerLeaseService(env.repo)
    lease = leases.acquire(CHAT, [USER], request_id="optout-requester", actor_user_id=ACTOR)
    assert leases.snapshot(lease)
    bound = leases.bind(lease, refs)
    leases.validate(bound, refs)
    assert env.repo.get_subject(CHAT, ACTOR) == original and original["optout"]


def test_stopping_actor_cannot_acquire_even_for_another_person(env):
    target(env)
    MemoryLifecycle(env.repo).begin(CHAT, scope="subject", target=ACTOR)
    with pytest.raises(MemoryUnavailable, match="requester is being erased"):
        AnswerLeaseService(env.repo).acquire(CHAT, [USER], request_id="late", actor_user_id=ACTOR)


def test_actor_identity_cannot_be_substituted_on_existing_lease(env):
    target(env)
    leases = AnswerLeaseService(env.repo)
    lease = leases.acquire(CHAT, [USER], request_id="bound-actor", actor_user_id=ACTOR)
    with pytest.raises(MemoryUnavailable):
        leases.snapshot(replace(lease, actor_user_id=USER))


def test_actor_creation_after_acquire_invalidates_missing_snapshot(env):
    target(env)
    leases = AnswerLeaseService(env.repo)
    lease = leases.acquire(CHAT, [USER], request_id="no-actor-profile", actor_user_id=ACTOR)
    env.repo.ensure_subject(CHAT, ACTOR)
    with pytest.raises(MemoryUnavailable, match="requester metadata changed"):
        leases.snapshot(lease)


def test_actual_missing_actor_condition_closes_acquire_race(env):
    target(env)
    leases = AnswerLeaseService(env.repo)
    transaction = env.repo._transaction
    fired = False

    def race(operations):
        nonlocal fired
        if not fired and any(
            operation.get("Put", {}).get("Item", {}).get("kind") == "ANSWER_LEASE" for operation in operations
        ):
            fired = True
            env.repo.ensure_subject(CHAT, ACTOR)
        return transaction(operations)

    env.repo._transaction = race
    with pytest.raises(MemoryConflict):
        leases.acquire(CHAT, [USER], request_id="racing", actor_user_id=ACTOR)
    assert not list(env.repo._list(CHAT, "ANSWER_LEASE#"))


def test_actor_same_as_fact_subject_deduplicates_native_transaction(env):
    refs = target(env)
    leases = AnswerLeaseService(env.repo)
    lease = leases.acquire(CHAT, [USER], request_id="self", actor_user_id=USER)
    assert leases.snapshot(lease)
    bound = leases.bind(lease, refs)
    leases.validate(bound, refs)
