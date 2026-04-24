"""Atomic daily RPD counter for Gemini API, backed by DynamoDB.

Uses the shared stats table with key pattern ``GEMINI_RPD#<date_pt>``.
*date_pt* is the calendar date in ``America/Los_Angeles`` (US Pacific), matching
Google's RPD reset at local midnight. Items auto-expire via TTL after 48 hours.
The counter is atomic (single UpdateItem with ADD) so concurrent Lambda
invocations never double-count or drift.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from botocore.exceptions import ClientError
from core.config import GEMINI_RPD_LIMIT, STATS_TABLE_NAME
from core.logger import LoggerAdapter, get_logger
from services.repositories._common import get_dynamodb

logger = LoggerAdapter(get_logger(__name__), {})

# US Pacific calendar day (PST/PDT). Gemini RPD resets at local midnight per Google docs.
_PT = ZoneInfo("America/Los_Angeles")
_PK_PREFIX = "GEMINI_RPD"
_TTL_DELTA = timedelta(hours=48)


class RateLimitRepository:
    """Atomic RPD counter in the shared stats DynamoDB table.

    Key schema: ``stat_key = GEMINI_RPD#<date_pt>``
    (e.g. ``GEMINI_RPD#2026-04-07``).
    """

    def __init__(self) -> None:
        self.rpd_limit = GEMINI_RPD_LIMIT
        logger.info(
            "RateLimitRepository initialized",
            extra={"table": STATS_TABLE_NAME, "rpd_limit": self.rpd_limit},
        )

    @property
    def _table(self):
        return get_dynamodb().Table(STATS_TABLE_NAME)

    @staticmethod
    def _today_pt() -> str:
        """Calendar date in America/Los_Angeles (Gemini RPD daily reset)."""
        return datetime.now(_PT).strftime("%Y-%m-%d")

    def increment_and_check(self) -> tuple[int, bool]:
        """Atomically increment today's counter.

        Returns:
            ``(count, within_limit)`` — count after increment, and
            whether it is still within *rpd_limit*.
        """
        date_str = self._today_pt()
        stat_key = f"{_PK_PREFIX}#{date_str}"

        midnight_pt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=_PT)
        ttl_epoch = int((midnight_pt + _TTL_DELTA).timestamp())

        try:
            resp = self._table.update_item(
                Key={"stat_key": stat_key},
                UpdateExpression=("SET request_count" " = if_not_exists(request_count, :zero) + :inc," " #t = :ttl"),
                ExpressionAttributeNames={"#t": "ttl"},
                ExpressionAttributeValues={
                    ":inc": 1,
                    ":zero": 0,
                    ":ttl": ttl_epoch,
                },
                ReturnValues="UPDATED_NEW",
            )
        except ClientError:
            logger.exception("Failed to increment Gemini RPD counter")
            return 0, True

        count = int(resp["Attributes"]["request_count"])
        return count, count <= self.rpd_limit

    def get_today_count(self) -> int:
        """Read today's request count without incrementing (for RPD decisions)."""
        stat_key = f"{_PK_PREFIX}#{self._today_pt()}"
        try:
            resp = self._table.get_item(Key={"stat_key": stat_key}, ConsistentRead=True)
            item = resp.get("Item") or {}
            return int(item.get("request_count", 0))
        except ClientError:
            logger.exception("Failed to read Gemini RPD counter")
            return 0
        except (TypeError, ValueError):
            return 0
