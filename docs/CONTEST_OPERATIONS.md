# Contest Operations Runbook

Use this runbook only for a known webhook outage, an unreachable contest root, or retention work that reached the DLQ. Contest lifecycle truth is in the memory table; ordinary group-memory rows are not a participant source.

## Fairness incident

1. If Telegram updates may have been missing for longer than Telegram's update-retention window, do not draw the affected open contest.
2. If the root or Zerde rules reply is still reachable, ask the current Telegram group creator to reply with `/contest cancel`.
3. If neither anchor is reachable, record the exact `(chat_id, root_message_id)` and inspect only that contest's rows. Do not scan messages to reconstruct entrants.

## Read-only inspection

Replace placeholders explicitly; do not use a wildcard chat or table name.

```bash
aws dynamodb get-item \
  --table-name '<memory-table>' \
  --key '{"pk":{"S":"CHAT#<chat_id>"},"sk":{"S":"CONTEST#<13-digit-root-message-id>#META"}}' \
  --consistent-read

aws dynamodb query \
  --table-name '<memory-table>' \
  --key-condition-expression 'pk = :pk AND begins_with(sk, :prefix)' \
  --expression-attribute-values '{":pk":{"S":"CHAT#<chat_id>"},":prefix":{"S":"CONTEST#<13-digit-root-message-id>#"}}' \
  --consistent-read

# Read rules_message_id from META, then inspect its exact alias.
aws dynamodb get-item \
  --table-name '<memory-table>' \
  --key '{"pk":{"S":"CHAT#<chat_id>"},"sk":{"S":"CONTEST_RULE#<13-digit-rules-message-id>"}}' \
  --consistent-read

aws dynamodb get-item \
  --table-name '<memory-table>' \
  --key '{"pk":{"S":"CONTEST_TTL_OUTBOX"},"sk":{"S":"CHAT#<chat_id>#ROOT#<13-digit-root-message-id>"}}' \
  --consistent-read
```

The expected rows are one `META`, zero or more `PARTICIPANT` rows, an optional `CONTEST_RULE` alias, and—after first draw/cancel until cleanup completes—one global outbox marker.

## Retention recovery

- A surviving outbox marker is authoritative pending work. Do not delete it manually just because an SQS message was sent.
- Redrive the failed `PROCESS_CONTEST_TTL_SWEEP` DLQ record when possible. Its payload needs only `chat_id` and `root_message_id`; META `ttl_sweep_cursor` and `ttl_sweep_version` own progress.
- The always-on production EventBridge rule seeds a bounded `PROCESS_CONTEST_TTL_RECOVERY` job. Recovery pages the global outbox and independently queues identity-only sweeps, even if the chat was later removed from configuration; duplicate recovery and sweep messages are expected and safe.
- Cleanup is complete only when participant rows and the rules alias have the same physical `ttl`, META has `ttl_sweep_status=COMPLETE` plus its physical `ttl`, and the exact outbox marker is absent.

## Precise manual cleanup

For an unreachable `OPEN` or stuck `CREATING` contest, first export the exact query result above to an incident backup. Obtain explicit approval before deleting data. Delete only the exact META, its participant-prefix rows, its stored rules alias, and its exact outbox marker; never delete `CHAT#<chat_id>` broadly. Record the backup location, row count, reason, operator, and UTC timestamp.

After any manual action, repeat the read-only queries and confirm that unrelated contest roots and memory rows remain unchanged.
