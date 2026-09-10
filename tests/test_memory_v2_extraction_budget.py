"""Exercise the extraction boundary with the actual Moto-backed budget owner."""

import asyncio

from services.memory_budget import RESERVATION_MICRO_USD, cost_micro_usd

from tests import test_memory_budget as budget_fixtures
from tests.test_memory_v2_extraction import extractor, response, source


def test_actual_budget_settles_successful_extraction_with_provider_usage(budget):
    repository, _ = budget
    instance, provider, _, _, _ = extractor()
    instance.budget = repository
    result = asyncio.run(instance.extract_batch([source()]))[0]
    assert result.status == "complete" and result.changes
    assert provider.generate.await_count == 1
    assert repository.snapshot()["charged_micro_usd"] == cost_micro_usd(100, 45)


def test_actual_duplicate_attempt_cannot_call_provider(budget):
    repository, _ = budget
    repository.reserve("attempt-1", purpose="extract")
    instance, provider, _, _, _ = extractor()
    instance.budget = repository
    result = asyncio.run(instance.extract_batch([source()]))[0]
    assert result.status == "defer"
    provider.generate.assert_not_awaited()
    assert repository.snapshot()["charged_micro_usd"] == RESERVATION_MICRO_USD


def test_unknown_transport_attempts_consume_separate_actual_reservations(budget):
    repository, _ = budget
    instance, provider, _, _, _ = extractor(replies=[TimeoutError(), TimeoutError()])
    instance.budget = repository
    result = asyncio.run(instance.extract_batch([source()]))[0]
    assert result.status == "defer" and provider.generate.await_count == 2
    assert repository.snapshot()["charged_micro_usd"] == 2 * RESERVATION_MICRO_USD


def test_complete_empty_extraction_with_unknown_usage_keeps_full_reservation(budget):
    repository, _ = budget
    instance, _, _, _, _ = extractor(replies=[response(usageMetadata=None)])
    instance.budget = repository
    result = asyncio.run(instance.extract_batch([source()]))[0]
    assert result.status == "complete" and not result.changes
    assert repository.snapshot()["charged_micro_usd"] == RESERVATION_MICRO_USD


def test_actual_paused_budget_does_not_consume_shared_provider_quota(budget):
    repository, _ = budget
    repository.table.put_item(Item={"pk": "MEMORY_BUDGET#CONTROL", "sk": "MODEL", "paused": True})
    instance, provider, _, _, quota = extractor()
    instance.budget = repository
    result = asyncio.run(instance.extract_batch([source()]))[0]
    assert result.status == "defer" and result.reason == "budget_unavailable"
    quota.increment_and_check.assert_not_called()
    provider.generate.assert_not_awaited()
    assert not repository.snapshot()


budget = budget_fixtures.budget
