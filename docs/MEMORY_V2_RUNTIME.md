# Memory V2 runtime integration

Status: **IMPLEMENTED_UNPROVEN**. This connects the independently reviewed Z01,
Z04–Z07, Z13 and Z17 changes. It does not activate a chat, delete old data, or
establish model quality or real Telegram acceptance.

## Admission and ownership

`services.memory_v2.runtime` is the single lazy composition module shared by the
webhook and dedicated worker. Missing V2 table or queue configuration cannot fall
back to the legacy table or mixed business queue. Configured storage still requires
an explicit ACTIVE V2 control record; no deployment seed creates one.

The authenticated, whitelisted webhook converts only the original message text or
caption. Replied text, attachment contents and model-produced media analysis are
never canonical sources. Telegram UTF-16 blockquote offsets are converted to Python
character spans. Invalid quote ranges conservatively mark the whole body quoted.

Every eligible personal message first advances source observation metadata, before
captcha and spam decisions. Empty, unsafe or command edits can therefore invalidate
an existing fact without becoming learning input. Deterministically obsolete or
same-time ambiguous edits are acknowledged without learning; a transaction conflict
or database failure returns HTTP 500 for redelivery.

Captcha-pending, enforced and queued messages cannot use the safe admission lane.
For queued moderation, the original body is staged in V2 with the exact moderation
input fingerprint. The SPAM_CHECK task receives only a source reference in addition
to its existing classification payload. A persisted CLEAN receipt authorizes promotion
through a cross-table transaction. The original staged body, never the task's text
or replied context, becomes RAW/HEAD/WORK. A failed enqueue remains recoverable from
WORK. A pending or unavailable review never silently becomes clean.

Immediate CLEAN processing asks the same ingestion owner to promote, reducing normal
learning latency. A five-minute recovery invocation covers failed deliveries and
manual-review completions. Paused admissions remain pending; actual expiry is
reported separately. See [ingestion states](memory-v2-ingestion.md).

## Infrastructure and costs

- One independent `zerde-serverless-memory-v2-queue-{env}` and DLQ; the main bot may
  send to it but cannot consume it. The worker cannot consume the mixed business queue.
- Worker: Python 3.13 ARM64, 512 MB, 120-second timeout, maximum concurrency two.
  SQS batches up to 20 references with a 20-second window; visibility is 740 seconds
  (six invocation timeouts plus the batching window), partial batch failures enabled.
- Recovery: EventBridge every five minutes, exact schema-2 recovery event, bounded
  four-page runs with durable progress maintained by the domain recovery owner.
- Dev defaults idle: worker reservation zero, mapping and recovery disabled, no dev
  alarms. An ACTIVE control record alone does not start an idle dev runtime.
- Worker IAM reads only the Gemini SSM secret, accesses its own V2 table, and uses
  scoped moderation/quota keys in the stats table. Receipt recovery uses a metadata
  projection on Scan; DynamoDB Scan does not support a LeadingKeys condition.
- Dev and prod model calls share the **prod V2 cost ledger**. Dev permission on that
  table is restricted to `MEMORY_BUDGET#*` and `MEMORY_ATTEMPT#*`; it cannot query or
  scan prod profiles. A missing/unavailable shared ledger stops optional calls.
- Active runtime adds five actionable worker/queue alarms, bringing this integration
  to 22 alarms. Both alarm and recovery notifications use Z17's private operations
  transport. Model budget semantics are in [the cost contract](MEMORY_V2_BUDGET.md).
  Project tags still require account activation; this is not an AWS billing hard cap.

The worker's SQS-processing DLQ and asynchronous recovery delivery failures use the
same dedicated DLQ. Their envelopes differ: SQS task bodies are schema-2 references;
EventBridge/Lambda failure envelopes must be inspected as metadata and routed back
to the recovery entrypoint. Do not feed an arbitrary failed event into fact writes,
purge a mixed queue, or replay an expired epoch.

## Build and acceptance

`httpx`, `httpcore` and `dnspython` are explicit locked bot/news dependencies. The
shared asynchronous transport resolves DNS without a blocking resolver thread,
preserves the original HTTP host and TLS name, and permits cancellation of DNS,
connection and response reads. Outer request deadlines still do not promise an
absolute deadline for unrelated synchronous AWS SDK or CPU work.

CDK layer annotations use `ILayerVersion`, verified under Python 3.13 rather than
relying on Python 3.14's deferred annotation evaluation. The strict asset probe registers the
sixth handler, `memory_worker_main.lambda_handler`; a newly added unregistered handler
fails verification. Template tests use stub code and are not packaging proof.

Run the complete tests, actual CDK synth and
`scripts/verify_lambda_bundles.py` against that fresh assembly. The latter imports
all six real packages in the pinned Python 3.13 ARM64 Lambda image with networking
disabled. Test moderation/source/fact transactions against the real boto3 Resource
serialization and Moto, including a classification payload containing someone else's
quoted text, to prove the admitted body remains the author's original message.

Before activation, integrate Z08/Z09 budget, answering and deletion boundaries, run
Z10 cleanup rehearsal, and pass Z11's synthetic and real-world gates. Read back actual
Lambda timeouts, queue settings, IAM, alarm actions and current control state after
any separately authorized deployment. A queue message or successful Lambda invocation
alone does not prove a correct profile. Failure recovery remains explicit question
answering without long-term memory; legacy learning must stay retired.
