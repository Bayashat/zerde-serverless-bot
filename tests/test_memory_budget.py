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


def observed_standard_usage():
    """HTTP 200 metadata shape observed in the bounded 2026-09-11 smoke.

    Token counters only; no prompt, response text, credentials or real ledger.
    """
    return {
        "promptTokenCount": 403,
        "candidatesTokenCount": 11,
        "totalTokenCount": 414,
        "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 403}],
        "serviceTier": "standard",
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
        repo = MemoryBudgetRepository("memory-budget-test", clock=lambda: now[0], inventory_version="test-inventory")
        from services.memory_v2._cost_state import CostState

        CostState(repo, clock=lambda: now[0]).record_measurement(
            repo.month(),
            inventory_version="test-inventory",
            verified=True,
            estimate=0,
            covered_until=int(now[0]),
            reason="SYNTHETIC_COMPLETE_MEASUREMENT",
        )
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


@pytest.mark.parametrize("tier", ["standard", "unspecified", "omitted"])
def test_documented_standard_wire_usage_settles_actual_shape_once(budget, tier):
    repo, _ = budget
    reservation = repo.reserve("standard-http-200", purpose="answer")
    data = observed_standard_usage()
    if tier == "omitted":
        del data["serviceTier"]
    else:
        data["serviceTier"] = tier
    assert repo.settle(reservation, data) is True
    assert repo.settle(reservation, data) is True
    assert repo.snapshot()["charged_micro_usd"] == repo.snapshot()["settled_micro_usd"] == 118
    with pytest.raises(DuplicateMemoryAttempt):
        repo.reserve("standard-http-200", purpose="answer")


@pytest.mark.parametrize("committed", [False, True])
def test_actual_usage_settlement_database_fault_retries_only_accounting(budget, committed):
    repo, _ = budget
    reservation = repo.reserve("standard-settlement-fault", purpose="extract")
    actual_transaction = repo.table.meta.client.transact_write_items

    def fault(**kwargs):
        if committed:
            actual_transaction(**kwargs)
        raise TimeoutError("Synthetic unavailable settlement response")

    with patch.object(repo.table.meta.client, "transact_write_items", side_effect=fault):
        with pytest.raises(TimeoutError):
            repo.settle(reservation, observed_standard_usage())
    assert repo.snapshot()["charged_micro_usd"] == (118 if committed else RESERVATION_MICRO_USD)
    assert repo.settle(reservation, observed_standard_usage())
    assert repo.settle(reservation, observed_standard_usage())
    assert repo.snapshot()["charged_micro_usd"] == repo.snapshot()["settled_micro_usd"] == 118
    with pytest.raises(DuplicateMemoryAttempt):
        repo.reserve("standard-settlement-fault", purpose="extract")


@pytest.mark.parametrize(
    "tier",
    [
        "flex",
        "priority",
        "STANDARD",
        "SERVICE_TIER_UNSPECIFIED",
        "UNSPECIFIED",
        "Standard",
        " standard",
        "",
        None,
        0,
        False,
        [],
        {},
    ],
)
def test_undocumented_or_unpriced_service_tier_keeps_full_hold(budget, tier):
    repo, _ = budget
    reservation = repo.reserve("unknown-tier", purpose="extract")
    assert repo.settle(reservation, {**observed_standard_usage(), "serviceTier": tier}) is False
    assert repo.snapshot()["charged_micro_usd"] == RESERVATION_MICRO_USD
    assert (
        repo.table.get_item(Key=repo._attempt_key(reservation.month, reservation.attempt_id))["Item"]["status"]
        == "RESERVED"
    )


@pytest.mark.parametrize(
    "patch_data",
    [
        {"cachedContentTokenCount": 1},
        {"cachedContentTokenCount": False},
        {"cachedContentTokenCount": None},
        {"toolUsePromptTokenCount": 1},
        {"toolUsePromptTokenCount": "0"},
        {"toolUsePromptTokenCount": 0.0},
        {"toolUsePromptTokenCount": -1},
        {"cacheTokensDetails": [{"modality": "TEXT", "tokenCount": 0}]},
        {"toolUsePromptTokensDetails": [{"modality": "TEXT", "tokenCount": 0}]},
        {"cacheTokensDetails": None},
        {"toolUsePromptTokensDetails": {}},
        {"promptTokensDetails": [{"modality": "TEXT"}]},
        {"promptTokensDetails": [{"modality": "TEXT", "tokenCount": 402}]},
        {"promptTokensDetails": [{"modality": "TEXT", "tokenCount": True}]},
        {"promptTokensDetails": [{"modality": "TEXT", "tokenCount": -1}]},
        {"candidatesTokensDetails": [{"modality": "AUDIO", "tokenCount": 11}]},
        {"candidatesTokensDetails": [{"modality": "IMAGE", "tokenCount": 11}]},
        {"candidatesTokensDetails": [{"modality": "TEXT", "tokenCount": "11"}]},
        {"candidatesTokensDetails": [{"modality": "TEXT", "tokenCount": 12}]},
        {"candidatesTokensDetails": None},
        {"totalTokenCount": 413},
        {"thoughtsTokenCount": 1},
    ],
)
def test_real_shape_invalid_counts_or_modalities_cannot_release_hold(budget, patch_data):
    repo, _ = budget
    reservation = repo.reserve("invalid-usage-detail", purpose="extract")
    assert repo.settle(reservation, {**observed_standard_usage(), **patch_data}) is False
    assert repo.snapshot()["charged_micro_usd"] == RESERVATION_MICRO_USD


def test_standard_text_details_and_explicit_integer_zeros_preserve_thinking_cost(budget):
    repo, _ = budget
    reservation = repo.reserve("complete-text-detail", purpose="answer")
    data = {
        **observed_standard_usage(),
        "totalTokenCount": 419,
        "thoughtsTokenCount": 5,
        "cachedContentTokenCount": 0,
        "toolUsePromptTokenCount": 0,
        "cacheTokensDetails": [],
        "toolUsePromptTokensDetails": [],
        "candidatesTokensDetails": [{"modality": "TEXT", "tokenCount": 11}],
    }
    assert repo.settle(reservation, data)
    assert repo.snapshot()["charged_micro_usd"] == cost_micro_usd(403, 16)


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
        {**usage(), "promptTokensDetails": ["TEXT"]},
        {**usage(), "promptTokensDetails": None},
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
    from services.memory_v2._cost_state import CostState

    CostState(repo, clock=lambda: now[0]).record_measurement(
        repo.month(),
        inventory_version="test-inventory",
        verified=True,
        estimate=0,
        covered_until=int(now[0]),
        reason="SYNTHETIC_COMPLETE_MEASUREMENT",
    )
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


def test_contract_pause_survives_month_rollover(budget):
    repo, now = budget
    reservation = repo.reserve("future-contract", purpose="extract")
    with pytest.raises(MemoryBudgetAccountingError):
        repo.settle(reservation, usage(inputs=2_000_000, candidates=200_000))
    now[0] = datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp()
    with pytest.raises(MemoryBudgetPaused) as error:
        repo.reserve("new-month-contract", purpose="extract")
    assert error.value.retry_after == datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp()
    assert not repo.snapshot()


def test_readonly_preflight_does_not_reserve_and_detects_pause(budget):
    repo, _ = budget
    assert repo.check_available() is None
    assert not repo.snapshot()
    repo.table.put_item(Item={"pk": "MEMORY_BUDGET#CONTROL", "sk": "MODEL", "paused": True})
    with pytest.raises(MemoryBudgetPaused):
        repo.check_available()
    assert not repo.snapshot()
