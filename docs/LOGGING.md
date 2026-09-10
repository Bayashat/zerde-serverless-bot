# Runtime logging

Bot, news, quiz, and vector workers use `zerde_common.logger.JSONFormatter` as
the final JSON log boundary. Log operation names, statuses, error classes,
counts, sizes, and durations. Do not place Telegram text, model output, request
or response bodies, contacts, or file references in log messages.

The formatter redacts credentials in the formatted message, nested adapter
extras, and the complete exception chain. It checks current secret environment
values at emission time so secrets loaded lazily from SSM are covered. It also
recognizes Telegram bot URLs/tokens, provider API keys, credential assignments,
and authorization schemes. Telegram file URLs are omitted in full. Known
content-bearing extra fields are omitted as defense in depth; this does not
replace metadata-only logging at call sites.
The urllib3 logger also uses this JSON sink at WARNING level without propagating
to Lambda's default handler, because automatic retry warnings contain request URLs.

Webhook update logs are emitted after webhook authentication and private-chat /
configured-group routing. `telegram_update_log_extra` returns only a known event
type, an integer update ID, and selected text lengths or collection counts.
It does not serialize Telegram Updates, unknown fields, usernames, contacts,
quoted messages, or media references. Unknown Lambda events log their shape,
never the raw event.

Telegram HTTP errors retain their status and response body internally for
existing error classification. Their string/repr and adapter logs expose only
status and response size. Network failures still propagate with their original
types and traceback, with credentials removed when the log is emitted.

Logging field changes:

- `telegram_update`, `telegram_update_json`, and truncation fields are removed.
- Model output helpers return `response_chars`, without a preview.
- Telegram adapters log `response_chars` instead of response text or previews.
- Unknown dictionary events report `key_count`, without copying their keys.

Validation uses synthetic credentials and HTTP failures, captures formatted JSON
output, and verifies metadata-only behavior for private, unconfigured,
unauthenticated, and configured group updates. No live credentials or Telegram
messages are needed for these tests.
