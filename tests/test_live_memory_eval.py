"""No real provider calls: native SQLite, real request validators and HTTP fakes."""

import asyncio
import copy
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
import pytest
from services.memory_budget import RESERVATION_MICRO_USD
from services.memory_v2.answer_prompt import build_answer_request
from services.memory_v2.extraction_prompt import build_request
from services.memory_v2.models import ExtractionSource, SourceRef

from dev.tools.memory_eval.contract import read_jsonl
from dev.tools.memory_eval.fixture_provider import FixtureCatalog, gemini_payload
from dev.tools.memory_eval.gemini_broker import BrokerEngine, ObservedClient, gemini_attempt, runtime_environment
from dev.tools.memory_eval.live import BrokerClient, RemoteProvider, build_manifest, run_scenarios
from dev.tools.memory_eval.live_session import AttemptLedger, SessionError, exclusive_lock, initialise_session


def corpus():
    return [
        copy.deepcopy(
            next(
                row
                for row in read_jsonl("tests/fixtures/memory_v2_eval/scenarios.jsonl")
                if row["scenario_id"] == "en-001"
            )
        )
    ]


def manifest(**overrides):
    return build_manifest(
        corpus(),
        [],
        budget_micro_usd=overrides.get("budget", 2_000_000),
        max_calls=overrides.get("max_calls", 10),
        rpm=60,
    )


def call(ordinal=0, *, kind="answer"):
    request = build_answer_request("What do you know about me?", [], [])
    if kind == "extraction":
        source = ExtractionSource("-100", SourceRef("10", 1, "epoch"), "1", "I use Python.", (), 2_000_000_001)
        request = build_request([source])
    return {"scenario_id": "en-001", "kind": kind, "ordinal": ordinal, "request": request}


async def no_sleep(_):
    pass


def good_payload():
    return gemini_payload({"mode": "unknown", "indices": []})


def test_reserve_before_wire_atomic_response_and_cached_no_second_charge(tmp_path):
    ledger = AttemptLedger(tmp_path, manifest())
    attempts = []

    async def wire(kind, request):
        assert ledger.summary()["charged_upper_micro_usd"] == RESERVATION_MICRO_USD
        attempts.append(request)
        return good_payload(), {"http_status": 200}

    engine = BrokerEngine(ledger, wire, sleep=no_sleep)
    first = asyncio.run(engine.generate(call()))
    second = asyncio.run(engine.generate(call()))
    assert first["payload"] == second["payload"] and second["cache_hit"]
    assert len(attempts) == 1
    assert ledger.summary()["charged_upper_micro_usd"] == 175
    assert ledger.summary()["usage_verified_attempts"] == 1
    ledger.close()
    reopened = AttemptLedger(tmp_path, manifest())
    assert reopened.cached(call())["payload"] == first["payload"]
    reopened.close()


@pytest.mark.parametrize("crash", [False, True])
def test_unknown_or_crashed_send_retains_reservation_and_cannot_replay(tmp_path, crash):
    ledger = AttemptLedger(tmp_path, manifest())
    seen = []

    async def wire(*_):
        seen.append(1)
        if crash:
            raise KeyboardInterrupt
        return None, {"http_status": None, "error_type": "TimeoutError"}

    engine = BrokerEngine(ledger, wire, sleep=no_sleep)
    if crash:
        with pytest.raises(KeyboardInterrupt):
            asyncio.run(engine.generate(call()))
    else:
        assert not asyncio.run(engine.generate(call()))["ok"]
    assert not asyncio.run(engine.generate(call()))["ok"]
    assert seen == [1]
    assert ledger.summary()["charged_upper_micro_usd"] == RESERVATION_MICRO_USD
    ledger.close()


def test_bad_schema_payload_is_cached_but_next_attempt_has_own_identity(tmp_path):
    ledger = AttemptLedger(tmp_path, manifest())
    responses = [gemini_payload({"bad_schema": True}), good_payload()]

    async def wire(*_):
        return responses.pop(0), {"http_status": 200}

    engine = BrokerEngine(ledger, wire, sleep=no_sleep)
    bad = asyncio.run(engine.generate(call()))
    good = asyncio.run(engine.generate(call(1)))
    assert bad["payload"] != good["payload"]
    assert asyncio.run(engine.generate(call()))["payload"] == bad["payload"]
    assert ledger.summary()["attempts_reserved"] == 2
    ledger.close()


@pytest.mark.parametrize(
    "options,reason", [({"budget": 500000}, "budget_exhausted"), ({"max_calls": 1}, "max_calls_exhausted")]
)
def test_limits_deny_before_the_next_wire_attempt(tmp_path, options, reason):
    ledger = AttemptLedger(tmp_path, manifest(**options))
    seen = []

    async def wire(*_):
        seen.append(1)
        return None, {"http_status": 503}

    engine = BrokerEngine(ledger, wire, sleep=no_sleep)
    asyncio.run(engine.generate(call()))
    assert asyncio.run(engine.generate(call(1)))["reason"] == reason
    assert seen == [1]
    ledger.close()


def test_native_sqlite_competing_reservations_cannot_overdraw(tmp_path):
    config = manifest(budget=500000)
    AttemptLedger(tmp_path, config).close()
    barrier = Barrier(2)

    def reserve(number):
        ledger = AttemptLedger(tmp_path, config)
        barrier.wait()
        try:
            ledger.reserve(call(number))
            return True
        except SessionError:
            return False
        finally:
            ledger.close()

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(reserve, [0, 1])) == [False, True]
    ledger = AttemptLedger(tmp_path, config)
    assert ledger.summary()["charged_upper_micro_usd"] == RESERVATION_MICRO_USD
    ledger.close()


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"totalTokenCount": 200},
        {"promptTokenCount": 1, "candidatesTokenCount": 1, "totalTokenCount": 2, "cachedContentTokenCount": 1},
    ],
)
def test_missing_or_unpriced_usage_cannot_refund(tmp_path, usage):
    ledger = AttemptLedger(tmp_path, manifest())
    identifier = ledger.reserve(call())
    ledger.finish(identifier, {"usageMetadata": usage}, {"http_status": 200})
    assert ledger.summary()["charged_upper_micro_usd"] == RESERVATION_MICRO_USD
    assert ledger.summary()["usage_verified_attempts"] == 0
    ledger.close()


def test_accounting_anomaly_is_persistent_no_more_network_authorization(tmp_path):
    ledger = AttemptLedger(tmp_path, manifest())
    identifier = ledger.reserve(call())
    assert not ledger.finish(
        identifier,
        {"usageMetadata": {"promptTokenCount": 4000000, "candidatesTokenCount": 0, "totalTokenCount": 4000000}},
        {},
    )
    with pytest.raises(SessionError, match="accounting_blocked"):
        ledger.reserve(call(1))
    ledger.close()


def test_request_or_configuration_drift_and_concurrent_session_fail_closed(tmp_path):
    original = manifest()
    with exclusive_lock(tmp_path / "session.lock"):
        initialise_session(tmp_path, original, resume=False)
        with pytest.raises(SessionError, match="Another"):
            with exclusive_lock(tmp_path / "session.lock"):
                pytest.fail("Second owner acquired the lock")
    initialise_session(tmp_path, original, resume=True)
    with pytest.raises(SessionError, match="configuration"):
        initialise_session(tmp_path, {**original, "rpm": 2}, resume=True)
    ledger = AttemptLedger(tmp_path, original)
    ledger.reserve(call())
    changed = call()
    changed["request"] = build_answer_request("Another question?", [], [])
    with pytest.raises(SessionError, match="ordinal"):
        ledger.cached(changed)
    ledger.close()
    with pytest.raises(SessionError, match="configuration"):
        AttemptLedger(tmp_path, {**original, "max_calls": 99})


@pytest.mark.parametrize("kind", ["answer", "extraction"])
def test_invalid_request_is_rejected_before_reserve_or_wire(tmp_path, kind):
    ledger = AttemptLedger(tmp_path, manifest())

    async def wire(*_):
        pytest.fail("Invalid input reached the network")

    invalid = call(kind=kind)
    invalid["request"]["tools"] = [{"googleSearch": {}}]
    with pytest.raises(ValueError):
        asyncio.run(BrokerEngine(ledger, wire).generate(invalid))
    assert ledger.summary()["attempts_reserved"] == 0
    ledger.close()


def test_pacing_happens_before_reserve_and_cached_receipts_do_not_wait(tmp_path):
    ledger = AttemptLedger(tmp_path, manifest(), clock=lambda: 1000)
    ledger.reserve(call())
    ledger.finish(AttemptLedger.identity(call()), good_payload(), {})
    waits = []

    async def sleep(seconds):
        waits.append(seconds)
        assert ledger.summary()["attempts_reserved"] == 1

    async def wire(*_):
        return good_payload(), {}

    engine = BrokerEngine(ledger, wire, sleep=sleep)
    asyncio.run(engine.generate(call()))
    asyncio.run(engine.generate(call(1)))
    assert waits == [1]
    ledger.close()


@pytest.mark.parametrize("kind", ["answer", "extraction"])
def test_actual_production_http_provider_records_only_fixed_host_and_usage(monkeypatch, kind):
    from zerde_common import async_http

    captured = []

    def respond(request):
        captured.append(request)
        return httpx.Response(200, json=good_payload())

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(async_http, "bounded_async_client", lambda **_: client)
    payload, evidence = asyncio.run(gemini_attempt(kind, call(kind=kind)["request"], "SYNTHETIC-API-CREDENTIAL"))
    assert payload["usageMetadata"]["totalTokenCount"] == 200
    assert evidence["http_status"] == 200 and evidence["response_sha256"]
    assert evidence["elapsed_ms"] >= 0
    assert (
        str(captured[0].url)
        == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent"
    )
    assert "SYNTHETIC-API-CREDENTIAL" not in json.dumps(evidence)


def test_non_success_response_does_not_log_server_credential_echo(monkeypatch):
    from zerde_common import async_http

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(403, text="SYNTHETIC-API-CREDENTIAL"))
    )
    monkeypatch.setattr(async_http, "bounded_async_client", lambda **_: client)
    payload, evidence = asyncio.run(gemini_attempt("answer", call()["request"], "SYNTHETIC-API-CREDENTIAL"))
    assert payload is None and evidence["http_status"] == 403
    assert "SYNTHETIC-API-CREDENTIAL" not in json.dumps(evidence)


def test_successful_model_credential_echo_is_rejected_and_redacted(monkeypatch):
    from zerde_common import async_http

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"text": "SYNTHETIC-API-CREDENTIAL"}))
    )
    monkeypatch.setattr(async_http, "bounded_async_client", lambda **_: client)
    payload, evidence = asyncio.run(gemini_attempt("answer", call()["request"], "SYNTHETIC-API-CREDENTIAL"))
    assert payload is None and evidence["error_type"] == "CredentialEchoRejected"
    assert "SYNTHETIC-API-CREDENTIAL" not in json.dumps(evidence)


def test_arbitrary_host_cannot_use_the_broker_client():
    async def rejected():
        observed = ObservedClient(None, {}, "secret", max_bytes=100)
        with pytest.raises(SessionError, match="destination"):
            async with observed.stream("POST", "https://api.telegram.org/sendMessage", follow_redirects=False):
                pytest.fail("Wrong destination accepted")

    asyncio.run(rejected())


class LocalBroker:
    def __init__(self):
        self.calls = []

    def call(self, call):
        self.calls.append(copy.deepcopy(call))
        document = json.loads(call["request"]["contents"][0]["parts"][0]["text"])
        result = (
            {"sources": [{"source_index": row["source_index"], "facts": []} for row in document["sources"]]}
            if call["kind"] == "extraction"
            else {"mode": "unknown", "indices": []}
        )
        return {"ok": True, "payload": gemini_payload(result), "cache_hit": False}


def test_real_domain_uses_projected_factory_and_completed_resume_never_calls_again(tmp_path):
    broker = LocalBroker()
    observations, executions = run_scenarios(corpus(), FixtureCatalog([]), tmp_path, broker)
    assert executions[0]["status"] == "EXECUTED" and observations[0]["facts"] == []
    assert observations[0]["answers"][0]["abstained"]
    count = len(broker.calls)
    assert count > 0
    again, _ = run_scenarios(corpus(), FixtureCatalog([]), tmp_path, broker)
    assert again == observations and len(broker.calls) == count
    encoded = json.dumps(broker.calls)
    assert all(
        label not in encoded for label in ("supporting_fact_ids", "accepted_values", "protected_business", "expected")
    )
    assert {row["kind"] for row in broker.calls} == {"answer", "extraction"}


def test_broker_failure_remains_missing_coverage_not_successful_empty_results(tmp_path):
    class Broken:
        def call(self, _):
            return {"ok": False, "reason": "budget_exhausted"}

    observations, executions = run_scenarios(corpus(), FixtureCatalog([]), tmp_path, Broken())
    assert executions[0]["status"] == "UNSUPPORTED"
    assert observations[0]["answers"] == []
    assert observations[0]["replay"]["missing_fixtures"]
    assert (tmp_path / "progress.json").exists()


def test_explicit_fault_event_never_reaches_broker_and_retry_ordinal_stays_stable():
    broker = LocalBroker()
    provider = RemoteProvider(broker, kind="answer", trace=[], scenario_id="en-001")
    provider.failed = True
    with pytest.raises(TimeoutError):
        asyncio.run(provider.generate(call()["request"]))
    assert broker.calls == [] and provider.missing == []
    provider.failed = False
    asyncio.run(provider.generate(call()["request"]))
    assert broker.calls[0]["ordinal"] == 1


def test_broker_subprocess_receives_key_only_in_sanitized_environment(tmp_path, monkeypatch):
    real_popen = subprocess.Popen
    launches = []

    def fake_popen(args, **kwargs):
        launches.append((args, kwargs["env"]))
        # A local stdio echo process, not the real Gemini broker.
        script = (
            "import sys,json\nfor line in sys.stdin:\n"
            " print(json.dumps({'ok':True,'payload':{},'cache_hit':False}),flush=True)\n"
        )
        return real_popen([sys.executable, "-c", script], **kwargs)

    monkeypatch.setenv("UNRELATED_PRODUCTION_SECRET", "must-not-inherit")
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    broker = BrokerClient(tmp_path, api_key="SYNTHETIC-API-CREDENTIAL", rpm=60)
    try:
        assert broker.call(call())["ok"]
    finally:
        broker.close()
    args, environment = launches[0]
    assert "SYNTHETIC-API-CREDENTIAL" not in json.dumps(args)
    assert environment["GEMINI_API_KEY"] == "SYNTHETIC-API-CREDENTIAL"
    assert "UNRELATED_PRODUCTION_SECRET" not in environment
    assert environment["AWS_SHARED_CREDENTIALS_FILE"] == "/dev/null"


def test_session_and_ledger_files_are_private_and_no_credentials_written(tmp_path):
    config = manifest()
    initialise_session(tmp_path, config, resume=False)
    ledger = AttemptLedger(tmp_path, config)
    ledger.reserve(call())
    ledger.close()
    assert (tmp_path / "session.json").stat().st_mode & 0o077 == 0
    assert (tmp_path / "attempts.sqlite3").stat().st_mode & 0o077 == 0
    assert "GEMINI_API_KEY" not in (tmp_path / "session.json").read_text()


@pytest.mark.parametrize("options", [{"budget": 0}, {"budget": 10000001}, {"max_calls": 0}, {"max_calls": 10001}])
def test_invalid_explicit_budget_or_call_limit_is_rejected(options):
    with pytest.raises(SessionError):
        manifest(**options)


def test_runtime_environment_has_no_real_cloud_or_telegram_credentials():
    environment = runtime_environment()
    assert environment["GEMINI_API_KEY"] == ""
    assert environment["BOT_TOKEN"] == "local-no-telegram-token"
    assert environment["AWS_EC2_METADATA_DISABLED"] == "true"


def test_exhausted_budget_does_not_wait_or_spawn_useless_attempts(tmp_path):
    ledger = AttemptLedger(tmp_path, manifest(budget=1), clock=lambda: 1000)

    async def forbidden(*_):
        pytest.fail("Denied budget waited or sent")

    result = asyncio.run(BrokerEngine(ledger, forbidden, sleep=forbidden).generate(call()))
    assert result["reason"] == "budget_exhausted"
    assert ledger.summary()["attempts_reserved"] == 0
    ledger.close()


def test_corrupted_cached_response_is_not_reused_or_billed_again(tmp_path):
    ledger = AttemptLedger(tmp_path, manifest())
    identifier = ledger.reserve(call())
    ledger.finish(identifier, good_payload(), {})
    with ledger.db:
        ledger.db.execute("UPDATE attempts SET response_json='{}' WHERE logical_id=?", (identifier,))
    with pytest.raises(SessionError, match="checksum"):
        ledger.cached(call())
    assert ledger.summary()["attempts_reserved"] == 1
    ledger.close()


def test_provider_fault_before_scenario_commit_recovers_using_same_logical_calls(tmp_path):
    ledger = AttemptLedger(tmp_path, manifest())
    attempts = []

    async def wire(*_):
        attempts.append(1)
        return good_payload(), {}

    engine = BrokerEngine(ledger, wire, sleep=no_sleep)
    response = asyncio.run(engine.generate(call(3)))
    ledger.close()
    # Restarted broker and deterministic per-scenario ordinal find the completed
    # attempt even though the scenario observation was not yet committed.
    recovered = AttemptLedger(tmp_path, manifest())
    again = asyncio.run(BrokerEngine(recovered, wire, sleep=no_sleep).generate(call(3)))
    assert response["payload"] == again["payload"] and len(attempts) == 1
    recovered.close()


def test_bad_model_schema_leaves_unfinished_work_and_fails_coverage(tmp_path):
    class Invalid:
        def call(self, _):
            return {"ok": True, "payload": gemini_payload({"bad_schema": True}), "cache_hit": False}

    records, executions = run_scenarios(corpus(), FixtureCatalog([]), tmp_path, Invalid())
    assert executions[0]["status"] == "UNSUPPORTED"
    assert records[0]["replay"]["unresolved_provider_work"]
    assert records[0]["answers"] == []


def test_unexpected_domain_error_is_recorded_without_fabricated_checkpoint(tmp_path, monkeypatch):
    from dev.tools.memory_eval.domain_adapter import DomainReplayAdapter

    def fail(*_):
        raise RuntimeError("An arbitrary exception body must not be persisted")

    monkeypatch.setattr(DomainReplayAdapter, "observe_scenario", fail)
    records, executions = run_scenarios(corpus(), FixtureCatalog([]), tmp_path, LocalBroker())
    assert records == [] and executions[0]["status"] == "FAILED"
    assert executions[0]["error_type"] == "RuntimeError"
    assert "arbitrary exception body" not in (tmp_path / "progress.json").read_text()


def test_actual_extraction_timeout_stays_bounded_and_preserves_safe_error(monkeypatch):
    from services.memory_v2 import gemini_extraction
    from zerde_common import async_http

    async def slow(_):
        await asyncio.sleep(1)
        pytest.fail("Response completed after request timeout")

    monkeypatch.setattr(gemini_extraction, "REQUEST_TIMEOUT_SECONDS", 0.01)
    client = httpx.AsyncClient(transport=httpx.MockTransport(slow))
    monkeypatch.setattr(async_http, "bounded_async_client", lambda **_: client)
    payload, evidence = asyncio.run(
        gemini_attempt("extraction", call(kind="extraction")["request"], "SYNTHETIC-API-CREDENTIAL")
    )
    assert payload is None and evidence["error_type"] == "ExtractionProviderError"
    assert evidence["elapsed_ms"] < 500


def test_live_cli_freezes_full_plan_before_smoke_and_resumes_without_repeating(tmp_path, monkeypatch):
    from dev.tools.memory_eval import live

    brokers = []

    class FakeClient(LocalBroker):
        def __init__(self, directory, **_):
            super().__init__()
            plan = json.loads((directory / "plan.json").read_text())
            assert len(plan["scenarios"]) == 240
            brokers.append(self)

        def close(self):
            pass

    monkeypatch.setattr(live, "BrokerClient", FakeClient)
    monkeypatch.setenv("GEMINI_API_KEY", "SYNTHETIC-API-CREDENTIAL")
    arguments = ["live", "--budget-usd", "2", "--max-calls", "2672", "--rpm", "10", "--output", str(tmp_path)]
    monkeypatch.setattr(sys, "argv", arguments + ["--stop-after-scenarios", "1"])
    assert live.main() == 2
    first_sid = brokers[0].calls[0]["scenario_id"]
    frozen = (tmp_path / "session.json").read_bytes()
    frozen_plan = (tmp_path / "plan.json").read_bytes()
    monkeypatch.setattr(sys, "argv", arguments + ["--resume", "--stop-after-scenarios", "2"])
    assert live.main() == 2
    assert all(call["scenario_id"] != first_sid for call in brokers[1].calls)
    assert (tmp_path / "session.json").read_bytes() == frozen
    assert (tmp_path / "plan.json").read_bytes() == frozen_plan
    provenance = json.loads((tmp_path / "provenance.json").read_text())
    assert provenance["planned_scenarios"] == 240 and provenance["completed_scenarios"] == 2
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["complete"] is False and report["numeric_thresholds_pass"] is False


@pytest.mark.parametrize("mutation", ["gold_only", "plan", "missing_plan"])
def test_live_resume_rejects_gold_or_plan_drift_before_broker(tmp_path, monkeypatch, mutation):
    from dev.tools.memory_eval import live
    from dev.tools.memory_eval.replay_input import project_scenario

    class FakeClient(LocalBroker):
        def __init__(self, *_args, **_kwargs):
            super().__init__()

        def close(self):
            pass

    monkeypatch.setattr(live, "BrokerClient", FakeClient)
    arguments = [
        "live",
        "--budget-usd",
        "2",
        "--max-calls",
        "20",
        "--rpm",
        "10",
        "--output",
        str(tmp_path),
        "--scenario",
        "en-001",
    ]
    monkeypatch.setattr(sys, "argv", arguments)
    assert live.main() == 2
    frozen_manifest = (tmp_path / "session.json").read_bytes()
    if mutation == "gold_only":
        changed = corpus()
        changed[0]["checkpoints"][0]["facts"][0]["accepted_values"] = ["Changed scoring label"]
        assert project_scenario(changed[0]) == project_scenario(corpus()[0])
        original_reader = live.read_jsonl
        monkeypatch.setattr(
            live, "read_jsonl", lambda path: changed if path.name == "scenarios.jsonl" else original_reader(path)
        )
    elif mutation == "plan":
        plan = json.loads((tmp_path / "plan.json").read_text())
        plan["scenarios"][0]["checkpoints"] = []
        (tmp_path / "plan.json").write_text(json.dumps(plan))
    else:
        (tmp_path / "plan.json").unlink()
    frozen_plan = (tmp_path / "plan.json").read_bytes() if (tmp_path / "plan.json").exists() else None
    monkeypatch.setattr(live, "BrokerClient", lambda *_a, **_k: pytest.fail("Drift started broker"))
    monkeypatch.setattr(sys, "argv", arguments + ["--resume"])
    with pytest.raises(SessionError):
        live.main()
    assert (tmp_path / "session.json").read_bytes() == frozen_manifest
    assert ((tmp_path / "plan.json").read_bytes() if (tmp_path / "plan.json").exists() else None) == frozen_plan


def test_midrun_source_drift_preserves_scenarios_but_refuses_new_scoring(tmp_path, monkeypatch):
    from dev.tools.memory_eval import live

    original_provenance = live.source_provenance

    class FakeClient(LocalBroker):
        def __init__(self, *_args, **_kwargs):
            super().__init__()

        def close(self):
            monkeypatch.setattr(
                live,
                "source_provenance",
                lambda root: {**original_provenance(root), "execution_source_sha256": "changed"},
            )

    monkeypatch.setattr(live, "BrokerClient", FakeClient)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "live",
            "--budget-usd",
            "2",
            "--max-calls",
            "20",
            "--rpm",
            "10",
            "--output",
            str(tmp_path),
            "--scenario",
            "en-001",
        ],
    )
    with pytest.raises(SessionError, match="source changed"):
        live.main()
    assert list((tmp_path / "scenarios").glob("*.json"))
    assert not (tmp_path / "report.json").exists()


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0.0000001", "not-a-number"])
def test_invalid_cli_amount_cannot_start_broker(tmp_path, monkeypatch, value):
    from dev.tools.memory_eval import live

    monkeypatch.setattr(
        sys, "argv", ["live", "--budget-usd", value, "--max-calls", "1", "--rpm", "1", "--output", str(tmp_path)]
    )
    monkeypatch.setattr(live, "BrokerClient", lambda *_, **__: pytest.fail("Invalid budget launched broker"))
    with pytest.raises(SessionError):
        live.main()


def test_live_cli_has_no_arbitrary_corpus_upload_option(monkeypatch):
    from dev.tools.memory_eval import live

    monkeypatch.setattr(sys, "argv", ["live", "--corpus", "real-telegram-export.json"])
    with pytest.raises(SystemExit) as stopped:
        live.main()
    assert stopped.value.code == 2


def test_actual_broker_process_refuses_insufficient_budget_under_forced_network_ban(tmp_path, monkeypatch):
    """Import and run the real child entrypoint, with sockets additionally disabled."""
    import sqlite3

    config = manifest(budget=1)
    initialise_session(tmp_path, config, resume=False)
    real_popen = subprocess.Popen

    def guarded_popen(args, **kwargs):
        script = (
            "import socket,sys\n"
            "def blocked(*a,**k): raise RuntimeError('TEST_NETWORK_FORBIDDEN')\n"
            "socket.socket.connect=blocked\nsocket.socket.connect_ex=blocked\n"
            "socket.socket.sendto=blocked\nsocket.getaddrinfo=blocked\n"
            "from dev.tools.memory_eval.gemini_broker import main\n"
            "sys.argv=['broker',sys.argv[1]]\nraise SystemExit(main())\n"
        )
        return real_popen([sys.executable, "-c", script, args[-1]], **kwargs)

    monkeypatch.setattr(subprocess, "Popen", guarded_popen)
    broker = BrokerClient(tmp_path, api_key="SYNTHETIC-API-CREDENTIAL", rpm=60)
    try:
        result = broker.call(call())
    finally:
        broker.close()
    assert result == {"ok": False, "reason": "budget_exhausted", "cache_hit": False}
    with sqlite3.connect(tmp_path / "attempts.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    assert b"SYNTHETIC-API-CREDENTIAL" not in (tmp_path / "attempts.sqlite3").read_bytes()


def test_broken_broker_receipt_closes_pipe_without_exposing_raw_output(tmp_path, monkeypatch):
    real_popen = subprocess.Popen

    def fake_popen(args, **kwargs):
        return real_popen(
            [sys.executable, "-c", "import sys; sys.stdin.readline(); print('SYNTHETIC-API-CREDENTIAL',flush=True)"],
            **kwargs,
        )

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    broker = BrokerClient(tmp_path, api_key="SYNTHETIC-API-CREDENTIAL", rpm=60)
    with pytest.raises(SessionError, match="trustworthy") as stopped:
        broker.call(call())
    assert "SYNTHETIC-API-CREDENTIAL" not in str(stopped.value)
    assert broker.dead
    with pytest.raises(SessionError, match="unavailable"):
        broker.call(call(1))


def test_oversized_real_response_is_bounded_and_retains_error_evidence(monkeypatch):
    from zerde_common import async_http

    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text="x" * 110000)))
    monkeypatch.setattr(async_http, "bounded_async_client", lambda **_: client)
    payload, evidence = asyncio.run(gemini_attempt("answer", call()["request"], "SYNTHETIC-API-CREDENTIAL"))
    assert payload is None and evidence["response_truncated"]
    assert len(evidence["response_text"]) == 100000 and evidence["received_bytes"] == 110000


def test_injected_factory_does_not_relax_the_existing_domain_network_ban(tmp_path):
    import socket

    class WrongBroker:
        def call(self, _):
            socket.create_connection(("example.invalid", 443))

    records, executions = run_scenarios(corpus(), FixtureCatalog([]), tmp_path, WrongBroker())
    assert records == [] and executions[0]["status"] == "FAILED"
    assert executions[0]["error_type"] == "EvaluationInputError"
