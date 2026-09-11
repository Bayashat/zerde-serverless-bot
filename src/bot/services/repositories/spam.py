"""Durable moderation receipts, leases and exactly-once confirmed-ban counters.

Only this repository owns spam_case# rows in the existing stats table. A CLEAN
receipt is a decision about a source revision, never a replacement for that source.
"""

import hashlib
import json
import time
import uuid
from typing import Any

from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError
from core.config import STATS_TABLE_NAME
from services.repositories._common import get_dynamodb
from services.repositories.stats import _almaty_now_str

_PREFIX = "spam_case#"
_RETENTION_SECONDS = 30 * 86400
_LEASE_SECONDS = 330


class SpamLeaseBusyError(RuntimeError):
    """Another invocation owns this moderation operation; delivery must retry."""


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _conditional_failure(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def source_reference(body: dict[str, Any]) -> dict[str, Any] | None:
    raw = body.get("source_ref")
    if raw is None:
        return None
    if (
        not isinstance(raw, dict)
        or set(raw) != {"source_id", "source_version", "epoch"}
        or raw.get("source_id") != str(body["message_id"])
        or type(raw.get("source_version")) is not int
        or raw["source_version"] < 1
        or not isinstance(raw.get("epoch"), str)
        or not 1 <= len(raw["epoch"]) <= 128
    ):
        raise ValueError("Invalid versioned spam source reference")
    return dict(raw)


class SpamRepository:
    def __init__(self) -> None:
        self.table = get_dynamodb().Table(STATS_TABLE_NAME)
        self.client = self.table.meta.client

    def get(self, case_id: str) -> dict[str, Any]:
        return self.table.get_item(Key={"stat_key": _PREFIX + case_id}, ConsistentRead=True).get("Item") or {}

    def _create(self, case_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time())
        item = {
            "stat_key": _PREFIX + case_id,
            "case_id": case_id,
            "state": "pending",
            "created_at": now,
            "updated_at": now,
            "ttl": now + _RETENTION_SECONDS,
            **fields,
        }
        try:
            self.table.put_item(Item=item, ConditionExpression="attribute_not_exists(stat_key)")
            return item
        except ClientError as exc:
            if not _conditional_failure(exc):
                raise
        existing = self.get(case_id)
        if not existing:
            raise RuntimeError("Moderation receipt disappeared during creation")
        return existing

    def ensure_case(self, body: dict[str, Any]) -> dict[str, Any]:
        ref = source_reference(body)
        context = body.get("message_context") or {}
        fingerprint = _digest({"text": body["text"], "message_context": context})
        identity = [body["chat_id"], body["user_id"], body["message_id"], ref, fingerprint]
        return self._create(
            "decision#" + _digest(identity)[:32],
            {
                "kind": "spam_decision",
                "chat_id": str(body["chat_id"]),
                "user_id": int(body["user_id"]),
                "message_id": int(body["message_id"]),
                "input_hash": fingerprint,
                "source_ref": ref or {},
                "guest_bot": context.get("guest_bot") is True,
            },
        )

    def ensure_action(self, chat_id: int, user_id: int, message_id: int, *, permanent: bool, until_date: int) -> dict:
        return self._create(
            "action#" + _digest([chat_id, user_id, message_id, permanent])[:32],
            {
                "kind": "spam_action",
                "chat_id": str(chat_id),
                "user_id": user_id,
                "message_id": message_id,
                "permanent": permanent,
                "until_date": until_date,
            },
        )

    def claim(self, case_id: str) -> tuple[str, dict[str, Any]]:
        now = int(time.time())
        owner = uuid.uuid4().hex
        try:
            response = self.table.update_item(
                Key={"stat_key": _PREFIX + case_id},
                UpdateExpression="SET lease_owner = :owner, lease_until = :until",
                ConditionExpression=(
                    "attribute_exists(stat_key) AND " "(attribute_not_exists(lease_owner) OR lease_until < :now)"
                ),
                ExpressionAttributeValues={":owner": owner, ":until": now + _LEASE_SECONDS, ":now": now},
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if _conditional_failure(exc):
                raise SpamLeaseBusyError("Moderation operation is already running") from exc
            raise
        return owner, response["Attributes"]

    def update(self, case_id: str, owner: str, fields: dict[str, Any], *, remove_ttl: bool = False) -> None:
        fields = {**fields, "updated_at": int(time.time())}
        names = {f"#f{i}": key for i, key in enumerate(fields)}
        values = {f":v{i}": value for i, value in enumerate(fields.values())}
        expression = "SET " + ", ".join(f"#f{i} = :v{i}" for i in range(len(fields)))
        if remove_ttl:
            names["#ttl"] = "ttl"
            expression += " REMOVE #ttl"
        self.table.update_item(
            Key={"stat_key": _PREFIX + case_id},
            UpdateExpression=expression,
            ConditionExpression="lease_owner = :owner",
            ExpressionAttributeNames=names,
            ExpressionAttributeValues={**values, ":owner": owner},
        )

    def release(self, case_id: str, owner: str) -> None:
        try:
            self.table.update_item(
                Key={"stat_key": _PREFIX + case_id},
                UpdateExpression="REMOVE lease_owner, lease_until",
                ConditionExpression="lease_owner = :owner",
                ExpressionAttributeValues={":owner": owner},
            )
        except ClientError as exc:
            if not _conditional_failure(exc):
                raise

    def finish_clean(self, case: dict[str, Any], owner: str, *, reviewed: bool = False) -> None:
        pending = bool(case.get("source_ref")) and not case.get("guest_bot")
        self.update(
            case["case_id"],
            owner,
            {"state": "clean", "outbox_pending": pending, "reviewed": reviewed},
            remove_ttl=pending,
        )

    def confirm_ban(self, action_id: str, owner: str, chat_id: int) -> None:
        """Commit confirmed Telegram success and its counter in one transaction."""

        self.client.transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": self.table.name,
                        "Key": {"stat_key": _PREFIX + action_id},
                        "UpdateExpression": "SET #state = :banned, updated_at = :now REMOVE lease_owner, lease_until",
                        "ConditionExpression": "lease_owner = :owner AND #state <> :banned",
                        "ExpressionAttributeNames": {"#state": "state"},
                        "ExpressionAttributeValues": {":banned": "banned", ":now": int(time.time()), ":owner": owner},
                    }
                },
                {
                    "Update": {
                        "TableName": self.table.name,
                        "Key": {"stat_key": str(chat_id)},
                        "UpdateExpression": (
                            "SET spam_bans = if_not_exists(spam_bans, :zero) + :one, "
                            "started_at = if_not_exists(started_at, :started)"
                        ),
                        "ExpressionAttributeValues": {":zero": 0, ":one": 1, ":started": _almaty_now_str()},
                    }
                },
            ]
        )

    def list_clean_pending(self, *, limit: int = 100, cursor: dict | None = None) -> tuple[list[dict], dict | None]:
        kwargs: dict[str, Any] = {
            "FilterExpression": Attr("kind").eq("spam_decision") & Attr("outbox_pending").eq(True),
            "Limit": max(1, min(limit, 100)),
            "ConsistentRead": True,
        }
        if cursor:
            kwargs["ExclusiveStartKey"] = cursor
        response = self.table.scan(**kwargs)
        return response.get("Items") or [], response.get("LastEvaluatedKey")

    def acknowledge_clean(
        self,
        case_id: str,
        source_ref: dict,
        *,
        chat_id: int,
        user_id: int,
        message_id: int,
        outcome: str,
    ) -> None:
        if outcome not in {"INGESTED", "EXPIRED"}:
            raise ValueError("Unknown clean-receipt acknowledgement")
        self.table.update_item(
            Key={"stat_key": _PREFIX + case_id},
            UpdateExpression="SET outbox_pending = :false, recovery_outcome = :outcome, #ttl = :ttl",
            ConditionExpression=(
                "#state = :clean AND source_ref = :source_ref AND chat_id = :chat_id "
                "AND user_id = :user_id AND message_id = :message_id "
                "AND (outbox_pending = :true OR recovery_outcome = :outcome)"
            ),
            ExpressionAttributeNames={"#state": "state", "#ttl": "ttl"},
            ExpressionAttributeValues={
                ":false": False,
                ":outcome": outcome,
                ":ttl": int(time.time()) + _RETENTION_SECONDS,
                ":clean": "clean",
                ":source_ref": source_ref,
                ":chat_id": str(chat_id),
                ":user_id": user_id,
                ":message_id": message_id,
                ":true": True,
            },
        )
