"""Serialize one notification stream; only operations# keys belong to this owner."""

import hashlib
import time
import uuid

from botocore.exceptions import ClientError


class DeliveryBusyError(RuntimeError):
    pass


class DeliveryRepository:
    def __init__(self, table):
        self.table = table

    def claim(self, stream: str, observed_at: int) -> tuple[str, str] | None:
        key = "operations#" + hashlib.sha256(stream.encode()).hexdigest()
        now = int(time.time())
        owner = uuid.uuid4().hex
        try:
            self.table.update_item(
                Key={"stat_key": key},
                UpdateExpression="SET lease_owner = :owner, lease_until = :until, #ttl = :ttl",
                ConditionExpression=(
                    "(attribute_not_exists(delivered_at) OR delivered_at < :observed) AND "
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
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
            row = self.table.get_item(Key={"stat_key": key}, ConsistentRead=True).get("Item") or {}
            if int(row.get("delivered_at", -1)) >= observed_at:
                return None
            raise DeliveryBusyError("Notification stream is busy") from None
        return key, owner

    def confirm(self, key: str, owner: str, observed_at: int) -> None:
        self.table.update_item(
            Key={"stat_key": key},
            UpdateExpression="SET delivered_at = :observed REMOVE lease_owner, lease_until",
            ConditionExpression="lease_owner = :owner",
            ExpressionAttributeValues={":observed": observed_at, ":owner": owner},
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
