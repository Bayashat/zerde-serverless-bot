"""Route parsed selections through actual transactions; semantic quality needs a real model.

The matrix is an expected-intent fixture, not a classifier implemented by this
test. Provider output is deliberately stubbed and must never be called model PASS.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from services.handlers.commands import handle_ask
from services.memory_v2.answer_prompt import SYSTEM, validate_answer_request
from services.memory_v2.answer_rendering import unknown_text
from services.memory_v2.answer_selector import MemoryAnswerSelector
from services.memory_v2.public_answers import MemoryPublicAnswers

from tests import test_memory_v2_contract as contract
from tests.test_memory_public_runtime import API, message
from tests.test_memory_v2_contract import CHAT, USER, activate, commit, event

env = contract.env
CASES = json.loads((Path(__file__).parent / "fixtures/ask_intent_cases.json").read_text())


def selected_service(env, mode):
    provider = Mock(
        generate=AsyncMock(
            return_value={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": json.dumps({"mode": mode, "indices": []})}]},
                    }
                ],
                "usageMetadata": {"promptTokenCount": 900, "candidatesTokenCount": 12, "totalTokenCount": 912},
            }
        )
    )
    budget, quota, api = Mock(), Mock(), API()
    quota.increment_and_check.return_value = (1, True)
    service = MemoryPublicAnswers(
        env.repo,
        api,
        selector_factory=lambda validate: MemoryAnswerSelector(
            provider, budget, validate_snapshot=validate, rate_limit=quota
        ),
        bot_username="zerde_bot",
    )
    return service, provider, budget, api


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
@pytest.mark.parametrize("has_unrelated_fact", [False, True], ids=["no-profile", "unrelated-python-fact"])
def test_current_selector_result_controls_plain_or_memory_delivery(env, case, has_unrelated_fact, monkeypatch):
    activate(env)
    if has_unrelated_fact:
        commit(env, env.repo.register_source(event(env)))
    service, provider, budget, api = selected_service(env, case["mode"])
    question = case["question"]
    msg = message(env, "/ask " + question)

    def memory_entry(value, **kwargs):
        assert value is msg and kwargs == {"question": question, "lang": case["lang"]}
        return asyncio.run(service.try_answer(value, **kwargs))

    monkeypatch.setattr("services.memory_v2.public_answers.try_memory_answer", memory_entry)
    ctx = MagicMock()
    ctx.text, ctx.message, ctx.lang_code = msg["text"], msg, case["lang"]
    ctx.chat_id, ctx.message_id, ctx.user_id = CHAT, msg["message_id"], int(USER)
    ctx.update_id, ctx.reply_to_message = 900, None
    ctx.username, ctx.user_data = "user_42", msg["from"]
    handle_ask(ctx)
    request = provider.generate.call_args.args[0]
    validate_answer_request(request)
    assert request["systemInstruction"]["parts"] == [{"text": SYSTEM}]
    inputs = json.loads(request["contents"][0]["parts"][0]["text"])
    assert inputs["question"] == question
    assert bool(inputs["facts"]) is has_unrelated_fact
    assert provider.generate.await_count == budget.reserve.call_count == budget.settle.call_count == 1
    if case["mode"] == "general":
        ctx.sqs_repo.send_group_ask_task.assert_called_once()
        queued = ctx.sqs_repo.send_group_ask_task.call_args.kwargs
        assert queued["user_text"] == queued["current_user_message"] == question
        assert queued["source_message_context"] == ""
        assert not {"facts", "subjects", "profile", "requester_profile_context"} & queued.keys()
        assert not api.sent and not list(env.repo._list(CHAT, "ANSWER_REQUEST#"))
    else:
        ctx.sqs_repo.send_group_ask_task.assert_not_called()
        assert api.sent == [unknown_text(case["lang"])]
        # A redelivery must not start the plain path or send another unknown reply.
        handle_ask(ctx)
        ctx.sqs_repo.send_group_ask_task.assert_not_called()
        assert api.sent == [unknown_text(case["lang"])]
        assert provider.generate.await_count == 1
    ctx.reply.assert_not_called()


@pytest.mark.parametrize("reply_is_bot", [False, True])
def test_general_selection_does_not_render_reply_authors_fact_or_bot_body(env, reply_is_bot):
    activate(env)
    commit(env, env.repo.register_source(event(env)))
    service, provider, _, api = selected_service(env, "general")
    msg = message(
        env,
        "Explain SQL",
        reply_to_message={
            "message_id": 8,
            "from": {"id": 77, "is_bot": reply_is_bot},
            "text": "Untrusted quoted claim: I own an RTX SPARK",
        },
    )
    assert not asyncio.run(service.try_answer(msg, question="Explain SQL", lang="en"))
    assert not api.sent
    inputs = json.loads(provider.generate.call_args.args[0]["contents"][0]["parts"][0]["text"])
    assert inputs["question"] == "Explain SQL"
    assert "Untrusted quoted claim" not in json.dumps(inputs)
