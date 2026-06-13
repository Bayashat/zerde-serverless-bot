"""DynamoDB-backed group memory for recent context and chat/user profiles."""

from __future__ import annotations

import re
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from core.config import (
    GROUP_MEMORY_AGENT_REPLY_RETENTION_DAYS,
    GROUP_MEMORY_DAILY_SUMMARY_RETENTION_DAYS,
    GROUP_MEMORY_LONG_TERM_RETENTION_DAYS,
    GROUP_MEMORY_PROACTIVE_COUNTER_RETENTION_DAYS,
    GROUP_MEMORY_RAW_MESSAGE_RETENTION_DAYS,
    GROUP_MEMORY_RETENTION_DAYS,
    MEMORY_TABLE_NAME,
)
from services.memory_safety import is_memory_learning_safe
from services.repositories._common import get_dynamodb

_SECONDS_PER_DAY = 24 * 60 * 60
_LONG_TERM_MEMORY_PREFIXES = ("EVENT#", "USER_FACT#", "GROUP_FACT#", "JOKE#")
_DAILY_SUMMARY_PREFIX = "DAILY_SUMMARY#"
_VECTOR_MEMORY_PREFIXES = (*_LONG_TERM_MEMORY_PREFIXES, _DAILY_SUMMARY_PREFIX)
_AGENT_REPLY_PREFIX = "AGENT_REPLY#"
_AMBIENT_REACTION_PREFIX = "AMBIENT_REACTION#"
_DURABLE_BOT_MEMORY_PREFIXES_BY_KIND = {
    "bot_commitment": "BOT_COMMITMENT#",
    "bot_correction": "BOT_CORRECTION#",
}
_DURABLE_BOT_MEMORY_PREFIXES = tuple(_DURABLE_BOT_MEMORY_PREFIXES_BY_KIND.values())
_USERNAME_ALIAS_PREFIX = "USERNAME#"
_LEXICAL_INDEX_PREFIX = "TERM#"
_VECTOR_PREFIX_TOKEN_KEY = "__vector_prefix"
_AMBIENT_REACTION_RETENTION_DAYS = 7
CHAT_STYLE_TONES = {"concise", "professional", "friendly"}
CHAT_STYLE_LOW_CONFIDENCE_BEHAVIORS = {"cautious", "avoid_weak_memory", "none"}
DEFAULT_CHAT_STYLE_PROFILE: dict[str, Any] = {
    "tone": "concise",
    "max_default_sentences": 5,
    "max_proactive_sentences": 2,
    "allow_light_humor": False,
    "low_confidence_behavior": "cautious",
}
_MAX_LEXICAL_INDEX_TERMS = 24
_MAX_LEXICAL_QUERY_TERMS = 8
_MAX_LEXICAL_INDEX_ROWS_PER_TERM = 100
_LEXICAL_TERM_RE = re.compile(r"[0-9a-zа-яәғқңөұүһіё][0-9a-zа-яәғқңөұүһіё+#._-]{1,}", re.IGNORECASE)
_LEXICAL_STOP_TERMS = {
    "about",
    "and",
    "are",
    "bot",
    "chat",
    "for",
    "from",
    "how",
    "the",
    "this",
    "what",
    "who",
    "why",
    "zerde",
    "бот",
    "как",
    "кто",
    "про",
    "что",
    "чат",
    "это",
    "бір",
    "деп",
    "кім",
    "мен",
    "неге",
    "осы",
    "сол",
    "үшін",
    "什么",
    "怎么",
    "这个",
}


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _bool_setting(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def normalise_chat_style_profile(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a safe chat-level style profile for agent replies."""
    profile = dict(DEFAULT_CHAT_STYLE_PROFILE)
    if not isinstance(raw, Mapping):
        return profile

    tone = str(raw.get("tone") or "").strip().lower()
    if tone in CHAT_STYLE_TONES:
        profile["tone"] = tone

    profile["max_default_sentences"] = _bounded_int(
        raw.get("max_default_sentences"),
        default=profile["max_default_sentences"],
        minimum=1,
        maximum=8,
    )
    profile["max_proactive_sentences"] = _bounded_int(
        raw.get("max_proactive_sentences"),
        default=profile["max_proactive_sentences"],
        minimum=1,
        maximum=4,
    )
    profile["allow_light_humor"] = _bool_setting(
        raw.get("allow_light_humor"),
        default=profile["allow_light_humor"],
    )
    low_confidence_behavior = str(raw.get("low_confidence_behavior") or "").strip().lower()
    if low_confidence_behavior in CHAT_STYLE_LOW_CONFIDENCE_BEHAVIORS:
        profile["low_confidence_behavior"] = low_confidence_behavior
    return profile


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
    def _normalise_username(username: str | None) -> str:
        return str(username or "").strip().lower().lstrip("@")

    @classmethod
    def _username_alias_sk(cls, username: str) -> str:
        normalised = cls._normalise_username(username)
        if not normalised:
            raise ValueError("username must not be empty")
        return f"{_USERNAME_ALIAS_PREFIX}{normalised}"

    @staticmethod
    def _msg_sk(created_at_ms: int, message_id: int | str) -> str:
        return f"MSG#{created_at_ms:013d}#{message_id}"

    @staticmethod
    def _memory_sk(kind: str, created_at_ms: int, message_id: int | str, user_id: int | str | None = None) -> str:
        if kind == "user_fact" and user_id is not None:
            return f"USER_FACT#{user_id}#{created_at_ms:013d}#{message_id}"
        prefix = {
            "event": "EVENT",
            "group_fact": "GROUP_FACT",
            "joke": "JOKE",
        }.get(kind)
        if not prefix:
            raise ValueError(f"Unsupported long-term memory kind: {kind}")
        return f"{prefix}#{created_at_ms:013d}#{message_id}"

    @staticmethod
    def _agent_reply_sk(message_id: int | str) -> str:
        return f"{_AGENT_REPLY_PREFIX}{int(message_id):013d}"

    @staticmethod
    def _ambient_reaction_sk(created_at_ms: int, message_id: int | str) -> str:
        return f"{_AMBIENT_REACTION_PREFIX}{created_at_ms:013d}#{message_id}"

    @staticmethod
    def _daily_summary_sk(summary_date: str) -> str:
        return f"{_DAILY_SUMMARY_PREFIX}{summary_date}"

    @staticmethod
    def _lexical_index_sk(term: str, created_at_ms: int, source_sk: str) -> str:
        return f"{_LEXICAL_INDEX_PREFIX}{term}#{created_at_ms:013d}#{source_sk}"

    @staticmethod
    def _lexical_index_prefix(term: str) -> str:
        return f"{_LEXICAL_INDEX_PREFIX}{term}#"

    @staticmethod
    def _ttl_from_days(now: int, days: int) -> int:
        return now + days * _SECONDS_PER_DAY

    @staticmethod
    def _vector_backfill_sk() -> str:
        return "VECTOR_BACKFILL"

    @staticmethod
    def is_vectorizable_sk(sk: str) -> bool:
        """Return whether a row is allowed to enter long-term semantic vector memory."""
        return sk.startswith(_VECTOR_MEMORY_PREFIXES)

    @staticmethod
    def is_agent_reply_sk(sk: str) -> bool:
        return sk.startswith(_AGENT_REPLY_PREFIX)

    @staticmethod
    def is_durable_bot_memory_sk(sk: str) -> bool:
        return sk.startswith(_DURABLE_BOT_MEMORY_PREFIXES)

    @staticmethod
    def durable_bot_memory_sk(kind: str, created_at_ms: int, source_message_id: int | str) -> str:
        """Reserved key format for explicit bot commitments/corrections.

        These rows are not written by normal answer generation. A future command
        or admin correction flow must call this deliberately and add its own
        review/permission checks before any bot-authored text becomes durable.
        """
        prefix = _DURABLE_BOT_MEMORY_PREFIXES_BY_KIND.get(kind)
        if not prefix:
            raise ValueError(f"Unsupported durable bot memory kind: {kind}")
        return f"{prefix}{int(created_at_ms):013d}#{source_message_id}"

    @staticmethod
    def _vector_prefix_for_start_key(start_key: dict[str, Any] | None) -> str:
        if not start_key:
            return _VECTOR_MEMORY_PREFIXES[0]
        token_prefix = str(start_key.get(_VECTOR_PREFIX_TOKEN_KEY) or "")
        if token_prefix in _VECTOR_MEMORY_PREFIXES:
            return token_prefix
        sk = str(start_key.get("sk") or "")
        for prefix in _VECTOR_MEMORY_PREFIXES:
            if sk.startswith(prefix):
                return prefix
        return _VECTOR_MEMORY_PREFIXES[0]

    @staticmethod
    def _dynamodb_start_key_for_prefix(start_key: dict[str, Any] | None, prefix: str) -> dict[str, Any] | None:
        if not start_key:
            return None
        sk = str(start_key.get("sk") or "")
        if not sk.startswith(prefix):
            return None
        return {key: value for key, value in start_key.items() if not str(key).startswith("__")}

    @staticmethod
    def _next_vector_prefix_token(prefix: str) -> dict[str, Any] | None:
        try:
            next_prefix = _VECTOR_MEMORY_PREFIXES[_VECTOR_MEMORY_PREFIXES.index(prefix) + 1]
        except IndexError:
            return None
        return {_VECTOR_PREFIX_TOKEN_KEY: next_prefix}

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
    def _normalise_profile_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        items: list[str] = []
        seen: set[str] = set()
        for raw in value:
            text = str(raw or "").replace("\n", " ").strip()
            key = text.lower()
            if text and key not in seen:
                seen.add(key)
                items.append(text[:180])
        return items[-12:]

    @staticmethod
    def _cleanup_terms_from_profile(profile: dict[str, Any]) -> set[str]:
        terms: set[str] = set()
        for field in ("username", "display_name", "requester_username", "requester_display_name"):
            value = str(profile.get(field) or "").strip().lower().lstrip("@")
            if value and value not in {"unknown", "user"}:
                terms.add(value)
        return terms

    @staticmethod
    def _daily_summary_mentions_terms(item: dict[str, Any], terms: set[str]) -> bool:
        if not terms:
            return False
        fields = [
            item.get("summary"),
            item.get("topics"),
            item.get("notable_events"),
            item.get("inside_jokes"),
            item.get("active_participants"),
            item.get("tension_points"),
        ]
        searchable = " ".join(
            str(part) for value in fields for part in (value if isinstance(value, list) else [value]) if part
        ).lower()
        return any(term in searchable for term in terms)

    @staticmethod
    def _normalise_lexical_term(raw: str) -> str:
        term = str(raw or "").lower().lstrip("@#").strip("._-")
        if not term or term in _LEXICAL_STOP_TERMS:
            return ""
        if len(term) < 3 and not any(char.isdigit() for char in term):
            return ""
        return term[:80]

    @classmethod
    def _ordered_lexical_terms(cls, text: str) -> list[str]:
        terms: list[str] = []
        seen: set[str] = set()
        for raw in _LEXICAL_TERM_RE.findall(text or ""):
            term = cls._normalise_lexical_term(raw)
            if not term or term in seen:
                continue
            seen.add(term)
            terms.append(term)
        return terms

    @classmethod
    def _normalise_lexical_terms(cls, text: str) -> set[str]:
        return set(cls._ordered_lexical_terms(text))

    @staticmethod
    def _memory_item_search_text(item: dict[str, Any]) -> str:
        fields = [
            item.get("summary"),
            item.get("text"),
            item.get("reason"),
            item.get("topics"),
            item.get("notable_events"),
            item.get("inside_jokes"),
            item.get("active_participants"),
            item.get("tension_points"),
            item.get("display_name"),
            item.get("username"),
            item.get("summary_date"),
            item.get("source"),
            item.get("kind"),
        ]
        return " ".join(
            str(part) for value in fields for part in (value if isinstance(value, list) else [value]) if part
        )

    @classmethod
    def _memory_item_lexical_terms(cls, item: dict[str, Any]) -> set[str]:
        return cls._normalise_lexical_terms(cls._memory_item_search_text(item))

    @classmethod
    def _memory_item_lexical_index_terms(cls, item: dict[str, Any]) -> list[str]:
        stored_terms = item.get("lexical_index_terms")
        if isinstance(stored_terms, list):
            terms: list[str] = []
            seen: set[str] = set()
            for raw in stored_terms:
                term = cls._normalise_lexical_term(str(raw))
                if term and term not in seen:
                    seen.add(term)
                    terms.append(term)
            if terms:
                return terms[:_MAX_LEXICAL_INDEX_TERMS]
        return cls._ordered_lexical_terms(cls._memory_item_search_text(item))[:_MAX_LEXICAL_INDEX_TERMS]

    @staticmethod
    def _source_created_at_ms(item: dict[str, Any]) -> int:
        try:
            created_at = int(item.get("created_at") or 0)
        except (TypeError, ValueError):
            created_at = 0
        if created_at > 0:
            return created_at * 1000

        sk = str(item.get("sk") or "")
        for part in sk.split("#"):
            if not part.isdigit():
                continue
            if len(part) >= 13:
                return int(part)
            if len(part) >= 10:
                return int(part) * 1000
        return 0

    @classmethod
    def _lexical_index_sks_for_item(cls, item: dict[str, Any]) -> list[str]:
        source_sk = str(item.get("sk") or "")
        if not source_sk or not cls.is_vectorizable_sk(source_sk):
            return []
        stored_terms = item.get("lexical_index_terms")
        if not isinstance(stored_terms, list):
            return []
        terms: list[str] = []
        seen: set[str] = set()
        for raw in stored_terms:
            term = cls._normalise_lexical_term(str(raw))
            if term and term not in seen:
                seen.add(term)
                terms.append(term)
        if not terms:
            return []
        created_at_ms = cls._source_created_at_ms(item)
        return [cls._lexical_index_sk(term, created_at_ms, source_sk) for term in terms[:_MAX_LEXICAL_INDEX_TERMS]]

    def _lexical_index_items_for_source(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        source_sk = str(item.get("sk") or "")
        if not source_sk or not self.is_vectorizable_sk(source_sk):
            return []
        terms = self._memory_item_lexical_index_terms(item)
        if not terms:
            return []

        created_at_ms = self._source_created_at_ms(item)
        source_created_at = item.get("created_at")
        rows: list[dict[str, Any]] = []
        for term in terms:
            row: dict[str, Any] = {
                "pk": item.get("pk") or self._chat_pk(item.get("chat_id") or ""),
                "sk": self._lexical_index_sk(term, created_at_ms, source_sk),
                "kind": "lexical_index",
                "chat_id": str(item.get("chat_id") or ""),
                "term": term,
                "source_sk": source_sk,
                "source_kind": str(item.get("kind") or ""),
                "source_created_at": source_created_at if source_created_at is not None else 0,
            }
            if item.get("user_id") is not None:
                row["source_user_id"] = str(item["user_id"])
            if item.get("ttl") is not None:
                row["ttl"] = item["ttl"]
            rows.append(row)
        return rows

    def _put_lexical_index_items(self, item: dict[str, Any]) -> None:
        rows = self._lexical_index_items_for_source(item)
        if not rows:
            return
        with self.table.batch_writer() as batch:
            for row in rows:
                batch.put_item(Item=row)

    def _put_username_alias(
        self,
        *,
        chat_id: int | str,
        user_id: int | str,
        username: str,
        display_name: str,
        now: int,
    ) -> None:
        normalised = self._normalise_username(username)
        if not normalised:
            return
        item = {
            "pk": self._chat_pk(chat_id),
            "sk": self._username_alias_sk(normalised),
            "kind": "username_alias",
            "chat_id": str(chat_id),
            "username": normalised,
            "user_id": str(user_id),
            "target_sk": self._user_sk(user_id),
            "updated_at": now,
        }
        if display_name:
            item["display_name"] = display_name[:160]
        self.table.put_item(Item=item)

    def _delete_username_alias(self, chat_id: int | str, username: str, *, user_id: int | str) -> None:
        normalised = self._normalise_username(username)
        if not normalised:
            return
        try:
            self.table.delete_item(
                Key={"pk": self._chat_pk(chat_id), "sk": self._username_alias_sk(normalised)},
                ConditionExpression="user_id = :user_id",
                ExpressionAttributeValues={":user_id": str(user_id)},
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code != "ConditionalCheckFailedException":
                raise

    @classmethod
    def _delete_sks_for_item(cls, item: dict[str, Any]) -> list[str]:
        sk = str(item.get("sk") or "")
        if not sk:
            return []

        keys = [sk]
        seen = {sk}
        if sk.startswith("USER#"):
            username = cls._normalise_username(str(item.get("username") or ""))
            if username:
                alias_sk = cls._username_alias_sk(username)
                if alias_sk not in seen:
                    seen.add(alias_sk)
                    keys.append(alias_sk)

        for index_sk in cls._lexical_index_sks_for_item(item):
            if index_sk not in seen:
                seen.add(index_sk)
                keys.append(index_sk)
        return keys

    @staticmethod
    def _is_internal_index_sk(sk: str) -> bool:
        return sk.startswith(_USERNAME_ALIAS_PREFIX) or sk.startswith(_LEXICAL_INDEX_PREFIX)

    @staticmethod
    def _feedback_metadata_defaults() -> dict[str, Any]:
        return {
            "wrong_feedback_count": Decimal(0),
            "negative_feedback_count": Decimal(0),
            "superseded_by": "",
        }

    @staticmethod
    def _normalise_evidence_message_ids(value: list[int] | None, fallback_message_id: int | str) -> list[int]:
        ids: list[int] = []
        for item in value or []:
            try:
                ids.append(int(item))
            except (TypeError, ValueError):
                continue
            if len(ids) >= 12:
                break
        if not ids:
            try:
                ids.append(int(fallback_message_id))
            except (TypeError, ValueError):
                pass
        return ids

    def _matches_user_memory_item(self, item: dict[str, Any], user_id: int | str, cleanup_terms: set[str]) -> bool:
        user_id_str = str(user_id)
        sk = str(item.get("sk") or "")
        return bool(
            str(item.get("user_id") or "") == user_id_str
            or str(item.get("source_user_id") or "") == user_id_str
            or sk == self._user_sk(user_id)
            or sk.startswith(f"USER_FACT#{user_id_str}#")
            or (sk.startswith("DAILY_SUMMARY#") and self._daily_summary_mentions_terms(item, cleanup_terms))
        )

    @classmethod
    def is_memory_item_related_to_user(cls, item: dict[str, Any], user_id: int | str) -> bool:
        """Return whether a stored memory item directly belongs to one user."""
        user_id_str = str(user_id)
        sk = str(item.get("sk") or "")
        return bool(
            str(item.get("user_id") or "") == user_id_str
            or sk == cls._user_sk(user_id)
            or sk.startswith(f"USER_FACT#{user_id_str}#")
        )

    @staticmethod
    def _item_matches_message_id(item: dict[str, Any], message_id: int | str) -> bool:
        try:
            target_id = int(message_id)
        except (TypeError, ValueError):
            return False
        try:
            if int(item.get("message_id")) == target_id:
                return True
        except (TypeError, ValueError):
            pass
        evidence_ids = item.get("evidence_message_ids")
        if not isinstance(evidence_ids, list):
            return False
        for raw_id in evidence_ids:
            try:
                if int(raw_id) == target_id:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def list_message_items_by_message_id(
        self,
        chat_id: int | str,
        message_id: int | str,
        *,
        scan_limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Find stored raw MSG items matching a Telegram message id."""
        items: list[dict[str, Any]] = []
        seen = 0
        start_key: dict[str, Any] | None = None
        scan_limit = max(1, int(scan_limit))
        while seen < scan_limit:
            kwargs: dict[str, Any] = {
                "KeyConditionExpression": Key("pk").eq(self._chat_pk(chat_id)) & Key("sk").begins_with("MSG#"),
                "ScanIndexForward": False,
                "Limit": min(100, scan_limit - seen),
            }
            if start_key:
                kwargs["ExclusiveStartKey"] = start_key
            resp = self.table.query(**kwargs)
            batch = resp.get("Items") or []
            seen += len(batch)
            items.extend(item for item in batch if self._item_matches_message_id(item, message_id))
            start_key = resp.get("LastEvaluatedKey")
            if not start_key:
                return items
        return items

    def list_long_term_memory_items_by_message_id(
        self,
        chat_id: int | str,
        message_id: int | str,
        *,
        scan_limit_per_prefix: int = 1000,
    ) -> list[dict[str, Any]]:
        """Find vectorizable long-term memories produced from one Telegram message."""
        matched: list[dict[str, Any]] = []
        scan_limit_per_prefix = max(1, int(scan_limit_per_prefix))
        for prefix in _VECTOR_MEMORY_PREFIXES:
            seen = 0
            start_key: dict[str, Any] | None = None
            while seen < scan_limit_per_prefix:
                kwargs: dict[str, Any] = {
                    "KeyConditionExpression": Key("pk").eq(self._chat_pk(chat_id)) & Key("sk").begins_with(prefix),
                    "Limit": min(100, scan_limit_per_prefix - seen),
                }
                if start_key:
                    kwargs["ExclusiveStartKey"] = start_key
                resp = self.table.query(**kwargs)
                batch = resp.get("Items") or []
                seen += len(batch)
                matched.extend(item for item in batch if self._item_matches_message_id(item, message_id))
                start_key = resp.get("LastEvaluatedKey")
                if not start_key:
                    break
        return matched

    def delete_memory_items_by_sks(self, chat_id: int | str, source_sks: list[str]) -> list[dict[str, Any]]:
        """Delete explicit memory items and return the items that existed."""
        unique_sks: list[str] = []
        seen: set[str] = set()
        for source_sk in source_sks:
            sk = str(source_sk or "").strip()
            if sk and sk not in seen:
                seen.add(sk)
                unique_sks.append(sk)
        if not unique_sks:
            return []

        items: list[dict[str, Any]] = []
        for sk in unique_sks:
            resp = self.table.get_item(Key={"pk": self._chat_pk(chat_id), "sk": sk})
            item = resp.get("Item") or {}
            if item:
                items.append(item)
        if not items:
            return []

        with self.table.batch_writer() as batch:
            for item in items:
                pk = item.get("pk") or self._chat_pk(chat_id)
                for sk in self._delete_sks_for_item(item):
                    batch.delete_item(Key={"pk": pk, "sk": sk})
        return items

    def delete_memory_for_message(self, chat_id: int | str, message_id: int | str) -> list[dict[str, Any]]:
        """Delete the stored raw message and long-term memories derived from it."""
        candidates = [
            *self.list_message_items_by_message_id(chat_id, message_id),
            *self.list_long_term_memory_items_by_message_id(chat_id, message_id),
        ]
        source_sks = [str(item.get("sk") or "") for item in candidates if item.get("sk")]
        return self.delete_memory_items_by_sks(chat_id, source_sks)

    def mark_memory_items_wrong(
        self,
        chat_id: int | str,
        source_sks: list[str],
        *,
        user_id: int | str | None = None,
        agent_reply_message_id: int | str | None = None,
    ) -> int:
        """Record negative feedback on retrieval sources without deleting them."""
        unique_sks: list[str] = []
        seen: set[str] = set()
        for source_sk in source_sks:
            sk = str(source_sk or "").strip()
            if sk and sk not in seen:
                seen.add(sk)
                unique_sks.append(sk)
        if not unique_sks:
            return 0

        now = int(time.time())
        values: dict[str, Any] = {
            ":zero": Decimal(0),
            ":one": Decimal(1),
            ":now": now,
            ":feedback_kind": "wrong",
            ":feedback_status": "wrong",
            ":empty": "",
        }
        sets = [
            "wrong_feedback_count = if_not_exists(wrong_feedback_count, :zero) + :one",
            "negative_feedback_count = if_not_exists(negative_feedback_count, :zero) + :one",
            "last_feedback_at = :now",
            "last_feedback_kind = :feedback_kind",
            "feedback_status = :feedback_status",
            "superseded_by = if_not_exists(superseded_by, :empty)",
        ]
        if user_id is not None:
            values[":feedback_user_id"] = str(user_id)
            sets.append("last_feedback_user_id = :feedback_user_id")
        if agent_reply_message_id is not None:
            values[":agent_reply_message_id"] = int(agent_reply_message_id)
            sets.append("last_feedback_agent_reply_id = :agent_reply_message_id")

        marked = 0
        for sk in unique_sks:
            try:
                self.table.update_item(
                    Key={"pk": self._chat_pk(chat_id), "sk": sk},
                    UpdateExpression="SET " + ", ".join(sets),
                    ConditionExpression="attribute_exists(pk) AND attribute_exists(sk)",
                    ExpressionAttributeValues=values,
                )
                marked += 1
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code")
                if code == "ConditionalCheckFailedException":
                    continue
                raise
        return marked

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

    @staticmethod
    def _detect_language_style(text: str) -> list[str]:
        import re

        styles: list[str] = []
        if re.search(r"[а-яәғқңөұүһіё]", text.lower()):
            styles.append("uses-cyrillic")
        if re.search(r"[\u4e00-\u9fff]", text):
            styles.append("uses-chinese")
        if re.search(r"[a-z]", text.lower()):
            styles.append("uses-latin")
        if "?" in text or "？" in text:
            styles.append("asks-questions")
        if re.search(r"[😂😅🤣😭🙂😉👍🔥]", text):
            styles.append("uses-emoji")
        if len(text) <= 80:
            styles.append("concise")
        elif len(text) >= 240:
            styles.append("long-form")
        return styles[:6]

    @staticmethod
    def _extract_structured_profile_updates(sample_text: str) -> dict[str, list[str]]:
        import re

        cleaned = sample_text.replace("\n", " ").strip()
        lowered = cleaned.lower()
        updates = {
            "language_style": GroupMemoryRepository._detect_language_style(cleaned),
            "interests": [],
            "preferences": [],
            "known_facts": [],
            "boundaries": [],
        }

        tech_terms = GroupMemoryRepository._profile_terms(cleaned)
        updates["interests"].extend(term for term in tech_terms[:5] if term)

        preference_patterns = (
            r"\b(?:i prefer|i like|i love|i use|my stack is)\b[^.!?\n]{0,120}",
            r"\b(?:предпочитаю|люблю|использую)\b[^.!?\n]{0,120}",
            r"(?:маған ұнайды|қолданам|ұнатам)[^.!?\n]{0,120}",
            r"(?:我喜欢|我用)[^。！？\n]{0,80}",
        )
        for pattern in preference_patterns:
            for match in re.finditer(pattern, cleaned, flags=re.IGNORECASE):
                updates["preferences"].append(match.group(0).strip()[:180])

        fact_patterns = (
            r"\b(?:i work|i am working|i live|i study|i built|i maintain)\b[^.!?\n]{0,120}",
            r"\b(?:работаю|живу|учусь|поддерживаю)\b[^.!?\n]{0,120}",
            r"(?:жұмыс істеймін|тұрамын|оқимын)[^.!?\n]{0,120}",
            r"(?:我在|我住|我负责)[^。！？\n]{0,80}",
        )
        for pattern in fact_patterns:
            for match in re.finditer(pattern, cleaned, flags=re.IGNORECASE):
                updates["known_facts"].append(match.group(0).strip()[:180])

        boundary_patterns = (
            r"\b(?:don't call me|do not call me|don't ping me|do not ping me|don't mention me)\b[^.!?\n]{0,120}",
            r"\b(?:не называй|не пингуй|не упоминай)\b[^.!?\n]{0,120}",
            r"(?:мені атама|мені мазалама)[^.!?\n]{0,120}",
            r"(?:别叫我|不要叫我|别提我)[^。！？\n]{0,80}",
        )
        for pattern in boundary_patterns:
            for match in re.finditer(pattern, cleaned, flags=re.IGNORECASE):
                updates["boundaries"].append(match.group(0).strip()[:180])

        # Strong negative preferences are useful as boundaries, but keep them as
        # self-stated facts rather than third-party character labels.
        if any(cue in lowered for cue in ("i hate", "ненавижу", "ұнатпаймын", "我不喜欢")):
            updates["preferences"].append(cleaned[:180])
        return updates

    def set_chat_settings(
        self,
        chat_id: int | str,
        *,
        memory_enabled: bool | None = None,
        agent_enabled: bool | None = None,
        style_profile: Mapping[str, Any] | None = None,
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

        if style_profile is not None:
            names["#style_profile"] = "style_profile"
            values[":style_profile"] = normalise_chat_style_profile(style_profile)
            sets.append("#style_profile = :style_profile")

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
            "memory_enabled": bool(item.get("memory_enabled", True)),
            "agent_enabled": bool(item.get("agent_enabled", True)),
            "style_profile": normalise_chat_style_profile(item.get("style_profile")),
            "updated_at": item.get("updated_at"),
        }

    def get_chat_style_profile(self, chat_id: int | str) -> dict[str, Any]:
        return normalise_chat_style_profile(self.get_chat_settings(chat_id).get("style_profile"))

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
        sender_type: str | None = None,
        created_at: int | None = None,
        reply_metadata: dict[str, Any] | None = None,
        touch_profile: bool = True,
        skip_if_exists: bool = False,
    ) -> bool:
        now = int(time.time())
        created_at = created_at or now
        created_at_ms = created_at * 1000
        ttl = self._ttl_from_days(now, GROUP_MEMORY_RAW_MESSAGE_RETENTION_DAYS)
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
        if sender_type:
            item["sender_type"] = str(sender_type)[:80]
        if username:
            item["username"] = username
        if reply_metadata:
            for key, value in reply_metadata.items():
                if value is not None:
                    item[key] = value
        kwargs: dict[str, Any] = {"Item": item}
        if skip_if_exists:
            kwargs["ConditionExpression"] = "attribute_not_exists(pk)"
        try:
            self.table.put_item(**kwargs)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if skip_if_exists and code == "ConditionalCheckFailedException":
                return False
            raise
        if touch_profile:
            self._touch_user_profile(
                chat_id=chat_id,
                user_id=user_id,
                display_name=display_name,
                username=username,
                sample_text=text,
                now=now,
            )
        return True

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
        names = {"#count": "message_count"}
        sets = [
            "first_seen = if_not_exists(first_seen, :now)",
            "kind = :kind",
            "user_id = :user_id",
            "last_seen = :now",
            "display_name = :display_name",
            "#count = if_not_exists(#count, :zero) + :one",
        ]
        if is_memory_learning_safe(sample_text):
            values[":samples"] = self._updated_profile_samples(profile, sample_text)
            values[":topics"] = self._updated_profile_topics(profile, sample_text)
            structured_updates = self._updated_structured_profile(profile, sample_text)
            values[":language_style"] = structured_updates["language_style"]
            values[":interests"] = structured_updates["interests"]
            values[":preferences"] = structured_updates["preferences"]
            values[":known_facts"] = structured_updates["known_facts"]
            values[":boundaries"] = structured_updates["boundaries"]
            sets.extend(
                [
                    "last_sample = :sample",
                    "recent_samples = :samples",
                    "topic_counts = :topics",
                    "language_style = :language_style",
                    "interests = :interests",
                    "preferences = :preferences",
                    "known_facts = :known_facts",
                    "boundaries = :boundaries",
                ]
            )
        if username:
            values[":username"] = username
            sets.append("username = :username")
        old_username = self._normalise_username(str(profile.get("username") or ""))
        new_username = self._normalise_username(username)

        self.table.update_item(
            Key={"pk": self._chat_pk(chat_id), "sk": self._user_sk(user_id)},
            UpdateExpression="SET " + ", ".join(sets),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
        if new_username:
            self._put_username_alias(
                chat_id=chat_id,
                user_id=user_id,
                username=new_username,
                display_name=display_name,
                now=now,
            )
            if old_username and old_username != new_username:
                self._delete_username_alias(chat_id, old_username, user_id=user_id)

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

    def _updated_structured_profile(self, profile: dict[str, Any], sample_text: str) -> dict[str, list[str]]:
        updates = self._extract_structured_profile_updates(sample_text)
        result: dict[str, list[str]] = {}
        for field in ("language_style", "interests", "preferences", "known_facts", "boundaries"):
            merged = self._normalise_profile_list(profile.get(field))
            seen = {item.lower() for item in merged}
            for item in updates[field]:
                text = str(item or "").replace("\n", " ").strip()
                key = text.lower()
                if text and key not in seen:
                    seen.add(key)
                    merged.append(text[:180])
            result[field] = merged[-12:]
        return result

    def get_recent_messages(self, chat_id: int | str, *, limit: int) -> list[dict[str, Any]]:
        resp = self.table.query(
            KeyConditionExpression=Key("pk").eq(self._chat_pk(chat_id)) & Key("sk").begins_with("MSG#"),
            ScanIndexForward=False,
            Limit=limit,
        )
        items = resp.get("Items") or []
        return list(reversed(items))

    def get_messages_for_day(
        self,
        chat_id: int | str,
        *,
        start_epoch: int,
        end_epoch: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Return messages in [start_epoch, end_epoch) ordered oldest to newest."""
        start_ms = start_epoch * 1000
        end_ms = max(start_ms, end_epoch * 1000 - 1)
        resp = self.table.query(
            KeyConditionExpression=Key("pk").eq(self._chat_pk(chat_id))
            & Key("sk").between(f"MSG#{start_ms:013d}#", f"MSG#{end_ms:013d}#~"),
            ScanIndexForward=True,
            Limit=limit,
        )
        return resp.get("Items") or []

    def store_long_term_memory(
        self,
        *,
        chat_id: int | str,
        message_id: int | str,
        user_id: int | str,
        display_name: str,
        username: str | None,
        text: str,
        kind: str,
        summary: str,
        reason: str,
        confidence: float,
        created_at: int | None = None,
        extractor_source: str = "rules",
        expires_in_days: int | None = None,
        evidence_message_ids: list[int] | None = None,
        sensitivity: str = "public",
    ) -> dict[str, Any]:
        """Store one trusted long-term memory extracted from a user's own message."""
        now = int(time.time())
        created_at = created_at or now
        created_at_ms = created_at * 1000
        retention_ttl = self._ttl_from_days(now, GROUP_MEMORY_LONG_TERM_RETENTION_DAYS)
        expires_at = None
        if expires_in_days is not None:
            try:
                expires_at = created_at + max(1, int(expires_in_days)) * _SECONDS_PER_DAY
            except (TypeError, ValueError):
                expires_at = None
        ttl = min(retention_ttl, expires_at) if expires_at else retention_ttl
        item = {
            "pk": self._chat_pk(chat_id),
            "sk": self._memory_sk(kind, created_at_ms, message_id, user_id),
            "kind": kind,
            "chat_id": str(chat_id),
            "message_id": int(message_id),
            "user_id": str(user_id),
            "display_name": display_name,
            "text": text[:1200],
            "summary": summary[:500],
            "reason": reason[:240],
            "confidence": Decimal(str(max(0.0, min(1.0, confidence)))),
            "created_at": created_at,
            "extractor_source": extractor_source[:40] if extractor_source else "rules",
            "evidence_message_ids": self._normalise_evidence_message_ids(evidence_message_ids, message_id),
            "sensitivity": sensitivity[:40] if sensitivity else "public",
            "ttl": ttl,
            **self._feedback_metadata_defaults(),
        }
        if expires_at:
            item["expires_at"] = expires_at
        if username:
            item["username"] = username
        index_terms = self._memory_item_lexical_index_terms(item)
        if index_terms:
            item["lexical_index_terms"] = index_terms
        self.table.put_item(Item=item)
        self._put_lexical_index_items(item)
        return item

    def get_recent_long_term_memories(self, chat_id: int | str, *, limit: int = 12) -> list[dict[str, Any]]:
        """Return recent important memories across long-term memory item types."""
        items: list[dict[str, Any]] = []
        per_kind_limit = max(1, limit // 2)
        for prefix in _LONG_TERM_MEMORY_PREFIXES:
            resp = self.table.query(
                KeyConditionExpression=Key("pk").eq(self._chat_pk(chat_id)) & Key("sk").begins_with(prefix),
                ScanIndexForward=False,
                Limit=per_kind_limit,
            )
            items.extend(resp.get("Items") or [])
        newest = sorted(items, key=lambda row: int(row.get("created_at") or 0), reverse=True)[:limit]
        return list(reversed(newest))

    def store_daily_summary(
        self,
        *,
        chat_id: int | str,
        summary_date: str,
        summary: str,
        topics: list[str],
        notable_events: list[str],
        inside_jokes: list[str],
        active_participants: list[str],
        tension_points: list[str],
        message_count: int,
        source: str,
    ) -> dict[str, Any]:
        """Store one daily compressed group memory summary."""
        now = int(time.time())
        ttl = self._ttl_from_days(now, GROUP_MEMORY_DAILY_SUMMARY_RETENTION_DAYS)
        item = {
            "pk": self._chat_pk(chat_id),
            "sk": self._daily_summary_sk(summary_date),
            "kind": "daily_summary",
            "chat_id": str(chat_id),
            "summary_date": summary_date,
            "summary": summary[:1200],
            "topics": topics[:12],
            "notable_events": notable_events[:12],
            "inside_jokes": inside_jokes[:8],
            "active_participants": active_participants[:20],
            "tension_points": tension_points[:8],
            "message_count": message_count,
            "source": source,
            "created_at": now,
            "ttl": ttl,
            **self._feedback_metadata_defaults(),
        }
        index_terms = self._memory_item_lexical_index_terms(item)
        if index_terms:
            item["lexical_index_terms"] = index_terms
        self.table.put_item(Item=item)
        self._put_lexical_index_items(item)
        return item

    def get_recent_daily_summaries(self, chat_id: int | str, *, limit: int = 7) -> list[dict[str, Any]]:
        resp = self.table.query(
            KeyConditionExpression=Key("pk").eq(self._chat_pk(chat_id)) & Key("sk").begins_with(_DAILY_SUMMARY_PREFIX),
            ScanIndexForward=False,
            Limit=limit,
        )
        items = resp.get("Items") or []
        return list(reversed(items))

    def search_long_term_memories_by_terms(
        self,
        chat_id: int | str,
        terms: set[str] | list[str] | tuple[str, ...],
        *,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Return exact-term long-term memory candidates without scanning raw messages."""
        query_terms = self._normalise_lexical_terms(" ".join(str(term) for term in terms if term))
        if not query_terms:
            return []

        matched_items: list[dict[str, Any]] = []
        seen_sks: set[str] = set()
        source_matches: dict[str, set[str]] = {}
        rows_per_term = max(max(int(limit), 1) * 3, 30)
        rows_per_term = min(_MAX_LEXICAL_INDEX_ROWS_PER_TERM, rows_per_term)

        for term in sorted(query_terms)[:_MAX_LEXICAL_QUERY_TERMS]:
            seen_rows = 0
            start_key: dict[str, Any] | None = None
            while seen_rows < rows_per_term:
                kwargs: dict[str, Any] = {
                    "KeyConditionExpression": Key("pk").eq(self._chat_pk(chat_id))
                    & Key("sk").begins_with(self._lexical_index_prefix(term)),
                    "ScanIndexForward": False,
                    "Limit": min(100, rows_per_term - seen_rows),
                }
                if start_key:
                    kwargs["ExclusiveStartKey"] = start_key
                resp = self.table.query(**kwargs)
                rows = resp.get("Items") or []
                seen_rows += len(rows)
                for row in rows:
                    source_sk = str(row.get("source_sk") or "")
                    if source_sk:
                        source_matches.setdefault(source_sk, set()).add(term)
                start_key = resp.get("LastEvaluatedKey")
                if not start_key:
                    break

        for source_sk, matched_terms_hint in source_matches.items():
            item = self.get_memory_item(chat_id, source_sk)
            if not item:
                continue
            copied = self._copy_lexical_match(item, query_terms, matched_terms_hint=matched_terms_hint)
            if not copied:
                continue
            matched_items.append(copied)
            seen_sks.add(source_sk)

        fetch_limit = max(int(limit), 30)
        fallback_candidates = [
            *self.get_recent_daily_summaries(chat_id, limit=fetch_limit),
            *self.get_recent_long_term_memories(chat_id, limit=fetch_limit),
        ]
        for item in fallback_candidates:
            sk = str(item.get("sk") or "")
            if not sk or sk in seen_sks:
                continue
            seen_sks.add(sk)
            copied = self._copy_lexical_match(item, query_terms, matched_terms_hint=set())
            if copied:
                matched_items.append(copied)

        def sort_key(item: dict[str, Any]) -> tuple[int, int]:
            try:
                match_count = int(item.get("_lexical_match_count") or 0)
            except (TypeError, ValueError):
                match_count = 0
            try:
                created_at = int(item.get("created_at") or 0)
            except (TypeError, ValueError):
                created_at = 0
            return (match_count, created_at)

        return sorted(matched_items, key=sort_key, reverse=True)[: max(1, int(limit))]

    def _copy_lexical_match(
        self,
        item: dict[str, Any],
        query_terms: set[str],
        *,
        matched_terms_hint: set[str],
    ) -> dict[str, Any] | None:
        searchable_text = self._memory_item_search_text(item)
        if not searchable_text or not is_memory_learning_safe(searchable_text):
            return None
        matched_terms = sorted(query_terms & self._memory_item_lexical_terms(item))
        if not matched_terms:
            matched_terms = sorted(query_terms & matched_terms_hint)
        if not matched_terms:
            return None

        copied = dict(item)
        copied["_lexical_terms"] = matched_terms[:12]
        copied["_lexical_match_count"] = len(matched_terms)
        return copied

    def get_memory_item(self, chat_id: int | str, source_sk: str) -> dict[str, Any]:
        resp = self.table.get_item(Key={"pk": self._chat_pk(chat_id), "sk": source_sk})
        return resp.get("Item") or {}

    def list_vectorizable_memory_items(
        self,
        chat_id: int | str,
        *,
        limit: int = 50,
        start_key: dict[str, Any] | None = None,
        user_id: int | str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """Return one page of memory items eligible for vector indexing."""
        cleanup_terms = (
            self._cleanup_terms_from_profile(self.get_user_profile(chat_id, user_id)) if user_id is not None else set()
        )
        limit = max(1, int(limit))
        items: list[dict[str, Any]] = []
        start_prefix = self._vector_prefix_for_start_key(start_key)
        start_index = _VECTOR_MEMORY_PREFIXES.index(start_prefix)
        exclusive_start_key = self._dynamodb_start_key_for_prefix(start_key, start_prefix)

        for prefix in _VECTOR_MEMORY_PREFIXES[start_index:]:
            remaining = limit - len(items)
            if remaining <= 0:
                return items, self._next_vector_prefix_token(prefix)

            kwargs: dict[str, Any] = {
                "KeyConditionExpression": Key("pk").eq(self._chat_pk(chat_id)) & Key("sk").begins_with(prefix),
                "Limit": remaining,
            }
            if exclusive_start_key:
                kwargs["ExclusiveStartKey"] = exclusive_start_key

            resp = self.table.query(**kwargs)
            for item in resp.get("Items") or []:
                if user_id is not None and not self._matches_user_memory_item(item, user_id, cleanup_terms):
                    continue
                items.append(item)

            next_key = resp.get("LastEvaluatedKey")
            if next_key:
                return items, next_key
            if len(items) >= limit:
                return items, self._next_vector_prefix_token(prefix)
            exclusive_start_key = None

        return items, None

    def mark_vector_status(
        self,
        chat_id: int | str,
        source_sk: str,
        *,
        status: str,
        vector_key: str | None = None,
        error: str | None = None,
        embedding_model: str | None = None,
        dimensions: int | None = None,
        document_hash: str | None = None,
        schema_version: str | None = None,
    ) -> None:
        now = int(time.time())
        values: dict[str, Any] = {
            ":status": status,
            ":now": now,
        }
        sets = ["vector_status = :status", "vector_updated_at = :now"]
        removes: list[str] = []
        if vector_key:
            values[":vector_key"] = vector_key
            sets.append("vector_key = :vector_key")
        if embedding_model:
            values[":model"] = embedding_model
            sets.append("vector_embedding_model = :model")
        if dimensions:
            values[":dimensions"] = Decimal(dimensions)
            sets.append("vector_dimensions = :dimensions")
        if document_hash:
            values[":document_hash"] = document_hash
            sets.append("vector_document_hash = :document_hash")
        if schema_version:
            values[":schema_version"] = schema_version
            sets.append("vector_schema_version = :schema_version")
        if error:
            values[":error"] = error[:300]
            sets.append("vector_error = :error")
        else:
            removes.append("vector_error")

        update = "SET " + ", ".join(sets)
        if removes:
            update += " REMOVE " + ", ".join(removes)
        self.table.update_item(
            Key={"pk": self._chat_pk(chat_id), "sk": source_sk},
            UpdateExpression=update,
            ExpressionAttributeValues=values,
        )

    def record_vector_backfill_status(
        self,
        chat_id: int | str,
        *,
        status: str,
        processed: int = 0,
        enqueued: int = 0,
        failures: int = 0,
        start_key: dict[str, Any] | None = None,
        next_token: dict[str, Any] | None = None,
        reset: bool = False,
        finished: bool = False,
    ) -> None:
        now = int(time.time())
        key = {"pk": self._chat_pk(chat_id), "sk": self._vector_backfill_sk()}

        def _item_int(item: dict[str, Any], *names: str) -> int:
            for name in names:
                value = item.get(name)
                if value is None:
                    continue
                try:
                    return int(value)
                except (TypeError, ValueError):
                    continue
            return 0

        existing: dict[str, Any] = {}
        if not reset:
            existing = self.table.get_item(Key=key).get("Item") or {}

        started_at = now if reset else _item_int(existing, "started_at", "vector_backfill_started_at") or now
        processed_total = (0 if reset else _item_int(existing, "processed_total", "vector_backfill_processed")) + max(
            0,
            int(processed),
        )
        enqueued_total = (0 if reset else _item_int(existing, "enqueued_total", "vector_backfill_enqueued")) + max(
            0,
            int(enqueued),
        )
        failures_total = (0 if reset else _item_int(existing, "failures_total", "vector_backfill_failures")) + max(
            0,
            int(failures),
        )

        item: dict[str, Any] = {
            **key,
            "kind": "vector_backfill",
            "chat_id": str(chat_id),
            "status": status,
            "vector_backfill_status": status,
            "processed_total": Decimal(processed_total),
            "enqueued_total": Decimal(enqueued_total),
            "failures_total": Decimal(failures_total),
            "started_at": started_at,
            "last_updated_at": now,
            "vector_backfill_processed": Decimal(processed_total),
            "vector_backfill_enqueued": Decimal(enqueued_total),
            "vector_backfill_failures": Decimal(failures_total),
            "vector_backfill_started_at": started_at,
            "vector_backfill_updated_at": now,
            "ttl": now + GROUP_MEMORY_RETENTION_DAYS * 24 * 60 * 60,
        }
        if start_key:
            item["last_start_key"] = start_key
            item["vector_backfill_last_start_key"] = start_key
        if next_token:
            item["next_token"] = next_token
            item["vector_backfill_next_token"] = next_token
        if finished:
            item["finished_at"] = now
            item["vector_backfill_finished_at"] = now
        self.table.put_item(Item=item)

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
        del scan_limit
        wanted = {self._normalise_username(username) for username in usernames if username}
        wanted.discard("")
        if not wanted:
            return []

        profiles: list[dict[str, Any]] = []
        seen_user_ids: set[str] = set()
        for username in sorted(wanted):
            alias_resp = self.table.get_item(
                Key={"pk": self._chat_pk(chat_id), "sk": self._username_alias_sk(username)}
            )
            alias = alias_resp.get("Item") or {}
            user_id = str(alias.get("user_id") or "").strip()
            if not user_id or user_id in seen_user_ids:
                continue
            profile = self.get_user_profile(chat_id, user_id)
            if not profile:
                continue
            if not profile.get("username"):
                profile = {**profile, "username": alias.get("username") or username}
            if alias.get("display_name") and not profile.get("display_name"):
                profile = {**profile, "display_name": alias["display_name"]}
            profiles.append(profile)
            seen_user_ids.add(user_id)
        return profiles

    def try_reserve_proactive_reply(self, chat_id: int | str, *, daily_limit: int) -> bool:
        """Atomically reserve one proactive agent reply for this chat/day."""
        if daily_limit <= 0:
            return False
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        now = int(time.time())
        ttl = self._ttl_from_days(now, GROUP_MEMORY_PROACTIVE_COUNTER_RETENTION_DAYS)
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

    def get_recent_ambient_reactions(
        self,
        chat_id: int | str,
        *,
        since_epoch: int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return recent ambient reaction event rows, newest first."""
        items: list[dict[str, Any]] = []
        limit = max(1, int(limit))
        start_key: dict[str, Any] | None = None
        while len(items) < limit:
            kwargs: dict[str, Any] = {
                "KeyConditionExpression": Key("pk").eq(self._chat_pk(chat_id))
                & Key("sk").begins_with(_AMBIENT_REACTION_PREFIX),
                "ScanIndexForward": False,
                "Limit": min(100, limit - len(items)),
            }
            if start_key:
                kwargs["ExclusiveStartKey"] = start_key
            resp = self.table.query(**kwargs)
            batch = resp.get("Items") or []
            for item in batch:
                try:
                    created_at = int(item.get("created_at") or 0)
                except (TypeError, ValueError):
                    created_at = 0
                if created_at >= since_epoch:
                    items.append(item)
                elif created_at > 0:
                    return items
            start_key = resp.get("LastEvaluatedKey")
            if not start_key:
                break
        return items[:limit]

    def record_ambient_reaction(
        self,
        *,
        chat_id: int | str,
        user_id: int | str,
        message_id: int | str,
        emoji: str,
        category: str,
        confidence: float,
        created_at: int | None = None,
    ) -> None:
        """Store short-lived ambient reaction metadata for cooldowns and debugging."""
        now = int(time.time())
        created_at = created_at or now
        item = {
            "pk": self._chat_pk(chat_id),
            "sk": self._ambient_reaction_sk(created_at * 1000, message_id),
            "kind": "ambient_reaction",
            "chat_id": str(chat_id),
            "user_id": str(user_id),
            "message_id": int(message_id),
            "emoji": emoji,
            "category": str(category or "")[:80],
            "confidence": Decimal(str(max(0.0, min(1.0, confidence)))),
            "created_at": created_at,
            "ttl": self._ttl_from_days(now, _AMBIENT_REACTION_RETENTION_DAYS),
        }
        self.table.put_item(Item=item)

    @staticmethod
    def _normalise_retrieval_sources(sources: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        normalised: list[dict[str, Any]] = []
        for source in (sources or [])[:20]:
            if not isinstance(source, dict):
                continue
            source_name = str(source.get("source") or "").strip()[:80]
            if not source_name:
                continue
            entry: dict[str, Any] = {"source": source_name}
            if source.get("source_sk"):
                entry["source_sk"] = str(source["source_sk"])[:180]
            if source.get("memory_kind"):
                entry["memory_kind"] = str(source["memory_kind"])[:60]
            if source.get("deletion_policy"):
                entry["deletion_policy"] = str(source["deletion_policy"])[:60]
            if source.get("deletable_source_sk"):
                entry["deletable_source_sk"] = str(source["deletable_source_sk"])[:180]
            try:
                entry["score"] = Decimal(str(round(float(source.get("score") or 0.0), 4)))
            except (TypeError, ValueError):
                entry["score"] = Decimal("0")
            if source.get("confidence") is not None:
                try:
                    entry["confidence"] = Decimal(str(round(max(0.0, min(1.0, float(source["confidence"]))), 4)))
                except (TypeError, ValueError):
                    pass
            if source.get("distance") is not None:
                try:
                    entry["distance"] = Decimal(str(round(max(0.0, float(source["distance"])), 4)))
                except (TypeError, ValueError):
                    pass
            try:
                entry["trust_level"] = int(source.get("trust_level") or 0)
            except (TypeError, ValueError):
                entry["trust_level"] = 0
            if source.get("created_at") is not None:
                try:
                    entry["created_at"] = int(source["created_at"])
                except (TypeError, ValueError):
                    pass
            normalised.append(entry)
        return normalised

    @staticmethod
    def _normalise_agent_reply_media_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(metadata, dict):
            return {}
        allowed_string_limits = {
            "media_type": 40,
            "mime_type": 120,
            "file_unique_id": 160,
            "file_name": 180,
            "caption": 500,
            "source_username": 160,
            "source_display_name": 160,
            "media_summary": 900,
        }
        item: dict[str, Any] = {}
        for key, limit in allowed_string_limits.items():
            value = metadata.get(key)
            if value not in (None, ""):
                item[key] = str(value)[:limit]
        for key in ("file_size", "source_message_id"):
            value = metadata.get(key)
            if value is None:
                continue
            try:
                item[key] = int(value)
            except (TypeError, ValueError):
                pass
        source_user_id = metadata.get("source_user_id")
        if source_user_id not in (None, ""):
            item["source_user_id"] = str(source_user_id)[:80]
        if metadata.get("media_analysis_available") is not None:
            item["media_analysis_available"] = bool(metadata.get("media_analysis_available"))
        return item

    def record_agent_reply(
        self,
        *,
        chat_id: int | str,
        bot_message_id: int | str,
        trigger_message_id: int | str,
        trigger_kind: str,
        reason: str,
        answer_text: str | None = None,
        user_message: str | None = None,
        current_user_message: str | None = None,
        source_message_context: str | None = None,
        parent_bot_message_id: int | str | None = None,
        confidence: float | None = None,
        requester_user_id: int | str | None = None,
        requester_username: str | None = None,
        requester_display_name: str | None = None,
        retrieval_sources: list[dict[str, Any]] | None = None,
        media_metadata: dict[str, Any] | None = None,
    ) -> None:
        now = int(time.time())
        ttl = self._ttl_from_days(now, GROUP_MEMORY_AGENT_REPLY_RETENTION_DAYS)
        item: dict[str, Any] = {
            "pk": self._chat_pk(chat_id),
            "sk": self._agent_reply_sk(bot_message_id),
            "kind": "agent_reply",
            "chat_id": str(chat_id),
            "bot_message_id": int(bot_message_id),
            "trigger_message_id": int(trigger_message_id),
            "trigger_kind": trigger_kind,
            "reason": reason[:500],
            "created_at": now,
            "ttl": ttl,
            **self._feedback_metadata_defaults(),
        }
        if answer_text:
            item["answer_text"] = answer_text[:3000]
        if user_message:
            item["user_message"] = user_message[:1500]
        if current_user_message:
            item["current_user_message"] = current_user_message[:1500]
        if source_message_context:
            item["source_message_context"] = source_message_context[:2200]
        if parent_bot_message_id is not None:
            item["parent_bot_message_id"] = int(parent_bot_message_id)
        if confidence is not None:
            item["confidence"] = Decimal(str(max(0.0, min(1.0, confidence))))
        if requester_user_id is not None:
            item["requester_user_id"] = str(requester_user_id)
        if requester_username:
            item["requester_username"] = requester_username[:160]
        if requester_display_name:
            item["requester_display_name"] = requester_display_name[:160]
        normalised_sources = self._normalise_retrieval_sources(retrieval_sources)
        if normalised_sources:
            item["retrieval_sources"] = normalised_sources
        normalised_media = self._normalise_agent_reply_media_metadata(media_metadata)
        if normalised_media:
            item["media_metadata"] = normalised_media
            if normalised_media.get("media_summary"):
                item["media_summary"] = normalised_media["media_summary"]
        self.table.put_item(Item=item)

    def get_agent_reply_explanation(
        self,
        chat_id: int | str,
        *,
        bot_message_id: int | str | None = None,
    ) -> dict[str, Any]:
        if bot_message_id is not None:
            resp = self.table.get_item(Key={"pk": self._chat_pk(chat_id), "sk": self._agent_reply_sk(bot_message_id)})
            return resp.get("Item") or {}

        resp = self.table.query(
            KeyConditionExpression=Key("pk").eq(self._chat_pk(chat_id)) & Key("sk").begins_with(_AGENT_REPLY_PREFIX),
            ScanIndexForward=False,
            Limit=1,
        )
        items = resp.get("Items") or []
        return items[0] if items else {}

    def count_recent_agent_replies(self, chat_id: int | str, *, since_epoch: int, limit: int = 25) -> int:
        resp = self.table.query(
            KeyConditionExpression=Key("pk").eq(self._chat_pk(chat_id)) & Key("sk").begins_with(_AGENT_REPLY_PREFIX),
            ScanIndexForward=False,
            Limit=limit,
        )
        count = 0
        for item in resp.get("Items") or []:
            try:
                created_at = int(item.get("created_at") or 0)
            except (TypeError, ValueError):
                created_at = 0
            if created_at >= since_epoch:
                count += 1
        return count

    def get_memory_overview(self, chat_id: int | str) -> dict[str, Any]:
        counts = {
            "recent_messages": 0,
            "user_profiles": 0,
            "events": 0,
            "user_facts": 0,
            "group_facts": 0,
            "jokes": 0,
            "daily_summaries": 0,
            "agent_replies": 0,
            "bot_commitments": 0,
            "bot_corrections": 0,
            "vector_total": 0,
            "vector_indexed": 0,
            "vector_failed": 0,
            "vector_skipped": 0,
            "vector_pending": 0,
            "vector_backfill_status": "",
            "vector_backfill_updated_at": "",
            "vector_backfill_processed": 0,
            "vector_backfill_enqueued": 0,
            "vector_backfill_failures": 0,
            "vector_backfill_processed_total": 0,
            "vector_backfill_enqueued_total": 0,
            "vector_backfill_failures_total": 0,
            "vector_backfill_started_at": "",
            "vector_backfill_finished_at": "",
            "vector_backfill_last_start_key": None,
            "vector_backfill_next_token": None,
        }
        start_key: dict[str, Any] | None = None
        while True:
            kwargs: dict[str, Any] = {
                "KeyConditionExpression": Key("pk").eq(self._chat_pk(chat_id)),
                "ProjectionExpression": (
                    "sk, vector_status, vector_backfill_status, vector_backfill_updated_at, "
                    "vector_backfill_processed, vector_backfill_enqueued, vector_backfill_failures, "
                    "processed_total, enqueued_total, failures_total, started_at, last_updated_at, "
                    "finished_at, last_start_key, next_token, vector_backfill_started_at, "
                    "vector_backfill_finished_at, vector_backfill_last_start_key, vector_backfill_next_token"
                ),
            }
            if start_key:
                kwargs["ExclusiveStartKey"] = start_key
            resp = self.table.query(**kwargs)
            for item in resp.get("Items") or []:
                sk = str(item.get("sk") or "")
                if sk.startswith("MSG#"):
                    counts["recent_messages"] += 1
                elif sk.startswith("USER#"):
                    counts["user_profiles"] += 1
                elif sk.startswith("EVENT#"):
                    counts["events"] += 1
                elif sk.startswith("USER_FACT#"):
                    counts["user_facts"] += 1
                elif sk.startswith("GROUP_FACT#"):
                    counts["group_facts"] += 1
                elif sk.startswith("JOKE#"):
                    counts["jokes"] += 1
                elif sk.startswith(_DAILY_SUMMARY_PREFIX):
                    counts["daily_summaries"] += 1
                elif sk.startswith(_AGENT_REPLY_PREFIX):
                    counts["agent_replies"] += 1
                elif sk.startswith(_DURABLE_BOT_MEMORY_PREFIXES_BY_KIND["bot_commitment"]):
                    counts["bot_commitments"] += 1
                elif sk.startswith(_DURABLE_BOT_MEMORY_PREFIXES_BY_KIND["bot_correction"]):
                    counts["bot_corrections"] += 1
                elif sk == self._vector_backfill_sk():
                    processed_total = int(item.get("processed_total") or item.get("vector_backfill_processed") or 0)
                    enqueued_total = int(item.get("enqueued_total") or item.get("vector_backfill_enqueued") or 0)
                    failures_total = int(item.get("failures_total") or item.get("vector_backfill_failures") or 0)
                    counts["vector_backfill_status"] = str(item.get("vector_backfill_status") or "")
                    counts["vector_backfill_updated_at"] = (
                        item.get("last_updated_at") or item.get("vector_backfill_updated_at") or ""
                    )
                    counts["vector_backfill_processed"] = processed_total
                    counts["vector_backfill_enqueued"] = enqueued_total
                    counts["vector_backfill_failures"] = failures_total
                    counts["vector_backfill_processed_total"] = processed_total
                    counts["vector_backfill_enqueued_total"] = enqueued_total
                    counts["vector_backfill_failures_total"] = failures_total
                    counts["vector_backfill_started_at"] = (
                        item.get("started_at") or item.get("vector_backfill_started_at") or ""
                    )
                    counts["vector_backfill_finished_at"] = (
                        item.get("finished_at") or item.get("vector_backfill_finished_at") or ""
                    )
                    counts["vector_backfill_last_start_key"] = item.get("last_start_key") or item.get(
                        "vector_backfill_last_start_key"
                    )
                    counts["vector_backfill_next_token"] = item.get("next_token") or item.get(
                        "vector_backfill_next_token"
                    )

                if self.is_vectorizable_sk(sk):
                    counts["vector_total"] += 1
                    vector_status = str(item.get("vector_status") or "")
                    if vector_status == "indexed":
                        counts["vector_indexed"] += 1
                    elif vector_status == "failed":
                        counts["vector_failed"] += 1
                    elif vector_status == "skipped":
                        counts["vector_skipped"] += 1
                    else:
                        counts["vector_pending"] += 1
            start_key = resp.get("LastEvaluatedKey")
            if not start_key:
                return counts

    def delete_user_memory(self, chat_id: int | str, user_id: int | str) -> int:
        deleted = 0
        cleanup_terms = self._cleanup_terms_from_profile(self.get_user_profile(chat_id, user_id))
        start_key: dict[str, Any] | None = None
        while True:
            kwargs: dict[str, Any] = {
                "KeyConditionExpression": Key("pk").eq(self._chat_pk(chat_id)),
            }
            if start_key:
                kwargs["ExclusiveStartKey"] = start_key
            resp = self.table.query(**kwargs)
            to_delete = []
            for item in resp.get("Items") or []:
                if self._matches_user_memory_item(item, user_id, cleanup_terms):
                    to_delete.append(item)
            if to_delete:
                with self.table.batch_writer() as batch:
                    deleted_keys: set[tuple[str, str]] = set()
                    for item in to_delete:
                        pk = item.get("pk") or self._chat_pk(chat_id)
                        item_sk = str(item.get("sk") or "")
                        for sk in self._delete_sks_for_item(item):
                            key = (str(pk), sk)
                            if key in deleted_keys:
                                continue
                            deleted_keys.add(key)
                            batch.delete_item(Key={"pk": pk, "sk": sk})
                        if item_sk and not self._is_internal_index_sk(item_sk):
                            deleted += 1
            start_key = resp.get("LastEvaluatedKey")
            if not start_key:
                return deleted

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
