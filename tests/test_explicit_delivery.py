"""Actual actor/source transactions at the plain/media Telegram send boundary."""

import asyncio
from dataclasses import replace
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError
from services.memory_v2.explicit_delivery import ExplicitDelivery
from services.memory_v2.explicit_request_gate import capture
from services.memory_v2.models import MemoryConflict, MemoryUnavailable
from services.memory_v2.public_answers import MemoryPublicAnswers
from services.telegram_media import MediaReference

from tests import test_memory_v2_contract as contract
from tests.test_ephemeral_media import store
from tests.test_memory_public_runtime import API, Selector, message
from tests.test_memory_v2_contract import CHAT, USER, activate, commit, event

env = contract.env


def body(env, *, refs=None):
    return {
        "chat_id": CHAT,
        "requester_user_id": USER,
        "reply_to_message_id": 90,
        "request_gate": capture(env.repo, CHAT, USER, 90, requested_at=env.clock.now),
        "media_refs": refs or [],
    }


def guard(env, request, api, overlay=None):
    return ExplicitDelivery(env.repo, overlay or Mock(), Mock(), request, api)


@pytest.mark.parametrize("active", [False, True])
def test_plain_delivery_is_durable_even_before_memory_activation(env, active):
    if active:
        activate(env)
    request, api = body(env), API()
    first = guard(env, request, api)
    first.start()
    first.send_message(CHAT, "A plain answer", reply_to_message_id=90)
    first.close()
    with pytest.raises(MemoryConflict):
        guard(env, request, api).start()
    assert len(api.sent) == 1
    receipts = list(env.repo._list(CHAT, "ANSWER_REQUEST#"))
    assert len(receipts) == 1 and receipts[0]["state"] == "SENT"
    assert not env.repo.get_subject(CHAT, USER)


def test_unknown_send_is_not_retried_after_lease_expiry(env):
    activate(env)
    request, api = body(env), API()

    async def unknown(*_, **kwargs):
        api.sent.append("unknown")
        raise TimeoutError("private provider detail")

    api.send = unknown
    first = guard(env, request, api)
    first.start()
    with pytest.raises(MemoryUnavailable):
        first.send_message(CHAT, "Answer", reply_to_message_id=90)
    first.close()
    env.clock.now += 361
    with pytest.raises(MemoryConflict):
        guard(env, request, api).start()
    assert api.sent == ["unknown"]


def test_pre_send_provider_failure_can_retry_without_receipt(env):
    activate(env)
    request, api = body(env), API()
    first = guard(env, request, api)
    first.start()
    first.close()
    second = guard(env, request, api)
    second.start()
    second.send_message(CHAT, "Recovered", reply_to_message_id=90)
    second.close()
    assert api.sent == ["Recovered"]


def test_public_fact_read_error_before_prepare_recovers_on_redelivery(env, monkeypatch):
    activate(env)
    commit(env, env.repo.register_source(event(env)))
    api = API()
    actual = env.repo._read
    failed = False

    def transient(chat, key):
        nonlocal failed
        if key.startswith("FACT#") and not failed:
            failed = True
            raise ClientError({"Error": {"Code": "InternalServerError"}}, "GetItem")
        return actual(chat, key)

    monkeypatch.setattr(env.repo, "_read", transient)
    service = MemoryPublicAnswers(env.repo, api, selector_factory=Selector, bot_username="zerde_bot")
    with pytest.raises(ClientError):
        asyncio.run(service.try_answer(message(env), question="What do I use?", lang="en"))
    assert asyncio.run(service.try_answer(message(env), question="What do I use?", lang="en"))
    assert len(api.sent) == 1 and "Python" in api.sent[0]


def test_album_reread_and_final_source_version_fence(env):
    from services.memory_v2.media_ephemeral import EphemeralMediaRepository

    activate(env)
    source, _ = store(env)
    media_repo = EphemeralMediaRepository(env.repo)
    refs = media_repo.get_refs(CHAT, "album-1")
    assert MediaReference.from_mapping(refs[0]).to_dict()["ephemeral_source_ref"] == refs[0]["ephemeral_source_ref"]
    overlay = Mock()
    overlay.get_media_group_refs.side_effect = media_repo.get_refs
    api = API()
    delivery = guard(env, body(env, refs=refs), api, overlay)
    delivery.start()
    env.clock.now += 1
    env.repo.observe(replace(source, edited_at=env.clock.now, text="changed"))
    with pytest.raises(MemoryUnavailable):
        delivery.send_message(CHAT, "Old media analysis", reply_to_message_id=90)
    delivery.close()
    assert not api.sent


def test_plain_sent_blocks_later_memory_selection_of_same_update(env):
    activate(env)
    api, msg = API(), message(env)
    service = MemoryPublicAnswers(env.repo, api, selector_factory=Selector, bot_username="zerde_bot")
    assert not asyncio.run(service.try_answer(msg, question="What do I use?", lang="en"))
    request = body(env)
    plain = guard(env, request, api)
    plain.start()
    plain.send_message(CHAT, "No stored information", reply_to_message_id=90)
    plain.close()
    commit(env, env.repo.register_source(event(env)))
    assert asyncio.run(service.try_answer(msg, question="What do I use?", lang="en"))
    assert api.sent == ["No stored information"]


def test_memory_sent_blocks_plain_after_control_stop(env):
    activate(env)
    commit(env, env.repo.register_source(event(env)))
    api, msg = API(), message(env)
    service = MemoryPublicAnswers(env.repo, api, selector_factory=Selector, bot_username="zerde_bot")
    assert asyncio.run(service.try_answer(msg, question="What do I use?", lang="en"))
    control = env.repo.get_control(CHAT)
    stopped = env.repo.begin_group_stop(CHAT, expected_revision=control["revision"])
    env.repo.complete_group_stop(CHAT, expected_revision=stopped["revision"])
    with pytest.raises(MemoryConflict):
        guard(env, body(env), api).start()
    assert len(api.sent) == 1


@pytest.mark.parametrize("edit", [True, False])
def test_old_original_question_after_edit_or_actor_forget_is_not_resent(env, edit):
    from services.memory_v2.lifecycle import MemoryLifecycle

    from tests.test_memory_v2_lifecycle import finish

    activate(env)
    commit(env, env.repo.register_source(event(env)))
    old_question = event(env, "90", text="What do I use?")
    env.repo.observe(old_question)
    api, msg = API(), message(env)
    service = MemoryPublicAnswers(env.repo, api, selector_factory=Selector, bot_username="zerde_bot")
    assert asyncio.run(service.try_answer(msg, question=msg["text"], lang="en"))
    env.clock.now += 1
    if edit:
        env.repo.observe(replace(old_question, edited_at=env.clock.now, text="unrelated"))
    else:
        lifecycle = MemoryLifecycle(env.repo)
        job = lifecycle.begin(CHAT, scope="subject", target=USER)
        finish(lifecycle, job)
    assert asyncio.run(service.try_answer(msg, question=msg["text"], lang="en"))
    assert len(api.sent) == 1


def test_authorization_429_then_redelivery_sends_once_before_receipt(env):
    import json

    import httpx
    from services.memory_v2.telegram_api import MemoryTelegramAPI, TelegramReadRetryRequired

    activate(env)
    commit(env, env.repo.register_source(event(env)))
    counts = {"read": 0, "send": 0}

    def handler(request):
        if request.url.path.endswith("/getChatMember"):
            counts["read"] += 1
            # Initial membership succeeds, final membership before prepare fails.
            if counts["read"] == 2:
                return httpx.Response(429, json={"ok": False})
            payload = json.loads(request.content)
            result = {"user": {"id": int(payload["user_id"])}, "status": "member"}
        else:
            counts["send"] += 1
            result = {"message_id": 71, "chat": {"id": CHAT}, "reply_to_message": {"message_id": 90}}
        return httpx.Response(200, json={"ok": True, "result": result})

    async def run():
        from services.memory_v2.answers import MemoryAnswerService

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            api = MemoryTelegramAPI("123456:synthetic-token", client=client, configured=lambda _: True)
            service = MemoryAnswerService(env.repo, authorize=api.authorize, sender=api.send, selector_factory=Selector)
            kwargs = dict(request_id="tg:-100123:90", question="What do I use?", lang="en", reply_to_message_id=90)
            with pytest.raises(TelegramReadRetryRequired):
                await service.answer(CHAT, USER, [USER], **kwargs)
            assert not list(env.repo._list(CHAT, "ANSWER_REQUEST#"))
            assert (await service.answer(CHAT, USER, [USER], **kwargs)).state == "SENT"

    asyncio.run(run())
    assert counts["send"] == 1
