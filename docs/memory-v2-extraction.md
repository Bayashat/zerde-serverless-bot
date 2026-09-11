# Explicit self-statement extraction (Z07 / #164)

The extractor proposes typed `FactChange` values. It does not write facts, sources,
profiles, controls, work state, trends or budget counters. Z06 supplies current
leased source snapshots; Z05's `FactWriter` performs the final source/subject/CAS
checks and atomically commits facts and DONE. Group rule/decision confirmation
uses the separate trusted administrator command lane, never model extraction.

## Interfaces and ownership

`models.ExtractionSource` and `models.ExtractionResult` are the shared Z06 types.
`MemoryExtractor.extract_batch(sources)` is async and returns one result per exact
source reference: `complete` with typed changes (possibly empty), or `defer` with
a safe reason and absolute UTC `retry_at`. Provider errors, blocked/truncated
responses, missing source results and invalid schemas never become empty success.
There is no regex fallback that invents facts.

The constructor requires a provider, the single budget owner and an async
`validate_sources(sources)` callback. Z06 constructs it through
`MemoryWorker(repo, extractor_factory=lambda validate: MemoryExtractor(...,
validate_sources=validate))`. The callback rechecks this invocation's leases,
CONTROL, observation/head/raw revision, generation, optout and logical expiry.
It runs before reservation work and again immediately before each actual provider
request, including the second attempt. Worker submission must revalidate again;
the extractor has no authority to mark a source processed.

`extraction_prompt.input_upper_bytes(sources)` supplies the shared batching gate.
The complete serialized UTF-8 request, including system instruction, source JSON
and response schema, must fit 8,000 bytes; at most 20 same-chat, same-epoch sources
are allowed. This conservative gate avoids character/4 token guesses. Z06 splits
batches with the same function; a single over-limit source gets an explicit
unprocessed outcome/coverage count rather than permanent invisible retries. No
source or evidence is truncated. Financial reservations independently cover the
model's complete published token ceilings.

## Provider and evidence

`GeminiExtractionProvider` makes a plain-text standard `gemini-3.1-flash-lite`
`generateContent` request, with JSON schema, one candidate, at most 8,192 output
tokens and minimal thinking. It uses no media, tools, cache, cross-source identity
resolution or legacy memory. The model receives source indices and text/quote
offsets, not Telegram user/chat IDs or source database keys. It cannot choose the
source author or override the source revision.

The adapter rejects altered instructions/generation configuration, multiple candidates,
tools, cache or media parts before HTTP, even if an internal caller bypasses the
normal request builder. The async HTTP adapter has a 20-second total cancellation deadline, no transport
retries and no redirects. Streaming responses are capped at 1 MB. It discards
transport error details and exception chains rather than leaking credential or
source text. `httpx` must be present in the generated bot/worker runtime lock
manifest; dev transitive availability alone is not deployment evidence.

Each model attempt first uses the budget owner's strongly read `check_available`
preflight so paused learning does not burn shared provider RPD quota. It then
checks RPD and requires its own fresh atomic `MemoryBudgetRepository.reserve` result;
the preflight is never a spending permit and races still fail closed at reserve.
A denied, duplicate or uncertain reservation makes no provider call. Valid usage
is settled even when schema/semantic validation rejects the response. Unknown
usage keeps the full reservation. Settlement failure leaves work deferred and
never repeats that network attempt; a future attempt needs another reservation.
The legacy daily quota remains separate; its `(0, True)` storage-error sentinel
does not authorize an extraction call.
Quota exhaustion defers until the actual America/Los_Angeles midnight reset;
quota/storage unavailability retries after 60 seconds. A budget pause uses the
owner's next-month `retry_after`, or a conservative one-hour retry if absent.

Only explicit self-attribution and the approved personal whitelist survive
parsing. The prompt excludes past/future assertions (apart from completed
education), questions, role-play, third-party claims, sensitive information,
instructions and inferred skill/interests. Values and evidence pass the common
public-content policy again. Exact evidence is located in that source's original
Unicode text, must occur uniquely outside quoted spans, and is converted to Python
character offsets without rewriting. Conflicting slot changes and foreign/missing
source indices are errors. Group fields and model-supplied actor IDs are rejected.

JSON schemas, exact spans and an attribution label do **not** prove semantic truth.
A model can still misread a self-statement. The multilingual Z11 gold evaluation
and real-group acceptance remain required before enabling learning; these local
tests do not establish the plan's precision/recall thresholds.

## Group trends

`aggregate_trends(sources, chat_id, epoch, as_of)` is a pure seven-day aggregation
over a complete, current, source-valid snapshot from the repository. A small
versioned technical dictionary counts each topic once per message, participants
once per topic, and UTC daily buckets. Quoted spans are excluded. Results carry
the exact source references needed for invalidation; they describe discussion
word frequencies, never a person's interests or inferred expertise.

Z06/root owns the daily schedule, snapshot completeness, bounded source paging,
derived-row storage and revalidation/invalidation after edits, optout or forgetting.
The pure function rejects duplicate source identities, mixed scope, future edits
and unsafe inputs. It does not claim a stored trend can bypass source/control checks.

## Evidence and rollout boundaries

Tests use synthetic model responses and HTTP transports for schema failures,
Unicode spans, quote exclusion, scope/identity isolation, budget denial, quota
failure, source expiry, retries, streaming cancellation and deterministic trends.
Actual Moto-backed budget integration checks reservation/settlement and duplicate
attempts. No real provider, AWS or Telegram calls occur in these tests.

Official contracts checked 2026-09-10: [model and structured extraction example](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite),
[generation config and usage metadata](https://ai.google.dev/api/generate-content),
[standard token pricing](https://ai.google.dev/gemini-api/docs/pricing).
Model correctness, generated runtime packaging and live source ingestion require
their separate release evidence. This slice remains IMPLEMENTED_UNPROVEN until
the plan's semantic and real-use gates pass.
