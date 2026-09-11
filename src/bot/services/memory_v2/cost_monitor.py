"""Project-wide, conservative Memory V2 AWS estimate and durable budget notices.

Only the prod monitor runs this owner. SDK clients are injected by runtime wiring;
tests use fake telemetry plus real boto3/Moto persistence, never account APIs.
"""

from __future__ import annotations

import calendar
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from services.memory_v2._cost_catalog import (
    BLOCK_SECONDS,
    GIB,
    HALO_SECONDS,
    REGION,
    CostInventory,
    UnverifiedCost,
    metric_totals,
    micro,
    number,
    parse_inventory,
    parse_reports,
    report_query,
)
from services.memory_v2._cost_state import CostState, month_at

_LOG_QUERY_SECONDS = 45
_SCAN_CEILING_BYTES = 64 * 1024 * 1024
_UNCERTAINTY_MICRO_USD = 100_000
_SHARED_LOG_BYTES_PER_REQUEST = 64 * 1024


def _utc(second):
    return datetime.fromtimestamp(second, timezone.utc)


def _time(value):
    return int(value.timestamp()) if isinstance(value, datetime) else int(value)


class SDKCostTelemetry:
    """Read only the named resources and fixed numerical metrics/REPORT aggregates.

    Callers must provide SDK clients with short connect/read timeouts and one
    attempt. The elapsed-time checks bound polling/loop work, not OS DNS or CPU.
    Lambda's configured timeout remains the final execution bound.
    """

    def __init__(self, inventory, *, cloudwatch, logs, dynamodb, sqs, lambda_client, clock=time.time):
        self.inventory = inventory
        self.cloudwatch, self.logs, self.dynamodb, self.sqs, self.lambda_client = (
            cloudwatch,
            logs,
            dynamodb,
            sqs,
            lambda_client,
        )
        self.clock = clock
        self.api_units = 0
        if any(client.meta.region_name != REGION for client in (cloudwatch, logs, dynamodb, sqs, lambda_client)):
            raise UnverifiedCost("Telemetry clients must use the priced inventory region")

    def resources(self):
        """Verify existence/type; an absent resource is never silently treated as idle."""
        created, tables, groups, queues = [], {}, {}, {}
        for spec in self.inventory.tables:
            self.api_units += 2
            table = self.dynamodb.describe_table(TableName=spec["name"])["Table"]
            indexes = table.get("GlobalSecondaryIndexes", [])
            backup = self.dynamodb.describe_continuous_backups(TableName=spec["name"])
            pitr = backup["ContinuousBackupsDescription"]["PointInTimeRecoveryDescription"]["PointInTimeRecoveryStatus"]
            if (
                table.get("TableName") != spec["name"]
                or table.get("TableArn")
                != f"arn:aws:dynamodb:{REGION}:{self.inventory.account_id}:table/{spec['name']}"
                or table.get("TableStatus") != "ACTIVE"
                or table.get("BillingModeSummary", {}).get("BillingMode") != "PAY_PER_REQUEST"
                or table.get("TableClassSummary", {}).get("TableClass", "STANDARD") != "STANDARD"
                or {item["IndexName"] for item in indexes} != set(spec["indexes"])
                or any(item.get("IndexStatus") != "ACTIVE" for item in indexes)
                or bool(table.get("Replicas"))
                or bool(table.get("LocalSecondaryIndexes"))
                or table.get("StreamSpecification", {}).get("StreamEnabled", False)
                or table.get("SSEDescription", {}).get("SSEType") == "KMS"
                or pitr not in {"ENABLED", "DISABLED"}
                or (pitr == "ENABLED") != spec["pitr"]
            ):
                raise UnverifiedCost("Table billing configuration differs from inventory")
            created.append(_time(table["CreationDateTime"]))
            size = number(table["TableSizeBytes"]) + sum(number(item["IndexSizeBytes"]) for item in indexes)
            tables[spec["name"]] = {"bytes": size, "pitr": spec["pitr"]}
        for spec in self.inventory.functions:
            self.api_units += 3
            function = self.lambda_client.get_function_configuration(FunctionName=spec["name"])
            provisioned = self.lambda_client.list_provisioned_concurrency_configs(FunctionName=spec["name"], MaxItems=1)
            if (
                function.get("FunctionName") != spec["name"]
                or function.get("FunctionArn")
                != f"arn:aws:lambda:{REGION}:{self.inventory.account_id}:function:{spec['name']}"
                or function.get("State") != "Active"
                or function.get("Architectures") != ["arm64"]
                or not 0 < int(function["Timeout"]) <= 300
                or function.get("SnapStart", {}).get("ApplyOn", "None") != "None"
                or function.get("EphemeralStorage", {}).get("Size", 512) > 512
                or function.get("VpcConfig", {}).get("VpcId")
                or provisioned.get("ProvisionedConcurrencyConfigs")
                or provisioned.get("NextMarker")
                or function.get("LoggingConfig", {}).get("LogFormat", "Text") != "Text"
                or function.get("LoggingConfig", {}).get("LogGroup", spec["log_group"]) != spec["log_group"]
                or function.get("Environment", {}).get("Variables", {}).get("MEMORY_COST_INSTRUMENTATION_SCHEMA") != "1"
                or parse_inventory(
                    function.get("Environment", {}).get("Variables", {}).get("MEMORY_COST_INVENTORY", "")
                ).version
                != self.inventory.version
            ):
                raise UnverifiedCost("Function billing/runtime configuration is unsupported")
            found = self.logs.describe_log_groups(logGroupNamePrefix=spec["log_group"])
            exact = [group for group in found.get("logGroups", []) if group["logGroupName"] == spec["log_group"]]
            if len(exact) != 1 or found.get("nextToken"):
                raise UnverifiedCost("Log group existence is ambiguous")
            group = exact[0]
            expected_log_arn = f"arn:aws:logs:{REGION}:{self.inventory.account_id}:log-group:{spec['log_group']}"
            if group.get("logGroupArn", group.get("arn", "").removesuffix(":*")) != expected_log_arn:
                raise UnverifiedCost("Log group account differs from inventory")
            if group.get("logGroupClass", "STANDARD") != "STANDARD" or not 1 <= group.get("retentionInDays", 0) <= 30:
                raise UnverifiedCost("Unsupported log retention or class")
            groups[spec["log_group"]] = {
                "created": int(group["creationTime"]) // 1000,
                "stored_bytes": number(group["storedBytes"]),
                "retention_days": group["retentionInDays"],
            }
            if spec["kind"] == "worker":
                created.append(groups[spec["log_group"]]["created"])
        for spec in self.inventory.queues:
            self.api_units += 1
            # FifoQueue is FIFO-only: requesting it for a standard queue can
            # raise InvalidAttributeName. The closed inventory and exact ARN
            # below bind the response to a name without the required .fifo suffix.
            response = self.sqs.get_queue_attributes(
                QueueUrl=spec["url"],
                AttributeNames=["QueueArn", "CreatedTimestamp", "MaximumMessageSize", "KmsMasterKeyId"],
            )["Attributes"]
            if (
                response.get("QueueArn") != f"arn:aws:sqs:{REGION}:{self.inventory.account_id}:{spec['name']}"
                or spec["name"].endswith(".fifo")
                or response.get("FifoQueue", "false") != "false"
                or response.get("KmsMasterKeyId")
                or not 0 < int(response["MaximumMessageSize"]) <= 1024 * 1024
            ):
                raise UnverifiedCost("Unpriced queue configuration")
            created.append(int(response["CreatedTimestamp"]))
            queues[spec["name"]] = (int(response["MaximumMessageSize"]) + 65535) // 65536
        start = self.inventory.value["metering_started_at"]
        # First-deployment evidence cannot discard an older dedicated resource's costs.
        if not created or min(created) < start - HALO_SECONDS or start > self.clock():
            raise UnverifiedCost("Metering start cannot erase an older resource's history")
        return {"tables": tables, "logs": groups, "queues": queues}

    def metrics(self, start, end):
        specs = []

        def add(namespace, name, dimensions, label):
            key = "m" + str(len(specs))
            specs.append(
                (
                    key,
                    label,
                    {
                        "Id": key,
                        "ReturnData": True,
                        "MetricStat": {
                            "Metric": {
                                "Namespace": namespace,
                                "MetricName": name,
                                "Dimensions": [{"Name": key, "Value": value} for key, value in dimensions.items()],
                            },
                            "Period": 300,
                            "Stat": "Sum",
                        },
                    },
                )
            )

        for table in self.inventory.tables:
            for index in [None, *table["indexes"]]:
                dims = {"TableName": table["name"]}
                if index:
                    dims["GlobalSecondaryIndexName"] = index
                for name, unit in (("ConsumedReadCapacityUnits", "rru"), ("ConsumedWriteCapacityUnits", "wru")):
                    add("AWS/DynamoDB", name, dims, (table["name"], unit, index or "table"))
        for function in self.inventory.functions:
            add("AWS/Lambda", "Invocations", {"FunctionName": function["name"]}, (function["name"], "invocations"))
            add("AWS/Logs", "IncomingBytes", {"LogGroupName": function["log_group"]}, (function["log_group"], "logs"))
        for queue in self.inventory.queues:
            for name in (
                "NumberOfMessagesSent",
                "NumberOfMessagesReceived",
                "NumberOfMessagesDeleted",
                "NumberOfEmptyReceives",
            ):
                add("AWS/SQS", name, {"QueueName": queue["name"]}, (queue["name"], name))
        kwargs = {"StartTime": _utc(start), "EndTime": _utc(end), "MetricDataQueries": [row[2] for row in specs]}
        pages, tokens = [], set()
        for _ in range(5):
            self.api_units += len(specs)
            response = self.cloudwatch.get_metric_data(**kwargs)
            pages.append(response)
            token = response.get("NextToken")
            if not token:
                totals = metric_totals(pages, {row[0] for row in specs}, start=start, end=end)
                # Wrong units are avoided by omitting Unit; wrong dimensions are
                # prevented by the fixed builder and resource metadata readback.
                return {label: totals[key] for key, label, _ in specs}
            if token in tokens:
                raise UnverifiedCost("Repeated CloudWatch page token")
            tokens.add(token)
            kwargs["NextToken"] = token
        raise UnverifiedCost("CloudWatch pagination bound exceeded")

    def reports(self, start, end, *, state, month, metadata, metrics, monotonic=time.monotonic, sleep=time.sleep):
        deadline = monotonic() + _LOG_QUERY_SECONDS
        all_reports = {}
        for kind in ("worker", "shared_bot"):
            groups = [row["log_group"] for row in self.inventory.functions if row["kind"] == kind]
            if not groups:
                continue
            if any(start < self.clock() - metadata["logs"][group]["retention_days"] * 86400 for group in groups):
                raise UnverifiedCost("Missing historical reports are older than log retention")
            # A fixed scan ceiling is not an AWS server-side scan limit. Refuse
            # known-large groups; unknown/lost scans retain the prepaid ceiling.
            known_bytes = sum(metadata["logs"][group]["stored_bytes"] for group in groups)
            if known_bytes > _SCAN_CEILING_BYTES or monotonic() >= deadline:
                raise UnverifiedCost("REPORT scan exceeds the bounded monitoring allowance")
            key = state.reserve_scan(month, uuid.uuid4().hex, micro(_SCAN_CEILING_BYTES / GIB, "log_scan_gib"))
            query_id, result = None, None
            try:
                self.api_units += 1
                response = self.logs.start_query(
                    logGroupNames=groups,
                    startTime=start - HALO_SECONDS,
                    endTime=end + HALO_SECONDS,
                    queryString=report_query(start, end, shared=kind == "shared_bot"),
                    limit=100,
                )
                query_id = response.get("queryId")
                if not query_id:
                    raise UnverifiedCost("Query start was not confirmed")
                while monotonic() < deadline:
                    self.api_units += 1
                    result = self.logs.get_query_results(queryId=query_id)
                    if result.get("status") == "Complete":
                        scanned = number(result.get("statistics", {}).get("bytesScanned"))
                        state.settle_scan(month, key, micro(scanned / GIB, "log_scan_gib"))
                        if scanned > _SCAN_CEILING_BYTES:
                            raise UnverifiedCost("Actual REPORT scan exceeded its allowance")
                        parsed = parse_reports(result, groups)
                        for function in self.inventory.functions:
                            if function["log_group"] not in groups:
                                continue
                            record = parsed.get(function["log_group"])
                            if kind == "worker" and metrics[(function["name"], "invocations")] != (
                                record["reports"] if record else 0
                            ):
                                raise UnverifiedCost("Worker REPORT coverage differs from Invocations")
                        all_reports.update(parsed)
                        break
                    if result.get("status") not in {"Scheduled", "Running"}:
                        raise UnverifiedCost("REPORT query failed")
                    sleep(min(1, max(0, deadline - monotonic())))
                else:
                    raise UnverifiedCost("REPORT query deadline exceeded")
            finally:
                if query_id:
                    # StopQuery on an already completed query is unnecessary;
                    # the explicit status is the only completion acknowledgement.
                    if not result or result.get("status") != "Complete":
                        self.api_units += 1
                        self.logs.stop_query(queryId=query_id)
        return all_reports


class MemoryCostMonitor:
    def __init__(self, budget, inventory, telemetry, *, sns, topic_arn, clock=time.time):
        self.inventory = inventory if isinstance(inventory, CostInventory) else CostInventory(inventory)
        self.state = CostState(budget, clock=clock)
        self.telemetry, self.sns, self.topic_arn, self.clock = telemetry, sns, topic_arn, clock

    def _blocks(self, now):
        month_start = int(_utc(now).replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
        start = max(month_start, self.inventory.value["metering_started_at"])
        # Align to 5-minute metric periods, conservatively including the leading fragment.
        start = start // 300 * 300
        end = (now - HALO_SECONDS) // 300 * 300
        if end <= start:
            raise UnverifiedCost("No settled observation window yet")
        blocks = []
        while start < end:
            boundary = (start // BLOCK_SECONDS + 1) * BLOCK_SECONDS
            blocks.append((start, min(boundary, end)))
            start = boundary
        return blocks

    def _variable(self, metrics, reports, metadata, seconds):
        amount = 0
        for table in self.inventory.tables:
            for index in ["table", *table["indexes"]]:
                for unit in ("rru", "wru"):
                    amount += micro(metrics[(table["name"], unit, index)], unit)
        for function in self.inventory.functions:
            group = function["log_group"]
            report = reports.get(group)
            if report:
                amount += micro(report["gb_seconds"], "lambda_gb_second")
                amount += micro(report["reports"], "lambda_request")
                amount += sum(
                    micro(report[key], rate) for key, rate in (("rru", "rru"), ("wru", "wru"), ("sqs", "sqs_unit"))
                )
            # Dedicated logs use the complete ingestion meter. For a shared Bot
            # invocation reserve 64 KiB of additional V2 logs, never its whole log.
            log_bytes = (
                metrics[(group, "logs")]
                if function["kind"] == "worker"
                else (report["starts"] * _SHARED_LOG_BYTES_PER_REQUEST if report else 0)
            )
            amount += micro(log_bytes / GIB, "log_ingest_gib")
            amount += micro(log_bytes / GIB, "log_storage_gib_month")
        for queue in self.inventory.queues:
            name, chunks = queue["name"], metadata["queues"][queue["name"]]
            sent = metrics[(name, "NumberOfMessagesSent")]
            received = metrics[(name, "NumberOfMessagesReceived")]
            units = (sent + received) * chunks + 2 * received
            units += metrics[(name, "NumberOfMessagesDeleted")] + metrics[(name, "NumberOfEmptyReceives")]
            # Explicit allowance for visibility/control requests outside message counters.
            units += Decimal(seconds) / 86400 * 1000
            amount += micro(units, "sqs_unit")
        return amount

    def run(self):
        now, reason, verified = int(self.clock()), "INCOMPLETE", False
        month = month_at(now)
        estimate, covered_until = 0, 0
        self.telemetry.api_units = 0
        try:
            metadata = self.telemetry.resources()
            blocks = self._blocks(now)
            rows = [(start, end, self.state.read(month, "DAY#" + str(start))) for start, end in blocks]
            # Catch up an old incomplete block first; once complete, refresh the
            # newest settled block. No unbounded historical Logs Insights query.
            start, end, _ = next(((a, b, row) for a, b, row in rows if int(row.get("covered_until", 0)) < b), rows[-1])
            metrics = self.telemetry.metrics(start, end)
            reports = self.telemetry.reports(
                start, end, state=self.state, month=month, metadata=metadata, metrics=metrics
            )
            row = self.state.save_day(
                month,
                str(start),
                {
                    "inventory_version": self.inventory.version,
                    "covered_from": start,
                    "covered_until": end,
                    "observed_at": now,
                    "variable_micro_usd": self._variable(metrics, reports, metadata, end - start),
                    "write_units": sum(value for key, value in metrics.items() if len(key) == 3 and key[1] == "wru"),
                },
            )
            rows = [(a, b, row if a == start else old) for a, b, old in rows]
            verified = all(
                value.get("inventory_version") == self.inventory.version and int(value.get("covered_until", 0)) >= b
                for _, b, value in rows
            )
            covered_until = max(int(value.get("covered_until", 0)) for _, _, value in rows)
            estimate = sum(int(value.get("variable_micro_usd", 0)) for _, _, value in rows)
            writes = sum(number(value.get("write_units", 0)) for _, _, value in rows)
            # Full-month current storage plus every metered KiB write is an
            # intentional upper estimate (updates/deletes/indexes may overcount).
            storage = sum(value["bytes"] for value in metadata["tables"].values()) + writes * 1124
            estimate += micro(storage / GIB, "storage_gib_month")
            if any(value["pitr"] for value in metadata["tables"].values()):
                estimate += micro(storage / GIB, "pitr_gib_month")
            estimate += micro(
                sum(value["stored_bytes"] for value in metadata["logs"].values()) / GIB,
                "log_storage_gib_month",
            )
            reason = "OBSERVED_GROSS_ESTIMATE" if verified else "HISTORICAL_COVERAGE_INCOMPLETE"
        except Exception as exc:
            reason = type(exc).__name__
        # Always include alarms, telemetry calls/unknown scans and a lag/operations
        # allowance. Never subtract account Free Tier, credits, tax or refunds.
        estimate += micro(self.inventory.value["alarm_count"], "standard_alarm_month") + _UNCERTAINTY_MICRO_USD
        days = calendar.monthrange(_utc(now).year, _utc(now).month)[1]
        # Reserve all scheduled hourly monitor API calls for the month up front.
        estimate += micro(max(self.telemetry.api_units, 64) * 24 * days, "metric_query")
        # Monitor/notification runtime allowance is independent of budget approval;
        # pausing optional work must not stop recovery and threshold delivery.
        estimate += 100_000
        measurement = self.state.record_measurement(
            month,
            inventory_version=self.inventory.version,
            verified=verified,
            estimate=estimate,
            covered_until=covered_until,
            reason=reason,
        )
        self.state.observe_model(month)
        self.state.dispatch_notices(sns=self.sns, topic_arn=self.topic_arn)
        if measurement["measurement_state"] != "ESTIMATE_VERIFIED":
            raise UnverifiedCost("Memory AWS measurement is incomplete; optional work remains paused")
        return {
            key: measurement[key]
            for key in ("measurement_state", "estimate_micro_usd", "observed_at", "covered_until", "paused", "reason")
        }
