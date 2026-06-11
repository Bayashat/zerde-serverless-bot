"""DynamoDB-backed group memory for recent context and chat/user profiles."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from core.config import GROUP_MEMORY_RETENTION_DAYS, MEMORY_TABLE_NAME
from services.repositories._common import get_dynamodb


class GroupMemoryRepository:
    """Store opt-in group memory in a single-table DynamoDB layout."""

    def __init__(self, table_name: str | None = None):
        table_name = table_name or MEMORY_TABLE_NAME
        if not table_name:
            raise ValueError("MEMORY_TABLE_NAME must be set")
        self.table = get_dynamodb().Table(table_name)

    @staticmethod
    def _chat_pk(chat_id: int | str) -> str:
        return f"CHAT#{chat_id}"

    @staticmethod
    def _settings_sk() -> str:
        return "SETTINGS"

    @staticmethod
    def _user_sk(user_id: int | str) -> str:
        return f"USER#{user_id}"

    @staticmethod
    def _msg_sk(created_at_ms: int, message_id: int | str) -> str:
        return f"MSG#{created_at_ms:013d}#{message_id}"

    def set_chat_settings(
        self,
        chat_id: int | str,
        *,
        memory_enabled: bool | None = None,
        agent_enabled: bool | None = None,
    ) -> None:
        names: dict[str, str] = {}
        values: dict[str, Any] = {":updated_at": int(time.time())}
        sets = ["updated_at = :updated_at"]

        if memory_enabled is not None:
            names["#memory_enabled"] = "memory_enabled"
            values[":memory_enabled"] = memory_enabled
            sets.append("#memory_enabled = :memory_enabled")

        if agent_enabled is not None:
            names["#agent_enabled"] = "agent_enabled"
            values[":agent_enabled"] = agent_enabled
            sets.append("#agent_enabled = :agent_enabled")

        kwargs: dict[str, Any] = {
            "Key": {"pk": self._chat_pk(chat_id), "sk": self._settings_sk()},
            "UpdateExpression": "SET " + ", ".join(sets),
            "ExpressionAttributeValues": values,
        }
        if names:
            kwargs["ExpressionAttributeNames"] = names
        self.table.update_item(**kwargs)

    def get_chat_settings(self, chat_id: int | str) -> dict[str, Any]:
        resp = self.table.get_item(Key={"pk": self._chat_pk(chat_id), "sk": self._settings_sk()})
        item = resp.get("Item") or {}
        return {
            "memory_enabled": bool(item.get("memory_enabled", False)),
            "agent_enabled": bool(item.get("agent_enabled", False)),
            "updated_at": item.get("updated_at"),
        }

    def is_memory_enabled(self, chat_id: int | str) -> bool:
        return bool(self.get_chat_settings(chat_id).get("memory_enabled"))

    def is_agent_enabled(self, chat_id: int | str) -> bool:
        settings = self.get_chat_settings(chat_id)
        return bool(settings.get("memory_enabled") and settings.get("agent_enabled"))

    def store_message(
        self,
        *,
        chat_id: int | str,
        message_id: int | str,
        user_id: int | str,
        display_name: str,
        username: str | None,
        text: str,
        created_at: int | None = None,
    ) -> None:
        now = int(time.time())
        created_at = created_at or now
        created_at_ms = created_at * 1000
        ttl = now + GROUP_MEMORY_RETENTION_DAYS * 24 * 60 * 60
        item = {
            "pk": self._chat_pk(chat_id),
            "sk": self._msg_sk(created_at_ms, message_id),
            "kind": "message",
            "chat_id": str(chat_id),
            "message_id": int(message_id),
            "user_id": str(user_id),
            "display_name": display_name,
            "text": text[:4000],
            "created_at": created_at,
            "ttl": ttl,
        }
        if username:
            item["username"] = username
        self.table.put_item(Item=item)
        self._touch_user_profile(
            chat_id=chat_id,
            user_id=user_id,
            display_name=display_name,
            username=username,
            sample_text=text,
            now=now,
        )

    def _touch_user_profile(
        self,
        *,
        chat_id: int | str,
        user_id: int | str,
        display_name: str,
        username: str | None,
        sample_text: str,
        now: int,
    ) -> None:
        values: dict[str, Any] = {
            ":zero": Decimal(0),
            ":one": Decimal(1),
            ":now": now,
            ":display_name": display_name,
            ":sample": sample_text[:500],
        }
        names = {"#count": "message_count"}
        sets = [
            "first_seen = if_not_exists(first_seen, :now)",
            "last_seen = :now",
            "display_name = :display_name",
            "last_sample = :sample",
            "#count = if_not_exists(#count, :zero) + :one",
        ]
        if username:
            values[":username"] = username
            sets.append("username = :username")

        self.table.update_item(
            Key={"pk": self._chat_pk(chat_id), "sk": self._user_sk(user_id)},
            UpdateExpression="SET " + ", ".join(sets),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )

    def get_recent_messages(self, chat_id: int | str, *, limit: int) -> list[dict[str, Any]]:
        resp = self.table.query(
            KeyConditionExpression=Key("pk").eq(self._chat_pk(chat_id)) & Key("sk").begins_with("MSG#"),
            ScanIndexForward=False,
            Limit=limit,
        )
        items = resp.get("Items") or []
        return list(reversed(items))

    def get_user_profile(self, chat_id: int | str, user_id: int | str) -> dict[str, Any]:
        resp = self.table.get_item(Key={"pk": self._chat_pk(chat_id), "sk": self._user_sk(user_id)})
        return resp.get("Item") or {}

    def try_reserve_proactive_reply(self, chat_id: int | str, *, daily_limit: int) -> bool:
        """Atomically reserve one proactive agent reply for this chat/day."""
        if daily_limit <= 0:
            return False
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        now = int(time.time())
        ttl = now + 3 * 24 * 60 * 60
        try:
            self.table.update_item(
                Key={"pk": self._chat_pk(chat_id), "sk": f"PROACTIVE#{day}"},
                UpdateExpression="SET #count = if_not_exists(#count, :zero) + :one, #ttl = :ttl",
                ConditionExpression="attribute_not_exists(#count) OR #count < :limit",
                ExpressionAttributeNames={"#count": "count", "#ttl": "ttl"},
                ExpressionAttributeValues={
                    ":zero": Decimal(0),
                    ":one": Decimal(1),
                    ":limit": Decimal(daily_limit),
                    ":ttl": ttl,
                },
            )
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code == "ConditionalCheckFailedException":
                return False
            raise

    def delete_chat_memory(self, chat_id: int | str) -> int:
        deleted = 0
        start_key: dict[str, Any] | None = None
        while True:
            kwargs: dict[str, Any] = {
                "KeyConditionExpression": Key("pk").eq(self._chat_pk(chat_id)),
                "ProjectionExpression": "pk, sk",
            }
            if start_key:
                kwargs["ExclusiveStartKey"] = start_key
            resp = self.table.query(**kwargs)
            items = resp.get("Items") or []
            if items:
                with self.table.batch_writer() as batch:
                    for item in items:
                        batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
                        deleted += 1
            start_key = resp.get("LastEvaluatedKey")
            if not start_key:
                return deleted
