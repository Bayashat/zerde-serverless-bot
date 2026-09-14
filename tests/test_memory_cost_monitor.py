"""Cost guards use real Resource transactions; telemetry and SNS are always fake."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from services.memory_budget import RESERVATION_MICRO_USD, MemoryBudgetPaused
from services.memory_v2._cost_catalog import (
    CostInventory,
    UnverifiedCost,
    metric_totals,
    micro,
    parse_inventory,
)
from services.memory_v2._cost_state import CostState, CostStateConflict
from services.memory_v2.cost_monitor import MemoryCostMonitor, SDKCostTelemetry

from tests import test_memory_budget

budget = test_memory_budget.budget


def compact(inv):
    return json.dumps(
        {key: inv.value[key] for key in ("schema", "region", "metering_started_at", "alarm_count")}
        | {"account_id": inv.account_id},
        separators=(",", ":"),
    )


def inventory(start):
    return CostInventory(
        {
            "schema": 1,
            "region": "eu-central-1",
            "metering_started_at": start,
            "alarm_count": 10,
            "functions": [
                {
                    "name": f"zerde-serverless-{kind}-{env}",
                    "log_group": f"/aws/lambda/zerde-serverless-{kind}-{env}",
                    "kind": "worker" if kind == "memory-v2-worker" else "shared_bot",
                }
                for env in ("dev", "prod")
                for kind in ("memory-v2-worker", "bot")
            ],
            "tables": [
                {"name": f"zerde-serverless-memory-v2-{env}", "indexes": ["work-due"], "pitr": env == "prod"}
                for env in ("dev", "prod")
            ],
            "queues": [
                {
                    "name": f"zerde-serverless-memory-v2-{kind}-{env}",
                    "url": "https://sqs.eu-central-1.amazonaws.com/123456789012/"
                    f"zerde-serverless-memory-v2-{kind}-{env}",
                }
                for env in ("dev", "prod")
                for kind in ("queue", "dlq")
            ],
        }
    )


def write_measurement(repo, now, *, amount=0, verified=True):
    state = CostState(repo, clock=lambda: now[0])
    return state.record_measurement(
        repo.month(),
        inventory_version=repo.inventory_version,
        verified=verified,
        estimate=amount,
        covered_until=int(now[0]),
        reason="SYNTHETIC",
    )


@pytest.mark.parametrize(
    "mutation", ["missing", "stale", "inventory", "price", "incomplete", "negative", "bad_amount", "no_coverage"]
)
def test_missing_or_stale_measurement_never_reserves_provider_budget(budget, mutation):
    repo, now = budget
    key = repo._key(repo.month(), "AWS")
    row = repo.table.get_item(Key=key)["Item"]
    if mutation == "missing":
        repo.table.delete_item(Key=key)
    else:
        changes = {
            "stale": {"valid_until": int(now[0])},
            "inventory": {"inventory_version": "other"},
            "price": {"price_version": "unpriced"},
            "incomplete": {"measurement_state": "UNVERIFIED"},
            "negative": {"estimate_micro_usd": -1},
            "bad_amount": {"estimate_micro_usd": "invalid"},
            "no_coverage": {"covered_until": int(now[0]) - 10801},
        }
        repo.table.put_item(Item={**row, **changes[mutation]})
    for operation in (repo.check_available, lambda: repo.reserve("fresh", purpose="extract")):
        with pytest.raises(MemoryBudgetPaused):
            operation()
    assert repo.snapshot() == {}


def test_aws_pause_racing_model_reserve_cannot_escape_transaction(budget):
    repo, now = budget
    transaction = repo.table.meta.client.transact_write_items
    fired = False

    def race(**kwargs):
        nonlocal fired
        if not fired:
            fired = True
            write_measurement(repo, now, amount=2_700_000)
        return transaction(**kwargs)

    with patch.object(repo.table.meta.client, "transact_write_items", side_effect=race):
        with pytest.raises(MemoryBudgetPaused):
            repo.reserve("raced", purpose="answer")
    assert not repo.snapshot()


def test_model_ninety_percent_does_not_introduce_a_new_model_cap(budget):
    repo, now = budget
    repo.table.put_item(Item={**repo._key(repo.month(), "MODEL"), "charged_micro_usd": 6_300_000})
    before = repo.snapshot()
    state = CostState(repo, clock=lambda: now[0])
    state.observe_model(repo.month())
    assert repo.snapshot() == before
    assert state.read(repo.month(), "NOTICE#MODEL")["event"]["status"] == "warning"
    repo.reserve("ninety-still-has-headroom", purpose="answer")
    assert repo.snapshot()["charged_micro_usd"] == 6_300_000 + RESERVATION_MICRO_USD


def test_aws_threshold_is_sticky_but_new_month_needs_fresh_evidence(budget):
    repo, now = budget
    write_measurement(repo, now, amount=2_700_000)
    write_measurement(repo, now, amount=0)
    with pytest.raises(MemoryBudgetPaused):
        repo.reserve("old-month", purpose="extract")
    now[0] = datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp()
    with pytest.raises(MemoryBudgetPaused):
        repo.reserve("new-month", purpose="extract")
    write_measurement(repo, now)
    repo.reserve("new-month", purpose="extract")


def test_lost_sns_ack_keeps_identical_outbox_and_cannot_rollback_pause(budget):
    repo, now = budget
    state = CostState(repo, clock=lambda: now[0])
    write_measurement(repo, now, amount=2_700_000)
    sns = Mock()
    sns.publish.side_effect = TimeoutError("synthetic unknown SNS")
    with pytest.raises(TimeoutError):
        state.dispatch_notices(sns=sns, topic_arn="synthetic-topic")
    first = json.loads(sns.publish.call_args.kwargs["Message"])
    now[0] += 60
    sns.publish.side_effect = None
    sns.publish.return_value = {"MessageId": "fake-confirmation"}
    assert state.dispatch_notices(sns=sns, topic_arn="synthetic-topic") == 1
    assert json.loads(sns.publish.call_args.kwargs["Message"]) == first
    assert state.read(repo.month(), "AWS")["paused"] is True
    assert state.dispatch_notices(sns=sns, topic_arn="synthetic-topic") == 0


def test_pending_warning_is_replaced_by_highest_atomic_transition(budget):
    repo, now = budget
    state = CostState(repo, clock=lambda: now[0])
    write_measurement(repo, now, amount=2_400_000)
    now[0] += 1
    write_measurement(repo, now, amount=3_000_000)
    sns = Mock(publish=Mock(return_value={"MessageId": "confirmed"}))
    state.dispatch_notices(sns=sns, topic_arn="synthetic")
    event = json.loads(sns.publish.call_args.kwargs["Message"])
    assert event["threshold_percent"] == 100 and event["status"] == "paused"
    assert sns.publish.call_count == 1


def test_long_shutdown_expires_pending_notice_without_refreshing_observation(budget):
    repo, now = budget
    state = CostState(repo, clock=lambda: now[0])
    month = repo.month()
    write_measurement(repo, now, amount=2_400_000)
    original = state.read(month, "NOTICE#AWS")["event"]
    now[0] += 70 * 86400
    sns = Mock()
    state.dispatch_notices(sns=sns, topic_arn="synthetic")
    sns.publish.assert_not_called()
    assert state.read(month, "NOTICE#AWS")["state"] == "EXPIRED"
    assert state.read(month, "NOTICE#AWS")["event"] == original


def test_scan_unknown_is_reserved_once_and_actual_overrun_disables_estimate(budget):
    repo, now = budget
    state = CostState(repo, clock=lambda: now[0])
    key = state.reserve_scan(repo.month(), "query-attempt", 394)
    with pytest.raises(CostStateConflict):
        state.reserve_scan(repo.month(), "query-attempt", 394)
    assert state.read(repo.month(), "MONITOR")["scan_micro_usd"] == 394
    state.settle_scan(repo.month(), key, 1000)
    state.settle_scan(repo.month(), key, 1000)
    row = write_measurement(repo, now, verified=True)
    assert row["estimate_micro_usd"] == 1000
    assert row["measurement_state"] == "UNVERIFIED"


def metric_page(**changes):
    return {"MetricDataResults": [{"Id": "m0", "StatusCode": "Complete", "Timestamps": [], "Values": [], **changes}]}


def test_complete_empty_series_differs_from_missing_or_partial():
    assert metric_totals([metric_page()], {"m0"}) == {"m0": 0}
    for pages in (
        [{}],
        [metric_page(StatusCode="PartialData")],
        [metric_page(Id="unknown")],
        [metric_page(Messages=[{}])],
    ):
        with pytest.raises(UnverifiedCost):
            metric_totals(pages, {"m0"})


def fake_clients(inv):
    start = inv.value["metering_started_at"]
    tables = {row["name"]: row for row in inv.tables}
    db = Mock()
    db.describe_table.side_effect = lambda TableName: {
        "Table": {
            "TableName": TableName,
            "TableArn": f"arn:aws:dynamodb:eu-central-1:123456789012:table/{TableName}",
            "TableStatus": "ACTIVE",
            "BillingModeSummary": {"BillingMode": "PAY_PER_REQUEST"},
            "TableSizeBytes": 0,
            "CreationDateTime": datetime.fromtimestamp(start, timezone.utc),
            "GlobalSecondaryIndexes": [{"IndexName": "work-due", "IndexStatus": "ACTIVE", "IndexSizeBytes": 0}],
        }
    }
    db.describe_continuous_backups.side_effect = lambda TableName: {
        "ContinuousBackupsDescription": {
            "PointInTimeRecoveryDescription": {
                "PointInTimeRecoveryStatus": "ENABLED" if tables[TableName]["pitr"] else "DISABLED"
            }
        }
    }
    fn = Mock()
    fn.list_provisioned_concurrency_configs.return_value = {}
    fn.get_function_configuration.side_effect = lambda FunctionName: {
        "FunctionName": FunctionName,
        "FunctionArn": f"arn:aws:lambda:eu-central-1:123456789012:function:{FunctionName}",
        "State": "Active",
        "Architectures": ["arm64"],
        "Timeout": 120,
        "Environment": {
            "Variables": {"MEMORY_COST_INSTRUMENTATION_SCHEMA": "1", "MEMORY_COST_INVENTORY": compact(inv)}
        },
    }
    logs = Mock()
    logs.describe_log_groups.side_effect = lambda logGroupNamePrefix: {
        "logGroups": [
            {
                "logGroupName": logGroupNamePrefix,
                "logGroupArn": f"arn:aws:logs:eu-central-1:123456789012:log-group:{logGroupNamePrefix}",
                "creationTime": start * 1000,
                "storedBytes": 0,
                "retentionInDays": 7,
            }
        ]
    }
    logs.start_query.return_value = {"queryId": "fake-query"}
    logs.get_query_results.return_value = {
        "status": "Complete",
        "results": [],
        "statistics": {"bytesScanned": 0, "recordsMatched": 0},
    }
    sqs = Mock()
    sqs.get_queue_attributes.side_effect = lambda QueueUrl, **kwargs: {
        "Attributes": {
            "QueueArn": "arn:aws:sqs:eu-central-1:123456789012:" + QueueUrl.rsplit("/", 1)[-1],
            "CreatedTimestamp": str(start),
            "MaximumMessageSize": "1048576",
        }
    }
    cw = Mock()
    cw.get_metric_data.side_effect = lambda **kwargs: {
        "MetricDataResults": [
            {"Id": query["Id"], "StatusCode": "Complete", "Timestamps": [], "Values": []}
            for query in kwargs["MetricDataQueries"]
        ]
    }
    for client in (logs, db, sqs, fn, cw):
        client.meta.region_name = "eu-central-1"
    return SimpleNamespace(logs=logs, dynamodb=db, sqs=sqs, lambda_client=fn, cloudwatch=cw)


def monitor(budget):
    repo, now = budget
    inv = inventory(int(now[0]))
    now[0] += 3600
    repo.inventory_version = inv.version
    clients = fake_clients(inv)
    telemetry = SDKCostTelemetry(inv, **vars(clients), clock=lambda: now[0])
    service = MemoryCostMonitor(repo, inv, telemetry, sns=Mock(), topic_arn="synthetic", clock=lambda: now[0])
    return service, clients, now


def test_real_owner_accepts_new_idle_resource_measurements_without_inventing_invoice_zero(budget):
    service, clients, now = monitor(budget)
    result = service.run()
    assert result["measurement_state"] == "ESTIMATE_VERIFIED"
    assert (
        1_000_000 < result["estimate_micro_usd"] < 2_400_000
    )  # alarms + monitoring + uncertainty, never Free Tier zero
    service.state.budget.reserve("after-real-observation", purpose="extract")
    assert clients.logs.start_query.call_count == 2
    for call in clients.logs.start_query.call_args_list:
        kwargs = call.kwargs
        assert kwargs["endTime"] - kwargs["startTime"] <= 24 * 3600
        assert "@message" not in kwargs["queryString"]


def test_partial_metrics_invalidates_old_permit_and_raises_for_alarm(budget):
    service, clients, _ = monitor(budget)
    clients.cloudwatch.get_metric_data.return_value = {"MetricDataResults": []}
    clients.cloudwatch.get_metric_data.side_effect = None
    with pytest.raises(UnverifiedCost):
        service.run()
    with pytest.raises(MemoryBudgetPaused):
        service.state.budget.reserve("no-meter", purpose="extract")
    clients.logs.start_query.assert_not_called()


def test_query_deadline_cancels_and_retains_unknown_scan_liability(budget):
    service, clients, now = monitor(budget)
    telemetry = service.telemetry
    metadata = telemetry.resources()
    start, end = service._blocks(int(now[0]))[0]
    metrics = telemetry.metrics(start, end)
    clients.logs.get_query_results.return_value = {"status": "Running"}
    tick = [0]

    def sleep(seconds):
        tick[0] += seconds

    with pytest.raises(UnverifiedCost):
        telemetry.reports(
            start,
            end,
            state=service.state,
            month=service.state.budget.month(),
            metadata=metadata,
            metrics=metrics,
            monotonic=lambda: tick[0],
            sleep=sleep,
        )
    assert tick[0] == 45
    clients.logs.stop_query.assert_called_once_with(queryId="fake-query")
    assert service.state.read(service.state.budget.month(), "MONITOR")["scan_micro_usd"] > 0


def test_catalog_prices_keep_gross_non_free_usage():
    assert micro(1_000_000, "wru") == 762_500
    assert micro(1_000_000, "rru") == 152_500
    assert micro(5, "standard_alarm_month") == 500_000
    assert micro(Decimal("0.5"), "lambda_gb_second") == 7


@pytest.mark.parametrize("value", ["0", True, Decimal("0.5"), Decimal("NaN")])
def test_corrupt_numeric_permit_does_not_coerce_to_valid_money(budget, value):
    repo, _ = budget
    key = repo._key(repo.month(), "AWS")
    row = repo.table.get_item(Key=key)["Item"]
    if isinstance(value, Decimal) and value.is_nan():
        # DynamoDB itself rejects NaN; exercise a corrupt read without a fake transaction.
        original = repo.table.get_item

        def read(**kwargs):
            return {"Item": {**row, "estimate_micro_usd": value}} if kwargs["Key"] == key else original(**kwargs)

        with patch.object(repo.table, "get_item", side_effect=read), pytest.raises(MemoryBudgetPaused):
            repo.reserve("bad-money", purpose="extract")
    else:
        repo.table.put_item(Item={**row, "estimate_micro_usd": value})
        with pytest.raises(MemoryBudgetPaused):
            repo.reserve("bad-money", purpose="extract")
    assert not repo.snapshot()


def test_query_reservation_invalidates_previous_permit_before_external_scan(budget):
    repo, now = budget
    state = CostState(repo, clock=lambda: now[0])
    state.reserve_scan(repo.month(), "one-query", 394)
    with pytest.raises(MemoryBudgetPaused):
        repo.reserve("cannot-use-yesterdays-permit", purpose="extract")
    assert state.read(repo.month(), "AWS")["reason"] == "REPORT_QUERY_IN_PROGRESS"


@pytest.mark.parametrize("control_owner", ["global", "month"])
def test_model_notification_is_fenced_against_accounting_pause_races(budget, control_owner):
    repo, now = budget
    repo.table.put_item(Item={**repo._key(repo.month(), "MODEL"), "charged_micro_usd": 6_300_000})
    state = CostState(repo, clock=lambda: now[0])
    original = repo.table.meta.client.transact_write_items

    def race(**kwargs):
        key = (
            {"pk": "MEMORY_BUDGET#CONTROL", "sk": "MODEL"}
            if control_owner == "global"
            else repo._key(repo.month(), "MODEL")
        )
        repo.table.update_item(
            Key=key, UpdateExpression="SET paused = :true", ExpressionAttributeValues={":true": True}
        )
        return original(**kwargs)

    with (
        patch.object(repo.table.meta.client, "transact_write_items", side_effect=race),
        pytest.raises(CostStateConflict),
    ):
        state.observe_model(repo.month())
    assert state.read(repo.month(), "NOTICE#MODEL") == {}
    state.observe_model(repo.month())
    assert state.read(repo.month(), "NOTICE#MODEL")["event"]["status"] == "paused"


@pytest.mark.parametrize("family", ["queues", "functions", "tables"])
def test_missing_idle_resource_is_not_a_complete_project_inventory(family):
    value = inventory(1_789_000_000).value
    value[family].pop(0)
    with pytest.raises(UnverifiedCost):
        CostInventory(value)


def test_complete_empty_logs_cannot_replace_expired_historical_reports(budget):
    service, clients, now = monitor(budget)
    now[0] += 8 * 86400
    with pytest.raises(UnverifiedCost):
        service.run()
    clients.logs.start_query.assert_not_called()
    assert service.state.read(service.state.budget.month(), "AWS")["measurement_state"] == "UNVERIFIED"


def test_history_catchup_requires_every_block_before_admission(budget):
    service, _, now = monitor(budget)
    now[0] += 13 * 3600
    repo = service.state.budget
    unknown_scan = service.state.reserve_scan(repo.month(), "prior-unknown-query", 394)
    result = service.run()
    assert result["measurement_state"] == "UNVERIFIED"
    assert result["reason"] == "HISTORICAL_COVERAGE_INCOMPLETE"
    assert result["covered_until"] == service._blocks(int(now[0]))[0][1]
    assert service.state.read(repo.month(), "AWS")["valid_until"] == int(now[0])
    assert service.state.read(repo.month(), "MONITOR")["scan_micro_usd"] == 394
    assert repo.table.get_item(Key=unknown_scan, ConsistentRead=True)["Item"]["state"] == "RESERVED"
    for operation in (
        repo.check_aws_available,
        repo.check_available,
        lambda: repo.reserve("partial-history", purpose="answer"),
    ):
        with pytest.raises(MemoryBudgetPaused):
            operation()
    assert service.run()["measurement_state"] == "ESTIMATE_VERIFIED"
    repo.reserve("complete-history", purpose="answer")


def test_exception_named_like_history_progress_is_still_a_failed_observation(budget):
    service, _, _ = monitor(budget)
    failure = type("HISTORICAL_COVERAGE_INCOMPLETE", (RuntimeError,), {})
    with patch.object(service.telemetry, "resources", side_effect=failure("synthetic")):
        with pytest.raises(UnverifiedCost):
            service.run()
    repo = service.state.budget
    assert service.state.read(repo.month(), "AWS")["reason"] == "HISTORICAL_COVERAGE_INCOMPLETE"
    with pytest.raises(MemoryBudgetPaused):
        repo.reserve("failed-observation", purpose="extract")


def test_late_cost_validation_failure_revokes_complete_coverage(budget):
    service, _, now = monitor(budget)
    now[0] += 13 * 3600
    repo = service.state.budget
    start, end = service._blocks(int(now[0]))[0]
    row = service.state.save_day(
        repo.month(),
        str(start),
        {
            "inventory_version": service.inventory.version,
            "covered_from": start,
            "covered_until": end,
            "observed_at": int(now[0]),
            "variable_micro_usd": 0,
            "write_units": 0,
        },
    )
    # Coverage is complete after the next block, but its persisted cost input
    # must still be validated before a fresh permit can be published.
    repo.table.put_item(Item={**row, "write_units": "not-a-priced-number"})
    with pytest.raises(UnverifiedCost):
        service.run()
    assert service.state.read(repo.month(), "AWS")["measurement_state"] == "UNVERIFIED"
    with pytest.raises(MemoryBudgetPaused):
        repo.reserve("invalid-cost-input", purpose="answer")


@pytest.mark.parametrize("boundary", ["save_day", "record_measurement", "observe_model"])
def test_history_progress_does_not_swallow_persistence_failures(budget, boundary):
    service, _, now = monitor(budget)
    now[0] += 13 * 3600
    expected = UnverifiedCost if boundary == "save_day" else TimeoutError
    with patch.object(service.state, boundary, side_effect=TimeoutError("synthetic persistence failure")):
        with pytest.raises(expected):
            service.run()
    with pytest.raises(MemoryBudgetPaused):
        service.state.budget.reserve("failed-persistence", purpose="extract")


def test_history_progress_waits_for_notice_ack_and_preserves_sticky_pause(budget):
    service, _, now = monitor(budget)
    now[0] += 13 * 3600
    repo = service.state.budget
    write_measurement(repo, now, amount=2_700_000)
    service.sns.publish.side_effect = TimeoutError("synthetic unknown SNS")
    with pytest.raises(TimeoutError):
        service.run()
    notice = service.state.read(repo.month(), "NOTICE#AWS")
    assert notice["state"] == "PENDING"
    first_event = notice["event"]
    service.sns.publish.side_effect = None
    service.sns.publish.return_value = {"MessageId": "confirmed"}
    # Keep another historical block outstanding while retrying the same notice.
    now[0] += 12 * 3600
    result = service.run()
    assert result["measurement_state"] == "UNVERIFIED"
    assert result["reason"] == "HISTORICAL_COVERAGE_INCOMPLETE"
    assert result["paused"] is True
    notice = service.state.read(repo.month(), "NOTICE#AWS")
    assert notice["state"] == "SENT" and notice["event"] == first_event
    with pytest.raises(MemoryBudgetPaused):
        repo.reserve("still-paused", purpose="answer")


def test_history_progress_does_not_mask_a_sticky_scan_overrun(budget):
    service, _, now = monitor(budget)
    now[0] += 13 * 3600
    repo = service.state.budget
    key = service.state.reserve_scan(repo.month(), "overrun-query", 394)
    service.state.settle_scan(repo.month(), key, 1000)
    with pytest.raises(UnverifiedCost):
        service.run()
    row = service.state.read(repo.month(), "AWS")
    assert row["measurement_state"] == "UNVERIFIED" and row["reason"] == "SCAN_BOUND_EXCEEDED"
    assert service.state.read(repo.month(), "MONITOR")["scan_micro_usd"] == 1000
    with pytest.raises(MemoryBudgetPaused):
        repo.reserve("scan-overrun", purpose="extract")


def test_metrics_reject_out_of_window_and_conflicting_pagination():
    stamp = datetime(2026, 9, 10, tzinfo=timezone.utc)
    page = metric_page(Timestamps=[stamp], Values=[1])
    with pytest.raises(UnverifiedCost):
        metric_totals([page], {"m0"}, start=int(stamp.timestamp()) + 1, end=int(stamp.timestamp()) + 301)
    with pytest.raises(UnverifiedCost):
        metric_totals([page, metric_page(Timestamps=[stamp], Values=[2])], {"m0"})
    assert metric_totals([page, page], {"m0"}) == {"m0": 1}


def test_runtime_inventory_json_computes_same_resolved_guard_version(budget, monkeypatch):
    repo, now = budget
    inv = inventory(int(now[0]))
    monkeypatch.setenv("MEMORY_COST_INVENTORY", compact(inv))
    actual = test_memory_budget.MemoryBudgetRepository(repo.table.name, clock=lambda: now[0])
    assert actual.inventory_version == inv.version
    monkeypatch.setenv("MEMORY_COST_INVENTORY", "invalid")
    assert not test_memory_budget.MemoryBudgetRepository(repo.table.name).inventory_version


def test_compact_env_expands_one_closed_catalog_and_rejects_full_or_unresolved_input():
    inv = inventory(1_789_000_000)
    assert len(compact(inv).encode()) < 160
    assert parse_inventory(compact(inv)).version == inv.version
    assert parse_inventory(compact(inv)).value == inv.value
    for raw in (
        json.dumps(inv.value),
        compact(inv).replace("123456789012", "${Token[AWS.AccountId]}"),
        compact(inv).replace('"schema":1', '"schema":1,"schema":1'),
    ):
        with pytest.raises(UnverifiedCost):
            parse_inventory(raw)


def test_telemetry_region_must_match_the_price_catalog(budget):
    _, now = budget
    inv = inventory(int(now[0]))
    clients = fake_clients(inv)
    clients.logs.meta.region_name = "us-east-1"
    with pytest.raises(UnverifiedCost):
        SDKCostTelemetry(inv, **vars(clients))


def test_aws_only_preflight_does_not_inherit_model_exhaustion(budget):
    repo, now = budget
    repo.table.put_item(Item={**repo._key(repo.month(), "MODEL"), "charged_micro_usd": 7_000_000})
    with pytest.raises(MemoryBudgetPaused):
        repo.check_available()
    repo.check_aws_available()
    write_measurement(repo, now, amount=2_700_000)
    with pytest.raises(MemoryBudgetPaused):
        repo.check_aws_available()


def test_monitor_uses_inventory_alarm_allowance_in_actual_recorded_estimate(budget):
    service, _, _ = monitor(budget)
    estimates = []
    original = service.inventory.value
    for count in (5, 10):
        service.inventory = CostInventory({**original, "alarm_count": count})
        with patch.object(service.telemetry, "resources", side_effect=UnverifiedCost("synthetic missing inventory")):
            with pytest.raises(UnverifiedCost):
                service.run()
        row = service.state.budget.table.get_item(Key=service.state.budget._key(service.state.budget.month(), "AWS"))[
            "Item"
        ]
        estimates.append(int(row["estimate_micro_usd"]))
    assert estimates[1] - estimates[0] == 500_000
    with pytest.raises(UnverifiedCost):
        parse_inventory(compact(CostInventory({**original, "alarm_count": 5})))
