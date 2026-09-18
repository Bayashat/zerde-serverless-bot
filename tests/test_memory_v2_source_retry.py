"""F3 failure shape: isolate a bad source without weakening attribution or billing."""

import asyncio
import json
from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from services.memory_v2 import extractor as extraction
from services.memory_v2.extraction_prompt import input_upper_bytes
from services.memory_v2.models import MemoryInputError, MemoryUnavailable
from services.memory_v2.worker import MemoryWorker

from tests import test_memory_v2_contract as contract
from tests.test_memory_v2_contract import CHAT, USER, activate, event
from tests.test_memory_v2_extraction import extractor, fact, response, source
from tests.test_memory_v2_ingestion import records

env = contract.env


def batch():
    # Put the invalid name in the middle to catch accidental reuse of old indices.
    sources = [
        source("Я предпочитаю официальный тон."),
        source("Call me Aster.", message_id="9"),
        source("Thanks.", message_id="10", actor="99"),
    ]
    facts = [
        [fact(sources[0].text, field="communication_preferences", facet="tone", value="formal")],
        [fact(sources[1].text, field="communication_preferences", facet="name", value="formal")],
        [],
    ]
    return sources, response(document={"sources": [{"source_index": i, "facts": f} for i, f in enumerate(facts)]})


def corrected():
    return response([fact("Call me Aster.", field="communication_preferences", facet="name", value="Aster")])


def assert_neighbors(results, sources):
    assert [r.ref for r in results] == [s.ref for s in sources]
    assert results[0].status == results[2].status == "complete"
    assert results[0].changes[0].value == "formal"
    assert results[2].changes == ()


def test_only_invalid_source_retried_and_restored_by_ref_with_fresh_local_indices():
    sources, payload = batch()
    instance, provider, budget, validate, quota = extractor(replies=[payload, corrected()])
    results = asyncio.run(instance.extract_batch(sources))
    assert_neighbors(results, sources)
    assert results[1].status == "complete" and results[1].changes[0].value == "Aster"
    sent = json.loads(provider.generate.await_args_list[1].args[0]["contents"][0]["parts"][0]["text"])
    assert sent == {"sources": [{"source_index": 0, "text": sources[1].text, "quoted_spans": []}]}
    assert [c.args[0] for c in validate.await_args_list] == [sources, sources, [sources[1]], [sources[1]]]
    assert provider.generate.await_count == budget.reserve.call_count == budget.settle.call_count == 2
    assert quota.increment_and_check.call_count == 2


@pytest.mark.parametrize(
    "failure,reason,attempts",
    [
        ("transport", "provider_or_schema_unavailable", 2),
        ("envelope", "provider_or_schema_unavailable", 2),
        ("facts", "provider_or_schema_unavailable", 2),
        ("settlement", "budget_settlement_unavailable", 2),
        ("preflight", "budget_unavailable", 1),
        ("reserve", "budget_unavailable", 1),
        ("uncertain_reserve", "budget_unavailable", 1),
        ("quota", "daily_quota_unavailable", 1),
        ("quota_exception", "daily_quota_unavailable", 1),
        ("quota_exhausted", "daily_quota_exhausted", 1),
    ],
)
def test_second_attempt_failures_preserve_completed_neighbors(failure, reason, attempts):
    sources, payload = batch()
    second = corrected()
    if failure == "transport":
        second = TimeoutError("synthetic")
    elif failure == "envelope":
        second = response(document={"sources": []})
    elif failure == "facts":
        second = response([fact("Call me Aster.", field="communication_preferences", facet="name", value="formal")])
    instance, provider, budget, _, quota = extractor(replies=[payload, second])
    if failure == "settlement":
        budget.settle.side_effect = [None, RuntimeError("uncertain settlement")]
    elif failure == "preflight":
        budget.check_available.side_effect = [None, RuntimeError("paused")]
    elif failure in {"reserve", "uncertain_reserve"}:
        budget.reserve.side_effect = ["reservation-1", RuntimeError("denied") if failure == "reserve" else None]
    elif failure.startswith("quota"):
        quota.increment_and_check.side_effect = [
            (1, True),
            (
                RuntimeError("unavailable")
                if failure == "quota_exception"
                else (0, True) if failure == "quota" else (2, False)
            ),
        ]
    results = asyncio.run(instance.extract_batch(sources))
    assert_neighbors(results, sources)
    assert (results[1].status, results[1].reason, results[1].changes) == ("defer", reason, ())
    assert results[1].retry_at > instance.clock()
    assert provider.generate.await_count == attempts


def test_source_rejection_is_atomic_even_when_earlier_facts_are_valid():
    original = source("I use Python. Call me Aster.")
    result = extraction.parse_extraction_response(
        response(
            [fact(original.text), fact(original.text, field="communication_preferences", facet="name", value="formal")]
        ),
        [original],
    )[0]
    assert result.status == "defer" and result.changes == ()


@pytest.mark.parametrize("indices", [[0, 1], [0, 1, 2, 3], [0, 1, 1], [0, True, 2]])
def test_entire_envelope_is_validated_before_any_fact_parsing(monkeypatch, indices):
    sources, _ = batch()
    parse_facts = MagicMock(side_effect=AssertionError("must not parse facts before attribution is complete"))
    monkeypatch.setattr(extraction, "_parse_facts", parse_facts)
    with pytest.raises(MemoryInputError):
        extraction.parse_extraction_response(
            response(document={"sources": [{"source_index": i, "facts": []} for i in indices]}), sources
        )
    parse_facts.assert_not_called()


@pytest.mark.parametrize("error", [TypeError("bug"), AttributeError("bug"), RuntimeError("bug"), ValueError("bug")])
def test_unknown_parser_errors_abort_instead_of_returning_partial_success(monkeypatch, error):
    sources, payload = batch()
    instance, provider, budget, _, _ = extractor(replies=[payload, corrected()])
    parser = extraction.parse_extraction_response
    calls = 0

    def parse(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise error
        return parser(*args)

    monkeypatch.setattr(extraction, "parse_extraction_response", parse)
    with pytest.raises(type(error), match="bug"):
        asyncio.run(instance.extract_batch(sources))
    assert provider.generate.await_count == budget.settle.call_count == 2


@pytest.mark.parametrize("error", [MemoryUnavailable("source changed"), asyncio.CancelledError()])
def test_second_source_validation_failure_or_cancellation_is_not_swallowed(error):
    sources, payload = batch()
    instance, provider, budget, validate, _ = extractor(replies=[payload])
    validate.side_effect = [None, None, error]
    with pytest.raises(type(error)):
        asyncio.run(instance.extract_batch(sources))
    assert provider.generate.await_count == budget.reserve.call_count == 1


@pytest.mark.parametrize("edit_completed", [False, True])
def test_real_worker_commits_valid_neighbor_but_never_stale_or_partial_source(env, edit_completed):
    activate(env)
    sources, payload = batch()
    events = [event(env, s.ref.source_id, s.text, user=s.actor_user_id) for s in sources]
    refs = [env.repo.register_source(item) for item in events]
    instance, provider, _, _, _ = extractor()
    instance.clock = lambda: env.clock.now
    calls = 0

    async def generate(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return payload
        if edit_completed:
            env.clock.now += 1
            env.repo.register_source(
                replace(events[0], text="I prefer a friendly tone.", edited_at=env.clock.now),
                expected_source_version=refs[0].source_version,
            )
        # Repeat the real invalid output for the one remaining source.
        return response([fact("Call me Aster.", field="communication_preferences", facet="name", value="formal")])

    provider.generate.side_effect = generate

    def factory(validate):
        instance.validate_sources = validate
        return instance

    worker = MemoryWorker(env.repo, factory, sizing_fn=input_upper_bytes)
    assert asyncio.run(worker.handle_records(records(*refs))) == {"batchItemFailures": []}
    assert env.repo.get_work(CHAT, refs[1])["state"] == "PENDING"
    assert env.repo.get_work(CHAT, refs[2])["state"] == "DONE"
    profile = env.repo.get_profile(CHAT, USER)
    assert [f["value"] for f in profile] == ([] if edit_completed else ["formal"])
    if not edit_completed:
        assert env.repo.get_work(CHAT, refs[0])["state"] == "DONE"
    assert calls == 2
