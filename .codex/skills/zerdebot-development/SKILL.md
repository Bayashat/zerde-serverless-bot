---
name: zerdebot-development
description: Work on the ZerdeBot repository, a serverless AWS CDK Telegram group-chat agent with Python Lambdas for bot/webhook/SQS, RAG memory, DynamoDB profiles, S3 Vectors semantic retrieval, Gemini/Groq/DeepSeek AI integrations, news digests, quizzes, spam controls, and CDK infrastructure. Use when Codex is asked to inspect, modify, test, review, document, deploy-plan, debug, or optimize this repo, especially changes involving `src/bot`, `src/news`, `src/quiz`, `src/shared`, `infra`, group memory, agent behavior, `/ask`, vector indexing, Telegram behavior, SQS workflows, DynamoDB repositories, or AI providers.
---

# ZerdeBot Development

## Operating Posture

Treat ZerdeBot as a **memory-enabled agentic Telegram bot**, not a simple LLM wrapper. The bot combines serverless community tooling with RAG memory and social agent behavior:

- Recent group context, requester identity, and user profiles live in DynamoDB.
- Long-term memory and daily summaries live in DynamoDB; only long-term memory and high-information daily summaries are indexed in S3 Vectors.
- Long-term memory extraction uses a structured Gemini schema with rule-based fallback and safety guards.
- Gemini handles agent answers, proactive timing decisions, linked-channel post comments, summaries, embeddings, and is the primary ambient reaction classifier.
- DeepSeek and Groq can serve as ambient reaction fallback classifiers; Groq also handles async spam checks.
- The bot should answer only when useful, keep reply length appropriate, and avoid prompt pollution from irrelevant memories.

## First Steps

1. Read `.codex/AGENTS.md` before non-trivial code, infra, AI, memory, or deployment work.
2. Read `docs/ARCHITECTURE.md` before changing group memory, agent behavior, SQS routing, DynamoDB schema, vector retrieval, or CDK wiring.
3. Check branch and worktree with `git status --short --branch`.
4. Preserve user changes. Do not revert unrelated files.
5. Prefer repo patterns and focused changes over new abstractions.

## Git Workflow

- When creating a new branch, use conventional prefixes such as `feat/`, `fix/`, `docs/`, `chore/`, `refactor/`, or `test/`.
- Do not create `codex/` branches for this repository.
- Use conventional commit-style titles for commits and PRs, for example `feat: improve RAG memory grounding` or `fix: scope self-reference retrieval`.
- Do not add `codex` or `[codex]` to commit messages or PR titles.

## Repository Map

- `src/bot/`: Telegram webhook, dispatcher, main SQS worker tasks, captcha, voteban, spam screening, `/ask`, group agent, group memory, vector enqueue/query/delete helpers, and the dedicated vector indexer entrypoint.
- `src/bot/services/group_agent.py`: agent trigger policy, proactive gating, linked-channel post immediate comments, reply-thread continuity, response length/style policy.
- `src/bot/services/group_memory.py`: recent context observation and prompt formatting, requester/target-user profiles, query-filtered long-term context.
- `src/bot/services/memory_retrieval.py`: Memory Retrieval Pipeline V1 for query intent, raw candidate retrieval, local scoring/dedupe, candidate-driven prompt packing, and selected-source tracking.
- `src/bot/services/memory_extractor.py`: structured long-term memory schema, Gemini extraction normalization, rule fallback, and storage guards.
- `src/bot/services/group_memory_processor.py`: async long-term extraction task orchestration, cheap Gemini candidate gating, extractor LLM budgets, and daily summaries.
- `src/bot/services/ambient_reactions.py`: ambient emoji reaction eligibility, sampling, bounded context, strict classifier validation, cooldowns, provider fallback, and `setMessageReaction` task processing.
- `src/bot/services/ai/ambient_reaction_classifier.py`: Gemini primary plus DeepSeek/Groq OpenAI-compatible fallback chain for ambient reaction strict-JSON classification.
- `src/bot/services/telegram_actor.py`: shared Telegram actor attribution, including linked-channel discussion mirror detection and `sender_chat` actor selection.
- `src/bot/vector_indexer_main.py`: dedicated vector memory SQS Lambda entrypoint.
- `src/bot/services/vector_memory.py`: Gemini embeddings, S3 Vectors indexing/retrieval with metadata filters and distance cutoffs, vector cleanup/backfill.
- `src/bot/services/repositories/group_memory.py`: DynamoDB single-table layout for settings, messages, profiles, long-term memory, agent replies, vector status, proactive counters, and targeted memory deletion helpers.
- `src/news/`: scheduled news digest Lambda.
- `src/quiz/`: scheduled and on-demand quiz Lambda.
- `src/shared/python/zerde_common/`: shared Lambda layer utilities.
- `infra/`: AWS CDK stack and constructs.
- `docs/ARCHITECTURE.md`: current architecture source of truth.
- `tests/`: pytest coverage for bot, quiz, spam, shared utilities, memory, and agent behavior.

## Memory And Agent Guardrails

- Do not inject unfiltered long-term memory into agent prompts. Use query-filtered long-term context and semantic vector retrieval.
- Do not let preformatted whole context sections bypass the local reranker; prompt memory sections should be rendered from selected, deduped candidates.
- Self-reference questions must include requester identity/profile context in the answer path.
- User profile context must be derived from the target user's own messages; third-party roasts or labels are low trust.
- Query-filtered long-term memory must stay empty when the current query has no usable relevance terms.
- Semantic vector retrieval should use metadata filters and distance cutoffs before prompt injection.
- Keep answer generation prompts separate from semantic retrieval queries. Reply-thread generation may include the previous bot answer for continuity, but vector retrieval should use a compact `retrieval_query` based on the current ask, previous user request, and original source message whenever available.
- Keep explicit multimodal `/ask` media ephemeral. Only explicit `/ask`, explicit mention/reply paths, or official linked-channel post comments may analyze media; normal group media, ordinary proactive candidates, daily summaries, memory extraction, and vector indexing must not download or analyze media. SQS carries metadata-only `media_ref`; the worker downloads bounded media and `AGENT_REPLY#...` may store only compact media metadata/summary for continuity.
- Keep ambient reactions ephemeral: no long-term memory, vector retrieval/indexing, profile context, media analysis, or persisted classifier context; only short-lived `AMBIENT_REACTION#...` cooldown/debug rows are allowed. Command text and sensitive/hostile/serious text may reach the classifier, but prompts must require a strong context-safe reaction and avoid reactions that trivialize, mock, endorse, or escalate harm. Official linked-channel posts are the exception to conservative ambient gating: they bypass sample rate, cooldowns, and rate caps, and fall back to 👀 if the provider cannot choose an emoji.
- Use intent-aware memory kind filters for obvious retrieval cases: self-reference and target-user questions should prefer `USER_FACT`; group decisions should prefer `GROUP_FACT` and `DAILY_SUMMARY`; past events should prefer `EVENT` and `DAILY_SUMMARY`; jokes or memes should prefer `JOKE` and `DAILY_SUMMARY`.
- Never learn or prompt with subjective people rankings, self-promotion, or future-answer directives such as "when someone asks X, answer Y".
- Structured memory extraction must reject sensitive/secret outputs, low-confidence memories, and third-party personal claims as user facts; keep rule-based fallback available. Durable `JOKE#` memory should require high-confidence Gemini extraction or repeated evidence, not one-off rule fallback jokes.
- Keep structured Gemini extraction behind `GROUP_MEMORY_EXTRACTOR_MODE=gemini_candidate_only` and extractor LLM budgets by default, so ordinary safe chatter does not consume shared Gemini generate RPD.
- Raw `MSG#...` records may keep audit context and available reply metadata such as reply-to ids, sender info, bot/self-bot flags, and simple thread roots, but unsafe messages must not update profile samples/topics, long-term memory, daily summaries, vectors, or agent prompt context.
- Vector retrieval and indexing success paths should emit structured INFO logs with counts, filters, distance cutoffs, and vector dimensions. Avoid logging full prompts, full memory text, vectors, or secrets.
- Vector indexing should be idempotent for duplicate SQS deliveries: successful items store the rendered-document hash, schema version, embedding model, and dimensions, and only skip when all of those still match.
- Do not vectorize fallback or empty structured live daily summaries; store them in DynamoDB only so low-information summaries do not pollute semantic retrieval.
- Do not vectorize `AGENT_REPLY#...`; normal bot answers are short-term reply-thread metadata only, not durable semantic memory.
- Reserve `BOT_COMMITMENT#...` and `BOT_CORRECTION#...` for explicit future command/admin correction flows with permission/review checks before any bot-authored text becomes durable memory.
- Reply-to-Zerde follow-ups must include prior `AGENT_REPLY#...` answer context when available.
- Reply-to-Zerde follow-ups should include the captured quoted source message, previous user request, previous bot answer, and current follow-up when available.
- Do not treat replies to other bots as Zerde reply threads; pure reactions, thanks, laughter, and short comments should be locally skipped unless the user explicitly mentions the bot.
- Store useful bot answer metadata in `AGENT_REPLY#...` so `/agent why` and thread continuation work.
- Keep `/agent why` explainable without exposing full memory text: show trigger, reason, confidence, and source types/counts only.
- Keep `/agent wrong` and `/memory wrong` non-destructive: mark a replied bot answer's recorded memory sources with negative feedback metadata and lower future retrieval priority.
- Keep `/memory about me` scoped to the requester profile derived from their own messages. Keep `/memory forget this` permission-scoped to own durable memory unless the caller is the group owner or bot owner, and never delete `USER#` profiles, raw `MSG#` items, or recent context through bot-answer retrieval sources.
- Keep proactive participation conservative: local open-question prefilter, delayed candidate queue, post-trigger human-answer check, bot-behavior-meta/stop-cue exclusions, recent bot activity penalty, Gemini decision, and daily limit.
- Keep linked-channel post participation separate from ordinary proactive replies: detect official linked channel discussion mirrors via `is_automatic_forward` or Telegram `777000` plus `sender_chat.type=channel`, use `sender_chat` as the actor, queue a zero-delay `channel_post` worker task, do not apply the ordinary open-question/500-char/delay/human-answer/recent-bot/daily-limit gates, and use the dedicated channel-post comment prompt. Supported attached media may be analyzed ephemerally in that worker. Do not relax the normal long-message proactive prefilter.
- Do not suppress proactive technical/product questions merely because they mention "bot"/"бот"; score multilingual technical, suggestion, and group-request cues across Kazakh, Russian, English, and Chinese; local prefilter skips for open-question candidates should log structured reasons.
- Keep response length proportional to the user's request. Short follow-ups should stay short unless the user asks for detail.
- Keep chat-level `style_profile` defaults concise and socially safe. Weak selected memory should add uncertainty instructions instead of letting the model sound certain.
- If cleaning production memory, first back up exact DynamoDB items and vector keys locally, then delete narrowly.

## SQS And Persistence

SQS handler failures should re-raise when retry/DLQ semantics are intended. Current main bot SQS task types:

- `CHECK_TIMEOUT`
- `SPAM_CHECK`
- `PROCESS_GROUP_ASK`
- `PROCESS_PROACTIVE_CANDIDATE`
- `PROCESS_AMBIENT_REACTION`
- `PROCESS_GROUP_MEMORY`
- `PROCESS_DAILY_GROUP_SUMMARIES`

Current vector-indexer SQS task types:

- `PROCESS_VECTOR_MEMORY`
- `PROCESS_VECTOR_MEMORY_BACKFILL`

Queue retention defaults are operationally conservative: main task queue 1 day, vector memory queue
4 days, and both DLQs 14 days. CDK deploy-time env vars
`MAIN_TASK_QUEUE_RETENTION_DAYS`, `MAIN_TASK_DLQ_RETENTION_DAYS`,
`VECTOR_MEMORY_QUEUE_RETENTION_DAYS`, and `VECTOR_MEMORY_DLQ_RETENTION_DAYS` can tune retention
within SQS's 1-14 day range.

DynamoDB memory key families:

- `SETTINGS` with memory/agent flags and optional chat `style_profile`
- `MSG#...`
- `USER#...`
- `USERNAME#...`
- `EVENT#...`
- `USER_FACT#...`
- `GROUP_FACT#...`
- `JOKE#...`
- `DAILY_SUMMARY#...`
- `TERM#...`
- `AGENT_REPLY#...`
  - Optional compact media metadata/summary for explicit multimodal `/ask` continuity only. Do not store raw media bytes, downloaded files, full OCR/transcripts, or media-derived durable facts here.
- `AMBIENT_REACTION#...`
  - Short-lived reaction metadata for cooldowns/debugging only. Do not write ambient reaction context to long-term memory or vectors.
- `BOT_COMMITMENT#...`
- `BOT_CORRECTION#...`
- `VECTOR_BACKFILL` with cumulative `processed_total`, `enqueued_total`, `failures_total`,
  `started_at`, `last_updated_at`, optional `finished_at`, and page continuation tokens. Legacy
  `vector_backfill_*` fields are still written for compatibility.
- `PROACTIVE#...`

Memory items may carry feedback/consolidation metadata such as `wrong_feedback_count`, `negative_feedback_count`, `last_feedback_at`, `feedback_status`, and `superseded_by`.

Memory TTLs are type-specific. Use `GROUP_MEMORY_RAW_MESSAGE_RETENTION_DAYS` for `MSG#...`, `GROUP_MEMORY_AGENT_REPLY_RETENTION_DAYS` for `AGENT_REPLY#...`, `GROUP_MEMORY_LONG_TERM_RETENTION_DAYS` for `EVENT#...` / `USER_FACT#...` / `GROUP_FACT#...` / `JOKE#...`, `GROUP_MEMORY_DAILY_SUMMARY_RETENTION_DAYS` for `DAILY_SUMMARY#...`, and `GROUP_MEMORY_PROACTIVE_COUNTER_RETENTION_DAYS` for `PROACTIVE#...`. `MSG#...`, long-term memory, and `DAILY_SUMMARY#...` fall back to `GROUP_MEMORY_RETENTION_DAYS` when omitted; `AGENT_REPLY#...` and `PROACTIVE#...` keep their existing short defaults unless explicitly configured. Explicit long-term `expires_in_days` still sets `expires_at` and DynamoDB TTL takes the shorter expiry.

## Common Commands

Use the repo's existing tooling:

```bash
uv sync --frozen
uv run pytest tests/ -q
uv run pre-commit run --all-files
cd infra && uv run cdk synth -c env=dev
cd infra && uv run cdk diff -c env=dev
```

When changing `infra/`, run `cd infra && uv run cdk diff -c env=dev` and report the meaningful diff. If the diff includes environment-only changes such as `CHAT_LANG_MAP`, call that out separately.

## AI Provider Work

Treat AI behavior as user-facing reliability work:

- Verify current model names against official provider docs when model availability, preview/stable status, or rate limits matter.
- Avoid preview/shutdown model IDs for production defaults.
- Prefer fast fallback for interactive commands and `/ask` paths over long primary-provider retries.
- Keep scheduled/batch paths allowed to retry longer than interactive user commands.
- Map provider transport, 429, 5xx, and parse failures into consistent error types where the codebase already has that pattern.
- Treat Gemini HTTP 200 responses with no candidate text as non-retryable for interactive `/ask`; log safe response-shape metadata such as block reason, finish reason, and candidate counts without logging full model responses.
- Do not log full prompts, model responses, API keys, Telegram file contents, or user secrets.

## Implementation Guidance

- Keep Lambda cold-start cost low: use lazy wiring and avoid unnecessary runtime dependencies.
- Use `zerde_common` for shared provider errors, config helpers, redaction, and structured logging.
- Keep Lambda env names consistent with code: `BOT_TOKEN`, `WEBHOOK_SECRET_TOKEN`, `GEMINI_API_KEY`, `GEMINI_EMBEDDING_API_KEY`, `DEEPSEEK_API_KEY`, `GROQ_API_KEY`.
- When adding or changing non-secret runtime/CDK env vars, wire them through `.env.example`, `infra/stack.py`, relevant construct environment maps, `.github/workflows/deploy.yml`, `.github/workflows/pr_check.yml`, docs, and GitHub repo Actions variables with `gh variable set <NAME> --repo Bayashat/zerde-serverless-bot --body <value>`. Do this before declaring deployment config complete; repo variables alone are ignored if workflow env mappings are missing.
- Use `CONSTRUCT_PREFIX` and `RESOURCE_PREFIX` from `infra/components/constants.py`; do not duplicate those string literals in constructs.
- S3 Vectors queries with metadata filters or `returnMetadata=True` need both `s3vectors:QueryVectors` and `s3vectors:GetVectors` in the Lambda role policy. Keep Bot Lambda permissions limited to query/get/delete/get-index; reserve `s3vectors:PutVectors` and `s3vectors:ListVectors` for the vector-indexer Lambda.
- If editing Telegram HTML output, normalize/escape LLM output before sending and respect Telegram length constraints.

## Documentation Maintenance

For substantial changes, update documentation proactively in the same work:

- Always update `.codex/AGENTS.md`, `docs/ARCHITECTURE.md`, and this skill for architecture, memory, agent, SQS, data schema, or infra changes.
- Update `README.md`, `docs/README_kk.md`, and `docs/README_ru.md` for user-visible behavior changes.
- Update `docs/LOCAL_TESTING.md` and `.env.example` for setup/config changes.
- Update `docs/telegram_history_import.md` for import, backfill, or vector indexing changes.
- Historical files under `docs/superpowers/` are plan snapshots; do not rewrite them as current architecture unless explicitly asked.

## Validation Expectations

Choose validation proportional to risk:

- Narrow Python change: run relevant pytest files.
- Shared behavior, AI provider routing, repositories, dispatcher, memory, or Telegram formatting: run `uv run pytest tests/ -q`.
- Formatting/lint-sensitive work: run `uv run pre-commit run --all-files`.
- CDK or Lambda env changes: run `cd infra && uv run cdk diff -c env=dev` and report the diff.
