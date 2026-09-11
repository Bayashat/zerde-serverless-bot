"""Actual command effects, interruption recovery and edit fences against Moto."""

import asyncio
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError
from services.memory_v2.command_receipts import COMMAND_LEASE_SECONDS, CommandReceipt, CommandRetryRequired
from services.memory_v2.ingestion import MemoryIngestion
from services.memory_v2.lifecycle import MemoryLifecycle
from services.memory_v2.models import MemoryConflict, MemoryInputError, MemoryUnavailable
from services.memory_v2.public_commands import execute
from services.memory_v2.safety import require_public_content
from services.memory_v2.telegram_ingestion import TelegramMemoryAdmission, source_event

from tests import test_memory_v2_contract as contract
from tests.test_memory_public_runtime import API, ctx
from tests.test_memory_v2_contract import CHAT, USER, activate, commit, event
from tests.test_memory_v2_lifecycle import finish

env = contract.env


def context(env, text, *, message_id=90, **kwargs):
    result = ctx(env, text, **kwargs)
    result.message_id = message_id
    result.message["message_id"] = message_id
    return result


def admission(env, update):
    return TelegramMemoryAdmission(MemoryIngestion(env.repo, None, SimpleNamespace(send=lambda *args: None)), update)


def run(env, context, *, admin=True):
    admission(env, context._update)
    return asyncio.run(execute(context, env.repo, API(admin=admin)))


def database_fault():
    return ClientError({"Error": {"Code": "InternalServerError"}}, "TransactWriteItems")


def seed(env):
    activate(env)
    commit(env, env.repo.register_source(event(env)))
    return env.repo.get_profile(CHAT, USER)[0]


def test_original_forget_redelivery_never_deletes_relearned_generation(env):
    seed(env)
    command = context(env, "/memory forget me")
    assert "DONE" in run(env, command)
    env.clock.now += 2
    commit(env, env.repo.register_source(event(env, "9")))
    before = env.repo.get_profile(CHAT, USER)
    assert "DONE" in run(env, command)
    assert env.repo.get_profile(CHAT, USER) == before
    assert env.repo.get_subject(CHAT, USER)["generation"] == 1


def test_applied_old_on_does_not_override_new_off(env):
    activate(env)
    on = context(env, "/memory on")
    assert "LEARNING_ON" in run(env, on)
    env.clock.now += 1
    assert "LEARNING_OFF" in run(env, context(env, "/memory off", message_id=91))
    assert "LEARNING_ON" in run(env, on)  # Receipt reports that historical operation only.
    assert env.repo.get_control(CHAT)["learning_enabled"] is False


def test_fault_before_effect_recovers_same_command(env, monkeypatch):
    activate(env)
    command = context(env, "/memory off")
    original = env.repo._transaction
    fired = False

    def fail(operations):
        nonlocal fired
        if not fired and any(op.get("Put", {}).get("Item", {}).get("sk") == "CONTROL" for op in operations):
            fired = True
            raise database_fault()
        return original(operations)

    monkeypatch.setattr(env.repo, "_transaction", fail)
    with pytest.raises(ClientError):
        run(env, command)
    assert env.repo.get_control(CHAT)["learning_enabled"] is True
    receipt = env.repo._read(CHAT, "CONTROL_COMMAND#" + str(90).zfill(20))
    assert receipt["state"] == "PENDING"
    assert "LEARNING_OFF" in run(env, command)
    assert env.repo.get_control(CHAT)["learning_enabled"] is False


@pytest.mark.parametrize("first,newer", [("off", "on"), ("optout", "optin")])
def test_newer_control_intent_prevents_unapplied_old_command_late_override(env, monkeypatch, first, newer):
    seed(env)
    old = context(env, "/memory " + first)
    original = env.repo._transaction
    fired = False

    def fail(operations):
        nonlocal fired
        if not fired and any(op.get("Put", {}).get("Item", {}).get("sk") == "CONTROL" for op in operations):
            fired = True
            raise database_fault()
        return original(operations)

    monkeypatch.setattr(env.repo, "_transaction", fail)
    with pytest.raises(ClientError):
        run(env, old)
    env.clock.now += 1
    run(env, context(env, "/memory " + newer, message_id=91))
    with pytest.raises(MemoryUnavailable):
        run(env, old)
    assert env.repo.get_control(CHAT)["learning_enabled"] is True
    assert env.repo.get_subject(CHAT, USER)["optout"] is False
    assert env.repo.get_profile(CHAT, USER)


def test_effect_committed_before_receipt_failure_is_not_repeated_after_recovery(env, monkeypatch):
    seed(env)
    command = context(env, "/memory forget me")
    original = CommandReceipt.complete
    fired = False

    def fail(self, result):
        nonlocal fired
        if not fired:
            fired = True
            raise database_fault()
        return original(self, result)

    monkeypatch.setattr(CommandReceipt, "complete", fail)
    with pytest.raises(ClientError):
        run(env, command)
    lifecycle = MemoryLifecycle(env.repo)
    finish(lifecycle, env.repo._read(CHAT, "PURGE#SUBJECT#" + USER))
    env.clock.now += 2
    commit(env, env.repo.register_source(event(env, "9")))
    assert "DONE" in run(env, command)
    assert env.repo.get_profile(CHAT, USER)
    assert env.repo.get_subject(CHAT, USER)["generation"] == 1


def test_purge_progress_failure_replays_only_original_job(env, monkeypatch):
    seed(env)
    command = context(env, "/memory forget me")
    original = MemoryLifecycle.advance
    fired = False

    def fail(self, *args, **kwargs):
        nonlocal fired
        if not fired:
            fired = True
            raise database_fault()
        return original(self, *args, **kwargs)

    monkeypatch.setattr(MemoryLifecycle, "advance", fail)
    with pytest.raises(ClientError):
        run(env, command)
    assert env.repo._read(CHAT, "CONTROL_COMMAND#" + str(90).zfill(20))["state"] == "APPLIED"
    assert "DONE" in run(env, command)
    assert env.repo.get_subject(CHAT, USER)["generation"] == 1


def test_active_command_owner_requires_retry_and_expired_owner_cannot_write(env):
    activate(env)
    command = context(env, "/memory off")
    admission(env, command._update)
    first = CommandReceipt(env.repo, command, "off")
    first.acquire()
    with pytest.raises(CommandRetryRequired):
        CommandReceipt(env.repo, command, "off").acquire()
    assert COMMAND_LEASE_SECONDS > 300
    env.clock.now += COMMAND_LEASE_SECONDS + 1
    second = CommandReceipt(env.repo, command, "off")
    second.acquire()
    with pytest.raises(CommandRetryRequired):
        first.fenced_repo.set_learning_enabled(CHAT, False, expected_revision=env.repo.get_control(CHAT)["revision"])
    first.release()
    assert env.repo._read(CHAT, "CONTROL_COMMAND#LOCK")["token"] == second.lock["token"]
    second.release()


def test_final_effect_transaction_checks_request_observation(env, monkeypatch):
    activate(env)
    command = context(env, "/memory off")
    original = env.repo._transaction
    fired = False

    def edit(operations):
        nonlocal fired
        if not fired and any(op.get("Put", {}).get("Item", {}).get("sk") == "CONTROL" for op in operations):
            fired = True
            env.clock.now += 1
            admission(env, {"edited_message": {**command.message, "text": "/memory on", "edit_date": env.clock.now}})
        return original(operations)

    monkeypatch.setattr(env.repo, "_transaction", edit)
    with pytest.raises(MemoryConflict):
        run(env, command)
    assert env.repo.get_control(CHAT)["learning_enabled"] is True


def test_plain_source_edited_into_confirmation_is_invalidated(env):
    seed(env)
    env.clock.now += 1
    edited = {
        "message_id": 8,
        "date": env.clock.now - 1,
        "edit_date": env.clock.now,
        "chat": {"id": CHAT, "type": "supergroup"},
        "from": {"id": int(USER)},
        "text": "/memory correct FACT#example@1 Rust",
    }
    result = admission(env, {"edited_message": edited})
    assert result.event.source_kind == "message" and not result.eligible
    assert env.repo.get_observation(CHAT, "8")["revision"] == 2
    assert not env.repo.get_profile(CHAT, USER)


def test_confirmation_edited_to_plain_text_only_invalidates_and_cannot_change_lane(env):
    activate(env)
    command = context(env, "/memory group confirm rule Be kind")
    assert "CONFIRMED" in run(env, command)
    env.clock.now += 1
    edited = {**command.message, "text": "I use Rust.", "edit_date": env.clock.now}
    result = admission(env, {"edited_message": edited})
    assert result.event.source_kind == "confirmation" and not result.eligible
    result.accept_safe()
    assert not env.repo.get_profile(CHAT, "GROUP")
    assert env.repo.get_source_head(CHAT, "90")["revision"] == 1
    assert env.repo.get_observation(CHAT, "90")["revision"] == 2


@pytest.mark.parametrize("action", ["wrong", "correct", "confirm_group"])
def test_fact_effect_recovered_after_receipt_write_failure(env, monkeypatch, action):
    fact = seed(env)
    ref = fact["fact_id"] + "@" + str(fact["fact_version"])
    text = (
        "/memory wrong " + ref
        if action == "wrong"
        else "/memory correct " + ref + " Rust" if action == "correct" else "/memory group confirm rule Be kind"
    )
    command = context(env, text)
    original = CommandReceipt.complete
    fired = False

    def fail(self, result):
        nonlocal fired
        if not fired:
            fired = True
            raise database_fault()
        return original(self, result)

    monkeypatch.setattr(CommandReceipt, "complete", fail)
    with pytest.raises(ClientError):
        run(env, command)
    before = env.table.scan()["Items"]
    assert any(word in run(env, command) for word in ("REJECTED", "CORRECTED", "CONFIRMED"))
    if action == "wrong":
        assert env.repo._read(CHAT, fact["fact_id"])["wrong_feedback_count"] == 1

    # Only the receipt/lock and an idempotent webhook observation may change.
    def relevant(rows):
        return sorted(str(row) for row in rows if row["sk"].startswith(("FACT#", "HISTORY#", "WORK#")))

    assert relevant(before) == relevant(env.table.scan()["Items"])


def test_command_receipts_survive_group_purge_but_contain_no_command_body(env):
    seed(env)
    command = context(env, "/memory forget group")
    assert "DONE" in run(env, command)
    rows = list(env.repo._list(CHAT, "CONTROL_COMMAND#"))
    assert rows and all(int(row["ttl"]) <= env.clock.now + 7 * 86400 for row in rows)
    assert all("/memory" not in str(row) and "Python" not in str(row) for row in rows)
    assert not list(env.repo._list(CHAT, "FACT#"))
    env.clock.now += 2
    activate(env)
    commit(env, env.repo.register_source(event(env, "9")))
    assert "DONE" in run(env, command)
    assert env.repo.get_profile(CHAT, USER)


@pytest.mark.parametrize("cutoff", ["time", "generation", "epoch"])
def test_absent_or_expired_receipt_never_authorizes_old_request(env, cutoff):
    seed(env)
    command = context(env, "/memory forget me")
    if cutoff == "time":
        env.clock.now += 86401
    elif cutoff == "generation":
        assert "DONE" in run(env, command)
        env.clock.now += 2
        commit(env, env.repo.register_source(event(env, "9")))
        for row in list(env.repo._list(CHAT, "CONTROL_COMMAND#")):
            env.table.delete_item(Key={"pk": row["pk"], "sk": row["sk"]})
    else:
        lifecycle = MemoryLifecycle(env.repo)
        finish(lifecycle, lifecycle.begin(CHAT, scope="group"))
        env.clock.now += 2
        activate(env)
        commit(env, env.repo.register_source(event(env, "9")))
    before = env.repo.get_profile(CHAT, USER)
    with pytest.raises(MemoryUnavailable):
        run(env, command)
    assert env.repo.get_profile(CHAT, USER) == before


def test_same_message_identity_cannot_be_reused_with_changed_command(env):
    activate(env)
    assert "LEARNING_OFF" in run(env, context(env, "/memory off"))
    with pytest.raises(MemoryUnavailable):
        run(env, context(env, "/memory on"))
    assert env.repo.get_control(CHAT)["learning_enabled"] is False


def test_non_admin_group_mutation_never_claims_receipt(env):
    activate(env)
    assert "requires" in run(env, context(env, "/memory off"), admin=False)
    assert not list(env.repo._list(CHAT, "CONTROL_COMMAND#"))


@pytest.mark.parametrize(
    "reference",
    [
        "FACT#USER#123456789#occupation#current@1",
        "FACT#USER#123456789#tech_stack#" + "a" * 64 + "@2",
        "FACT#USER#123456789#communication_preferences#language@3",
        "FACT#GROUP#decision#" + "b" * 64 + "@4",
    ],
)
def test_canonical_control_reference_projection_preserves_value_and_quote_offsets(env, reference):
    original = "/memory@zerde_bot  correct\t" + reference + "\nRust 🦀"
    start = original.index("Rust")
    command = context(
        env,
        original,
        entities=[{"type": "blockquote", "offset": start, "length": len("Rust 🦀".encode("utf-16-le")) // 2}],
    )
    source = source_event(command._update)
    assert source.text == original.replace(reference, " " * len(reference))
    assert source.text[start:] == "Rust 🦀"
    assert source.quoted_spans == ((start, len(original)),)
    assert source.source_kind == "confirmation"
    require_public_content(source.text, max_length=20000)


@pytest.mark.parametrize(
    "reference",
    [
        "FACT#USER#123456789#occupation#current@0",
        "FACT#USER#123456789#occupation#current@1trailing",
        "FACT#USER#123456789#occupation#language@1",
        "FACT#GROUP#tech_stack#" + "a" * 64 + "@1",
    ],
)
def test_invalid_control_identity_is_never_removed_from_public_content(env, reference):
    original = "/memory correct " + reference + " Rust"
    assert source_event(context(env, original)._update).text == original


def test_correct_value_stays_unchanged_and_private_values_remain_rejected(env):
    fact = seed(env)
    reference = fact["fact_id"] + "@" + str(fact["fact_version"])
    command = context(env, "/memory correct " + reference + " api_key=sk-" + "x" * 24)
    source = source_event(command._update)
    assert source.text.endswith("api_key=sk-" + "x" * 24)
    with pytest.raises(MemoryInputError):
        run(env, command)
    assert env.repo.get_profile(CHAT, USER)[0]["value"] == "Python"


def test_prepared_confirmation_recovers_after_fact_transaction_failure(env, monkeypatch):
    fact = seed(env)
    reference = fact["fact_id"] + "@" + str(fact["fact_version"])
    command = context(env, "/memory correct " + reference + " Rust")
    original = env.repo._transaction
    fired = False

    def fail(operations):
        nonlocal fired
        if not fired and any(op.get("Put", {}).get("Item", {}).get("sk", "").startswith("FACT#") for op in operations):
            fired = True
            raise database_fault()
        return original(operations)

    monkeypatch.setattr(env.repo, "_transaction", fail)
    with pytest.raises(ClientError):
        run(env, command)
    source = source_event(command._update)
    assert env.repo._read(CHAT, "RAW#90")["text"] == source.text
    assert env.repo.get_profile(CHAT, USER)[0]["value"] == "Python"
    assert "CORRECTED" in run(env, command)
    assert [fact["value"] for fact in env.repo.get_profile(CHAT, USER)] == ["Rust"]


def test_foreign_actor_cannot_recover_pending_source_purge(env):
    seed(env)
    job = MemoryLifecycle(env.repo).begin(CHAT, scope="source", target="8")
    command = context(env, "/memory forget this", reply_to_message={"message_id": 8})
    command.user_id = "777"
    command.message["from"] = {"id": 777}
    with pytest.raises(MemoryUnavailable):
        run(env, command)
    assert env.repo._read(CHAT, job["sk"])["state"] == "WAITING"
