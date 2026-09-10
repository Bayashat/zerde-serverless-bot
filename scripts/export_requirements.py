"""Export CDK's pip inputs from the single root uv.lock; never resolve per Lambda."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = {
    "src/bot/requirements.txt": ["--only-group", "lambda-bot"],
    "src/news/requirements.txt": ["--only-group", "lambda-news"],
    "src/quiz/requirements.txt": ["--only-group", "lambda-quiz"],
    "src/operations/requirements.txt": ["--only-group", "lambda-common"],
    "infra/requirements.txt": ["--no-dev"],
}
HEADER = "# Generated from root uv.lock by scripts/export_requirements.py; do not edit.\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail on drift without modifying files")
    args = parser.parse_args()
    mismatches = []
    for relative_path, groups in EXPORTS.items():
        result = subprocess.run(
            [
                os.environ.get("UV", "uv"),
                "export",
                "--locked",
                "--no-emit-project",
                "--no-header",
                "--no-annotate",
                "--format",
                "requirements.txt",
                *groups,
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        expected = HEADER + result.stdout
        path = ROOT / relative_path
        if args.check:
            if not path.exists() or path.read_text() != expected:
                mismatches.append(relative_path)
        else:
            path.write_text(expected)
    if mismatches:
        print("Requirements drift: " + ", ".join(mismatches))
        print("Run uv lock, then uv run python scripts/export_requirements.py")
        return 1
    print("Locked requirements " + ("verified" if args.check else "exported") + f" ({len(EXPORTS)} packages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
