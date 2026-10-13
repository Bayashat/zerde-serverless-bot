"""Serialize one notification stream; only operations# keys belong to this owner."""

import hashlib
import time
import uuid
from decimal import Decimal

from botocore.exceptions import ClientError


class DeliveryBusyError(RuntimeError):
    pass


class DeliveryRepository:
    def __init__(self, table):
        self.table = table

    def claim(self, stream: str, observed_at: int, *, cooldown_seconds: int = 0) -> tuple[str, str] | None:
        if type(cooldown_seconds) is not int or cooldown_seconds < 0:
            raise ValueError("Invalid notification cooldown")
        key = "operations#" + hashlib.sha256(stream.encode()).hexdigest()
        now_ms = int(time.time() * 1000)
        now = now_ms // 1000
        owner = uuid.uuid4().hex
        try:
            claimed = self.table.update_item(
                Key={"stat_key": key},
                UpdateExpression="SET lease_owner = :owner, lease_until = :until, #ttl = :ttl",
                ConditionExpression=(
                    "(attribute_not_exists(delivered_at) OR delivered_at < :observed) AND "
                    "(attribute_not_exists(handled_at) OR handled_at < :observed) AND "
                    "(attribute_not_exists(lease_owner) OR lease_until < :now)"
                ),
                ExpressionAttributeNames={"#ttl": "ttl"},
                ExpressionAttributeValues={
                    ":owner": owner,
                    ":until": now + 90,
                    ":ttl": now + 30 * 86400,
                    ":observed": observed_at,
                    ":now": now,
                },
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
            row = self.table.get_item(Key={"stat_key": key}, ConsistentRead=True).get("Item") or {}
            if any(self._stored_timestamp(row, field) >= observed_at for field in ("delivered_at", "handled_at")):
                return None
            raise DeliveryBusyError("Notification stream is busy") from None
        if cooldown_seconds:
            row = claimed["Attributes"]
            field = "last_sent_at" if "last_sent_at" in row else "delivered_at"
            anchor = self._stored_timestamp(row, field)
            if anchor >= 0 and now_ms - anchor < cooldown_seconds * 1000:
                self.suppress(key, owner, observed_at)
                return None
        return key, owner

    @staticmethod
    def _stored_timestamp(row: dict, field: str) -> int:
        if field not in row:
            return -1
        value = row[field]
        if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
            raise ValueError("Invalid notification timestamp")
        if isinstance(value, Decimal) and not value.is_finite():
            raise ValueError("Invalid notification timestamp")
        if value < 0 or int(value) != value:
            raise ValueError("Invalid notification timestamp")
        return int(value)

    def suppress(self, key: str, owner: str, observed_at: int) -> None:
        """Remember a silent transition without claiming a successful send."""
        self.table.update_item(
            Key={"stat_key": key},
            UpdateExpression="SET handled_at = :observed REMOVE lease_owner, lease_until",
            ConditionExpression="lease_owner = :owner",
            ExpressionAttributeValues={":observed": observed_at, ":owner": owner},
        )

    def confirm(self, key: str, owner: str, observed_at: int) -> None:
        self.table.update_item(
            Key={"stat_key": key},
            UpdateExpression=(
                "SET delivered_at = :observed, handled_at = :observed, last_sent_at = :sent "
                "REMOVE lease_owner, lease_until"
            ),
            ConditionExpression="lease_owner = :owner",
            ExpressionAttributeValues={":observed": observed_at, ":owner": owner, ":sent": int(time.time() * 1000)},
        )

    def release(self, key: str, owner: str) -> None:
        try:
            self.table.update_item(
                Key={"stat_key": key},
                UpdateExpression="REMOVE lease_owner, lease_until",
                ConditionExpression="lease_owner = :owner",
                ExpressionAttributeValues={":owner": owner},
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
