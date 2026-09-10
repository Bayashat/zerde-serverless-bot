"""Real SDK transactions: budget contention, unknown billing and exactly-once refunds."""

from datetime import datetime, timezone
from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws
from services.memory_budget import (
    MONTHLY_LIMIT_MICRO_USD,
    RESERVATION_MICRO_USD,
    DuplicateMemoryAttempt,
    MemoryBudgetAccountingError,
    MemoryBudgetPaused,
    MemoryBudgetRepository,
    Reservation,
    cost_micro_usd,
)


def usage(inputs=100, candidates=50, thoughts=20):
    return {
        "promptTokenCount": inputs,
        "candidatesTokenCount": candidates,
        "thoughtsTokenCount": thoughts,
        "totalTokenCount": inputs + candidates + thoughts,
    }


@pytest.fixture
def budget(monkeypatch):
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="eu-central-1")
        resource.create_table(
            TableName="memory-budget-test",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setattr("services.memory_budget.get_dynamodb", lambda: resource)
        now = [datetime(2026, 9, 10, tzinfo=timezone.utc).timestamp()]
        repo = MemoryBudgetRepository("memory-budget-test", clock=lambda: now[0])
        yield repo, now


def test_real_transaction_reserves_and_refunds_once(budget):
    repo, _ = budget
    reservation = repo.reserve("network-attempt-1", purpose="extract")
    assert repo.snapshot()["charged_micro_usd"] == RESERVATION_MICRO_USD
    with pytest.raises(DuplicateMemoryAttempt):
        repo.reserve("network-attempt-1", purpose="extract")
    assert repo.settle(reservation, usage()) is True
    assert repo.settle(reservation, usage()) is True
    assert repo.snapshot()["charged_micro_usd"] == cost_micro_usd(100, 70)
    with pytest.raises(DuplicateMemoryAttempt):
        repo.reserve("network-attempt-1", purpose="extract")


def test_last_reservation_cannot_cross_monthly_limit(budget):
    repo, _ = budget
    count = MONTHLY_LIMIT_MICRO_USD // RESERVATION_MICRO_USD
    for i in range(count):
        repo.reserve(f"failed-network-{i}", purpose="answer")
    with pytest.raises(MemoryBudgetPaused):
        repo.reserve("last", purpose="answer")
    assert repo.snapshot()["charged_micro_usd"] == count * RESERVATION_MICRO_USD
    assert not repo.table.get_item(Key=repo._attempt_key(repo.month(), "last")).get("Item")


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"promptTokenCount": 1},
        usage(inputs=True),
        {**usage(), "totalTokenCount": 999},
        {**usage(), "promptTokensDetails": [{"modality": "AUDIO"}]},
        {**usage(), "serviceTier": "PRIORITY"},
    ],
)
def test_unknown_invalid_or_unpriced_usage_cannot_refund(budget, data):
    repo, _ = budget
    reservation = repo.reserve("unknown", purpose="extract")
    assert repo.settle(reservation, data) is False
    assert repo.snapshot()["charged_micro_usd"] == RESERVATION_MICRO_USD


def test_omitted_thoughts_deduced_from_documented_total(budget):
    repo, _ = budget
    reservation = repo.reserve("no-thought-field", purpose="extract")
    data = usage()
    del data["thoughtsTokenCount"]
    assert repo.settle(reservation, data)
    assert repo.snapshot()["charged_micro_usd"] == cost_micro_usd(100, 70)


def test_changed_usage_cannot_refund_twice(budget):
    repo, _ = budget
    reservation = repo.reserve("settle-twice", purpose="extract")
    repo.settle(reservation, usage())
    with pytest.raises(MemoryBudgetAccountingError):
        repo.settle(reservation, usage(candidates=0))
    assert repo.snapshot()["charged_micro_usd"] == cost_micro_usd(100, 70)


def test_month_rollover_does_not_reuse_attempt_or_refund_new_month(budget):
    repo, now = budget
    old = repo.reserve("same-attempt", purpose="extract")
    now[0] = datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp()
    with pytest.raises(DuplicateMemoryAttempt):
        repo.reserve("same-attempt", purpose="answer")
    current = repo.reserve("new-attempt", purpose="answer")
    repo.settle(old, usage())
    assert repo.snapshot()["charged_micro_usd"] == RESERVATION_MICRO_USD
    assert repo.snapshot(month="2026-09")["charged_micro_usd"] == cost_micro_usd(100, 70)
    forged = Reservation("2026-09", current.attempt_id, current.token, current.reserved_micro_usd)
    with pytest.raises(MemoryBudgetAccountingError):
        repo.settle(forged, usage())


def test_lost_commit_response_reserve_never_authorizes_second_call(budget):
    repo, _ = budget
    original = repo.table.meta.client.transact_write_items

    def lost(**kwargs):
        original(**kwargs)
        raise TimeoutError("synthetic lost reply")

    with patch.object(repo.table.meta.client, "transact_write_items", side_effect=lost):
        with pytest.raises(TimeoutError):
            repo.reserve("ambiguous", purpose="extract")
    with pytest.raises(DuplicateMemoryAttempt):
        repo.reserve("ambiguous", purpose="extract")
    assert repo.snapshot()["charged_micro_usd"] == RESERVATION_MICRO_USD


def test_settlement_response_lost_can_retry_without_double_refund(budget):
    repo, _ = budget
    reservation = repo.reserve("settlement", purpose="answer")
    original = repo.table.meta.client.transact_write_items

    def lost(**kwargs):
        original(**kwargs)
        raise TimeoutError("synthetic lost reply")

    with patch.object(repo.table.meta.client, "transact_write_items", side_effect=lost):
        with pytest.raises(TimeoutError):
            repo.settle(reservation, usage())
    assert repo.settle(reservation, usage())
    assert repo.snapshot()["charged_micro_usd"] == cost_micro_usd(100, 70)


def test_database_fault_never_returns_permit(budget):
    repo, _ = budget
    fault = ClientError({"Error": {"Code": "ProvisionedThroughputExceededException"}}, "TransactWriteItems")
    with patch.object(repo.table.meta.client, "transact_write_items", side_effect=fault):
        with pytest.raises(ClientError):
            repo.reserve("throttled", purpose="extract")
    assert not repo.snapshot()


def test_usage_anomaly_records_liability_and_pauses_without_duplicate_charge(budget):
    repo, _ = budget
    reservation = repo.reserve("anomaly", purpose="extract")
    data = usage(inputs=2_000_000, candidates=200_000)
    for _ in range(2):
        with pytest.raises(MemoryBudgetAccountingError):
            repo.settle(reservation, data)
    assert repo.snapshot()["charged_micro_usd"] == cost_micro_usd(2_000_000, 200_020)
    assert repo.snapshot()["paused"] is True
    with pytest.raises(MemoryBudgetPaused):
        repo.reserve("after-anomaly", purpose="extract")


@pytest.mark.parametrize("model,purpose", [("new-unpriced-model", "extract"), ("gemini-3.1-flash-lite", "media")])
def test_unpriced_calls_rejected_before_database(budget, model, purpose):
    repo, _ = budget
    with pytest.raises(ValueError):
        repo.reserve("unpriced", purpose=purpose, model=model)
    assert not repo.snapshot()
