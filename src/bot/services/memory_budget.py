"""Memory V2 model budget: one conservative reservation per network attempt.

USD micro-units avoid binary floating point. No API credentials, source text or
Telegram identities belong here. The table must be the independent V2 table.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from botocore.exceptions import ClientError
from services.repositories._common import get_dynamodb

MODEL = "gemini-3.1-flash-lite"
PRICE_VERSION = "google-standard-text-2026-09-10"
MONTHLY_LIMIT_MICRO_USD = 7_000_000
# Full published model limits; do not mistake chars/4 for a multilingual token bound.
# Reserve a separate full output allowance for thoughts as an additional margin.
INPUT_CEILING = 1_048_576
OUTPUT_CEILING = 2 * 65_536
RESERVATION_MICRO_USD = (INPUT_CEILING + 6 * OUTPUT_CEILING + 3) // 4
RETENTION_SECONDS = 400 * 86400


class MemoryBudgetPaused(RuntimeError):
    """Optional learning/enhancement must stop; plain explicit asks may continue."""

    retry_after: int | None = None


class DuplicateMemoryAttempt(RuntimeError):
    """A reservation already exists; do not make this network attempt again."""


class MemoryBudgetAccountingError(RuntimeError):
    """Provider metadata contradicts the bounded billing contract."""


def _nonnegative_int(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("Expected nonnegative token count")
    return value


def cost_micro_usd(input_tokens: int, output_tokens: int) -> int:
    """Standard text: $0.25/M input + $1.50/M output, including thinking."""
    return (_nonnegative_int(input_tokens) + 6 * _nonnegative_int(output_tokens) + 3) // 4


@dataclass(frozen=True)
class Reservation:
    month: str
    attempt_id: str
    token: str
    reserved_micro_usd: int


class MemoryBudgetRepository:
    def __init__(self, table_name: str, *, clock=time.time, inventory_version=None):
        if not isinstance(table_name, str) or not table_name.strip():
            raise ValueError("An independent V2 table is required")
        self.table = get_dynamodb().Table(table_name)
        self.clock = clock
        self.inventory_version = inventory_version or ""
        if not self.inventory_version:
            from services.memory_v2._cost_catalog import UnverifiedCost, parse_inventory

            try:
                self.inventory_version = parse_inventory(os.environ.get("MEMORY_COST_INVENTORY", "")).version
            except (ValueError, TypeError, KeyError, UnverifiedCost):
                pass  # Invalid/missing deployment metadata cannot create an AWS permit.

    def next_month(self):
        current = datetime.fromtimestamp(self.clock(), timezone.utc)
        year, month = (current.year + 1, 1) if current.month == 12 else (current.year, current.month + 1)
        return int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp())

    def month(self):
        return datetime.fromtimestamp(self.clock(), timezone.utc).strftime("%Y-%m")

    @staticmethod
    def _key(month, sk):
        if not isinstance(month, str) or not re.fullmatch(r"20[0-9]{2}-(0[1-9]|1[0-2])", month):
            raise ValueError("Invalid UTC billing month")
        return {"pk": f"MEMORY_BUDGET#{month}", "sk": sk}

    def _attempt_key(self, month, attempt_id):
        if not isinstance(attempt_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", attempt_id):
            raise ValueError("Invalid attempt identifier")
        # Opaque keys do not reveal caller identifiers or input.
        return {"pk": "MEMORY_ATTEMPT#" + hashlib.sha256(attempt_id.encode()).hexdigest(), "sk": "MODEL"}

    def snapshot(self, *, month=None):
        return self.table.get_item(Key=self._key(month or self.month(), "MODEL"), ConsistentRead=True).get("Item", {})

    def _aws_permit(self, month, now):
        from services.memory_v2._cost_state import AWS_STOP, FRESH_SECONDS, PRICE_VERSION

        row = self.table.get_item(Key=self._key(month, "AWS"), ConsistentRead=True).get("Item") or {}
        try:

            def integer(field, default=0):
                value = row.get(field, default)
                if isinstance(value, bool) or not isinstance(value, (int, Decimal)) or int(value) != value:
                    raise ValueError("Malformed AWS observation")
                return int(value)

            numbers_valid = (
                integer("revision") > 0
                and 0 <= integer("estimate_micro_usd", -1) < AWS_STOP
                and now - FRESH_SECONDS < integer("observed_at") <= now
                and now - FRESH_SECONDS < integer("covered_until") <= now
                and now < integer("valid_until") <= integer("observed_at") + FRESH_SECONDS
            )
        except (TypeError, ValueError, OverflowError):
            numbers_valid = False
        if (
            not numbers_valid
            or not self.inventory_version
            or row.get("inventory_version") != self.inventory_version
            or row.get("price_version") != PRICE_VERSION
            or row.get("measurement_state") != "ESTIMATE_VERIFIED"
            or type(row.get("paused")) is not bool
            or row["paused"]
        ):
            error = MemoryBudgetPaused("Optional memory AWS estimate is paused, incomplete or stale")
            error.retry_after = self.next_month() if row.get("paused") else now + 300
            raise error
        return row

    def check_available(self) -> None:
        """Read-only preflight before consuming shared provider quota; not a permit."""
        self._check_model_control()
        self._aws_permit(self.month(), int(self.clock()))
        month = self.snapshot()
        if (
            month.get("paused")
            or int(month.get("charged_micro_usd", 0)) > MONTHLY_LIMIT_MICRO_USD - RESERVATION_MICRO_USD
        ):
            error = MemoryBudgetPaused("Optional memory budget unavailable")
            error.retry_after = self.next_month()
            raise error

    def check_aws_available(self) -> None:
        """Read-only preflight for optional AWS work, independent of model headroom.

        Deterministic profile/forget commands and the monitor itself must not be
        routed through the combined model gate. This read is not a lasting permit.
        """
        self._aws_permit(self.month(), int(self.clock()))

    def _check_model_control(self):
        """Accounting anomalies remain global and retain their existing retry semantics."""
        control = (
            self.table.get_item(Key={"pk": "MEMORY_BUDGET#CONTROL", "sk": "MODEL"}, ConsistentRead=True).get("Item")
            or {}
        )
        if control.get("paused"):
            error = MemoryBudgetPaused("Optional memory budget unavailable")
            error.retry_after = self.next_month()
            raise error

    def reserve(self, attempt_id: str, *, purpose: str, model: str = MODEL) -> Reservation:
        """Only a freshly created reservation authorizes one bounded HTTP attempt.

        A timeout from this transaction is ambiguous: do not call the provider.
        Retry with the same id; a persisted reservation produces DuplicateMemoryAttempt.
        The caller may create a new attempt id, consuming another reservation.
        """
        if model != MODEL or purpose not in {"extract", "answer"}:
            raise ValueError("Unpriced model or purpose")
        month = self.month()
        key = self._attempt_key(month, attempt_id)
        if self.table.get_item(Key=key, ConsistentRead=True).get("Item"):
            raise DuplicateMemoryAttempt("Network attempt already reserved")
        token = uuid.uuid4().hex
        now = int(self.clock())
        self._check_model_control()
        aws = self._aws_permit(month, now)
        item = {
            **key,
            "status": "RESERVED",
            "month": month,
            "token": token,
            "reserved_micro_usd": RESERVATION_MICRO_USD,
            "model": MODEL,
            "purpose": purpose,
            "price_version": PRICE_VERSION,
            "created_at": now,
            "ttl": now + RETENTION_SECONDS,
        }
        try:
            self.table.meta.client.transact_write_items(
                TransactItems=[
                    {
                        "ConditionCheck": {
                            "TableName": self.table.name,
                            "Key": self._key(month, "AWS"),
                            "ConditionExpression": "#revision = :revision AND paused = :false "
                            "AND valid_until > :now AND inventory_version = :inventory "
                            "AND measurement_state = :verified AND price_version = :price",
                            "ExpressionAttributeNames": {"#revision": "revision"},
                            "ExpressionAttributeValues": {
                                ":revision": aws["revision"],
                                ":false": False,
                                ":now": now,
                                ":inventory": self.inventory_version,
                                ":verified": "ESTIMATE_VERIFIED",
                                ":price": aws["price_version"],
                            },
                        }
                    },
                    {
                        "ConditionCheck": {
                            "TableName": self.table.name,
                            "Key": {"pk": "MEMORY_BUDGET#CONTROL", "sk": "MODEL"},
                            "ConditionExpression": "attribute_not_exists(paused) OR paused = :false",
                            "ExpressionAttributeValues": {":false": False},
                        }
                    },
                    {
                        "Put": {
                            "TableName": self.table.name,
                            "Item": item,
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                    {
                        "Update": {
                            "TableName": self.table.name,
                            "Key": self._key(month, "MODEL"),
                            "UpdateExpression": "SET charged_micro_usd = "
                            "if_not_exists(charged_micro_usd, :zero) + :cost, "
                            "#ttl = :ttl, price_version = :price",
                            "ConditionExpression": "(attribute_not_exists(charged_micro_usd) "
                            "OR charged_micro_usd <= :room) "
                            "AND (attribute_not_exists(paused) OR paused = :false)",
                            "ExpressionAttributeNames": {"#ttl": "ttl"},
                            "ExpressionAttributeValues": {
                                ":cost": RESERVATION_MICRO_USD,
                                ":room": MONTHLY_LIMIT_MICRO_USD - RESERVATION_MICRO_USD,
                                ":zero": 0,
                                ":false": False,
                                ":ttl": now + RETENTION_SECONDS,
                                ":price": PRICE_VERSION,
                            },
                        }
                    },
                ]
            )
        except ClientError as exc:
            reasons = exc.response.get("CancellationReasons") or []
            if exc.response.get("Error", {}).get("Code") == "TransactionCanceledException" and any(
                r.get("Code") == "ConditionalCheckFailed" for r in reasons
            ):
                existing = self.table.get_item(Key=key, ConsistentRead=True).get("Item")
                if existing:
                    raise DuplicateMemoryAttempt("Network attempt already reserved") from exc
                # An hourly measurement can change its revision between the read
                # and transaction. No permit escaped: allow a later bounded retry.
                if reasons and reasons[0].get("Code") == "ConditionalCheckFailed":
                    error = MemoryBudgetPaused("AWS measurement changed before reservation")
                    error.retry_after = now + 300
                    raise error from exc
                error = MemoryBudgetPaused("Insufficient conservative model budget or budget paused")
                error.retry_after = self.next_month()
                raise error from exc
            raise  # Database failure cannot authorize an optional provider call.
        return Reservation(month, attempt_id, token, RESERVATION_MICRO_USD)

    @staticmethod
    def _usage_cost(usage):
        if not isinstance(usage, dict):
            raise ValueError("Missing provider usage")
        # Missing component counts are unknown, not zero. No unsafe refund.
        inputs = _nonnegative_int(usage["promptTokenCount"])
        candidates = _nonnegative_int(usage["candidatesTokenCount"])
        total = _nonnegative_int(usage["totalTokenCount"])
        # An omitted thoughts count is recoverable only from the documented total.
        thoughts = _nonnegative_int(usage.get("thoughtsTokenCount", total - inputs - candidates))
        if inputs + candidates + thoughts != total:
            raise ValueError("Inconsistent provider token totals")
        if usage.get("cachedContentTokenCount", 0) or usage.get("toolUsePromptTokenCount", 0):
            raise ValueError("Memory calls do not use cache or tools")
        if usage.get("serviceTier", "STANDARD") not in {"STANDARD", "SERVICE_TIER_UNSPECIFIED"}:
            raise ValueError("Unpriced service tier")
        details = usage.get("promptTokensDetails", [])
        if not isinstance(details, list):
            raise ValueError("Invalid modality metadata")
        for detail in details:
            if not isinstance(detail, dict) or detail.get("modality") != "TEXT":
                raise ValueError("Non-text model billing is unsupported")
        return cost_micro_usd(inputs, candidates + thoughts)

    def settle(self, reservation: Reservation, usage: dict | None) -> bool:
        """Refund only a valid completed call's over-reservation, atomically once.

        None/missing/malformed metadata retains the entire reservation, including
        timeouts, safety failures and token counts omitted by the provider. It is
        safe to retry settlement after a database error, but never the HTTP call.
        """
        try:
            actual = self._usage_cost(usage)
        except (KeyError, TypeError, ValueError):
            return False
        anomaly = actual > reservation.reserved_micro_usd
        key = self._attempt_key(reservation.month, reservation.attempt_id)
        refund = reservation.reserved_micro_usd - actual
        try:
            self.table.meta.client.transact_write_items(
                TransactItems=(
                    [
                        {
                            "Update": {
                                "TableName": self.table.name,
                                "Key": {"pk": "MEMORY_BUDGET#CONTROL", "sk": "MODEL"},
                                "UpdateExpression": "SET paused = :true, pause_reason = :reason, "
                                "price_version = :price",
                                "ExpressionAttributeValues": {
                                    ":true": True,
                                    ":price": PRICE_VERSION,
                                    ":reason": "PROVIDER_USAGE_EXCEEDS_RESERVATION",
                                },
                            }
                        }
                    ]
                    if anomaly
                    else []
                )
                + [
                    {
                        "Update": {
                            "TableName": self.table.name,
                            "Key": key,
                            "UpdateExpression": "SET #status = :settled, actual_micro_usd = :actual",
                            "ConditionExpression": "#status = :reserved AND #token = :token "
                            "AND reserved_micro_usd = :amount AND #month = :month "
                            "AND price_version = :price",
                            "ExpressionAttributeNames": {"#status": "status", "#token": "token", "#month": "month"},
                            "ExpressionAttributeValues": {
                                ":reserved": "RESERVED",
                                ":settled": "SETTLED",
                                ":token": reservation.token,
                                ":amount": reservation.reserved_micro_usd,
                                ":actual": actual,
                                ":month": reservation.month,
                                ":price": PRICE_VERSION,
                            },
                        }
                    },
                    {
                        "Update": {
                            "TableName": self.table.name,
                            "Key": self._key(reservation.month, "MODEL"),
                            "UpdateExpression": "SET charged_micro_usd = charged_micro_usd - :refund, "
                            "settled_micro_usd = if_not_exists(settled_micro_usd, :zero) + :actual"
                            + (", paused = :true, pause_reason = :reason" if anomaly else ""),
                            "ConditionExpression": "charged_micro_usd >= :refund",
                            "ExpressionAttributeValues": {
                                ":refund": refund,
                                ":zero": 0,
                                ":actual": actual,
                                **({":true": True, ":reason": "PROVIDER_USAGE_EXCEEDS_RESERVATION"} if anomaly else {}),
                            },
                        }
                    },
                ]
            )
        except ClientError as exc:
            reasons = exc.response.get("CancellationReasons") or []
            if exc.response.get("Error", {}).get("Code") == "TransactionCanceledException" and any(
                r.get("Code") == "ConditionalCheckFailed" for r in reasons
            ):
                previous = self.table.get_item(Key=key, ConsistentRead=True).get("Item") or {}
                if previous.get("token") == reservation.token and previous.get("status") == "SETTLED":
                    if previous.get("actual_micro_usd") == actual:
                        if anomaly:
                            raise MemoryBudgetAccountingError("Provider usage exceeds model ceiling") from exc
                        return True
                raise MemoryBudgetAccountingError("Settlement conflicts with persisted reservation") from exc
            raise
        if anomaly:
            raise MemoryBudgetAccountingError("Provider usage exceeds model ceiling")
        return True
