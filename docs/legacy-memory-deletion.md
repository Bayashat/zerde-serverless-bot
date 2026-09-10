# Legacy memory deletion boundary (Z03 / #160)

This safety fix applies to the existing mixed DynamoDB memory table. It does not
perform the Z10 production wipe and does not implement V2 deletion leases.

## Ownership

Deletion first applies a closed sort-key allowlist: MSG, MEDIA_GROUP, USER,
USERNAME, EVENT, USER_FACT, GROUP_FACT, JOKE, DAILY_SUMMARY, TERM, AGENT_REPLY,
AMBIENT_REACTION, PROACTIVE, VECTOR_BACKFILL, BOT_COMMITMENT and BOT_CORRECTION.
SETTINGS, CONTEST, CONTEST_RULE, CONTEST_TTL_OUTBOX, every unknown type, other chat
partitions and other tables are protected even if their user_id/message_id matches.

Group forgetting removes only this allowlist. Personal forgetting uses the USER /
USER_FACT identity in the key, username aliases' target and owner, AGENT_REPLY's
requester, or the author of a personal memory row. A name substring or a contributor
user_id does not authorize deleting shared GROUP_FACT / DAILY_SUMMARY records.
Their complete historical removal belongs to Z10; the personal command explicitly
states that limitation. Lexical rows are removed with the authorized source.
A username reassignment is guarded by a conditional target check.

A reply to a bot answer can delete only vectorizable durable sources and remains
subject to the existing user/group-owner permission check. It cannot nominate a
business key, user profile or raw message as a durable source. A direct reply to a
source message uses its Telegram author permission and the raw/derived-message
lookup. These legacy lookups retain their existing bounded scan limits; this is
not a proof that all historical derivations or unstructured mentions were found.

## Durable vector recovery

Each source deletion and its known lexical rows are one DynamoDB transaction. For
vectorizable sources the transaction also writes a reference-only marker at
`pk=MEMORY_VECTOR_DELETE#<chat_id>, sk=<source_sk>`. It stores the canonical vector
key, chat/source identity, generation and creation time, with no memory text or TTL.
The DynamoDB resource client accepts Python values; do not pre-serialize them.

`recover_pending_memory_vector_deletes(chat_id, repo=...)` processes at most 100
markers per invocation. Every vector must be confirmed deleted before its marker
is conditionally acknowledged by generation. Provider failure, a disabled legacy
index, lost acknowledgement or more pending pages is incomplete cleanup. Forget
commands attempt recovery after deleting sources; repeat the command or run the
same recovery function with the authorized chat to continue. A retry does not need
the source row, which may already be gone. This change adds no recovery schedule
or queue task. Operators must inspect pending markers until recovery is complete.

The memory partition allowlist never deletes these recovery markers. Z10's exact
manifest must explicitly include them, recover the recorded vectors, enumerate
pre-existing orphan vectors separately, and verify that no marker remains before
claiming physical vector cleanup. Disabled vectors do not mean absent vectors.
Never purge the mixed task queue or the complete table.

## Cutover and evidence limits

Release with Z01's legacy writer/indexer stop and wait for old invocations before
cleanup. A still-running legacy writer can recreate a deleted key; this patch is
not a substitute for that cutover gate. V2 uses an independent table/index and
must not consume this legacy recovery namespace. Existing logs, PITR/backups and
queues have their own retention windows; source deletion is not immediate physical
wipe of those copies, nor deletion of already sent Telegram messages.

Semantic candidates re-read the source with a strong read. Missing, unreadable,
unsafe or logically expired sources are excluded, and prompt text is taken from
the current source rather than the vector payload. No source means no semantic
fallback to the deleted text.

`tests/test_memory_delete_boundary.py` uses Moto to exercise transaction rollback,
mixed-partition key/count/content preservation, pagination, reference-only
recovery after provider/acknowledgement failure, generation fences, alias
reassignment and source fail-closed retrieval. It is local DynamoDB simulation,
not live AWS or Telegram acceptance. Moto is a development-only test dependency.
