# ZerdeBot working instructions

Answer the user in Chinese. Follow [FINISH_EXECUTION](../docs/goals/zerdebot-memory-v2/FINISH_EXECUTION.md), [TASKS](../docs/goals/zerdebot-memory-v2/TASKS.md), [HANDOFF](../docs/goals/zerdebot-memory-v2/HANDOFF.md) and [ARCHITECTURE](../docs/ARCHITECTURE.md). The approved PLAN owns the target contract; task_manifest owns current issue state; EVIDENCE records actual results. Historical reports are evidence, not instructions to rerun completed work.

## Current product and cleanup boundary

Memory V2 is the sole fact/control/source/lifecycle owner. Personal facts need explicit self-statements, group-scoped Telegram IDs, current evidence and correction/forget support. Profiles are projections. Automatic participation/reactions/channel comments, history import and experimental contests are retired. Do not recreate them behind flags, rules or fallback providers.

The source-retirement change deletes 13 legacy algorithm modules and their callers. Physical AWS retirement is a separate step: keep the current discard-only vector entry until its resources are removed. Keep the small old-task rejection protocol to stop delayed mixed-queue messages reviving old behavior. Do not equate old words in an inert task schema or historical audit record with a live knowledge owner.

Before any new feature/group/production-memory activation, finish [the deletion inventory](../docs/goals/zerdebot-memory-v2/RETIREMENT_INVENTORY.md). Tell the user precisely what will be deleted, kept or still needs verification. Current broad repair/deploy authority does not justify unrelated deletion or payment changes. Existing dev pilot CONTROL/epoch must not be reset; legitimate revision changes must not be overwritten with a historic value.

Old SETTINGS are not an active settings owner. The last complete audit found dev0/prod3 rows, only retired flags/timestamps and no custom style. Before deploying the code that stops reading them, and again before actual deletion, freshly verify full strongly consistent pagination, exact keys/AttributeValue types/whole-row hashes, strict five-field allowlist and preserved stop-write protection. Any new row, field, custom style or writer stops that path; protect its semantics before proceeding. Do not migrate dead flags into new stats rows or V2 learning control.

## Active owners

- `app.py` lazily wires current business/V2 dependencies. Explicit context never requires the old table env.
- `services/explicit_context.py` is the single pure text/reference/style helper shared with strict evaluation.
- `services/group_agent.py` retains explicit triggers, answer length and primary/fallback orchestration only.
- `ExplicitContextRepository` delegates metadata-only temporary albums to V2 EphemeralMediaRepository; no old-store fallback or bot-answer body writes.
- `memory_v2` owns facts, source edit/deletion/epoch fences, public commands/answers and recovery. Preserve explicit delivery leases, before-attempt and final-send checks.
- Existing model budget/AWS cost owners and UNKNOWN liability remain authoritative. Never handwrite permits, clear uncertainty, or treat read-only availability as durable call authorization.
- Business stats/Quiz/V2 tables, captcha/spam/vote/news/Quiz recovery, Operations, shared layer/assets and current queues remain protected.

No rule-based fact fallback on extraction failure. No old profile/recent/vector/self-bot answer context in plain requests. No false claim that unavailable memory means an empty database. No background media transcription/profile learning. Ordinary messages and channel posts produce zero unsolicited social output; explicit requested media acknowledgement remains allowed.

## Reliability and evidence

Captcha uses generation/revision and durable decisions before Telegram effects; never treat database failure as missing state or kick a verified member from an old timeout. Spam success requires confirmed enforcement, and CLEAN admission reloads staged sources. Preserve vote session IDs, logical expiry, per-group news recovery, Quiz publication/answer idempotence and unknown-send handling.

Do not log secrets, complete Telegram updates, source/model text or raw media. Preserve shared redaction for exception chains and SDK logs. Production Chinese news stays DISABLED; do not recreate old group-summary schedules.

Keep frozen gold, scorers, model runs, published reports and once-script results unchanged. Current explicit serializers must match the saved pre-cleanup synthetic request baseline, not merely each other. Keep useful mixed tests; retire only tests whose algorithm was removed. Build actual ARM packages and inspect deployed ZIP/source/dependency bytes; source grep or a merged PR alone is insufficient.

Update PLAN/task_manifest/TASKS/HANDOFF/EVIDENCE and relevant GitHub issues after material progress. Distinguish local code, merge, deployment, synthetic/real quality, resource absence and copy expiry. Natural seven-day acceptance starts from actual use; do not invent chat or count empty calendar days. Continue independent cleanup/business/cost work while natural samples are missing.

## Repository workflow

Read current branch/main/PR and protect unrelated user work. Use a suitable existing managed worktree; default branch prefix `feat/`. Main agent integrates implementation sequentially, with independent plan/correctness/maintenance review. Use conventional commit prefixes and FEATURE/FIX PR titles. Publish completed work through a PR; user authorization already covers scoped CI, merge and dev/prod deployment.

Commands: `uv sync --frozen`, `uv run pytest tests/ -q`, `uv run pre-commit run --all-files`; for infrastructure, synth and inspect meaningful dev diff/changeset before deployment. Use lock-derived Lambda requirements and actual six-handler ARM verification until the vector resource retirement changes that exact count. Runtime config changes must stay consistent with infra, workflows, examples and repo variables; inert old infra settings are removed in the resource phase, not silently read again.

No mixed-queue Receive/Purge, whole-stack deletion, unrelated resource cleanup or old-memory restoration. CloudFormation Retain is not physical deletion. User exports remain; PITR next review is 2026-10-17 16:20:38UTC, with log/DLQ/other-copy obligations separately tracked. Update this file together with architecture and the development skill when ownership changes.
