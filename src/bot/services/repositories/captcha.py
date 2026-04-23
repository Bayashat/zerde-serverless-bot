"""Pending captcha state in DynamoDB (reuses STATS_TABLE_NAME, ttl-backed)."""

import time
from typing import Any

from botocore.exceptions import ClientError
from core.config import CAPTCHA_TIMEOUT_SECONDS, STATS_TABLE_NAME
from core.logger import LoggerAdapter, get_logger
from services.repositories._common import get_dynamodb

logger = LoggerAdapter(get_logger(__name__), {})

_KEY_PREFIX = "captcha_pending#"


def _key(chat_id: int | str, user_id: int | str) -> str:
    return f"{_KEY_PREFIX}{chat_id}#{user_id}"


class CaptchaRepository:
    """Stores pending captcha challenges keyed by chat+user with TTL auto-expiry."""

    def __init__(self) -> None:
        self._table = get_dynamodb().Table(STATS_TABLE_NAME)

    def save_pending(
        self,
        chat_id: int | str,
        user_id: int | str,
        expected: str,
        join_msg_id: int,
        verify_msg_id: int,
    ) -> None:
        ttl = int(time.time()) + CAPTCHA_TIMEOUT_SECONDS + 60  # grace buffer
        try:
            self._table.put_item(
                Item={
                    "stat_key": _key(chat_id, user_id),
                    "expected": expected,
                    "join_msg_id": join_msg_id,
                    "verify_msg_id": verify_msg_id,
                    "attempts": 0,
                    "ttl": ttl,
                }
            )
        except ClientError as e:
            logger.exception("Failed to save pending captcha: %s", e)
            raise

    def get_pending(self, chat_id: int | str, user_id: int | str) -> dict[str, Any] | None:
        try:
            resp = self._table.get_item(
                Key={"stat_key": _key(chat_id, user_id)},
                ConsistentRead=True,
            )
            item = resp.get("Item")
            if not item:
                return None
            # Guard against expired items not yet removed by DynamoDB TTL sweep
            if int(item.get("ttl", 0)) < int(time.time()):
                return None
            return {
                "expected": item["expected"],
                "join_msg_id": int(item["join_msg_id"]),
                "verify_msg_id": int(item["verify_msg_id"]),
                "attempts": int(item.get("attempts", 0)),
            }
        except ClientError as e:
            logger.exception("Failed to get pending captcha: %s", e)
            return None

    def increment_attempts(self, chat_id: int | str, user_id: int | str) -> int:
        """Increment wrong-attempt counter, return new count."""
        try:
            resp = self._table.update_item(
                Key={"stat_key": _key(chat_id, user_id)},
                UpdateExpression="SET attempts = if_not_exists(attempts, :zero) + :inc",
                ExpressionAttributeValues={":inc": 1, ":zero": 0},
                ReturnValues="UPDATED_NEW",
            )
            return int(resp["Attributes"].get("attempts", 1))
        except ClientError as e:
            logger.exception("Failed to increment attempts: %s", e)
            return 1

    def delete_pending(self, chat_id: int | str, user_id: int | str) -> None:
        try:
            self._table.delete_item(Key={"stat_key": _key(chat_id, user_id)})
        except ClientError as e:
            logger.warning("Failed to delete pending captcha: %s", e)
