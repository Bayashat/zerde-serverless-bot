"""Atomic daily RPD counter for Quiz Gemini usage (global across all chats)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import boto3
from botocore.exceptions import ClientError
from core.config import QUIZ_LLM_RPD, TABLE_NAME
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

_PT = ZoneInfo("America/Los_Angeles")
_PK_PREFIX = "QUIZ_GEMINI_RPD"
_TTL_DELTA = timedelta(hours=48)


class QuizRateLimitRepository:
    """DynamoDB-backed daily counter for quiz Gemini requests."""

    def __init__(self) -> None:
        self._table = boto3.resource("dynamodb").Table(TABLE_NAME)
        self.rpd_limit: int = QUIZ_LLM_RPD
        logger.info(
            "QuizRateLimitRepository initialized",
            extra={"table": TABLE_NAME, "rpd_limit": self.rpd_limit},
        )

    @staticmethod
    def _today_pt() -> str:
        """US Pacific calendar day, matching Gemini daily reset."""
        return datetime.now(_PT).strftime("%Y-%m-%d")

    def increment_and_check(self) -> tuple[int, bool]:
        """Atomically increment today's counter and return (count, within_limit)."""
        date_str = self._today_pt()
        stat_key = f"{_PK_PREFIX}#{date_str}"

        midnight_pt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=_PT)
        ttl_epoch = int((midnight_pt + _TTL_DELTA).timestamp())

        try:
            resp = self._table.update_item(
                Key={"PK": stat_key, "SK": "LATEST"},
                UpdateExpression="SET request_count = if_not_exists(request_count, :zero) + :inc, #t = :ttl",
                ExpressionAttributeNames={"#t": "ttl"},
                ExpressionAttributeValues={":inc": 1, ":zero": 0, ":ttl": ttl_epoch},
                ReturnValues="UPDATED_NEW",
            )
        except ClientError:
            logger.exception("Failed to increment quiz Gemini RPD counter")
            return 0, True

        count = int(resp["Attributes"]["request_count"])
        return count, count <= self.rpd_limit

    def get_today_count(self) -> int:
        """Read today's request count without incrementing."""
        stat_key = f"{_PK_PREFIX}#{self._today_pt()}"
        try:
            resp = self._table.get_item(Key={"PK": stat_key, "SK": "LATEST"}, ConsistentRead=True)
            item = resp.get("Item") or {}
            return int(item.get("request_count", 0))
        except ClientError:
            logger.exception("Failed to read quiz Gemini RPD counter")
            return 0
        except (TypeError, ValueError):
            return 0
