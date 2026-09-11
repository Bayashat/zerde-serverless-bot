"""Deterministic group sample and source-bound public presentation."""

import asyncio
from dataclasses import replace
from unittest.mock import Mock

import pytest
from services.memory_v2.answers import MemoryAnswerService
from services.memory_v2.models import MemoryUnavailable
from services.memory_v2.trend_runtime import maintain
from services.memory_v2.trend_service import TrendService

from tests import test_memory_v2_contract as contract
from tests.test_memory_public_runtime import API, Selector, ask, message
from tests.test_memory_v2_contract import CHAT, USER, activate, event

env = contract.env


def test_group_profile_presents_bounded_topics_without_model(env):
    activate(env)
    ref = env.repo.register_source(event(env, text="Let's discuss Python and AWS."))
    TrendService(env.repo).contribute(CHAT, ref)
    api = API()
    assert ask(env, api, message(env), about=True, group=True)
    assert "python: 1 messages" in api.sent[0]
    assert "not all group messages" in api.sent[0]
    assert "https://t.me/c/123/8" in api.sent[0]
    row = list(env.repo._list(CHAT, "ANSWER_REQUEST#"))[0]
    assert row["source_refs"] == [ref.as_dict()] and row["evidence_authors"] == [USER]
    assert not row["fact_refs"] and not env.repo.get_subject(CHAT, "GROUP")


def test_source_edit_after_trend_binding_prevents_public_send(env, monkeypatch):
    activate(env)
    source = event(env)
    ref = env.repo.register_source(source)
    TrendService(env.repo).contribute(CHAT, ref)
    api = API()
    service = MemoryAnswerService(env.repo, authorize=api.authorize, sender=api.send, selector_factory=Selector)
    actual = service.leases.bind

    def edit(*args, **kwargs):
        lease = actual(*args, **kwargs)
        env.clock.now += 1
        env.repo.observe(replace(source, edited_at=env.clock.now, text="different"))
        return lease

    monkeypatch.setattr(service.leases, "bind", edit)
    with pytest.raises(MemoryUnavailable):
        asyncio.run(
            service.answer(
                CHAT,
                USER,
                [],
                request_id="trend-edit",
                question="Group",
                lang="en",
                reply_to_message_id=90,
                about=True,
                include_trends=True,
            )
        )
    assert not api.sent


def test_recovery_contributes_even_when_no_extraction_has_run(env, monkeypatch):
    from services.memory_v2 import trend_runtime

    activate(env)
    env.repo.register_source(event(env))
    budget = Mock()
    monkeypatch.setattr(trend_runtime, "get_memory_budget", lambda: budget)
    result = maintain(env.repo, chat_ids=[CHAT])
    assert result["updated"] == 1 and budget.check_aws_available.call_count == 1
    assert not env.repo.get_profile(CHAT, USER)
    assert TrendService(env.repo).read(CHAT).snapshot.topics[0].topic == "python"


def test_aws_pause_keeps_trend_recovery_pending_without_writes(env, monkeypatch):
    from services.memory_budget import MemoryBudgetPaused
    from services.memory_v2 import trend_runtime

    activate(env)
    env.repo.register_source(event(env))
    budget = Mock()
    budget.check_aws_available.side_effect = MemoryBudgetPaused()
    monkeypatch.setattr(trend_runtime, "get_memory_budget", lambda: budget)
    assert maintain(env.repo, chat_ids=[CHAT])["paused"]
    assert not list(env.repo._list(CHAT, "TREND#"))
