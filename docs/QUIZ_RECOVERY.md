# Quiz publication and answer recovery (Z16 / #173)

This implements the local code contract in [Z16](goals/zerdebot-memory-v2/issues/Z16.md).
It does not deploy resources, invoke Telegram, or prove a real poll is scoreable.
The public Bot router/webhook, SQS producer, live-admin command and five-minute
recovery schedules are wired in the integration slice. Deployment readback and the
old-writer drain below remain release gates.

## One owner for each state

Both Lambdas use the existing Quiz DynamoDB table (`PK`, `SK`). `PollIdIndex` remains
only for legacy publications. No new scoring table, generic workflow framework or
second score writer is introduced.

| Owner | Keys | Meaning |
| --- | --- | --- |
| Quiz `QuizRepository` / `_publication.py` | `QUIZ_EXEC#chat` + `DATE#Almaty-date` or `REQUEST#command-message-id` | Durable intent, generation, draft, send state, action lease |
| Same publication owner | `POLL#poll-id` + `META` | Strongly readable, immutable scoring lookup bound to execution generation |
| Same publication owner | `QUIZ#chat` + request key | Completed publication record; daily uniqueness also respects old records |
| Same publication owner | `QUIZ_PUBLICATION_OUTBOX` / `QUIZ_PUBLICATION_RECOVERY` | Reference-only pending work and persisted traversal cursor |
| Bot `QuizRepository` / `_quiz_answers.py` | `ANSWER#poll-id` + `USER#user-id` | Immutable accepted choice, receipt revision, retry/terminal state |
| Same answer owner | `QUIZ_ANSWER_OUTBOX` / `QUIZ_ANSWER_RECOVERY` | Pending references, due times and persisted traversal cursor |
| Same answer owner | `SCORE#chat` + `USER#user-id` | Score and streak projection, updated with answer revision CAS |
| Same answer owner | `QUIZ_ANSWER_COVERAGE` + `TOTAL` | Atomic terminal counts, including expired unknown answers |

The old `save_quiz_record`, per-deck save helpers and `update_score_correct/wrong`
paths are removed. Generation and bank selection remain within the current Quiz
service. Bank import/maintenance and existing leaderboard/season operations are
separate existing business operations; their publication/reset workflow is not
made transactionally idempotent by this issue.

## Publication protocol

`GENERATING → PREPARED → SENDING → SENT → DONE` is persisted with revision and
generation CAS. A 330-second lease exceeds the current maximum 300-second Quiz and
Bot Lambda writer durations. Increasing either writer timeout requires increasing
this lease first. A live lease cannot be claimed by another language or invocation.

Daily identity is per chat/date, irrespective of language, derived from the original
EventBridge `scheduled_at` (or native event `time`), never the retry's wall clock.
The same scheduled event crossing Almaty midnight still refers to the previous
date and its difficulty. Missing or timezone-less scheduler timestamps are explicit
nonretryable input errors. On-demand identity is
the originating Telegram command/reply message ID in that chat. Missing IDs are
nonretryable input errors; random Lambda request IDs cannot stand in for a command.
Scheduled timestamps over five minutes in the future also fail before persistence.
The scheduled Lambda converts an input-error result into an exception so a broken
input transformer triggers the existing Lambda Errors alarm; platform retries are
bounded but cannot repair the invalid event by choosing the current time.
The first request persists its language/topic/difficulty before generation, and
recovery uses that original intent. Unsent daily intents expire at the end of their
Almaty date; unsent on-demand intents expire after 24 hours. `EXPIRED` never sends.

The draft and `SENDING` intent precede the network call. `sendPoll` makes one HTTP
attempt with urllib3 retries disabled. A Telegram JSON rejection with a matching
4xx error code returns to `PREPARED`; transport failure, 5xx, incomplete metadata or
interruption while `SENDING` becomes `UNKNOWN`. An expired sender lease also becomes
`UNKNOWN`. Unknown sends never trigger an automatic replacement poll.

After a valid response, one native DynamoDB transaction binds the execution and
primary `POLL#...` lookup. A second transaction writes the final record, completes
the execution, removes its outbox and applies eligible deck rotations. Thus a
record collision or finalization outage cannot erase a successfully persisted poll
lookup. Daily `failed[]` produces a non-success result; scheduled daily failure
raises so the invocation is visible to operational alarms/retry. A collision retains
the known poll in `CONFLICT`, with its original scoring identity.

Deck snapshots are captured when read. Publication completion conditionally applies
only unchanged snapshots and marks `rotation_conflicts` when a later execution has
already advanced a deck. A failed completion does not consume the next question;
a late completion cannot roll a newer deck back. The 5-minute publication recovery
action persists its cursor before each possibly slow generation, so one failing
row cannot indefinitely starve later rows. It starts no further row after its
200-second elapsed-time check; the Lambda's 300-second limit remains the outer bound.

There is an unavoidable external-system gap: if Telegram accepted a poll but every
attempt to persist its response failed, only the original send intent survives.
That execution becomes `UNKNOWN` and requires reconciliation. This code does not
claim exactly-once Telegram delivery or invent a poll ID to fill that gap.

## Reconciliation and Bot API compatibility

The public command must freshly verify a live administrator in the source group,
an actual reply to this bot's poll, and the restricted Bot-to-Quiz invoke permission.
The Quiz domain also requires the exact execution generation, chat, own-bot author,
message ID/date, non-forwarded quiz, question, options, single correct answer and
single-choice/no-revoting policy. The Telegram message date must lie within that
execution's send window (5-second clock allowance, at most its 330-second lease).
If required metadata is absent, it remains `UNKNOWN`.

Telegram does not echo our generation. If multiple unknown sends of an identical
question fit the same receipt, the bounded, strongly consistent reconciliation
search refuses to guess. It examines at most 1,000 execution records for the chat;
exceeding that bound is also an explicit unresolved result. A poll already bound
to another generation cannot be reassigned.

The sender uses the current [Bot API sendPoll contract](https://core.telegram.org/bots/api#sendpoll):
`correct_option_ids: [index]`, `allows_multiple_answers=false`, and
`allows_revoting=false`. Returned options and correct-answer mapping are validated
before scoring, including shuffled options. Legacy singular `correct_option_id`
is accepted only when it describes one correct answer. Bank source labels in poll
questions are plain text; ordinary bold HTML is not a supported question parse mode.

## Answer and recovery protocol

`handle_poll_answer` first commits the answer receipt and outbox atomically. It
then best-effort enqueues only `poll_id` and `user_id`. Persistence failure raises
`QuizAnswerRetryRequiredError`; the public webhook must return HTTP 500. Enqueue
failure keeps the receipt and is recovered by the schedule. Empty withdrawals,
multiple choices, anonymous voter-chat answers and malformed IDs/options do not
create scoring work. This product disables revoting, so the first valid persisted
choice owns scoring; a duplicate never changes that choice.

`lookup_poll` first strongly reads `POLL#id/META`. Only if absent does it consult the
legacy GSI. Missing, malformed or logically expired TTLs are not valid polls. A GSI
miss is retained as `PENDING`; database exceptions propagate and do not consume an
unknown-poll attempt. After 12 lookup misses at five-minute intervals, the receipt
becomes `UNRESOLVED` and retries hourly. All pending work has a hard seven-day
logical expiry, regardless of delayed DynamoDB TTL deletion. At expiry, a transaction
sets `EXPIRED`, removes the outbox and increments the coverage count.

The approximate maximum unresolved lookup schedule is 12 frequent attempts plus
at most 168 hourly attempts. Recovery still reads reference metadata on its page
traversals, but future-due rows do not enqueue or perform a GSI lookup. These are
bounded retry counts, not an AWS billing estimate or a bill cap. `answer_coverage()`
returns persistent terminal counts; `answer_pending_coverage()` reports pending vs
unresolved, future-due, expired-due and oldest age, explicitly flagging when its
1,000-row scan is incomplete. Nothing here counts unknown answers as successfully
learned or scored.

For a known poll, score arithmetic, answer completion, outbox deletion and coverage
increment form one transaction. The score's `answer_revision` serializes concurrent
answers. The valid poll and fresh answer expiry are checked within that transaction.
Legacy `answered_poll_ids` still prevents replaying old scores, but no new IDs are
appended to that unbounded list. New receipt rows retain dedupe for 90 days, matching
poll retention. Outboxes do not expire independently before acknowledgement;
orphaned markers after prolonged shutdown are removed only after their logical
expiry and an atomic check that the source receipt/execution is absent.

Points earned on on-demand quizzes count toward the all-time total only. Daily
answers count toward the current week only when their persisted receipt belongs
to that week. Late older answers can add earned total points but cannot reset a
newer streak. Receipt time plus Telegram update ID defines ordering; no historical
streak reconstruction is claimed. Existing weekly/season reset operations keep
their prior semantics and are not automatically retried as publication recovery.

## Public integration API

- `SQSClient.send_quiz_answer_task(poll_id, user_id)` emits exactly
  `{"schema":2,"task_type":"PROCESS_QUIZ_ANSWER","poll_id":"...","user_id":"..."}`.
- `process_quiz_answer_task(*, repo, body)` returns `state` and optionally
  `next_attempt_at`; retryable storage failures propagate.
- `recover_quiz_answers(*, repo, sqs_repo, limit=100)` handles one persisted page;
  its five-minute task must run even when no group list is configured.
- Quiz Lambda `action="recover_publications"` calls
  `QuizService.recover_publications(limit=50)` on a five-minute schedule.
- Daily EventBridge input must preserve `scheduled_at` from `$.time`; retries and
  manual replay must pass the original timestamp instead of creating a fresh date.
- Quiz Lambda `action="reconcile"` requires `chat_id`, `request_key`, `generation`,
  `poll_message`, and `bot_user_id`, supplied by the authorized live-admin adapter.
- On-demand calls must include their original positive `reply_to_message_id`.

## Release and evidence boundary

Before enabling the new paths, stop new Quiz sends briefly, update both writers and
wait for every old invocation to finish (at least the old maximum duration, with
configuration/invocation evidence). An old unconditional score/deck writer must
not overlap the new CAS protocol. Existing polls remain readable through the legacy
GSI and old score dedupe list. Include the SQS producer/router, webhook retry catch,
both recovery schedules, their alarm routes and restricted admin command in the
same release gate. Retrying a DLQ message uses the same stable reference; it never
constructs another poll send from old payload text.

Local evidence uses Moto's native resource-client transaction semantics and fake
Telegram/provider responses. For a two-thread CAS test, only Moto's atomic server
operation is serialized because its internal rollback snapshot is not thread-safe;
the workers still read the same stale score before competing. This is simulator
evidence, not real DynamoDB isolation, GSI propagation, Lambda timing or Telegram
delivery evidence. Actual dev then production poll/answer tests, deployment readback
and a real uncertain-send reconciliation remain unproven until separately authorized.

## Runtime wiring

`/quizreconcile <request_key> <generation>` must reply to this bot's existing poll
in a configured group. The adapter calls live `getChatMember`, requires that exact
user to be administrator/creator, and constructs only the restricted `reconcile`
event. Bot ownership alone does not bypass group authorization.

Both recovery rules exist even without configured chat lists and follow the
existing dev on-demand switch. News and Quiz async invocation failures retain
Lambda destination envelopes in the unconsumed main DLQ after at most two retries
and six hours. EventBridge target delivery separately has three retries and a
one-hour age limit. Operators must inspect those envelopes and replay the original
business identity; destination envelopes are not SQS task bodies.

News receives only `GetItem`/`UpdateItem` for `news_manifest#*` and `news_delivery#*`
in the existing stats table. Daily Quiz and each News slot retain EventBridge's
original timestamp; a retry cannot create a new publication date.

Runtime integration evidence (2026-09-11): full local suite 1,178 passed on Python
3.13.6; independent public/domain/IAM review ran 129 focused cases. A fresh dev CDK
synthesis built all six real assets, imported in the pinned ARM64 Lambda Python
3.13.15 image with networking disabled. This verifies packaging and local wiring,
not deployed permissions or a real Telegram poll. No cloud mutation was performed.
