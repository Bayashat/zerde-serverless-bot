---
name: zerdebot-development
description: Work on the ZerdeBot repository, a serverless AWS CDK Telegram group-chat agent with Python Lambdas for bot/webhook/SQS, RAG memory, DynamoDB profiles, S3 Vectors semantic retrieval, Gemini/Groq/DeepSeek AI integrations, news digests, quizzes, spam controls, and CDK infrastructure. Use when Codex is asked to inspect, modify, test, review, document, deploy-plan, debug, or optimize this repo, especially changes involving `src/bot`, `src/news`, `src/quiz`, `src/shared`, `infra`, group memory, agent behavior, `/ask`, vector indexing, Telegram behavior, SQS workflows, DynamoDB repositories, or AI providers.
---

# ZerdeBot Development

## Operating Posture

Treat ZerdeBot as a **memory-enabled agentic Telegram bot**, not a simple LLM wrapper. The bot combines serverless community tooling with RAG memory and social agent behavior:

- Recent group context, requester identity, and user profiles live in DynamoDB.
- Long-term memory and daily summaries live in DynamoDB and are indexed in S3 Vectors.
- Gemini handles agent answers, proactive timing decisions, summaries, and embeddings.
- Groq handles async spam checks.
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

- `src/bot/`: Telegram webhook, dispatcher, SQS worker tasks, captcha, voteban, spam screening, `/ask`, group agent, group memory, vector indexing.
- `src/bot/services/group_agent.py`: agent trigger policy, proactive gating, reply-thread continuity, response length policy.
- `src/bot/services/group_memory.py`: recent context observation and prompt formatting, requester/target-user profiles, query-filtered long-term context.
- `src/bot/services/group_memory_processor.py`: async long-term memory extraction and daily summaries.
- `src/bot/services/vector_memory.py`: Gemini embeddings, S3 Vectors indexing/retrieval with metadata filters and distance cutoffs, vector cleanup/backfill.
- `src/bot/services/repositories/group_memory.py`: DynamoDB single-table layout for settings, messages, profiles, long-term memory, agent replies, vector status, and proactive counters.
- `src/news/`: scheduled news digest Lambda.
- `src/quiz/`: scheduled and on-demand quiz Lambda.
- `src/shared/python/zerde_common/`: shared Lambda layer utilities.
- `infra/`: AWS CDK stack and constructs.
- `docs/ARCHITECTURE.md`: current architecture source of truth.
- `tests/`: pytest coverage for bot, quiz, spam, shared utilities, memory, and agent behavior.

## Memory And Agent Guardrails

- Do not inject unfiltered long-term memory into agent prompts. Use query-filtered long-term context and semantic vector retrieval.
- Self-reference questions must include requester identity/profile context in the answer path.
- User profile context must be derived from the target user's own messages; third-party roasts or labels are low trust.
- Query-filtered long-term memory must stay empty when the current query has no usable relevance terms.
- Semantic vector retrieval should use metadata filters and distance cutoffs before prompt injection.
- Reply-to-bot follow-ups must include prior `AGENT_REPLY#...` answer context when available.
- Store useful bot answer metadata in `AGENT_REPLY#...` so `/agent why` and thread continuation work.
- Keep proactive participation conservative: local open-question prefilter, bot-meta/stop-cue exclusions, recent bot activity penalty, Gemini decision, and daily limit.
- Keep response length proportional to the user's request. Short follow-ups should stay short unless the user asks for detail.
- If cleaning production memory, first back up exact DynamoDB items and vector keys locally, then delete narrowly.

## SQS And Persistence

SQS handler failures should re-raise when retry/DLQ semantics are intended. Current bot SQS task types:

- `CHECK_TIMEOUT`
- `SPAM_CHECK`
- `PROCESS_GROUP_ASK`
- `PROCESS_GROUP_MEMORY`
- `PROCESS_DAILY_GROUP_SUMMARIES`
- `PROCESS_VECTOR_MEMORY`
- `PROCESS_VECTOR_MEMORY_BACKFILL`

DynamoDB memory key families:

- `SETTINGS`
- `MSG#...`
- `USER#...`
- `EVENT#...`
- `USER_FACT#...`
- `GROUP_FACT#...`
- `JOKE#...`
- `DAILY_SUMMARY#...`
- `AGENT_REPLY#...`
- `VECTOR_BACKFILL`
- `PROACTIVE#...`

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
- Do not log full prompts, model responses, API keys, Telegram file contents, or user secrets.

## Implementation Guidance

- Keep Lambda cold-start cost low: use lazy wiring and avoid unnecessary runtime dependencies.
- Use `zerde_common` for shared provider errors, config helpers, redaction, and structured logging.
- Keep Lambda env names consistent with code: `BOT_TOKEN`, `WEBHOOK_SECRET_TOKEN`, `GEMINI_API_KEY`, `GEMINI_EMBEDDING_API_KEY`, `DEEPSEEK_API_KEY`, `GROQ_API_KEY`.
- Use `CONSTRUCT_PREFIX` and `RESOURCE_PREFIX` from `infra/components/constants.py`; do not duplicate those string literals in constructs.
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
