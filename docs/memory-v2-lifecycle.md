# Memory V2 correction, deletion, and answer leases (Z09 / #166)

This slice implements the lifecycle over Z05/Z06's single V2 table. Telegram parsing,
configured-group authorization, scheduling and actual sending are owned by the app
integration. Local Moto/transport fixtures are implementation evidence; no live user
records, AWS resources or Telegram messages were changed.

## Answer contract

`AnswerLeaseService(repo)` provides:

- `acquire(chat_id, subject_ids, request_id=...) -> AnswerLease`: one to eight existing
  active subjects, CAS with CONTROL/subject revisions; no subject creation on an ask.
  The request ID is hashed. Each lease has a random token and a fixed 360-second end.
- `snapshot(lease) -> list[dict]`: current profile facts, with evidence/freshness. It
  checks FACT/HEAD/OBSERVATION and actual evidence authors, then atomically checks
  CONTROL and all participating subject/author revisions. Every fact mutation changes
  its subject revision; every source invalidation changes its author revision.
- `bind(lease, fact_refs) -> AnswerLease`: select at most 16 exact references shaped
  `{fact_id: str, fact_version: int}`. The service reads evidence from its owner, checks
  all selected facts/pointers/authors and CAS-binds their metadata to the lease. An
  already-bound lease cannot choose another set. Use the returned revised lease.
- `validate(lease, fact_refs)`: selected references must exactly match the binding.
  Strong reads plus a final transaction recheck the live state. More than 40 seconds
  must remain both before and after the transaction for a bounded send. Snapshot and
  bind also recheck the time after their final transaction; slow SDK calls cannot
  return an expired permission.
- `release(lease)`: token-scoped, idempotent, including a caller's pre-bind view.
  RELEASED metadata keeps a seven-day TTL to prevent reopening the same request ID.

No question, answer or excerpt is stored in a lease. A GROUP fact binds its actual
administrator evidence author too. An unbound lease conservatively covers the whole
chat during deletion. More than 98 distinct snapshot fences fails explicitly rather
than silently truncating the profile. Leases never renew. Bot Lambda is bounded to
300 seconds; V2 Telegram sends must be bounded and have no implicit HTTP retries.
Database/Telegram operations are not one transaction and do not promise exactly-once
sending. The app must distinguish a known request from an unknown send outcome.

## Deletion protocol

`MemoryLifecycle(repo, derived_cleaners=...)` exposes `begin(chat_id, scope=..., target=...,
optout=False)`, `advance(chat_id, job_key, max_pages=4)` and bounded `recover()`.
The app verifies permission before `begin`; `MemoryCommandService` supplies this boundary.

1. `begin` atomically registers PURGE and its control fence. Subject deletion sets
   STOPPING, increments generation and optional optout. Source deletion marks its
   OBSERVATION deleted, increments source and author revisions. All begin operations
   increment CONTROL revision; group deletion also sets group STOPPING. Concurrent
   scope deletions in a chat serialize, rather than interfering with each other's fences.
2. WAITING prevents success confirmation until matching answer and extraction leases
   finish or reach their fixed deadlines. Lease inventory is bounded; for a larger
   inventory the conservative wait is at most 360 seconds from the fence. No answer
   acquired after the fence can bind a pre-deletion snapshot.
3. DELETING queries strongly in 40-row pages. Conditional deletes and the next cursor
   commit together. Other users and non-chat partitions such as the shared budget are
   preserved. The purge covers RAW, CANDIDATE, ADMISSION, WORK, FACT, HISTORY, and V2
   ANSWER_REQUEST / ANSWER_REPLY reference metadata when their actor, subject, source,
   or evidence author matches. Source author lookup resolves actor-free candidates
   before their observations are removed. Subject controls and the purge proof remain.
4. Registered derived owners must return `True` before completion. An error or `False`
   keeps DERIVED pending. Current Z07 trends are a pure function, with no persisted
   projection to delete; introducing a new persistent projection requires registering
   its cleanup owner and testing edit/forget invalidation. Missing future integration
   is not evidence that such a projection was cleared.
5. DONE changes a subject back to ACTIVE with a new message cutoff, or a group to
   STOPPED. Optout remains true until an explicit self optin. The one-second conservative
   cutoff rejects old deliveries within the same Telegram timestamp second. Source
   deletion keeps only an ID/epoch/deleted tombstone, without actor, hash or text, so a
   duplicate webhook cannot recreate it. Control generation/optout metadata is retained
   deliberately as the anti-revival boundary. Restarting a purged group creates a new
   non-reusable epoch and respects its purge cutoff.

Recovery stores a CAS cursor in `RECOVERY/purges`, keeps filtered empty pages, and tries
other jobs before reporting item failures. The app can give it a short time budget in
its existing recovery invocation. Until a job is DONE, user-facing text must say that
learning is fenced and cleanup is pending, rather than confirming erasure.

Moderation outcomes are separate business records; they contain no source body and are
not deleted by this memory purge. Delayed CLEAN receipts can only be acknowledged as
expired after their canonical source has been erased; they cannot recreate a fact.
Operational backups/PITR/log retention and messages already sent to Telegram are not
physically removed by this service. Those copies have their separately documented
retention boundaries. Unknown, expired, or purged reply receipts must never cause the
app to rebuild old memory context from Telegram's quoted bot answer body.

## Commands and sole fact writer

`MemoryCommandService(repo, lifecycle, authorize=...)` uses a live authorization
callback: `authorize(chat_id, actor_user_id, require_admin=bool) is True`. False or a
read failure cannot mutate memory. The initial app integration enables configured
groups only; private chats provide explanations rather than private memory access.

| Syntax | Boundary |
| --- | --- |
| `/memory about me` / `/memory about group` | `about_subject` returns the authorized scope; the sole answer renderer uses leases |
| `/memory wrong <fact_id>@<version>` | Self fact, or currently authorized administrator for GROUP; reject exactly that version |
| `/memory correct <fact_id>@<version> <value>` | Same permission; new personal Telegram command with exact value evidence |
| `/memory group confirm <rule\|decision> <value>` | Current administrator; explicit new group rule/decision |
| `/memory forget this <source_id>` | The original source author only |
| `/memory forget me` | Clear the caller's old profile and evidence; future messages may learn after completion |
| `/memory forget group` | Current administrator; stop group memory and clear its data |
| `/memory optout` / `/memory optin` | Caller only; optout includes cleanup and retains the future-learning prohibition |

New correction/group-confirmation messages use `source_kind=confirmation`; the webhook
must exclude exactly those parsed new commands from ordinary message observation.
Edited commands never execute a correction or confirmation. Editing an existing source
into a command must still advance ordinary OBSERVATION first, invalidating its old facts.

`FactWriter` remains the only fact writer. Wrong marks the exact version REJECTED,
retains source ordering and feedback, and increments the target subject revision in
the same transaction. Correction uses a separate authenticated self-confirmation lane
or the existing administrator lane, with exact command evidence and expected fact
version. A multi-value correction retracts its selected previous value and asserts the
replacement together. Work DONE, facts/history and source pointers commit together;
negative feedback survives in history when a later explicit correction replaces it.
No model can manufacture the command authorization objects or choose another author.
