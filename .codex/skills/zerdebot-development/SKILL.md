---
name: zerdebot-development
description: Inspect, implement, test, review and operate ZerdeBot's Python Lambda Telegram bot, Memory V2, explicit AI answers/media, captcha, spam, votes, news, Quiz, operational alerts and AWS CDK. Follow the current memory ownership, retirement, deployment and evidence contracts.
---

# ZerdeBot development

Read [.codex/AGENTS](../../AGENTS.md), [architecture](../../../docs/ARCHITECTURE.md), [finishing contract](../../../docs/goals/zerdebot-memory-v2/FINISH_EXECUTION.md), current TASKS/HANDOFF and the relevant issue. Check current source/branch/PR and live evidence before continuing. Historical plans and frozen reports do not authorize rerunning completed scripts.

## Product and ownership

Memory V2 is the unique fact/source/control/lifecycle owner. Explicit self-statements are scoped by group and Telegram ID, supported by evidence and corrected/forgotten through one interface. Profiles are views, not another free-text knowledge store. Preserve source version/epoch/generation/expiry checks and the original model/AWS budget owners; UNKNOWN liability remains.

The legacy 13-module memory/profile/extraction/retrieval/vector/social/import implementation is deleted in the source-retirement change. Do not recreate rule fallback, autonomous replies/reactions, channel comments, historical import or contests. Source removal, deployed package absence and physical AWS deletion are separate proofs. The discard-only vector entry remains only until its dedicated resources retire; old task rejection prevents delayed envelopes from acting.

Explicit `/ask`, mentions and requested bot replies stay usable independently of old switches. Current pure text/reference/style helpers live in `services/explicit_context.py`; the temporary-media facade directly delegates to V2 EphemeralMediaRepository. It does not inherit an old repository or need `MEMORY_TABLE_NAME`. Preserve ephemeral source/actor/TTL fences, before-attempt checks and final delivery leases across primary/fallback models. Do not use quoted old bot answers or old recent/profile/vector context as fallback knowledge.

## Cleanup and operating boundary

The user requires retired code/resources cleared before new feature/group/prod-memory activation, and a precise delete/keep/unverified list before deletion. Follow [inventory](../../../docs/goals/zerdebot-memory-v2/RETIREMENT_INVENTORY.md) and [source execution](../../../docs/goals/zerdebot-memory-v2/SOURCE_RETIREMENT_EXECUTION.md). Keep current dev CONTROL/epoch; never force a historic revision after legitimate activity.

The last old-SETTINGS audit found dev0/prod3 retired-flag rows without custom style. Before stopping their reads in deployment and before physical deletion, recheck complete strong pagination, exact keys, AV types/full-row hashes, strict fields and preserved stop-write protection. Changes block that path until actual semantics are protected. Do not create pointless settings rows or map retired flags to V2 ACTIVE. Retain the six current business/Quiz/V2 tables; unknown orphan consumers still require evidence. Never purge/receive mixed queues or delete stacks/shared assets.

Keep captcha generation/decision/recovery, confirmed spam enforcement and CLEAN admission, vote session/expiry, news per-group delivery and Quiz publication/answer recovery intact. Preserve production Chinese news DISABLED and absence of the old summary schedule. Operational alerts go to the configured administrator private chat.

## Implementation and verification

Use current providers and existing error/fallback handling; avoid unrelated SDK/model upgrades. Verify changed model availability/pricing against official sources when needed. Do not log complete Telegram events, source/model text, secrets or media; preserve redaction of nested exceptions and SDK errors.

Main agent implements sequentially; independent agents review ownership, correctness and maintainability. Preserve useful mixed tests while deleting retired-owner tests. Keep frozen gold/scorer/runs unchanged. Compare complete current explicit requests against the saved 18-case pre-cleanup synthetic baseline, not just a new serializer against itself. Source grep/tests do not prove a deployed package: verify actual ARM handlers, locked dependency versions and physical ZIP contents, including absence of retired modules/bytecode.

Use `uv sync --frozen`, focused then full meaningful tests, and repo pre-commit hooks. For infra, inspect synth/dev diff and exact changeset; maintain config/workflow/example/repo-variable parity. Use a managed worktree, default `feat/` branch, conventional commits and FEATURE/FIX PR titles. Finish scoped changes through a PR and already-authorized review/CI/deployment gates, with actual readback.

Every material result updates PLAN/task_manifest/TASKS/HANDOFF/EVIDENCE and corresponding GitHub issues. Natural acceptance requires real use and answer quality, not generated chats or elapsed idle days. Continue cleanup/business/cost work while samples are missing. Keep deployment, data deletion, resource absence and retained-copy expiry separate; do not claim all copies erased. User exports remain; Z10 retains PITR/log/DLQ/backup duties and real historical delay/UNKNOWN records.
