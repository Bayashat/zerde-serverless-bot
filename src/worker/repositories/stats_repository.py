"""
Repository for bot statistics (joins, verified users) in DynamoDB.
Per-chat stats: partition key stat_key = chat_id as string.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError
from repositories import STATS_TABLE_NAME

logger = Logger()

dynamodb = boto3.resource("dynamodb")

ALMATY_TZ = timezone(timedelta(hours=5))


def _almaty_now_str() -> str:
    """Current time in Almaty (UTC+5) as string for started_at."""
    return datetime.now(ALMATY_TZ).strftime("%Y-%m-%d %H:%M:%S UTC+5")


class StatsRepository:
    """
    Repository for ZerdeStats table: total_joins, verified_users per chat.
    PK: stat_key = chat_id (string).
    """

    def __init__(self) -> None:
        self._table = dynamodb.Table(STATS_TABLE_NAME)
        logger.info("StatsRepository initialized", extra={"table_name": STATS_TABLE_NAME})

    def increment_total_joins(self, chat_id: int | str) -> None:
        self._increment(str(chat_id), "total_joins")

    def increment_verified_users(self, chat_id: int | str) -> None:
        self._increment(str(chat_id), "verified_users")

    def _increment(self, stat_key: str, attr: str) -> None:
        try:
            self._table.update_item(
                Key={"stat_key": stat_key},
                UpdateExpression="SET #a = if_not_exists(#a, :zero) + :inc, #d = if_not_exists(#d, :now)",
                ExpressionAttributeNames={"#a": attr, "#d": "started_at"},
                ExpressionAttributeValues={":inc": 1, ":zero": 0, ":now": _almaty_now_str()},
            )
        except ClientError as e:
            logger.exception(f"Failed to increment {attr}: {e}")
            raise

    def get_stats(self, chat_id: int | str) -> dict[str, Any]:
        """Return total_joins, verified_users, and started_at for the given chat."""
        key = str(chat_id)
        try:
            resp = self._table.get_item(
                Key={"stat_key": key},
                ConsistentRead=False,
            )
            item: dict[str, Any] = resp.get("Item") or {}
            return {
                "total_joins": int(item.get("total_joins", 0)),
                "verified_users": int(item.get("verified_users", 0)),
                "started_at": item.get("started_at", "N/A"),
            }
        except ClientError as e:
            logger.exception(f"Failed to get stats: {e}")
            raise
