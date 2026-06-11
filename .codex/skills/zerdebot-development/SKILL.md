---
name: zerdebot-development
description: Work on the ZerdeBot repository, a serverless AWS CDK Telegram bot with Python Lambdas for bot/webhook/SQS, news, quiz, spam, and AI provider integrations. Use when Codex is asked to inspect, modify, test, review, deploy-plan, debug, or optimize this repo, especially changes involving `src/bot`, `src/news`, `src/quiz`, `src/shared`, `infra`, AI providers such as Gemini/DeepSeek/Groq, Telegram behavior, SQS workflows, DynamoDB repositories, or CDK infrastructure.
---

# ZerdeBot Development

## Overview

Use this skill as the project-specific operating guide for ZerdeBot. It keeps Codex aligned with the repo architecture, validation commands, deployment constraints, and AI-provider reliability expectations.

## First Steps

1. Read `.codex/AGENTS.md` before making non-trivial code, infra, AI, or deployment changes.
2. Check the active branch and dirty worktree with `git status --short --branch`.
3. Preserve user changes. Do not revert unrelated files.
4. Prefer focused changes that follow existing package boundaries.

## Repository Map

- `src/bot/`: Telegram webhook, dispatcher, SQS worker tasks, spam screening, `/wtf`, `/explain`, `/genquiz` invoke path.
- `src/news/`: scheduled news digest Lambda.
- `src/quiz/`: scheduled and on-demand quiz Lambda, AI-generated question bank, Telegram poll sending.
- `src/shared/python/zerde_common/`: shared Lambda layer utilities.
- `infra/`: AWS CDK stack and constructs.
- `tests/`: pytest coverage for bot, quiz, spam, shared utilities.

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
- Prefer fast fallback for interactive commands (`/wtf`, `/explain`, `/genquiz`) over long primary-provider retries.
- Keep scheduled/batch paths allowed to retry longer than interactive user commands.
- Map provider transport, 429, 5xx, and parse failures into consistent error types where the codebase already has that pattern.
- Do not log full model prompts, responses, API keys, Telegram file contents, or user secrets.

## Implementation Guidance

- Bot SQS routing failures should re-raise when retry/DLQ semantics are intended.
- Keep Lambda cold-start cost low: use lazy wiring and avoid unnecessary runtime dependencies.
- Use `zerde_common` for shared provider errors, config helpers, redaction, and structured logging.
- Keep Lambda env names consistent with code: `BOT_TOKEN`, `WEBHOOK_SECRET_TOKEN`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `GROQ_API_KEY`.
- Use `CONSTRUCT_PREFIX` and `RESOURCE_PREFIX` from `infra/components/constants.py`; do not duplicate those string literals in constructs.
- If editing Telegram HTML output, normalize/escape LLM output before sending.

## Validation Expectations

Choose validation proportional to the change:

- Narrow Python change: run the directly relevant pytest files.
- Shared behavior, AI provider routing, repositories, dispatcher, or Telegram formatting: run `uv run pytest tests/ -q`.
- Formatting/lint-sensitive work: run `uv run pre-commit run --all-files`.
- CDK or Lambda env changes: run `cd infra && uv run cdk diff -c env=dev`.

## Reference

Detailed architecture, command, secret, and design-decision guidance lives in `.codex/AGENTS.md`. Read it when context is needed rather than duplicating it here.
