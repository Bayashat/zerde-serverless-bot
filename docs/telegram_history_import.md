# Telegram History Import

Use this for one-time import of Telegram Desktop JSON exports into ZerdeBot group memory.

## Export

In Telegram Desktop, open a group, choose **Export chat history**, and export JSON. Media files are not needed for the first import pass; text-only JSON is enough.

Suggested groups:

- `@timurdaninfochat` from `2026-01-01`
- `@amanchikworld` from `2026-01-01`
- `@kz_it_chat` from `2026-01-01`

The bot cannot fetch old Telegram history itself. This importer uses the JSON exported by your own Telegram account.

## Dry Run

Run dry-run first. It does not write DynamoDB or enqueue SQS.

```bash
uv run python dev/tools/import_telegram_history.py \
  --chat-id -1001234567890 \
  --export ~/Downloads/Telegram/result.json \
  --since 2026-01-01
```

The report shows parsed messages, skipped sensitive/command/service messages, estimated long-term memories, daily summaries, and vector tasks.

## Import

When the dry-run looks right, run with `--apply`:

```bash
uv run python dev/tools/import_telegram_history.py \
  --chat-id -1001234567890 \
  --export ~/Downloads/Telegram/result.json \
  --since 2026-01-01 \
  --table-name zerde-serverless-bot-memory-dev \
  --queue-url https://sqs.eu-central-1.amazonaws.com/123456789012/zerde-serverless-timeout-tasks-queue-dev \
  --apply
```

Repeat once per group/export file.

## What Gets Imported

- `MSG#...` raw text records for non-sensitive messages, with user profile updates.
- `EVENT#...`, `USER_FACT#...`, `GROUP_FACT#...`, and `JOKE#...` long-term memory items.
- `DAILY_SUMMARY#YYYY-MM-DD` summaries for each imported day.
- `PROCESS_VECTOR_MEMORY` tasks for each long-term memory and daily summary.

The importer skips commands, empty/system messages, and secret/sensitive-looking content. It does not embed every raw message directly; only long-term memory items and daily summaries go to S3 Vectors.

## Useful Options

- `--max-messages 1000` for a small smoke test.
- `--until YYYY-MM-DD` to limit the date range.
- `--no-vector-enqueue` to import DynamoDB memory without queueing embeddings.
- `--no-raw-messages` to skip raw `MSG#...` records and user profile updates.
- `--no-long-term` to skip event/fact/joke extraction.
- `--no-daily-summaries` to skip daily summaries.
