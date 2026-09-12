"""Fixed Frankfurt gross price/telemetry contract; no Free Tier assumptions."""

import hashlib
import json
import re
from datetime import datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation

REGION = "eu-central-1"
GIB = 1024**3
BLOCK_SECONDS = 12 * 3600
HALO_SECONDS = 15 * 60
# USD per unit, from the public regional AWS Price List (retrieved 2026-09-11).
RATES = {
    "wru": Decimal("0.0000007625"),
    "rru": Decimal("0.0000001525"),
    "storage_gib_month": Decimal("0.306"),
    "pitr_gib_month": Decimal("0.2448"),
    "lambda_gb_second": Decimal("0.0000133334"),
    "lambda_request": Decimal("0.0000002"),
    "sqs_unit": Decimal("0.0000004"),
    "log_ingest_gib": Decimal("0.63"),
    "log_storage_gib_month": Decimal("0.0324"),
    "log_scan_gib": Decimal("0.0063"),
    "metric_query": Decimal("0.00001"),
    "standard_alarm_month": Decimal("0.1"),
    "sns_publish": Decimal("0.0000005"),
}


class UnverifiedCost(RuntimeError):
    """A measurement gap cannot authorize optional memory work."""


def number(value):
    if isinstance(value, bool):
        raise UnverifiedCost("Boolean usage is invalid")
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0:
            raise ValueError()
        return result
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise UnverifiedCost("Usage must be a finite nonnegative number") from exc


def micro(amount, rate):
    return int((number(amount) * RATES[rate] * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


class CostInventory:
    """A reviewed, explicit all-environment roster, supplied by the infra owner.

    metering_started_at is the authorized first V2 rollout epoch. It cannot be
    advanced to hide usage. Mid-month roster changes require a reviewed rebuild.
    """

    def __init__(self, value):
        required = {"schema", "region", "metering_started_at", "functions", "tables", "queues", "alarm_count"}
        if (
            not isinstance(value, dict)
            or set(value) != required
            or type(value["schema"]) is not int
            or value["schema"] != 1
            or value["region"] != REGION
        ):
            raise UnverifiedCost("Unknown cost inventory schema or unpriced region")
        if type(value["metering_started_at"]) is not int or value["metering_started_at"] <= 0:
            raise UnverifiedCost("A reviewed metering start is required")
        if type(value["alarm_count"]) is not int or value["alarm_count"] not in {5, 10}:
            raise UnverifiedCost("The reviewed incremental alarm allowance is required")
        self.value = json.loads(json.dumps(value))
        self.functions, self.tables, self.queues = (self.value[key] for key in ("functions", "tables", "queues"))
        fields = {
            "functions": {"name", "log_group", "kind"},
            "tables": {"name", "pitr", "indexes"},
            "queues": {"name", "url"},
        }
        for family in fields:
            rows = self.value[family]
            if not isinstance(rows, list) or not 1 <= len(rows) <= 8:
                raise UnverifiedCost("Inventory resource count is invalid")
            names = set()
            for row in rows:
                if set(row) != fields[family] or not re.fullmatch(r"zerde-serverless-[A-Za-z0-9_-]+", row["name"]):
                    raise UnverifiedCost("Unknown inventory resource")
                if row["name"] in names:
                    raise UnverifiedCost("Duplicate inventory resource")
                names.add(row["name"])
                if family == "functions" and (
                    row["kind"] not in {"worker", "shared_bot"} or row["log_group"] != "/aws/lambda/" + row["name"]
                ):
                    raise UnverifiedCost("Unknown function metering contract")
                if family == "tables" and (type(row["pitr"]) is not bool or row["indexes"] != ["work-due"]):
                    raise UnverifiedCost("Unpriced table/index configuration")
                if family == "queues" and not re.fullmatch(
                    rf"https://sqs\.{REGION}\.amazonaws\.com/[0-9]{{12}}/{re.escape(row['name'])}", row["url"]
                ):
                    raise UnverifiedCost("Queue URL does not match its registered name")
        # Closed roster: omitting an idle dev DLQ must not produce a 'complete'
        # estimate. New resource families require a priced schema migration.
        expected = {
            "functions": {
                f"zerde-serverless-{kind}-{env}" for env in ("dev", "prod") for kind in ("bot", "memory-v2-worker")
            },
            "tables": {f"zerde-serverless-memory-v2-{env}" for env in ("dev", "prod")},
            "queues": {
                f"zerde-serverless-memory-v2-{kind}-{env}" for env in ("dev", "prod") for kind in ("queue", "dlq")
            },
        }
        for family, names in expected.items():
            if {row["name"] for row in self.value[family]} != names:
                raise UnverifiedCost("Inventory must cover all project resources, including both DLQs")
        if any(("-memory-v2-worker-" in row["name"]) != (row["kind"] == "worker") for row in self.functions):
            raise UnverifiedCost("Function kind does not match its registered role")
        accounts = {row["url"].split("/")[3] for row in self.queues}
        if len(accounts) != 1:
            raise UnverifiedCost("Inventory must identify one project account")
        self.account_id = accounts.pop()
        canonical = json.dumps(self.value, sort_keys=True, separators=(",", ":"))
        self.version = hashlib.sha256(canonical.encode()).hexdigest()


def parse_inventory(raw):
    """Expand the only supported environment format without consuming 2 KiB env space.

    Hash the complete resolved inventory, never CloudFormation token text. Full
    documents remain available for explicit programmatic construction/tests only.
    """

    def unique(pairs):
        row = {}
        for key, value in pairs:
            if key in row:
                raise UnverifiedCost("Duplicate inventory declaration")
            row[key] = value
        return row

    if not isinstance(raw, str):
        raise UnverifiedCost("Cost inventory environment must be compact JSON")
    try:
        value = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, TypeError) as exc:
        raise UnverifiedCost("Invalid cost inventory JSON") from exc
    fields = {"schema", "region", "account_id", "metering_started_at", "alarm_count"}
    if not isinstance(value, dict) or set(value) != fields or not isinstance(value.get("account_id"), str):
        raise UnverifiedCost("Unknown compact inventory declaration")
    if value["alarm_count"] != 10:
        raise UnverifiedCost("Compact deployment must reserve both environments alarms")
    account = value["account_id"]
    if not re.fullmatch(r"[0-9]{12}", account):
        raise UnverifiedCost("An actual resolved project account is required")
    return CostInventory(
        {key: item for key, item in value.items() if key != "account_id"}
        | {
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
                    "url": f"https://sqs.{REGION}.amazonaws.com/{account}/zerde-serverless-memory-v2-{kind}-{env}",
                }
                for env in ("dev", "prod")
                for kind in ("queue", "dlq")
            ],
        }
    )


# Lambda Logs Insights discovers @memorySize in decimal bytes (official example
# divides it by 1,000,000 for configured MB). Lambda bills GB = configured MB/1024.
# Two stats stages return only per-log-group numerical aggregates, never request IDs.
# Keep intermediate aliases distinct: Logs Insights rejects redefining an
# ephemeral field in a later stats command, even for a further aggregation.
_REQUEST_STATS = """fields coalesce(request_id, @requestId) as rid
| filter @type in ["START", "REPORT"] or cost_event in ["MemoryV2CostStart", "MemoryV2Cost"]
| stats min(toMillis(@timestamp)) as req_started_ms,
    sum(if(@type = "START", 1, 0)) as req_platform_starts,
    count(@billedDuration) as req_reports,
    max(@billedDuration * @memorySize / 1000000 / 1024 / 1000) as req_gb_seconds,
    sum(memory_request) as req_starts, count(complete) as req_finals, sum(complete) as req_completed,
    count(cost_schema) as req_schema_count, sum(cost_schema) as req_schema_sum,
    min(cost_schema) as req_schema_min, max(cost_schema) as req_schema_max,
    count(shared_stats_rru) as req_rru_count, sum(shared_stats_rru) as req_rru,
    count(shared_stats_wru) as req_wru_count, sum(shared_stats_wru) as req_wru,
    count(shared_sqs_units) as req_sqs_count, sum(shared_sqs_units) as req_sqs,
    sum(elapsed_ms) as req_elapsed_ms
    by @log, rid
"""
_TOTAL_STATS = """| stats sum(if(
    ispresent(rid) and rid != "" and req_platform_starts = 1 and req_reports = 1
    and ispresent(req_gb_seconds) and req_gb_seconds >= 0
    and req_starts = 1 and req_finals = 1 and req_completed = 1
    and req_schema_count = 2 and req_schema_min = 1 and req_schema_max = 1
    and req_rru_count = 1 and req_rru >= 0 and req_wru_count = 1 and req_wru >= 0
    and req_sqs_count = 1 and req_sqs >= 0 and ispresent(req_elapsed_ms) and req_elapsed_ms >= 0,
    0, 1)) as invalid_records,
    sum(req_platform_starts) as platform_starts, sum(req_reports) as reports, count(req_gb_seconds) as billed_records,
    sum(req_gb_seconds) as gb_seconds, sum(req_starts) as starts,
    sum(req_finals) as finals, sum(req_completed) as completed,
    sum(req_schema_count) as schema_count, sum(req_schema_sum) as schema_sum,
    sum(req_rru_count) as rru_count, sum(req_rru) as rru,
    sum(req_wru_count) as wru_count, sum(req_wru) as wru,
    sum(req_sqs_count) as sqs_count, sum(req_sqs) as sqs, sum(req_elapsed_ms) as elapsed_ms by @log"""


def report_query(start, end, *, shared):
    if not 0 < end - start <= BLOCK_SECONDS:
        raise UnverifiedCost("Unbounded REPORT window")
    return (
        _REQUEST_STATS
        + f"| filter req_started_ms >= {start * 1000} and req_started_ms < {end * 1000}\n"
        + ("| filter req_starts > 0 or req_finals > 0\n" if shared else "")
        + _TOTAL_STATS
    )


def parse_reports(result, groups):
    if result.get("status") != "Complete" or result.get("nextToken"):
        raise UnverifiedCost("REPORT query did not finish completely")
    parsed = {}
    fields = {
        "invalid_records",
        "platform_starts",
        "reports",
        "billed_records",
        "gb_seconds",
        "starts",
        "finals",
        "completed",
        "schema_count",
        "schema_sum",
        "rru_count",
        "rru",
        "wru_count",
        "wru",
        "sqs_count",
        "sqs",
        "elapsed_ms",
    }
    for items in result.get("results", []):
        row = {entry["field"]: entry["value"] for entry in items}
        if len(row) != len(items) or set(row) != fields | {"@log"}:
            raise UnverifiedCost("Unexpected or missing aggregate fields")
        group = row.pop("@log").split(":", 1)[-1]
        if group not in groups or group in parsed:
            raise UnverifiedCost("REPORT group differs from inventory")
        values = {key: number(value) for key, value in row.items()}
        count = values["starts"]
        if (
            values["invalid_records"]
            or not count
            or any(
                values[key] != count
                for key in (
                    "platform_starts",
                    "reports",
                    "billed_records",
                    "finals",
                    "completed",
                    "rru_count",
                    "wru_count",
                    "sqs_count",
                )
            )
            or values["schema_count"] != 2 * count
            or values["schema_sum"] != 2 * count
        ):
            raise UnverifiedCost("START, FINAL or REPORT coverage is incomplete")
        parsed[group] = values
    return parsed


def metric_totals(pages, expected, *, start=None, end=None):
    """Complete empty series means no *reported* usage, not proof of a zero invoice."""
    found = {key: {} for key in expected}
    seen = set()
    for page in pages:
        if page.get("Messages"):
            raise UnverifiedCost("Metric query returned a warning")
        for result in page.get("MetricDataResults", []):
            key = result.get("Id")
            if key not in expected or result.get("StatusCode") != "Complete" or result.get("Messages"):
                raise UnverifiedCost("Missing, partial or unregistered metric")
            timestamps, values = result.get("Timestamps"), result.get("Values")
            if not isinstance(timestamps, list) or not isinstance(values, list) or len(timestamps) != len(values):
                raise UnverifiedCost("Metric points are incomplete")
            seen.add(key)
            for timestamp, value in zip(timestamps, values):
                if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
                    raise UnverifiedCost("Metric timestamp is not an aware UTC instant")
                second = int(timestamp.timestamp())
                if start is not None and (second < start or second >= end):
                    raise UnverifiedCost("Metric point is outside the requested window")
                value = number(value)
                if second in found[key] and found[key][second] != value:
                    raise UnverifiedCost("Inconsistent metric pagination")
                found[key][second] = value
    if seen != set(expected):
        raise UnverifiedCost("Required metric result is absent")
    return {key: sum(values.values(), Decimal(0)) for key, values in found.items()}
