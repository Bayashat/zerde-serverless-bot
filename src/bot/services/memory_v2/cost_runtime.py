"""One Lambda invocation meter and the existing Bot's strict monitor entrypoint."""

import os
import threading
from contextvars import ContextVar
from functools import wraps

from ._cost_catalog import REGION, UnverifiedCost, parse_inventory
from .cost_meter import CostInventory as MeterInventory
from .cost_meter import InvocationCostMeter, register_client

_CURRENT = ContextVar("memory_cost_invocation", default=None)
MONITOR_EVENT = {"schema": 2, "task_type": "MONITOR_MEMORY_V2_COST"}


class _Invocation:
    def __init__(self, context):
        self.started, self.lock = False, threading.RLock()
        environment = os.environ.get("ENVIRONMENT", "")
        try:
            inventory = parse_inventory(os.environ.get("MEMORY_COST_INVENTORY", ""))
            queue_root = f"https://sqs.{REGION}.amazonaws.com/{inventory.account_id}/zerde-serverless-"
            stats = f"zerde-serverless-bot-stats-{environment}"
            excluded = {row["name"] for row in inventory.tables}
            excluded.update(
                f"zerde-serverless-{kind}-{env}" for kind in ("bot-memory", "quiz") for env in ("dev", "prod")
            )
            queues = {row["url"] for row in inventory.queues}
            queues.update(
                queue_root + f"vector-memory-tasks-{kind}{env}"
                for env in ("dev", "prod")
                for kind in ("queue-", "dlq-")
            )
            spec = MeterInventory(
                shared_stats_table=stats,
                shared_main_queue_url=queue_root + f"timeout-tasks-queue-{environment}",
                excluded_tables=frozenset(excluded),
                excluded_queue_urls=frozenset(queues),
                version=inventory.version,
                factory_coverage_verified=(
                    environment in {"dev", "prod"}
                    and os.environ.get("STATS_TABLE_NAME") == stats
                    and os.environ.get("MEMORY_COST_INSTRUMENTATION_SCHEMA") == "1"
                ),
                shared_stats_index_count=0,
                shared_stats_replica_count=0,
            )
        except UnverifiedCost:
            spec = MeterInventory("", "", frozenset(), frozenset(), "")
        self.meter = InvocationCostMeter(context, spec)

    def touch(self):
        with self.lock:
            if self.started:
                return
            self.started = True
            self.meter.touch()
            # Installation makes no data request, and completes before the first
            # metered SDK call. The scope was inherited from the outer invocation.
            from services.repositories._common import get_dynamodb
            from services.repositories.sqs import _get_sqs_client

            register_client(get_dynamodb().meta.client)
            register_client(_get_sqs_client())

    def finish(self):
        self.meter.finish()


def touch():
    owner = _CURRENT.get()
    if owner is not None:
        owner.touch()


def metered(*, touch_first=False):
    def decorate(handler):
        @wraps(handler)
        def run(event, context):
            # Unconfigured local/legacy entrypoints retain their existing behavior.
            if not os.environ.get("MEMORY_COST_INVENTORY"):
                return handler(event, context)
            owner = _Invocation(context)
            token = _CURRENT.set(owner)
            try:
                with owner.meter.bind_invocation():
                    if touch_first:
                        owner.touch()
                    return handler(event, context)
            finally:
                try:
                    owner.finish()
                finally:
                    _CURRENT.reset(token)

        return run

    return decorate


def run_monitor(event):
    if event != MONITOR_EVENT or os.environ.get("ENVIRONMENT") != "prod":
        raise ValueError("Only the production monitor schedule is supported")
    touch()
    import boto3
    from botocore.config import Config
    from services.memory_budget import MemoryBudgetRepository

    from .cost_monitor import MemoryCostMonitor, SDKCostTelemetry

    inventory = parse_inventory(os.environ.get("MEMORY_COST_INVENTORY", ""))
    config = Config(connect_timeout=2, read_timeout=5, retries={"total_max_attempts": 1})

    def client(service):
        value = boto3.client(service, region_name=REGION, config=config)
        if service in {"dynamodb", "sqs"}:
            register_client(value)
        return value

    telemetry = SDKCostTelemetry(
        inventory,
        cloudwatch=client("cloudwatch"),
        logs=client("logs"),
        dynamodb=client("dynamodb"),
        sqs=client("sqs"),
        lambda_client=client("lambda"),
    )
    budget = MemoryBudgetRepository(os.environ["MEMORY_BUDGET_TABLE_NAME"], inventory_version=inventory.version)
    return MemoryCostMonitor(
        budget, inventory, telemetry, sns=client("sns"), topic_arn=os.environ["OPERATIONS_TOPIC_ARN"]
    ).run()
