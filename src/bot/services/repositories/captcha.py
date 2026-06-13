"""Pending captcha state in DynamoDB (reuses STATS_TABLE_NAME, ttl-backed)."""

import time
from typing import Any

from botocore.exceptions import ClientError
from core.config import CAPTCHA_TIMEOUT_SECONDS, STATS_TABLE_NAME
from core.logger import LoggerAdapter, get_logger
from services.repositories._common import get_dynamodb

logger = LoggerAdapter(get_logger(__name__), {})

_KEY_PREFIX = "captcha_pending#"
_STATUS_PENDING = "pending"
_STATUS_VERIFIED = "verified"
_STATE_TTL_BUFFER_SECONDS = 24 * 60 * 60


def _key(chat_id: int | str, user_id: int | str) -> str:
    return f"{_KEY_PREFIX}{chat_id}#{user_id}"


class CaptchaRepository:
    """Stores pending captcha challenges keyed by chat+user with TTL auto-expiry."""

    def __init__(self) -> None:
        pass

    @property
    def _table(self):
        return get_dynamodb().Table(STATS_TABLE_NAME)

    def save_pending(
        self,
        chat_id: int | str,
        user_id: int | str,
        expected: str,
        join_msg_id: int,
        verify_msg_id: int,
    ) -> None:
        now = int(time.time())
        expires_at = now + CAPTCHA_TIMEOUT_SECONDS
        ttl = expires_at + _STATE_TTL_BUFFER_SECONDS
        try:
            self._table.put_item(
                Item={
                    "stat_key": _key(chat_id, user_id),
                    "status": _STATUS_PENDING,
                    "expected": expected,
                    "join_msg_id": join_msg_id,
                    "verify_msg_id": verify_msg_id,
                    "attempts": 0,
                    "created_at": now,
                    "expires_at": expires_at,
                    "ttl": ttl,
                }
            )
        except ClientError as e:
            logger.exception("Failed to save pending captcha: %s", e)
            raise

    def _format_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": item.get("status", _STATUS_PENDING),
            "expected": item["expected"],
            "join_msg_id": int(item["join_msg_id"]),
            "verify_msg_id": int(item["verify_msg_id"]),
            "attempts": int(item.get("attempts", 0)),
            "wrong_msg_ids": [int(m) for m in item.get("wrong_msg_ids", [])],
            "created_at": int(item.get("created_at", 0)),
            "expires_at": int(item.get("expires_at", item.get("ttl", 0))),
            "ttl": int(item.get("ttl", 0)),
        }

    def get_challenge(self, chat_id: int | str, user_id: int | str) -> dict[str, Any] | None:
        """Return captcha state regardless of pending/verified status."""
        try:
            resp = self._table.get_item(
                Key={"stat_key": _key(chat_id, user_id)},
                ConsistentRead=True,
            )
            item = resp.get("Item")
            if not item:
                return None
            return self._format_item(item)
        except ClientError as e:
            logger.exception("Failed to get captcha challenge: %s", e)
            return None

    def get_pending(self, chat_id: int | str, user_id: int | str) -> dict[str, Any] | None:
        challenge = self.get_challenge(chat_id, user_id)
        if not challenge:
            return None
        if challenge.get("status") != _STATUS_PENDING:
            return None
        # Guard against expired challenges not yet enforced by the delayed timeout task.
        if int(challenge.get("expires_at", 0)) < int(time.time()):
            return None
        return challenge

    def mark_verified(self, chat_id: int | str, user_id: int | str) -> None:
        now = int(time.time())
        try:
            self._table.update_item(
                Key={"stat_key": _key(chat_id, user_id)},
                UpdateExpression="SET #status = :verified, verified_at = :now",
                ConditionExpression="attribute_exists(stat_key)",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":verified": _STATUS_VERIFIED, ":now": now},
            )
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                logger.warning("mark_verified: captcha entry no longer exists for user %s", user_id)
                return None
            logger.warning("Failed to mark captcha verified: %s", e)

    def append_wrong_message(self, chat_id: int | str, user_id: int | str, msg_id: int) -> None:
        """Append a wrong-answer message ID to the tracked list for later cleanup."""
        try:
            self._table.update_item(
                Key={"stat_key": _key(chat_id, user_id)},
                UpdateExpression="SET wrong_msg_ids = list_append(if_not_exists(wrong_msg_ids, :empty), :new_id)",
                ExpressionAttributeValues={":empty": [], ":new_id": [msg_id]},
            )
        except ClientError as e:
            logger.warning("Failed to append wrong message id: %s", e)

    def increment_attempts(self, chat_id: int | str, user_id: int | str) -> int:
        """Increment wrong-attempt counter, return new count."""
        try:
            resp = self._table.update_item(
                Key={"stat_key": _key(chat_id, user_id)},
                UpdateExpression="SET attempts = if_not_exists(attempts, :zero) + :inc",
                ConditionExpression="attribute_exists(stat_key)",
                ExpressionAttributeValues={":inc": 1, ":zero": 0},
                ReturnValues="UPDATED_NEW",
            )
            return int(resp["Attributes"].get("attempts", 1))
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                logger.warning("increment_attempts: captcha entry no longer exists for user %s", user_id)
                return 0
            logger.exception("Failed to increment attempts: %s", e)
            return 1

    def delete_pending(self, chat_id: int | str, user_id: int | str) -> None:
        try:
            self._table.delete_item(Key={"stat_key": _key(chat_id, user_id)})
        except ClientError as e:
            logger.warning("Failed to delete pending captcha: %s", e)
