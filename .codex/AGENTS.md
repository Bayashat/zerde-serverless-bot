# AGENTS.md

This file guides Codex when working in this repository. Keep it current with `docs/ARCHITECTURE.md` and `.codex/skills/zerdebot-development/SKILL.md`.

## Commands

```bash
# Install dependencies
uv sync --frozen

# Validate Python behavior
uv run pytest tests/ -q
uv run pre-commit run --all-files

# Validate CDK infrastructure
cd infra && uv run cdk synth -c env=dev
cd infra && uv run cdk diff -c env=dev

# Deploy / destroy
cd infra && uv run cdk deploy -c env=dev
cd infra && uv run cdk destroy -c env=dev
```

When changing `infra/`, include meaningful `cd infra && uv run cdk diff -c env=dev` output in PR notes. If the diff is only environment config such as `CHAT_LANG_MAP`, say that explicitly.

## Git Workflow

- Create new work branches with conventional prefixes such as `feat/`, `fix/`, `docs/`, `chore/`, `refactor/`, or `test/`.
- Do not use `codex/` as a branch prefix in this repository.
- Use conventional commit-style commit and PR titles, for example `feat: improve RAG memory grounding` or `fix: scope self-reference retrieval`.
- Do not include `codex` or `[codex]` in commit messages or PR titles.

## Product Direction

ZerdeBot started as a simple serverless Telegram bot and LLM wrapper. It is now a **memory-enabled agentic Telegram group bot**:

- It observes opted-in group messages.
- It stores recent context, user profiles, long-term memory, daily summaries, and agent reply metadata in DynamoDB.
- It extracts long-term memory with cheap local candidate gates, bounded structured Gemini extraction, and rule-based fallback when Gemini is unavailable, disabled, over budget, or not warranted.
- It indexes long-term memory and high-information daily summaries in S3 Vectors for semantic RAG retrieval.
- It answers `/ask`, @mentions, and reply-to-bot follow-ups through a retrieval pipeline that gathers requester, profile, recent, long-term, and semantic context from a compact retrieval query that is separate from the full Gemini generation prompt.
- Reply-thread follow-ups carry the captured quoted source message, previous user request, and previous bot answer when available for generation, while semantic retrieval uses a shorter query based on the current follow-up, previous user request, and original source message.
- It may proactively answer only after a short delayed candidate window plus conservative local and LLM social-timing gates.
- It still supports captcha, anti-spam, voteban, daily news, and quizzes.

RAG is one capability inside the agent. Do not treat vector search as the only source of truth; requester identity, recent context, target-user profiles, reply-thread context, and query-filtered long-term memory are also part of the answer path.

## Architecture

```mermaid
flowchart LR
  Telegram[Telegram_groups] --> APIGW[HTTP_API_Gateway]
  APIGW --> BotLambda[Bot_Lambda_webhook_and_main_SQS_worker]
  MainQ[SQS_timeout_tasks_queue] --> BotLambda
  VectorQ[SQS_vector_memory_queue] --> VectorIndexer[Vector_Indexer_Lambda]
  BotLambda --> MainQ
  BotLambda -- "enqueue vector tasks" --> VectorQ
  BotLambda --> Stats[(DynamoDB_stats)]
  BotLambda --> Memory[(DynamoDB_group_memory)]
  BotLambda -- "query/delete" --> S3Vectors[S3_Vectors_memory_index]
  BotLambda --> Gemini[Gemini]
  BotLambda --> Groq[Groq]
  VectorIndexer -- "backfill fan-out" --> VectorQ
  VectorIndexer --> Stats
  VectorIndexer --> Memory
  VectorIndexer -- "index/backfill" --> S3Vectors
  VectorIndexer --> Gemini
  EventBridge[EventBridge_schedules] --> NewsLambda[News_Lambda]
  EventBridge --> QuizLambda[Quiz_Lambda]
  Layer[zerde_common_layer] -.-> BotLambda
  Layer -.-> VectorIndexer
  Layer -.-> NewsLambda
  Layer -.-> QuizLambda
```

| Lambda | Package | Entry | Purpose |
|--------|---------|-------|---------|
| Bot | `src/bot/` | `main.py:lambda_handler` | API Gateway webhook and main SQS worker. Handles captcha, voteban, spam, `/ask`, agent replies, group memory, semantic retrieval, and cleanup commands. |
| Vector indexer | `src/bot/` | `vector_indexer_main.py:lambda_handler` | Dedicated vector memory queue consumer for `PROCESS_VECTOR_MEMORY` and `PROCESS_VECTOR_MEMORY_BACKFILL`. |
| News | `src/news/` | `main.py:lambda_handler` | Scheduled IT news digest. |
| Quiz | `src/quiz/` | `main.py:lambda_handler` | Scheduled and on-demand quiz workflow. |

Detailed architecture lives in `docs/ARCHITECTURE.md`.

## Bot Package Map

- `main.py` — detects API Gateway vs main SQS tasks and delegates.
- `vector_indexer_main.py` — consumes only vector memory SQS tasks.
- `app.py` — lazy wiring for Telegram client, dispatcher, captcha repo, and memory repo.
- `webhook.py` — verifies Telegram secret, screens spam, observes memory, filters irrelevant events, routes agent/commands.
- `services/sqs_task_router.py` — routes main and vector SQS task families and re-raises failures for retry/DLQ semantics.
- `services/group_memory.py` — stores recent group context, formats prompt context, requester/target-user profile context, and query-filtered long-term memory.
- `services/memory_retrieval.py` — Memory Retrieval Pipeline V1 for query intent, raw candidate retrieval, local scoring/dedupe, candidate-driven prompt packing, and source tracking.
- `services/memory_extractor.py` — structured long-term memory schema, Gemini extraction normalisation, rule fallback, and storage guards.
- `services/group_memory_processor.py` — async long-term extraction task orchestration, cheap Gemini candidate gating, extractor LLM budgets, and daily summaries.
- `services/group_agent.py` — agent trigger policy, proactive gating, reply-thread continuity, answer-length policy.
- `services/vector_memory.py` — embedding, S3 Vectors indexing, semantic retrieval, cleanup/backfill.
- `services/repositories/group_memory.py` — DynamoDB single-table layout for settings, messages, profiles, long-term memory, agent replies, vector status, proactive counters, and targeted memory deletion helpers.
- `services/ai/gemini_client.py` — Gemini calls for agent answers, proactive decisions, summaries, embeddings.
- `services/spam/` — rule-based spam screening plus Groq async checks.

## Memory Table

Single table partitioned by `pk=CHAT#<chat_id>`:

- `SETTINGS` — memory/agent flags.
- `MSG#<created_at_ms>#<message_id>` — recent non-command group messages.
- `USER#<user_id>` — profile from the user's own messages only.
- `USERNAME#<lower_username>` — per-chat username alias pointing to `USER#<user_id>` for direct target-profile lookup.
- `EVENT#...`, `USER_FACT#...`, `GROUP_FACT#...`, `JOKE#...` — long-term memories. Durable `JOKE#`
  items require high-confidence Gemini extraction or repeated evidence so one-off jokes do not over-pollute retrieval.
- `DAILY_SUMMARY#YYYY-MM-DD` — compressed daily group memory.
- `TERM#<term>#<created_at_ms>#<source_sk>` — bounded exact-term lexical index rows for long-term memories and daily summaries.
- `AGENT_REPLY#<bot_message_id>` — bot answer text, triggering/current user message, optional quoted source-message context, parent bot message id, requester metadata, retrieval source metadata, and reason for reply-thread continuity, `/agent why`, `/agent wrong`, `/memory wrong`, and `/memory forget this`.
- `VECTOR_BACKFILL` — vector backfill status.
- `PROACTIVE#YYYYMMDD` — daily proactive reply reservation counter.

Memory items include feedback/consolidation metadata such as `wrong_feedback_count`, `negative_feedback_count`,
`last_feedback_at`, `feedback_status`, and `superseded_by`.

Vectorizable prefixes are `EVENT#`, `USER_FACT#`, `GROUP_FACT#`, `JOKE#`, and high-information `DAILY_SUMMARY#` items. Fallback or empty live daily summaries stay in DynamoDB but are not enqueued for vector indexing.
Indexed memory items also carry `vector_document_hash`, `vector_schema_version`, `vector_embedding_model`, and `vector_dimensions` so duplicate SQS deliveries can skip unchanged items and future embedding migrations can redrive stale records explicitly.

Memory TTLs are type-specific: raw `MSG#...`, `AGENT_REPLY#...`, long-term memory, `DAILY_SUMMARY#...`, and `PROACTIVE#...` counters use their own retention env vars. `MSG#...`, long-term memory, and `DAILY_SUMMARY#...` fall back to `GROUP_MEMORY_RETENTION_DAYS` when omitted; `AGENT_REPLY#...` and `PROACTIVE#...` keep their existing short defaults unless explicitly configured. Long-term `expires_in_days` still records `expires_at` and uses the shorter DynamoDB TTL.

## SQS Tasks

- `CHECK_TIMEOUT` — captcha timeout enforcement.
- `SPAM_CHECK` — async Groq spam decision.
- `PROCESS_GROUP_ASK` — async explicit `/ask` answer.
- `PROCESS_PROACTIVE_CANDIDATE` — delayed proactive final check after humans have had time to answer.
- `PROCESS_GROUP_MEMORY` — extract/store long-term memory from one message using structured Gemini extraction with rule fallback.
- `PROCESS_DAILY_GROUP_SUMMARIES` — daily summaries for configured groups.
- `PROCESS_VECTOR_MEMORY` — embed/index one memory item; consumed by the vector-indexer Lambda.
- `PROCESS_VECTOR_MEMORY_BACKFILL` — page through vectorizable memory and enqueue indexing; consumed by the vector-indexer Lambda.

## Secrets And Config

- Deploy-time `.env` is loaded by `infra/stack.py` for non-secret CDK config and local runs.
- Runtime secrets live in SSM Parameter Store under `SSM_SECRET_PREFIX`, for example `/zerde/prod/bot-token`.
- Bot Lambda env names are `BOT_TOKEN`, `WEBHOOK_SECRET_TOKEN`, `GEMINI_API_KEY`, `GEMINI_EMBEDDING_API_KEY`, `GROQ_API_KEY`, and `DEEPSEEK_API_KEY`; avoid old informal names such as `TELEGRAM_BOT_TOKEN`.
- Telegram BotFather privacy mode must be disabled, or the bot must be an admin, for full group context.

## Key Design Decisions

- **No SnapStart**: low-frequency workloads and Python package trade-offs make SnapStart unnecessary here.
- **Bot Lambda for webhook and main SQS only**: `/ask`, spam, captcha, and memory extraction share the bot warm path.
- **Separate vector indexer Lambda and vector queue**: slower embedding/backfill/S3 Vectors work has independent concurrency, logs, alarms, and DLQ visibility so it does not block webhook or interactive `/ask` work.
- **Trust hierarchy for agent answers**: current user message and reply-thread context > requester profile for self-reference > target user's own profile > query-matched vector memory > query-filtered long-term memory > recent group chatter.
- **Prompt pollution control**: do not inject unfiltered recent long-term memories into answers; filter by query or use vector retrieval.
- **Vector retrieval discipline**: use chat metadata filters, requester filters for self-reference when available, and distance cutoffs before adding semantic memories to prompts.
- **Memory Retrieval Pipeline V1**: `services.memory_retrieval.build_agent_memory_context` retrieves profile, semantic, lexical, long-term, and recent candidates from `retrieval_query`, scores/dedupes them locally, renders prompt sections only from selected top candidates, and persists compact metadata for the selected retrieval sources used by `/agent why` and wrong-source feedback. Username target profiles use `USERNAME#...` aliases, exact lexical retrieval uses `TERM#...` index rows before falling back to recent legacy candidates, and negative feedback on a source lowers its future retrieval score.
- **Intent-aware retrieval filters**: obvious self-reference and target-user questions narrow semantic/lexical memory to user facts; group-decision questions narrow to group facts and daily summaries; past-event questions narrow to events and daily summaries; joke/meme questions narrow to jokes and daily summaries.
- **User-facing memory controls**: `/memory about me` shows only the current user's own profile. `/memory forget this` deletes memory tied to a replied bot answer's recorded source keys or a replied source message, with vector cleanup when configured. `/agent wrong` and `/memory wrong` mark a replied bot answer's recorded memory sources as wrong without deleting them. Regular users can delete only their own memory; the group owner or bot owner can delete group memory.
- **Memory extraction budget**: default `GROUP_MEMORY_EXTRACTOR_MODE=gemini_candidate_only` means ordinary safe chatter falls back to rules without calling Gemini. `GROUP_MEMORY_EXTRACTOR_DAILY_LLM_LIMIT` and `GROUP_MEMORY_EXTRACTOR_PER_CHAT_DAILY_LIMIT` bound candidate Gemini extraction before it can consume shared generate RPD.
- **Memory safety filters**: never learn or prompt with future-answer directives such as "when someone asks X, answer Y", self-promotion, or subjective people rankings such as "best in the chat" / "strongest developer".
- **S3 Vectors IAM**: metadata-filtered queries and `returnMetadata=True` require both `s3vectors:QueryVectors` and `s3vectors:GetVectors`. Bot Lambda can query, get index metadata, and delete vectors for cleanup; `PutVectors` and `ListVectors` stay scoped to the vector-indexer Lambda.
- **Reply-thread control**: follow-up replies should stay short and should only continue when the reply-to-bot message is a clear question or request; reactions, thanks, laughter, and short comments stay silent.
- **Proactive prefiltering**: suppress bot-behavior meta chatter and stop cues, but do not treat generic technical/product mentions of "bot"/"бот" as bot-meta. Score multilingual technical, suggestion, and group-request cues across Kazakh, Russian, English, and Chinese, and log structured local prefilter skips for open-question candidates. Queue passing candidates with `AGENT_PROACTIVE_DELAY_SECONDS`, then re-read post-trigger context and stay silent if humans already answered sufficiently.
- **Gemini empty responses**: HTTP 200 responses without candidate text are non-retryable for interactive `/ask`; log safe response-shape fields such as block reason, finish reason, and candidate counts, then notify the user without requeueing.
- **Structured logging**: use `zerde_common` and avoid logging full prompts, model responses, API keys, Telegram files, or user secrets.
- **Vector observability**: retrieval and indexing success paths emit INFO logs with counts, filters, distance cutoffs, and vector dimensions; do not rely only on ERROR logs to confirm vector health.

## Documentation Maintenance

When making a large change to architecture, memory, agent behavior, SQS tasks, data schemas, environment variables, or infrastructure:

1. Update `docs/ARCHITECTURE.md`.
2. Update this file.
3. Update `.codex/skills/zerdebot-development/SKILL.md`.
4. Update `README.md`, `docs/README_kk.md`, and `docs/README_ru.md` when user-visible behavior changes.
5. Update `docs/LOCAL_TESTING.md` and `.env.example` when setup/config changes.
6. Update `docs/telegram_history_import.md` when import or vector indexing behavior changes.

Historical documents under `docs/superpowers/` are plan snapshots, not current architecture references.
