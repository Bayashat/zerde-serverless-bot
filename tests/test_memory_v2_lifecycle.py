"""Deletion fences, bounded physical purge, and anti-revival semantics in real Moto."""

from dataclasses import replace

import pytest
from services.memory_v2.leases import AnswerLeaseService
from services.memory_v2.lifecycle import MemoryLifecycle
from services.memory_v2.models import MemoryConflict, MemoryUnavailable

from tests import test_memory_v2_contract as contract
from tests.test_memory_v2_contract import CHAT, USER, activate, change, commit, event

env = contract.env


@pytest.fixture
def stored(env):
    activate(env)
    source = event(env)
    ref = env.repo.register_source(source)
    commit(env, ref)
    return source, ref


def finish(lifecycle, job):
    for _ in range(50):
        job = lifecycle.advance(CHAT, job["sk"], max_pages=2)
        if job["state"] == "DONE":
            return job
    pytest.fail("Deletion did not reach its durable terminal state")


def test_forget_me_hides_immediately_waits_answer_then_physically_clears(env, stored):
    source, _ = stored
    leases = AnswerLeaseService(env.repo)
    lease = leases.acquire(CHAT, [USER], request_id="answer")
    facts = leases.snapshot(lease)
    bound = leases.bind(lease, [{"fact_id": facts[0]["fact_id"], "fact_version": int(facts[0]["revision"])}])
    lifecycle = MemoryLifecycle(env.repo)
    job = lifecycle.begin(CHAT, scope="subject", target=USER)
    with pytest.raises(MemoryUnavailable):
        env.repo.get_profile(CHAT, USER)
    assert lifecycle.advance(CHAT, job["sk"])["state"] == "WAITING"
    assert env.repo._read(CHAT, "RAW#8")
    leases.release(bound)
    done = finish(lifecycle, job)
    assert done["deleted_rows"] >= 4
    assert env.repo.get_profile(CHAT, USER) == []
    assert not env.repo._read(CHAT, "RAW#8")
    with pytest.raises(MemoryUnavailable):
        env.repo.register_source(source)
    env.clock.now += 1
    fresh = env.repo.register_source(event(env, "9"))
    commit(env, fresh)
    assert env.repo.get_profile(CHAT, USER)[0]["value"] == "Python"


def test_forget_this_keeps_minimal_source_tombstone_and_blocks_webhook_replay(env, stored):
    source, _ = stored
    lifecycle = MemoryLifecycle(env.repo)
    done = finish(lifecycle, lifecycle.begin(CHAT, scope="source", target="8"))
    assert done["state"] == "DONE"
    assert not env.repo.get_profile(CHAT, USER)
    tombstone = env.repo.get_observation(CHAT, "8")
    assert tombstone["deleted"] is True
    assert not {"actor_user_id", "text", "content_hash", "ttl"} & set(tombstone)
    with pytest.raises(MemoryUnavailable):
        env.repo.register_source(source)
    env.clock.now += 1
    with pytest.raises(MemoryUnavailable):
        env.repo.observe(replace(source, text="I use Rust.", edited_at=env.clock.now))


def test_source_purge_waits_fixed_worker_lease_before_confirmation(env):
    activate(env)
    ref = env.repo.register_source(event(env))
    lease = env.repo.claim_work(CHAT, ref)
    lifecycle = MemoryLifecycle(env.repo)
    job = lifecycle.begin(CHAT, scope="source", target="8")
    assert lifecycle.advance(CHAT, job["sk"])["state"] == "WAITING"
    with pytest.raises(MemoryUnavailable):
        env.repo.valid_leased_source(CHAT, lease)
    env.clock.now = lease.lease_until
    assert finish(lifecycle, job)["state"] == "DONE"
    assert env.repo.claim_work(CHAT, ref) is None


def test_unbound_answer_conservatively_delays_source_purge(env, stored):
    leases = AnswerLeaseService(env.repo)
    lease = leases.acquire(CHAT, [USER], request_id="unbound")
    lifecycle = MemoryLifecycle(env.repo)
    job = lifecycle.begin(CHAT, scope="source", target="8")
    assert lifecycle.advance(CHAT, job["sk"])["state"] == "WAITING"
    env.clock.now = lease.lease_until
    assert finish(lifecycle, job)["state"] == "DONE"


def test_optout_survives_cleanup_until_explicit_optin(env, stored):
    lifecycle = MemoryLifecycle(env.repo)
    finish(lifecycle, lifecycle.begin(CHAT, scope="subject", target=USER, optout=True))
    env.clock.now += 10
    with pytest.raises(MemoryUnavailable):
        env.repo.register_source(event(env, "9"))
    subject = env.repo.get_subject(CHAT, USER)
    assert subject["optout"] is True
    env.repo.opt_in(CHAT, USER, expected_revision=int(subject["revision"]))
    assert env.repo.register_source(event(env, "10"))


def test_group_forget_stops_and_new_epoch_rejects_same_second_old_delivery(env, stored):
    old_source, old_ref = stored
    lifecycle = MemoryLifecycle(env.repo)
    finish(lifecycle, lifecycle.begin(CHAT, scope="group"))
    stopped = env.repo.get_control(CHAT)
    assert stopped["state"] == "STOPPED"
    activated = env.repo.activate_group(CHAT, expected_revision=int(stopped["revision"]))
    assert activated["epoch"] != old_ref.epoch
    with pytest.raises(MemoryUnavailable):
        env.repo.register_source(old_source)
    env.clock.now += 1
    assert env.repo.register_source(event(env, "9")).epoch == activated["epoch"]


def test_other_subject_data_and_shared_budget_partition_are_preserved(env, stored):
    other = env.repo.register_source(event(env, "9", user="43", text="I use Rust."))
    commit(env, other, [change("I use Rust.", "Rust")])
    env.table.put_item(Item={"pk": "MEMORY_BUDGET#2026-09", "sk": "COUNTER", "spent": 123})
    lifecycle = MemoryLifecycle(env.repo)
    finish(lifecycle, lifecycle.begin(CHAT, scope="subject", target=USER))
    assert env.repo.get_profile(CHAT, "43")[0]["value"] == "Rust"
    assert env.repo._read(CHAT, "RAW#9")
    assert env.table.get_item(Key={"pk": "MEMORY_BUDGET#2026-09", "sk": "COUNTER"})["Item"]["spent"] == 123


def test_derived_owner_failure_never_confirms_and_resumes(env, stored):
    ready = False

    def cleaner(chat_id, job):
        assert chat_id == CHAT and job["scope"] == "subject"
        return ready

    lifecycle = MemoryLifecycle(env.repo, derived_cleaners=[cleaner])
    job = lifecycle.begin(CHAT, scope="subject", target=USER)
    assert lifecycle.advance(CHAT, job["sk"])["state"] == "DERIVED"
    assert env.repo.get_subject(CHAT, USER)["state"] == "STOPPING"
    ready = True
    assert finish(lifecycle, job)["state"] == "DONE"


def test_purge_cursor_resumes_and_ref_only_answer_records_are_removed(env, stored):
    for index in range(100):
        env.table.put_item(
            Item={
                "pk": f"CHAT#{CHAT}",
                "sk": f"ANSWER_REPLY#{index:03}",
                "revision": 1,
                "source_refs": [{"source_id": "8", "source_version": 1, "epoch": "synthetic"}],
                "evidence_authors": [USER],
            }
        )
    lifecycle = MemoryLifecycle(env.repo)
    job = lifecycle.begin(CHAT, scope="subject", target=USER)
    first = lifecycle.advance(CHAT, job["sk"], max_pages=2)
    assert first["state"] == "DELETING" and first["cursor"]
    done = finish(lifecycle, first)
    assert done["deleted_rows"] >= 100
    assert not list(env.repo._list(CHAT, "ANSWER_REPLY#"))


def test_overlapping_scopes_are_serialized(env, stored):
    lifecycle = MemoryLifecycle(env.repo)
    job = lifecycle.begin(CHAT, scope="subject", target=USER)
    assert lifecycle.begin(CHAT, scope="subject", target=USER) == job
    with pytest.raises(MemoryConflict):
        lifecycle.begin(CHAT, scope="group")


def test_transaction_fault_leaves_fence_and_job_atomic(env, stored, monkeypatch):
    lifecycle = MemoryLifecycle(env.repo)
    monkeypatch.setattr(env.repo, "_transaction", lambda operations: (_ for _ in ()).throw(RuntimeError("offline")))
    with pytest.raises(RuntimeError):
        lifecycle.begin(CHAT, scope="subject", target=USER)
    assert env.repo.get_subject(CHAT, USER)["state"] == "ACTIVE"
    assert not list(env.repo._list(CHAT, "PURGE#"))


def test_delayed_clean_after_source_purge_cannot_recreate_canonical_body(env):
    from tests import test_memory_v2_ingestion as ingestion_tests

    ingestion = ingestion_tests.ingestion.__wrapped__(env)
    _, ref, digest = ingestion_tests.prepare(env, ingestion)
    case = ingestion_tests.clean(ingestion, ref, digest)
    lifecycle = MemoryLifecycle(env.repo)
    finish(lifecycle, lifecycle.begin(CHAT, scope="source", target="8"))
    assert ingestion.promote_clean(case) == "EXPIRED"
    assert not env.repo._read(CHAT, "RAW#8")
    assert not env.repo.get_work(CHAT, ref)
    assert not list(env.repo._list(CHAT, "FACT#"))


def test_subject_purge_removes_quarantined_actor_free_candidate(env):
    from tests import test_memory_v2_ingestion as ingestion_tests

    ingestion = ingestion_tests.ingestion.__wrapped__(env)
    ingestion_tests.prepare(env, ingestion)
    lifecycle = MemoryLifecycle(env.repo)
    finish(lifecycle, lifecycle.begin(CHAT, scope="subject", target=USER))
    assert not env.repo._read(CHAT, "CANDIDATE#8#1")
    assert not env.repo.get_observation(CHAT, "8")


def test_optin_does_not_shorten_post_purge_cutoff(env, stored):
    lifecycle = MemoryLifecycle(env.repo)
    finish(lifecycle, lifecycle.begin(CHAT, scope="subject", target=USER, optout=True))
    subject = env.repo.get_subject(CHAT, USER)
    env.repo.opt_in(CHAT, USER, expected_revision=int(subject["revision"]))
    with pytest.raises(MemoryUnavailable):
        env.repo.register_source(event(env, "9"))
    env.clock.now += 1
    assert env.repo.register_source(event(env, "10"))


def test_recovery_keeps_filtered_scan_cursor_and_finishes_pending_job(env, stored):
    for index in range(60):
        env.table.put_item(Item={"pk": "UNRELATED", "sk": str(index), "kind": "NOT_A_PURGE"})
    lifecycle = MemoryLifecycle(env.repo)
    job = lifecycle.begin(CHAT, scope="source", target="8")
    for _ in range(20):
        lifecycle.recover(max_pages=1)
        if env.repo._read(CHAT, job["sk"])["state"] == "DONE":
            break
    assert env.repo._read(CHAT, job["sk"])["state"] == "DONE"


def test_optout_can_strengthen_pending_forget_and_cannot_be_downgraded(env, stored):
    lifecycle = MemoryLifecycle(env.repo)
    lifecycle.begin(CHAT, scope="subject", target=USER)
    strengthened = lifecycle.begin(CHAT, scope="subject", target=USER, optout=True)
    assert strengthened["optout"] is True
    assert lifecycle.begin(CHAT, scope="subject", target=USER)["optout"] is True
    finish(lifecycle, strengthened)
    assert env.repo.get_subject(CHAT, USER)["optout"] is True


def test_forget_removes_own_feedback_identity_on_another_authors_group_fact(env, stored):
    from services.memory_v2.models import AdminConfirmation

    source = event(env, "90", "Be kind.", user="43", source_kind="confirmation")
    ref = env.repo.register_source(source)
    group = env.repo.ensure_subject(CHAT, "GROUP")
    env.writer.confirm_group_fact(
        CHAT,
        ref,
        expected_subject_revision=int(group["revision"]),
        changes=[change(source.text, "Be kind.", "rule", assertion_kind="admin_confirmed")],
        confirmation=AdminConfirmation("43", True),
    )
    fact = env.repo.get_profile(CHAT, "GROUP")[0]
    env.writer.reject_fact(
        CHAT, fact["fact_id"], expected_fact_version=int(fact["revision"]), confirmation=AdminConfirmation(USER, True)
    )
    lifecycle = MemoryLifecycle(env.repo)
    finish(lifecycle, lifecycle.begin(CHAT, scope="subject", target=USER))
    assert not env.repo._read(CHAT, fact["fact_id"])
    assert env.repo._read(CHAT, "RAW#90")["actor_user_id"] == "43"
