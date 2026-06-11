"""Async long-term group memory extraction for PROCESS_GROUP_MEMORY tasks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from core.config import GROUP_MEMORY_DAILY_SUMMARY_MESSAGE_LIMIT, get_chat_lang, get_gemini_api_key
from core.logger import LoggerAdapter, get_logger
from services.ai.gemini_client import GeminiClient, GeminiRPDExhaustedError, GeminiUnavailableError
from services.group_memory import format_long_term_memory_context
from services.repositories.group_memory import GroupMemoryRepository
from services.repositories.sqs import SQSClient
from services.vector_memory import vector_memory_configured

logger = LoggerAdapter(get_logger(__name__), {})

_summary_gemini: GeminiClient | None = None

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


@dataclass(frozen=True)
class DailySummaryWindow:
    summary_date: str
    start_epoch: int
    end_epoch: int


def _get_gemini() -> GeminiClient | None:
    global _summary_gemini
    if get_gemini_api_key() and _summary_gemini is None:
        _summary_gemini = GeminiClient()
    return _summary_gemini


def _contains_any(text: str, cues: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(cue in lowered for cue in cues)


def _is_sensitive(text: str) -> bool:
    lowered = text.lower()
    return bool(_EMAIL_RE.search(text) or _PHONE_RE.search(text) or any(cue in lowered for cue in _SECRET_CUES))


def _contains_secret_or_sensitive_cue(text: str) -> bool:
    lowered = text.lower()
    return any(cue in lowered for cue in _SECRET_CUES) or _contains_any(text, _SENSITIVE_CUES)


def _should_skip_for_privacy(text: str) -> bool:
    return _is_sensitive(text) or _contains_any(text, _SENSITIVE_CUES)


def _redact_for_summary(text: str) -> str:
    redacted = _EMAIL_RE.sub("[email]", text)
    redacted = _PHONE_RE.sub("[phone]", redacted)
    return redacted


def _list_field(value: Any, *, limit: int = 12) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").replace("\n", " ").strip()
        if text:
            result.append(text[:180])
        if len(result) >= limit:
            break
    return result


def _summary_window(summary_date: str | None = None) -> DailySummaryWindow:
    if summary_date:
        day = date.fromisoformat(summary_date)
    else:
        day = datetime.now(UTC).date() - timedelta(days=1)
    start = datetime.combine(day, time.min, tzinfo=UTC)
    end = start + timedelta(days=1)
    return DailySummaryWindow(
        summary_date=day.isoformat(),
        start_epoch=int(start.timestamp()),
        end_epoch=int(end.timestamp()),
    )


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


def _fallback_daily_summary(
    *,
    summary_date: str,
    messages: list[dict[str, Any]],
    long_term_memory_context: str,
) -> dict[str, Any]:
    participants: list[str] = []
    seen: set[str] = set()
    for message in messages:
        name = str(message.get("display_name") or message.get("username") or message.get("user_id") or "Unknown")
        if name not in seen:
            seen.add(name)
            participants.append(name[:80])
        if len(participants) >= 12:
            break

    event_lines = []
    for line in long_term_memory_context.splitlines():
        if "[event " in line or "[group_fact " in line:
            event_lines.append(line.split("] ", 1)[-1][:180])
        if len(event_lines) >= 6:
            break

    return {
        "summary": f"{summary_date}: observed {len(messages)} group messages. AI summary was unavailable.",
        "topics": [],
        "notable_events": event_lines,
        "inside_jokes": [],
        "active_participants": participants,
        "tension_points": [],
        "source": "fallback",
    }


def _normalise_daily_summary(raw: dict[str, Any], *, summary_date: str, source: str) -> dict[str, Any]:
    summary = str(raw.get("summary") or "").replace("\n", " ").strip()
    if not summary:
        summary = f"{summary_date}: group activity summary."
    return {
        "summary": summary[:1200],
        "topics": _list_field(raw.get("topics")),
        "notable_events": _list_field(raw.get("notable_events")),
        "inside_jokes": _list_field(raw.get("inside_jokes"), limit=8),
        "active_participants": _list_field(raw.get("active_participants"), limit=20),
        "tension_points": _list_field(raw.get("tension_points"), limit=8),
        "source": source,
    }


def build_daily_messages_context(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in messages:
        if _contains_secret_or_sensitive_cue(str(item.get("text") or "")):
            continue
        name = str(item.get("display_name") or item.get("username") or item.get("user_id") or "Unknown")
        text = _redact_for_summary(str(item.get("text") or "")).replace("\n", " ").strip()
        if text:
            lines.append(f"{name[:80]}: {text[:500]}")
    return "\n".join(lines)


def _enqueue_vector_memory_index(
    *,
    chat_id: int | str,
    source_sk: str,
    sqs_repo: SQSClient | None = None,
) -> None:
    if not vector_memory_configured():
        return
    try:
        (sqs_repo or SQSClient()).send_vector_memory_task(
            chat_id=chat_id,
            source_sk=source_sk,
            reason="memory_write",
        )
    except Exception:
        logger.exception(
            "Failed to enqueue vector memory indexing",
            extra={"chat_id": chat_id, "source_sk": source_sk},
        )


def process_daily_group_summary(
    *,
    chat_id: int | str,
    summary_date: str | None = None,
    repo: GroupMemoryRepository | None = None,
    sqs_repo: SQSClient | None = None,
) -> bool:
    """Build and store one daily summary for a memory-enabled group."""
    repo = repo or GroupMemoryRepository()
    if not repo.is_memory_enabled(chat_id):
        logger.info("Daily group summary skipped because memory is disabled", extra={"chat_id": chat_id})
        return False

    window = _summary_window(summary_date)
    messages = repo.get_messages_for_day(
        chat_id,
        start_epoch=window.start_epoch,
        end_epoch=window.end_epoch,
        limit=GROUP_MEMORY_DAILY_SUMMARY_MESSAGE_LIMIT,
    )
    if not messages:
        logger.info("Daily group summary skipped because no messages were found", extra={"chat_id": chat_id})
        return False

    messages_context = build_daily_messages_context(messages)
    if not messages_context:
        logger.info("Daily group summary skipped because messages were sensitive-only", extra={"chat_id": chat_id})
        return False

    long_term_memory_context = format_long_term_memory_context(repo, chat_id, limit=20)
    raw_summary: dict[str, Any]
    source = "gemini"
    gemini = _get_gemini()
    if gemini:
        try:
            raw_summary, _ = gemini.group_daily_summary(
                summary_date=window.summary_date,
                messages_context=messages_context,
                long_term_memory_context=long_term_memory_context,
                lang=get_chat_lang(chat_id),
            )
        except GeminiRPDExhaustedError:
            logger.info(
                "Daily group summary using fallback because Gemini RPD is exhausted", extra={"chat_id": chat_id}
            )
            raw_summary = _fallback_daily_summary(
                summary_date=window.summary_date,
                messages=messages,
                long_term_memory_context=long_term_memory_context,
            )
            source = "fallback_rpd"
        except GeminiUnavailableError:
            logger.warning(
                "Daily group summary using fallback because Gemini is unavailable", extra={"chat_id": chat_id}
            )
            raw_summary = _fallback_daily_summary(
                summary_date=window.summary_date,
                messages=messages,
                long_term_memory_context=long_term_memory_context,
            )
            source = "fallback_unavailable"
    else:
        raw_summary = _fallback_daily_summary(
            summary_date=window.summary_date,
            messages=messages,
            long_term_memory_context=long_term_memory_context,
        )
        source = "fallback_no_gemini"

    summary = _normalise_daily_summary(raw_summary, summary_date=window.summary_date, source=source)
    item = repo.store_daily_summary(
        chat_id=chat_id,
        summary_date=window.summary_date,
        summary=summary["summary"],
        topics=summary["topics"],
        notable_events=summary["notable_events"],
        inside_jokes=summary["inside_jokes"],
        active_participants=summary["active_participants"],
        tension_points=summary["tension_points"],
        message_count=len(messages),
        source=summary["source"],
    )
    _enqueue_vector_memory_index(chat_id=chat_id, source_sk=str(item["sk"]), sqs_repo=sqs_repo)
    logger.info(
        "Daily group summary stored",
        extra={"chat_id": chat_id, "summary_date": window.summary_date, "message_count": len(messages)},
    )
    return True


def process_daily_group_summaries_task(
    body: dict[str, Any],
    *,
    repo: GroupMemoryRepository | None = None,
    sqs_repo: SQSClient | None = None,
) -> None:
    """Process a scheduled SQS task for one or more configured groups."""
    repo = repo or GroupMemoryRepository()
    chat_ids = body.get("chat_ids")
    if not isinstance(chat_ids, list) or not chat_ids:
        logger.warning("PROCESS_DAILY_GROUP_SUMMARIES missing chat_ids")
        return

    stored = 0
    for chat_id in chat_ids:
        if process_daily_group_summary(
            chat_id=chat_id,
            summary_date=body.get("summary_date"),
            repo=repo,
            sqs_repo=sqs_repo,
        ):
            stored += 1
    logger.info("Daily group summaries task completed", extra={"requested": len(chat_ids), "stored": stored})


def process_group_memory_task(
    body: dict[str, Any],
    *,
    repo: GroupMemoryRepository | None = None,
    sqs_repo: SQSClient | None = None,
) -> None:
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

    item = repo.store_long_term_memory(
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
    _enqueue_vector_memory_index(chat_id=chat_id, source_sk=str(item["sk"]), sqs_repo=sqs_repo)
    logger.info(
        "PROCESS_GROUP_MEMORY stored long-term memory",
        extra={"chat_id": chat_id, "message_id": message_id, "kind": classification.kind},
    )
