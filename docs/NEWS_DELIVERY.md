# News deadlines and delivery recovery

Status: **IMPLEMENTED_UNPROVEN**. This change is locally implemented with synthetic network tests and real boto3/Moto persistence tests. It has not sent a live digest, changed AWS, or proved delivery in a Telegram group.

## One daily job, one frozen manifest

The EventBridge input must include `scheduled_at`, copied from the original event's `time`, along with the existing `chat_ids` and `lang`. The handler rejects missing/timezone-naive timestamps, events more than five minutes in the future, and events older than 36 hours. This is a deliberate cutover: an old static event without stable identity must fail rather than create a new digest on every retry.

`scheduled_at` is normalized to UTC; the business date is that instant in `Asia/Almaty`. The job key is `<Almaty date>#<language>#<schedule slot>`. The default slot is the original UTC `HHMM`; an explicit alphanumeric `schedule_slot` can distinguish additional intentional runs. Current schedules have one slot per day/language (04:00/04:05/04:10 UTC), and retries crossing midnight retain the original job. A replay must retain the original timestamp, slot and destination list. Changing the audience of an existing job is rejected instead of silently broadcasting to a new group.

The existing stats table owns two new key families, through `NewsDeliveryRepository` only:

| Prefix | State and purpose |
| --- | --- |
| `news_manifest#<job_id>` | `BUILDING` with a 360-second generation lease, then immutable `READY` with intro/article steps and their SHA-256 content hash. The hash includes both the prepared text and photo-caption variants; retries send those frozen strings instead of reformatting them. The lease prevents concurrent invocations from generating the same digest. |
| `news_delivery#<job_id>#<chat_id>` | Content hash, revision, 360-second effect lease, and an ordered receipt for each step. Each receipt has mode, attempt ID/count and `PENDING`, `UNKNOWN` or `SENT`; `SENT` includes the actual Telegram message ID. |

Manifest generation can be retried after a known failure or expired lease. A model response lost before the frozen manifest is stored can therefore incur another model charge; this work does not claim exactly-once model calls or add a competing model-cost ledger. Once `READY` exists, retries do no fetching or generation and use those same content steps. A successful feed read with no fresh news freezes an empty no-news manifest and sends nothing. Failed feeds or an exhausted overall budget are not misreported as a successful empty digest.

Rows have a 30-day physical TTL for bounded operational recovery, including unknown receipts. The 36-hour logical delivery window prevents an old event from recreating a digest after TTL removal; it is not extended by retries. This is an operational receipt store, not a permanent news archive. DynamoDB TTL timing does not authorize another send.

## Execution time and cancellation

The invocation starts with `min(240 seconds, Lambda remaining time - 15 seconds)`. It checks remaining time before persistence and each send, retaining time for state writes and clean shutdown. RSS has a 15-second stage deadline; at most 45 deep-scrape candidates share a 45-second deadline and five concurrent requests. Completed article data is retained; unfinished requests are cancelled and use the existing source summaries. Each Gemini or DeepSeek attempt has a 20-second wall deadline, the existing provider fallback order remains, and at most three article summaries run concurrently. Model names, source lists, and local quality/source-text fallbacks remain unchanged.

`zerde_common.async_http.bounded_async_client()` is the single shared HTTP factory for news RSS, deep pages, Telegram, and the Gemini/DeepSeek transports. Its dnspython async resolver reads the system resolver configuration; it does not hardcode a public DNS service. The HTTPCore backend connects to resolved IPs while retaining the original hostname for HTTP Host, TLS SNI, and certificate verification. Environment proxies and implicit HTTP retries are disabled. HTTPX/HTTPCore extension points are public APIs; no private connection-pool mutation is used.

This avoids the default asyncio DNS thread-pool shutdown wait: cancelling an HTTP request is insufficient when `asyncio.run()` then waits for a still-running `getaddrinfo` thread. The tests include a real local UDP DNS server, forbid `loop.getaddrinfo`, and verify that no default executor was created. Other tests cancel connection/header and slow body waits, verify socket closure and verify the actual Gemini SDK's custom async client is closed. Gemini retains its official SDK and structured schemas; the caller owns and closes the custom HTTP client.

The cancellation guarantee covers asynchronous network waits, including DNS, connect and response streaming. It cannot preempt synchronous parsing/CPU work or synchronous boto3/SSM calls. State-table boto3 requests have connect/read limits of 2/3 seconds and one SDK attempt; the remaining-time margin and platform Lambda timeout remain the final bounds for those calls. A Python test is not a guarantee about arbitrary OS scheduling or a deployed timeout. Do not describe SDK socket timeouts alone as absolute wall-clock cancellation.

Primary API references: [dnspython async resolver](https://dnspython.readthedocs.io/en/latest/async-resolver-class.html), [HTTPCore network backends](https://www.encode.io/httpcore/network-backends/), and [HTTPX async transports](https://www.python-httpx.org/advanced/transports/).

## Per-chat delivery and unknown results

Before every HTTP send, a revision/lease CAS records that exact step as `UNKNOWN` with a fresh attempt ID. Only `ok: true`, a positive integer `message_id`, and the expected destination chat can mark it `SENT`. Each successful step is saved before the next begins. An already-successful chat or intro/article is never automatically resent during retries of other chats.

A definitive Telegram 429 or 4xx rejection returns the step to `PENDING`, retaining a retry time; the handler raises so Lambda retries and the News Lambda Errors alarm can observe failure. It does not sleep through an unbounded `retry_after`. A rejected photo may switch the same persisted step to one text fallback; a rate-limited or unknown photo cannot trigger a text fallback. A malformed success response, wrong chat, transport timeout, 5xx, cancellation or lost database acknowledgement remains `UNKNOWN`. Automatic recovery stops that chat at the unknown step, continues independent chats, and raises for the unfinished job. Failure does not broadcast diagnostic messages to every group.

A crash after recording `UNKNOWN` but before actually sending can leave a false-positive unknown result. A successful Telegram send whose database acknowledgement is lost can also remain unknown. The same conservative outcome prevents blind duplicate delivery. There is no Telegram idempotency key or exactly-once claim. Failed jobs must remain operationally visible; a returned `statusCode: 500` would count as a successful Lambda invocation, so incomplete work raises an exception instead.

## Operator recovery

Read back the exact job, manifest hash and per-chat receipts with the stats table's `GetItem`; inspect only state/attempt metadata when sharing diagnostic output. Do not reset the row, change the date, regenerate content, or rerun the entire broadcast under a new job identity to hide a failure.

For `PENDING`, fix the relevant Telegram permission/configuration problem, respect `not_before`, then invoke the **original** event again within its 36-hour window. It skips every `SENT` step. After a crashed invocation, wait until the actual writer has drained and its 360-second lease expires. A pending job beyond its logical delivery window requires an operator decision; routine recovery does not send stale news.

For `UNKNOWN`, inspect the designated Telegram group's actual messages and determine whether that specific content step was delivered. An operator must provide the exact `job_id`, `chat_id`, `content_hash`, `step_index`, `attempt_id`, and current row `expected_revision` to `NewsDeliveryRepository.repair_unknown()`:

- `resolution="CONFIRM_SENT"` requires the actual Telegram message ID and a short operator verification note. It records the existing delivery; it does not send a message.
- `resolution="REOPEN"` is allowed only after the operator has established that resending this exact step is appropriate. It moves only that unknown attempt to pending. Running the original event later still enforces the 36-hour delivery window.

The repair condition checks manifest/chat/hash/step/attempt/revision and refuses a live lease, stale repair or later attempt. It is never invoked from scheduled event input. Store a concrete repair document locally, for example:

```json
{
  "job_id": "YYYY-MM-DD#kk#0400",
  "chat_id": "-GROUP_ID",
  "content_hash": "EXACT_MANIFEST_HASH",
  "step_index": 1,
  "attempt_id": "EXACT_UNKNOWN_ATTEMPT_ID",
  "expected_revision": 3,
  "resolution": "CONFIRM_SENT",
  "message_id": 12345,
  "note": "Operator verified this exact message in the group"
}
```

After separately authorizing the production repair, run from the repository with `STATS_TABLE_NAME` set to the verified physical stats table and the intended AWS profile/region selected:

```bash
PYTHONPATH=src/news:src/shared/python uv run python -c 'import json; from services.delivery_state import NewsDeliveryRepository; NewsDeliveryRepository().repair_unknown(**json.load(open("news-repair.json")))'
```

This command changes only the conditional receipt; it sends no Telegram message. Read the same row back and verify the exact step/revision before invoking the original event. Keep the repair document and readback evidence with the incident. A stale or rejected repair must not be retried with guessed new identifiers.

## Integration, rollout and acceptance

- The integration owner injects `STATS_TABLE_NAME`, grants only DynamoDB `GetItem`/`UpdateItem` for `news_manifest#*` and `news_delivery#*`, and changes EventBridge input to include `scheduled_at: EventField.time` (plus a stable slot when needed). No scan, broad stats-table write, new table, or workflow service is required.
- Include the shared async HTTP module and the locked direct `httpx`, `httpcore`, and `dnspython` dependencies in the News bundle. The shared layer module alone does not provide these runtime packages. Root packaging owns the lock/export and ARM import probes.
- Keep Z02's safe logging and Z17's visible News Lambda Errors alarm in the same reviewed deployment. Real Lambda errors and the actual notifier path still need deployed readback and a controlled failure canary; local tests do not establish alert delivery.
- Before switching from old unconditional broadcast code, disable the schedule/admission and drain existing News invocations using the **actual deployed timeout**. Verify it remains below the new 360-second lease. Old invocations do not honor the new receipts and must not overlap the new writer.
- Do not roll back to unconditional broadcasting while frozen manifests or pending/unknown receipts exist. Stop admission and preserve the rows until a reviewed forward fix or explicit incident repair is ready.
- Validate under Python 3.13 with actual boto3/Moto persistence and synthetic HTTP/DNS/provider streams, then verify the real ARM Lambda package. A separately approved test-group deployment must exercise one failed destination after another succeeded, an unknown send, stale repair rejection, replay across midnight, and actual alert delivery without broadcasting to production groups as an unattended test.
