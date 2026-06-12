"""Async long-term group memory extraction for PROCESS_GROUP_MEMORY tasks."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from core.config import (
    GROUP_MEMORY_DAILY_SUMMARY_MESSAGE_LIMIT,
    GROUP_MEMORY_EXTRACTOR_DAILY_LLM_LIMIT,
    GROUP_MEMORY_EXTRACTOR_MIN_CONFIDENCE,
    GROUP_MEMORY_EXTRACTOR_MODE,
    GROUP_MEMORY_EXTRACTOR_PER_CHAT_DAILY_LIMIT,
    GROUP_MEMORY_EXTRACTOR_PROVIDER,
    get_chat_lang,
    get_gemini_api_key,
)
from core.logger import LoggerAdapter, get_logger
from services.ai.gemini_client import GeminiClient, GeminiRPDExhaustedError, GeminiUnavailableError
from services.group_memory import format_long_term_memory_context
from services.memory_extractor import (
    ExtractedMemory,
    MemoryClassification,
    classify_long_term_memory_rule_based,
    contains_secret_or_sensitive_cue,
    extract_long_term_memory_llm,
    is_storable_extracted_memory,
    redact_sensitive_for_summary,
    should_skip_for_privacy,
    storage_memory_kind,
)
from services.memory_safety import is_memory_learning_safe
from services.repositories.group_memory import GroupMemoryRepository
from services.repositories.rate_limit import RateLimitRepository
from services.repositories.sqs import SQSClient
from services.vector_memory import vector_memory_configured

logger = LoggerAdapter(get_logger(__name__), {})

_summary_gemini: GeminiClient | None = None
_EXTRACTOR_BUDGET_SCOPE = "group_memory_extractor_llm"
_LONG_FORM_SAMPLE_MODULO = 20
_CANDIDATE_CUE_RE = re.compile(
    r"\b("
    r"agreed|decided|decision|deadline|deploy(?:ed|ing)?|incident|issue|outage|postmortem|"
    r"prefer|preference|my stack|i use|we use|workaround|root cause|migration|release|"
    r"meme|joke|inside joke|open.?search|s3 vectors?|lambda|dynamodb|backfill|vector"
    r")\b|"
    r"(шештік|келістік|қолданам|ұнайды|мерзім|деплой|оқиға|мәселе|әзіл)|"
    r"(решили|договорились|предпочитаю|использую|дедлайн|деплой|инцидент|проблема|мем|шутк)|"
    r"(决定|同意|偏好|我用|截止|部署|事故|问题|梗|玩笑)",
    re.IGNORECASE,
)
_TECH_TERM_RE = re.compile(
    r"\b("
    r"aws|api|cdk|ci|deploy|dynamodb|gemini|lambda|opensearch|postgres|python|rag|s3|sqs|"
    r"vector|vectors|webhook|[a-z]+-\d+|[a-z]+\d{2,}"
    r")\b",
    re.IGNORECASE,
)

__all__ = [
    "DailySummaryWindow",
    "MemoryClassification",
    "build_daily_messages_context",
    "classify_long_term_memory",
    "classify_long_term_memory_rule_based",
    "is_gemini_extraction_candidate",
    "process_daily_group_summaries_task",
    "process_daily_group_summary",
    "process_group_memory_task",
]


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


classify_long_term_memory = classify_long_term_memory_rule_based


def _normalise_extractor_mode(provider: str, mode: str) -> str:
    provider = provider.strip().lower()
    mode = mode.strip().lower()
    if provider == "rules" or mode in {"rules", "rule", "rules_only"}:
        return "rules"
    if mode in {"gemini_all", "all"}:
        return "gemini_all"
    if mode in {"gemini_candidate_only", "candidate", "candidate_only", ""}:
        return "gemini_candidate_only"
    logger.warning("Unknown group memory extractor mode; using gemini_candidate_only", extra={"mode": mode})
    return "gemini_candidate_only"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _sample_long_form_candidate(text: str, message_id: int | str | None) -> bool:
    seed = f"{message_id or ''}:{text[:240]}".encode("utf-8", "ignore")
    digest = hashlib.blake2s(seed, digest_size=2).digest()
    return int.from_bytes(digest, "big") % _LONG_FORM_SAMPLE_MODULO == 0


def is_gemini_extraction_candidate(
    text: str,
    *,
    rule_based: ExtractedMemory | None = None,
    is_reply: bool = False,
    has_mention: bool = False,
    message_id: int | str | None = None,
) -> tuple[bool, str]:
    """Cheaply decide whether an ordinary group message deserves LLM extraction."""
    cleaned = " ".join((text or "").split())
    if rule_based is not None:
        return True, f"rule_{rule_based.kind}"
    if _CANDIDATE_CUE_RE.search(cleaned):
        return True, "cue"
    if (is_reply or has_mention) and len(cleaned) >= 40:
        return True, "reply_or_mention"
    if len(cleaned) >= 180 and _TECH_TERM_RE.search(cleaned) and _sample_long_form_candidate(cleaned, message_id):
        return True, "long_form_technical_sample"
    return False, "no_candidate_signal"


def _budget_scope_part(value: int | str) -> str:
    return re.sub(r"[^0-9A-Za-z_-]+", "_", str(value))[:80]


def _reserve_extractor_llm_budget(chat_id: int | str, message_id: int | str) -> bool:
    if GROUP_MEMORY_EXTRACTOR_DAILY_LLM_LIMIT <= 0 or GROUP_MEMORY_EXTRACTOR_PER_CHAT_DAILY_LIMIT <= 0:
        logger.info(
            "Group memory Gemini extraction skipped by disabled LLM budget",
            extra={
                "chat_id": chat_id,
                "message_id": message_id,
                "daily_limit": GROUP_MEMORY_EXTRACTOR_DAILY_LLM_LIMIT,
                "per_chat_limit": GROUP_MEMORY_EXTRACTOR_PER_CHAT_DAILY_LIMIT,
            },
        )
        return False

    chat_scope = f"{_EXTRACTOR_BUDGET_SCOPE}_chat_{_budget_scope_part(chat_id)}"
    chat_count, chat_within_limit = RateLimitRepository(
        scope=chat_scope,
        rpd_limit=GROUP_MEMORY_EXTRACTOR_PER_CHAT_DAILY_LIMIT,
    ).increment_and_check()
    if not chat_within_limit:
        logger.info(
            "Group memory Gemini extraction skipped by per-chat daily budget",
            extra={
                "chat_id": chat_id,
                "message_id": message_id,
                "extractor_llm_chat_count": chat_count,
                "extractor_llm_chat_limit": GROUP_MEMORY_EXTRACTOR_PER_CHAT_DAILY_LIMIT,
            },
        )
        return False

    daily_count, daily_within_limit = RateLimitRepository(
        scope=_EXTRACTOR_BUDGET_SCOPE,
        rpd_limit=GROUP_MEMORY_EXTRACTOR_DAILY_LLM_LIMIT,
    ).increment_and_check()
    if not daily_within_limit:
        logger.info(
            "Group memory Gemini extraction skipped by global daily budget",
            extra={
                "chat_id": chat_id,
                "message_id": message_id,
                "extractor_llm_daily_count": daily_count,
                "extractor_llm_daily_limit": GROUP_MEMORY_EXTRACTOR_DAILY_LLM_LIMIT,
            },
        )
        return False
    return True


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
    if not summary or not is_memory_learning_safe(summary):
        summary = f"{summary_date}: group activity summary."
    return {
        "summary": summary[:1200],
        "topics": [item for item in _list_field(raw.get("topics")) if is_memory_learning_safe(item)],
        "notable_events": [item for item in _list_field(raw.get("notable_events")) if is_memory_learning_safe(item)],
        "inside_jokes": [
            item for item in _list_field(raw.get("inside_jokes"), limit=8) if is_memory_learning_safe(item)
        ],
        "active_participants": _list_field(raw.get("active_participants"), limit=20),
        "tension_points": [
            item for item in _list_field(raw.get("tension_points"), limit=8) if is_memory_learning_safe(item)
        ],
        "source": source,
    }


def build_daily_messages_context(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in messages:
        if contains_secret_or_sensitive_cue(str(item.get("text") or "")):
            continue
        name = str(item.get("display_name") or item.get("username") or item.get("user_id") or "Unknown")
        text = redact_sensitive_for_summary(str(item.get("text") or "")).replace("\n", " ").strip()
        if text and is_memory_learning_safe(text):
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


def _extract_long_term_memory(
    *,
    chat_id: int | str,
    message_id: int | str,
    user_id: int | str,
    display_name: str,
    username: str | None,
    text: str,
    is_reply: bool = False,
    has_mention: bool = False,
) -> ExtractedMemory | None:
    cleaned = " ".join((text or "").split())
    if len(cleaned) < 12 or should_skip_for_privacy(cleaned) or not is_memory_learning_safe(cleaned):
        return None

    provider = GROUP_MEMORY_EXTRACTOR_PROVIDER.strip().lower()
    mode = _normalise_extractor_mode(provider, GROUP_MEMORY_EXTRACTOR_MODE)
    rule_based = classify_long_term_memory_rule_based(cleaned, message_id=message_id, user_id=user_id)
    if mode == "rules":
        return rule_based
    if provider != "gemini":
        logger.warning(
            "Unknown group memory extractor provider; using rules",
            extra={"chat_id": chat_id, "message_id": message_id, "provider": provider},
        )
        return rule_based

    candidate_reason = "gemini_all"
    if mode == "gemini_candidate_only":
        is_candidate, candidate_reason = is_gemini_extraction_candidate(
            cleaned,
            rule_based=rule_based,
            is_reply=is_reply,
            has_mention=has_mention,
            message_id=message_id,
        )
        if not is_candidate:
            logger.debug(
                "Group memory extraction using rules because message is not an LLM candidate",
                extra={"chat_id": chat_id, "message_id": message_id, "candidate_reason": candidate_reason},
            )
            return rule_based

    gemini = _get_gemini()
    if not gemini:
        logger.info(
            "Group memory extraction using rules because Gemini is not configured",
            extra={"chat_id": chat_id, "message_id": message_id, "candidate_reason": candidate_reason},
        )
        return rule_based

    if not _reserve_extractor_llm_budget(chat_id, message_id):
        return rule_based

    try:
        extracted = extract_long_term_memory_llm(
            gemini=gemini,
            chat_id=chat_id,
            message_id=message_id,
            user_id=user_id,
            display_name=display_name,
            username=username,
            text=cleaned,
            lang=get_chat_lang(chat_id),
        )
        logger.info(
            "Group memory extraction used Gemini",
            extra={"chat_id": chat_id, "message_id": message_id, "candidate_reason": candidate_reason},
        )
        return extracted
    except GeminiRPDExhaustedError:
        logger.info(
            "Group memory extraction using rules because Gemini RPD is exhausted",
            extra={"chat_id": chat_id, "message_id": message_id, "candidate_reason": candidate_reason},
        )
    except GeminiUnavailableError:
        logger.warning(
            "Group memory extraction using rules because Gemini is unavailable",
            extra={"chat_id": chat_id, "message_id": message_id, "candidate_reason": candidate_reason},
        )
    except Exception:
        logger.exception(
            "Group memory extraction using rules because Gemini extractor failed",
            extra={"chat_id": chat_id, "message_id": message_id, "candidate_reason": candidate_reason},
        )

    return rule_based


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

    extracted = _extract_long_term_memory(
        chat_id=chat_id,
        message_id=message_id,
        user_id=user_id,
        display_name=display_name,
        username=str(username) if username else None,
        text=text,
        is_reply=_truthy(body.get("is_reply")),
        has_mention=_truthy(body.get("has_mention")),
    )
    if not is_storable_extracted_memory(
        extracted,
        min_confidence=GROUP_MEMORY_EXTRACTOR_MIN_CONFIDENCE,
        speaker_user_id=user_id,
    ):
        logger.debug(
            "PROCESS_GROUP_MEMORY skipped low-value or sensitive message",
            extra={
                "chat_id": chat_id,
                "message_id": message_id,
                "extractor_source": extracted.extractor_source if extracted else "",
                "kind": extracted.kind if extracted else "",
                "sensitivity": extracted.sensitivity if extracted else "",
                "confidence": extracted.confidence if extracted else 0.0,
            },
        )
        return

    assert extracted is not None
    storage_kind = storage_memory_kind(extracted)
    if storage_kind is None:
        logger.debug("PROCESS_GROUP_MEMORY skipped unsupported memory kind", extra={"chat_id": chat_id})
        return
    store_user_id = extracted.subject_user_id if storage_kind == "user_fact" and extracted.subject_user_id else user_id
    item = repo.store_long_term_memory(
        chat_id=chat_id,
        message_id=message_id,
        user_id=store_user_id,
        display_name=display_name,
        username=str(username) if username else None,
        text=text,
        kind=storage_kind,
        summary=extracted.summary,
        reason=extracted.reason,
        confidence=extracted.confidence,
        created_at=body.get("created_at"),
        extractor_source=extracted.extractor_source,
        expires_in_days=extracted.expires_in_days,
        evidence_message_ids=extracted.evidence_message_ids,
        sensitivity=extracted.sensitivity,
    )
    _enqueue_vector_memory_index(chat_id=chat_id, source_sk=str(item["sk"]), sqs_repo=sqs_repo)
    logger.info(
        "PROCESS_GROUP_MEMORY stored long-term memory",
        extra={
            "chat_id": chat_id,
            "message_id": message_id,
            "kind": storage_kind,
            "extractor_source": extracted.extractor_source,
        },
    )
