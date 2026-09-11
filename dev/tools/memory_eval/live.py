"""Explicit, bounded Gemini evaluation on repository synthetic data only.

Run separately from the always-offline memory_eval CLI. This module never enables
AWS/Telegram networking in the domain replay process.
"""

import argparse
import copy
import json
import os
import selectors
import sqlite3
import subprocess
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from unittest.mock import patch

from .__main__ import source_provenance
from .contract import fingerprint, read_jsonl, validate_corpus
from .evaluator import evaluate
from .fixture_provider import FixtureCatalog
from .gemini_broker import MAX_FRAME_BYTES, ROOT, runtime_environment
from .live_session import SessionError, atomic_json, exclusive_lock, initialise_session
from .replay_input import project_scenario
from .reporting import write_report


class BrokerClient:
    def __init__(self, directory, *, api_key, rpm):
        if not isinstance(api_key, str) or not api_key.strip():
            raise SessionError("GEMINI_API_KEY is required in the environment")
        environment = {**runtime_environment(), "GEMINI_API_KEY": api_key}
        self.process = subprocess.Popen(
            [sys.executable, "-m", "dev.tools.memory_eval.gemini_broker", str(directory)],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self.timeout = 60 / rpm + 30
        self.dead = False

    def close(self):
        self.dead = True
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)
        if self.process.stdout:
            self.process.stdout.close()

    def call(self, call):
        if self.dead:
            raise SessionError("Provider broker is unavailable")
        raw = json.dumps(call, ensure_ascii=False, allow_nan=False).encode() + b"\n"
        if len(raw) > MAX_FRAME_BYTES:
            raise SessionError("Provider frame exceeds its bound")
        try:
            self.process.stdin.write(raw)
            self.process.stdin.flush()
            expires, received = time.monotonic() + self.timeout, bytearray()
            with selectors.DefaultSelector() as selector:
                selector.register(self.process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = expires - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise SessionError("Provider broker deadline exceeded")
                    chunk = os.read(self.process.stdout.fileno(), 65536)
                    if not chunk:
                        raise SessionError("Provider broker stopped before a receipt")
                    received.extend(chunk)
                    if len(received) > MAX_FRAME_BYTES:
                        raise SessionError("Provider receipt exceeds its bound")
                    if received.endswith(b"\n"):
                        result = json.loads(received)
                        if not isinstance(result, dict) or type(result.get("ok")) is not bool:
                            raise SessionError("Invalid provider receipt")
                        return result
        except Exception:
            self.close()  # Never reuse a potentially desynchronised pipe.
            raise SessionError("Provider broker has no trustworthy receipt") from None


class RemoteProvider:
    """Projected-domain provider seam; recorded failures never become fake facts."""

    def __init__(self, broker, *, kind, trace, scenario_id):
        self.broker, self.kind, self.trace, self.scenario_id = broker, kind, trace, scenario_id
        self.ordinal, self.failed = 0, False
        self.missing = []

    async def generate(self, request):
        self.trace.append(copy.deepcopy(request))
        ordinal, self.ordinal = self.ordinal, self.ordinal + 1
        if self.failed:
            raise TimeoutError("Explicit synthetic provider fault")
        digest = fingerprint(request)
        try:
            result = self.broker.call(
                {"scenario_id": self.scenario_id, "kind": self.kind, "ordinal": ordinal, "request": request}
            )
        except SessionError:
            result = {"ok": False, "reason": "broker_unavailable"}
        if result.get("ok") is not True or not isinstance(result.get("payload"), dict):
            self.missing.append(
                {"kind": self.kind, "request_sha256": digest, "reason": result.get("reason", "invalid_receipt")}
            )
            raise RuntimeError("Real provider attempt has no usable response")
        # A distinct, successfully budgeted retry can resolve this exact request.
        self.missing = [row for row in self.missing if row["request_sha256"] != digest]
        return result["payload"]


def provider_summary(directory):
    path = directory / "attempts.sqlite3"
    if not path.exists():
        return {"attempts_reserved": 0, "charged_upper_micro_usd": 0, "cache_hits": 0, "unknown_attempts": 0}
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        rows = db.execute("SELECT state,charged_micro_usd,hits,evidence_json FROM attempts").fetchall()
    return {
        "evidence_kind": "local_real_provider_budget_not_aws_or_moto",
        "attempts_reserved": len(rows),
        "charged_upper_micro_usd": sum(row[1] for row in rows),
        "cache_hits": sum(row[2] for row in rows),
        "unknown_attempts": sum(row[0] != "RESPONSE" for row in rows),
        "usage_verified_attempts": sum(bool(json.loads(row[3] or "{}").get("usage_verified")) for row in rows),
    }


def run_scenarios(corpus, catalog, directory, broker, *, stop_after=None):
    """Caller holds session.lock. Completed scenarios resume without domain/HTTP replay."""
    from .domain_adapter import DomainReplayAdapter

    result_directory = directory / "scenarios"
    result_directory.mkdir(mode=0o700, exist_ok=True)
    observations, executions = [], []
    for scenario in corpus:
        sid = scenario["scenario_id"]
        projected = project_scenario(scenario)
        path = result_directory / (fingerprint(sid) + ".json")
        if path.exists():
            result = json.loads(path.read_text())
            if result["input_sha256"] != fingerprint(projected):
                raise SessionError("Persisted scenario input changed")
        else:
            adapter = DomainReplayAdapter(catalog, provider_factory=lambda **kwargs: RemoteProvider(broker, **kwargs))
            adapter.provider_kind = "recorded_provider"
            try:
                records = adapter.observe_scenario(projected)
                for record in records:
                    record["replay"]["network_scope"] = "domain_process_zero_broker_attempts_in_persistent_ledger"
                    record["traces"]["budget_ledger"][
                        "evidence_kind"
                    ] = "moto_domain_transactions_provider_response_usage_synthetic_aws_not_real_billing"
                    checkpoint = next(
                        cp for cp in projected["checkpoints"] if cp["checkpoint_id"] == record["checkpoint_id"]
                    )
                    fault_injected = False
                    for event in projected["events"]:
                        if event["type"] in {"provider_failure", "provider_resume"}:
                            fault_injected = event["type"] == "provider_failure"
                        if event["event_id"] == checkpoint["after_event"]:
                            break
                    unresolved = [
                        row["work_id"]
                        for row in record["traces"]["work"]
                        if row["state"] in {"PENDING", "LEASED"} and row["reason"] in {"provider", "schema"}
                    ]
                    if unresolved and not fault_injected:
                        record["replay"].update(state="UNSUPPORTED", unresolved_provider_work=unresolved)
                result = {
                    "scenario_id": sid,
                    "input_sha256": fingerprint(projected),
                    "status": (
                        "UNSUPPORTED" if any(r["replay"]["state"] == "UNSUPPORTED" for r in records) else "EXECUTED"
                    ),
                    "observations": records,
                }
            except Exception as exc:
                # Preserve the missing checkpoints, rather than fabricate empty
                # gold-shaped observations or silently drop a planned scenario.
                result = {
                    "scenario_id": sid,
                    "input_sha256": fingerprint(projected),
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "observations": [],
                }
            atomic_json(path, result)
        observations.extend(result["observations"])
        executions.append({key: value for key, value in result.items() if key != "observations"})
        atomic_json(
            directory / "progress.json", {"scenarios": executions, "provider_budget": provider_summary(directory)}
        )
        # A scenario-level commit is the recovery boundary. The full observation
        # list can always be reconstructed from these atomic records.
        print(json.dumps({"scenario_id": sid, "status": result["status"], "completed": len(executions)}), flush=True)
        if stop_after is not None and len(executions) >= stop_after:
            break
    return observations, executions


def build_manifest(corpus, confirmation_rows, *, budget_micro_usd, max_calls, rpm):
    from services.memory_budget import MODEL, PRICE_VERSION

    validate_corpus(corpus)
    if (
        type(budget_micro_usd) is not int
        or not 0 < budget_micro_usd <= 10_000_000
        or type(max_calls) is not int
        or not 1 <= max_calls <= 10000
        or type(rpm) is not int
        or not 1 <= rpm <= 60
    ):
        raise SessionError("Require explicit budget >0 and <=$10, max_calls 1..10000, rpm 1..60")
    projected = [project_scenario(scenario) for scenario in corpus]
    return {
        "schema": 1,
        "model": MODEL,
        "price_version": PRICE_VERSION,
        "budget_micro_usd": budget_micro_usd,
        "max_calls": max_calls,
        "rpm": rpm,
        "scenario_ids": [row["scenario_id"] for row in projected],
        "input_sha256": fingerprint(projected),
        "corpus_sha256": fingerprint(corpus),
        "confirmation_fixture_sha256": fingerprint(confirmation_rows),
        **source_provenance(ROOT),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget-usd", required=True)
    parser.add_argument("--max-calls", required=True, type=int)
    parser.add_argument("--rpm", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--stop-after-scenarios", type=int)
    args = parser.parse_args()
    if args.stop_after_scenarios is not None and args.stop_after_scenarios < 1:
        raise SessionError("Stop-after must be positive")
    try:
        amount = Decimal(args.budget_usd) * 1_000_000
        if not amount.is_finite() or amount != int(amount):
            raise SessionError("Budget must use whole USD micro-units")
    except (InvalidOperation, ValueError, OverflowError):
        raise SessionError("Invalid explicit USD budget") from None
    corpus = read_jsonl(ROOT / "tests/fixtures/memory_v2_eval/scenarios.jsonl")
    validate_corpus(corpus)
    if args.scenario:
        if len(set(args.scenario)) != len(args.scenario) or set(args.scenario) - {row["scenario_id"] for row in corpus}:
            raise SessionError("Unknown or duplicate planned scenario")
        corpus = [row for row in corpus if row["scenario_id"] in args.scenario]
    confirmations = [
        row
        for row in read_jsonl(ROOT / "tests/fixtures/memory_v2_eval/provider_fixtures.jsonl")
        if row["kind"] == "confirmation"
    ]
    catalog = FixtureCatalog(confirmations)
    api_key = os.environ.get("GEMINI_API_KEY", "")  # Only the child receives it; never argv or files.
    directory = args.output.resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    sys.path[:0] = [str(ROOT / "src/bot"), str(ROOT / "src/shared/python")]
    with exclusive_lock(directory / "session.lock"), patch.dict(os.environ, runtime_environment(), clear=True):
        manifest = build_manifest(
            corpus, confirmations, budget_micro_usd=int(amount), max_calls=args.max_calls, rpm=args.rpm
        )
        initialise_session(directory, manifest, resume=args.resume)
        plan = {
            "input_sha256": manifest["input_sha256"],
            "corpus_sha256": manifest["corpus_sha256"],
            "scenarios": [
                {
                    "scenario_id": row["scenario_id"],
                    "events": [event["event_id"] for event in row["events"]],
                    "checkpoints": [
                        {"checkpoint_id": cp["checkpoint_id"], "questions": [q["question_id"] for q in cp["questions"]]}
                        for cp in row["checkpoints"]
                    ],
                }
                for row in corpus
            ],
        }
        plan_path = directory / "plan.json"
        if args.resume:
            if not plan_path.exists() or json.loads(plan_path.read_text()) != plan:
                raise SessionError("Frozen evaluation plan is missing or changed")
        else:
            atomic_json(plan_path, plan)
        broker = BrokerClient(directory, api_key=api_key, rpm=args.rpm)
        try:
            observations, executions = run_scenarios(
                corpus, catalog, directory, broker, stop_after=args.stop_after_scenarios
            )
        finally:
            broker.close()
        current_source = source_provenance(ROOT)
        if any(manifest.get(key) != value for key, value in current_source.items()):
            raise SessionError("Executable source changed during the evaluation")
        provenance = {
            "provider_kind": "recorded_provider",
            "purpose": "REAL_GEMINI_SYNTHETIC_DOMAIN_EVALUATION",
            "model": manifest["model"],
            "corpus_sha256": manifest["corpus_sha256"],
            "domain_network_calls": 0,
            "provider_budget": provider_summary(directory),
            "faults_and_membership": "synthetic",
            "scenario_executions": executions,
            "planned_scenarios": len(corpus),
            "completed_scenarios": len(executions),
            **{key: manifest[key] for key in current_source},
        }
        atomic_json(directory / "provenance.json", provenance)
        fd = os.open(directory / "observations.jsonl", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            for row in observations:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        report = evaluate(corpus, observations, provenance=provenance)
        write_report(report, directory)
        print(
            json.dumps(
                {
                    "output": str(directory),
                    "numeric_thresholds_pass": report["numeric_thresholds_pass"],
                    "model_quality_claim": report["model_quality_claim"],
                }
            )
        )
        return 0 if report["numeric_thresholds_pass"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SessionError, OSError):
        print(
            "Evaluation stopped: invalid configuration or unavailable local session; no credentials are displayed.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
