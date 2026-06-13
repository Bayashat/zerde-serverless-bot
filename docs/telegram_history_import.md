# Telegram History Import

Use this for one-time import of Telegram Desktop JSON exports into ZerdeBot group memory and RAG retrieval.

The importer is for bootstrapping memory when Telegram cannot give the bot old group history. It writes DynamoDB memory items first, then optionally enqueues vector indexing on the vector-memory SQS queue so the dedicated vector-indexer Lambda can index historical facts into S3 Vectors.

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

The report shows parsed messages, skipped sensitive/command/service messages, estimated long-term memories, daily summaries, and vector tasks. Review this before writing because imported memory can influence future agent answers.

## Import

When the dry-run looks right, run with `--apply`:

```bash
uv run python dev/tools/import_telegram_history.py \
  --chat-id -1001234567890 \
  --export ~/Downloads/Telegram/result.json \
  --since 2026-01-01 \
  --table-name zerde-serverless-bot-memory-dev \
  --queue-url https://sqs.eu-central-1.amazonaws.com/123456789012/zerde-serverless-vector-memory-tasks-queue-dev \
  --apply
```

Repeat once per group/export file.

`--queue-url` must be the vector-memory queue URL. The main timeout/tasks queue is for Bot Lambda work such as captcha, spam, `/ask`, group memory extraction, and daily summaries.

## What Gets Imported

- `MSG#...` raw text records for non-sensitive messages, with `USER#...` profile updates derived from the speaker's own text.
- `EVENT#...`, `USER_FACT#...`, `GROUP_FACT#...`, and `JOKE#...` long-term memory items.
- `DAILY_SUMMARY#YYYY-MM-DD` summaries for each imported day.
- `TERM#...` lexical index rows for a bounded set of exact terms on long-term memory items and daily summaries.
- `PROCESS_VECTOR_MEMORY` tasks on the vector-memory queue for each long-term memory item.

The importer skips commands, empty/system messages, and secret/sensitive-looking content. It does not embed every raw message directly; only long-term memory items go to S3 Vectors by default, and the vector-indexer Lambda performs that embedding/indexing work.

By default, imported `DAILY_SUMMARY#...` items are stored in DynamoDB but not vectorized, because generic import summaries are low-information retrieval candidates. Use `--vectorize-daily-summaries` only after inspecting summary quality.

Imported long-term memory is later used by `/ask` and proactive agent replies through a mix of query-filtered DynamoDB reads, exact-term `TERM#...` lexical lookup, and semantic vector retrieval. Keep joke-like or sarcastic memories narrow; a one-off roast should not become a permanent user fact.

## Useful Options

- `--max-messages 1000` for a small smoke test.
- `--until YYYY-MM-DD` to limit the date range.
- `--no-vector-enqueue` to import DynamoDB memory without queueing embeddings.
- `--vectorize-daily-summaries` to also enqueue imported `DAILY_SUMMARY#...` items for embeddings after inspection.
- `--no-raw-messages` to skip raw `MSG#...` records and user profile updates.
- `--no-long-term` to skip event/fact/joke extraction.
- `--no-daily-summaries` to skip daily summaries.

If you import with `--no-vector-enqueue`, run a vector backfill later before expecting semantic retrieval to find long-term history. Imported daily summaries should stay out of semantic retrieval unless you have inspected them and decided they are useful.

## Cleanup And Pollution Control

Before importing a large group, do a small `--max-messages` dry run and inspect whether user facts, group facts, and jokes look trustworthy. If polluted records are written, clean both sides of memory:

- Delete the narrow DynamoDB keys for bad `USER#...`, `USER_FACT#...`, `GROUP_FACT#...`, `JOKE#...`, or `DAILY_SUMMARY#...` items.
- Delete matching vector keys for vectorized long-term memory and any explicitly vectorized daily summaries.
- Back up the exact items and vector keys before production cleanup.

Do not rely on vector backfill to fix bad source data. If DynamoDB memory is polluted, the agent can still retrieve it through non-vector long-term context.
