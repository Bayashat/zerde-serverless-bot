"""Real fact/source/lease transactions surrounding synthetic answer delivery."""

import asyncio
import json
from dataclasses import replace

import pytest
from services.memory_v2.answer_prompt import build_answer_request, parse_selection, validate_answer_request
from services.memory_v2.answer_rendering import render_facts, source_link
from services.memory_v2.answers import MemoryAnswerService
from services.memory_v2.lifecycle import MemoryLifecycle
from services.memory_v2.models import FRESHNESS_SECONDS, MemoryConflict, MemoryInputError, MemoryUnavailable

from tests import test_memory_v2_contract as contract
from tests.test_memory_v2_contract import CHAT, USER, activate, change, commit, event

env = contract.env


@pytest.fixture
def ready(env):
    activate(env)
    source = event(env)
    ref = env.repo.register_source(source)
    commit(env, ref)
    return source


class Selector:
    def __init__(self, validate, *, mode="facts", before=None):
        self.validate, self.mode, self.before = validate, mode, before

    async def select(self, *_, **kwargs):
        if self.before:
            self.before()
        await self.validate()
        return self.mode, (0,) if self.mode == "facts" else ()


def service(env, *, mode="facts", before=None, during_send=None):
    sends = []

    async def send(chat_id, text, **kwargs):
        if during_send:
            during_send()
        sends.append((chat_id, text, kwargs))
        return 70 + len(sends)

    answer = MemoryAnswerService(
        env.repo,
        authorize=lambda *_: True,
        sender=send,
        selector_factory=lambda validate: Selector(validate, mode=mode, before=before),
    )
    return answer, sends


def ask(answer, **kwargs):
    return asyncio.run(
        answer.answer(
            CHAT,
            USER,
            [USER],
            request_id="ask-1",
            question="What do I use?",
            lang="en",
            reply_to_message_id=90,
            **kwargs,
        )
    )


def test_answer_uses_native_ddb_values_and_only_reference_receipts(env, ready):
    answer, sends = service(env)
    result = ask(answer)
    assert result.state == "SENT" and result.message_ids == (71,)
    assert "Python" in sends[0][1] and "https://t.me/c/123/8" in sends[0][1]
    receipt = env.repo._read(CHAT, "ANSWER_REPLY#71")
    assert receipt["subject_ids"] == [USER] and receipt["source_refs"]
    assert not set(receipt) & {"question", "answer", "text", "value", "excerpt"}
    assert answer.reply_subjects(CHAT, 71) == (USER,)
    with pytest.raises(MemoryConflict):
        ask(answer)
    assert len(sends) == 1


def test_edit_while_model_selects_blocks_send(env, ready):
    def edit():
        env.clock.now += 1
        env.repo.observe(replace(ready, text="", edited_at=env.clock.now))

    answer, sends = service(env, before=edit)
    with pytest.raises(MemoryUnavailable):
        ask(answer)
    assert sends == []


def test_delete_during_send_waits_then_erases_receipts(env, ready):
    lifecycle = MemoryLifecycle(env.repo)
    jobs = []

    def erase():
        job = lifecycle.begin(CHAT, scope="subject", target=USER)
        jobs.append(job)
        assert lifecycle.advance(CHAT, job["sk"])["state"] == "WAITING"

    answer, sends = service(env, during_send=erase)
    assert ask(answer).state == "SENT"
    assert lifecycle.advance(CHAT, jobs[0]["sk"])["state"] == "DONE"
    assert not env.repo._read(CHAT, "ANSWER_REPLY#71")
    assert not answer.reply_subjects(CHAT, 71)
    assert len(sends) == 1  # A delivered message is not falsely claimed retractable.


def test_unknown_http_result_is_not_replayed(env, ready):
    def lost():
        raise TimeoutError("synthetic unknown delivery")

    answer, sends = service(env, during_send=lost)
    assert ask(answer).state == "UNKNOWN"
    row = list(env.repo._list(CHAT, "ANSWER_REQUEST#"))[0]
    assert row["state"] == "UNKNOWN"
    with pytest.raises(MemoryConflict):
        ask(answer)
    assert not sends


def test_about_needs_no_model_or_budget(env, ready):
    answer, sends = service(env)
    answer.selector_factory = lambda *_: pytest.fail("Deterministic profile must not call model")
    assert ask(answer, about=True).state == "SENT"
    assert "Fact reference" in sends[0][1]


def test_unknown_and_general_never_render_unused_facts(env, ready):
    answer, sends = service(env, mode="unknown")
    assert ask(answer).state == "SENT"
    assert "Python" not in sends[0][1]
    general, general_sends = service(env, mode="general")
    result = asyncio.run(
        general.answer(
            CHAT, USER, [USER], request_id="general-2", question="Explain SQL", lang="en", reply_to_message_id=91
        )
    )
    assert result.state == "GENERAL" and general_sends == []


def test_requester_left_group_cannot_send(env, ready):
    answer, sends = service(env)
    checks = iter([True, False])
    answer.authorize = lambda *_: next(checks)
    with pytest.raises(MemoryUnavailable):
        ask(answer)
    assert not sends


def test_source_link_has_no_fabricated_basic_group_link():
    assert source_link(-100123, 8) == "https://t.me/c/123/8"
    assert source_link(-123, 8) is None
    assert source_link(-100123, "8?foo") is None


def test_prompt_validates_native_decimal_profile_and_closed_options(env, ready):
    facts = env.repo.get_profile(CHAT, USER)
    request = build_answer_request("What do I use?", facts, [USER])
    validate_answer_request(request)
    request["generationConfig"]["candidateCount"] = 2
    with pytest.raises(MemoryInputError):
        validate_answer_request(request)


@pytest.mark.parametrize(
    "field,value",
    [
        ("field", "salary"),
        ("facet", "instructions"),
        ("freshness", "certain"),
        ("last_confirmed_at", True),
        ("subject_index", 8),
    ],
)
def test_provider_boundary_rejects_unpriced_or_unsupported_fact_metadata(env, ready, field, value):
    request = build_answer_request("What do I use?", env.repo.get_profile(CHAT, USER), [USER])
    raw = json.loads(request["contents"][0]["parts"][0]["text"])
    raw["facts"][0][field] = value
    request["contents"][0]["parts"][0]["text"] = json.dumps(raw)
    with pytest.raises(MemoryInputError):
        validate_answer_request(request)


@pytest.mark.parametrize(
    "selection",
    [
        {"mode": "facts", "indices": [1]},
        {"mode": "facts", "indices": [True]},
        {"mode": "facts", "indices": [0, 0]},
        {"mode": "unknown", "indices": [0]},
        {"mode": "general", "indices": [0]},
        {"mode": "facts", "indices": [], "answer": "invented"},
    ],
)
def test_model_cannot_emit_personal_prose_or_unavailable_references(selection):
    response = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(selection)}]}}]}
    with pytest.raises(MemoryInputError):
        parse_selection(response, 1)


def test_renderer_rechecks_180_day_boundary_and_escapes_evidence(env):
    activate(env)
    source = event(env, text="I live in Almaty.")
    ref = env.repo.register_source(source)
    commit(env, ref, [change(source.text, "Almaty", "location")])
    facts = env.repo.get_profile(CHAT, USER)
    output = render_facts(CHAT, facts, subject_names={"USER#" + USER: "<admin>"}, now=env.clock.now + FRESHNESS_SECONDS)
    assert "Last mentioned; not confirmed as current" in output[0] and "&lt;admin&gt;" in output[0]
    with pytest.raises(MemoryInputError):
        render_facts(-100999, facts)


def test_absent_subject_about_is_unknown_and_does_not_create_subject(env):
    activate(env)
    answer, sends = service(env)
    answer.selector_factory = lambda *_: pytest.fail("About needs no model")
    result = ask(answer, about=True)
    assert result.state == "SENT" and "Python" not in sends[0][1]
    assert not env.repo.get_subject(CHAT, USER)
    assert env.repo._read(CHAT, "ANSWER_REPLY#71")["subject_ids"] == []


def test_requester_forget_between_binding_and_prepare_blocks_late_receipt(env, ready, monkeypatch):
    answer, sends = service(env)
    lifecycle = MemoryLifecycle(env.repo)
    prepare = answer._prepare
    jobs = []

    def during_prepare(*args, **kwargs):
        job = lifecycle.begin(CHAT, scope="subject", target="99")
        jobs.append(job)
        assert lifecycle.advance(CHAT, job["sk"])["state"] == "WAITING"
        return prepare(*args, **kwargs)

    monkeypatch.setattr(answer, "_prepare", during_prepare)
    with pytest.raises(MemoryUnavailable):
        asyncio.run(
            answer.answer(
                CHAT,
                "99",
                [USER],
                request_id="actor-forget",
                question="What does this member use?",
                lang="en",
                reply_to_message_id=90,
            )
        )
    assert not sends
    assert lifecycle.advance(CHAT, jobs[0]["sk"])["state"] == "DONE"
    assert not list(env.repo._list(CHAT, "ANSWER_REQUEST#"))
    assert not list(env.repo._list(CHAT, "ANSWER_REPLY#"))


def test_async_authorization_is_awaited_again_before_sending(env, ready):
    answer, sends = service(env)
    checks = iter([True, False])

    async def authorize(*_):
        return next(checks)

    answer.authorize = authorize
    with pytest.raises(MemoryUnavailable):
        ask(answer)
    assert not sends
