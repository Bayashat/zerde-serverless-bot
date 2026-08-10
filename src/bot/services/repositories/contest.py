"""DynamoDB truth owner for linked-channel contests."""

from __future__ import annotations

import time
from collections.abc import Iterator
from enum import StrEnum
from typing import Any

from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError
from core.config import MEMORY_TABLE_NAME
from services.repositories._common import get_dynamodb

_SECONDS_PER_DAY = 24 * 60 * 60
CONTEST_RETENTION_DAYS = 30
_TTL_OUTBOX_PK = "CONTEST_TTL_OUTBOX"


class RegistrationResult(StrEnum):
    """Outcome of one participant registration transaction."""

    REGISTERED = "registered"
    REPLAY = "replay"
    DUPLICATE = "duplicate"
    CLOSED = "closed"
    MISSING = "missing"


class ContestRepository:
    """Store contest lifecycle and participants in the existing memory table."""

    def __init__(self, table_name: str | None = None):
        table_name = table_name or MEMORY_TABLE_NAME
        if not table_name:
            raise ValueError("MEMORY_TABLE_NAME must be set")
        self.table = get_dynamodb().Table(table_name)
        self.table_name = self.table.name
        self.client = self.table.meta.client
        self._serializer = TypeSerializer()

    @staticmethod
    def _chat_pk(chat_id: int | str) -> str:
        return f"CHAT#{chat_id}"

    @staticmethod
    def _contest_prefix(root_message_id: int | str) -> str:
        return f"CONTEST#{int(root_message_id):013d}#"

    @classmethod
    def _meta_sk(cls, root_message_id: int | str) -> str:
        return f"{cls._contest_prefix(root_message_id)}META"

    @classmethod
    def _participant_prefix(cls, root_message_id: int | str) -> str:
        return f"{cls._contest_prefix(root_message_id)}PARTICIPANT#"

    @classmethod
    def _participant_sk(cls, root_message_id: int | str, user_id: int | str) -> str:
        return f"{cls._participant_prefix(root_message_id)}{int(user_id):020d}"

    @staticmethod
    def _rule_anchor_sk(rules_message_id: int | str) -> str:
        return f"CONTEST_RULE#{int(rules_message_id):013d}"

    @staticmethod
    def _ttl_outbox_key(chat_id: int | str, root_message_id: int | str) -> dict[str, str]:
        return {
            "pk": _TTL_OUTBOX_PK,
            "sk": f"CHAT#{chat_id}#ROOT#{int(root_message_id):013d}",
        }

    @classmethod
    def _ttl_outbox_item(
        cls,
        chat_id: int | str,
        root_message_id: int,
        *,
        expires_at: int,
        created_at: int,
    ) -> dict[str, Any]:
        return {
            **cls._ttl_outbox_key(chat_id, root_message_id),
            "kind": "contest_ttl_outbox",
            "chat_id": str(chat_id),
            "root_message_id": int(root_message_id),
            "expires_at": int(expires_at),
            "created_at": int(created_at),
        }

    @staticmethod
    def _expiry(now: int) -> int:
        return int(now) + CONTEST_RETENTION_DAYS * _SECONDS_PER_DAY

    def _serialize_map(self, value: dict[str, Any]) -> dict[str, Any]:
        return {key: self._serializer.serialize(item) for key, item in value.items() if item is not None}

    @staticmethod
    def _is_condition_failure(exc: ClientError) -> bool:
        code = exc.response.get("Error", {}).get("Code")
        if code == "ConditionalCheckFailedException":
            return True
        if code != "TransactionCanceledException":
            return False
        reasons = exc.response.get("CancellationReasons")
        if not isinstance(reasons, list) or not reasons:
            return False
        reason_codes = {str(reason.get("Code") or "None") for reason in reasons if isinstance(reason, dict)}
        return "ConditionalCheckFailed" in reason_codes and reason_codes <= {
            "None",
            "ConditionalCheckFailed",
        }

    def create_contest(
        self,
        *,
        chat_id: int | str,
        root_message_id: int,
        source_channel_id: int | str,
        source_channel_title: str | None,
        source_channel_username: str | None,
        source_channel_post_id: int | None,
        created_at: int | None = None,
    ) -> bool:
        """Create one fail-closed ``CREATING`` contest for a mirrored root."""
        now = int(created_at or time.time())
        item: dict[str, Any] = {
            "pk": self._chat_pk(chat_id),
            "sk": self._meta_sk(root_message_id),
            "kind": "contest",
            "chat_id": str(chat_id),
            "root_message_id": int(root_message_id),
            "source_channel_id": str(source_channel_id),
            "status": "CREATING",
            "participant_count": 0,
            "draw_count": 0,
            "winner_user_ids": [],
            "winners": [],
            "created_at": now,
            "updated_at": now,
        }
        if source_channel_title:
            item["source_channel_title"] = str(source_channel_title)[:200]
        if source_channel_username:
            item["source_channel_username"] = str(source_channel_username)[:100]
        if source_channel_post_id is not None:
            item["source_channel_post_id"] = int(source_channel_post_id)
        try:
            self.table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
            return True
        except ClientError as exc:
            if self._is_condition_failure(exc):
                return False
            raise

    def activate_contest(
        self,
        chat_id: int | str,
        root_message_id: int,
        rules_message_id: int,
        *,
        attempt_id: str,
        now: int | None = None,
    ) -> bool:
        """Attach the rules anchor and atomically transition ``CREATING -> OPEN``."""
        now = int(now or time.time())
        pk = self._chat_pk(chat_id)
        meta_key = {"pk": pk, "sk": self._meta_sk(root_message_id)}
        alias = {
            "pk": pk,
            "sk": self._rule_anchor_sk(rules_message_id),
            "kind": "contest_rule_anchor",
            "chat_id": str(chat_id),
            "root_message_id": int(root_message_id),
            "rules_message_id": int(rules_message_id),
            "created_at": now,
        }
        try:
            self.client.transact_write_items(
                TransactItems=[
                    {
                        "Update": {
                            "TableName": self.table_name,
                            "Key": self._serialize_map(meta_key),
                            "UpdateExpression": (
                                "SET #status = :open, rules_message_id = :rules, updated_at = :now "
                                "REMOVE creation_attempt_id, creation_started_at"
                            ),
                            "ConditionExpression": ("#status = :creating AND creation_attempt_id = :attempt"),
                            "ExpressionAttributeNames": {"#status": "status"},
                            "ExpressionAttributeValues": self._serialize_map(
                                {
                                    ":open": "OPEN",
                                    ":creating": "CREATING",
                                    ":attempt": str(attempt_id),
                                    ":rules": rules_message_id,
                                    ":now": now,
                                }
                            ),
                        }
                    },
                    {
                        "Put": {
                            "TableName": self.table_name,
                            "Item": self._serialize_map(alias),
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                ]
            )
            return True
        except ClientError as exc:
            if not self._is_condition_failure(exc):
                raise
            current = self.get_contest(chat_id, root_message_id, consistent=True)
            return bool(
                current
                and current.get("status") == "OPEN"
                and int(current.get("rules_message_id") or 0) == int(rules_message_id)
            )

    def fail_creation(
        self,
        chat_id: int | str,
        root_message_id: int,
        *,
        attempt_id: str,
        now: int | None = None,
    ) -> bool:
        """Close an unannounced contest so it can never accept participants."""
        now = int(now or time.time())
        expires_at = self._expiry(now)
        try:
            self.table.update_item(
                Key={"pk": self._chat_pk(chat_id), "sk": self._meta_sk(root_message_id)},
                UpdateExpression=(
                    "SET #status = :failed, failed_at = :now, updated_at = :now, "
                    "expires_at = :expires, #ttl = :expires"
                ),
                ConditionExpression=("#status = :creating AND creation_attempt_id = :attempt"),
                ExpressionAttributeNames={"#status": "status", "#ttl": "ttl"},
                ExpressionAttributeValues={
                    ":failed": "CREATION_FAILED",
                    ":creating": "CREATING",
                    ":attempt": str(attempt_id),
                    ":now": now,
                    ":expires": expires_at,
                },
            )
            return True
        except ClientError as exc:
            if self._is_condition_failure(exc):
                return False
            raise

    def begin_creation_attempt(
        self,
        chat_id: int | str,
        root_message_id: int,
        *,
        attempt_id: str,
        stale_before: int,
        now: int | None = None,
    ) -> bool:
        """Claim or replace a stale rules-publication lease."""
        now = int(now or time.time())
        try:
            self.table.update_item(
                Key={"pk": self._chat_pk(chat_id), "sk": self._meta_sk(root_message_id)},
                UpdateExpression=("SET creation_attempt_id = :attempt, creation_started_at = :now, updated_at = :now"),
                ConditionExpression=(
                    "#status = :creating AND "
                    "(attribute_not_exists(creation_attempt_id) OR creation_started_at < :stale_before)"
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":creating": "CREATING",
                    ":attempt": str(attempt_id),
                    ":stale_before": int(stale_before),
                    ":now": now,
                },
            )
            return True
        except ClientError as exc:
            if self._is_condition_failure(exc):
                return False
            raise

    def release_creation_attempt(
        self,
        chat_id: int | str,
        root_message_id: int,
        *,
        attempt_id: str,
        now: int | None = None,
    ) -> bool:
        """Release only the caller's rules-publication lease after retryable failure."""
        now = int(now or time.time())
        try:
            self.table.update_item(
                Key={"pk": self._chat_pk(chat_id), "sk": self._meta_sk(root_message_id)},
                UpdateExpression=("SET updated_at = :now REMOVE creation_attempt_id, creation_started_at"),
                ConditionExpression=("#status = :creating AND creation_attempt_id = :attempt"),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":creating": "CREATING",
                    ":attempt": str(attempt_id),
                    ":now": now,
                },
            )
            return True
        except ClientError as exc:
            if self._is_condition_failure(exc):
                return False
            raise

    def get_contest(
        self,
        chat_id: int | str,
        root_message_id: int | str,
        *,
        consistent: bool = False,
    ) -> dict[str, Any] | None:
        response = self.table.get_item(
            Key={"pk": self._chat_pk(chat_id), "sk": self._meta_sk(root_message_id)},
            ConsistentRead=bool(consistent),
        )
        item = response.get("Item")
        return item if isinstance(item, dict) else None

    def get_participant(
        self,
        chat_id: int | str,
        root_message_id: int | str,
        user_id: int | str,
        *,
        consistent: bool = False,
    ) -> dict[str, Any] | None:
        response = self.table.get_item(
            Key={"pk": self._chat_pk(chat_id), "sk": self._participant_sk(root_message_id, user_id)},
            ConsistentRead=bool(consistent),
        )
        item = response.get("Item")
        return item if isinstance(item, dict) else None

    def resolve_contest_by_anchor(
        self,
        chat_id: int | str,
        anchor_message_id: int | str,
    ) -> dict[str, Any] | None:
        """Resolve either the mirrored root id or the stored rules-message id."""
        direct = self.get_contest(chat_id, anchor_message_id, consistent=True)
        if direct:
            return direct
        response = self.table.get_item(
            Key={"pk": self._chat_pk(chat_id), "sk": self._rule_anchor_sk(anchor_message_id)},
            ConsistentRead=True,
        )
        alias = response.get("Item") or {}
        root_message_id = alias.get("root_message_id")
        if root_message_id is None:
            return None
        return self.get_contest(chat_id, root_message_id, consistent=True)

    def register_participant(
        self,
        *,
        chat_id: int | str,
        root_message_id: int,
        user_id: int,
        entry_message_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        text: str,
        accepted_at: int | None = None,
    ) -> RegistrationResult:
        """Atomically require ``OPEN`` and insert the user's first entry."""
        now = int(accepted_at or time.time())
        pk = self._chat_pk(chat_id)
        participant_key = {"pk": pk, "sk": self._participant_sk(root_message_id, user_id)}
        item: dict[str, Any] = {
            **participant_key,
            "kind": "contest_participant",
            "chat_id": str(chat_id),
            "root_message_id": int(root_message_id),
            "user_id": str(user_id),
            "entry_message_id": int(entry_message_id),
            "text": str(text)[:4096],
            "accepted_at": now,
        }
        if username:
            item["username"] = str(username)[:100]
        if first_name:
            item["first_name"] = str(first_name)[:200]
        if last_name:
            item["last_name"] = str(last_name)[:200]
        try:
            self.client.transact_write_items(
                TransactItems=[
                    {
                        "Update": {
                            "TableName": self.table_name,
                            "Key": self._serialize_map({"pk": pk, "sk": self._meta_sk(root_message_id)}),
                            "UpdateExpression": (
                                "SET participant_count = if_not_exists(participant_count, :zero) + :one"
                            ),
                            "ConditionExpression": "#status = :open",
                            "ExpressionAttributeNames": {"#status": "status"},
                            "ExpressionAttributeValues": self._serialize_map({":open": "OPEN", ":zero": 0, ":one": 1}),
                        }
                    },
                    {
                        "Put": {
                            "TableName": self.table_name,
                            "Item": self._serialize_map(item),
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                ]
            )
            return RegistrationResult.REGISTERED
        except ClientError as exc:
            if not self._is_condition_failure(exc):
                raise
            participant = self.get_participant(chat_id, root_message_id, user_id, consistent=True)
            if participant:
                if int(participant.get("entry_message_id") or 0) == int(entry_message_id):
                    return RegistrationResult.REPLAY
                return RegistrationResult.DUPLICATE
            contest = self.get_contest(chat_id, root_message_id, consistent=True)
            if not contest:
                return RegistrationResult.MISSING
            if contest.get("status") != "OPEN":
                return RegistrationResult.CLOSED
            raise RuntimeError("Contest registration transaction conflicted while contest remained OPEN")

    def participant_page(
        self,
        chat_id: int | str,
        root_message_id: int | str,
        *,
        limit: int | None = None,
        start_key: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(self._chat_pk(chat_id))
            & Key("sk").begins_with(self._participant_prefix(root_message_id)),
            "ConsistentRead": True,
        }
        if limit is not None:
            kwargs["Limit"] = max(1, int(limit))
        if start_key:
            kwargs["ExclusiveStartKey"] = start_key
        response = self.table.query(**kwargs)
        return list(response.get("Items") or []), response.get("LastEvaluatedKey")

    def iter_participants(
        self,
        chat_id: int | str,
        root_message_id: int | str,
    ) -> Iterator[dict[str, Any]]:
        """Yield every immutable participant from strongly consistent pages."""
        start_key: dict[str, Any] | None = None
        while True:
            page, start_key = self.participant_page(chat_id, root_message_id, start_key=start_key)
            yield from page
            if not start_key:
                return

    def begin_first_draw(
        self,
        chat_id: int | str,
        root_message_id: int,
        *,
        attempt_id: str,
        now: int | None = None,
    ) -> bool:
        now = int(now or time.time())
        try:
            self.table.update_item(
                Key={"pk": self._chat_pk(chat_id), "sk": self._meta_sk(root_message_id)},
                UpdateExpression=(
                    "SET #status = :drawing, pending_draw_number = :one, draw_attempt_id = :attempt, "
                    "draw_started_at = :now, updated_at = :now"
                ),
                ConditionExpression="#status = :open AND draw_count = :zero",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":drawing": "DRAWING",
                    ":open": "OPEN",
                    ":zero": 0,
                    ":one": 1,
                    ":attempt": str(attempt_id),
                    ":now": now,
                },
            )
            return True
        except ClientError as exc:
            if self._is_condition_failure(exc):
                return False
            raise

    def begin_redraw(
        self,
        chat_id: int | str,
        root_message_id: int,
        *,
        expected_draw_count: int,
        attempt_id: str,
        now: int | None = None,
    ) -> bool:
        now = int(now or time.time())
        next_draw = int(expected_draw_count) + 1
        try:
            self.table.update_item(
                Key={"pk": self._chat_pk(chat_id), "sk": self._meta_sk(root_message_id)},
                UpdateExpression=(
                    "SET #status = :drawing, pending_draw_number = :next, draw_attempt_id = :attempt, "
                    "draw_started_at = :now, updated_at = :now"
                ),
                ConditionExpression=(
                    "#status = :drawn AND draw_count = :expected AND draw_count < :max_draws "
                    "AND announcement_state = :sent AND expires_at > :now"
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":drawing": "DRAWING",
                    ":drawn": "DRAWN",
                    ":expected": int(expected_draw_count),
                    ":next": next_draw,
                    ":attempt": str(attempt_id),
                    ":max_draws": 3,
                    ":sent": "SENT",
                    ":now": now,
                },
            )
            return True
        except ClientError as exc:
            if self._is_condition_failure(exc):
                return False
            raise

    def abort_draw(
        self,
        chat_id: int | str,
        root_message_id: int,
        *,
        draw_number: int,
        attempt_id: str,
        now: int | None = None,
    ) -> bool:
        now = int(now or time.time())
        restore_status = "OPEN" if int(draw_number) == 1 else "DRAWN"
        try:
            self.table.update_item(
                Key={"pk": self._chat_pk(chat_id), "sk": self._meta_sk(root_message_id)},
                UpdateExpression=(
                    "SET #status = :restore, updated_at = :now "
                    "REMOVE pending_draw_number, draw_attempt_id, draw_started_at"
                ),
                ConditionExpression=(
                    "#status = :drawing AND pending_draw_number = :draw AND draw_attempt_id = :attempt"
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":restore": restore_status,
                    ":drawing": "DRAWING",
                    ":draw": int(draw_number),
                    ":attempt": str(attempt_id),
                    ":now": now,
                },
            )
            return True
        except ClientError as exc:
            if self._is_condition_failure(exc):
                return False
            raise

    @staticmethod
    def _winner_snapshot(participant: dict[str, Any], *, draw_number: int, selected_at: int) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "draw_number": int(draw_number),
            "selected_at": int(selected_at),
            "user_id": str(participant["user_id"]),
            "entry_message_id": int(participant["entry_message_id"]),
            "text": str(participant.get("text") or "")[:4096],
        }
        for key, limit in (("username", 100), ("first_name", 200), ("last_name", 200)):
            if participant.get(key):
                snapshot[key] = str(participant[key])[:limit]
        return snapshot

    def complete_draw(
        self,
        chat_id: int | str,
        root_message_id: int,
        *,
        draw_number: int,
        attempt_id: str,
        participant: dict[str, Any],
        frozen_participant_count: int,
        now: int | None = None,
    ) -> bool:
        """Persist one immutable winner before Telegram announcement delivery."""
        now = int(now or time.time())
        draw_number = int(draw_number)
        winner = self._winner_snapshot(participant, draw_number=draw_number, selected_at=now)
        values: dict[str, Any] = {
            ":drawn": "DRAWN",
            ":drawing": "DRAWING",
            ":draw": draw_number,
            ":winner": [winner],
            ":winner_id": [str(participant["user_id"])],
            ":attempt": str(attempt_id),
            ":pending": "PENDING",
            ":now": now,
        }
        if draw_number == 1:
            expires_at = self._expiry(now)
            values.update({":zero": 0, ":count": int(frozen_participant_count), ":expires": expires_at})
            update_expression = (
                "SET #status = :drawn, draw_count = :draw, winners = :winner, winner_user_ids = :winner_id, "
                "frozen_participant_count = :count, first_draw_at = :now, expires_at = :expires, "
                "ttl_sweep_status = :pending, ttl_sweep_version = :zero, "
                "announcement_state = :pending, updated_at = :now "
                "REMOVE pending_draw_number, draw_attempt_id, draw_started_at"
            )
            condition = (
                "#status = :drawing AND pending_draw_number = :draw AND draw_attempt_id = :attempt "
                "AND draw_count = :zero AND participant_count = :count "
                "AND attribute_not_exists(expires_at)"
            )
        else:
            values.update(
                {
                    ":previous": draw_number - 1,
                    ":single_winner_id": str(participant["user_id"]),
                }
            )
            update_expression = (
                "SET #status = :drawn, draw_count = :draw, winners = list_append(winners, :winner), "
                "winner_user_ids = list_append(winner_user_ids, :winner_id), announcement_state = :pending, "
                "updated_at = :now REMOVE pending_draw_number, draw_attempt_id, draw_started_at"
            )
            condition = (
                "#status = :drawing AND pending_draw_number = :draw AND draw_attempt_id = :attempt "
                "AND draw_count = :previous "
                "AND expires_at > :now AND NOT contains(winner_user_ids, :single_winner_id)"
            )
        try:
            if draw_number == 1:
                outbox = self._ttl_outbox_item(
                    chat_id,
                    root_message_id,
                    expires_at=expires_at,
                    created_at=now,
                )
                self.client.transact_write_items(
                    TransactItems=[
                        {
                            "Update": {
                                "TableName": self.table_name,
                                "Key": self._serialize_map(
                                    {"pk": self._chat_pk(chat_id), "sk": self._meta_sk(root_message_id)}
                                ),
                                "UpdateExpression": update_expression,
                                "ConditionExpression": condition,
                                "ExpressionAttributeNames": {"#status": "status"},
                                "ExpressionAttributeValues": self._serialize_map(values),
                            }
                        },
                        {
                            "Put": {
                                "TableName": self.table_name,
                                "Item": self._serialize_map(outbox),
                                "ConditionExpression": "attribute_not_exists(pk)",
                            }
                        },
                    ]
                )
            else:
                self.table.update_item(
                    Key={"pk": self._chat_pk(chat_id), "sk": self._meta_sk(root_message_id)},
                    UpdateExpression=update_expression,
                    ConditionExpression=condition,
                    ExpressionAttributeNames={"#status": "status"},
                    ExpressionAttributeValues=values,
                )
            return True
        except ClientError as exc:
            if self._is_condition_failure(exc):
                return False
            raise

    def mark_announcement_sent(
        self,
        chat_id: int | str,
        root_message_id: int,
        *,
        draw_number: int,
        announcement_message_id: int,
        now: int | None = None,
    ) -> bool:
        now = int(now or time.time())
        index = int(draw_number) - 1
        try:
            self.table.update_item(
                Key={"pk": self._chat_pk(chat_id), "sk": self._meta_sk(root_message_id)},
                UpdateExpression=(
                    f"SET announcement_state = :sent, winners[{index}].announcement_message_id = :message, "
                    "updated_at = :now"
                ),
                ConditionExpression=("#status = :drawn AND draw_count = :draw AND announcement_state = :pending"),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":drawn": "DRAWN",
                    ":draw": int(draw_number),
                    ":pending": "PENDING",
                    ":sent": "SENT",
                    ":message": int(announcement_message_id),
                    ":now": now,
                },
            )
            return True
        except ClientError as exc:
            if self._is_condition_failure(exc):
                return False
            raise

    def mark_orphaned(
        self,
        chat_id: int | str,
        root_message_id: int,
        *,
        draw_number: int,
        now: int | None = None,
    ) -> bool:
        now = int(now or time.time())
        try:
            self.table.update_item(
                Key={"pk": self._chat_pk(chat_id), "sk": self._meta_sk(root_message_id)},
                UpdateExpression=("SET #status = :orphaned, orphaned_at = :now, updated_at = :now"),
                ConditionExpression=("#status = :drawn AND draw_count = :draw AND announcement_state = :pending"),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":drawn": "DRAWN",
                    ":orphaned": "ORPHANED",
                    ":draw": int(draw_number),
                    ":pending": "PENDING",
                    ":now": now,
                },
            )
            return True
        except ClientError as exc:
            if self._is_condition_failure(exc):
                return False
            raise

    def cancel_contest(
        self,
        chat_id: int | str,
        root_message_id: int,
        *,
        now: int | None = None,
    ) -> dict[str, Any] | None:
        now = int(now or time.time())
        expires_at = self._expiry(now)
        values = {
            ":cancelled": "CANCELLED",
            ":open": "OPEN",
            ":pending": "PENDING",
            ":zero": 0,
            ":now": now,
            ":expires": expires_at,
        }
        update_expression = (
            "SET #status = :cancelled, cancelled_at = :now, expires_at = :expires, "
            "ttl_sweep_status = :pending, ttl_sweep_version = :zero, updated_at = :now"
        )
        condition = "#status = :open AND attribute_not_exists(expires_at)"
        try:
            self.client.transact_write_items(
                TransactItems=[
                    {
                        "Update": {
                            "TableName": self.table_name,
                            "Key": self._serialize_map(
                                {"pk": self._chat_pk(chat_id), "sk": self._meta_sk(root_message_id)}
                            ),
                            "UpdateExpression": update_expression,
                            "ConditionExpression": condition,
                            "ExpressionAttributeNames": {"#status": "status"},
                            "ExpressionAttributeValues": self._serialize_map(values),
                        }
                    },
                    {
                        "Put": {
                            "TableName": self.table_name,
                            "Item": self._serialize_map(
                                self._ttl_outbox_item(
                                    chat_id,
                                    root_message_id,
                                    expires_at=expires_at,
                                    created_at=now,
                                )
                            ),
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                ]
            )
            return self.get_contest(chat_id, root_message_id, consistent=True)
        except ClientError as exc:
            if self._is_condition_failure(exc):
                return None
            raise

    def ttl_outbox_page(
        self,
        *,
        limit: int = 100,
        start_key: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """Return one strongly consistent page of durably pending sweep markers."""
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(_TTL_OUTBOX_PK),
            "ConsistentRead": True,
            "Limit": max(1, int(limit)),
        }
        if start_key:
            kwargs["ExclusiveStartKey"] = start_key
        response = self.table.query(**kwargs)
        return list(response.get("Items") or []), response.get("LastEvaluatedKey")

    def record_ttl_sweep_progress(
        self,
        chat_id: int | str,
        root_message_id: int,
        *,
        expected_start_key: dict[str, Any] | None,
        expected_version: int,
        next_start_key: dict[str, Any],
        now: int | None = None,
    ) -> bool:
        now = int(now or time.time())
        cursor_condition = (
            "ttl_sweep_cursor = :expected_cursor"
            if expected_start_key is not None
            else "attribute_not_exists(ttl_sweep_cursor)"
        )
        values: dict[str, Any] = {
            ":pending": "PENDING",
            ":cursor": next_start_key,
            ":version": int(expected_version),
            ":next_version": int(expected_version) + 1,
            ":now": now,
        }
        if expected_start_key is not None:
            values[":expected_cursor"] = expected_start_key
        try:
            self.table.update_item(
                Key={"pk": self._chat_pk(chat_id), "sk": self._meta_sk(root_message_id)},
                UpdateExpression=(
                    "SET ttl_sweep_status = :pending, ttl_sweep_cursor = :cursor, "
                    "ttl_sweep_version = :next_version, ttl_sweep_updated_at = :now"
                ),
                ConditionExpression=(
                    "ttl_sweep_status = :pending AND ttl_sweep_version = :version AND " f"{cursor_condition}"
                ),
                ExpressionAttributeValues=values,
            )
            return True
        except ClientError as exc:
            if self._is_condition_failure(exc):
                return False
            raise

    def stamp_participant_ttl(self, items: list[dict[str, Any]], expires_at: int) -> None:
        """Idempotently stamp the immutable contest expiry on participant rows."""
        for item in items:
            self.table.update_item(
                Key={"pk": item["pk"], "sk": item["sk"]},
                UpdateExpression="SET expires_at = :expires, #ttl = :expires",
                ExpressionAttributeNames={"#ttl": "ttl"},
                ExpressionAttributeValues={":expires": int(expires_at)},
            )

    def complete_ttl_sweep(
        self,
        chat_id: int | str,
        root_message_id: int,
        *,
        rules_message_id: int | None,
        expires_at: int,
        expected_start_key: dict[str, Any] | None,
        expected_version: int,
        now: int | None = None,
    ) -> bool:
        """Stamp alias then make META physically expirable after every participant page."""
        now = int(now or time.time())
        if rules_message_id is not None:
            self.table.update_item(
                Key={"pk": self._chat_pk(chat_id), "sk": self._rule_anchor_sk(rules_message_id)},
                UpdateExpression="SET expires_at = :expires, #ttl = :expires",
                ExpressionAttributeNames={"#ttl": "ttl"},
                ExpressionAttributeValues={":expires": int(expires_at)},
            )
        cursor_condition = (
            "ttl_sweep_cursor = :expected_cursor"
            if expected_start_key is not None
            else "attribute_not_exists(ttl_sweep_cursor)"
        )
        values: dict[str, Any] = {
            ":complete": "COMPLETE",
            ":pending": "PENDING",
            ":version": int(expected_version),
            ":now": now,
            ":expires": int(expires_at),
        }
        if expected_start_key is not None:
            values[":expected_cursor"] = expected_start_key
        try:
            self.client.transact_write_items(
                TransactItems=[
                    {
                        "Update": {
                            "TableName": self.table_name,
                            "Key": self._serialize_map(
                                {"pk": self._chat_pk(chat_id), "sk": self._meta_sk(root_message_id)}
                            ),
                            "UpdateExpression": (
                                "SET ttl_sweep_status = :complete, ttl_sweep_updated_at = :now, #ttl = :expires "
                                "REMOVE ttl_sweep_cursor"
                            ),
                            "ConditionExpression": (
                                "expires_at = :expires AND ttl_sweep_status = :pending "
                                "AND ttl_sweep_version = :version AND "
                                f"{cursor_condition}"
                            ),
                            "ExpressionAttributeNames": {"#ttl": "ttl"},
                            "ExpressionAttributeValues": self._serialize_map(values),
                        }
                    },
                    {
                        "Delete": {
                            "TableName": self.table_name,
                            "Key": self._serialize_map(self._ttl_outbox_key(chat_id, root_message_id)),
                        }
                    },
                ]
            )
            return True
        except ClientError as exc:
            if self._is_condition_failure(exc):
                return False
            raise

    @staticmethod
    def is_logically_expired(contest: dict[str, Any], *, now: int | None = None) -> bool:
        expires_at = contest.get("expires_at")
        if expires_at is None:
            return False
        return int(expires_at) <= int(now or time.time())
