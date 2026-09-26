"""Public route engineering fixtures, never real-model quality evidence."""

import asyncio
import copy
import json

import pytest

from dev.tools.memory_eval.contract import EvaluationInputError, read_jsonl
from dev.tools.memory_eval.domain_adapter import DomainReplayAdapter
from dev.tools.memory_eval.fixture_provider import FixtureCatalog, FixtureProvider, gemini_payload
from dev.tools.memory_eval.plain_requests import (
    build_audit_request,
    build_plain_payload,
    parse_audit,
    validate_audit_request,
    validate_plain_request,
)
from dev.tools.memory_eval.replay_input import project_scenario


def catalog():
    return FixtureCatalog(read_jsonl("tests/fixtures/memory_v2_eval/provider_fixtures.jsonl"))


@pytest.mark.parametrize("language", ["kk", "ru", "en", "mixed"])
def test_plain_wire_reuses_production_without_memory_and_rejects_modifications(language):
    from services.explicit_context import normalise_chat_style_profile

    request = {
        "question": "What do you know about me?",
        "language": language,
        "style_profile": normalise_chat_style_profile(None),
    }
    request["payload"] = build_plain_payload(request["question"], language)
    validate_plain_request(request)
    changed = copy.deepcopy(request)
    changed["payload"]["contents"][0]["parts"].append({"inlineData": {"data": "hidden"}})
    with pytest.raises(EvaluationInputError):
        validate_plain_request(changed)
    changed = copy.deepcopy(request)
    changed["payload"]["contents"][0]["parts"][0]["text"] += "Saved secret profile: surgeon"
    with pytest.raises(EvaluationInputError):
        validate_plain_request(changed)


@pytest.mark.parametrize(
    "reply,label,refusal,claims",
    [
        ("I do not know your city.", "refusal", "I do not know your city.", []),
        ("You live in Rome.", "claims", "", ["You live in Rome."]),
        ("The service is temporarily unavailable.", "other", "", []),
    ],
)
def test_audit_observations_require_actual_verbatim_text(reply, label, refusal, claims):
    request = build_audit_request("Where do I live?", reply)
    validate_audit_request(request)
    result = {"classification": label, "refusal_quote": refusal, "claim_quotes": claims}
    assert parse_audit(gemini_payload(result), reply) == result
    bad = copy.deepcopy(result)
    bad["refusal_quote"] = "Invented refusal text"
    with pytest.raises(EvaluationInputError):
        parse_audit(gemini_payload(bad), reply)


def test_public_route_requires_its_own_observed_providers():
    with pytest.raises(EvaluationInputError):
        DomainReplayAdapter(catalog(), answer_route="public-v1")


@pytest.mark.parametrize("sid", ["en-033", "en-054"])
def test_paused_or_forgotten_memory_executes_public_delivery_without_passing_facts(sid):
    fixture = catalog()
    plain_requests, audits = [], []
    refusal = "I do not know this person's details."

    class Plain:
        missing = []

        async def generate(self, request):
            validate_plain_request(request)
            plain_requests.append(request)
            return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": refusal}]}}]}

    class Audit:
        missing = []

        async def generate(self, request):
            validate_audit_request(request)
            audits.append(request)
            return gemini_payload({"classification": "refusal", "refusal_quote": refusal, "claim_quotes": []})

    def provider(*, kind, trace, scenario_id):
        if kind == "plain_answer":
            return Plain()
        if kind == "plain_answer_audit":
            return Audit()
        return FixtureProvider(fixture, kind=kind, trace=trace)

    scenario = next(
        row for row in read_jsonl("tests/fixtures/memory_v2_eval/scenarios.jsonl") if row["scenario_id"] == sid
    )
    adapter = DomainReplayAdapter(fixture, provider_factory=provider, answer_route="public-v1")
    observations = adapter.observe_scenario(project_scenario(scenario))
    final = observations[-1]
    assert plain_requests and len(plain_requests) == len(audits) == 2
    assert len(final["answers"]) == 2
    assert all(answer["delivery"]["state"] == "SENT" and answer["abstained"] for answer in final["answers"])
    assert final["traces"]["business_before"] == final["traces"]["business_after"]
    assert adapter.network_attempts == 0
    # Audit input is only question and actual delivered text, never saved facts.
    for request in audits:
        assert set(json.loads(request["contents"][0]["parts"][0]["text"])) == {"question", "reply"}


def test_unverifiable_semantic_classification_is_not_abstention():
    with pytest.raises(EvaluationInputError):
        parse_audit(gemini_payload({"classification": "refusal", "refusal_quote": "", "claim_quotes": []}), "Hello")
    with pytest.raises(EvaluationInputError):
        parse_audit(gemini_payload({"classification": "ambiguous", "refusal_quote": "", "claim_quotes": []}), "Hello")


@pytest.mark.parametrize("kind", ["plain_answer", "plain_answer_audit"])
def test_new_wire_kinds_reserve_once_and_require_frozen_public_route(tmp_path, kind):
    from services.explicit_context import normalise_chat_style_profile
    from services.memory_budget import RESERVATION_MICRO_USD

    from dev.tools.memory_eval.gemini_broker import BrokerEngine
    from dev.tools.memory_eval.live_session import AttemptLedger, SessionError
    from tests.test_live_memory_eval import manifest

    frozen = {**manifest(), "answer_route": "public-v1"}
    ledger, calls = AttemptLedger(tmp_path, frozen), []
    request = build_audit_request("What do you know?", "I do not know.")
    if kind == "plain_answer":
        request = {
            "question": "What do you know?",
            "language": "en",
            "style_profile": normalise_chat_style_profile(None),
        }
        request["payload"] = build_plain_payload(request["question"], "en")
    call = {"scenario_id": "en-001", "kind": kind, "ordinal": 0, "request": request}

    async def wire(*args):
        assert ledger.summary()["charged_upper_micro_usd"] == RESERVATION_MICRO_USD
        calls.append(args)
        return None, {"error_type": "TimeoutError"}

    engine = BrokerEngine(ledger, wire)
    ledger.manifest = {**frozen, "answer_route": "domain"}
    with pytest.raises(SessionError):
        asyncio.run(engine.generate(call))
    assert not calls and ledger.summary()["attempts_reserved"] == 0
    ledger.manifest = frozen
    assert not asyncio.run(engine.generate(call))["ok"]
    assert not asyncio.run(engine.generate(call))["ok"]
    assert len(calls) == 1 and ledger.summary()["unknown_hold_micro_usd"] == RESERVATION_MICRO_USD
    ledger.close()


def test_a_changed_answer_route_cannot_resume_a_session(tmp_path):
    from dev.tools.memory_eval.live_session import SessionError, initialise_session
    from tests.test_live_memory_eval import manifest

    frozen = manifest()
    initialise_session(tmp_path, frozen, resume=False)
    with pytest.raises(SessionError):
        initialise_session(tmp_path, {**frozen, "answer_route": "public-v1"}, resume=True)


@pytest.mark.parametrize("fail_all", [False, True])
def test_plain_provider_failure_uses_production_retry_and_unavailable_delivery(monkeypatch, fail_all):
    from services import group_agent

    from dev.tools.memory_eval.live import RemoteProvider

    monkeypatch.setattr(group_agent, "GROUP_CHAT_REPLY_GEMINI_RETRY_DELAYS_SECONDS", (0, 0))
    fixture, calls = catalog(), []
    refusal = "I do not know this person's details."

    class Broker:
        def call(self, call):
            calls.append(call)
            if fail_all or len(calls) == 1:
                return {"ok": False, "reason": "provider_unknown"}
            return {
                "ok": True,
                "payload": {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": refusal}]}}]},
            }

    class Audit:
        missing = []

        async def generate(self, request):
            data = json.loads(request["contents"][0]["parts"][0]["text"])
            result = {"classification": "other", "refusal_quote": "", "claim_quotes": []}
            if data["reply"] == refusal:
                result.update(classification="refusal", refusal_quote=refusal)
            return gemini_payload(result)

    def provider(*, kind, trace, scenario_id):
        if kind == "plain_answer":
            return RemoteProvider(Broker(), kind=kind, trace=trace, scenario_id=scenario_id)
        if kind == "plain_answer_audit":
            return Audit()
        return FixtureProvider(fixture, kind=kind, trace=trace)

    scenario = next(
        row for row in read_jsonl("tests/fixtures/memory_v2_eval/scenarios.jsonl") if row["scenario_id"] == "en-033"
    )
    adapter = DomainReplayAdapter(fixture, provider_factory=provider, answer_route="public-v1")
    final = adapter.observe_scenario(project_scenario(scenario))[-1]
    assert len(final["answers"]) == 2 and all(answer["delivery"]["state"] == "SENT" for answer in final["answers"])
    assert len(calls) == (2 * group_agent.GROUP_CHAT_REPLY_GEMINI_MAX_ATTEMPTS if fail_all else 3)
    assert final["replay"]["state"] == ("UNSUPPORTED" if fail_all else "EXECUTED")
    assert all(answer["abstained"] is not fail_all for answer in final["answers"])


@pytest.mark.parametrize("language", ["kk", "ru", "en", "mixed"])
def test_actual_public_transport_matches_the_strict_plain_serializer(monkeypatch, language):
    from unittest.mock import MagicMock

    from services import group_agent
    from services.ai import gemini_client
    from services.explicit_context import normalise_chat_style_profile

    from dev.tools.memory_eval.plain_requests import plain_client

    class Captured(BaseException):
        pass

    question = "What do you know about my current project?"
    style = normalise_chat_style_profile({"tone": "concise"})
    client, captured = plain_client(), []

    def capture(**kwargs):
        assert kwargs["operation"] == "group_chat_reply"
        captured.append(json.loads(kwargs["body"]))
        raise Captured()

    client._post_generate_content = capture
    monkeypatch.setattr(group_agent, "_get_gemini", lambda: client)
    monkeypatch.setattr(gemini_client, "_circuit_is_open", lambda *args: False)
    with pytest.raises(Captured):
        group_agent.answer_group_question(
            repo=MagicMock(),
            bot=MagicMock(),
            chat_id=-100123,
            reply_to_message_id=11,
            user_text=question,
            lang=language,
        )
    assert captured == [build_plain_payload(question, language, style)]
