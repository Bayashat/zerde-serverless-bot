"""Conservative daily Gemini admission counts in the shared stats table.

Uses the shared stats table with key pattern ``RATE#<scope>#<date_pt>``.
*date_pt* is the calendar date in ``America/Los_Angeles`` (US Pacific), matching
Google's RPD reset at local midnight. Items auto-expire via TTL after 48 hours.
Validated counters use conditional updates; uncertain writes do not grant a
permit or get refunded. Admissions are not provider requests or billed usage,
and separate application calls do not share an idempotency identity.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from botocore.exceptions import ClientError
from core.config import GEMINI_RPD_LIMIT, STATS_TABLE_NAME
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
}


def _valid_count(value) -> int | None:
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, Decimal) and value.is_finite() and value >= 0 and value == value.to_integral_value():
        return int(value)
    return None


def _known_conflict(error: ClientError) -> bool:
    response = error.response
    if not isinstance(response, dict):
        return False
    detail, metadata = response.get("Error"), response.get("ResponseMetadata")
    return (
        isinstance(detail, dict)
        and detail.get("Code") == "ConditionalCheckFailedException"
        and isinstance(metadata, dict)
        and type(metadata.get("RetryAttempts")) is int
        and metadata["RetryAttempts"] == 0
    )


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
        """CAS one admission; retain the original unavailable sentinel (0, True).

        All three consumers reject that sentinel before their provider calls.
        Valid exhausted admissions still increment and return (count, False).
        Only a known, unretried condition failure permits another CAS round.
        """
        resolved_scope = scope or self.scope
        date_str = self._today_pt()
        stat_key = self._stat_key(date_str, resolved_scope)

        midnight_pt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=_PT)
        ttl_epoch = int((midnight_pt + _TTL_DELTA).timestamp())
        limit = self._limit_for_scope(resolved_scope)
        key = {"stat_key": stat_key}

        def unavailable(reason):
            logger.warning("Gemini quota admission unavailable", extra={"scope": resolved_scope, "reason": reason})
            return 0, True

        try:
            table = self._table
        except ClientError:
            return unavailable("resource_error")
        for _ in range(3):
            try:
                response = table.get_item(Key=key, ConsistentRead=True)
            except ClientError:
                return unavailable("read_error")
            if not isinstance(response, dict):
                return unavailable("read_shape")
            previous = None
            if "Item" in response:
                item = response["Item"]
                if not isinstance(item, dict) or item.get("stat_key") != stat_key:
                    return unavailable("record_shape")
                previous = _valid_count(item.get("request_count"))
                if previous is None:
                    return unavailable("invalid_count")
            count = 1 if previous is None else previous + 1
            values = {":next": count, ":ttl": ttl_epoch}
            condition = "attribute_not_exists(stat_key)"
            if previous is not None:
                condition = "request_count = :previous"
                values[":previous"] = previous
            try:
                response = table.update_item(
                    Key=key,
                    UpdateExpression="SET request_count = :next, #t = :ttl",
                    ConditionExpression=condition,
                    ExpressionAttributeNames={"#t": "ttl"},
                    ExpressionAttributeValues=values,
                    ReturnValues="UPDATED_NEW",
                )
            except ClientError as exc:
                if _known_conflict(exc):
                    continue
                return unavailable("write_error")
            attrs = response.get("Attributes") if isinstance(response, dict) else None
            if not isinstance(attrs, dict) or _valid_count(attrs.get("request_count")) != count:
                return unavailable("write_response")
            return count, count <= limit
        return unavailable("contention")

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
