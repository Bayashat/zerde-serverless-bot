"""Quiz score and streak repository for the Bot Lambda."""

from datetime import datetime, timedelta, timezone
from typing import Any

from botocore.exceptions import ClientError
from core.config import QUIZ_TABLE_NAME
from core.logger import LoggerAdapter, get_logger
from services.repositories._common import get_dynamodb

logger = LoggerAdapter(get_logger(__name__), {})

_ALMATY_TZ = timezone(timedelta(hours=5))


def _today_almaty() -> str:
    return datetime.now(_ALMATY_TZ).strftime("%Y-%m-%d")


def _yesterday_almaty() -> str:
    return (datetime.now(_ALMATY_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")


class QuizRepository:
    """Reads/writes quiz scores, streaks, and poll lookups via DynamoDB."""

    def __init__(self) -> None:
        self._table = get_dynamodb().Table(QUIZ_TABLE_NAME)
        logger.info("QuizRepository initialized", extra={"table": QUIZ_TABLE_NAME})

    def lookup_poll(self, poll_id: str) -> dict[str, Any] | None:
        """Look up a quiz record by poll_id using the GSI."""
        try:
            resp = self._table.query(
                IndexName="PollIdIndex",
                KeyConditionExpression="poll_id = :pid",
                ExpressionAttributeValues={":pid": str(poll_id)},
                Limit=1,
            )
            items = resp.get("Items", [])
            return items[0] if items else None
        except ClientError as e:
            logger.error("Failed to lookup poll", extra={"poll_id": poll_id, "error": str(e)})
            return None

    def get_user_score(self, chat_id: str, user_id: str) -> dict[str, Any] | None:
        """Get a user's score record for a chat."""
        try:
            resp = self._table.get_item(
                Key={"PK": f"SCORE#{chat_id}", "SK": f"USER#{user_id}"},
                ConsistentRead=False,
            )
            return resp.get("Item")
        except ClientError as e:
            logger.error("Failed to get user score", extra={"error": str(e)})
            return None

    def update_score_correct(self, chat_id: str, user_id: str, first_name: str) -> None:
        """Update user score for a correct answer with streak logic."""
        today = _today_almaty()
        yesterday = _yesterday_almaty()
        current = self.get_user_score(chat_id, user_id)

        if current and current.get("last_answered_date") == today:
            return  # Already answered today

        if current and current.get("last_correct_date") == today:
            return  # Already counted a correct answer today

        if current and current.get("last_correct_date") == yesterday:
            new_streak = current.get("current_streak", 0) + 1
        else:
            new_streak = 1

        best_streak = max(new_streak, (current or {}).get("best_streak", 0))
        new_score = (current or {}).get("total_score", 0) + 1

        try:
            self._table.put_item(
                Item={
                    "PK": f"SCORE#{chat_id}",
                    "SK": f"USER#{user_id}",
                    "total_score": new_score,
                    "current_streak": new_streak,
                    "best_streak": best_streak,
                    "last_correct_date": today,
                    "last_answered_date": today,
                    "first_name": first_name,
                }
            )
        except ClientError as e:
            logger.error("Failed to update score (correct)", extra={"error": str(e)})
            raise

    def update_score_wrong(self, chat_id: str, user_id: str, first_name: str) -> None:
        """Update user record for a wrong answer — reset streak."""
        today = _today_almaty()
        current = self.get_user_score(chat_id, user_id)

        if current and current.get("last_answered_date") == today:
            return  # Already answered today

        try:
            self._table.put_item(
                Item={
                    "PK": f"SCORE#{chat_id}",
                    "SK": f"USER#{user_id}",
                    "total_score": (current or {}).get("total_score", 0),
                    "current_streak": 0,
                    "best_streak": (current or {}).get("best_streak", 0),
                    "last_correct_date": (current or {}).get("last_correct_date", ""),
                    "last_answered_date": today,
                    "first_name": first_name,
                }
            )
        except ClientError as e:
            logger.error("Failed to update score (wrong)", extra={"error": str(e)})
            raise

    def get_leaderboard(self, chat_id: str) -> list[dict[str, Any]]:
        """Get all user scores for a chat, sorted by total_score descending."""
        try:
            resp = self._table.query(
                KeyConditionExpression="PK = :pk",
                ExpressionAttributeValues={":pk": f"SCORE#{chat_id}"},
            )
            items = resp.get("Items", [])
            return sorted(items, key=lambda x: x.get("total_score", 0), reverse=True)
        except ClientError as e:
            logger.error("Failed to get leaderboard", extra={"error": str(e)})
            return []
