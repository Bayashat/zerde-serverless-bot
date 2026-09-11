# Memory V2 model budget (Z08)

`services/memory_budget.py` is the sole model-cost reservation owner. Extraction,
retries and the entire request for a memory-enhanced answer share the independent
Memory V2 table. The limit is USD 7 per UTC month across the project. Both environments use
the production V2 table's cost-only key prefixes via an explicit budget-table
configuration. Dev facts stay in the dev table; dev IAM must restrict access to
`MEMORY_BUDGET#*` and `MEMORY_ATTEMPT#*`. A missing shared ledger disables optional
model work, never creates another independent allowance. This is an application
allowance, not an AWS account or provider invoice cap.

Only `gemini-3.1-flash-lite`, standard service, one candidate and plain text are
priced here. No tools/search, caching, media, flex/priority or provider fallback is
allowed inside a reserved memory call. Explicit media and no-memory asks remain
separate from this enhancement path. Unknown models must fail closed, not silently
inherit another model's rate.

The rates verified on 2026-09-10 are $0.25/M input and $1.50/M output (including
thinking). [Google pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.1-flash-lite)
The model publishes a 1,048,576 input and 65,536 output token ceiling.
[Model specification](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite)

Before each network attempt, reserve USD **0.458752**: the full model input ceiling
and two full output ceilings, conservatively allowing a separate thinking margin.
This intentionally avoids treating multilingual character counts as guaranteed
token counts. The extractor still caps actual batches at 20 messages/8k input and
limits response tokens/timeout; the reservation is not permission to send a
model-sized batch. The estimate can be narrowed later only with demonstrated
provider-counted input and total-output bounds. When less than one reservation
remains, pause optional model work even if a smaller request would probably fit.

A successful response with valid usage metadata atomically replaces that hold
with its actual token-based cost, rounding up to micro USD. `totalTokenCount`
includes prompt, thoughts and candidates; an omitted thoughts component can be
derived only when the documented total and other components are present.
[Usage metadata](https://ai.google.dev/api/generate-content#UsageMetadata)
Missing/inconsistent/unpriced usage keeps the entire hold. HTTP failures,
timeouts, process crashes and ambiguous database responses do not refund it.
A subsequent attempt needs a new ID and reservation. Costs on provider free tier
are conservatively counted at standard paid rates; this ledger is not proof of a
provider invoice or payment.

On 2026-09-11, a bounded real smoke returned HTTP 200 with
`serviceTier: "standard"`. The documented GenerateContent wire enum uses lowercase
`standard` and `unspecified`; the latter means the standard default. This ledger
accepts exactly those two strings or an omitted field. It does not case-fold,
trim or infer a tier from SDK enum member names; uppercase `STANDARD` and
`SERVICE_TIER_UNSPECIFIED` have no verified wire contract for this endpoint and
retain the hold, as do flex, priority, unknown strings and non-string values.
[ServiceTier reference](https://ai.google.dev/api/generate-content?hl=en#ServiceTier)

Token counts must be nonnegative integers, excluding booleans. Optional cache and
tool counts must be absent or integer zero; their modality lists must be absent
or empty. Optional prompt/candidate modality lists must contain only `TEXT` with
integer counts. Nonempty lists must sum to their corresponding prompt/candidate
total, with thinking accounted separately by `thoughtsTokenCount` or the total
difference. Malformed lists, non-text data, cache/tool usage or inconsistent
totals never release a reservation. This metadata check complements the provider
owner's fixed one-candidate, text-only request contract.
[Usage metadata reference](https://ai.google.dev/api/generate-content?hl=en#UsageMetadata)

The observed shape (403 prompt, 11 candidate, 414 total tokens, omitted thoughts,
403 `TEXT` prompt-detail tokens, lowercase standard tier) costs **118 micro USD**
after upward rounding. Local native-SDK/Moto regressions verify settlement and
database-failure recovery without double refunds. This compatibility repair does
not alter prices, ceilings, reservation transactions or old ledgers. Historical
HTTP errors with unknown usage keep the entire USD 0.458752 hold; independently
verified successful calls can be reconciled separately without resending them.

The monthly counter's `charged_micro_usd` is **settled usage plus unresolved
reservations**. `settled_micro_usd` reports only confirmed token-based usage;
the difference is held/unknown liability. Show both, never label the entire
counter as an actual bill. Reservations use globally opaque attempt keys,
so a repeated ID cannot authorize another HTTP call after a month rollover.
Settlement remains charged to the reservation's UTC month. Calls must begin
promptly after reservation; do not persist a permit in a queue for later reuse.

Reserve and settlement use the native boto3 Resource client transaction encoding.
A conditional reservation plus counter update enforces concurrency; a token and
month-bound conditional settlement prevents duplicate or wrong-month refunds.
Database faults propagate and cannot authorize a provider call. When observed
valid usage exceeds the conservative ceiling, persist the liability and pause the
ledger and its global control record, then surface an accounting error.
The contract pause survives month rollover and needs operator review before
resuming; insufficient-budget exceptions expose a next-UTC-month `retry_after`
to prevent immediate queue retry loops. Do not keep calling through a pricing
or provider-contract change. Records contain no chat text/Telegram identities and
expire after 400 days; outboxes carrying raw messages must not use these keys.

The provider adapter owns one no-hidden-retry HTTP attempt per reservation.
DuplicateMemoryAttempt means **do not call**. A lost settlement response may retry
settlement with the same token/usage, never the generation call. Budget exhaustion
must defer learning and remove all memory enhancement from model answers;
deterministic valid profiles, correction/forget/optout and no-memory explicit asks
remain available. The old RPD counter is a provider-quota guard and does not own
this cost boundary.

AWS increment estimation, USD 3 reserve, threshold notifications and source-safe
answer integration are the remainder of Z08; this module alone is not their
acceptance evidence. Production enablement still requires Z11 gates.
