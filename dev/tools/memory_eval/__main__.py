"""python -m dev.tools.memory_eval: offline files only; no provider invocation path."""

import argparse
import json
from pathlib import Path

from .contract import read_jsonl, validate_corpus
from .evaluator import evaluate
from .reporting import render_catalog, write_report
from .runner import OracleSelfCheck, collect_observations


def main():
    parser = argparse.ArgumentParser(
        description="Offline Memory V2 evaluation; never a production/model acceptance claim"
    )
    parser.add_argument("command", choices=("validate", "catalog", "evaluate", "self-check"))
    parser.add_argument("--corpus", default="tests/fixtures/memory_v2_eval/scenarios.jsonl")
    parser.add_argument("--predictions")
    parser.add_argument("--provenance")
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
    if args.command == "self-check":
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
