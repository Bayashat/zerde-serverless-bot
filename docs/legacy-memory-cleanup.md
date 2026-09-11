# Legacy memory cleanup operator contract (Z10)

The implementation is an **offline-tested operator tool**, not evidence of deployment,
production backup, deletion, or physical erasure. It does not enable Memory V2.
The original memory-only authority is [PLAN section 3](goals/zerdebot-memory-v2/PLAN.md), issue
[#167](https://github.com/Bayashat/zerde-serverless-bot/issues/167), the
[Z03 deletion allowlist](legacy-memory-deletion.md), and [Z01 cutover](MEMORY_CUTOVER.md).
Resource deletion in [Z18](LEGACY_AWS_CLEANUP.md) remains a separate action.
The subsequent owner-approved retirement of the experimental contest feature in
[PR #204](https://github.com/Bayashat/zerde-serverless-bot/pull/204) adds an explicit
per-contest scope below. It does not widen public `/memory forget` behavior or
authorize this tool to run automatically.

## Current production gate

The historical Z01 slice alone was insufficient: it still wrote explicit-only
`AGENT_REPLY` threads and `MEDIA_GROUP` album membership to the legacy table. The
final V2 source retires those paths, but deployed artifact readback must confirm it.
Before apply, the final cutover must migrate or stop **both** of those writers, every legacy reader,
Bot and vector-indexer writer, import/backfill path, and external writer. Old queue
messages may remain only behind verified retired-task guards. No table or index data
was read from production while developing or rehearsing this tool.

The gate combines reviewed evidence with live AWS readback; it cannot discover or
prove the absence of every external client or infer code semantics from a Lambda
flag. An operator must review the complete writer/consumer/index inventory and the
actual deployed artifact's stop/replay evidence. Setting JSON booleans without that
evidence is not verification. There is no generated “all ready” evidence file.

## Scope and ownership

Run `uv run python -m dev.tools.legacy_cleanup.cli --help` from the repository. The
standalone module does not import runtime bot settings or secrets. Dependencies come
from the repository dev environment. It has no `DeleteTable`, index/bucket deletion,
queue body read/delete/purge, deployment, import, or restore operation.

A private JSON scope file contains the following fields (`retired_contests` may be
omitted for the original memory-only scope and then defaults to an empty list):

```json
{
  "account_id": "123456789012",
  "region": "eu-central-1",
  "table_arn": "arn:aws:dynamodb:eu-central-1:123456789012:table/example-old-memory",
  "index_arns": ["arn:aws:s3vectors:eu-central-1:123456789012:bucket/example-old/index/example-index"],
  "chat_ids": null,
  "confirmed_bot_prefixes": [],
  "retired_contests": []
}
```

These are synthetic identifiers. Replace them only with reviewed exact production
identities. `chat_ids: null` means all canonical `CHAT#<id>` partitions; an explicit
list narrows table records. **Every vector in every specified index is in scope,
including orphans and vectors belonging to other chats.** Chat filtering never
silently narrows an index wipe. Only indexes confirmed to contain entirely retired
memory may be selected. All historical old index ARNs must be enumerated explicitly;
the tool does not guess them from the current environment or delete an entire bucket.

Allowed table families are MSG, MEDIA_GROUP, USER, USERNAME, EVENT, USER_FACT,
GROUP_FACT, JOKE, DAILY_SUMMARY, TERM, AGENT_REPLY, AMBIENT_REACTION, PROACTIVE and
exact `VECTOR_BACKFILL`. BOT_COMMITMENT/BOT_CORRECTION are protected unless their
exact `...#` prefix is explicitly confirmed in `confirmed_bot_prefixes` after review.
SETTINGS, moderation, Quiz, V2 controls, unknown families, other scopes and all other
tables remain protected. CONTEST, CONTEST_RULE and CONTEST_TTL_OUTBOX remain protected
unless the exact contest identity is explicitly selected as described below.
Malformed selected deletion markers abort.
Valid `MEMORY_VECTOR_DELETE#<chat>` markers are included even when their original
source has already gone; markers are deleted only after all specified indexes are empty.

### Explicit retirement of old contest data

To include one reviewed historical contest, set:

```json
"retired_contests": [{"chat_id": "-100", "root_message_id": "10"}]
```

Both values are canonical decimal strings; root IDs must be positive. Every entry
must also fall within `chat_ids`. There is no wildcard, include-all flag, arbitrary
prefix, or whole-partition deletion. The following closed shapes are allowed only
for that chat/root:

| Record | Required identity/shape |
| --- | --- |
| `CONTEST#<root padded to 13 digits>#META` | `kind=contest`, matching numeric root and string chat, known lifecycle status and positive creation time |
| `CONTEST#<root>#PARTICIPANT#<user padded to 20 digits>` | `kind=contest_participant`, matching root/chat/user, positive entry ID and acceptance time, text string |
| `CONTEST_RULE#<rules message padded to 13 digits>` | `kind=contest_rule_anchor`, matching root/chat and rules ID, positive creation time |
| `pk=CONTEST_TTL_OUTBOX`, `sk=CHAT#<chat>#ROOT#<root padded to 13 digits>` | `kind=contest_ttl_outbox`, matching root/chat, positive expiry and creation time, no physical TTL |

The manifest includes each exact key, type and original content hash. A mismatch
inside a recognized selected shape aborts planning/apply; unknown key forms stay
protected for separate inspection and are never guessed from a `user_id` or text.
An alias without an attributable numeric root stays protected. Root selection does
not require a surviving META: TTL may already have removed it, while an independently
validated participant, alias or outbox still has an exact identity. Selecting a root
does not select a neighboring root or the same root in another chat.

All selected bodies, including winners/participants and the global outbox, enter
the same lossless encrypted backup. The tool removes outboxes **after** selected
contest records, preserves the original manifest for retries, and rejects a changed
or recreated row. It never recreates contest state or sends Telegram results.
Restoration remains offline review only: inspect/restore the complete associated
records in an isolated, non-serving table with old writers/recovery disabled;
restoring an outbox into a live retired consumer is not a supported recovery path.
The tool provides no restore operation. Unselected business bodies stay outside the
backup and their complete key/count/content digests must remain unchanged.

## Local artifacts and seven-day deletion deadline

Create a dedicated private directory outside **any** Git checkout (mode 0700) and a
separate, unique, owner-only 32-byte random key file (mode 0600). Keep the key outside
the archive directory. The tool rejects symlink key files and unsafe ownership/modes.
Do not reuse a key across cleanups or place it in shell arguments, logs, Git or GitHub.
Do not point the tool at original Telegram export files; it never needs those exports.

`plan` strongly scans all table pages and enumerates every specified index with data
and metadata. It writes `manifest.zenc`: exact keys, type, content digest, table/index
creation identities, source commit, protected key/count/content digests. Before plan, backup and apply,
the CLI rejects staged, unstaged or untracked changes in the tool package, its local
import roots, pyproject.toml and uv.lock. Backup/apply also require the current HEAD
to equal the manifest commit: restore the exact reviewed checkout or review a new
plan; an unchanged-looking tool on a different commit is not silently accepted.
No dirty diff or source contents are printed. It emits only
counts and hashes. This is a fresh inventory, not the old audit's deletion list.

`backup` re-reads and requires an exact match with the manifest, then writes
`backup.zenc` containing only selected table records plus complete selected vectors
and metadata. Protected business bodies are not copied. AES-256-GCM authenticates the
contents and header, including expiry and digest; lossless encoding preserves DynamoDB
decimals, binary values, sets, and vector floats. No plaintext record body is written.

All three archives (manifest, backup and resumable journal) expire at the original
manifest time plus seven days. Resuming or rewriting a journal cannot extend that
boundary. Apply refuses an expired backup. **Expiry does not erase a file.** The
operator must register a deletion job/owner for this exact deadline before creating a
production backup and retain its completion evidence. `archives` is a local-only,
authenticated inventory that also reads expired headers and reports their content
hashes and deadlines. `expire` previews removal; `expire --execute` unlinks only the
named authenticated, expired archive with the exact supplied content digest. It does
not recursively delete a directory or promise SSD/snapshot physical erasure. After
all archives are removed, destroy the dedicated key and verify any filesystem backup
copies separately. No local expiry job was installed during this implementation.

Operator sequence (paths and hashes are placeholders):

```text
plan     --scope <private-scope.json> --archive-dir <private-dir> --key-file <separate-key>
backup   --archive-dir <private-dir> --key-file <separate-key>
apply    --archive-dir <private-dir> --key-file <separate-key> --evidence <private-evidence.json> --expected-digest <manifest-digest>
apply    --archive-dir <private-dir> --key-file <separate-key> --evidence <private-evidence.json> --expected-digest <manifest-digest> --execute
status   --archive-dir <private-dir> --key-file <separate-key>
archives --archive-dir <private-dir> --key-file <separate-key>
expire   --archive-dir <private-dir> --key-file <separate-key> --archive-name backup.zenc --expected-digest <backup-content-digest> --execute
```

Each line is a subcommand of the module above. Without `--execute`, even `apply`
performs only readiness verification. `plan` and `backup` write encrypted local files
but never mutate AWS. The current assignment authorizes only implementation and
synthetic rehearsal; these production operations have not been performed.

## Stop/drain evidence schema

The private evidence object uses `format: zerde-legacy-cutover-evidence-v1`, the exact
`manifest_sha256`, and `reviewed_evidence_sha256` for the reviewed deployment/replay/
external-stop report. `observed_at`, `valid_until`, `stopped_at` are integer epoch
seconds. Validity lasts at most 15 minutes. The manifest must postdate the complete
stop. `old_max_timeout_seconds` must cover every old invocation (at least 900 seconds
for the legacy indexer); a further 60-second drain margin is required. A missing
CloudWatch data point is not evidence that an invocation ended.

Every boolean in `aws_adapter.ATTESTATIONS` must be explicitly true based on that
report, including explicit threads, albums, import, complete index/consumer inventory,
old-task replay, and an ongoing change freeze. The report must separately confirm
that new events cannot start an old version while the drain window elapses.

`lambda_targets` contains every Bot/indexer executable target (and any other legacy
writer), with `role`, full `function_arn`, `revision_id`, `code_sha256`, `aliases`, and
`event_sources`. Roles must include `bot` and `vector_indexer`. Live configuration
must be Active/Successful, match the reviewed artifact/revision, and predate the stop.
Alias inventory entries contain AliasArn, FunctionVersion, RevisionId, RoutingConfig;
weighted routing is rejected, and every alias version must be another explicitly
verified target. Event source entries contain UUID, EventSourceArn, FunctionArn and
State. Bot and indexer must each include their unqualified function target; a version-only
list cannot hide the current executable artifact. Immutable version targets are separately
verified, while complete alias/consumer inventories are always read on the unqualified
function. Every mapping must point to an explicitly verified target or alias. Only
stable Enabled/Disabled states matching the reviewed inventory pass;
enabled consumers require the reviewed guarded artifact. Full paginated inventories
are compared, so new or changing mappings/aliases stop cleanup.

`disabled_legacy_rules` explicitly lists every retired EventBridge rule by name,
ARN and optional event_bus; live state must be DISABLED. `queues` lists all main,
vector, and DLQ identities with url, arn, retention_seconds,
visibility_timeout_seconds, and dedicated_legacy. The complete inventory assertion
is required even when no old schedule exists. Dedicated legacy queues must have no
in-flight messages. Mixed queues can still contain business work and are never purged.
Only queue attributes are read. Their reported retention deadline is an expectation
from the complete stop, not a claim of body deletion.

When `retired_contests` is nonempty, the evidence additionally requires all three
of these reviewed attestations to be true:

- `all_retired_contest_writers_stopped`: command, webhook, participant, draw/cancel,
  sweep and external writers are retired in every deployed artifact/alias/version.
- `retired_contest_task_replay_verified`: both `PROCESS_CONTEST_TTL_SWEEP` and
  `PROCESS_CONTEST_TTL_RECOVERY` are inert on the deployed consumers, including old
  task bodies, retries and DLQs. The shared queue may continue unrelated business;
  it must not be purged or redriven wholesale.
- `complete_retired_contest_recovery_inventory`: the separate
  `retired_contest_recovery_rules` list includes every historical contest schedule
  in this scope, including rules removed by the retirement deployment.

`retired_contest_recovery_rules` must be present even if the reviewed inventory is
empty. Each item contains exact `name`, `arn`, optional `event_bus` (default bus if
omitted), and `expected_state` equal to `DISABLED` or `ABSENT`. Names and ARNs must
agree with the selected account/region/bus. `DISABLED` requires a matching live
DescribeRule result; `ABSENT` accepts only `ResourceNotFoundException`. Access
denials, transient failures and a still-existing rule all fail the absence gate.
Do not also put a removed rule in `disabled_legacy_rules`, which retains its original
DISABLED-only contract. No rule is changed or removed by this tool.

The complete `lambda_targets` and `queues` inventory above must include all former
contest writers, recovery consumers and their main/DLQ routes. `stopped_at` is after
the last of these paths was stopped; wait the largest **actual old deployed** timeout
plus 60 seconds before planning deletion, and keep artifact hashes, aliases, mappings
and recovery-rule readback frozen through every batch. The minimum existing
900-second drain remains. Source removal or an empty queue observation does not
substitute for this proof, and a bool without the reviewed report does not prove it.

Fresh STS account, table ARN/schema/creation identity, and index ARN/creation identity
must still match the manifest. These checks run again before each deletion batch.
A final cheap check reserves 30 seconds of valid evidence/backup life before every
mutation; AWS calls have bounded timeouts and no automatic retries. SDK/credential
errors never print raw exception messages or chains.

## Deletion, recovery and honest completion

The engine authenticates a complete matching backup, re-scans for changed/new records,
and validates deletion conditions before touching AWS. It deletes exact vector keys
in batches of at most 25, verifies their absence, verifies indexes empty, then deletes
exact table keys and finally markers. DynamoDB native-value conditions compare every
known original attribute; no manual low-level serialization is used.

**This is not a whole-row atomic hash CAS.** DynamoDB cannot condition on a computed
hash or reject an unknown concurrently added attribute on these legacy rows, and
S3 Vectors DeleteVectors has no version/ETag condition. Strong re-reads detect observed
changes; only the verified complete writer stop and change freeze close the remaining
race. Do not substitute a new lock field that old writers ignore. Too-wide conditions
fail before deletion and require separate review rather than an unconditional fallback.

An encrypted atomic journal records progress. After a network/disk failure, the same
unexpired manifest and backup can resume: missing exact keys count as already deleted,
while changed/recreated keys stop the run. New evidence must preserve the same complete
stop and manifest scope; it cannot widen the deletion list. A final strong scan must
show zero selected table records/markers, empty specified indexes, and unchanged
protected key/count/content digests. A concurrent unselected contest/settings change makes that
verification fail, even if intended memory deletion already succeeded; do not report
business data as unchanged or discard the evidence. Do not blindly regenerate a
manifest around unexplained changes.

Success is `online_clean_copies_pending`. Logs, PITR/on-demand backups, queue/DLQ
bodies, local archives and filesystem backups have separate retention/physical-readback
requirements. The output does not claim any of those copies have been erased, nor
that already sent Telegram messages disappeared. Register seven-day log retention,
actual PITR/backups, and actual queue policies from their owners; timestamps passing
alone are not physical erasure evidence. A backup restore requires offline review and
memory disabled throughout; this tool offers no automatic restore/import function.
Only Z11 acceptance and the approved deployment process may enable a fresh V2 epoch.

## Local verification

`tests/test_legacy_cleanup.py` uses real Moto DynamoDB transactions/conditions and
synthetic vector/service responses, including the pinned AWS SDK pagination shape.
It covers preservation, orphan vectors, marker ordering, incomplete stop/drain
proof, expiry/slow reads, concurrent changes, resource recreation, crash/resume,
encryption/authentication/permissions, and replay through the actual retired worker
routers after cleanup. `tests/test_memory_cutover.py` also checks old reply/context
isolation. Neither suite is AWS deletion proof or a deployed replay canary.
Contest retirement coverage additionally exercises default protection, exact roots
across chats, shape mismatches, isolated orphan aliases/outboxes, encrypted lossless
backup, outbox-last deletion, changed outbox/crash recovery, scope widening rejection,
and the distinct absent/disabled/denied recovery-rule gates. All data is synthetic.

Primary API contracts: [ListVectors](https://docs.aws.amazon.com/boto3/latest/reference/services/s3vectors/client/list_vectors.html),
[GetIndex](https://docs.aws.amazon.com/boto3/latest/reference/services/s3vectors/client/get_index.html),
[DeleteVectors](https://docs.aws.amazon.com/boto3/latest/reference/services/s3vectors/client/delete_vectors.html).

Lambda inventory contracts: [ListAliases](https://docs.aws.amazon.com/lambda/latest/api/API_ListAliases.html),
[ListEventSourceMappings](https://docs.aws.amazon.com/lambda/latest/api/API_ListEventSourceMappings.html).
