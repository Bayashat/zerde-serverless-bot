# Moderation execution and safe-review receipts (Z13)

Related: [#170](https://github.com/Bayashat/zerde-serverless-bot/issues/170), [Epic #157](https://github.com/Bayashat/zerde-serverless-bot/issues/157).

This is the source contract for the local implementation. It does not establish deployment, real-user moderation success, or Memory V2 ingestion.

## State ownership

`services/repositories/spam.py` owns `spam_case#decision#...` and `spam_case#action#...` in the existing stats table. No memory, contest, captcha or ordinary statistics keys are repurposed. Classification receipts contain identity, an input hash, decision metadata and an optional source reference; they do not contain message text, quoted text, contact data or media references.

Decision identity includes chat, actor, message, source revision and moderation input hash. A conditional creation and invocation lease serialize conflicting work. Successful classification is persisted before enforcement or alert delivery so a retry does not need another model call. Provider failure and unknown captcha/membership state never become `clean`.

The action owner records completed deletion separately from the ban. Only a positively acknowledged Telegram ban can commit `state=banned`; that state and the chat's `spam_bans` increment share one DynamoDB transaction. A completed action is replayed without banning or counting again. A failed/unknown operation does not display a successful-ban notification. Administrator callbacks keep their buttons after an unconfirmed action so permissions can be corrected and the action retried. Ban and ignore compete for the same decision lease; the first selected action is persisted before external enforcement. Only that action can resume after a failure. Neither an opposite button nor worker replay may turn a pending/confirmed ban into CLEAN, including when the final decision write fails after Telegram succeeds.

Automatic bans remain temporary. The effective minimum duration is explicitly 60 seconds; the old 31-second configuration is normalized to 60, with configured/effective durations in structured diagnostics. This safety correction prevents a short temporary request becoming permanent during transport: Telegram treats a deadline less than 30 seconds away as permanent ([Bot API](https://core.telegram.org/bots/api#banchatmember)). The deadline is persisted immediately before the first ban attempt and never extended on retry; near-expiry retries stop with an actionable failure. The implementation leaves a ten-second transport margin and disables hidden HTTP retries for moderation calls. Existing permanent bans and administrator/creator targets are not changed. Guest spam only deletes the guest response and proposes review of the Telegram-provided personal caller; it never automatically bans the guest or caller.

429, transport failures and storage failures remain retryable. Other Telegram 400/401/403/404 errors become explicit failed outcomes and a reviewable administrator action where delivery is possible. Already-deleted messages use the Telegram client's structured not-found handling. Both ordinary and guest review-alert delivery failures propagate instead of silently dropping the review.

## Z06 source and recovery interface

New `SPAM_CHECK` tasks may carry `source_ref={source_id, source_version, epoch}`:

- `source_id`: string form of the Telegram message ID; must match `message_id`.
- `source_version`: positive integer revision owned by the V2 source row, not Telegram `edit_date`.
- `epoch`: the chat CONTROL's non-reusable string token.

The decision also records chat/user/message identity. Z06 remains the sole owner of canonical source text, source hash, edit ordering, epoch validity and quarantine. It must match all those identities and the exact source version before using a receipt. The moderation-formatted text is not passed back as learning evidence. Old tasks without a source reference are business receipts only and cannot trigger learning.

For atomic source promotion, the stats table's partition key is `stat_key="spam_case#" + case_id`, where `case_id="decision#" + 32 hexadecimal characters`. `get(case_id)` uses a strongly consistent read. A cross-table condition must verify `kind="spam_decision"`, `state="clean"`, `outbox_pending=True`, `guest_bot=False`, `chat_id` as a string, `user_id` and `message_id` as integers, and the complete `source_ref` map. Z06 must also check the current source revision, epoch and observation in its own rows in that transaction; only after source promotion commits may it acknowledge the receipt.

`input_hash` is SHA-256 of `json.dumps({"text": task["text"], "message_context": task.get("message_context") or {}}, sort_keys=True, separators=(",", ":")).encode()`. It identifies the submitted moderation input and is **not** the canonical source hash. A producer that persists this expected moderation hash can include equality in the promotion condition. Receipt fields contain no substitute source body. DynamoDB resource reads represent integer attributes as `Decimal`; the wire task reference still requires a positive JSON integer.

`clean` with a source reference creates a durable `outbox_pending=True` receipt with no TTL until Z06 acknowledges it. `list_clean_pending(limit, cursor)` scans at most 100 evaluated items per page and returns the continuation cursor, including pages with no matches. The consumer must paginate. This bounded recovery hook creates no schedule or legacy-memory observer.

After same-version ingestion, Z06 calls `acknowledge_clean(..., outcome="INGESTED")` with matching chat/user/message and reference. If the source expired or its epoch was revoked, it calls `outcome="EXPIRED"` and counts that outcome in coverage reporting. Acknowledgement is conditional and replayable for the same outcome, then starts a 30-day receipt TTL. The consumer must not silently skip a pending receipt or leave revoked sources pending forever. Guest content is never a personal-profile learning source, including after a caller review is ignored.

Other action/decision receipts retain a 30-day TTL; current CLEAN receipts without a V2 source reference do not create pending ingestion. Previously sent ID-based review buttons remain usable as unversioned business actions only. New buttons use a bounded case ID and validate the callback chat against the stored case.

## Limits and release dependencies

Telegram and DynamoDB cannot share a transaction. An acknowledgement lost after Telegram accepted a ban may leave its attribution unknown: the retry does not credit an already-banned user to this bot, so such a ban can be undercounted. It does not invent success or repeat the counter. An alert accepted by Telegram immediately before a crash can also be sent again before its delivery marker is persisted. These are explicit transport limits, not exactly-once Telegram delivery guarantees.

Z01 cuts the runtime's old-memory context input off. Z12 must deploy in the same release so the underlying captcha repository propagates read failures; this change propagates them through the spam worker. Z06 owns the future source-reference producer and recovery consumer. No AWS changes, real bans, new memory ingestion or threshold changes belong to this PR.

Local evidence includes Moto-backed execution of the actual boto3 resource transactions, conditional CLEAN acknowledgement and TTL expressions, plus stateful synthetic scenarios for 429/403/timeouts, partial completion, duplicate tasks/buttons, permissions, actual Telegram error classes, explicit positive acknowledgements, source-version isolation, durable CLEAN recovery and guest-caller protection. Production permission/configuration readback and real moderation acceptance remain separate evidence.
