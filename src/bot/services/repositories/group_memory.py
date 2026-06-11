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

    @staticmethod
    def _normalise_profile_samples(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        samples: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                samples.append(text[:220])
        return samples[-8:]

    @staticmethod
    def _normalise_topic_counts(value: Any) -> dict[str, int]:
        if not isinstance(value, dict):
            return {}
        counts: dict[str, int] = {}
        for key, raw_count in value.items():
            term = str(key or "").strip().lower()
            if not term:
                continue
            try:
                count = int(raw_count)
            except (TypeError, ValueError):
                continue
            if count > 0:
                counts[term] = count
        return counts

    @staticmethod
    def _profile_terms(text: str) -> list[str]:
        """Extract lightweight topic terms from a user's own message."""
        import re

        cleaned = re.sub(r"https?://\S+|@\w+|/\w+", " ", text.lower())
        raw_terms = re.findall(r"[0-9a-zа-яәғқңөұүһіё][0-9a-zа-яәғқңөұүһіё+#._-]{2,}", cleaned)
        stopwords = {
            "and",
            "are",
            "for",
            "from",
            "that",
            "the",
            "this",
            "with",
            "бар",
            "деп",
            "ғой",
            "мен",
            "сол",
            "үшін",
            "бір",
            "как",
            "для",
            "или",
            "что",
            "это",
        }
        terms: list[str] = []
        seen: set[str] = set()
        for term in raw_terms:
            if term in stopwords or term.isdigit() or term in seen:
                continue
            seen.add(term)
            terms.append(term[:40])
            if len(terms) >= 8:
                break
        return terms

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
            ":kind": "profile",
            ":sample": sample_text[:500],
            ":user_id": str(user_id),
        }
        profile = self.get_user_profile(chat_id, user_id)
        values[":samples"] = self._updated_profile_samples(profile, sample_text)
        values[":topics"] = self._updated_profile_topics(profile, sample_text)
        names = {"#count": "message_count"}
        sets = [
            "first_seen = if_not_exists(first_seen, :now)",
            "kind = :kind",
            "user_id = :user_id",
            "last_seen = :now",
            "display_name = :display_name",
            "last_sample = :sample",
            "recent_samples = :samples",
            "topic_counts = :topics",
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

    def _updated_profile_samples(self, profile: dict[str, Any], sample_text: str) -> list[str]:
        samples = self._normalise_profile_samples(profile.get("recent_samples"))
        sample = sample_text.replace("\n", " ").strip()[:220]
        if sample and (not samples or samples[-1] != sample):
            samples.append(sample)
        return samples[-8:]

    def _updated_profile_topics(self, profile: dict[str, Any], sample_text: str) -> dict[str, Decimal]:
        counts = self._normalise_topic_counts(profile.get("topic_counts"))
        for term in self._profile_terms(sample_text):
            counts[term] = counts.get(term, 0) + 1
        top_terms = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:30]
        return {term: Decimal(count) for term, count in top_terms}

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

    def get_user_profiles_by_usernames(
        self,
        chat_id: int | str,
        usernames: set[str],
        *,
        scan_limit: int = 500,
    ) -> list[dict[str, Any]]:
        wanted = {username.lower().lstrip("@") for username in usernames if username}
        if not wanted:
            return []

        profiles: list[dict[str, Any]] = []
        seen = 0
        start_key: dict[str, Any] | None = None
        while seen < scan_limit:
            kwargs: dict[str, Any] = {
                "KeyConditionExpression": Key("pk").eq(self._chat_pk(chat_id)) & Key("sk").begins_with("USER#"),
                "ScanIndexForward": False,
                "Limit": min(100, scan_limit - seen),
            }
            if start_key:
                kwargs["ExclusiveStartKey"] = start_key
            resp = self.table.query(**kwargs)
            items = resp.get("Items") or []
            seen += len(items)
            for item in items:
                username = str(item.get("username") or "").lower().lstrip("@")
                if username in wanted:
                    profiles.append(item)
                    wanted.remove(username)
                    if not wanted:
                        return profiles
            start_key = resp.get("LastEvaluatedKey")
            if not start_key:
                return profiles
        return profiles

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
