"""Structured long-term memory extraction for group messages."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from services.ai.gemini_client import GeminiClient
from services.memory_safety import is_memory_learning_safe

MemoryKind = Literal["event", "user_fact", "group_fact", "joke", "boundary", "preference", "none"]
StorageMemoryKind = Literal["event", "user_fact", "group_fact", "joke"]
Sensitivity = Literal["public", "personal", "sensitive", "secret"]
ExtractorSource = Literal["gemini", "rules"]

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b")
_PHONE_RE = re.compile(r"(?<![\w+])(?:\+\d[\d\s().-]{7,}\d|\d{10,15})(?!\w)")
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
_ALLOWED_KINDS: set[str] = {"event", "user_fact", "group_fact", "joke", "boundary", "preference", "none"}
_ALLOWED_SENSITIVITIES: set[str] = {"public", "personal", "sensitive", "secret"}


@dataclass(frozen=True)
class ExtractedMemory:
    should_store: bool = True
    kind: MemoryKind = "none"
    summary: str = ""
    reason: str = ""
    confidence: float = 0.0
    subject_user_id: str | None = None
    sensitivity: Sensitivity = "public"
    expires_in_days: int | None = None
    evidence_message_ids: list[int] = field(default_factory=list)
    extractor_source: ExtractorSource = "rules"


MemoryClassification = ExtractedMemory


def contains_any(text: str, cues: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(cue in lowered for cue in cues)


def is_sensitive_text(text: str) -> bool:
    lowered = text.lower()
    return bool(_EMAIL_RE.search(text) or _PHONE_RE.search(text) or any(cue in lowered for cue in _SECRET_CUES))


def contains_secret_or_sensitive_cue(text: str) -> bool:
    lowered = text.lower()
    return any(cue in lowered for cue in _SECRET_CUES) or contains_any(text, _SENSITIVE_CUES)


def should_skip_for_privacy(text: str) -> bool:
    return is_sensitive_text(text) or contains_any(text, _SENSITIVE_CUES)


def redact_sensitive_for_summary(text: str) -> str:
    redacted = _EMAIL_RE.sub("[email]", text)
    redacted = _PHONE_RE.sub("[phone]", redacted)
    return redacted


def classify_long_term_memory_rule_based(
    text: str,
    *,
    message_id: int | str | None = None,
    user_id: int | str | None = None,
) -> ExtractedMemory | None:
    """Classify a message into a trusted long-term memory item, if worth keeping."""
    cleaned = " ".join((text or "").split())
    if len(cleaned) < 12 or should_skip_for_privacy(cleaned) or not is_memory_learning_safe(cleaned):
        return None

    evidence = _normalise_evidence_message_ids([], fallback_message_id=message_id)
    subject_user_id = str(user_id) if user_id is not None else None
    if contains_any(cleaned, _GROUP_FACT_CUES):
        return ExtractedMemory(
            should_store=True,
            kind="group_fact",
            summary=cleaned[:280],
            reason="group decision or shared preference",
            confidence=0.72,
            sensitivity="public",
            evidence_message_ids=evidence,
            extractor_source="rules",
        )
    if contains_any(cleaned, _PREFERENCE_CUES):
        return ExtractedMemory(
            should_store=True,
            kind="user_fact",
            summary=cleaned[:280],
            reason="user stated a preference or recurring personal context",
            confidence=0.7,
            subject_user_id=subject_user_id,
            sensitivity="personal",
            evidence_message_ids=evidence,
            extractor_source="rules",
        )
    if contains_any(cleaned, _EVENT_CUES):
        return ExtractedMemory(
            should_store=True,
            kind="event",
            summary=cleaned[:280],
            reason="time-bound event or operational update",
            confidence=0.66,
            sensitivity="public",
            evidence_message_ids=evidence,
            extractor_source="rules",
        )
    if contains_any(cleaned, _JOKE_CUES):
        return ExtractedMemory(
            should_store=True,
            kind="joke",
            summary=cleaned[:280],
            reason="possible recurring group joke or meme",
            confidence=0.62,
            sensitivity="public",
            evidence_message_ids=evidence,
            extractor_source="rules",
        )
    return None


def extract_long_term_memory_llm(
    *,
    gemini: GeminiClient,
    chat_id: int | str,
    message_id: int | str,
    user_id: int | str,
    display_name: str,
    username: str | None,
    text: str,
    lang: str,
) -> ExtractedMemory:
    """Ask Gemini for structured memory extraction and normalise the schema."""
    raw, _ = gemini.group_memory_extraction(
        chat_id=chat_id,
        message_id=message_id,
        user_id=user_id,
        display_name=display_name,
        username=username,
        text=text,
        lang=lang,
    )
    return normalise_extracted_memory(raw, message_id=message_id, user_id=user_id, extractor_source="gemini")


def normalise_extracted_memory(
    raw: dict[str, Any],
    *,
    message_id: int | str | None,
    user_id: int | str | None,
    extractor_source: ExtractorSource,
) -> ExtractedMemory:
    """Clamp untrusted LLM JSON to the extractor schema."""
    if not isinstance(raw, dict):
        return _empty_memory(message_id=message_id, user_id=user_id, extractor_source=extractor_source)
    kind = str(raw.get("kind") or "none").strip().lower()
    if kind not in _ALLOWED_KINDS:
        kind = "none"
    sensitivity = str(raw.get("sensitivity") or "public").strip().lower()
    if sensitivity not in _ALLOWED_SENSITIVITIES:
        sensitivity = "sensitive"
    summary = str(raw.get("summary") or "").replace("\n", " ").strip()
    reason = str(raw.get("reason") or "").replace("\n", " ").strip()
    confidence = _clamped_float(raw.get("confidence"), default=0.0)
    should_store = _normalise_bool(raw.get("should_store")) and kind != "none"
    if not summary or not is_memory_learning_safe(summary) or not is_memory_learning_safe(reason):
        should_store = False
    subject_user_id = raw.get("subject_user_id")
    if subject_user_id in ("", "null"):
        subject_user_id = None
    if subject_user_id is not None:
        subject_user_id = str(subject_user_id)
    elif kind in {"user_fact", "preference", "boundary"} and user_id is not None:
        subject_user_id = str(user_id)

    return ExtractedMemory(
        should_store=should_store,
        kind=kind,  # type: ignore[arg-type]
        summary=summary[:500],
        reason=reason[:240],
        confidence=confidence,
        subject_user_id=subject_user_id,
        sensitivity=sensitivity,  # type: ignore[arg-type]
        expires_in_days=_normalise_expiry(raw.get("expires_in_days")),
        evidence_message_ids=_normalise_evidence_message_ids(raw.get("evidence_message_ids"), message_id),
        extractor_source=extractor_source,
    )


def storage_memory_kind(memory: ExtractedMemory) -> StorageMemoryKind | None:
    if memory.kind in {"preference", "boundary"}:
        return "user_fact"
    if memory.kind in {"event", "user_fact", "group_fact", "joke"}:
        return memory.kind
    return None


def is_storable_extracted_memory(
    memory: ExtractedMemory | None,
    *,
    min_confidence: float,
    speaker_user_id: int | str,
) -> bool:
    if memory is None or not memory.should_store:
        return False
    if memory.confidence < min_confidence:
        return False
    if memory.sensitivity in {"sensitive", "secret"}:
        return False
    if not storage_memory_kind(memory):
        return False
    if not memory.summary or not is_memory_learning_safe(memory.summary):
        return False
    if storage_memory_kind(memory) == "user_fact" and memory.subject_user_id not in (None, str(speaker_user_id)):
        return False
    return True


def _empty_memory(
    *,
    message_id: int | str | None,
    user_id: int | str | None,
    extractor_source: ExtractorSource,
) -> ExtractedMemory:
    return ExtractedMemory(
        should_store=False,
        kind="none",
        summary="",
        reason="invalid extractor output",
        confidence=0.0,
        subject_user_id=str(user_id) if user_id is not None else None,
        sensitivity="public",
        evidence_message_ids=_normalise_evidence_message_ids([], message_id),
        extractor_source=extractor_source,
    )


def _normalise_expiry(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        days = int(value)
    except (TypeError, ValueError):
        return None
    if days <= 0:
        return None
    return min(days, 3650)


def _normalise_evidence_message_ids(value: Any, fallback_message_id: int | str | None) -> list[int]:
    ids: list[int] = []
    if isinstance(value, list):
        for item in value:
            try:
                ids.append(int(item))
            except (TypeError, ValueError):
                continue
            if len(ids) >= 12:
                break
    if not ids and fallback_message_id is not None:
        try:
            ids.append(int(fallback_message_id))
        except (TypeError, ValueError):
            pass
    return ids


def _clamped_float(value: Any, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


def _normalise_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
