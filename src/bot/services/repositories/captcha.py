"""Generation-scoped captcha decisions and recoverable Telegram actions.

The stats table remains the only state owner. Conditional writes serialize a
challenge's decision, and a bounded lease fences a later join while an older
invocation may still be calling Telegram. Terminal rows are retained beyond the
14-day DLQ window instead of being deleted by a delayed timeout.
"""

import time
from typing import Any
from uuid import uuid4

from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError
from core.config import CAPTCHA_TIMEOUT_SECONDS, STATS_TABLE_NAME
from services.repositories._common import get_dynamodb

CAPTCHA_LEASE_SECONDS = 360  # Longer than the Bot Lambda's 300-second timeout.
_RETENTION_SECONDS = 15 * 24 * 60 * 60
TERMINAL_STATUSES = {"verified", "rejected", "cancelled"}


class CaptchaRetryRequiredError(RuntimeError):
    """Dependency failure or concurrent work requiring webhook/SQS redelivery."""


class CaptchaBusyError(CaptchaRetryRequiredError):
    def __init__(self, retry_after: int = CAPTCHA_LEASE_SECONDS) -> None:
        super().__init__("Captcha operation is already in progress")
        self.retry_after = max(1, retry_after)


def _key(chat_id: int | str, user_id: int | str) -> dict[str, str]:
    return {"stat_key": f"captcha_pending#{chat_id}#{user_id}"}


def _conditional_failure(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def action_completed(challenge: dict[str, Any]) -> bool:
    # Old verified rows were written only AFTER Telegram unrestriction.
    return bool(challenge.get("action_done", challenge.get("status") == "verified" and "generation" not in challenge))


def _snapshot_condition(challenge: dict[str, Any]):
    condition = Attr("join_msg_id").eq(challenge["join_msg_id"])
    for field in ("generation", "revision"):
        condition &= Attr(field).eq(challenge[field]) if field in challenge else Attr(field).not_exists()
    # Legacy records have no generation; both Telegram anchors are mandatory.
    if "generation" not in challenge:
        condition &= Attr("verify_msg_id").eq(challenge["verify_msg_id"])
    return condition


class CaptchaRepository:
    @property
    def _table(self):
        return get_dynamodb().Table(STATS_TABLE_NAME)

    def get_challenge(self, chat_id: int | str, user_id: int | str) -> dict[str, Any] | None:
        """Strong read. Service failures are never represented as NotFound."""
        return self._table.get_item(Key=_key(chat_id, user_id), ConsistentRead=True).get("Item")

    def get_pending(self, chat_id: int | str, user_id: int | str) -> dict[str, Any] | None:
        """Route expired/incomplete challenges to captcha, never into other flows."""
        item = self.get_challenge(chat_id, user_id)
        if not item or action_completed(item):
            return None
        return item

    def prepare(self, chat_id: int | str, user_id: int | str, join_msg_id: int) -> dict[str, Any] | None:
        """Persist a generation before any restriction/send; replays reuse it."""
        now = int(time.time())
        old = self.get_challenge(chat_id, user_id)
        if old and int(old["join_msg_id"]) >= join_msg_id:
            return old if int(old["join_msg_id"]) == join_msg_id else None
        if old and int(old.get("lease_until", 0)) > now:
            raise CaptchaBusyError(int(old["lease_until"]) - now)
        item = {
            **_key(chat_id, user_id),
            "generation": uuid4().hex,
            "revision": 0,
            "status": "preparing",
            "join_msg_id": join_msg_id,
            "verify_msg_id": 0,
            "attempts": 0,
            "handled_message_ids": [],
            "wrong_msg_ids": [],
            "created_at": now,
            "expires_at": now + CAPTCHA_TIMEOUT_SECONDS,
            "ttl": now + CAPTCHA_TIMEOUT_SECONDS + _RETENTION_SECONDS,
            "action_done": False,
        }
        condition = Attr("stat_key").not_exists()
        if old:
            condition = _snapshot_condition(old) & (Attr("lease_until").not_exists() | Attr("lease_until").lte(now))
        try:
            self._table.put_item(Item=item, ConditionExpression=condition)
        except ClientError as exc:
            if _conditional_failure(exc):
                raise CaptchaBusyError() from exc
            raise
        return item

    def acquire(self, challenge: dict[str, Any]) -> dict[str, Any]:
        """Claim the exact snapshot, upgrading legacy identity only under CAS."""
        now = int(time.time())
        condition = _snapshot_condition(challenge) & (Attr("lease_until").not_exists() | Attr("lease_until").lte(now))
        try:
            response = self._table.update_item(
                Key={"stat_key": challenge["stat_key"]},
                UpdateExpression=(
                    "SET lease_owner = :owner, lease_until = :until, "
                    "generation = if_not_exists(generation, :generation), "
                    "revision = if_not_exists(revision, :zero), "
                    "action_done = if_not_exists(action_done, :done), "
                    "#status = if_not_exists(#status, :pending)"
                ),
                ConditionExpression=condition,
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":owner": uuid4().hex,
                    ":until": now + CAPTCHA_LEASE_SECONDS,
                    ":generation": uuid4().hex,
                    ":zero": 0,
                    ":done": action_completed(challenge),
                    ":pending": "pending",
                },
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if _conditional_failure(exc):
                raise CaptchaBusyError() from exc
            raise
        return response["Attributes"]

    def save(self, challenge: dict[str, Any], **changes: Any) -> dict[str, Any]:
        """CAS the decision/state while the same invocation owns the live lease."""
        status = challenge.get("status", "pending")
        next_status = changes.get("status", status)
        transitions = {
            "preparing": {"creating", "cancelled"},
            "creating": {"pending", "cancelled"},
            "pending": {"verified", "rejected"},
        }
        if next_status != status and next_status not in transitions.get(status, set()):
            raise ValueError("Captcha decision is immutable")
        now = int(time.time())
        item = {**challenge, **changes, "revision": int(challenge.get("revision", 0)) + 1}
        item["ttl"] = max(int(item.get("ttl", 0)), now + _RETENTION_SECONDS)
        condition = (
            _snapshot_condition(challenge)
            & Attr("lease_owner").eq(challenge["lease_owner"])
            & Attr("lease_until").gt(now)
        )
        try:
            self._table.put_item(Item=item, ConditionExpression=condition)
        except ClientError as exc:
            if _conditional_failure(exc):
                raise CaptchaBusyError() from exc
            raise
        return item

    def assert_owned(self, challenge: dict[str, Any]) -> None:
        """Final fence immediately before external actions; raises on stale work."""
        actual = self._table.get_item(Key={"stat_key": challenge["stat_key"]}, ConsistentRead=True).get("Item")
        if (
            not actual
            or actual.get("generation") != challenge.get("generation")
            or actual.get("revision") != challenge.get("revision")
            or actual.get("lease_owner") != challenge.get("lease_owner")
            or int(actual.get("lease_until", 0)) <= int(time.time())
        ):
            raise CaptchaBusyError()

    def release(self, challenge: dict[str, Any]) -> None:
        """Never clear a different generation's lease, including after rejoin."""
        try:
            self._table.update_item(
                Key={"stat_key": challenge["stat_key"]},
                UpdateExpression="REMOVE lease_owner, lease_until",
                ConditionExpression=(
                    Attr("generation").eq(challenge["generation"]) & Attr("lease_owner").eq(challenge["lease_owner"])
                ),
            )
        except ClientError as exc:
            if not _conditional_failure(exc):
                raise
