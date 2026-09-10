"""Actual factory hooks/outer-finally composition with native Moto data requests."""

import json
from types import SimpleNamespace

import boto3
import pytest
from moto import mock_aws
from services.memory_v2 import cost_runtime
from services.memory_v2.cost_meter import InvocationCostMeter
from services.memory_v2.repository import MemoryRepository
from services.repositories import _common, sqs


@pytest.fixture
def wired(monkeypatch):
    with mock_aws():
        db = boto3.resource("dynamodb", region_name="eu-central-1")
        for name, keys in (
            ("zerde-serverless-memory-v2-prod", ["pk", "sk"]),
            ("zerde-serverless-bot-stats-prod", ["stat_key"]),
        ):
            db.create_table(
                TableName=name,
                KeySchema=[
                    {"AttributeName": key, "KeyType": "HASH" if index == 0 else "RANGE"}
                    for index, key in enumerate(keys)
                ],
                AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"} for key in keys],
                BillingMode="PAY_PER_REQUEST",
            )
        monkeypatch.setattr(_common, "_dynamodb_resource", db)
        monkeypatch.setattr(sqs, "_SQS_CLIENT", boto3.client("sqs", region_name="eu-central-1"))
        monkeypatch.setenv("ENVIRONMENT", "prod")
        monkeypatch.setenv("STATS_TABLE_NAME", "zerde-serverless-bot-stats-prod")
        monkeypatch.setenv("MEMORY_COST_INSTRUMENTATION_SCHEMA", "1")
        monkeypatch.setenv(
            "MEMORY_COST_INVENTORY",
            json.dumps(
                {
                    "schema": 1,
                    "region": "eu-central-1",
                    "account_id": "123456789012",
                    "metering_started_at": 1789000000,
                    "alarm_count": 10,
                }
            ),
        )
        markers = []
        monkeypatch.setattr(
            cost_runtime,
            "InvocationCostMeter",
            lambda context, spec: InvocationCostMeter(context, spec, emit=markers.append),
        )
        yield db, markers


def test_untouched_invocation_is_excluded_then_real_repo_touch_and_shared_write_are_counted(wired):
    db, markers = wired

    @cost_runtime.metered()
    def handler(event, context):
        if event:
            MemoryRepository("zerde-serverless-memory-v2-prod").get_control(-100123)
            db.Table("zerde-serverless-bot-stats-prod").put_item(Item={"stat_key": "synthetic", "count": 1})

    handler({}, SimpleNamespace(aws_request_id="request-zero-123"))
    assert not markers
    handler({"read": True}, SimpleNamespace(aws_request_id="request-one-123"))
    assert [row["cost_event"] for row in markers] == ["MemoryV2CostStart", "MemoryV2Cost"]
    assert markers[-1]["complete"] == 1 and markers[-1]["shared_stats_wru"] > 0
    assert "synthetic" not in json.dumps(markers) and "-100123" not in json.dumps(markers)


def test_finally_preserves_business_failure_and_warm_invocation_identity(wired):
    _, markers = wired

    @cost_runtime.metered(touch_first=True)
    def handler(event, context):
        if event:
            raise RuntimeError("synthetic business failure")

    with pytest.raises(RuntimeError, match="business failure"):
        handler(True, SimpleNamespace(aws_request_id="request-first-123"))
    handler(False, SimpleNamespace(aws_request_id="request-second-123"))
    finals = [row for row in markers if row["cost_event"] == "MemoryV2Cost"]
    assert [row["request_id"] for row in finals] == ["request-first-123", "request-second-123"]
    assert all(row["complete"] == 1 for row in finals)
    assert cost_runtime._CURRENT.get() is None


def test_bad_inventory_is_incomplete_and_cannot_disrupt_plain_business(wired, monkeypatch):
    _, markers = wired
    monkeypatch.setenv("MEMORY_COST_INVENTORY", "invalid")

    @cost_runtime.metered(touch_first=True)
    def handler(event, context):
        return "ordinary explicit QA can still run"

    assert handler({}, SimpleNamespace(aws_request_id="request-invalid-123"))
    assert markers[-1]["complete"] == 0


def test_monitor_rejects_dev_and_extra_task_fields_before_any_client(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    with pytest.raises(ValueError):
        cost_runtime.run_monitor(cost_runtime.MONITOR_EVENT)
    monkeypatch.setenv("ENVIRONMENT", "prod")
    with pytest.raises(ValueError):
        cost_runtime.run_monitor({**cost_runtime.MONITOR_EVENT, "untrusted": True})


@pytest.mark.parametrize("in_thread", [False, True])
def test_async_first_touch_preserves_outer_result_final_and_later_sync_wire(wired, in_thread):
    import asyncio

    db, markers = wired

    @cost_runtime.metered()
    def handler(event, context):
        async def first():
            repo = MemoryRepository("zerde-serverless-memory-v2-prod")
            if in_thread:
                await asyncio.to_thread(repo.get_control, -100123)
            else:
                repo.get_control(-100123)

        asyncio.run(first())
        # The invocation owner remains active in the parent after asyncio.run exits.
        db.Table("zerde-serverless-bot-stats-prod").put_item(Item={"stat_key": "after-async", "count": 1})
        return "preserved business result"

    assert handler({}, SimpleNamespace(aws_request_id="request-async-123")) == "preserved business result"
    assert len(markers) == 2 and markers[-1]["complete"] == 1
    assert markers[-1]["shared_stats_wru"] > 0


def test_async_failure_after_first_touch_keeps_original_exception_and_final(wired):
    import asyncio

    _, markers = wired

    @cost_runtime.metered()
    def handler(event, context):
        async def work():
            MemoryRepository("zerde-serverless-memory-v2-prod").get_control(-100123)
            raise LookupError("domain failure")

        asyncio.run(work())

    with pytest.raises(LookupError, match="domain failure"):
        handler({}, SimpleNamespace(aws_request_id="request-async-failure-123"))
    assert len(markers) == 2 and markers[-1]["complete"] == 1
