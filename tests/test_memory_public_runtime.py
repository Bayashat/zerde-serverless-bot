"""Authenticated Telegram text/command adapters against real V2 transaction owners."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from services.memory_v2.public_answers import MemoryPublicAnswers
from services.memory_v2.public_commands import execute
from services.memory_v2.telegram_ingestion import TelegramMemoryAdmission

from tests import test_memory_v2_contract as contract
from tests.test_memory_v2_contract import CHAT, USER, activate, commit, event

env = contract.env


class API:
    def __init__(self, *, member=True, admin=False):
        self.is_member, self.admin = member, admin
        self.sent, self.authorizations = [], []

    async def authorize(self, chat, user, *, require_admin=False):
        self.authorizations.append((chat, user, require_admin))
        return self.is_member and (not require_admin or self.admin)

    async def member(self, chat, user):
        return {"user": {"id": int(user), "username": f"user_{user}"}, "status": "member"}

    async def send(self, chat, value, **kwargs):
        self.sent.append(value)
        return 70 + len(self.sent)


class Selector:
    def __init__(self, validate):
        self.validate = validate

    async def select(self, question, facts, *args, **kwargs):
        await self.validate()
        return ("facts", (0,)) if facts else ("general", ())


def message(env, text="What do I use?", **kwargs):
    return {
        "message_id": 90,
        "date": env.clock.now,
        "text": text,
        "chat": {"id": CHAT, "type": "supergroup"},
        "from": {"id": int(USER), "username": "user_42"},
        **kwargs,
    }


def ask(env, api, msg, **kwargs):
    service = MemoryPublicAnswers(env.repo, api, selector_factory=Selector, bot_username="zerde_bot")
    return asyncio.run(service.try_answer(msg, question=msg["text"], lang="en", **kwargs))


def ctx(env, text, **kwargs):
    msg = message(env, text, **kwargs)
    return SimpleNamespace(
        text=text,
        lang_code="en",
        chat_id=CHAT,
        user_id=USER,
        message_id=msg["message_id"],
        message=msg,
        _update={"update_id": 999, "message": msg},
        reply_to_message=msg.get("reply_to_message"),
    )


def test_public_answer_reads_current_facts_then_duplicate_does_not_plain_fallback(env):
    activate(env)
    commit(env, env.repo.register_source(event(env)))
    api = API()
    assert ask(env, api, message(env)) is True
    assert "Python" in api.sent[0]
    assert ask(env, api, message(env)) is True
    assert len(api.sent) == 1


def test_no_facts_general_question_falls_back_without_creating_subject(env):
    activate(env)
    api = API()
    assert ask(env, api, message(env, "Explain SQL")) is False
    assert not api.sent and not env.repo.get_subject(CHAT, USER)


def test_absent_profile_is_deterministic_unknown(env):
    activate(env)
    api = API()
    assert ask(env, api, message(env), about=True) is True
    assert len(api.sent) == 1 and not env.repo.get_subject(CHAT, USER)


def test_unresolved_username_never_selects_requester_profile(env):
    activate(env)
    commit(env, env.repo.register_source(event(env)))
    msg = message(env, "What does @no_such_user use?", entities=[{"type": "mention", "offset": 10, "length": 13}])
    api = API()
    assert ask(env, api, msg) is True
    assert "Python" not in api.sent[0]


def test_old_or_edited_ask_never_reads_or_sends_v2(env):
    activate(env)
    api = API()
    assert ask(env, api, message(env, date=env.clock.now - 1)) is True
    assert ask(env, api, message(env, edit_date=env.clock.now + 1)) is True
    assert not api.sent and not api.authorizations


def test_raw_quoted_bot_answer_does_not_supply_facts(env):
    activate(env)
    api = API()
    msg = message(
        env,
        "Where do I live?",
        reply_to_message={"message_id": 10, "text": "You live in SECRET_CITY", "from": {"id": 1, "is_bot": True}},
    )
    assert ask(env, api, msg) is False
    assert not api.sent


def test_command_confirmation_uses_same_source_kind_as_webhook_observation(env):
    activate(env)
    context = ctx(env, "/memory group confirm rule Be kind")
    admission = TelegramMemoryAdmission(SimpleNamespace(observe=env.repo.observe), context._update)
    assert admission.event.source_kind == "confirmation" and not admission.eligible
    result = asyncio.run(execute(context, env.repo, API(admin=True)))
    assert "CONFIRMED" in result
    assert env.repo.get_profile(CHAT, "GROUP")[0]["value"] == "Be kind"
    edited = message(env, "/memory group confirm rule Be cruel", edit_date=env.clock.now + 1)
    env.clock.now += 1
    TelegramMemoryAdmission(SimpleNamespace(observe=env.repo.observe), {"edited_message": edited})
    assert not env.repo.get_profile(CHAT, "GROUP")


def test_group_command_no_owner_bypass(env):
    activate(env)
    assert "requires" in asyncio.run(execute(ctx(env, "/memory group confirm rule Be kind"), env.repo, API()))
    assert not env.repo.get_subject(CHAT, "GROUP")


def test_public_forget_optout_and_optin_share_control_owner(env):
    activate(env)
    commit(env, env.repo.register_source(event(env)))
    assert "DONE" in asyncio.run(execute(ctx(env, "/memory optout"), env.repo, API()))
    assert env.repo.get_subject(CHAT, USER)["optout"] is True
    from services.memory_v2.models import MemoryUnavailable

    with pytest.raises(MemoryUnavailable):
        env.repo.get_profile(CHAT, USER)
    env.clock.now += 2
    assert "OPTED_IN" in asyncio.run(execute(ctx(env, "/memory optin", message_id=91), env.repo, API()))
    assert env.repo.get_subject(CHAT, USER)["optout"] is False


def test_pending_derived_owner_is_not_reported_completed(env, monkeypatch):
    from services.memory_v2 import public_commands

    activate(env)
    lifecycle = Mock()
    lifecycle.begin.return_value = {"kind": "PURGE", "state": "WAITING", "sk": "PURGE#USER#42"}
    lifecycle.advance.return_value = {"kind": "PURGE", "state": "DERIVED"}
    monkeypatch.setattr(public_commands, "MemoryLifecycle", lambda repo: lifecycle)
    result = asyncio.run(execute(ctx(env, "/memory forget me"), env.repo, API()))
    assert "still pending" in result and "completed-deletion acknowledgement" in result


def test_initial_epoch_cannot_be_enabled_by_chat_command(env):
    from services.memory_v2.models import MemoryConflict

    with pytest.raises(MemoryConflict):
        asyncio.run(execute(ctx(env, "/memory on"), env.repo, API(admin=True)))
    assert env.repo.get_control(CHAT)["state"] == "STOPPED"
