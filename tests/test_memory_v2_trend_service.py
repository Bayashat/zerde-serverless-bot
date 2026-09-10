"""Versioned trend contributions against Moto native DynamoDB semantics."""

from dataclasses import replace

import pytest
from botocore.exceptions import ClientError
from services.memory_v2.lifecycle import MemoryLifecycle
from services.memory_v2.models import MemoryConflict, MemoryInputError, MemoryUnavailable
from services.memory_v2.trend_service import REFRESH_KEY, TrendService
from services.memory_v2.trends import WINDOW_SECONDS

from tests import test_memory_v2_contract as contract
from tests.test_memory_v2_contract import CHAT, USER, activate, event
from tests.test_memory_v2_lifecycle import finish

env = contract.env


@pytest.fixture
def stored(env):
    activate(env)
    source = event(env)
    ref = env.repo.register_source(source)
    service = TrendService(env.repo)
    row = service.contribute(CHAT, ref)
    return service, source, ref, row


def test_contribution_has_one_source_owner_no_body_and_replay_counts_once(env, stored):
    service, _, ref, row = stored
    replay = service.contribute(CHAT, ref)
    assert replay["revision"] == row["revision"] + 1
    assert not {"text", "profile", "evidence", "value"} & set(replay)
    view = service.read(CHAT)
    assert view.snapshot.eligible_source_count == 1
    assert view.snapshot.topics[0].topic == "python"
    assert view.snapshot.topics[0].message_count == view.snapshot.topics[0].participant_count == 1
    assert view.source_refs == (ref,) and view.evidence_authors == (USER,)
    assert view.coverage["inventory_verified"] is False
    assert view.coverage["newer_sources_may_be_missing"] is True


def test_multiple_sources_count_messages_and_distinct_people_without_personal_facts(env, stored):
    service, _, _, _ = stored
    for message_id, user in (("9", USER), ("10", "43")):
        ref = env.repo.register_source(event(env, message_id, "Python and AWS are useful.", user=user))
        service.contribute(CHAT, ref)
    view = service.read(CHAT)
    python = next(topic for topic in view.snapshot.topics if topic.topic == "python")
    assert (python.message_count, python.participant_count) == (3, 2)
    assert env.repo.get_profile(CHAT, USER) == []
    assert len(view.source_refs) == 3 and view.evidence_authors == (USER, "43")


def test_edit_invalidates_before_new_safe_source_admission_and_old_task_cannot_restore(env, stored):
    service, source, old, _ = stored
    env.clock.now += 1
    changed = replace(source, text="I use AWS.", edited_at=env.clock.now)
    ref = env.repo.observe(changed)
    assert service.read(CHAT).snapshot.eligible_source_count == 0
    with pytest.raises(MemoryUnavailable):
        service.contribute(CHAT, old)
    assert env.repo.register_source(changed, expected_source_version=1) == ref
    service.contribute(CHAT, ref)
    assert [topic.topic for topic in service.read(CHAT).snapshot.topics] == ["cloud_infrastructure"]


def test_unsafe_edit_while_learning_paused_cannot_leave_stale_topic(env, stored):
    service, source, ref, _ = stored
    control = env.repo.get_control(CHAT)
    env.repo.set_learning_enabled(CHAT, False, expected_revision=int(control["revision"]))
    assert service.read(CHAT).snapshot.eligible_source_count == 1
    env.clock.now += 1
    env.repo.observe(replace(source, text="My password is fake-secret.", edited_at=env.clock.now))
    assert service.read(CHAT).snapshot.eligible_source_count == 0
    with pytest.raises(MemoryUnavailable):
        service.contribute(CHAT, ref)


def test_quoted_topic_never_becomes_group_discussion_signal(env):
    activate(env)
    source = event(env, text="Python. Thank you.", quoted_spans=((0, 7),))
    ref = env.repo.register_source(source)
    service = TrendService(env.repo)
    assert service.contribute(CHAT, ref)["topics"] == []
    assert service.read(CHAT).snapshot.topics == ()


@pytest.mark.parametrize("scope,target", [("subject", USER), ("source", "8"), ("group", "GROUP")])
def test_lifecycle_physically_owns_contributions_and_fences_late_reads(env, stored, scope, target):
    service, _, ref, _ = stored
    view = service.read(CHAT)
    lifecycle = MemoryLifecycle(env.repo)
    job = lifecycle.begin(CHAT, scope=scope, target=target)
    with pytest.raises((MemoryUnavailable, MemoryConflict)):
        service.validate_snapshot(view)
    with pytest.raises(MemoryUnavailable):
        service.contribute(CHAT, ref)
    done = finish(lifecycle, job)
    assert done["state"] == "DONE" and not env.repo._read(CHAT, "TREND#00000000000000000008")


def test_forget_subject_preserves_other_person_and_other_group_contributions(env, stored):
    service, _, _, _ = stored
    other = env.repo.register_source(event(env, "9", user="43"))
    service.contribute(CHAT, other)
    activate(env, chat=-100456)
    foreign = env.repo.register_source(event(env, "8", chat=-100456))
    service.contribute(-100456, foreign)
    lifecycle = MemoryLifecycle(env.repo)
    finish(lifecycle, lifecycle.begin(CHAT, scope="subject", target=USER))
    assert service.read(CHAT).evidence_authors == ("43",)
    assert service.read(-100456).snapshot.eligible_source_count == 1


def test_logical_seven_day_expiry_does_not_wait_for_dynamodb_ttl(env, stored):
    service, _, ref, _ = stored
    env.clock.now += WINDOW_SECONDS
    assert env.repo._read(CHAT, "TREND#00000000000000000008")  # Moto leaves TTL rows present.
    view = service.read(CHAT)
    assert view.snapshot.eligible_source_count == 0 and view.coverage["obsolete"] == 1
    with pytest.raises(MemoryUnavailable):
        service.contribute(CHAT, ref)


def test_daily_refresh_resumes_persisted_pages_and_reports_inventory_limits(env):
    activate(env)
    service = TrendService(env.repo)
    for mid in ("8", "9", "10"):
        env.repo.register_source(event(env, mid))
    first = service.refresh(CHAT, max_pages=1, page_size=1)
    assert first["pending"] and first["updated"] == 1
    saved = env.repo._read(CHAT, REFRESH_KEY)
    assert saved["cursor"]
    second = service.refresh(CHAT, max_pages=10, page_size=1)
    assert not second["pending"]
    view = service.read(CHAT)
    assert view.coverage["inventory_verified"] and not view.coverage["refresh_in_progress"]
    assert view.coverage["last_full_refresh_completed_at"] == env.clock.now
    assert view.snapshot.eligible_source_count == 3


def test_read_cutoff_resumes_exact_next_item_without_claiming_full_group(env):
    activate(env)
    service = TrendService(env.repo)
    for mid in ("8", "9", "10"):
        ref = env.repo.register_source(event(env, mid))
        service.contribute(CHAT, ref)
    first = service.read(CHAT, page_size=3, max_sources=1)
    assert first.coverage["truncated"] and not first.coverage["contribution_scan_complete"]
    second = service.read(CHAT, cursor=first.coverage["cursor"])
    assert not second.coverage["truncated"]
    assert len(set(first.source_refs + second.source_refs)) == 3
    assert first.source_refs[0] not in second.source_refs


def test_empty_filtered_pages_continue_and_old_dictionary_requires_refresh(env, stored):
    service, _, _, row = stored
    env.table.put_item(Item={**row, "dictionary_version": "old-dictionary"})
    view = service.read(CHAT, page_size=1)
    assert view.coverage["obsolete"] == 1 and not view.snapshot.topics
    service.refresh(CHAT)
    assert service.read(CHAT).snapshot.topics[0].topic == "python"


def test_storage_failure_propagates_and_refresh_cursor_does_not_skip_page(env, stored, monkeypatch):
    service, _, _, _ = stored
    before = env.repo._read(CHAT, REFRESH_KEY)
    failure = ClientError({"Error": {"Code": "ProvisionedThroughputExceededException"}}, "GetItem")
    monkeypatch.setattr(env.repo, "source_snapshot", lambda *args, **kwargs: (_ for _ in ()).throw(failure))
    with pytest.raises(ClientError):
        service.refresh(CHAT)
    assert env.repo._read(CHAT, REFRESH_KEY) == before
    with pytest.raises(ClientError):
        service.read(CHAT)


def test_contribution_transaction_rechecks_edit_after_source_read(env, stored, monkeypatch):
    service, source, ref, row = stored
    original = env.repo._transaction
    fired = False

    def race(operations):
        nonlocal fired
        if not fired and any(
            op.get("Put", {}).get("Item", {}).get("kind") == "TREND_CONTRIBUTION" for op in operations
        ):
            fired = True
            env.clock.now += 1
            env.repo.observe(replace(source, text="I use AWS.", edited_at=env.clock.now))
        return original(operations)

    monkeypatch.setattr(env.repo, "_transaction", race)
    with pytest.raises(MemoryConflict):
        service.contribute(CHAT, ref)
    assert env.repo._read(CHAT, "TREND#00000000000000000008") == row
    assert service.read(CHAT).snapshot.eligible_source_count == 0


def test_atomic_validation_catches_edit_after_final_source_read(env, stored, monkeypatch):
    service, source, _, _ = stored
    view = service.read(CHAT)
    original = env.repo._transaction
    fired = False

    def race(operations):
        nonlocal fired
        if not fired and all("ConditionCheck" in op for op in operations):
            fired = True
            env.clock.now += 1
            env.repo.observe(replace(source, text="I use AWS.", edited_at=env.clock.now))
        return original(operations)

    monkeypatch.setattr(env.repo, "_transaction", race)
    with pytest.raises(MemoryConflict):
        service.validate_snapshot(view)


def test_corrupt_derived_identity_or_topic_is_filtered_by_canonical_source(env, stored):
    service, _, _, row = stored
    for altered in ({"actor_user_id": "999"}, {"topics": ["imaginary_relationship"]}, {"expires_at": 0}):
        env.table.put_item(Item={**row, **altered})
        assert not service.read(CHAT).snapshot.topics


def test_cross_chat_cursor_stopped_group_and_oversized_bounds_are_rejected(env, stored):
    service, _, _, _ = stored
    with pytest.raises(MemoryInputError):
        service.read(CHAT, cursor={"pk": "CHAT#-999", "sk": "TREND#00000000000000000008"})
    with pytest.raises(MemoryInputError):
        service.read(CHAT, max_sources=21)
    with pytest.raises(MemoryUnavailable):
        service.read(-100456)


def test_bounded_sample_prefers_recent_numeric_message_ids_across_digit_lengths(env):
    activate(env)
    service = TrendService(env.repo)
    for mid in ("9", "10", "100"):
        ref = env.repo.register_source(event(env, mid))
        service.contribute(CHAT, ref)
    view = service.read(CHAT, max_sources=1)
    assert view.source_refs[0].source_id == "100" and view.coverage["truncated"]


def test_expiry_during_multi_source_validation_is_rechecked_with_fresh_clock(env, stored, monkeypatch):
    service, _, _, _ = stored
    view = service.read(CHAT)
    original = service._snapshot

    def expire_after_read(*args, **kwargs):
        result = original(*args, **kwargs)
        env.clock.now += WINDOW_SECONDS
        return result

    monkeypatch.setattr(service, "_snapshot", expire_after_read)
    with pytest.raises(MemoryUnavailable, match="expired during"):
        service.validate_snapshot(view)


def test_maximum_source_snapshot_uses_one_bounded_native_transaction(env, monkeypatch):
    activate(env)
    service = TrendService(env.repo)
    for number in range(1, 21):
        ref = env.repo.register_source(event(env, str(number), user=str(number + 1000)))
        service.contribute(CHAT, ref)
    original = env.repo._transaction
    seen = []

    def record(operations):
        if all("ConditionCheck" in op for op in operations):
            seen.append(len(operations))
        return original(operations)

    monkeypatch.setattr(env.repo, "_transaction", record)
    view = service.read(CHAT)
    assert len(view.source_refs) == 20 and seen == [81]
