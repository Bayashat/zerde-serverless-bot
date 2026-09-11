"""Quiz score and streak repository for the Bot Lambda."""

import time
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from core.config import QUIZ_TABLE_NAME
from core.logger import LoggerAdapter, get_logger
from services.repositories._common import get_dynamodb
from services.repositories._quiz_answers import AnswerState

logger = LoggerAdapter(get_logger(__name__), {})


class QuizRepository(AnswerState):
    """Reads/writes quiz scores, streaks, and poll lookups via DynamoDB."""

    def __init__(self) -> None:
        logger.info("QuizRepository initialized", extra={"table": QUIZ_TABLE_NAME})

    @property
    def _table(self):
        return get_dynamodb().Table(QUIZ_TABLE_NAME)

    def lookup_poll(self, poll_id: str) -> dict[str, Any] | None:
        """Strong primary lookup for new polls; a legacy GSI miss stays retryable."""

        def active(item):
            try:
                return not isinstance(item["ttl"], bool) and int(item["ttl"]) > int(time.time())
            except (KeyError, TypeError, ValueError):
                return False

        item = self._answer_read({"PK": f"POLL#{poll_id}", "SK": "META"})
        if item:
            return item if active(item) else None
        kwargs = {"IndexName": "PollIdIndex", "KeyConditionExpression": Key("poll_id").eq(str(poll_id))}
        while True:
            response = self._table.query(**kwargs)
            for candidate in response.get("Items", []):
                if str(candidate.get("PK", "")).startswith("QUIZ#") and active(candidate):
                    return candidate
            if not response.get("LastEvaluatedKey"):
                return None
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    def get_user_score(self, chat_id: str, user_id: str) -> dict[str, Any] | None:
        """Read score strongly; a dependency failure is never a missing score."""
        return self._answer_read({"PK": f"SCORE#{chat_id}", "SK": f"USER#{user_id}"}) or None

    def get_leaderboard(self, chat_id: str) -> list[dict[str, Any]]:
        """Get all user scores for a chat, sorted by week_score descending."""
        try:
            query_kwargs: dict = {"KeyConditionExpression": Key("PK").eq(f"SCORE#{chat_id}")}
            items: list[dict[str, Any]] = []
            while True:
                resp = self._table.query(**query_kwargs)
                items.extend(resp.get("Items", []))
                last_key = resp.get("LastEvaluatedKey")
                if not last_key:
                    break
                query_kwargs["ExclusiveStartKey"] = last_key
            return sorted(items, key=lambda x: x.get("week_score", 0), reverse=True)
        except ClientError as e:
            logger.error("Failed to get leaderboard", extra={"error": str(e)})
            return []
