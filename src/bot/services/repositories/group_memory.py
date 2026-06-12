"""DynamoDB-backed group memory for recent context and chat/user profiles."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from core.config import GROUP_MEMORY_RETENTION_DAYS, MEMORY_TABLE_NAME
from services.memory_safety import is_memory_learning_safe
from services.repositories._common import get_dynamodb

_VECTOR_MEMORY_PREFIXES = ("EVENT#", "USER_FACT#", "GROUP_FACT#", "JOKE#", "DAILY_SUMMARY#")
_VECTOR_PREFIX_TOKEN_KEY = "__vector_prefix"
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
        return f"AGENT_REPLY#{int(message_id):013d}"

    @staticmethod
    def _daily_summary_sk(summary_date: str) -> str:
        return f"DAILY_SUMMARY#{summary_date}"

    @staticmethod
    def _vector_backfill_sk() -> str:
        return "VECTOR_BACKFILL"

    @staticmethod
    def is_vectorizable_sk(sk: str) -> bool:
        return sk.startswith(_VECTOR_MEMORY_PREFIXES)

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
    def _normalise_lexical_terms(text: str) -> set[str]:
        terms: set[str] = set()
        for raw in _LEXICAL_TERM_RE.findall(text or ""):
            term = raw.lower().lstrip("@#").strip("._-")
            if not term or term in _LEXICAL_STOP_TERMS:
                continue
            if len(term) < 3 and not any(char.isdigit() for char in term):
                continue
            terms.add(term)
        return terms

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

    def _matches_user_memory_item(self, item: dict[str, Any], user_id: int | str, cleanup_terms: set[str]) -> bool:
        user_id_str = str(user_id)
        sk = str(item.get("sk") or "")
        return bool(
            str(item.get("user_id") or "") == user_id_str
            or sk == self._user_sk(user_id)
            or sk.startswith(f"USER_FACT#{user_id_str}#")
            or (sk.startswith("DAILY_SUMMARY#") and self._daily_summary_mentions_terms(item, cleanup_terms))
        )

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
            "memory_enabled": bool(item.get("memory_enabled", True)),
            "agent_enabled": bool(item.get("agent_enabled", True)),
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
        touch_profile: bool = True,
        skip_if_exists: bool = False,
    ) -> bool:
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
    ) -> dict[str, Any]:
        """Store one trusted long-term memory extracted from a user's own message."""
        now = int(time.time())
        created_at = created_at or now
        created_at_ms = created_at * 1000
        ttl = now + GROUP_MEMORY_RETENTION_DAYS * 24 * 60 * 60
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
            "ttl": ttl,
        }
        if username:
            item["username"] = username
        self.table.put_item(Item=item)
        return item

    def get_recent_long_term_memories(self, chat_id: int | str, *, limit: int = 12) -> list[dict[str, Any]]:
        """Return recent important memories across long-term memory item types."""
        items: list[dict[str, Any]] = []
        per_kind_limit = max(1, limit // 2)
        for prefix in ("EVENT#", "USER_FACT#", "GROUP_FACT#", "JOKE#"):
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
        ttl = now + GROUP_MEMORY_RETENTION_DAYS * 24 * 60 * 60
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
        }
        self.table.put_item(Item=item)
        return item

    def get_recent_daily_summaries(self, chat_id: int | str, *, limit: int = 7) -> list[dict[str, Any]]:
        resp = self.table.query(
            KeyConditionExpression=Key("pk").eq(self._chat_pk(chat_id)) & Key("sk").begins_with("DAILY_SUMMARY#"),
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

        fetch_limit = max(int(limit), 30)
        candidates = [
            *self.get_recent_daily_summaries(chat_id, limit=fetch_limit),
            *self.get_recent_long_term_memories(chat_id, limit=fetch_limit),
        ]
        matched_items: list[dict[str, Any]] = []
        seen_sks: set[str] = set()
        for item in candidates:
            sk = str(item.get("sk") or "")
            if not sk or sk in seen_sks:
                continue
            seen_sks.add(sk)

            searchable_text = self._memory_item_search_text(item)
            if not searchable_text or not is_memory_learning_safe(searchable_text):
                continue
            matched_terms = sorted(query_terms & self._memory_item_lexical_terms(item))
            if not matched_terms:
                continue

            copied = dict(item)
            copied["_lexical_terms"] = matched_terms[:12]
            copied["_lexical_match_count"] = len(matched_terms)
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
        next_token: dict[str, Any] | None = None,
    ) -> None:
        now = int(time.time())
        item: dict[str, Any] = {
            "pk": self._chat_pk(chat_id),
            "sk": self._vector_backfill_sk(),
            "kind": "vector_backfill",
            "chat_id": str(chat_id),
            "vector_backfill_status": status,
            "vector_backfill_processed": Decimal(processed),
            "vector_backfill_enqueued": Decimal(enqueued),
            "vector_backfill_failures": Decimal(failures),
            "vector_backfill_updated_at": now,
            "ttl": now + GROUP_MEMORY_RETENTION_DAYS * 24 * 60 * 60,
        }
        if next_token:
            item["vector_backfill_next_token"] = next_token
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
            try:
                entry["score"] = Decimal(str(round(float(source.get("score") or 0.0), 4)))
            except (TypeError, ValueError):
                entry["score"] = Decimal("0")
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
    ) -> None:
        now = int(time.time())
        ttl = now + 7 * 24 * 60 * 60
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
            KeyConditionExpression=Key("pk").eq(self._chat_pk(chat_id)) & Key("sk").begins_with("AGENT_REPLY#"),
            ScanIndexForward=False,
            Limit=1,
        )
        items = resp.get("Items") or []
        return items[0] if items else {}

    def count_recent_agent_replies(self, chat_id: int | str, *, since_epoch: int, limit: int = 25) -> int:
        resp = self.table.query(
            KeyConditionExpression=Key("pk").eq(self._chat_pk(chat_id)) & Key("sk").begins_with("AGENT_REPLY#"),
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
        }
        start_key: dict[str, Any] | None = None
        while True:
            kwargs: dict[str, Any] = {
                "KeyConditionExpression": Key("pk").eq(self._chat_pk(chat_id)),
                "ProjectionExpression": (
                    "sk, vector_status, vector_backfill_status, vector_backfill_updated_at, "
                    "vector_backfill_processed, vector_backfill_enqueued, vector_backfill_failures"
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
                elif sk.startswith("DAILY_SUMMARY#"):
                    counts["daily_summaries"] += 1
                elif sk.startswith("AGENT_REPLY#"):
                    counts["agent_replies"] += 1
                elif sk == self._vector_backfill_sk():
                    counts["vector_backfill_status"] = str(item.get("vector_backfill_status") or "")
                    counts["vector_backfill_updated_at"] = item.get("vector_backfill_updated_at") or ""
                    counts["vector_backfill_processed"] = int(item.get("vector_backfill_processed") or 0)
                    counts["vector_backfill_enqueued"] = int(item.get("vector_backfill_enqueued") or 0)
                    counts["vector_backfill_failures"] = int(item.get("vector_backfill_failures") or 0)

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
                    for item in to_delete:
                        batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
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
