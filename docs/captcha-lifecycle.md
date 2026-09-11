# Captcha lifecycle and recovery

The stats table owns each `(chat_id, user_id)` challenge. New rows include a random
`generation`, `revision`, immutable join-message identity, and a bounded operation
lease. Creation persists `preparing` and successfully enqueues a generation-scoped
`CHECK_TIMEOUT` before restricting a member or sending a captcha image.

The state machine is:

- `preparing -> creating -> pending -> verified | rejected`
- `preparing | creating -> cancelled` when creation cannot be completed safely.
- Terminal decisions never change. `action_done` separately records reconciliation
  of the decided Telegram action. Failed actions keep their decision and retry.

All state writes require the same generation, revision and live lease. The
360-second lease exceeds the current Bot Lambda's 300-second timeout; a later
join cannot replace a generation while its action lease is live. Keep this
relationship valid if Lambda timeout changes. A process crash can delay recovery
until the lease expires, but cannot make a creating challenge a timeout rejection.

Correct answers persist `verified` before unrestricting; wrong-answer exhaustion
and timeout persist `rejected` before kicking. Duplicate message IDs count as one
wrong attempt. Expired pending challenges stay in captcha routing, including
commands, instead of entering spam/memory/agent flows. A new join system message
is routed as a join, not as an answer to an older challenge.

Before applying a pending terminal action, the worker reads current Telegram
membership and revalidates its lease. Only the exact captcha text-only restriction
may be removed or kicked; different administrator restrictions and promotions are
left intact. A lost unrestrict/kick response stays pending. Retry uses membership
readback to avoid repeating an already observed effect. An invalid/unavailable
readback requests retry. This is recoverable reconciliation, not an exactly-once
guarantee across Telegram and DynamoDB.

The original recovery message also handles a crash after restriction/photo send
but before activation: the decision becomes `cancelled`, then permissions are
restored. An unconfirmed photo message ID cannot always be cleaned up; no new
captcha is blindly sent to compensate. Known prompt/wrong-answer messages are
cleaned up best effort after reconciliation. Verified joins keep the system join
message. Terminal rows are retained for 15 days, covering the 14-day DLQ retention;
timeout tasks never unconditionally delete the current user's state.

New timeout tasks carry `generation` and join identity; their initial verification
message ID can be zero because enqueue precedes sending. Legacy tasks without a
generation require both exact nonzero join and verification message IDs. Missing
state is harmless; database failures propagate instead of pretending to be missing.
Early recovery tasks reschedule against the persisted deadline. A live lease is
rescheduled rather than consuming SQS's dependency-failure retry budget. All SQS
delays are capped at 900 seconds, with deadline checking on the next delivery.

Creation/answer failures return webhook 500 through `CaptchaRetryRequiredError`.
`CHECK_TIMEOUT` dependency failures propagate for retry/DLQ inspection. Counters and message
cleanup are best effort after a committed outcome; counters are operational
estimates, not an exactly-once accounting ledger.

Answers must have a Telegram message id later than both the current join and
challenge photo. Delayed messages and edits from a previous join, and messages
sent before the photo, are ignored without consuming attempts or deleting input.

## Rollout gate

Old in-flight code used unconditional writes/deletes and cannot honor the new
generation fence. Before enabling new captcha creation, stop admitting new join
work to the old runtime and let existing Bot invocations finish (up to 300 seconds),
then enable the new protocol. Preserve pending Telegram updates and mixed SQS work;
do not purge the main queue. Queued legacy timeouts can be consumed by the new code
using the exact-identity compatibility rule above. This document is a release
requirement; this change itself performs no AWS or Telegram configuration updates.

Z12 changes the webhook captcha entry and `CHECK_TIMEOUT` path. The separate
`SPAM_CHECK` worker still has a legacy pending-captcha lookup that catches storage
errors; Z13 owns making that caller propagate failures. Z12 must not be released
until the Z13 caller fix is integrated and verified in the same release.

## Validation

`tests/test_captcha.py` exercises the actual DynamoDB repository expressions with
Moto, plus simulated Telegram side effects and faults. Coverage includes competing
lease holders, stale snapshots, lost write/action responses, creation failures,
early tasks, legacy identity, rejoin fencing, duplicate attempts, and webhook 500
handling. Moto is a development-only dependency; these are local simulations, not
claims of live AWS transaction or Telegram acceptance.
