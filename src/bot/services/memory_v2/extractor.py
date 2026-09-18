"""Pure structured extraction; persistence and source ownership stay with Z06/Z05."""

import json
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo

from services.memory_budget import MemoryBudgetPaused
from services.repositories.rate_limit import RateLimitRepository

from .evidence import EVIDENCE_DEFER_REASON, EVIDENCE_RETRY_SECONDS, complete_evidence_span
from .extraction_prompt import (
    MAX_BATCH_SOURCES,
    MAX_INPUT_UPPER_BYTES,
    MODEL,
    build_request,
    input_upper_bytes,
    unique_object,
    validate_source,
)
from .models import (
    EvidenceSpan,
    ExtractionResult,
    ExtractionSource,
    FactChange,
    MemoryInputError,
)
from .safety import require_public_content, require_verbatim_name

MAX_ATTEMPTS = 2
_FACT_KEYS = {"field", "value", "evidence", "action", "facet", "attribution"}
_ATTRIBUTIONS = {"self_explicit", "ambiguous", "third_party", "quoted", "instruction", "sensitive"}


class Budget(Protocol):
    def check_available(self): ...

    def reserve(self, attempt_id: str, *, purpose: str, model: str): ...

    def settle(self, reservation, usage_metadata: dict | None): ...


class Provider(Protocol):
    async def generate(self, request: dict) -> dict: ...


def _span_for_excerpt(source, excerpt):
    if not isinstance(excerpt, str) or not excerpt.strip() or len(excerpt) > 240:
        raise MemoryInputError("Invalid extraction evidence")
    eligible = []
    start = source.text.find(excerpt)
    while start >= 0:
        end = start + len(excerpt)
        if not any(start < quote_end and end > quote_start for quote_start, quote_end in source.quoted_spans):
            eligible.append(EvidenceSpan(start, end))
        start = source.text.find(excerpt, start + 1)
    if len(eligible) != 1:
        raise MemoryInputError("Evidence is absent, quoted or ambiguous")
    require_public_content(excerpt, max_length=240)
    complete = complete_evidence_span(source.text, source.quoted_spans)
    if complete is None or complete.start > eligible[0].start or complete.end < eligible[0].end:
        raise MemoryInputError("Complete source evidence is unsupported")
    require_public_content(complete.excerpt({"text": source.text, "quoted_spans": source.quoted_spans}), max_length=240)
    return complete


def _parse_facts(source, facts):
    if not isinstance(facts, list) or len(facts) > 16:
        raise MemoryInputError("Invalid number of extraction facts")
    changes, slots = [], set()
    for fact in facts:
        if not isinstance(fact, dict) or set(fact) != _FACT_KEYS or any(not isinstance(v, str) for v in fact.values()):
            raise MemoryInputError("Invalid extraction fact shape")
        if fact["attribution"] not in _ATTRIBUTIONS:
            raise MemoryInputError("Unknown extraction attribution")
        if fact["attribution"] != "self_explicit":
            continue
        evidence = _span_for_excerpt(source, fact["evidence"])
        change = FactChange(
            field=fact["field"],
            value=fact["value"],
            evidence=evidence,
            action=fact["action"],
            facet=fact["facet"],
        )
        slot, value = change.slot()
        require_public_content(value, max_length=160)
        if change.field == "communication_preferences" and change.facet == "name":
            # Check the model's original evidence too: expansion cannot rescue a
            # borrowed name found elsewhere in the message.
            require_verbatim_name(value, fact["evidence"])
        if change.field == "location" and any(character.isdigit() for character in value):
            raise MemoryInputError("Only city-level locations can be extracted")
        identity = (change.field, slot)
        if identity in slots:
            raise MemoryInputError("Conflicting extraction changes to one fact slot")
        slots.add(identity)
        changes.append(change)
    return tuple(changes)


def parse_extraction_response(payload: dict, sources: list[ExtractionSource]) -> list[ExtractionResult]:
    """Validate the whole attribution envelope before isolating fact errors by source."""
    if any(complete_evidence_span(source.text, source.quoted_spans) is None for source in sources):
        raise MemoryInputError("Complete source evidence is unsupported")
    if not isinstance(payload, dict):
        raise MemoryInputError("Invalid extraction response")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1 or not isinstance(candidates[0], dict):
        raise MemoryInputError("Expected one extraction candidate")
    candidate = candidates[0]
    if candidate.get("finishReason") != "STOP":
        raise MemoryInputError("Extraction was blocked or incomplete")
    content = candidate.get("content")
    if not isinstance(content, dict):
        raise MemoryInputError("Extraction had no content")
    parts = content.get("parts")
    if not isinstance(parts, list):
        raise MemoryInputError("Extraction had no text")
    texts = [
        part["text"]
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str) and not part.get("thought")
    ]
    try:
        document = json.loads("".join(texts), object_pairs_hook=unique_object)
    except json.JSONDecodeError as exc:
        raise MemoryInputError("Invalid extraction JSON") from exc
    if not isinstance(document, dict) or set(document) != {"sources"} or not isinstance(document["sources"], list):
        raise MemoryInputError("Invalid extraction result shape")
    indexed = {}
    for item in document["sources"]:
        if not isinstance(item, dict) or set(item) != {"source_index", "facts"}:
            raise MemoryInputError("Invalid extraction source shape")
        index = item["source_index"]
        if type(index) is not int or index not in range(len(sources)) or index in indexed:
            raise MemoryInputError("Extraction source attribution is invalid")
        indexed[index] = item["facts"]
    if set(indexed) != set(range(len(sources))):
        raise MemoryInputError("Extraction omitted a source")
    results = []
    for index, source in enumerate(sources):
        try:
            changes = _parse_facts(source, indexed[index])
        except MemoryInputError:
            # Never commit a valid prefix from a source with any invalid fact.
            results.append(ExtractionResult(source.ref, status="defer", reason="invalid_source_facts"))
        else:
            results.append(ExtractionResult(source.ref, changes))
    return results


class MemoryExtractor:
    """At most two individually budgeted attempts; errors never become empty facts.

    validate_sources is mandatory and checks this invocation's current leases,
    controls and exact source versions immediately before each provider attempt.
    """

    def __init__(
        self,
        *,
        provider: Provider,
        budget: Budget,
        validate_sources: Callable[[list[ExtractionSource]], Awaitable[None]],
        rate_limit=None,
        clock=time.time,
        attempt_id_factory=lambda: uuid.uuid4().hex,
    ):
        self.provider = provider
        self.budget = budget
        self.validate_sources = validate_sources
        self.rate_limit = rate_limit if rate_limit is not None else RateLimitRepository()
        self.clock = clock
        self.attempt_id_factory = attempt_id_factory

    def _defer(self, sources, reason, *, retry_at=None):
        if type(retry_at) is not int or retry_at <= int(self.clock()):
            retry_at = int(self.clock()) + 60
        return [ExtractionResult(source.ref, status="defer", reason=reason, retry_at=retry_at) for source in sources]

    def _budget_defer(self, sources, exc):
        retry_at = getattr(exc, "retry_after", None)
        if isinstance(exc, MemoryBudgetPaused) and (type(retry_at) is not int or retry_at <= int(self.clock())):
            retry_at = int(self.clock()) + 3600
        return self._defer(sources, "budget_unavailable", retry_at=retry_at)

    def _quota_reset(self):
        # Use the same daily boundary as RateLimitRepository, including DST.
        pacific = ZoneInfo("America/Los_Angeles")
        tomorrow = datetime.fromtimestamp(self.clock(), pacific).date() + timedelta(days=1)
        return int(datetime.combine(tomorrow, datetime.min.time(), tzinfo=pacific).astimezone(timezone.utc).timestamp())

    async def extract_batch(self, sources: list[ExtractionSource]) -> list[ExtractionResult]:
        if not sources:
            return []
        if len(sources) > MAX_BATCH_SOURCES:
            return self._defer(sources, "batch_input_limit")
        for source in sources:
            validate_source(source)
        scopes = {(str(source.chat_id), source.ref.epoch) for source in sources}
        if len(scopes) != 1 or len({source.ref for source in sources}) != len(sources):
            raise MemoryInputError("Extraction batch mixes scope or duplicate sources")
        eligible, deferred = [], []
        for source in sources:
            if complete_evidence_span(source.text, source.quoted_spans) is None:
                deferred.extend(
                    self._defer([source], EVIDENCE_DEFER_REASON, retry_at=int(self.clock()) + EVIDENCE_RETRY_SECONDS)
                )
            else:
                eligible.append(source)
        results = await self._extract_eligible(eligible) if eligible else []
        by_ref = {result.ref: result for result in [*deferred, *results]}
        return [by_ref[source.ref] for source in sources]

    async def _extract_eligible(self, sources):
        if input_upper_bytes(sources) > MAX_INPUT_UPPER_BYTES:
            return self._defer(sources, "batch_input_limit")
        pending, completed = sources, {}

        def finish(unresolved):
            by_ref = {**completed, **{result.ref: result for result in unresolved}}
            return [by_ref[source.ref] for source in sources]

        for _ in range(MAX_ATTEMPTS):
            # Local indices belong only to this request; immutable refs restore
            # the original order after retries and the earlier evidence filter.
            request = build_request(pending)
            await self.validate_sources(pending)
            try:
                self.budget.check_available()
            except Exception as exc:
                return finish(self._budget_defer(pending, exc))
            try:
                count, within_limit = self.rate_limit.increment_and_check()
                # The legacy quota adapter returns (0, True) on storage failure.
                # Never interpret that sentinel as permission for a V2 model call.
                if type(count) is not int or count < 1 or type(within_limit) is not bool:
                    return finish(self._defer(pending, "daily_quota_unavailable"))
                if not within_limit:
                    return finish(self._defer(pending, "daily_quota_exhausted", retry_at=self._quota_reset()))
            except Exception:
                return finish(self._defer(pending, "daily_quota_unavailable"))
            try:
                reservation = self.budget.reserve(self.attempt_id_factory(), purpose="extract", model=MODEL)
            except Exception as exc:
                # DuplicateMemoryAttempt is also a hard no-call result. No retry
                # can bypass a denied or uncertain financial reservation.
                return finish(self._budget_defer(pending, exc))
            if reservation is None or reservation is False:
                return finish(self._defer(pending, "budget_unavailable"))
            # Storage calls above can outlive a source/lease. Validate again at
            # the actual model boundary; an unused reservation stays conservative.
            await self.validate_sources(pending)
            try:
                payload = await self.provider.generate(request)
            except Exception:
                # No trusted provider usage: keep the full reservation, then make
                # a separately reserved attempt if there is time/budget left.
                continue
            try:
                self.budget.settle(reservation, payload.get("usageMetadata"))
            except Exception:
                return finish(self._defer(pending, "budget_settlement_unavailable"))
            try:
                results = parse_extraction_response(payload, pending)
            except MemoryInputError:
                continue
            completed.update((result.ref, result) for result in results if result.status == "complete")
            pending = [source for source in pending if source.ref not in completed]
            if not pending:
                return finish([])
        return finish(self._defer(pending, "provider_or_schema_unavailable"))
