"""DynamoDB repository for Quiz Lambda — writes quiz records and category metadata."""

import time
from datetime import datetime, timedelta, timezone

import boto3
from core.config import QUIZ_TABLE_NAME
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

_ALMATY_TZ = timezone(timedelta(hours=5))
_TTL_DAYS = 90


class QuizRepository:
    """Writes daily quiz records and category metadata to DynamoDB."""

    def __init__(self) -> None:
        self._table = boto3.resource("dynamodb").Table(QUIZ_TABLE_NAME)
        logger.info("QuizRepository initialized", extra={"table": QUIZ_TABLE_NAME})

    def get_category_queue(self) -> list[str]:
        """Read the remaining category queue from metadata.

        Backward compatible: returns [] if item is missing or uses old format.
        """
        try:
            resp = self._table.get_item(
                Key={"PK": "META#category", "SK": "LATEST"},
                ConsistentRead=False,
            )
            item = resp.get("Item")
            if item and "remaining" in item:
                return list(item["remaining"])
            return []
        except Exception as e:
            logger.error("Failed to get category queue", extra={"error": str(e)})
            return []

    def save_category_queue(self, remaining: list[str], used_category: str) -> None:
        """Write the updated category queue and last-used category."""
        today = datetime.now(_ALMATY_TZ).strftime("%Y-%m-%d")
        try:
            self._table.put_item(
                Item={
                    "PK": "META#category",
                    "SK": "LATEST",
                    "remaining": remaining,
                    "category": used_category,
                    "date": today,
                }
            )
        except Exception as e:
            logger.error("Failed to save category queue", extra={"error": str(e)})

    def save_quiz_record(
        self,
        chat_id: str,
        question: str,
        options: list[str],
        correct_option_id: int,
        explanation: str | None,
        category: str,
        lang: str,
        poll_id: str,
        message_id: int,
    ) -> None:
        """Write a daily quiz record for a chat."""
        now = datetime.now(_ALMATY_TZ)
        today = now.strftime("%Y-%m-%d")
        ttl = int(time.time()) + (_TTL_DAYS * 86400)

        try:
            self._table.put_item(
                Item={
                    "PK": f"QUIZ#{chat_id}",
                    "SK": f"DATE#{today}",
                    "question": question,
                    "options": options,
                    "correct_option_id": correct_option_id,
                    "explanation": explanation,
                    "category": category,
                    "lang": lang,
                    "poll_id": str(poll_id),
                    "message_id": message_id,
                    "sent_at": now.isoformat(),
                    "ttl": ttl,
                }
            )
            logger.info("Quiz record saved", extra={"chat_id": chat_id, "date": today})
        except Exception as e:
            logger.error("Failed to save quiz record", extra={"chat_id": chat_id, "error": str(e)})
            raise
