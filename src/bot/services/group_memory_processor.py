"""Async long-term group memory extraction for PROCESS_GROUP_MEMORY tasks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.logger import LoggerAdapter, get_logger
from services.repositories.group_memory import GroupMemoryRepository

logger = LoggerAdapter(get_logger(__name__), {})

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b")
_PHONE_RE = re.compile(r"(?:\+?\d[\s().-]*){9,}")
_SECRET_CUES = (
    "password",
    "passwd",
    "secret",
    "api key",
    "token",
    "пароль",
    "құпия",
    "密码",
    "令牌",
)
_SENSITIVE_CUES = (
    "diagnosis",
    "medical",
    "salary",
    "passport",
    "credit card",
    "диагноз",
    "медицина",
    "зарплата",
    "паспорт",
    "жалақы",
    "ауырып",
    "身份证",
    "工资",
    "银行卡",
)
_EVENT_CUES = (
    "today",
    "tomorrow",
    "yesterday",
    "meeting",
    "deploy",
    "release",
    "incident",
    "deadline",
    "сегодня",
    "завтра",
    "вчера",
    "релиз",
    "созвон",
    "бүгін",
    "ертең",
    "кеше",
    "релиз",
    "жиналыс",
    "今天",
    "明天",
    "昨天",
    "发布",
)
_GROUP_FACT_CUES = (
    "we decided",
    "we agreed",
    "let's use",
    "по договоренности",
    "решили",
    "договорились",
    "келістік",
    "шештік",
    "用",
    "决定",
)
_PREFERENCE_CUES = (
    "i prefer",
    "i like",
    "i hate",
    "i use",
    "my stack",
    "предпочитаю",
    "люблю",
    "ненавижу",
    "использую",
    "маған ұнайды",
    "ұнатпаймын",
    "қолданам",
    "我喜欢",
    "我不喜欢",
    "我用",
)
_JOKE_CUES = (
    "inside joke",
    "meme",
    "лол",
    "хаха",
    "ахах",
    "әзіл",
    "қалжың",
    "мем",
    "哈哈",
    "梗",
)


@dataclass(frozen=True)
class MemoryClassification:
    kind: str
    summary: str
    reason: str
    confidence: float


def _contains_any(text: str, cues: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(cue in lowered for cue in cues)


def _is_sensitive(text: str) -> bool:
    lowered = text.lower()
    return bool(_EMAIL_RE.search(text) or _PHONE_RE.search(text) or any(cue in lowered for cue in _SECRET_CUES))


def _should_skip_for_privacy(text: str) -> bool:
    return _is_sensitive(text) or _contains_any(text, _SENSITIVE_CUES)


def classify_long_term_memory(text: str) -> MemoryClassification | None:
    """Classify a message into a trusted long-term memory item, if worth keeping."""
    cleaned = " ".join((text or "").split())
    if len(cleaned) < 12 or _should_skip_for_privacy(cleaned):
        return None

    if _contains_any(cleaned, _GROUP_FACT_CUES):
        return MemoryClassification(
            kind="group_fact",
            summary=cleaned[:280],
            reason="group decision or shared preference",
            confidence=0.72,
        )
    if _contains_any(cleaned, _PREFERENCE_CUES):
        return MemoryClassification(
            kind="user_fact",
            summary=cleaned[:280],
            reason="user stated a preference or recurring personal context",
            confidence=0.7,
        )
    if _contains_any(cleaned, _EVENT_CUES):
        return MemoryClassification(
            kind="event",
            summary=cleaned[:280],
            reason="time-bound event or operational update",
            confidence=0.66,
        )
    if _contains_any(cleaned, _JOKE_CUES):
        return MemoryClassification(
            kind="joke",
            summary=cleaned[:280],
            reason="possible recurring group joke or meme",
            confidence=0.62,
        )
    return None


def process_group_memory_task(body: dict[str, Any], *, repo: GroupMemoryRepository | None = None) -> None:
    """Process one SQS group-memory task and store important long-term memory."""
    repo = repo or GroupMemoryRepository()
    try:
        chat_id = body["chat_id"]
        message_id = body["message_id"]
        user_id = body["user_id"]
        display_name = str(body.get("display_name") or user_id)
        username = body.get("username")
        text = str(body.get("text") or "").strip()
    except KeyError as exc:
        logger.warning("PROCESS_GROUP_MEMORY missing required field", extra={"missing": str(exc)})
        return

    classification = classify_long_term_memory(text)
    if not classification:
        logger.debug("PROCESS_GROUP_MEMORY skipped low-value or sensitive message", extra={"chat_id": chat_id})
        return

    repo.store_long_term_memory(
        chat_id=chat_id,
        message_id=message_id,
        user_id=user_id,
        display_name=display_name,
        username=str(username) if username else None,
        text=text,
        kind=classification.kind,
        summary=classification.summary,
        reason=classification.reason,
        confidence=classification.confidence,
        created_at=body.get("created_at"),
    )
    logger.info(
        "PROCESS_GROUP_MEMORY stored long-term memory",
        extra={"chat_id": chat_id, "message_id": message_id, "kind": classification.kind},
    )
