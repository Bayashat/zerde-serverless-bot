"""Offline operator pauses must not turn unexecuted scenarios into successes."""

import asyncio
import json

from services.memory_budget import RESERVATION_MICRO_USD

from dev.tools.memory_eval.gemini_broker import BrokerEngine
from dev.tools.memory_eval.live import run_scenarios
from dev.tools.memory_eval.live_session import AttemptLedger
from tests.test_live_memory_eval import call, corpus, good_payload, manifest, no_sleep


def test_rate_limit_stops_new_wire_and_preserves_reserved_attempt_until_explicit_resume(tmp_path):
    ledger, attempts = AttemptLedger(tmp_path, manifest()), []

    async def wire(kind, request):
        attempts.append(request)
        return None, {"http_status": 429}

    engine = BrokerEngine(ledger, wire, sleep=no_sleep)
    assert asyncio.run(engine.generate(call()))["reason"] == "provider_rate_limited"
    assert asyncio.run(engine.generate(call(1)))["reason"] == "provider_rate_limited"
    assert len(attempts) == 1 and ledger.summary()["unknown_hold_micro_usd"] == RESERVATION_MICRO_USD
    assert ledger.summary()["attempts_reserved"] == 1
    ledger.close()

    reopened = AttemptLedger(tmp_path, manifest())

    async def recovered(kind, request):
        attempts.append(request)
        return good_payload(), {"http_status": 200}

    resumed = BrokerEngine(reopened, recovered, sleep=no_sleep)
    cached = asyncio.run(resumed.generate(call()))
    assert cached["reason"] == "recorded_rate_limited" and cached["cache_hit"]
    assert asyncio.run(resumed.generate(call(1)))["ok"]
    assert len(attempts) == 2 and reopened.summary()["unknown_hold_micro_usd"] == RESERVATION_MICRO_USD
    reopened.close()


def test_real_rate_limit_unwinds_production_handlers_without_committing_partial_scenario(tmp_path):
    requests = []

    class Broker:
        def call(self, request):
            requests.append(request)
            return {"ok": False, "reason": "provider_rate_limited"}

    observations, executions = run_scenarios(corpus(), [], tmp_path, Broker(), answer_route="public-v1")
    assert requests and len(requests) == 1
    assert observations == executions == []
    assert list((tmp_path / "scenarios").iterdir()) == []
    pause = json.loads((tmp_path / "execution-status.json").read_text())
    assert pause["reason"] == "provider_rate_limited"
    assert pause["planned_scenarios"] == 1 and pause["completed_scenarios"] == 0


def test_single_shot_public_audit_resumes_past_only_its_cached_rate_limit(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    import pytest
    from services import group_agent

    from dev.tools.memory_eval.contract import read_jsonl
    from dev.tools.memory_eval.domain_adapter import DomainReplayAdapter
    from dev.tools.memory_eval.fixture_provider import FixtureProvider, gemini_payload
    from dev.tools.memory_eval.live import EvaluationPaused, RemoteProvider
    from dev.tools.memory_eval.replay_input import project_scenario
    from tests.test_public_memory_eval import catalog

    monkeypatch.setattr(group_agent, "GROUP_CHAT_REPLY_GEMINI_RETRY_DELAYS_SECONDS", (0, 0))
    fixture, wires, owner = catalog(), [], {}
    refusal = "I do not know this person's details."
    frozen = {**manifest(), "answer_route": "public-v1", "scenario_ids": ["en-033"]}

    async def wire(kind, request):
        wires.append(kind)
        if kind == "plain_answer_audit" and wires.count(kind) == 1:
            return None, {"http_status": 429}
        payload = gemini_payload({"classification": "refusal", "refusal_quote": refusal, "claim_quotes": []})
        if kind == "plain_answer":
            payload["candidates"][0]["content"]["parts"] = [{"text": refusal}]
        return payload, {"http_status": 200}

    with ThreadPoolExecutor(max_workers=1) as executor:

        def initialise():
            owner["ledger"] = AttemptLedger(tmp_path, frozen)
            owner["engine"] = BrokerEngine(owner["ledger"], wire, sleep=no_sleep)

        executor.submit(initialise).result()

        class Broker:
            def call(self, request):
                return executor.submit(lambda: asyncio.run(owner["engine"].generate(request))).result()

        def provider(*, kind, trace, scenario_id):
            if kind in {"plain_answer", "plain_answer_audit"}:
                return RemoteProvider(Broker(), kind=kind, trace=trace, scenario_id=scenario_id)
            return FixtureProvider(fixture, kind=kind, trace=trace)

        scenario = next(
            row for row in read_jsonl("tests/fixtures/memory_v2_eval/scenarios.jsonl") if row["scenario_id"] == "en-033"
        )
        with pytest.raises(EvaluationPaused):
            DomainReplayAdapter(fixture, provider_factory=provider, answer_route="public-v1").observe_scenario(
                project_scenario(scenario)
            )
        assert len(wires) == 2
        executor.submit(lambda: owner.update(engine=BrokerEngine(owner["ledger"], wire, sleep=no_sleep))).result()
        result = DomainReplayAdapter(fixture, provider_factory=provider, answer_route="public-v1").observe_scenario(
            project_scenario(scenario)
        )[-1]
        assert result["replay"]["state"] == "EXECUTED"
        assert len(result["answers"]) == 2 and all(
            a["abstained"] and a["delivery"]["state"] == "SENT" for a in result["answers"]
        )
        assert len(wires) == 5
        summary = executor.submit(owner["ledger"].summary).result()
        assert summary["unknown_hold_micro_usd"] == RESERVATION_MICRO_USD
        assert summary["cache_hits"] == 2
        executor.submit(owner["ledger"].close).result()
