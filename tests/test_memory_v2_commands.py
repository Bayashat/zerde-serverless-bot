"""Authenticated command ownership and correction feedback in real DynamoDB semantics."""

from dataclasses import replace

import pytest
from services.memory_v2.commands import MemoryCommandService
from services.memory_v2.leases import AnswerLeaseService
from services.memory_v2.lifecycle import MemoryLifecycle
from services.memory_v2.models import MemoryConflict, MemoryInputError, MemoryUnavailable

from tests import test_memory_v2_contract as contract
from tests.test_memory_v2_contract import CHAT, USER, activate, commit, event

env = contract.env


@pytest.fixture
def prepared(env):
    activate(env)
    commit(env, env.repo.register_source(event(env)))
    facts = env.repo.get_profile(CHAT, USER)
    ref = {"fact_id": facts[0]["fact_id"], "fact_version": int(facts[0]["revision"])}

    def auth(chat, actor, require_admin=False):
        return actor == USER

    service = MemoryCommandService(env.repo, MemoryLifecycle(env.repo), authorize=auth)
    return service, ref


def command(env, value="Rust", **kwargs):
    return event(env, "99", "/memory correct selected@1 " + value, source_kind="confirmation", **kwargs)


def test_wrong_excludes_exact_version_preserves_order_and_blocks_bound_answer(env, prepared):
    service, ref = prepared
    leases = AnswerLeaseService(env.repo)
    lease = leases.acquire(CHAT, [USER], request_id="read-before-wrong")
    bound = leases.bind(lease, [ref])
    old = env.repo._read(CHAT, ref["fact_id"])
    result = service.wrong(CHAT, USER, ref)
    current = env.repo._read(CHAT, ref["fact_id"])
    assert result["state"] == "REJECTED" and current["wrong_feedback_count"] == 1
    assert current["source_order"] == old["source_order"]
    assert env.repo.get_profile(CHAT, USER) == []
    with pytest.raises(MemoryUnavailable):
        leases.validate(bound, [ref])
    assert service.wrong(CHAT, USER, ref) == result
    assert env.repo._read(CHAT, ref["fact_id"])["wrong_feedback_count"] == 1


def test_self_correction_replaces_multivalue_and_keeps_command_evidence(env, prepared):
    service, ref = prepared
    env.clock.now += 1
    result = service.correct(CHAT, USER, ref, source_event=command(env), value="Rust")
    assert result["state"] == "CORRECTED"
    facts = env.repo.get_profile(CHAT, USER)
    assert [row["value"] for row in facts] == ["Rust"]
    assert facts[0]["evidence"]["excerpt"] == "Rust"
    assert facts[0]["evidence"]["source_ref"]["source_id"] == "99"
    assert env.repo._read(CHAT, "WORK#99#1")["state"] == "DONE"
    assert service.correct(CHAT, USER, ref, source_event=command(env), value="Rust")["duplicate"] is True


def test_correction_keeps_wrong_feedback_in_history(env, prepared):
    service, ref = prepared
    rejected = service.wrong(CHAT, USER, ref)["fact_ref"]
    env.clock.now += 1
    service.correct(CHAT, USER, rejected, source_event=command(env), value="Rust")
    history = list(env.repo._list(CHAT, "HISTORY#"))
    assert any(row.get("feedback_status") == "WRONG" and row.get("rejected_fact_version") == 1 for row in history)
    assert env.repo.get_profile(CHAT, USER)[0]["value"] == "Rust"


def test_stale_fact_version_cannot_correct_newer_state(env, prepared):
    service, ref = prepared
    service.wrong(CHAT, USER, ref)
    env.clock.now += 1
    with pytest.raises(MemoryConflict):
        service.correct(CHAT, USER, ref, source_event=command(env), value="Rust")
    assert env.repo.get_profile(CHAT, USER) == []


@pytest.mark.parametrize(
    "alter", [{"edited_at": 2000000001}, {"actor_user_id": "43"}, {"chat_id": -100456}, {"is_forwarded": True}]
)
def test_correction_requires_new_original_authenticated_command(env, prepared, alter):
    service, ref = prepared
    env.clock.now += 1
    source = replace(command(env), **alter)
    with pytest.raises((MemoryInputError, MemoryUnavailable)):
        service.correct(CHAT, USER, ref, source_event=source, value="Rust")
    assert env.repo.get_profile(CHAT, USER)[0]["value"] == "Python"


def test_group_confirmation_requires_current_admin_and_has_no_model_work(env, prepared):
    service, _ = prepared
    env.clock.now += 1
    source = event(env, "100", "/memory group confirm rule Be kind.", source_kind="confirmation")
    result = service.confirm_group(CHAT, USER, source_event=source, field="rule", value="Be kind.")
    assert result["state"] == "CONFIRMED"
    facts = env.repo.get_profile(CHAT, "GROUP")
    assert facts[0]["value"] == "Be kind." and facts[0]["confirmed_by"] == USER
    assert env.repo._read(CHAT, "WORK#100#1")["state"] == "DONE"
    assert "work_queue" not in env.repo._read(CHAT, "WORK#100#1")
    service.authorize = lambda chat, actor, require_admin=False: not require_admin
    with pytest.raises(MemoryUnavailable):
        service.confirm_group(
            CHAT, USER, source_event=replace(source, message_id="101"), field="rule", value="Be kind."
        )
    group_ref = {"fact_id": facts[0]["fact_id"], "fact_version": int(facts[0]["revision"])}
    with pytest.raises(MemoryUnavailable):
        service.wrong(CHAT, USER, group_ref)


def test_members_cannot_modify_other_person_or_spoof_private_scope(env, prepared):
    service, ref = prepared
    service.authorize = lambda chat, actor, require_admin=False: True
    with pytest.raises(MemoryUnavailable):
        service.wrong(CHAT, "43", ref)
    with pytest.raises(MemoryUnavailable):
        service.forget_source(CHAT, "43", "8")
    with pytest.raises(MemoryUnavailable):
        service.about_subject(42, USER)


def test_live_authorization_failure_propagates_without_mutation(env, prepared):
    service, _ = prepared

    def failed(*args, **kwargs):
        raise RuntimeError("membership lookup unavailable")

    service.authorize = failed
    with pytest.raises(RuntimeError):
        service.forget_me(CHAT, USER)
    assert env.repo.get_subject(CHAT, USER)["state"] == "ACTIVE"


def test_group_correction_replaces_selected_rule_without_retaining_old_rule(env, prepared):
    service, _ = prepared
    first = event(env, "100", "/memory group confirm rule Be kind.", source_kind="confirmation")
    service.confirm_group(CHAT, USER, source_event=first, field="rule", value="Be kind.")
    old = env.repo.get_profile(CHAT, "GROUP")[0]
    ref = {"fact_id": old["fact_id"], "fact_version": int(old["revision"])}
    env.clock.now += 1
    source = event(env, "101", "/memory correct selected@1 Be respectful.", source_kind="confirmation")
    service.correct(CHAT, USER, ref, source_event=source, value="Be respectful.")
    assert [fact["value"] for fact in env.repo.get_profile(CHAT, "GROUP")] == ["Be respectful."]
