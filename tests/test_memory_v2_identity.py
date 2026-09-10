"""Authenticated alias history cannot transfer a person's facts to a namesake."""

from dataclasses import replace

import pytest
from services.memory_v2.identity import IdentityDirectory, select_subjects
from services.memory_v2.lifecycle import MemoryLifecycle
from services.memory_v2.models import MemoryInputError, MemoryUnavailable

from tests import test_memory_v2_contract as contract
from tests.test_memory_v2_contract import CHAT, USER, activate, event

env = contract.env


def member(user_id=42, alias="test_person", status="member"):
    return {"status": status, "user": {"id": user_id, "username": alias, "first_name": "Same name"}}


def test_same_display_name_never_merges_user_ids(env):
    activate(env)
    records = {42: member(), 43: member(43, "another_person")}
    directory = IdentityDirectory(env.repo, get_chat_member=lambda _, actor: records[actor])
    for actor in (42, 43):
        source = event(env, message_id=str(actor), user=str(actor))
        env.repo.observe(source)
        directory.observe(source, records[actor]["user"])
    assert directory.resolve(CHAT, "test_person") == "42"
    assert directory.resolve(CHAT, "another_person") == "43"


def test_live_username_transfer_does_not_resolve_old_owner(env):
    activate(env)
    source = event(env)
    env.repo.observe(source)
    directory = IdentityDirectory(env.repo, get_chat_member=lambda *_: member(alias="renamed_person"))
    directory.observe(source, member()["user"])
    with pytest.raises(MemoryUnavailable):
        directory.resolve(CHAT, "test_person")


def test_forged_live_identity_and_other_chat_cannot_resolve(env):
    activate(env)
    source = event(env)
    env.repo.observe(source)
    directory = IdentityDirectory(env.repo, get_chat_member=lambda *_: member(43))
    directory.observe(source, member()["user"])
    with pytest.raises(MemoryUnavailable):
        directory.resolve(CHAT, "test_person")
    with pytest.raises(MemoryUnavailable):
        directory.resolve(-100999, "test_person")


def test_forget_erases_alias_and_optout_blocks_new_observation(env):
    activate(env)
    source = event(env)
    env.repo.observe(source)
    directory = IdentityDirectory(env.repo, get_chat_member=lambda *_: member())
    directory.observe(source, member()["user"])
    lifecycle = MemoryLifecycle(env.repo)
    job = lifecycle.begin(CHAT, scope="subject", target=USER, optout=True)
    assert lifecycle.advance(CHAT, job["sk"])["state"] == "DONE"
    assert not list(env.repo._list(CHAT, "ALIAS#"))
    with pytest.raises(MemoryUnavailable):
        directory.observe(replace(source, message_id="12"), member()["user"])


def test_alias_ttl_is_logical_and_author_is_required(env):
    activate(env)
    source = event(env)
    env.repo.observe(source)
    directory = IdentityDirectory(env.repo, get_chat_member=lambda *_: member())
    with pytest.raises(MemoryInputError):
        directory.observe(source, member(43)["user"])
    directory.observe(source, member()["user"])
    env.clock.now += 30 * 86400
    with pytest.raises(MemoryUnavailable):
        directory.resolve(CHAT, "test_person")


def test_utf16_mention_and_stable_reply_ids_have_no_name_heuristic():
    message = {
        "from": {"id": 42},
        "text": "😀 @test_person explain",
        "entities": [{"type": "mention", "offset": 3, "length": 12}],
        "reply_to_message": {"from": {"id": 43, "first_name": "test_person"}},
    }
    result = select_subjects(
        message, bot_username="zerde_bot", resolve_alias=lambda alias: "44", reply_subjects=lambda _: ()
    )
    assert result.subject_ids == ("44", "43", "42")


def test_unresolved_mention_is_reported_not_assigned_to_requester():
    def missing(_):
        raise MemoryUnavailable("unresolved")

    message = {"from": {"id": 42}, "text": "@test_person", "entities": [{"type": "mention", "offset": 0, "length": 12}]}
    result = select_subjects(message, bot_username="zerde_bot", resolve_alias=missing, reply_subjects=lambda _: ())
    assert result.unresolved_aliases == ("test_person",)


def test_deleted_bot_reply_text_does_not_become_identity_context():
    message = {
        "from": {"id": 42},
        "text": "why?",
        "reply_to_message": {
            "from": {"id": 9, "is_bot": True},
            "message_id": 20,
            "text": "Invented old personal facts about @other_person",
        },
    }
    result = select_subjects(
        message,
        bot_username="zerde_bot",
        resolve_alias=lambda _: pytest.fail("raw quote scanned"),
        reply_subjects=lambda _: (),
    )
    assert result.subject_ids == ("42",)
