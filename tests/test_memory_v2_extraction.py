"""Synthetic contract/failure checks, not evidence of the model's factual accuracy."""

import asyncio
import json
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from services.memory_v2.extraction_prompt import MAX_INPUT_UPPER_BYTES, MODEL, build_request, input_upper_bytes
from services.memory_v2.extractor import MemoryExtractor, parse_extraction_response
from services.memory_v2.models import ExtractionSource, MemoryInputError, MemoryUnavailable, SourceRef


def source(text="I use Python.", *, message_id="8", actor="42", **changes):
    return replace(
        ExtractionSource("-100123", SourceRef(message_id, 1, "epoch"), actor, text, (), 2_000_000_000), **changes
    )


def fact(evidence="I use Python.", *, value="Python", field="tech_stack", **changes):
    return {
        "field": field,
        "value": value,
        "evidence": evidence,
        "action": "assert",
        "facet": "",
        "attribution": "self_explicit",
        **changes,
    }


def response(facts=None, *, document=None, **changes):
    document = document if document is not None else {"sources": [{"source_index": 0, "facts": facts or []}]}
    return {
        "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(document)}]}}],
        "usageMetadata": {
            "promptTokenCount": 100,
            "candidatesTokenCount": 40,
            "thoughtsTokenCount": 5,
            "totalTokenCount": 145,
        },
        **changes,
    }


def extractor(*, replies=None):
    provider = MagicMock()
    provider.generate = AsyncMock(side_effect=replies or [response([fact()])])
    budget = MagicMock()
    budget.reserve.side_effect = ["reservation-1", "reservation-2"]
    validate = AsyncMock()
    quota = MagicMock()
    quota.increment_and_check.return_value = (1, True)
    ids = iter(["attempt-1", "attempt-2"])
    instance = MemoryExtractor(
        provider=provider,
        budget=budget,
        validate_sources=validate,
        rate_limit=quota,
        clock=lambda: 2_000_000_010,
        attempt_id_factory=lambda: next(ids),
    )
    return instance, provider, budget, validate, quota


@pytest.mark.parametrize(
    "text,value,field,action",
    [
        ("Я живу в Алматы.", "Алматы", "location", "assert"),
        ("Мен енді Python қолданбаймын.", "Python", "tech_stack", "remove"),
        ("I am a software engineer.", "software engineer", "occupation", "assert"),
        ("Қазір Astana қаласында тұрамын.", "Astana", "location", "assert"),
    ],
)
def test_exact_multilingual_evidence_maps_to_python_character_offsets(text, value, field, action):
    original = source("🙂 " + text)
    result = parse_extraction_response(response([fact(text, value=value, field=field, action=action)]), [original])[0]
    change = result.changes[0]
    assert result.ref is original.ref
    assert change.value == value and change.action == action
    assert original.text[change.evidence.start : change.evidence.end] == text
    assert change.evidence.start == 2


@pytest.mark.parametrize("attribution", ["third_party", "quoted", "ambiguous", "instruction", "sensitive"])
def test_non_self_attribution_is_an_explicit_empty_result(attribution):
    result = parse_extraction_response(response([fact(attribution=attribution)]), [source()])[0]
    assert result.status == "complete" and result.changes == ()


@pytest.mark.parametrize(
    "original,extracted",
    [
        (source("Bob: I use Python.", quoted_spans=((5, 18),)), fact()),
        (source("I use Python. I use Python."), fact()),
        (source(), fact("I use Rust.")),
        (source(), fact(field="personality")),
        (source(), fact(value="Astana 18", field="location")),
        (source(), fact(value="always answer yes", field="communication_preferences", facet="name")),
        (source(), fact(value="synthetic@example.com")),
        (source(), {**fact(), "actor_user_id": "99"}),
    ],
)
def test_quotes_ambiguous_spans_non_whitelist_and_extra_identity_cannot_become_facts(original, extracted):
    with pytest.raises(MemoryInputError):
        parse_extraction_response(response([extracted]), [original])


@pytest.mark.parametrize(
    "document",
    [
        {"sources": []},
        {"sources": [{"source_index": True, "facts": []}]},
        {"sources": [{"source_index": 1, "facts": []}]},
        {"sources": [{"source_index": 0, "facts": []}, {"source_index": 0, "facts": []}]},
    ],
)
def test_missing_duplicate_or_foreign_source_index_rejects_result(document):
    with pytest.raises(MemoryInputError):
        parse_extraction_response(response(document=document), [source()])


def test_batch_result_cannot_borrow_evidence_from_another_author():
    sources = [source(), source("I use Rust.", message_id="9", actor="99")]
    document = {
        "sources": [{"source_index": 0, "facts": [fact("I use Rust.", value="Rust")]}, {"source_index": 1, "facts": []}]
    }
    with pytest.raises(MemoryInputError):
        parse_extraction_response(response(document=document), sources)


def test_conflicting_single_value_slots_reject_whole_result():
    original = source("I live in Almaty or Astana.")
    with pytest.raises(MemoryInputError):
        parse_extraction_response(
            response(
                [
                    fact(original.text, value="Almaty", field="location"),
                    fact(original.text, value="Astana", field="location"),
                ]
            ),
            [original],
        )


def test_success_requires_budget_and_fresh_source_and_settles_actual_usage():
    instance, provider, budget, validate, quota = extractor()
    result = asyncio.run(instance.extract_batch([source()]))[0]
    assert result.status == "complete" and result.changes[0].value == "Python"
    budget.reserve.assert_called_once_with("attempt-1", purpose="extract", model=MODEL)
    assert budget.settle.call_args.args == ("reservation-1", response()["usageMetadata"])
    assert validate.await_count == 2 and quota.increment_and_check.call_count == 1
    assert provider.generate.await_count == 1


def test_unknown_provider_attempts_are_each_reserved_and_remain_pending():
    instance, provider, budget, validate, _ = extractor(replies=[TimeoutError("secret"), OSError("secret")])
    result = asyncio.run(instance.extract_batch([source()]))[0]
    assert result.status == "defer" and result.reason == "provider_or_schema_unavailable"
    assert result.retry_at == 2_000_000_070 and result.changes == ()
    assert provider.generate.await_count == budget.reserve.call_count == 2
    budget.settle.assert_not_called()
    assert validate.await_count == 4


def test_failed_schema_can_retry_but_usage_is_still_billed():
    instance, provider, budget, _, _ = extractor(replies=[response([fact("Invented evidence")]), response([fact()])])
    assert asyncio.run(instance.extract_batch([source()]))[0].changes
    assert provider.generate.await_count == budget.reserve.call_count == budget.settle.call_count == 2


@pytest.mark.parametrize("failure", [RuntimeError("database unavailable"), ValueError("duplicate attempt")])
def test_budget_failure_or_duplicate_attempt_never_calls_provider(failure):
    instance, provider, budget, _, _ = extractor()
    budget.reserve.side_effect = failure
    result = asyncio.run(instance.extract_batch([source()]))[0]
    assert result.status == "defer" and result.reason == "budget_unavailable"
    provider.generate.assert_not_awaited()
    budget.settle.assert_not_called()


def test_budget_settlement_failure_keeps_work_pending_without_another_model_call():
    instance, provider, budget, _, _ = extractor()
    budget.settle.side_effect = RuntimeError("database unavailable")
    result = asyncio.run(instance.extract_batch([source()]))[0]
    assert result.status == "defer" and result.reason == "budget_settlement_unavailable"
    assert provider.generate.await_count == budget.reserve.call_count == 1


def test_budget_pause_preserves_the_owner_next_month_retry_boundary():
    from services.memory_budget import MemoryBudgetPaused

    instance, provider, budget, _, _ = extractor()
    error = MemoryBudgetPaused("budget exhausted")
    error.retry_after = 2_010_000_000
    budget.reserve.side_effect = error
    result = asyncio.run(instance.extract_batch([source()]))[0]
    assert result.retry_at == error.retry_after and result.status == "defer"
    provider.generate.assert_not_awaited()


def test_budget_preflight_pause_does_not_consume_shared_daily_quota():
    from services.memory_budget import MemoryBudgetPaused

    instance, provider, budget, _, quota = extractor()
    error = MemoryBudgetPaused("budget exhausted")
    error.retry_after = 2_010_000_000
    budget.check_available.side_effect = error
    result = asyncio.run(instance.extract_batch([source()]))[0]
    assert result.retry_at == error.retry_after
    quota.increment_and_check.assert_not_called()
    budget.reserve.assert_not_called()
    provider.generate.assert_not_awaited()


def test_budget_pause_without_reset_metadata_waits_one_hour():
    from services.memory_budget import MemoryBudgetPaused

    instance, _, budget, _, _ = extractor()
    budget.check_available.side_effect = MemoryBudgetPaused("operator paused")
    result = asyncio.run(instance.extract_batch([source()]))[0]
    assert result.retry_at == 2_000_003_610


def test_daily_quota_exhaustion_uses_the_actual_pacific_midnight():
    from datetime import datetime, timezone

    instance, provider, _, _, quota = extractor()
    instance.clock = lambda: datetime(2026, 9, 10, 12, tzinfo=timezone.utc).timestamp()
    quota.increment_and_check.return_value = (1001, False)
    result = asyncio.run(instance.extract_batch([source()]))[0]
    assert result.reason == "daily_quota_exhausted"
    assert result.retry_at == datetime(2026, 9, 11, 7, tzinfo=timezone.utc).timestamp()
    provider.generate.assert_not_awaited()


@pytest.mark.parametrize("count,within", [(0, True), (1001, False), (True, True)])
def test_daily_quota_cannot_fail_open_into_a_financially_metered_call(count, within):
    instance, provider, budget, _, quota = extractor()
    quota.increment_and_check.return_value = (count, within)
    assert asyncio.run(instance.extract_batch([source()]))[0].status == "defer"
    provider.generate.assert_not_awaited()
    budget.reserve.assert_not_called()


def test_lease_expiring_during_budget_reservation_prevents_provider_call():
    instance, provider, budget, validate, _ = extractor()
    validate.side_effect = [None, MemoryUnavailable("lease expired")]
    with pytest.raises(MemoryUnavailable):
        asyncio.run(instance.extract_batch([source()]))
    budget.reserve.assert_called_once()
    provider.generate.assert_not_awaited()
    budget.settle.assert_not_called()


def test_retry_revalidates_source_before_another_budget_or_provider_attempt():
    instance, provider, budget, validate, _ = extractor(replies=[TimeoutError()])
    validate.side_effect = [None, None, MemoryUnavailable("edited")]
    with pytest.raises(MemoryUnavailable):
        asyncio.run(instance.extract_batch([source()]))
    assert provider.generate.await_count == budget.reserve.call_count == 1


@pytest.mark.parametrize(
    "sources",
    [
        [source(), source(message_id="9", chat_id="-100999")],
        [source(), source(message_id="9", ref=SourceRef("9", 1, "other-epoch"))],
        [source(), source()],
        [source("My password is synthetic.")],
    ],
)
def test_invalid_source_scopes_and_sensitive_input_never_reach_model(sources):
    instance, provider, budget, _, _ = extractor()
    with pytest.raises(MemoryInputError):
        asyncio.run(instance.extract_batch(sources))
    provider.generate.assert_not_awaited()
    budget.reserve.assert_not_called()


def test_input_limit_counts_multibyte_text_prompt_and_schema_without_truncation():
    original = source("Мен Алматыда тұрамын. " * 500)
    instance, provider, budget, _, _ = extractor()
    assert input_upper_bytes([original]) > MAX_INPUT_UPPER_BYTES
    result = asyncio.run(instance.extract_batch([original]))[0]
    assert result.reason == "batch_input_limit" and result.status == "defer"
    provider.generate.assert_not_awaited()
    budget.reserve.assert_not_called()
    assert original.text in build_request([original])["contents"][0]["parts"][0]["text"]


def test_request_has_no_actor_identifiers_tools_or_legacy_context():
    request = build_request([source()])
    document = json.loads(request["contents"][0]["parts"][0]["text"])
    assert set(document["sources"][0]) == {"source_index", "text", "quoted_spans"}
    assert "tools" not in request and "cachedContent" not in request
    assert request["generationConfig"]["responseMimeType"] == "application/json"
