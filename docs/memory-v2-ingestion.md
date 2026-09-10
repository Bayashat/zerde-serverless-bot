# Memory V2 ingestion and recovery (Z06 / #163)

This slice adds the source lifecycle and a reference-only worker to Z05. It does
not enable a group, call a real model, modify AWS, or establish production latency.
The shared webhook/Lambda/IAM wiring is integrated separately by the root owner;
Z13 moderation receipts and Z07 extraction are required for the complete path.

## One source version owner

`MemoryRepository` owns every source/control/work state transition in the V2 table.
`FactWriter` alone commits facts. `MemoryIngestion` coordinates trusted moderation
and queue adapters and never substitutes moderation-formatted text for evidence.

The webhook first calls `observe(SourceEvent)`, before moderation branches. This
updates only `OBSERVATION#message_id`: source revision, original/edit time, actor,
hash, epoch/generation and flags. It accepts metadata invalidation for an empty or
unsafe edit; identity or original-time changes, old edits and revoked epochs fail.
Same-second edits with different hashes conservatively advance the observation
once and mark it ambiguous; repeated/older deliveries cannot make it current again.
Only a strictly later edit clears ambiguity. `MemorySourceConflict` identifies
permanent old/ambiguous deliveries for webhook acknowledgement; ordinary
`MemoryConflict` remains retryable storage CAS contention. Promotion and fact reads reject this
state. The stored hash contains no recoverable body. Existing facts require both current
OBSERVATION and accepted HEAD versions, so an edit invalidates them immediately,
even when the new text is rejected or still waiting for review. Initial observations
must be after activation. An already retained source edited after its 30-day raw
window can invalidate facts but cannot be learned again.

| Key family | Body and retention | Lifecycle |
| --- | --- | --- |
| OBSERVATION#id | Metadata only; initial TTL at original + 30 days | Sole source revision owner; first fact atomically removes TTL alongside HEAD |
| CANDIDATE#id#version | Safety-filtered original text and quote offsets; logical and physical 24-hour expiry, capped by raw expiry | Never a retrieval/model source; deleted on promotion/rejection/expiry |
| ADMISSION#id#version | Body-free reference, actor/generation, canonical and moderation hashes | PENDING_REVIEW -> ACCEPTED / REJECTED / EXPIRED; terminal coverage uses the same CAS transaction |
| HEAD / RAW / WORK | Existing Z05 owners; RAW expires at original + 30 days | Accepted atomically only after trusted safe admission |
| COVERAGE#UTC-day | Outcome counts, no body or excerpts; 90 days | Incremented in the same transaction as the corresponding terminal state |
| pk=RECOVERY, sk=lane | Cursor and revision only | Bounded sweeps resume across invocations, including filtered empty pages |

Pending ADMISSION metadata outlives its candidate by seven days so TTL GC does not
silently erase expiry reporting. An accepted ADMISSION keeps its receipt case ID
and has no TTL until the CLEAN receipt is acknowledged. After ACK it gets seven
days; recovery also repairs a lost local completion write after a successful remote
ACK. This is an outbox proof, not another fact/profile source. Z09 deletion and Z10
manifests must explicitly include observations, admissions, candidates and coverage
scope; retained pointers cannot be removed while valid facts/history need them.

## Admission API and authorization boundary

`MemoryIngestion(repo, moderation_repo, queue)` exposes synchronous methods:

- `observe(event)`: metadata invalidation, before moderation.
- `prepare(event, moderation_input_hash)`: idempotent observation plus quarantined
  candidate/admission. Use the returned exact source_ref in SPAM_CHECK.
- `accept_safe(event)`: only the webhook's deterministic CLEAN or explicit
  review-exempt lane. ENQUEUED, UNKNOWN and REJECTED branches never call it.
- `reject(chat_id, ref)`: exact-version rejection and body removal.
- `promote_clean(case_id)`: fetch the immutable Z13 receipt, validate its exact
  identity and hash, promote canonical candidate text, then acknowledge CLEAN.

`moderation_input_hash(text, context)` matches Z13's hash of its formatted moderation
input; it is distinct from the source hash. Promotion checks the stats table row's
kind, CLEAN state, pending outbox, non-guest flag, chat/user/message, full source ref
and expected moderation hash in the *same DynamoDB transaction* as candidate expiry,
OBSERVATION/control/subject fences and HEAD + RAW + WORK. The app injects the trusted
moderation repository/table. No caller-provided boolean, arbitrary predicate or
receipt body authorizes learning. Lost acceptance responses and lost ACKs replay
through the exact ADMISSION state; stale/expired candidates receive EXPIRED ACKs.
A temporary learning pause returns PAUSED without deleting the candidate or
acknowledging its receipt; actual expiry/revocation still becomes EXPIRED. In a
concurrent accept/edit race, ACK follows the persisted ADMISSION terminal state,
so an already ACCEPTED source is never acknowledged as EXPIRED.
Malformed receipts remain pending with a visible recovery error and cannot block
later valid rows in the sweep.

CLEAN recovery acknowledges only INGESTED or EXPIRED. A revoked/expired source never
re-enters an epoch. Raw Telegram deletions are not automatically observable through
the ordinary Bot API; explicit deletion uses Z09's control/revision protocol.

## Worker and queue protocol

`MemoryQueue(queue_url)` requires an explicit independent URL and never falls back
to the captcha/main queue. Its JSON payload is exactly:

```json
{"schema":2,"task_type":"PROCESS_MEMORY_V2","chat_id":"-100123","source_ref":{"source_id":"8","source_version":1,"epoch":"example"}}
```

It includes no text, username, prompt or provider result. Initial delivery is best
effort after the pending transaction; failure leaves recoverable work. The root
Lambda adapter awaits `MemoryWorker.handle_records(records)`, which returns standard
SQS `batchItemFailures`. Invalid/legacy body payloads fail for DLQ handling.

`MemoryWorker(repo, extractor_factory, sizing_fn=...)` injects an extractor through
`extractor_factory(validate_sources)`. `ExtractionSource` and `ExtractionResult`
live in models.py; extraction cannot choose another author or write facts.
`validate_sources` rechecks current CONTROL, subject generation, OBSERVATION,
HEAD/RAW, WORK ownership and logical expiries. Z07 calls it before each of at most
two provider attempts, including after budget reservation and immediately before
network I/O. Provider attempts have 20-second deadlines. The worker adds a 50-second
batch ceiling and stops starting model work before its 100-second local deadline.
Its persisted lease is 130 seconds, beyond the Lambda's 120-second maximum; a dead
invocation's lease becomes recoverable without a second concurrent owner.

Batches contain one chat, at most 20 messages, and at most 8,000 bytes for Z07's
complete serialized request, including system instructions and schema. This is a
conservative token upper bound, not a tokenizer estimate. The same sizing function
is used by worker and extractor. Batches split without truncating evidence; a single
oversized message becomes FAILED/input_limit and increments coverage. Live provider
usage validation remains required before relaxing this conservative bound.

PENDING -> LEASED -> DONE is conditional; facts/history, both retained pointers and
DONE commit atomically. Empty complete output explicitly means no facts. Provider,
schema or budget deferral returns to PENDING with a future due time; it never
pretends no-fact success. Budget reasons can defer until the UTC monthly reset.
Paused work remains visible. EXPIRED/FAILED/DONE leave the due index. Group admin
confirmation WORK has no due-index fields and cannot enter model extraction.

## Recovery, coverage and limits

The root's sole EventBridge recovery invocation uses `RECOVER_MEMORY_V2`; it does
not enqueue a recovery task on the shared main queue. `MemoryRecovery(ingestion).run()`
uses a 90-second local deadline, up to four 100-item pages per lane by default, and
saved CAS cursors. It scans the four `work-due` shards, expired/admitted candidate
metadata, and Z13's pending CLEAN receipts. GSI results are hints followed by strong
base-row reads. A queue outage, poison receipt or stale checkpoint cannot acknowledge
unprocessed work. Failed rows remain pending; the sweep advances and then fails
visibly so alarms/retries can act without permanently starving later pages.

`coverage_snapshot(chat_id)` exposes pending/leased/paused/terminal counts, oldest
pending age, outcome counters and sample counts/p95 for normal versus recovery-marked
completions. WORK diagnostic samples retain seven days after completion; counter
rows retain 90 days. P95 is based on observed completions, includes moderation delay,
and is never called meaningful with zero samples. It is not precision/recall or proof
that all chat traffic was learned. Backlog and logical expiry remain visible under
budget/provider outages. Scans and diagnostic queries are bounded operational work
whose real cost and freshness need deployment evidence.

Targets remain normal learning p95 <= 5 minutes and lost-delivery recovery <= 10
minutes, measured separately after deployment. Local Moto transactions and fake
queues/providers prove only the tested code semantics. They do not prove real AWS
permissions, actual throughput/latency, provider accuracy or Telegram acceptance.
