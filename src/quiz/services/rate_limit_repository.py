"""Conservative daily admission counter; not a provider invoice or send count."""

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import boto3
from botocore.exceptions import ClientError
from core.config import QUIZ_LLM_RPD, TABLE_NAME
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})
_PT = ZoneInfo("America/Los_Angeles")
_PK_PREFIX = "QUIZ_GEMINI_RPD"
_TTL_DELTA = timedelta(hours=48)


class QuizQuotaUnavailable(Exception):
    """Local admission is uncertain; never route this to another provider."""


def _count(value) -> int:
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, Decimal) and value.is_finite() and value >= 0 and value == value.to_integral_value():
        return int(value)
    raise QuizQuotaUnavailable("Invalid Quiz admission counter")


class QuizRateLimitRepository:
    """The single writer for the existing global Pacific-day Quiz counter."""

    def __init__(self) -> None:
        self._table = boto3.resource("dynamodb").Table(TABLE_NAME)
        self.rpd_limit: int = QUIZ_LLM_RPD
        logger.info("QuizRateLimitRepository initialized", extra={"table": TABLE_NAME, "rpd_limit": self.rpd_limit})

    @staticmethod
    def _today_pt() -> str:
        return datetime.now(_PT).strftime("%Y-%m-%d")

    def _read_count(self, key) -> int | None:
        try:
            response = self._table.get_item(Key=key, ConsistentRead=True)
        except Exception:
            raise QuizQuotaUnavailable("Quiz admission counter read unavailable") from None
        if not isinstance(response, dict):
            raise QuizQuotaUnavailable("Invalid Quiz admission read response")
        if "Item" not in response:
            return None
        item = response["Item"]
        if not isinstance(item, dict):
            raise QuizQuotaUnavailable("Invalid Quiz admission record")
        return _count(item.get("request_count"))

    def increment_and_check(self) -> tuple[int, bool]:
        """CAS one admission; unknown writes retain their liability without a permit."""
        date_str = self._today_pt()
        key = {"PK": f"{_PK_PREFIX}#{date_str}", "SK": "LATEST"}
        midnight_pt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=_PT)
        ttl_epoch = int((midnight_pt + _TTL_DELTA).timestamp())
        for _ in range(3):
            previous = self._read_count(key)
            count = 1 if previous is None else previous + 1
            values = {":next": count, ":ttl": ttl_epoch}
            condition = "attribute_not_exists(PK)"
            if previous is not None:
                condition = "request_count = :previous"
                values[":previous"] = previous
            try:
                response = self._table.update_item(
                    Key=key,
                    UpdateExpression="SET request_count = :next, #t = :ttl",
                    ConditionExpression=condition,
                    ExpressionAttributeNames={"#t": "ttl"},
                    ExpressionAttributeValues=values,
                    ReturnValues="UPDATED_NEW",
                )
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                    continue
                raise QuizQuotaUnavailable("Quiz admission counter write unavailable") from None
            except Exception:
                raise QuizQuotaUnavailable("Quiz admission counter write unavailable") from None
            attrs = response.get("Attributes") if isinstance(response, dict) else None
            if not isinstance(attrs, dict) or _count(attrs.get("request_count")) != count:
                raise QuizQuotaUnavailable("Invalid Quiz admission write response")
            return count, count <= self.rpd_limit
        raise QuizQuotaUnavailable("Quiz admission counter contention")

    def get_today_count(self) -> int:
        count = self._read_count({"PK": f"{_PK_PREFIX}#{self._today_pt()}", "SK": "LATEST"})
        return 0 if count is None else count
