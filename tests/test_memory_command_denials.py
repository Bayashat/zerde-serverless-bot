"""Definite ownership denial, redelivery and uncertain writes through public commands."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError
from services.memory_v2 import public_commands
from services.memory_v2.command_receipts import CommandReceipt
from services.memory_v2.lifecycle import MemoryLifecycle
from services.memory_v2.models import MemoryUnavailable
from services.memory_v2.public_answers import MemoryPublicRetryRequiredError
from services.memory_v2.repository import MemoryRepository

from tests import test_memory_v2_contract as contract
from tests.test_memory_control_replay import context, database_fault, run, seed
from tests.test_memory_public_runtime import API
from tests.test_memory_v2_contract import CHAT, USER

env = contract.env
OTHER = "43"


def request(env, fact, action="wrong", lang="en", *, other=True):
    ref = fact["fact_id"] + "@" + str(fact["fact_version"])
    if action == "forget_this":
        command = context(env, "/memory forget this", reply_to_message={"message_id": 8})
    else:
        command = context(env, "/memory " + action + " " + ref + (" Rust" if action == "correct" else ""))
    command.lang_code = lang
    if other:
        command.user_id = OTHER
        command.message["from"] = {"id": int(OTHER), "username": "other"}
    return command


def receipt(env):
    return env.repo._read(CHAT, "CONTROL_COMMAND#" + str(90).zfill(20))


def protected(env):
    return {
        row["sk"]: row
        for row in env.table.scan()["Items"]
        if row["sk"] == "CONTROL"
        or row["sk"] == "SUBJECT#USER#" + USER
        or row["sk"] == "OBSERVATION#8"
        or row["sk"].startswith(("FACT#", "HEAD#", "RAW#", "WORK#", "HISTORY#", "PURGE#"))
    }


@pytest.mark.parametrize("action", ["wrong", "correct", "forget_this"])
@pytest.mark.parametrize(
    "lang,expected",
    [
        ("en", "You can only change your own personal memory or forget messages you sent."),
        ("ru", "Можно изменять только свою личную память или удалять из памяти свои сообщения."),
        ("kk", "Тек өзіңіз туралы жеке жадты өзгертуге немесе өз хабарламаларыңызды жадтан өшіруге болады."),
        ("zh", "你只能修改自己的个人记忆，或从记忆中遗忘自己发送的消息。"),
    ],
)
def test_foreign_ownership_is_terminal_localized_and_replayable(env, action, lang, expected, monkeypatch):
    fact = seed(env)
    command = request(env, fact, action, lang)
    before = protected(env)
    assert run(env, command, admin=False) == expected
    assert receipt(env)["state"] == "DENIED"
    assert env.repo._read(CHAT, "CONTROL_COMMAND#LOCK")["state"] == "RELEASED"
    assert protected(env) == before
    assert not {"text", "value", "excerpt", "reason"} & receipt(env).keys()
    # A saved rejection never dispatches the domain operation again.
    monkeypatch.setattr(public_commands, "MemoryCommandService", Mock(side_effect=AssertionError("redispatched")))
    assert run(env, command, admin=False) == expected
    assert protected(env) == before


@pytest.mark.parametrize("committed", [False, True])
def test_denial_write_failure_is_retryable_and_lost_ack_recovers(env, committed, monkeypatch):
    fact = seed(env)
    command = request(env, fact)
    before = protected(env)
    original = env.repo._transaction
    fired = False

    def fail(operations):
        nonlocal fired
        if not fired and any(op.get("Put", {}).get("Item", {}).get("state") == "DENIED" for op in operations):
            fired = True
            if committed:
                original(operations)
            raise database_fault()
        return original(operations)

    monkeypatch.setattr(env.repo, "_transaction", fail)
    with pytest.raises(ClientError):
        run(env, command, admin=False)
    assert receipt(env)["state"] == ("DENIED" if committed else "PENDING")
    assert protected(env) == before
    assert "own personal memory" in run(env, command, admin=False)
    assert receipt(env)["state"] == "DENIED" and protected(env) == before


@pytest.mark.parametrize("action", ["wrong", "correct"])
@pytest.mark.parametrize("committed", [False, True])
def test_legal_effect_unknown_is_never_relabelled_denied(env, action, committed, monkeypatch):
    fact = seed(env)
    command = request(env, fact, action, other=False)
    original = env.repo._transaction
    fired = False

    def fail(operations):
        nonlocal fired
        if not fired and any(op.get("Put", {}).get("Item", {}).get("sk", "").startswith("FACT#") for op in operations):
            fired = True
            if committed:
                original(operations)
            raise database_fault()
        return original(operations)

    monkeypatch.setattr(env.repo, "_transaction", fail)
    with pytest.raises(ClientError):
        run(env, command)
    assert receipt(env)["state"] == "PENDING"
    assert ("REJECTED" if action == "wrong" else "CORRECTED") in run(env, command)
    assert receipt(env)["state"] == "APPLIED"
    if action == "wrong":
        assert env.repo._read(CHAT, fact["fact_id"])["wrong_feedback_count"] == 1
    else:
        assert [r["value"] for r in env.repo.get_profile(CHAT, USER)] == ["Rust"]


def test_missing_source_stays_unavailable_not_a_permanent_ownership_denial(env):
    fact = seed(env)
    command = request(env, fact, "forget_this")
    command.reply_to_message["message_id"] = 999
    with pytest.raises(MemoryUnavailable):
        run(env, command, admin=False)
    assert receipt(env)["state"] == "PENDING"


def test_expired_live_authorization_stays_unavailable(env, monkeypatch):
    fact = seed(env)
    command = request(env, fact)
    monkeypatch.setattr(public_commands, "time", SimpleNamespace(monotonic=Mock(side_effect=[10, 31])))
    with pytest.raises(MemoryUnavailable):
        run(env, command, admin=False)
    assert receipt(env)["state"] == "PENDING"


def test_foreign_pending_source_purge_cannot_be_recovered_or_advanced(env):
    fact = seed(env)
    original = MemoryLifecycle(env.repo).begin(CHAT, scope="source", target="8")
    command = request(env, fact, "forget_this")
    with pytest.raises(MemoryUnavailable):
        run(env, command, admin=False)
    assert receipt(env)["state"] == "PENDING"
    assert env.repo._read(CHAT, original["sk"]) == original


def test_denial_does_not_bypass_command_observation_fence(env, monkeypatch):
    fact = seed(env)
    command = request(env, fact)
    original = CommandReceipt.deny

    def changed(self):
        env.clock.now += 1
        env.repo.observe(replace(self.event, edited_at=env.clock.now))
        return original(self)

    monkeypatch.setattr(CommandReceipt, "deny", changed)
    with pytest.raises(MemoryUnavailable):
        run(env, command, admin=False)
    assert receipt(env)["state"] == "PENDING"
    assert env.repo._read(CHAT, fact["fact_id"])["status"] == "ACTIVE"


def test_public_adapter_retries_database_failure_without_a_denial_ack(env, monkeypatch):
    from services.memory_v2 import runtime, telegram_api

    fact = seed(env)
    command = request(env, fact)
    api = API()
    monkeypatch.setattr(runtime, "get_memory_v2_repo", lambda: env.repo)
    monkeypatch.setattr(telegram_api, "MemoryTelegramAPI", lambda *a, **kw: api)
    monkeypatch.setattr(CommandReceipt, "deny", Mock(side_effect=database_fault()))
    with pytest.raises(MemoryPublicRetryRequiredError):
        public_commands.handle_memory_v2(command)
    assert not api.sent and receipt(env)["state"] == "PENDING"


@pytest.mark.parametrize("fault", ["missing", "database"])
def test_unavailable_target_is_not_permanently_denied(env, monkeypatch, fault):
    fact = seed(env)
    command = request(env, fact)
    original = MemoryRepository._read

    def read(self, chat, key):
        if key == fact["fact_id"]:
            if fault == "database":
                raise database_fault()
            return {}
        return original(self, chat, key)

    monkeypatch.setattr(MemoryRepository, "_read", read)
    with pytest.raises(ClientError if fault == "database" else MemoryUnavailable):
        run(env, command, admin=False)
    assert receipt(env)["state"] == "PENDING"


def test_denial_requires_current_command_lease_and_cannot_replace_success(env):
    from services.memory_v2.command_receipts import COMMAND_LEASE_SECONDS, CommandRetryRequired

    fact = seed(env)
    command = request(env, fact)
    first = CommandReceipt(env.repo, command, "wrong", fact_ref={"fact_id": fact["fact_id"], "fact_version": 1})
    first.acquire()
    env.clock.now += COMMAND_LEASE_SECONDS + 1
    second = CommandReceipt(env.repo, command, "wrong", fact_ref=first.fact_ref)
    second.acquire()
    with pytest.raises(CommandRetryRequired):
        first.deny()
    first.release()
    assert env.repo._read(CHAT, "CONTROL_COMMAND#LOCK")["token"] == second.lock["token"]
    second.complete({"state": "REJECTED"})
    with pytest.raises(MemoryUnavailable):
        second.deny()
    assert receipt(env)["state"] == "APPLIED"
    second.release()


@pytest.mark.parametrize("change", ["actor", "body"])
def test_changed_delivery_cannot_reuse_a_saved_denial(env, change):
    fact = seed(env)
    command = request(env, fact)
    assert "own personal memory" in run(env, command, admin=False)
    if change == "actor":
        command.user_id = USER
        command.message["from"] = {"id": int(USER)}
    else:
        command.text += " changed"
        command.message["text"] = command.text
        # Keep a valid command shape so identity validation, not parsing, rejects it.
        command.text = command.text.replace("wrong", "correct")
        command.message["text"] = command.text
    with pytest.raises(MemoryUnavailable):
        asyncio.run(public_commands.execute(command, env.repo, API(admin=True)))
    assert receipt(env)["state"] == "DENIED"
    assert env.repo._read(CHAT, fact["fact_id"])["status"] == "ACTIVE"
