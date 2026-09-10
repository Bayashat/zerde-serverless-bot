from dataclasses import replace

import pytest
from services.memory_v2.explicit_request_gate import capture, validate
from services.memory_v2.lifecycle import MemoryLifecycle
from services.memory_v2.models import MemoryUnavailable

from tests import test_memory_v2_contract as contract
from tests.test_memory_v2_contract import CHAT, USER, activate, event

env = contract.env


def test_old_queued_explicit_request_stops_when_epoch_activates(env):
    gate = capture(env.repo, CHAT, USER, "90", requested_at=env.clock.now)
    assert validate(env.repo, CHAT, USER, "90", gate)
    activate(env)
    with pytest.raises(MemoryUnavailable):
        validate(env.repo, CHAT, USER, "90", gate)


def test_edit_invalidates_request_source_before_worker(env):
    activate(env)
    source = event(env, message_id="90", text="/ask Describe this")
    env.repo.observe(source)
    gate = capture(env.repo, CHAT, USER, "90", requested_at=env.clock.now)
    env.clock.now += 1
    env.repo.observe(replace(source, edited_at=env.clock.now, text="/ask Cancel"))
    with pytest.raises(MemoryUnavailable):
        validate(env.repo, CHAT, USER, "90", gate)


@pytest.mark.parametrize("scope", ["subject", "source", "group"])
def test_pending_explicit_request_cannot_survive_deletion(env, scope):
    activate(env)
    env.repo.observe(event(env, message_id="90"))
    gate = capture(env.repo, CHAT, USER, "90", requested_at=env.clock.now)
    lifecycle = MemoryLifecycle(env.repo)
    job = lifecycle.begin(CHAT, scope=scope, target="90" if scope == "source" else USER)
    assert lifecycle.advance(CHAT, job["sk"])["state"] == "DONE"
    with pytest.raises(MemoryUnavailable):
        validate(env.repo, CHAT, USER, "90", gate)


def test_optout_allows_future_explicit_input_without_learning(env):
    activate(env)
    lifecycle = MemoryLifecycle(env.repo)
    job = lifecycle.begin(CHAT, scope="subject", target=USER, optout=True)
    lifecycle.advance(CHAT, job["sk"])
    env.clock.now += 1
    gate = capture(env.repo, CHAT, USER, "90", requested_at=env.clock.now)
    assert validate(env.repo, CHAT, USER, "90", gate)
    assert not env.repo.get_observation(CHAT, "90")


def test_missing_protocol_never_uses_old_preassembled_context(env):
    with pytest.raises(MemoryUnavailable):
        validate(env.repo, CHAT, USER, "90", None)
