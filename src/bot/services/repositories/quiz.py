"""Quiz score and streak repository for the Bot Lambda."""

from datetime import datetime, timedelta, timezone
from typing import Any

from boto3.dynamodb.conditions import Key
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
        logger.info("QuizRepository initialized", extra={"table": QUIZ_TABLE_NAME})

    @property
    def _table(self):
        return get_dynamodb().Table(QUIZ_TABLE_NAME)

    def lookup_poll(self, poll_id: str) -> dict[str, Any] | None:
        """Look up a quiz record by poll_id using the GSI."""
        try:
            resp = self._table.query(
                IndexName="PollIdIndex",
                KeyConditionExpression=Key("poll_id").eq(str(poll_id)),
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

    def update_score_correct(self, chat_id: str, user_id: str, first_name: str, points: int = 1) -> None:
        """Update user score for a correct answer with streak logic.

        Atomic conditional write prevents double-counting on duplicate poll_answer events.
        """
        today = _today_almaty()
        yesterday = _yesterday_almaty()
        current = self.get_user_score(chat_id, user_id)

        if current and current.get("last_correct_date") == yesterday:
            new_streak = int(current.get("current_streak", 0)) + 1
        else:
            new_streak = 1
        best_streak = max(new_streak, int((current or {}).get("best_streak", 0)))

        try:
            self._table.update_item(
                Key={"PK": f"SCORE#{chat_id}", "SK": f"USER#{user_id}"},
                UpdateExpression=(
                    "SET total_score = if_not_exists(total_score, :zero) + :pts,"
                    "    week_score = if_not_exists(week_score, :zero) + :pts,"
                    "    current_streak = :streak,"
                    "    best_streak = :best,"
                    "    last_correct_date = :today,"
                    "    last_answered_date = :today,"
                    "    first_name = :name"
                ),
                ConditionExpression=("attribute_not_exists(last_answered_date) OR last_answered_date <> :today"),
                ExpressionAttributeValues={
                    ":zero": 0,
                    ":pts": points,
                    ":streak": new_streak,
                    ":best": best_streak,
                    ":today": today,
                    ":name": first_name,
                },
            )
            logger.info("Correct answer recorded", extra={"user_id": user_id, "chat_id": chat_id, "points": points})
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info("Duplicate poll_answer ignored", extra={"user_id": user_id, "chat_id": chat_id})
                return
            logger.error("Failed to update score (correct)", extra={"error": str(e)})
            raise

    def update_score_wrong(self, chat_id: str, user_id: str, first_name: str) -> None:
        """Update user record for a wrong answer — reset streak.

        Uses if_not_exists to avoid a pre-read; conditional write blocks duplicates.
        """
        today = _today_almaty()
        try:
            self._table.update_item(
                Key={"PK": f"SCORE#{chat_id}", "SK": f"USER#{user_id}"},
                UpdateExpression=(
                    "SET total_score = if_not_exists(total_score, :zero),"
                    "    week_score = if_not_exists(week_score, :zero),"
                    "    current_streak = :zero,"
                    "    best_streak = if_not_exists(best_streak, :zero),"
                    "    last_answered_date = :today,"
                    "    first_name = :name,"
                    "    last_correct_date = if_not_exists(last_correct_date, :empty)"
                ),
                ConditionExpression=("attribute_not_exists(last_answered_date) OR last_answered_date <> :today"),
                ExpressionAttributeValues={
                    ":zero": 0,
                    ":today": today,
                    ":name": first_name,
                    ":empty": "",
                },
            )
            logger.info("Wrong answer recorded", extra={"user_id": user_id, "chat_id": chat_id})
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info("Duplicate poll_answer ignored", extra={"user_id": user_id, "chat_id": chat_id})
                return
            logger.error("Failed to update score (wrong)", extra={"error": str(e)})
            raise

    def get_leaderboard(self, chat_id: str) -> list[dict[str, Any]]:
        """Get all user scores for a chat, sorted by week_score descending."""
        try:
            resp = self._table.query(
                KeyConditionExpression=Key("PK").eq(f"SCORE#{chat_id}"),
            )
            items = resp.get("Items", [])
            return sorted(items, key=lambda x: x.get("week_score", 0), reverse=True)
        except ClientError as e:
            logger.error("Failed to get leaderboard", extra={"error": str(e)})
            return []
