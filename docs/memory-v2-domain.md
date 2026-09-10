# Memory V2 domain contract (Z05 / #162)

This package owns the independent Memory V2 table's controls, accepted sources
and facts. It is not connected to Telegram ingestion, an extraction model or a
worker by this slice. The table name is mandatory; there is no legacy-table
fallback. `FactWriter` is the only fact mutation service. Profiles are validated
reads of current facts, not another writable model.

## Storage and identity

All keys use `pk=CHAT#<canonical chat id>`. User identity is the Telegram user id;
names are values and never merge identities across people or groups.

| Sort key | Owner and purpose |
| --- | --- |
| CONTROL | Group state, independent learning_enabled, epoch, learning_started_at and CAS revision. Missing means STOPPED. |
| SUBJECT#USER#id / SUBJECT#GROUP | State, optout, generation, activation boundary and revision. Changes serialize writes for that subject. |
| HEAD#message_id | Accepted source version, original/edit time, actor, content hash, epoch/generation, deletion and evidence-retention flags. |
| RAW#message_id | Safety-checked original text, quote offsets and identity; logical expires_at and physical ttl are original_sent_at + 30 days. |
| WORK#message_id#version | Reference-only PENDING work, source_ref, actor/generation, lease fields, attempts and due time. |
| FACT#USER#id#field#slot / FACT#GROUP#field#slot | Sole current slot: value/status, fact version, source order, temporal fields and minimal source evidence. |
| HISTORY#FACT#...#version | Replaced version, marked SUPERSEDED, maximum 90-day TTL. It never appears in profile reads. |

`source_ref = {source_id: str, source_version: int, epoch: str}`. Source authors
come from stored HEAD/RAW, never extraction output. The content hash covers text,
quote offsets and message/confirmation kind. Same edit time with a different
hash is an ambiguous conflict; old revisions cannot win. Original send time must
be in the current group and subject learning window, including for message edits.
Timestamps are UTC seconds, matching Telegram's source timestamp precision.

Source registration creates HEAD + RAW + PENDING and advances the subject
revision in one transaction. Duplicate delivery with the same source fingerprint
returns the existing reference without changing state. Source edit advances HEAD
and makes every old-version derived fact immediately invalid on reads.

HEAD initially expires with RAW. A transaction that writes facts also removes
HEAD's TTL and sets retained_evidence. Raw text still expires after 30 days, but
facts retain their exact evidence excerpt and can validate against HEAD after raw
expiry. Empty extraction finishes WORK without retaining HEAD forever. Z09 owns
removing retained heads when their final fact/history reference is gone; this
slice does not claim physical forgetting.

## Fact writer and temporal rules

The public interfaces are:

- `MemoryRepository(table_name)`: controls, `ensure_subject`, `get_subject`,
  `register_source(event, expected_source_version=...)`, `source_snapshot`,
  `get_source_head`, `get_work`, and `get_profile(chat_id, user_id)`.
- `FactWriter(repo).apply_source_changes(chat_id, source_ref,
  subject_generation=..., expected_subject_revision=..., changes=..., lease=...)`.
  The WorkLease is mandatory and must match the source/generation.
- `FactWriter(repo).confirm_group_fact(..., confirmation=AdminConfirmation(...))`:
  a separate trusted command lane, never a model extraction option.

Automatic fields are occupation, current_project, city-level location, education,
tech_stack, interests and communication_preferences. Occupation/project/location
use a single current slot. Education/tech/interests use a normalized value hash
per slot. Preferences use language/name/length/tone slots: language, length and tone
have narrow enumerations; a name has short name-only constraints and cannot install
response instructions. Unsupported fields, malformed evidence and third-party
attribution fail; ambiguous claims are skipped without inventing a current truth.
Semantic identification of an explicit self-claim remains Z07's responsibility.

Each change cites an exact non-quoted source span of at most 240 characters. Values
are at most 160 characters. The shared V2 `safety.require_public_content` rejection
layer checks values and excerpts again, including secrets/token patterns, contacts,
precise addresses, salary/account and selected sensitive content. Source admission
uses the same policy before RAW is written. This conservative deterministic layer
is not a claim of perfect multilingual sensitivity classification; Z07/Z11 must
validate and improve it with the agreed gold cases, not bypass it.

A source's order is original_sent_at, numeric message_id, edit time, source version.
Editing an older message cannot outrank a newer self-statement. A single-value new
statement replaces the current version only if its source order is later. Multiple
values require explicit assert/remove; removal retains a RETRACTED current marker
so delayed older adds cannot resurrect it. A remove naming a different current
single value leaves that value alone. Future validity intervals are rejected in
V1. Reconfirmation records source observation time, not worker execution time.
Occupation/project/location older than 180 days are labelled `last_confirmed`.

The commit transaction includes group and subject revision fences, the exact
HEAD version/epoch/generation and logical expiry, fact CAS/history, and a WORK
LEASED-token/expiry check plus DONE transition. Time is read again after validation,
not reused from before a model call. A transaction conflict writes no partial
facts/history or DONE. Lost commit responses are safely retried through DONE.
Groups can pause learning while leaving profiles readable; STOPPING or optout
blocks new writes and reads. No new group activates itself.

Group rules/decisions require a confirmation-kind source from the same actor as a
trusted AdminConfirmation, and the writer only accepts admin_confirmed changes.
The Telegram command adapter must check that actor's live administrator permission
before constructing the confirmation. A model cannot supply that object or use the
confirmation entry. Live Telegram authorization and command wiring are not shipped
by this slice; the ordinary extraction entry rejects group fields.

## Z06 / Z09 integration boundaries

`work-due` is a KEYS_ONLY GSI with `work_queue` string partition and numeric `due_at`.
There are four stable `MEMORY_WORK#0..3` shards, derived from chat identity. Only
PENDING/LEASED rows are indexed; due_at is next_attempt_at or lease_until. Recovery
must strongly read the actual row and source/control state after reading the GSI.
DONE removes GSI attributes. Logical WORK expiry is the original 30-day deadline;
physical reference retention lasts seven extra days for expiry accounting, and
DONE has seven-day physical retention. Z06 owns lease/recovery methods and worker
transport, and must submit facts through FactWriter so DONE remains atomic.

Safety eligibility precedes accepted-source registration. Pending spam review must
not call register_source with classifier context or unapproved messages. The
approved Z06 extension uses a separate short-lived CANDIDATE plus OBSERVATION
version owner, immutable moderation receipt and atomic promotion to HEAD/RAW/WORK.
It will extend this same repository, including observation-version validation and
retention, rather than creating a second source/fact writer. No such candidate or
receipt protocol is claimed implemented here.

Subject/group begin-stop methods establish a version fence. Completion methods
are low-level control transitions: Z09 must drain registered answer leases and
clean facts/history/raw/derived references before acknowledging forget to a user.
Optout persists across group epochs; only an authorized personal opt-in clears it.
Completed personal deletion starts the next learning window at completion time.
Old source identities cannot be recreated in a new generation. Already sent
Telegram replies and external backups are outside this table's atomic boundary.

## Evidence

`tests/test_memory_v2_contract.py` uses Moto service semantics for source/work
atomicity, fact/history/DONE rollback, CAS races, stale source and lease rejection,
optout/epoch isolation, multivalue withdrawal, source edits, raw expiry with retained
evidence, privacy rejection and trusted command separation. Work leases in these
unit tests are fixtures implementing the frozen row protocol; no production
unleased fact path is added. Tests and local CDK synthesis do not establish live
AWS, Telegram, model correctness or the Z11 product acceptance thresholds.
