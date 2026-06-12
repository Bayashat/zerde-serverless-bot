"""Atomic daily RPD counters for Gemini APIs, backed by DynamoDB.

Uses the shared stats table with key pattern ``RATE#<scope>#<date_pt>``.
*date_pt* is the calendar date in ``America/Los_Angeles`` (US Pacific), matching
Google's RPD reset at local midnight. Items auto-expire via TTL after 48 hours.
The counter is atomic (single UpdateItem with ADD) so concurrent Lambda
invocations never double-count or drift.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from botocore.exceptions import ClientError
from core.config import GEMINI_EMBEDDING_RPD_LIMIT, GEMINI_RPD_LIMIT, STATS_TABLE_NAME
from core.logger import LoggerAdapter, get_logger
from services.repositories._common import get_dynamodb

logger = LoggerAdapter(get_logger(__name__), {})

# US Pacific calendar day (PST/PDT). Gemini RPD resets at local midnight per Google docs.
_PT = ZoneInfo("America/Los_Angeles")
_PK_PREFIX = "RATE"
_TTL_DELTA = timedelta(hours=48)
_DEFAULT_SCOPE = "gemini_generate"
_SCOPE_LIMITS = {
    _DEFAULT_SCOPE: GEMINI_RPD_LIMIT,
    "gemini_embedding": GEMINI_EMBEDDING_RPD_LIMIT,
}


class RateLimitRepository:
    """Atomic RPD counter in the shared stats DynamoDB table.

    Key schema: ``stat_key = RATE#<scope>#<date_pt>``
    (e.g. ``RATE#gemini_generate#2026-04-07``).
    """

    def __init__(self, *, scope: str = _DEFAULT_SCOPE, rpd_limit: int | None = None) -> None:
        self.scope = scope or _DEFAULT_SCOPE
        default_limit = _SCOPE_LIMITS.get(self.scope, GEMINI_RPD_LIMIT)
        self.rpd_limit = int(rpd_limit if rpd_limit is not None else default_limit)
        logger.info(
            "RateLimitRepository initialized",
            extra={"table": STATS_TABLE_NAME, "scope": self.scope, "rpd_limit": self.rpd_limit},
        )

    @property
    def _table(self):
        return get_dynamodb().Table(STATS_TABLE_NAME)

    @staticmethod
    def _today_pt() -> str:
        """Calendar date in America/Los_Angeles (Gemini RPD daily reset)."""
        return datetime.now(_PT).strftime("%Y-%m-%d")

    def _limit_for_scope(self, scope: str) -> int:
        if scope == self.scope:
            return self.rpd_limit
        return int(_SCOPE_LIMITS.get(scope, GEMINI_RPD_LIMIT))

    def _stat_key(self, date_str: str, scope: str | None = None) -> str:
        return f"{_PK_PREFIX}#{scope or self.scope}#{date_str}"

    def increment_and_check(self, *, scope: str | None = None) -> tuple[int, bool]:
        """Atomically increment today's counter.

        Returns:
            ``(count, within_limit)`` — count after increment, and
            whether it is still within the scope's RPD limit.
        """
        resolved_scope = scope or self.scope
        date_str = self._today_pt()
        stat_key = self._stat_key(date_str, resolved_scope)

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
            logger.exception("Failed to increment Gemini RPD counter", extra={"scope": resolved_scope})
            return 0, True

        count = int(resp["Attributes"]["request_count"])
        limit = self._limit_for_scope(resolved_scope)
        return count, count <= limit

    def get_today_count(self, *, scope: str | None = None) -> int:
        """Read today's request count without incrementing (for RPD decisions)."""
        resolved_scope = scope or self.scope
        stat_key = self._stat_key(self._today_pt(), resolved_scope)
        try:
            resp = self._table.get_item(Key={"stat_key": stat_key}, ConsistentRead=True)
            item = resp.get("Item") or {}
            return int(item.get("request_count", 0))
        except ClientError:
            logger.exception("Failed to read Gemini RPD counter", extra={"scope": resolved_scope})
            return 0
        except (TypeError, ValueError):
            return 0
