"""python -m dev.tools.memory_eval: offline files only; no provider invocation path."""

import argparse
import json
import os
import platform
import sys
from pathlib import Path
from unittest.mock import patch

from .contract import fingerprint, read_jsonl, validate_corpus
from .evaluator import evaluate
from .reporting import render_catalog, write_report
from .runner import OracleSelfCheck, collect_observations


def source_provenance(root):
    """Hash the declared local source scope, not an alleged production image."""
    scopes = ("src/bot", "src/shared/python", "dev/tools/memory_eval")
    paths = {path for scope in scopes for path in (root / scope).rglob("*.py")}
    paths.update(root / name for name in ("pyproject.toml", "uv.lock"))
    return {
        "execution_source_sha256": fingerprint(
            {str(path.relative_to(root)): path.read_text() for path in sorted(paths)}
        ),
        "execution_source_scope": [*(scope + "/**/*.py" for scope in scopes), "pyproject.toml", "uv.lock"],
        "execution_source_files": len(paths),
        "python_version": platform.python_version(),
        "dependency_evidence": "locked_manifest_only_not_installed_package_attestation",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Offline Memory V2 evaluation; never a production/model acceptance claim"
    )
    parser.add_argument("command", choices=("validate", "catalog", "evaluate", "self-check", "replay"))
    parser.add_argument("--corpus", default="tests/fixtures/memory_v2_eval/scenarios.jsonl")
    parser.add_argument("--predictions")
    parser.add_argument("--provenance")
    parser.add_argument("--provider-fixtures", default="tests/fixtures/memory_v2_eval/provider_fixtures.jsonl")
    parser.add_argument("--output", default="/tmp/zerde-memory-eval")
    args = parser.parse_args()
    corpus = read_jsonl(args.corpus)
    if args.command == "validate":
        info = validate_corpus(corpus)
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0 if info["size_gate"] else 2
    if args.command == "catalog":
        validate_corpus(corpus)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(render_catalog(corpus))
        return 0
    if args.command == "replay":
        validate_corpus(corpus)
        root = Path(__file__).resolve().parents[3]
        sys.path[:0] = [str(root / "src/bot"), str(root / "src/shared/python")]
        from .fixture_provider import FixtureCatalog

        fixture_rows = read_jsonl(args.provider_fixtures)
        with patch.dict(
            os.environ,
            {
                "STATS_TABLE_NAME": "local-replay-stats",
                "QUEUE_URL": "local-replay-queue",
                "BOT_TOKEN": "local-replay-no-token",
                "GEMINI_API_KEY": "",
                "LOG_LEVEL": "INFO",
                "ADMIN_USER_ID": "1",
                "GEMINI_RPD_LIMIT": "1000",
                "CHAT_LANG_MAP": "{}",
                "CAPTCHA_TIMEOUT_SECONDS": "300",
                "VOTEBAN_THRESHOLD": "5",
                "VOTEBAN_FORGIVE_THRESHOLD": "3",
                "CAPTCHA_MAX_ATTEMPTS": "3",
            },
        ):
            from .domain_adapter import DomainReplayAdapter

            adapter = DomainReplayAdapter(FixtureCatalog(fixture_rows))
            observations = collect_observations(corpus, adapter)
        provenance = {
            "provider_kind": "fake_provider",
            "purpose": "REAL_DOMAIN_SYNTHETIC_TRANSPORT_REPLAY",
            "network_calls": 0,
            "fixture_sha256": fingerprint(fixture_rows),
            **source_provenance(root),
            "unsupported_scenarios": sum(bool(run["missing_fixtures"]) for run in adapter.runs),
        }
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        (output / "observations.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in observations)
        )
        (output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    elif args.command == "self-check":
        observations = collect_observations(corpus, OracleSelfCheck())
        provenance = {"provider_kind": "synthetic_oracle", "purpose": "EVALUATOR_SELF_CHECK_ONLY", "network_calls": 0}
    else:
        if not args.predictions:
            parser.error("evaluate requires --predictions; gold is never substituted for model output")
        observations = read_jsonl(args.predictions)
        provenance = json.loads(Path(args.provenance).read_text()) if args.provenance else None
    report = evaluate(corpus, observations, provenance=provenance)
    write_report(report, args.output)
    print(
        json.dumps(
            {
                "output": str(Path(args.output).resolve()),
                "scope": "offline",
                "model_quality_claim": "NOT_VERIFIED",
                "numeric_thresholds_pass": report["numeric_thresholds_pass"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["numeric_thresholds_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
