"""One owner for AWS estimates, bounded scan reservations, and budget notices.

MODEL/CONTROL and provider attempts remain owned by MemoryBudgetRepository.
All amounts are integer USD micro-units; these rows are not AWS invoice records.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

AWS_LIMIT = 3_000_000
AWS_STOP = 2_700_000
FRESH_SECONDS = 3 * 3600
RETENTION_SECONDS = 400 * 86400
PRICE_VERSION = "aws-eu-central-1-gross-2026-09-11"
NOTICE_SCOPES = {"AWS": "incremental_aws", "MODEL": "model"}


class CostStateConflict(RuntimeError):
    pass


def month_at(now):
    return datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m")


class CostState:
    def __init__(self, budget, *, clock=time.time):
        self.budget, self.table, self.clock = budget, budget.table, clock

    def key(self, month, sk):
        return self.budget._key(month, sk)

    def read(self, month, sk):
        return self.table.get_item(Key=self.key(month, sk), ConsistentRead=True).get("Item") or {}

    def _transaction(self, operations):
        try:
            self.table.meta.client.transact_write_items(TransactItems=operations)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "TransactionCanceledException" and any(
                reason.get("Code") == "ConditionalCheckFailed" for reason in exc.response.get("CancellationReasons", [])
            ):
                raise CostStateConflict("Cost observation changed concurrently") from exc
            raise

    def _put(self, row, previous):
        operation = {"TableName": self.table.name, "Item": row}
        if previous:
            operation.update(
                ConditionExpression="#revision = :revision",
                ExpressionAttributeNames={"#revision": "revision"},
                ExpressionAttributeValues={":revision": previous["revision"]},
            )
        else:
            operation["ConditionExpression"] = "attribute_not_exists(pk)"
        return {"Put": operation}

    def _row(self, month, sk, previous, **fields):
        return {
            **previous,
            **self.key(month, sk),
            "revision": int(previous.get("revision", 0)) + 1,
            "ttl": int(self.clock()) + RETENTION_SECONDS,
            **fields,
        }

    def reserve_scan(self, month, attempt_id, upper_micro_usd):
        """Persist liability before StartQuery; a lost response never permits a repeat."""
        if month != month_at(self.clock()):
            raise CostStateConflict("A stale monitor cannot start a new month's query")
        if type(upper_micro_usd) is not int or not 0 <= upper_micro_usd <= 50_000:
            raise ValueError("Scan reservation exceeds the per-query ceiling")
        digest = hashlib.sha256(attempt_id.encode()).hexdigest()
        key = self.key(month, "SCAN#" + digest)
        item = {
            **key,
            "state": "RESERVED",
            "reserved_micro_usd": upper_micro_usd,
            "price_version": PRICE_VERSION,
            "ttl": int(self.clock()) + RETENTION_SECONDS,
        }
        previous = self.read(month, "MONITOR")
        row = self._row(
            month,
            "MONITOR",
            previous,
            scan_micro_usd=int(previous.get("scan_micro_usd", 0)) + upper_micro_usd,
        )
        operations = [
            {"Put": {"TableName": self.table.name, "Item": item, "ConditionExpression": "attribute_not_exists(pk)"}},
            self._put(row, previous),
        ]
        aws = self.read(month, "AWS")
        if aws:
            operations.append(
                self._put(
                    self._row(
                        month,
                        "AWS",
                        aws,
                        measurement_state="UNVERIFIED",
                        valid_until=int(self.clock()),
                        reason="REPORT_QUERY_IN_PROGRESS",
                    ),
                    aws,
                )
            )
        self._transaction(operations)
        return key

    def settle_scan(self, month, key, actual_micro_usd):
        current = self.table.get_item(Key=key, ConsistentRead=True).get("Item") or {}
        if not current or type(actual_micro_usd) is not int or actual_micro_usd < 0:
            raise ValueError("Invalid scan settlement")
        if current["state"] == "SETTLED":
            if current["actual_micro_usd"] != actual_micro_usd:
                raise CostStateConflict("Scan settlement changed")
            return
        previous = self.read(month, "MONITOR")
        # Exceeding the estimate retains the extra liability and invalidates admission.
        anomaly = actual_micro_usd > int(current["reserved_micro_usd"])
        row = self._row(
            month,
            "MONITOR",
            previous,
            scan_micro_usd=int(previous.get("scan_micro_usd", 0))
            + actual_micro_usd
            - int(current["reserved_micro_usd"]),
            scan_bound_exceeded=bool(previous.get("scan_bound_exceeded")) or anomaly,
        )
        self._transaction(
            [
                {
                    "Put": {
                        "TableName": self.table.name,
                        "Item": {**current, "state": "SETTLED", "actual_micro_usd": actual_micro_usd},
                        "ConditionExpression": "#state = :reserved",
                        "ExpressionAttributeNames": {"#state": "state"},
                        "ExpressionAttributeValues": {":reserved": "RESERVED"},
                    }
                },
                self._put(row, previous),
            ]
        )

    def save_day(self, month, day, observed):
        """A recomputed UTC block can increase totals/coverage, never erase liability."""
        previous = self.read(month, "DAY#" + day)
        if previous and previous.get("inventory_version") != observed["inventory_version"]:
            raise CostStateConflict("Inventory changed inside a metered month")
        if previous and int(previous["covered_until"]) > observed["covered_until"]:
            raise CostStateConflict("Stale daily observation")
        row = self._row(month, "DAY#" + day, previous, **observed)
        row["variable_micro_usd"] = max(int(previous.get("variable_micro_usd", 0)), observed["variable_micro_usd"])
        row["write_units"] = max(previous.get("write_units", 0), observed["write_units"])
        self._transaction([self._put(row, previous)])
        return row

    def record_measurement(self, month, *, inventory_version, verified, estimate, covered_until, reason):
        """The AWS guard and its highest notification transition commit together."""
        now = int(self.clock())
        if month != month_at(now):
            raise CostStateConflict("An old observation cannot authorize a new month")
        if type(estimate) is not int or estimate < 0:
            raise ValueError("Invalid estimate")
        previous = self.read(month, "AWS")
        monitor = self.read(month, "MONITOR")
        base = max(int(previous.get("base_estimate_micro_usd", 0)), estimate)
        gross = base + int(monitor.get("scan_micro_usd", 0))
        paused = bool(previous.get("paused")) or gross >= AWS_STOP
        verified = verified and not monitor.get("scan_bound_exceeded", False)
        row = self._row(
            month,
            "AWS",
            previous,
            estimate_micro_usd=gross,
            base_estimate_micro_usd=base,
            budget_micro_usd=AWS_LIMIT,
            price_version=PRICE_VERSION,
            inventory_version=inventory_version,
            measurement_state="ESTIMATE_VERIFIED" if verified else "UNVERIFIED",
            observed_at=now,
            covered_until=covered_until,
            valid_until=now + FRESH_SECONDS if verified else now,
            paused=paused,
            reason="SCAN_BOUND_EXCEEDED" if monitor.get("scan_bound_exceeded") else reason,
        )
        operations = [self._put(row, previous)]
        notice = self._notice_operation(month, "AWS", gross, AWS_LIMIT, paused)
        if notice:
            operations.extend(notice)
        if monitor:
            operations.append(
                {
                    "ConditionCheck": {
                        "TableName": self.table.name,
                        "Key": self.key(month, "MONITOR"),
                        "ConditionExpression": "#revision = :revision",
                        "ExpressionAttributeNames": {"#revision": "revision"},
                        "ExpressionAttributeValues": {":revision": monitor["revision"]},
                    }
                }
            )
        else:
            operations.append(
                {
                    "ConditionCheck": {
                        "TableName": self.table.name,
                        "Key": self.key(month, "MONITOR"),
                        "ConditionExpression": "attribute_not_exists(pk)",
                    }
                }
            )
        self._transaction(operations)
        return row

    def _notice_operation(self, month, scope, amount, limit, paused):
        threshold = next((p for p in (100, 90, 80) if amount * 100 >= limit * p), 0)
        if not threshold:
            return None
        rank = threshold * 2 + int(paused)
        previous = self.read(month, "NOTICE#" + scope)
        if int(previous.get("rank", 0)) >= rank:
            return None
        row = self._row(
            month,
            "NOTICE#" + scope,
            previous,
            rank=rank,
            state="PENDING",
            event={
                "schema": "zerde.operations.v1",
                "kind": "budget",
                "project": "ZerdeBot",
                "environment": "prod",
                "component": "memory-v2",
                "budget_scope": NOTICE_SCOPES[scope],
                "threshold_percent": threshold,
                "status": "paused" if paused else "warning",
                "period": month,
                "observed_at": datetime.fromtimestamp(self.clock(), timezone.utc).isoformat().replace("+00:00", "Z"),
            },
        )
        # Pending notifications survive until delivery/explicit expiry, not a TTL race.
        row.pop("ttl", None)
        marker = {
            "pk": "MEMORY_BUDGET#NOTICE_OUTBOX",
            "sk": month + "#" + scope,
            "month": month,
            "scope": scope,
            "revision": row["revision"],
        }
        return [self._put(row, previous), {"Put": {"TableName": self.table.name, "Item": marker}}]

    def observe_model(self, month):
        """A fenced read of the existing model ledger; never write a second MODEL owner."""
        if month != month_at(self.clock()):
            raise CostStateConflict("Model observation belongs to a stale month")
        current = self.budget.snapshot(month=month)
        control_key = {"pk": "MEMORY_BUDGET#CONTROL", "sk": "MODEL"}
        control = self.table.get_item(Key=control_key, ConsistentRead=True).get("Item") or {}
        amount = int(current.get("charged_micro_usd", 0))
        from services.memory_budget import MONTHLY_LIMIT_MICRO_USD, RESERVATION_MICRO_USD

        paused = (
            bool(control.get("paused"))
            or bool(current.get("paused"))
            or amount > MONTHLY_LIMIT_MICRO_USD - RESERVATION_MICRO_USD
        )
        operation = self._notice_operation(month, "MODEL", amount, MONTHLY_LIMIT_MICRO_USD, paused)
        if not operation:
            return

        def pause_fence(row):
            if "paused" in row:
                return "paused = :paused", {":paused": row["paused"]}
            return "attribute_not_exists(paused)", {}

        month_condition, month_values = pause_fence(current)
        global_condition, global_values = pause_fence(control)
        global_check = {
            "TableName": self.table.name,
            "Key": control_key,
            "ConditionExpression": global_condition,
        }
        if global_values:
            global_check["ExpressionAttributeValues"] = global_values
        self._transaction(
            [
                {
                    "ConditionCheck": {
                        "TableName": self.table.name,
                        "Key": self.key(month, "MODEL"),
                        "ConditionExpression": "charged_micro_usd = :amount AND " + month_condition,
                        "ExpressionAttributeValues": {":amount": amount, **month_values},
                    }
                },
                {"ConditionCheck": global_check},
                *operation,
            ]
        )

    def dispatch_notices(self, *, sns, topic_arn):
        """Publish an unchanged event; a lost acknowledgement can repeat, never lose, it."""
        sent = 0
        markers = self.table.query(
            KeyConditionExpression=Key("pk").eq("MEMORY_BUDGET#NOTICE_OUTBOX"), ConsistentRead=True, Limit=20
        ).get("Items", [])
        for marker in markers:
            month, scope = marker["month"], marker["scope"]
            previous = self.read(month, "NOTICE#" + scope)
            if previous.get("state") != "PENDING" or previous.get("revision") != marker["revision"]:
                raise CostStateConflict("Notification outbox differs from its owner")
            event = {**previous["event"], "threshold_percent": int(previous["event"]["threshold_percent"])}
            observed = datetime.fromisoformat(event["observed_at"].replace("Z", "+00:00")).timestamp()
            expired = self.clock() - observed > 7 * 86400
            if not expired:
                response = sns.publish(TopicArn=topic_arn, Message=json.dumps(event, separators=(",", ":")))
                if not response.get("MessageId"):
                    raise RuntimeError("Budget SNS publish was not confirmed")
            row = self._row(month, "NOTICE#" + scope, previous, state="EXPIRED" if expired else "SENT")
            self._transaction(
                [
                    self._put(row, previous),
                    {
                        "Delete": {
                            "TableName": self.table.name,
                            "Key": {"pk": marker["pk"], "sk": marker["sk"]},
                            "ConditionExpression": "#revision = :revision",
                            "ExpressionAttributeNames": {"#revision": "revision"},
                            "ExpressionAttributeValues": {":revision": marker["revision"]},
                        }
                    },
                ]
            )
            sent += not expired
        return sent
