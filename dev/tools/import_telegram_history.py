#!/usr/bin/env python3
"""Import Telegram Desktop JSON history into ZerdeBot group memory.

Example:
  uv run python dev/tools/import_telegram_history.py \
    --chat-id -1001234567890 \
    --export ~/Downloads/Telegram/result.json \
    --since 2026-01-01 \
    --table-name zerde-serverless-bot-memory-dev \
    --queue-url https://sqs.eu-central-1.amazonaws.com/123/zerde-serverless-timeout-tasks-queue-dev \
    --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BOT_SRC = PROJECT_ROOT / "src" / "bot"
SHARED_SRC = PROJECT_ROOT / "src" / "shared" / "python"


def _prepare_import_path() -> None:
    for path in (str(SHARED_SRC), str(BOT_SRC)):
        if path not in sys.path:
            sys.path.insert(0, path)


def _seed_required_env(args: argparse.Namespace) -> None:
    if args.table_name:
        os.environ["MEMORY_TABLE_NAME"] = args.table_name
    if args.queue_url:
        os.environ["QUEUE_URL"] = args.queue_url
    os.environ.setdefault("AWS_DEFAULT_REGION", args.aws_region)
    os.environ.setdefault("QUEUE_URL", "https://sqs.eu-central-1.amazonaws.com/000000000000/history-import-dry-run")
    os.environ.setdefault("STATS_TABLE_NAME", "unused-history-import")
    os.environ.setdefault("ADMIN_USER_ID", "0")
    os.environ.setdefault("GEMINI_RPD_LIMIT", "1000")
    os.environ.setdefault("CHAT_LANG_MAP", "{}")
    os.environ.setdefault("CAPTCHA_TIMEOUT_SECONDS", "120")
    os.environ.setdefault("KICK_BAN_DURATION_SECONDS", "31")
    os.environ.setdefault("VOTEBAN_THRESHOLD", "7")
    os.environ.setdefault("VOTEBAN_FORGIVE_THRESHOLD", "7")
    os.environ.setdefault("CAPTCHA_MAX_ATTEMPTS", "3")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chat-id", required=True, help="Target Telegram chat id, e.g. -1001234567890")
    parser.add_argument("--export", required=True, dest="export_path", type=Path, help="Telegram Desktop result.json")
    parser.add_argument("--since", default="2026-01-01", help="Import messages from this date, YYYY-MM-DD")
    parser.add_argument("--until", help="Optional inclusive end date, YYYY-MM-DD")
    parser.add_argument("--table-name", help="Memory DynamoDB table name. Required with --apply.")
    parser.add_argument("--queue-url", help="SQS queue URL for vector indexing tasks.")
    parser.add_argument("--aws-region", default=os.environ.get("AWS_DEFAULT_REGION", "eu-central-1"))
    parser.add_argument("--apply", action="store_true", help="Write to DynamoDB. Default is dry-run only.")
    parser.add_argument("--max-messages", type=int, help="Limit parsed messages for a small test run.")
    parser.add_argument("--no-raw-messages", action="store_true", help="Do not store raw MSG# records/user profiles.")
    parser.add_argument("--no-long-term", action="store_true", help="Do not extract EVENT/USER_FACT/GROUP_FACT/JOKE.")
    parser.add_argument("--no-daily-summaries", action="store_true", help="Do not create DAILY_SUMMARY items.")
    parser.add_argument("--no-vector-enqueue", action="store_true", help="Do not enqueue vector indexing tasks.")
    parser.add_argument(
        "--vectorize-daily-summaries",
        action="store_true",
        help="Also enqueue imported DAILY_SUMMARY items for vector indexing after inspecting summary quality.",
    )
    return parser.parse_args()


def _make_vector_enqueue(queue_url: str | None):
    if not queue_url:
        return None
    from services.repositories.sqs import SQSClient

    sqs = SQSClient()
    return sqs.send_vector_memory_task


def main() -> int:
    args = _parse_args()
    if args.apply and not args.table_name:
        raise SystemExit("--table-name is required with --apply")
    if args.apply and not args.no_vector_enqueue and not args.queue_url:
        raise SystemExit("--queue-url is required with --apply unless --no-vector-enqueue is set")

    _prepare_import_path()
    _seed_required_env(args)

    from services.history_import import HistoryImportOptions, import_telegram_history
    from services.repositories.group_memory import GroupMemoryRepository

    repo = GroupMemoryRepository(table_name=args.table_name) if args.apply else None
    vector_enqueue = None if args.no_vector_enqueue else _make_vector_enqueue(args.queue_url)
    options = HistoryImportOptions(
        chat_id=args.chat_id,
        export_path=args.export_path,
        since=date.fromisoformat(args.since),
        until=date.fromisoformat(args.until) if args.until else None,
        dry_run=not args.apply,
        store_raw_messages=not args.no_raw_messages,
        extract_long_term=not args.no_long_term,
        create_daily_summaries=not args.no_daily_summaries,
        enqueue_vectors=not args.no_vector_enqueue,
        vectorize_daily_summaries=args.vectorize_daily_summaries,
        max_messages=args.max_messages,
    )

    result = import_telegram_history(options, repo=repo, vector_enqueue=vector_enqueue)
    print(json.dumps(_compact_result(result.as_dict()), ensure_ascii=False, indent=2))
    return 0


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    daily_counts = result.get("daily_message_counts") or {}
    result["daily_message_counts"] = {
        "days": len(daily_counts),
        "total_messages": sum(int(value) for value in daily_counts.values()),
        "first_10_days": dict(list(daily_counts.items())[:10]),
    }
    return result


if __name__ == "__main__":
    raise SystemExit(main())
