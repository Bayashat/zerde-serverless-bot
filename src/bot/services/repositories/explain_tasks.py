"""Idempotency storage for async /wtf explain tasks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from botocore.exceptions import ClientError
from core.config import STATS_TABLE_NAME
from core.logger import LoggerAdapter, get_logger
from services.repositories._common import get_dynamodb

logger = LoggerAdapter(get_logger(__name__), {})

_PK_PREFIX = "WTF_UPDATE"
_TTL_DELTA = timedelta(hours=24)


class ExplainTaskRepository:
    """Tracks whether a Telegram update was already enqueued/completed.

    Uses the shared stats table with key pattern: ``WTF_UPDATE#<update_id>``.
    """

    def __init__(self) -> None:
        pass

    @property
    def _table(self):
        return get_dynamodb().Table(STATS_TABLE_NAME)

    @staticmethod
    def _stat_key(update_id: int) -> str:
        return f"{_PK_PREFIX}#{update_id}"

    @staticmethod
    def _ttl_epoch() -> int:
        return int((datetime.now(timezone.utc) + _TTL_DELTA).timestamp())

    def try_reserve_update(self, update_id: int) -> bool:
        """Reserve an update id. Returns False when duplicate webhook delivery."""
        try:
            self._table.put_item(
                Item={
                    "stat_key": self._stat_key(update_id),
                    "status": "reserved",
                    "ttl": self._ttl_epoch(),
                },
                ConditionExpression="attribute_not_exists(stat_key)",
            )
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code == "ConditionalCheckFailedException":
                return False
            logger.exception("Failed to reserve explain update", extra={"update_id": update_id})
            raise

    def mark_enqueued(self, update_id: int) -> None:
        """Mark task as enqueued to improve traceability."""
        try:
            self._table.update_item(
                Key={"stat_key": self._stat_key(update_id)},
                UpdateExpression="SET #s = :status, #t = :ttl",
                ExpressionAttributeNames={"#s": "status", "#t": "ttl"},
                ExpressionAttributeValues={":status": "enqueued", ":ttl": self._ttl_epoch()},
            )
        except ClientError:
            logger.exception("Failed to mark explain task as enqueued", extra={"update_id": update_id})
            raise

    def mark_completed(self, update_id: int) -> None:
        """Mark task as completed after the final Telegram message is sent."""
        try:
            self._table.update_item(
                Key={"stat_key": self._stat_key(update_id)},
                UpdateExpression="SET #s = :status, #t = :ttl",
                ExpressionAttributeNames={"#s": "status", "#t": "ttl"},
                ExpressionAttributeValues={":status": "completed", ":ttl": self._ttl_epoch()},
            )
        except ClientError:
            logger.exception("Failed to mark explain task as completed", extra={"update_id": update_id})
            raise

    def release_reservation(self, update_id: int) -> None:
        """Remove dedup row so the user can retry after SQS send failed (reservation was written)."""
        try:
            self._table.delete_item(Key={"stat_key": self._stat_key(update_id)})
        except ClientError:
            logger.exception("Failed to release explain reservation", extra={"update_id": update_id})
            raise
