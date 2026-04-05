"""DynamoDB repository for Quiz Lambda — writes quiz records and category metadata."""

import time
from datetime import datetime, timedelta, timezone
from typing import Any

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

    def get_last_category(self) -> str | None:
        """Read the last used quiz category from metadata."""
        try:
            resp = self._table.get_item(
                Key={"PK": "META#category", "SK": "LATEST"},
                ConsistentRead=False,
            )
            item = resp.get("Item")
            return item.get("category") if item else None
        except Exception as e:
            logger.error("Failed to get last category", extra={"error": str(e)})
            return None

    def save_last_category(self, category: str) -> None:
        """Write the current category as the latest."""
        today = datetime.now(_ALMATY_TZ).strftime("%Y-%m-%d")
        try:
            self._table.put_item(
                Item={
                    "PK": "META#category",
                    "SK": "LATEST",
                    "category": category,
                    "date": today,
                }
            )
        except Exception as e:
            logger.error("Failed to save last category", extra={"error": str(e)})

    def save_quiz_record(
        self,
        chat_id: str,
        question: dict[str, Any],
        category: str,
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
                    "question": question["question"],
                    "options": question["options"],
                    "correct_option_id": question["correct_option_id"],
                    "poll_id": str(poll_id),
                    "message_id": message_id,
                    "category": category,
                    "sent_at": now.isoformat(),
                    "ttl": ttl,
                }
            )
            logger.info("Quiz record saved", extra={"chat_id": chat_id, "date": today})
        except Exception as e:
            logger.error("Failed to save quiz record", extra={"chat_id": chat_id, "error": str(e)})
            raise
