# Telegram Contest Random Winner Implementation Plan

**Intent:** Let a linked Telegram channel run a fair, auditable Kazakh-language contest in its discussion supergroup by marking the original post with `#конкурс`, recording each eligible person once, and allowing only the group creator to draw one winner plus at most two distinct redraws.
**Current Behavior:** Zerde recognizes official linked-channel mirror posts for AI comments and ambient reactions, and stores ordinary discussion messages for memory, but it has no contest state, participant uniqueness contract, owner-only draw command, frozen entrant boundary, or winner evidence path. A plain-message handler cannot be added safely because the dispatcher currently uses its single handler for captcha answers, and the group-agent path may consume ordinary text before the dispatcher sees it.
**Expected Outcome:** Every configured linked discussion supergroup can create one contest per official mirrored root post when the initial text or caption contains a case-insensitive standalone `#конкурс`. Eligible first-level text replies containing `қатысамын` are atomically deduplicated by Telegram user id. The current Telegram group creator can close and draw securely, redraw at most twice without repeating winners, cancel an open contest, and admins can inspect status. Results publicly show the unique entrant count and reply to the winner's original entry when it still exists.
**Target-Perspective Output:** A group member sees a fixed Kazakh rules reply under the channel post, receives the Bot API-supported `🎉` reaction on their first accepted entry, and cannot gain another chance by posting again. The group owner replies to the root or rules message with `/contest draw` and sees a winner announcement anchored to the actual accepted comment, including participant count and draw number. Unauthorized users see no successful state transition.
**Truth Owner:** `ContestRepository` rows in the existing DynamoDB memory table own contest lifecycle, first accepted participant evidence, frozen counts, winner history, announcement ids, expiry, and rule-message anchors. Telegram messages are presentation/evidence anchors, not lifecycle truth.
**Contract Boundary:** Raw Telegram `Update.message` payloads cross into contest observation after captcha/spam short-circuiting and before memory/ambient/agent handling. `/contest` commands cross through the existing dispatcher `Context`. Repository operations expose explicit state transitions and registration outcomes; no AI model participates in eligibility or winner selection.
**Cutover:** Insert one non-consuming contest observation step into the webhook. It records contest state/reactions but then preserves the existing memory, ambient reaction, linked-channel AI-comment, group-agent, and dispatcher paths. Register `/contest` as a normal command without replacing the captcha `on_message` handler. Reuse the existing memory table, main task queue, and IAM; add no table, queue, env var, or webhook update type. Add idempotent `PROCESS_CONTEST_TTL_SWEEP` and bounded `PROCESS_CONTEST_TTL_RECOVERY` tasks, a same-table durable outbox marker, and one always-on production EventBridge recovery seed so missed initial enqueue is recovered without participant scans even after all chats leave configuration.
**Displaced Path:** No user-visible path is removed. The unsafe alternatives are explicitly displaced: do not route entries through the single dispatcher message handler, do not infer participants from group-memory rows, do not keep participants in one growing DynamoDB list, and do not let the group-agent own contest recognition.
**Value Density:** One hashtag, one entry phrase, four subcommands, one secure winner path, one existing DynamoDB table/queue, and one small production recovery schedule deliver the requested contest loop without deadlines, exports, DMs, prize workflows, new storage, or new runtime configuration.
**Acceptance Evidence:** Capture an executable Telegram-shaped acceptance transcript in focused tests: official mirror -> Kazakh rules reply; direct eligible entry -> one conditional participant record and `🎉`; duplicate/nested/anonymous entry -> no extra chance; creator draw -> frozen complete entrant set and winner reply to the saved entry message; two redraws -> distinct winners; deleted-entry fallback -> root reply; missing root -> terminal `ORPHANED`. The integration matrix also covers root/rules anchoring, owner/admin authorization, 0/1-person draws, exhausted redraws, logical expiry, crash recovery, and resumable TTL sweep. Run the complete test suite and pre-commit. Because this task does not authorize deployment to a real Telegram group, report the result as implemented but unproven live.
**Evidence Lane:** Repository contract tests, webhook/dispatcher integration tests using real Telegram update shapes, Telegram API payload tests, and a target-perspective contest flow test. Live Telegram acceptance is a later deployment gate.
**Kill Criteria:** There must be exactly one contest truth model and one registration path. No scan of raw memory messages, no second participant store, no alternate draw code, no partial-page random selection, no bot-owner draw exception, no nested-reply eligibility, and no fallthrough winner message into the supergroup main chat.
**Architecture Slice:** `webhook.py` observation -> `services/contest.py` orchestration -> `repositories/contest.py` state/transactions; `/contest` -> `handlers/contest.py` -> the same service/repository; `TelegramClient` remains the only Bot API boundary.
**Plan Review Gate:** Requires PRE review before execution.

## Confirmed Product Contract

### Contest creation

- Apply to all supergroups already configured through `CHAT_LANG_MAP`; add no feature flag.
- Accept only official linked-channel discussion mirrors: supergroup message, linked-channel actor, automatic-forward/fallback marker, and current `getChat(...).linked_chat_id` matching `sender_chat.id`.
- Match a standalone `#конкурс` case-insensitively in the initial root `text` or `caption` only.
- Do not subscribe to or process `edited_message`; later edits neither create contests nor change entries.
- Resolve the current Bot id through a cached Telegram `getMe` call, then require its current chat-member status to be `administrator`; otherwise send a fixed Kazakh configuration error and create no open contest.
- Reply to the root with deterministic Kazakh rules while preserving all existing linked-post AI comments and reactions.

### Entry eligibility

- Accept only `message.text` containing the case-insensitive substring `қатысамын`.
- Require `message_thread_id == root_message_id` and `reply_to_message.message_id == root_message_id` so only first-level comments count.
- Require a real personal `from.id`, `from.is_bot != true`, and no `sender_chat`; exclude bots, anonymous admins, and channel identities.
- Deduplicate atomically by `(chat_id, root_message_id, user_id)` and retain only the first accepted message snapshot.
- Ignore later edits/deletions for eligibility. Telegram message deletion is not available as a normal Bot API update.
- Set the Bot API-supported `🎉` reaction for a newly stored participant; an idempotent redelivery of that exact accepted Telegram message may reassert the same reaction after ambiguous delivery. A different duplicate, late, invalid, nested, or anonymous entry receives no contest feedback. Existing ambient reactions may later replace the `🎉`.
- Continue the existing group-memory, ambient-reaction, proactive-agent, and command pipeline after contest observation.

### Authorization and commands

- Every command must be sent by a personal account while replying to the root message or the stored rules message.
- `/contest draw`, `/contest redraw`, and `/contest cancel` require live `getChatMember(...).status == creator`.
- `/contest status` accepts live `creator` or `administrator` status.
- Do not grant `ADMIN_USER_ID` / bot owner a contest exception.
- Commands and all public contest text are fixed Kazakh messages.

### Lifecycle and randomness

- Public lifecycle: `OPEN -> DRAWN` or `OPEN -> CANCELLED`; there is no reopen.
- Internal fail-closed states are explicit: `CREATING` accepts no entries until the rules-message id and alias are durably attached; `DRAWING` accepts no entries while the complete entrant set is selected; `announcement_state=PENDING|SENT` tracks delivery of an already-persisted winner; and `ORPHANED` is terminal.
- First draw atomically stops registration before a strongly consistent, fully paginated participant read.
- Zero participants returns an error and restores/remains `OPEN`; one participant wins normally.
- Use a uniform `secrets.randbelow` reservoir sample across every strongly consistent participant page. Never choose from a partial page or materialize an unbounded participant list.
- First draw stores a frozen participant count and closes registration.
- Allow two redraws within the fixed retention window, exclude all previous winners, and never exceed three winner records total.
- Repeating `/contest draw` returns the stored first result; only `/contest redraw` may append a new distinct winner.
- If no unselected participant remains, reject redraw without changing stored winners.
- A pending winner announcement must be retried with the same persisted winner before any redraw can begin. Retrying a command must never select a replacement winner merely because Telegram delivery failed.

### Evidence, retention, and failure behavior

- Store entry message id, user id, username, first/last name, original accepted text, and acceptance timestamp.
- HTML-escape every user-controlled display value, create mentions with the safe `tg://user?id=...`/escaped username helper, and deterministically truncate the public fallback snapshot so every message remains below Telegram's limit. Keep the bounded full accepted text only in DynamoDB.
- Publish winner mention, unique participant count, and draw ordinal (`1/3`, `2/3`, `3/3`) by replying directly to that winner's first accepted comment.
- If Telegram explicitly reports that the entry reply target is missing, reply to the root with the stored snapshot and original message id.
- If the root reply target is also missing, mark the contest `ORPHANED`; never use `allow_sending_without_reply=true` and never spill the result into the main chat. `ORPHANED` preserves the frozen count and winner audit, permits authorized `status` only, and rejects draw/redraw/cancel.
- `OPEN` has no automatic expiry. The first successful draw or cancellation atomically writes one immutable 30-day logical `expires_at` plus a global durable cleanup marker, then enqueues an idempotent paginated TTL sweep; redraws do not extend it.
- Logical expiry is authoritative even if DynamoDB has not physically removed rows yet. Every command rejects expired state before mutation.
- A known webhook outage longer than Telegram's 24-hour update retention invalidates live fairness; the operational rule is to cancel the affected contest.
- If a root disappears before the first draw and Telegram never reports the deletion, leave the unreachable `OPEN` rows for precise operator cleanup by `(chat_id, root_message_id)`; do not add a bot-owner chat command.

### Cross-system recovery protocol

- Creation writes `CREATING`, sends the rules reply, then atomically attaches the returned rules-message alias and transitions to `OPEN`. Registration condition-checks `OPEN`, so a failed rules send can never leave a hidden active contest.
- If a direct comment webhook overlaps the root webhook before META exists, an unedited embedded official root posted at most five minutes before that comment may request Telegram redelivery while the comment remains within Telegram's 24-hour update-retention window. The nested snapshot never creates a contest itself, so edited roots or old-root/new-comment history cannot be backfilled.
- A definite rules-delivery failure marks `CREATION_FAILED` with a 30-day cleanup TTL. An ambiguous network failure may mean Telegram displayed a duplicate rules message on retry; exactly-once Telegram delivery is not promised, but the repository still remains fail-closed and never counts entries before one returned message id is attached.
- First draw transitions `OPEN -> DRAWING` before a strongly consistent participant read. A read/selection failure conditionally restores `OPEN`; a crash may leave `DRAWING`, and the same creator command resumes that frozen attempt rather than opening a second draw.
- Winner choice is persisted before Telegram delivery with `announcement_state=PENDING`. Delivery success stores the Bot announcement id and changes it to `SENT`. A repeated `/contest draw` or the next `/contest redraw` first replays a pending announcement for the same stored winner; it never reselects.
- Telegram acknowledgement loss can produce a duplicate announcement for the same winner, because Bot API `sendMessage` has no idempotency key. The invariant is no hidden-open contest, no changed winner, no extra chance, and no main-chat spill—not cross-system exactly-once presentation.
- First draw/cancel writes `expires_at` and `pk=CONTEST_TTL_OUTBOX` in one transaction, then best-effort enqueues `PROCESS_CONTEST_TTL_SWEEP` without delaying the winner/status response. The worker stamps the same `ttl` on a bounded participant page and persists its continuation key before identity-only re-enqueue. Reprocessing a page is idempotent; second-page failure resumes from the META cursor/version, the only sweep-progress truth. It stamps the rules alias, then atomically marks `ttl_sweep_status=COMPLETE`, applies META physical TTL, and deletes the outbox marker. An always-on production EventBridge rule seeds an independent bounded `PROCESS_CONTEST_TTL_RECOVERY` job; recovery strongly pages the global outbox and queues sweeps, including when a chat—or every chat—was removed from configuration. Recovery-task failures retain normal SQS retry/DLQ behavior and do not share the daily-summary failure domain.

### Non-goals

- Automatic deadline or draw.
- Multiple simultaneous winners in one draw.
- Manual participant removal or disqualification.
- Participant export.
- Direct-message winner notification.
- Prize fulfillment/claim tracking.
- Edit-driven eligibility changes or deleted-message history recovery.
- Deployment or live production acceptance in this change.

## Architecture Map

### Files to create

- `src/bot/services/repositories/contest.py` — sole DynamoDB contest/participant/anchor repository, conditional writes, transactions, pagination, state transitions, TTL stamping.
- `src/bot/services/contest.py` — marker/entry recognition, root validation, secure draw/redraw orchestration, fixed Kazakh rendering, winner announcement/fallback behavior.
- `src/bot/services/handlers/contest.py` — `/contest` parsing, reply-anchor validation, live permission checks, and calls into the contest service.
- `tests/test_contest_repository.py` — DynamoDB key, condition, transaction, pagination, state, and TTL contract tests.
- `tests/test_contest_service.py` — recognition, eligibility, reaction, secure draw, announcement, fallback, and state behavior.
- `tests/test_contest_acceptance.py` — target-perspective Telegram-shaped end-to-end flow across root, entries, commands, and output payloads.
- `tests/test_contest_wiring.py` — application/Lambda dependency injection for the contest repository and shared queue client.
- `docs/CONTEST_OPERATIONS.md` — fairness incidents, exact-row inspection, DLQ recovery, and narrow manual-cleanup runbook.
- `docs/goals/telegram-contest-random-winner/PLAN.md` — this source plan.
- `docs/goals/telegram-contest-random-winner/GOAL.md` — compact execution handoff.

### Files to modify

- `src/bot/app.py` — lazily construct/inject `ContestRepository` from the existing memory table.
- `src/bot/main.py`, `src/bot/services/sqs_task_router.py`, `src/bot/services/repositories/sqs.py` — route/enqueue idempotent contest TTL sweep and bounded recovery tasks on the existing main queue.
- `src/bot/core/dispatcher.py` — carry `contest_repo` in `Dispatcher`/`Context`; do not change single-message-handler semantics.
- `src/bot/services/repositories/__init__.py` — export `ContestRepository`.
- `src/bot/services/handlers/__init__.py` — register `/contest` only.
- `src/bot/webhook.py` — observe contest roots/entries after spam/captcha and before memory/ambient/agent while continuing the normal flow.
- `src/bot/services/telegram.py` — add only the Bot API identity/reply semantics needed for admin verification and missing-anchor-safe replies.
- `infra/components/bot.py`, `tests/test_infra_configuration.py` — add and prove the production recovery schedule remains present with zero configured chats.
- `tests/conftest.py`, `tests/test_dispatcher.py`, `tests/test_webhook.py`, `tests/test_telegram_client.py`, `tests/test_sqs_task_router.py` — update shared wiring, task routing, and boundary expectations.
- `.codex/AGENTS.md`, `.codex/skills/zerdebot-development/SKILL.md`, `docs/ARCHITECTURE.md` — document the new truth rows, webhook step, command contract, and fairness/failure boundaries.
- `README.md`, `docs/README_kk.md`, `docs/README_ru.md` — document the user-visible hashtag, entry rule, commands, permissions, and 30-day window.

### Files to avoid

- `src/bot/services/group_agent.py` and AI provider prompts — existing AI behavior remains unchanged.
- `src/bot/services/group_memory.py` and `repositories/group_memory.py` — contest is not memory extraction or semantic retrieval.
- `src/bot/services/handlers/captcha.py` — keep the pending-captcha isolation and existing plain-message handler.
- `.env.example` and GitHub workflows — add no environment configuration; reuse the existing table/main queue/IAM.
- `scripts/setup_webhook.sh` — edited updates remain out of scope.

### Source of truth

The existing DynamoDB memory table with dedicated non-vectorizable chat rows plus one global cleanup-outbox partition:

```text
sk=CONTEST#<root_message_id>#META
sk=CONTEST#<root_message_id>#PARTICIPANT#<telegram_user_id>
sk=CONTEST_RULE#<rules_message_id>
pk=CONTEST_TTL_OUTBOX, sk=CHAT#<chat_id>#ROOT#<root_message_id>
```

### Read path

- Root/entry observation derives the stable contest id from the discussion supergroup root message id.
- Commands resolve either the root anchor directly or a stored rules-message alias.
- Draw streams participant keys with strong consistency and full pagination; status reads the exact transactional participant counter.
- Scheduled retention recovery strongly pages only the global outbox partition, never participant rows.

### Write path

- Conditional contest creation prevents duplicate webhook delivery from creating duplicate activities.
- Participant registration uses one DynamoDB transaction: conditionally increment the exact META participant counter while `OPEN`, plus conditional put of the per-user participant row.
- Draw closes registration before reading; conditional completion stores one winner history. Concurrent/retried commands return the persisted result rather than selecting again.
- First draw/cancel atomically sets logical expiry and creates a durable outbox marker, then best-effort enqueues a cursor-based, idempotent main-queue sweep that stamps participant/alias/META TTLs without extending on redraw. Completion atomically consumes the marker; the independent production recovery schedule seeds bounded, independently retried recovery pages for missed work.

### Integration points

- Telegram `getMe` (cached), `getChat`, `getChatMember`, `sendMessage`, and `setMessageReaction` through `TelegramClient`.
- Existing main SQS queue for `PROCESS_CONTEST_TTL_SWEEP` and `PROCESS_CONTEST_TTL_RECOVERY`; task failures retain the current retry/DLQ semantics.
- Existing webhook spam/captcha ordering.
- Existing dispatcher command parsing and `@botname` normalization.
- Existing memory table/IAM and DynamoDB TTL attribute `ttl`.
- One always-on production EventBridge rule targeting the existing main queue with `PROCESS_CONTEST_TTL_RECOVERY`; no new queue, table, role, or environment setting.

### Migration/cutover

No data migration. New key prefixes are ignored by existing memory/vector readers. The feature becomes active when this code is deployed; historical `#конкурс` posts are not backfilled.

### Acceptance evidence gate

Before publication:

1. Targeted repository/service/webhook/dispatcher/Telegram tests pass.
2. The acceptance/integration matrix proves visible rules, one reaction per user, root/rules command anchoring, owner-only draw/cancel, admin status, 0/1-person behavior, correct winner reply anchoring, unique/exhausted redraws, logical expiry, safe missing-message fallback, and fail-closed delivery recovery.
3. `uv run pytest tests/ -q` passes.
4. `uv run pre-commit run --all-files` passes.
5. Review confirms the only infra diff is the production contest-recovery schedule, there is no env diff, and AI decision behavior is unchanged.

## Execution Tasks

### Task 1 — Establish contest persistence and concurrency contract

**Files:** Create `src/bot/services/repositories/contest.py`, `tests/test_contest_repository.py`; modify repository exports.

**Allowed scope:** Dedicated `CONTEST#`/`CONTEST_RULE#` rows and one `CONTEST_TTL_OUTBOX` partition in the existing memory table; conditional `CREATING -> OPEN`; transactional unique registration/count; strong paginated reservoir reads; begin/complete/abort/resume draw; announcement state; redraw history; cancel/terminal orphan; immutable logical expiry; durable-outbox cursor-based TTL sweeping.

**Expected output:** A repository API that makes duplicate registration, registration-after-close, concurrent draw, partial reads, repeated draws, winner repetition, and TTL extension structurally difficult.

**Verification:** `uv run pytest tests/test_contest_repository.py -q`.

**Acceptance evidence:** Tests inspect exact keys, conditions/transactions, pagination continuation, conditional-failure outcomes, creation/draw crash boundaries, winner/announcement history, second-page TTL retry, alias/participant expiry equality, terminal orphan behavior, and unchanged 30-day expiry across redraws.

**Parallel:** No; this contract is prerequisite for orchestration.

### Task 2 — Implement contest recognition, lifecycle orchestration, and Telegram evidence

**Files:** Create `src/bot/services/contest.py`, `tests/test_contest_service.py`; minimally modify `src/bot/services/telegram.py` and its tests.

**Allowed scope:** Confirmed hashtag/text rules, strict official-root checks, cached `getMe` bot identity and bot-admin prerequisite, participant recognition, `🎉`, uniform `secrets.randbelow` reservoir selection, fixed Kazakh messages, HTML-safe bounded dynamic fields, winner direct reply, deleted-entry root fallback, pending-announcement replay, terminal orphan handling.

**Expected output:** Deterministic eligibility and state behavior with no LLM or memory-retrieval dependency.

**Verification:** `uv run pytest tests/test_contest_service.py tests/test_telegram_client.py -q`.

**Acceptance evidence:** Outgoing Telegram payload assertions show the rules under the root and winner announcement under the saved accepted comment; malicious HTML/max-length snapshots stay safe; failure/retry tests prove the same winner is replayed and no main-chat spill occurs.

**Parallel:** No; depends on Task 1.

### Task 3 — Wire webhook observation and owner/admin commands

**Files:** Create `src/bot/services/handlers/contest.py`; modify `app.py`, `main.py`, `core/dispatcher.py`, repository/handler exports, `repositories/sqs.py`, `sqs_task_router.py`, `webhook.py`, `infra/components/bot.py`, `tests/conftest.py`, `tests/test_dispatcher.py`, `tests/test_webhook.py`, `tests/test_sqs_task_router.py`, and `tests/test_infra_configuration.py`.

**Allowed scope:** Lazy repository injection, one pre-memory observation call when captcha/spam did not short-circuit, `/contest` registration, reply-anchor lookup, live exact Telegram status checks, best-effort main-queue TTL sweep enqueue/routing, webhook 5xx retry for persistence/overlap failures, independent bounded outbox recovery, and its always-on production EventBridge seed.

**Expected output:** Contest updates are recorded before the group agent can consume them, but all existing AI/memory/ambient paths still run; captcha and spam remain higher priority.

**Verification:** `uv run pytest tests/test_webhook.py tests/test_dispatcher.py tests/test_contest_service.py -q`.

**Acceptance evidence:** Tests prove spam/captcha never register entrants, accepted contest messages still reach existing memory/agent mocks, permission/anchor failures do not mutate contest state, and failed/incomplete TTL pages re-enter the existing retry path.

**Parallel:** No; depends on Tasks 1–2.

### Task 4 — Add target-perspective acceptance scenario and documentation

**Files:** Create `tests/test_contest_acceptance.py`; modify architecture/agent skill files and English/Kazakh/Russian READMEs.

**Allowed scope:** One representative multi-user flow and current-state documentation only. Do not add deployment configuration or historical backfill.

**Expected output:** A maintainer and group owner can understand activation, accepted comments, commands, permissions, redraws, retention, and failure limits from current docs.

**Verification:** `uv run pytest tests/test_contest_acceptance.py -q`; documentation links/commands checked by pre-commit.

**Acceptance evidence:** The scenario's captured Bot API calls form the non-live Telegram transcript promised by the plan.

**Parallel:** Documentation can run after the service contract stabilizes; acceptance test depends on Tasks 1–3.

### Task 5 — Integration review and full validation

**Files:** All files changed by Tasks 1–4.

**Allowed scope:** Fix only defects revealed by review/tests; do not broaden V1.

**Expected output:** No duplicate truth path, no partial-page draw, no unauthorized transition, no regression to captcha/spam/AI routing, and no format/lint failures.

**Verification:** `uv run pytest tests/ -q` and `uv run pre-commit run --all-files`.

**Acceptance evidence:** Preserve command output and test counts for the PR summary. If no real Telegram group is exercised, label live acceptance unproven.

**Parallel:** Reviewer may inspect while full tests run, but fixes and final proof are serialized.

### Task 6 — Publish for review

**Files:** Stage only the intentional feature, tests, plan, and docs.

**Allowed scope:** Conventional commit and draft PR against `main`; no merge and no deployment.

**Expected output:** Branch `feat/contest-random-winner`, commit `feat: add fair Telegram contest draws`, pushed to `origin`, with a draft PR describing contract, risks, validation, and live-acceptance limitation.

**Verification:** `git status --short`, `git diff --check`, `git log -1 --oneline`, and PR metadata.

**Acceptance evidence:** Draft PR URL plus exact validation summary.

**Parallel:** No; final gate only.
