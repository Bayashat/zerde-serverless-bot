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
from .safety import require_preference_name, require_public_content

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
    return eligible[0]


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
            require_preference_name(value)
        if change.field == "location" and any(character.isdigit() for character in value):
            raise MemoryInputError("Only city-level locations can be extracted")
        identity = (change.field, slot)
        if identity in slots:
            raise MemoryInputError("Conflicting extraction changes to one fact slot")
        slots.add(identity)
        changes.append(change)
    return tuple(changes)


def parse_extraction_response(payload: dict, sources: list[ExtractionSource]) -> list[ExtractionResult]:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1 or not isinstance(candidates[0], dict):
        raise MemoryInputError("Expected one extraction candidate")
    candidate = candidates[0]
    if candidate.get("finishReason") != "STOP":
        raise MemoryInputError("Extraction was blocked or incomplete")
    parts = (candidate.get("content") or {}).get("parts")
    if not isinstance(parts, list):
        raise MemoryInputError("Extraction had no text")
    texts = [
        part["text"]
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str) and not part.get("thought")
    ]
    document = json.loads("".join(texts), object_pairs_hook=unique_object)
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
    return [ExtractionResult(source.ref, _parse_facts(source, indexed[index])) for index, source in enumerate(sources)]


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
        if input_upper_bytes(sources) > MAX_INPUT_UPPER_BYTES:
            return self._defer(sources, "batch_input_limit")
        request = build_request(sources)
        for _ in range(MAX_ATTEMPTS):
            await self.validate_sources(sources)
            try:
                self.budget.check_available()
            except Exception as exc:
                return self._budget_defer(sources, exc)
            try:
                count, within_limit = self.rate_limit.increment_and_check()
                # The legacy quota adapter returns (0, True) on storage failure.
                # Never interpret that sentinel as permission for a V2 model call.
                if type(count) is not int or count < 1 or type(within_limit) is not bool:
                    return self._defer(sources, "daily_quota_unavailable")
                if not within_limit:
                    return self._defer(sources, "daily_quota_exhausted", retry_at=self._quota_reset())
            except Exception:
                return self._defer(sources, "daily_quota_unavailable")
            try:
                reservation = self.budget.reserve(self.attempt_id_factory(), purpose="extract", model=MODEL)
            except Exception as exc:
                # DuplicateMemoryAttempt is also a hard no-call result. No retry
                # can bypass a denied or uncertain financial reservation.
                return self._budget_defer(sources, exc)
            if reservation is None or reservation is False:
                return self._defer(sources, "budget_unavailable")
            # Storage calls above can outlive a source/lease. Validate again at
            # the actual model boundary; an unused reservation stays conservative.
            await self.validate_sources(sources)
            try:
                payload = await self.provider.generate(request)
            except Exception:
                # No trusted provider usage: keep the full reservation, then make
                # a separately reserved attempt if there is time/budget left.
                continue
            try:
                self.budget.settle(reservation, payload.get("usageMetadata"))
            except Exception:
                return self._defer(sources, "budget_settlement_unavailable")
            try:
                return parse_extraction_response(payload, sources)
            except (MemoryInputError, ValueError, TypeError, AttributeError):
                continue
        return self._defer(sources, "provider_or_schema_unavailable")
