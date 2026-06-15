"""Context-aware group chat agent helpers."""

from __future__ import annotations

import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.config import (
    AGENT_BOT_ID,
    AGENT_BOT_USERNAME,
    AGENT_DAILY_PROACTIVE_LIMIT,
    AGENT_ENABLED,
    AGENT_PROACTIVE_DELAY_SECONDS,
    AGENT_PROACTIVE_FINAL_THRESHOLD,
    AGENT_RECENT_CONTEXT_LIMIT,
    get_chat_lang,
    get_gemini_api_key,
)
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.ai.channel_post_comment import (
    FallbackChannelPostCommentProvider,
    create_channel_post_comment_fallback_provider,
)
from services.ai.gemini_client import (
    GeminiClient,
    GeminiRPDExhaustedError,
    GeminiUnavailableError,
    GroupAgentDecision,
)
from services.ai.group_chat_reply_fallback import (
    FallbackGroupChatReplyProvider,
    create_group_chat_reply_fallback_provider,
)
from services.ai.proactive_decision import (
    FallbackProactiveDecisionProvider,
    create_proactive_decision_provider,
)
from services.ai.telegram_html import (
    fit_llm_output,
    normalize_llm_output_for_telegram_html,
)
from services.bot_identity import is_self_bot_user
from services.group_memory import (
    display_name,
    extract_message_text,
    format_long_term_memory_context,
    format_message_reference,
    format_recent_context,
    format_requester_profile_context,
    format_user_profile_context,
)
from services.memory_retrieval import build_agent_memory_context
from services.memory_safety import (
    looks_like_future_answer_directive,
    looks_like_subjective_person_ranking_question,
)
from services.repositories.group_memory import (
    GroupMemoryRepository,
    normalise_chat_style_profile,
)
from services.repositories.sqs import SQSClient
from services.telegram import TelegramClient
from services.telegram_actor import (
    actor_display_name,
    actor_sender_type,
    actor_username,
    is_linked_channel_discussion_post,
    message_actor,
)
from services.telegram_media import (
    MediaDisabledError,
    MediaError,
    MediaTooLargeError,
    MediaUnavailableError,
    MediaUnsupportedError,
    detect_media_reference,
    media_reference_log_extra,
    prepare_media_for_gemini,
)
from services.vector_memory import (
    format_semantic_memory_context,
    retrieve_relevant_memories,
)
from zerde_common.ai_errors import ProviderResponseError, ZerdeProviderError

logger = LoggerAdapter(get_logger(__name__), {})

_agent_gemini: GeminiClient | None = None
_channel_post_comment_fallback: FallbackChannelPostCommentProvider | None = None
_group_chat_reply_fallback: FallbackGroupChatReplyProvider | None = None
_proactive_decision_provider: FallbackProactiveDecisionProvider | None = None

CHANNEL_POST_GEMINI_MAX_ATTEMPTS = 3
CHANNEL_POST_GEMINI_RETRY_DELAYS_SECONDS: tuple[float, ...] = (1.0, 2.0)
GROUP_CHAT_REPLY_GEMINI_MAX_ATTEMPTS = 3
GROUP_CHAT_REPLY_GEMINI_RETRY_DELAYS_SECONDS: tuple[float, ...] = (1.0, 2.0)


@dataclass(frozen=True)
class ReplyPolicy:
    instructions: str
    max_output_tokens: int
    max_chars: int


@dataclass(frozen=True)
class ExplicitQuestionContext:
    user_text: str
    current_user_message: str
    retrieval_query: str
    source_message_context: str = ""
    parent_bot_message_id: int | None = None


_LOW_CONFIDENCE_MEMORY_THRESHOLD = 0.55
_WEAK_RETRIEVAL_DISTANCE_THRESHOLD = 0.78


def _get_gemini() -> GeminiClient | None:
    global _agent_gemini
    if get_gemini_api_key() and _agent_gemini is None:
        _agent_gemini = GeminiClient()
    return _agent_gemini


def _get_channel_post_comment_fallback() -> FallbackChannelPostCommentProvider | None:
    global _channel_post_comment_fallback
    if _channel_post_comment_fallback is None:
        _channel_post_comment_fallback = create_channel_post_comment_fallback_provider()
    return _channel_post_comment_fallback


def _get_group_chat_reply_fallback() -> FallbackGroupChatReplyProvider | None:
    global _group_chat_reply_fallback
    if _group_chat_reply_fallback is None:
        _group_chat_reply_fallback = create_group_chat_reply_fallback_provider()
    return _group_chat_reply_fallback


def _get_proactive_decision_provider() -> FallbackProactiveDecisionProvider | None:
    global _proactive_decision_provider
    if _proactive_decision_provider is None:
        _proactive_decision_provider = create_proactive_decision_provider()
    return _proactive_decision_provider


def _is_plain_text_message(update: dict[str, Any]) -> bool:
    message = update.get("message")
    if not isinstance(message, dict):
        return False
    chat = message.get("chat") or {}
    if chat.get("type") not in {"group", "supergroup"}:
        return False
    text = extract_message_text(message)
    return bool(text and not text.startswith("/"))


def _mentions_bot(text: str) -> bool:
    if not AGENT_BOT_USERNAME:
        return False
    return re.search(rf"@{re.escape(AGENT_BOT_USERNAME)}\b", text, flags=re.IGNORECASE) is not None


def _replies_to_bot(message: dict[str, Any]) -> bool:
    reply = message.get("reply_to_message")
    if not isinstance(reply, dict):
        return False
    sender = reply.get("from") or {}
    return is_self_bot_user(sender, bot_id=AGENT_BOT_ID, bot_username=AGENT_BOT_USERNAME)


def _replies_to_any_bot(message: dict[str, Any]) -> bool:
    reply = message.get("reply_to_message")
    if not isinstance(reply, dict):
        return False
    sender = reply.get("from") or {}
    return bool(isinstance(sender, dict) and sender.get("is_bot"))


def _reply_text(message: dict[str, Any]) -> str:
    reply = message.get("reply_to_message")
    if not isinstance(reply, dict):
        return ""
    return extract_message_text(reply)


def _load_agent_reply_context(
    repo: GroupMemoryRepository,
    chat_id: int | str,
    *,
    bot_message_id: int | str,
) -> dict[str, Any]:
    try:
        item = repo.get_agent_reply_explanation(chat_id, bot_message_id=bot_message_id)
    except Exception:
        logger.exception("Failed to load previous agent reply context", extra={"chat_id": chat_id})
        return {}
    return item if isinstance(item, dict) else {}


def _agent_reply_thread_context(
    item: dict[str, Any],
    *,
    telegram_reply_text: str,
) -> str:
    source_context = str(item.get("source_message_context") or "").strip()
    media_context = _agent_reply_media_context(item)
    previous_user = str(item.get("current_user_message") or item.get("user_message") or "").strip()
    previous_answer = str(item.get("answer_text") or telegram_reply_text or "").strip()
    parts = ["The user is continuing a thread with this previous bot answer:"]
    if source_context:
        parts.append(f"Original source message for the previous answer:\n{source_context[:1800]}")
    if media_context:
        parts.append(f"Previous explicit media context for the prior answer:\n{media_context}")
    if previous_user:
        parts.append(f"Previous user request:\n{previous_user[:1200]}")
    if previous_answer:
        parts.append(f"Previous bot answer:\n{previous_answer[:1800]}")
    elif telegram_reply_text:
        parts.append(f"Previous bot answer from Telegram reply:\n{telegram_reply_text[:1800]}")
    return "\n\n".join(parts)


def _compact_query_text(text: str, *, limit: int) -> str:
    return " ".join((text or "").split())[:limit]


def _agent_reply_media_context(item: dict[str, Any]) -> str:
    metadata = item.get("media_metadata")
    if not isinstance(metadata, Mapping):
        return ""
    lines: list[str] = []
    media_type = str(metadata.get("media_type") or "").strip()
    if media_type:
        lines.append(f"media_type={media_type}")
    for key in (
        "mime_type",
        "file_name",
        "caption",
        "source_message_id",
        "source_display_name",
    ):
        value = metadata.get(key)
        if value not in (None, ""):
            lines.append(f"{key}={str(value)[:500]}")
    summary = str(metadata.get("media_summary") or item.get("media_summary") or "").strip()
    if summary:
        lines.append(f"media_summary={summary[:900]}")
    return "\n".join(lines)


def _media_summary_from_metadata(answer_text: str, metadata: Mapping[str, Any]) -> str:
    media_type = str(metadata.get("media_type") or "media").replace("_", " ")
    file_name = str(metadata.get("file_name") or "").strip()
    answer = " ".join((answer_text or "").split())
    prefix = f"{media_type} {file_name[:120]}".strip()
    if not answer:
        return prefix[:180]
    return f"{prefix}: {answer[:760]}"


def _text_only_media_context_for_fallback(
    *,
    media_parts: list[dict[str, Any]] | None,
    media_context: str,
) -> str:
    lines: list[str] = []
    if media_context:
        lines.append(media_context)
    if media_parts:
        lines.append(
            "Binary media bytes were not sent to the fallback provider. Use only this metadata/caption context."
        )
    return _compact_query_text("\n".join(lines), limit=6000)


def _group_chat_reply_gemini_retry_delay(attempt: int) -> float:
    index = attempt - 1
    if 0 <= index < len(GROUP_CHAT_REPLY_GEMINI_RETRY_DELAYS_SECONDS):
        return max(0.0, float(GROUP_CHAT_REPLY_GEMINI_RETRY_DELAYS_SECONDS[index]))
    return 0.0


def _try_gemini_group_chat_reply(
    *,
    user_message: str,
    recent_context: str,
    long_term_memory_context: str,
    semantic_memory_context: str,
    user_profile_context: str,
    requester_profile_context: str,
    reply_instructions: str,
    max_output_tokens: int,
    lang: str,
    media_parts: list[dict[str, Any]] | None,
    media_context: str,
    chat_id: int,
    reply_to_message_id: int,
    proactive: bool,
) -> tuple[str, str] | None:
    gemini = _get_gemini()
    if not gemini:
        logger.info(
            "Group agent Gemini reply skipped because Gemini is not configured",
            extra={"chat_id": chat_id, "reply_to_message_id": reply_to_message_id, "proactive": proactive},
        )
        return None

    max_attempts = max(1, int(GROUP_CHAT_REPLY_GEMINI_MAX_ATTEMPTS))
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            answer, _ = gemini.group_chat_reply(
                user_message=user_message,
                recent_context=recent_context,
                long_term_memory_context=long_term_memory_context,
                semantic_memory_context=semantic_memory_context,
                user_profile_context=user_profile_context,
                requester_profile_context=requester_profile_context,
                reply_instructions=reply_instructions,
                max_output_tokens=max_output_tokens,
                lang=lang,
                media_parts=media_parts,
                media_context=media_context,
                proactive=proactive,
            )
            if not answer.strip():
                raise ProviderResponseError("gemini returned empty group chat reply")
            return answer, "gemini"
        except GeminiRPDExhaustedError as exc:
            logger.warning(
                "Gemini group chat reply hit RPD limit; trying text-only fallback",
                extra={"chat_id": chat_id, "reply_to_message_id": reply_to_message_id, "attempt": attempt},
            )
            last_error = exc
            break
        except GeminiUnavailableError as exc:
            last_error = exc
            logger.warning(
                "Gemini group chat reply attempt failed",
                extra={
                    "chat_id": chat_id,
                    "reply_to_message_id": reply_to_message_id,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "error_type": exc.__class__.__name__,
                    "retryable": getattr(exc, "retryable", True),
                },
            )
        except ProviderResponseError as exc:
            last_error = exc
            logger.warning(
                "Gemini group chat reply returned unusable content",
                extra={
                    "chat_id": chat_id,
                    "reply_to_message_id": reply_to_message_id,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "error_type": exc.__class__.__name__,
                },
            )

        if attempt < max_attempts:
            delay = _group_chat_reply_gemini_retry_delay(attempt)
            if delay > 0:
                time.sleep(delay)

    logger.warning(
        "Gemini group chat reply exhausted; trying text-only fallback",
        extra={
            "chat_id": chat_id,
            "reply_to_message_id": reply_to_message_id,
            "attempts": max_attempts,
            "error_type": last_error.__class__.__name__ if last_error else "",
        },
    )
    return None


def _fallback_group_chat_reply(
    *,
    user_message: str,
    recent_context: str,
    long_term_memory_context: str,
    semantic_memory_context: str,
    user_profile_context: str,
    requester_profile_context: str,
    reply_instructions: str,
    max_output_tokens: int,
    lang: str,
    media_parts: list[dict[str, Any]] | None,
    media_context: str,
    proactive: bool,
) -> tuple[str, str]:
    fallback = _get_group_chat_reply_fallback()
    if fallback is None:
        raise ProviderResponseError("No group chat reply fallback providers configured")
    text_only_media_context = _text_only_media_context_for_fallback(
        media_parts=media_parts,
        media_context=media_context,
    )
    answer, provider_name = fallback.generate_reply(
        user_message=user_message,
        recent_context=recent_context,
        long_term_memory_context=long_term_memory_context,
        semantic_memory_context=semantic_memory_context,
        user_profile_context=user_profile_context,
        requester_profile_context=requester_profile_context,
        reply_instructions=reply_instructions,
        max_output_tokens=max_output_tokens,
        lang=lang,
        text_only_media_context=text_only_media_context,
        proactive=proactive,
    )
    if not answer.strip():
        raise ProviderResponseError(f"{provider_name} returned empty group chat reply")
    return answer, provider_name


def _generate_group_chat_reply(
    *,
    user_message: str,
    recent_context: str,
    long_term_memory_context: str,
    semantic_memory_context: str,
    user_profile_context: str,
    requester_profile_context: str,
    reply_instructions: str,
    max_output_tokens: int,
    lang: str,
    media_parts: list[dict[str, Any]] | None,
    media_context: str,
    chat_id: int,
    reply_to_message_id: int,
    proactive: bool = False,
) -> tuple[str, str]:
    answer_provider = _try_gemini_group_chat_reply(
        user_message=user_message,
        recent_context=recent_context,
        long_term_memory_context=long_term_memory_context,
        semantic_memory_context=semantic_memory_context,
        user_profile_context=user_profile_context,
        requester_profile_context=requester_profile_context,
        reply_instructions=reply_instructions,
        max_output_tokens=max_output_tokens,
        lang=lang,
        media_parts=media_parts,
        media_context=media_context,
        chat_id=chat_id,
        reply_to_message_id=reply_to_message_id,
        proactive=proactive,
    )
    if answer_provider is not None:
        return answer_provider
    return _fallback_group_chat_reply(
        user_message=user_message,
        recent_context=recent_context,
        long_term_memory_context=long_term_memory_context,
        semantic_memory_context=semantic_memory_context,
        user_profile_context=user_profile_context,
        requester_profile_context=requester_profile_context,
        reply_instructions=reply_instructions,
        max_output_tokens=max_output_tokens,
        lang=lang,
        media_parts=media_parts,
        media_context=media_context,
        proactive=proactive,
    )


def _reply_source_retrieval_query(*, current_question: str, source_context: str) -> str:
    question = _compact_query_text(current_question, limit=600)
    source = _compact_query_text(source_context, limit=700)
    if question and source:
        return f"{question}\n\nReplied source message: {source}"
    if question:
        return question
    if source:
        return f"Explain replied source message: {source}"
    return ""


def _agent_reply_thread_retrieval_query(
    item: dict[str, Any],
    *,
    followup: str,
    telegram_reply_text: str,
) -> str:
    source_context = _compact_query_text(str(item.get("source_message_context") or ""), limit=700)
    media_context = _compact_query_text(_agent_reply_media_context(item), limit=700)
    previous_user = _compact_query_text(
        str(item.get("current_user_message") or item.get("user_message") or ""),
        limit=600,
    )
    followup_text = _compact_query_text(followup, limit=300)
    parts: list[str] = []
    if followup_text:
        parts.append(f"Current follow-up: {followup_text}")
    if previous_user:
        parts.append(f"Previous user request: {previous_user}")
    if source_context:
        parts.append(f"Original source message: {source_context}")
    if media_context:
        parts.append(f"Previous media summary: {media_context}")
    if len(parts) <= 1:
        fallback_answer = _compact_query_text(str(item.get("answer_text") or telegram_reply_text or ""), limit=400)
        if fallback_answer:
            parts.append(f"Previous bot answer: {fallback_answer}")
    return "\n\n".join(parts)


def build_explicit_question_context(
    repo: GroupMemoryRepository,
    chat_id: int | str,
    message: dict[str, Any],
    *,
    current_text: str | None = None,
) -> ExplicitQuestionContext:
    text = (current_text if current_text is not None else extract_message_text(message)).strip()
    reply = message.get("reply_to_message")
    if not isinstance(reply, dict):
        return ExplicitQuestionContext(user_text=text, current_user_message=text, retrieval_query=text)

    if _replies_to_bot(message):
        replied_text = _reply_text(message)
        parent_bot_message_id = reply.get("message_id")
        item = _load_agent_reply_context(
            repo,
            chat_id,
            bot_message_id=parent_bot_message_id or 0,
        )
        thread_context = _agent_reply_thread_context(
            item,
            telegram_reply_text=replied_text,
        )
        source_context = str(item.get("source_message_context") or "").strip()
        followup = text or "The user replied to the previous bot answer and wants an explanation or continuation."
        return ExplicitQuestionContext(
            user_text=f"{thread_context}\n\nUser follow-up:\n{followup}",
            current_user_message=text,
            retrieval_query=_agent_reply_thread_retrieval_query(
                item,
                followup=followup,
                telegram_reply_text=replied_text,
            ),
            source_message_context=source_context,
            parent_bot_message_id=(int(parent_bot_message_id) if parent_bot_message_id is not None else None),
        )

    source_context = format_message_reference(reply)
    if not source_context:
        return ExplicitQuestionContext(user_text=text, current_user_message=text, retrieval_query=text)
    if text:
        user_text = (
            "The user is asking about this replied-to group message:\n"
            f"{source_context}\n\n"
            "User question:\n"
            f"{text}"
        )
    else:
        user_text = (
            "The user replied to this group message and wants you to explain it or answer based on it:\n"
            f"{source_context}"
        )
    return ExplicitQuestionContext(
        user_text=user_text,
        current_user_message=text,
        retrieval_query=_reply_source_retrieval_query(current_question=text, source_context=source_context),
        source_message_context=source_context,
    )


def _clear_reply_to_bot_request(text: str) -> bool:
    lowered = " ".join((text or "").lower().split())
    if not lowered:
        return False
    if "?" in text or "？" in text:
        return True
    if re.search(
        r"\b(why|how|what|who|where|when|explain|expand|elaborate|detail|details|more|example|examples)\b",
        lowered,
    ):
        return True
    if re.search(
        (
            r"(^|\s)(қалай|неге|не|кім|түсіндір|толық|толығырақ|мысал|как|что|кто|почему|зачем|"
            r"объясни|расскажи|подробнее|поделись)(\s|$|[?.!,])"
        ),
        lowered,
    ):
        return True
    return any(cue in lowered for cue in ("怎么", "为什么", "什么", "谁", "解释", "详细", "展开", "举例"))


def _reply_to_bot_followup_skip_reason(text: str) -> str | None:
    lowered = " ".join((text or "").lower().split())
    if not lowered:
        return "empty_followup"
    if _clear_reply_to_bot_request(text):
        return None
    reaction_cues = (
        "haha",
        "lol",
        "lmao",
        "хаха",
        "ахах",
        "哈哈",
        "thanks",
        "thank you",
        "спасибо",
        "рахмет",
        "ок",
        "okay",
        "interesting",
        "nice",
        "cool",
        "қызық",
        "круто",
    )
    if any(cue in lowered for cue in reaction_cues):
        return "reaction_or_ack"
    return "no_clear_question_or_request"


def _load_chat_style_profile(repo: GroupMemoryRepository, chat_id: int | str) -> dict[str, Any]:
    try:
        settings = repo.get_chat_settings(chat_id)
    except Exception:
        logger.exception(
            "Failed to load chat style profile; using defaults",
            extra={"chat_id": chat_id},
        )
        return normalise_chat_style_profile(None)
    raw = settings.get("style_profile") if isinstance(settings, Mapping) else None
    return normalise_chat_style_profile(raw)


def _sentence_count(profile: Mapping[str, Any], key: str) -> int:
    return int(normalise_chat_style_profile(profile).get(key, 1))


def _style_instruction(style_profile: Mapping[str, Any]) -> str:
    profile = normalise_chat_style_profile(style_profile)
    tone = str(profile["tone"])
    tone_text = {
        "concise": "concise and direct",
        "professional": "professional, calm, and precise",
        "friendly": "friendly, natural, and respectful",
    }.get(tone, "concise and direct")
    humor = (
        "Light humor is allowed only when it fits the chat and does not weaken factual clarity."
        if profile["allow_light_humor"]
        else "Do not add jokes or playful asides unless the user clearly asks for that tone."
    )
    return f"Tone: {tone_text}. {humor}"


def _default_reply_budget(max_sentences: int) -> tuple[int, int]:
    if max_sentences == 5:
        return 300, 1800
    tokens = max(140, min(460, 120 + max_sentences * 36))
    chars = max(700, min(2600, 500 + max_sentences * 260))
    return tokens, chars


def _short_reply_budget(max_sentences: int) -> tuple[int, int]:
    if max_sentences >= 3:
        return 180, 900
    tokens = max(100, 90 + max_sentences * 30)
    chars = max(420, 300 + max_sentences * 200)
    return tokens, chars


def _ask_without_question_budget(max_sentences: int) -> tuple[int, int]:
    if max_sentences == 5:
        return 260, 1400
    tokens = max(130, min(300, 110 + max_sentences * 32))
    chars = max(650, min(1600, 450 + max_sentences * 190))
    return tokens, chars


def _proactive_reply_budget(max_sentences: int) -> tuple[int, int]:
    if max_sentences == 2:
        return 300, 900
    tokens = max(120, min(300, 90 + max_sentences * 70))
    chars = max(420, min(1200, 280 + max_sentences * 310))
    return tokens, chars


def _low_confidence_instruction(style_profile: Mapping[str, Any]) -> str:
    behavior = str(normalise_chat_style_profile(style_profile)["low_confidence_behavior"])
    if behavior == "none":
        return ""
    if behavior == "avoid_weak_memory":
        return (
            "Some retrieved memory is weak. Prefer current and high-trust context; if you must use weak memory, "
            "state uncertainty clearly instead of presenting it as fact."
        )
    return (
        "Some retrieved memory is low confidence or weakly matched. Do not sound certain about it. "
        "Use wording such as 'I may be remembering this imperfectly' or 'from weak memory' when relying on it."
    )


def _compose_reply_instructions(
    base_instruction: str,
    *,
    style_profile: Mapping[str, Any],
    low_confidence_retrieval: bool,
) -> str:
    parts = [base_instruction, _style_instruction(style_profile)]
    if low_confidence_retrieval:
        instruction = _low_confidence_instruction(style_profile)
        if instruction:
            parts.append(instruction)
    return " ".join(part for part in parts if part)


def _float_value(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_low_confidence_retrieval(retrieval_sources: list[dict[str, Any]]) -> bool:
    memory_sources = {"semantic", "lexical", "long_term"}
    for source in retrieval_sources:
        if str(source.get("source") or "") not in memory_sources:
            continue
        confidence = _float_value(source.get("confidence"))
        if confidence is not None and confidence < _LOW_CONFIDENCE_MEMORY_THRESHOLD:
            return True
        distance = _float_value(source.get("distance"))
        if distance is not None and distance > _WEAK_RETRIEVAL_DISTANCE_THRESHOLD:
            return True
        score = _float_value(source.get("score"))
        if confidence is None and distance is None and score is not None and 0 < score < 0.38:
            return True
    return False


def _reply_policy(
    user_text: str,
    *,
    style_profile: Mapping[str, Any] | None = None,
    low_confidence_retrieval: bool = False,
) -> ReplyPolicy:
    style = normalise_chat_style_profile(style_profile)
    lowered = user_text.lower()
    explicit_long = any(
        cue in lowered
        for cue in (
            "подробно",
            "толық",
            "детально",
            "развернуто",
            "deep dive",
            "explain in detail",
            "详细",
            "展开",
        )
    )
    explicit_short = any(
        cue in lowered
        for cue in (
            "қысқа",
            "қысқаша",
            "короче",
            "кратко",
            "short",
            "brief",
            "tl;dr",
            "tldr",
            "总结",
            "简短",
        )
    )
    continuation = "user is continuing a thread with this previous bot answer" in lowered
    ask_without_question = "wants you to explain it or answer based on it" in lowered
    max_default_sentences = _sentence_count(style, "max_default_sentences")

    if explicit_long:
        return ReplyPolicy(
            instructions=_compose_reply_instructions(
                (
                    "The user asked for detail. Answer with the minimum useful detail, up to 5 short paragraphs "
                    "or 6 bullets. Avoid repeating the full context."
                ),
                style_profile=style,
                low_confidence_retrieval=low_confidence_retrieval,
            ),
            max_output_tokens=460,
            max_chars=2600,
        )
    if explicit_short or continuation:
        max_short_sentences = min(3, max_default_sentences)
        tokens, chars = _short_reply_budget(max_short_sentences)
        return ReplyPolicy(
            instructions=_compose_reply_instructions(
                (
                    f"This is a short follow-up. Answer directly in 1-{max_short_sentences} short sentences. "
                    "Do not recap the whole previous answer unless the user asks."
                ),
                style_profile=style,
                low_confidence_retrieval=low_confidence_retrieval,
            ),
            max_output_tokens=tokens,
            max_chars=chars,
        )
    if ask_without_question:
        min_sentences = 1 if max_default_sentences <= 2 else 3
        tokens, chars = _ask_without_question_budget(max_default_sentences)
        return ReplyPolicy(
            instructions=_compose_reply_instructions(
                (
                    "The user asked about a replied-to message without a specific question. "
                    f"Give the main point in {min_sentences}-{max_default_sentences} concise sentences "
                    "or at most 3 bullets."
                ),
                style_profile=style,
                low_confidence_retrieval=low_confidence_retrieval,
            ),
            max_output_tokens=tokens,
            max_chars=chars,
        )
    min_sentences = 1 if max_default_sentences <= 2 else 2
    tokens, chars = _default_reply_budget(max_default_sentences)
    return ReplyPolicy(
        instructions=_compose_reply_instructions(
            (
                f"Answer in {min_sentences}-{max_default_sentences} concise sentences. "
                "Use bullets only when they make the answer easier to scan. "
                "Do not write an essay by default."
            ),
            style_profile=style,
            low_confidence_retrieval=low_confidence_retrieval,
        ),
        max_output_tokens=tokens,
        max_chars=chars,
    )


def _proactive_reply_policy(
    style_profile: Mapping[str, Any] | None = None,
) -> ReplyPolicy:
    style = normalise_chat_style_profile(style_profile)
    max_sentences = _sentence_count(style, "max_proactive_sentences")
    tokens, chars = _proactive_reply_budget(max_sentences)
    return ReplyPolicy(
        instructions=_compose_reply_instructions(
            f"If speaking, write up to {max_sentences} short sentences. Do not lecture or recap the whole chat.",
            style_profile=style,
            low_confidence_retrieval=False,
        ),
        max_output_tokens=tokens,
        max_chars=chars,
    )


def _guardrail_reply(user_text: str, lang: str) -> str:
    lowered_lang = (lang or "").lower()
    if looks_like_future_answer_directive(user_text):
        if lowered_lang == "ru":
            return (
                "Понял шутку, но я не буду запоминать такие инструкции как правило. "
                "Особенно если это субъективный рейтинг или фиксированный ответ про человека."
            )
        if lowered_lang == "zh":
            return "懂你的意思，但我不会把这种固定回答当成长期规则，尤其是关于某个人的主观排名。"
        return (
            "Түсіндім, бірақ мұндайды тұрақты ереже ретінде сақтамаймын. "
            "Әсіресе адам туралы субъективті рейтинг немесе алдын ала бекітілген жауап болса."
        )
    if looks_like_subjective_person_ranking_question(user_text):
        if lowered_lang == "ru":
            return (
                "Не буду ранжировать людей как «самого сильного» в чате. "
                "Если нужен разбор по конкретному опыту или сообщениям, спроси точнее."
            )
        if lowered_lang == "zh":
            return "我不会给群友做“最强/第一”这种主观排名。可以问某个人说过什么、做过什么或擅长哪些话题。"
        return (
            "Чаттағы адамдарды «ең мықты» деп рейтингтемеймін. "
            "Нақты тәжірибесі, айтқан сөздері немесе тақырыптары бойынша сұрасаң, соған сүйеніп жауап берем."
        )
    return ""


def _log_proactive_silent(
    silent_reason: str,
    *,
    chat_id: int | str,
    message_id: int | str | None = None,
    **extra: Any,
) -> None:
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "silent_reason": silent_reason,
    }
    payload.update(extra)
    logger.info("Group agent proactive candidate stayed silent", extra=payload)


def _channel_post_proactive_skip_reason(text: str) -> str | None:
    """Explain why a linked-channel post should not become a discussion-starter candidate."""
    return None


def _trigger_kind(update: dict[str, Any]) -> str | None:
    if not AGENT_ENABLED:
        return None
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat") or {}
    if chat.get("type") not in {"group", "supergroup"}:
        return None
    if is_linked_channel_discussion_post(message):
        return "channel_post"
    if not _is_plain_text_message(update):
        return None
    text = extract_message_text(message)
    if _mentions_bot(text):
        return "explicit"
    if _replies_to_bot(message) and _reply_to_bot_followup_skip_reason(text) is None:
        return "explicit"
    if _replies_to_any_bot(message):
        return None
    return "proactive"


def _log_skipped_reply_to_bot_followup(update: dict[str, Any]) -> None:
    if not AGENT_ENABLED or not _is_plain_text_message(update):
        return
    message = update["message"]
    text = extract_message_text(message)
    if not _replies_to_bot(message) or _mentions_bot(text):
        return
    skip_reason = _reply_to_bot_followup_skip_reason(text)
    if not skip_reason:
        return
    logger.info(
        "Group agent reply-to-bot follow-up skipped",
        extra={
            "chat_id": (message.get("chat") or {}).get("id"),
            "message_id": message.get("message_id"),
            "skip_reason": skip_reason,
        },
    )


def should_answer(update: dict[str, Any]) -> bool:
    """Return True when the agent policy allows considering an answer."""
    return _trigger_kind(update) is not None


def handle_update(
    *,
    repo: GroupMemoryRepository | None,
    bot: TelegramClient,
    update: dict[str, Any],
    sqs_repo: SQSClient | None = None,
) -> bool:
    """Handle non-/ask group prompts when agent participation is enabled.

    ``agent_enabled`` gates proactive, @mention, and reply-to-bot
    participation. Explicit ``/ask`` requests are handled by the command path
    and remain available while group memory is enabled. Proactive candidates
    are queued for a delayed final decision; explicit triggers answer now.

    Returns True when the agent handled the update and the dispatcher should not
    continue routing it as a plain message.
    """
    trigger_kind = _trigger_kind(update)
    if trigger_kind is None:
        _log_skipped_reply_to_bot_followup(update)
        return False
    if repo is None:
        return False

    message = update["message"]
    chat_id = message["chat"]["id"]
    if not repo.is_agent_enabled(chat_id):
        return False
    message_id = message["message_id"]
    if trigger_kind == "proactive":
        actor = message_actor(message)
        if sqs_repo is None:
            logger.warning(
                "Group agent proactive candidate could not be queued",
                extra={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "reason": "missing_sqs_repo",
                },
            )
            return False
        sqs_repo.send_proactive_candidate_task(
            update_id=update.get("update_id"),
            chat_id=chat_id,
            trigger_message_id=message_id,
            trigger_user_id=actor.get("id") if actor else None,
            user_text=extract_message_text(message),
            lang=get_chat_lang(chat_id),
            trigger_username=actor_username(actor),
            trigger_display_name=actor_display_name(actor) if actor else None,
            trigger_sender_type=actor_sender_type(actor),
            created_at=message.get("date"),
            delay_seconds=AGENT_PROACTIVE_DELAY_SECONDS,
        )
        logger.info(
            "Group agent proactive candidate queued",
            extra={
                "chat_id": chat_id,
                "message_id": message_id,
                "delay_seconds": AGENT_PROACTIVE_DELAY_SECONDS,
            },
        )
        return True
    if trigger_kind == "channel_post":
        actor = message_actor(message)
        media_ref = detect_media_reference(message, prefer_reply=False)
        if sqs_repo is None:
            logger.warning(
                "Group agent proactive candidate could not be queued",
                extra={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "reason": "missing_sqs_repo",
                    "candidate_kind": "channel_post",
                },
            )
            return False
        sqs_repo.send_proactive_candidate_task(
            update_id=update.get("update_id"),
            chat_id=chat_id,
            trigger_message_id=message_id,
            trigger_user_id=actor.get("id") if actor else None,
            user_text=extract_message_text(message),
            lang=get_chat_lang(chat_id),
            candidate_kind="channel_post",
            trigger_username=actor_username(actor),
            trigger_display_name=actor_display_name(actor) if actor else None,
            trigger_sender_type=actor_sender_type(actor),
            media_ref=media_ref.to_dict() if media_ref else None,
            created_at=message.get("date"),
            delay_seconds=0,
        )
        logger.info(
            "Group agent linked channel post candidate queued",
            extra={
                "chat_id": chat_id,
                "message_id": message_id,
                "delay_seconds": 0,
                "has_media": bool(media_ref),
                **(media_reference_log_extra(media_ref) if media_ref else {}),
            },
        )
        return True

    question_context = build_explicit_question_context(repo, chat_id, message)
    handled = answer_group_question(
        repo=repo,
        bot=bot,
        chat_id=chat_id,
        reply_to_message_id=message_id,
        user_text=question_context.user_text,
        retrieval_query=question_context.retrieval_query,
        lang=get_chat_lang(chat_id),
        requester_user_id=(message.get("from") or {}).get("id"),
        requester_username=(message.get("from") or {}).get("username"),
        requester_display_name=display_name(message.get("from") or {}),
        current_user_message=question_context.current_user_message,
        source_message_context=question_context.source_message_context,
        parent_bot_message_id=question_context.parent_bot_message_id,
    )
    if handled:
        logger.info(
            "Group agent handled update",
            extra={
                "chat_id": chat_id,
                "message_id": message_id,
                "trigger_kind": trigger_kind,
            },
        )
    return handled


def maybe_answer_proactively(
    *,
    repo: GroupMemoryRepository,
    bot: TelegramClient,
    chat_id: int,
    reply_to_message_id: int,
    user_text: str,
    lang: str,
    trigger_user_id: int | str | None = None,
    trigger_username: str | None = None,
    trigger_display_name: str | None = None,
) -> bool:
    """Ask Groq/DeepSeek whether speaking is useful; generate only on a strong yes."""
    decision_provider = _get_proactive_decision_provider()
    if decision_provider is None:
        _log_proactive_silent("proactive_decision_not_configured", chat_id=chat_id, message_id=reply_to_message_id)
        return False

    recent_context = format_recent_context(repo, chat_id, limit=AGENT_RECENT_CONTEXT_LIMIT)
    long_term_memory_context = format_long_term_memory_context(repo, chat_id, query_text=user_text)
    style_profile = _load_chat_style_profile(repo, chat_id)
    reply_policy = _proactive_reply_policy(style_profile)
    try:
        decision, decision_provider_name = decision_provider.decide(
            current_message=user_text,
            recent_context=recent_context,
            long_term_memory_context=long_term_memory_context,
            lang=lang,
            reply_instructions=reply_policy.instructions,
        )
    except ZerdeProviderError as exc:
        _log_proactive_silent(
            "proactive_decision_failed",
            chat_id=chat_id,
            message_id=reply_to_message_id,
            error_type=exc.__class__.__name__,
            error_message=str(exc)[:500],
        )
        return False
    except Exception:
        logger.exception("Group agent proactive decision failed", extra={"chat_id": chat_id})
        return False

    if not decision.should_reply or decision.confidence < AGENT_PROACTIVE_FINAL_THRESHOLD:
        _log_proactive_silent(
            "model_said_no",
            chat_id=chat_id,
            message_id=reply_to_message_id,
            confidence=decision.confidence,
            confidence_threshold=AGENT_PROACTIVE_FINAL_THRESHOLD,
            reason=decision.reason,
            provider=decision_provider_name,
        )
        return False

    if not repo.try_reserve_proactive_reply(chat_id, daily_limit=AGENT_DAILY_PROACTIVE_LIMIT):
        _log_proactive_silent(
            "daily_limit",
            chat_id=chat_id,
            message_id=reply_to_message_id,
            reason=decision.reason,
            provider=decision_provider_name,
        )
        return False

    ignored_usernames = {AGENT_BOT_USERNAME} if AGENT_BOT_USERNAME else set()
    proactive_user_message = (
        "ZerdeBot may proactively answer this ordinary group message. "
        "The message was not necessarily directed at the bot.\n\n"
        f"AI decision reason: {decision.reason or '(no reason provided)'}\n"
        f"Answer guidance: {decision.answer_guidance or '(no extra guidance)'}\n\n"
        "Ordinary group message:\n"
        f"{user_text}"
    )
    try:
        memory_bundle = build_agent_memory_context(
            repo=repo,
            chat_id=chat_id,
            user_text=user_text,
            retrieval_query=user_text,
            requester_user_id=trigger_user_id,
            requester_username=trigger_username,
            requester_display_name=trigger_display_name,
            ignored_usernames=ignored_usernames,
            recent_limit=AGENT_RECENT_CONTEXT_LIMIT,
            semantic_limit=8,
            recent_context_fn=format_recent_context,
            long_term_context_fn=format_long_term_memory_context,
            semantic_retrieval_fn=retrieve_relevant_memories,
            semantic_context_fn=format_semantic_memory_context,
            user_profile_context_fn=format_user_profile_context,
            requester_profile_context_fn=format_requester_profile_context,
        )
        answer, answer_provider = _generate_group_chat_reply(
            user_message=proactive_user_message,
            recent_context=memory_bundle.recent_context,
            long_term_memory_context=memory_bundle.long_term_memory_context,
            semantic_memory_context=memory_bundle.semantic_memory_context,
            user_profile_context=memory_bundle.user_profile_context,
            requester_profile_context=memory_bundle.requester_profile_context,
            reply_instructions=reply_policy.instructions,
            max_output_tokens=reply_policy.max_output_tokens,
            lang=lang,
            media_parts=None,
            media_context="",
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            proactive=True,
        )
    except (GeminiUnavailableError, ZerdeProviderError) as exc:
        _log_proactive_silent(
            "answer_provider_failed",
            chat_id=chat_id,
            message_id=reply_to_message_id,
            decision_provider=decision_provider_name,
            error_type=exc.__class__.__name__,
            error_message=str(exc)[:500],
        )
        return False
    except Exception:
        logger.exception("Group agent proactive answer generation failed", extra={"chat_id": chat_id})
        return False

    answer_text = fit_llm_output(answer, max_chars=reply_policy.max_chars)
    answer_html = normalize_llm_output_for_telegram_html(answer_text)
    sent = bot.send_message(chat_id, answer_html, reply_to_message_id=reply_to_message_id)
    bot_message_id = sent.get("message_id") if isinstance(sent, dict) else None
    if bot_message_id:
        repo.record_agent_reply(
            chat_id=chat_id,
            bot_message_id=bot_message_id,
            trigger_message_id=reply_to_message_id,
            trigger_kind="proactive",
            reason=(
                f"{decision.reason or 'AI decision judged this as a useful moment to answer.'} "
                f"decision_provider={decision_provider_name}; answer_provider={answer_provider}"
            ),
            answer_text=answer_text,
            user_message=user_text,
            current_user_message=user_text,
            requester_user_id=trigger_user_id,
            requester_username=trigger_username,
            requester_display_name=trigger_display_name,
            retrieval_sources=memory_bundle.retrieval_sources,
            confidence=decision.confidence,
        )
    logger.info(
        "Group agent handled update",
        extra={
            "chat_id": chat_id,
            "message_id": reply_to_message_id,
            "trigger_kind": "proactive",
            "confidence": decision.confidence,
            "reason": decision.reason,
            "decision_provider": decision_provider_name,
            "answer_provider": answer_provider,
        },
    )
    return True


def _format_channel_post_task_for_prompt(
    *,
    message_id: int,
    user_text: str,
    trigger_user_id: int | str | None,
    trigger_username: str | None,
    trigger_display_name: str | None,
    trigger_sender_type: str | None,
) -> str:
    bits: list[str] = []
    sender_type = str(trigger_sender_type or "channel").strip()
    if sender_type and sender_type != "user":
        bits.append(f"sender_type={sender_type[:80]}")
    elif trigger_user_id is not None:
        bits.append(f"user_id={trigger_user_id}")
    if trigger_username:
        bits.append(f"username=@{str(trigger_username).lstrip('@')[:80]}")
    if trigger_display_name:
        bits.append(f"name={str(trigger_display_name)[:80]}")
    bits.append(f"message_id={message_id}")
    speaker = f"[speaker {' '.join(bits)}]" if bits else "[speaker unknown]"
    text = _compact_query_text(user_text, limit=5000) if user_text else "No text caption was included."
    return f"{speaker} {text}"


def _ensure_channel_post_comment_decision(
    decision: GroupAgentDecision,
    *,
    provider_name: str,
) -> GroupAgentDecision:
    if not decision.should_reply or not decision.reply_text:
        raise ProviderResponseError(f"{provider_name} returned no usable channel-post comment")
    return decision


def _channel_post_gemini_retry_delay(attempt: int) -> float:
    index = attempt - 1
    if 0 <= index < len(CHANNEL_POST_GEMINI_RETRY_DELAYS_SECONDS):
        return max(0.0, float(CHANNEL_POST_GEMINI_RETRY_DELAYS_SECONDS[index]))
    return 0.0


def _try_gemini_channel_post_comment(
    *,
    channel_post: str,
    recent_context: str,
    lang: str,
    reply_instructions: str,
    max_output_tokens: int,
    media_parts: list[dict[str, Any]] | None,
    media_context: str,
    chat_id: int,
    message_id: int,
) -> tuple[GroupAgentDecision, str] | None:
    gemini = _get_gemini()
    if not gemini:
        _log_proactive_silent("gemini_not_configured", chat_id=chat_id, message_id=message_id)
        return None

    max_attempts = max(1, int(CHANNEL_POST_GEMINI_MAX_ATTEMPTS))
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            decision, _ = gemini.group_chat_channel_post_comment_decision(
                channel_post=channel_post,
                recent_context=recent_context,
                lang=lang,
                reply_instructions=reply_instructions,
                max_output_tokens=max_output_tokens,
                media_parts=media_parts,
                media_context=media_context,
            )
            return (
                _ensure_channel_post_comment_decision(decision, provider_name="gemini"),
                "gemini",
            )
        except GeminiRPDExhaustedError as exc:
            _log_proactive_silent(
                "gemini_rpd_limit",
                chat_id=chat_id,
                message_id=message_id,
                candidate_kind="channel_post",
            )
            logger.warning(
                "Gemini channel post comment hit RPD limit; trying text-only fallback",
                extra={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "attempt": attempt,
                },
            )
            last_error = exc
            break
        except (GeminiUnavailableError, ProviderResponseError) as exc:
            last_error = exc
            logger.warning(
                "Gemini channel post comment attempt failed",
                extra={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "error_type": exc.__class__.__name__,
                },
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Gemini channel post comment attempt failed unexpectedly",
                extra={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "error_type": exc.__class__.__name__,
                },
                exc_info=True,
            )

        if attempt < max_attempts:
            delay = _channel_post_gemini_retry_delay(attempt)
            if delay > 0:
                time.sleep(delay)

    logger.warning(
        "Gemini channel post comment exhausted; trying text-only fallback",
        extra={
            "chat_id": chat_id,
            "message_id": message_id,
            "attempts": max_attempts,
            "error_type": last_error.__class__.__name__ if last_error else "",
        },
    )
    return None


def _fallback_channel_post_comment(
    *,
    channel_post: str,
    recent_context: str,
    lang: str,
    reply_instructions: str,
    max_output_tokens: int,
) -> tuple[GroupAgentDecision, str]:
    fallback = _get_channel_post_comment_fallback()
    if fallback is None:
        raise ProviderResponseError("No channel-post comment providers configured")
    decision, provider_name = fallback.comment_decision(
        channel_post=channel_post,
        recent_context=recent_context,
        lang=lang,
        reply_instructions=reply_instructions,
        max_output_tokens=max_output_tokens,
    )
    return (
        _ensure_channel_post_comment_decision(decision, provider_name=provider_name),
        provider_name,
    )


def maybe_comment_on_channel_post(
    *,
    repo: GroupMemoryRepository,
    bot: TelegramClient,
    chat_id: int,
    reply_to_message_id: int,
    user_text: str,
    lang: str,
    trigger_user_id: int | str | None = None,
    trigger_username: str | None = None,
    trigger_display_name: str | None = None,
    trigger_sender_type: str | None = None,
    media_ref: Mapping[str, Any] | None = None,
) -> bool:
    """Generate a follow-up comment under a linked-channel post."""
    recent_context = format_recent_context(repo, chat_id, limit=AGENT_RECENT_CONTEXT_LIMIT)
    style = normalise_chat_style_profile(_load_chat_style_profile(repo, chat_id))
    reply_instructions = _compose_reply_instructions(
        (
            "Write a natural comment under the official linked-channel post. "
            "Use 1-4 concise sentences depending on the post. It can be a concrete observation, "
            "a light opinion, or a natural question that helps discussion continue. "
            "Do not recap the whole post and do not write a generic thank-you."
        ),
        style_profile=style,
        low_confidence_retrieval=False,
    )
    media_parts: list[dict[str, Any]] | None = None
    media_context = ""
    media_metadata: dict[str, Any] | None = None
    if isinstance(media_ref, Mapping):
        try:
            prepared_media = prepare_media_for_gemini(bot, media_ref)
            media_parts = prepared_media.media_parts
            media_context = prepared_media.media_context
            media_metadata = prepared_media.agent_reply_metadata
            logger.info(
                "Linked channel post media prepared",
                extra={
                    "chat_id": chat_id,
                    "reply_to_message_id": reply_to_message_id,
                    **media_reference_log_extra(media_ref),
                    "downloaded_bytes": prepared_media.downloaded_bytes,
                    "content_mode": prepared_media.content_mode,
                    "media_part_count": len(media_parts or []),
                    "media_context_chars": len(media_context),
                },
            )
        except (
            MediaDisabledError,
            MediaUnsupportedError,
            MediaTooLargeError,
            MediaUnavailableError,
        ) as exc:
            media_context = (
                "Attached media metadata is available, but the media content could not be analyzed. "
                "Do not claim visual/audio/file details that are not in the text."
            )
            logger.info(
                "Linked channel post media unavailable; continuing text-only",
                extra={
                    "chat_id": chat_id,
                    "reply_to_message_id": reply_to_message_id,
                    "error_type": exc.__class__.__name__,
                    **media_reference_log_extra(media_ref),
                },
            )
        except MediaError as exc:
            logger.info(
                "Linked channel post media failed safely; continuing text-only",
                extra={
                    "chat_id": chat_id,
                    "reply_to_message_id": reply_to_message_id,
                    "error_type": exc.__class__.__name__,
                    **media_reference_log_extra(media_ref),
                },
            )

    channel_post = _format_channel_post_task_for_prompt(
        message_id=reply_to_message_id,
        user_text=user_text,
        trigger_user_id=trigger_user_id,
        trigger_username=trigger_username,
        trigger_display_name=trigger_display_name,
        trigger_sender_type=trigger_sender_type,
    )
    decision_provider = _try_gemini_channel_post_comment(
        channel_post=channel_post,
        recent_context=recent_context,
        lang=lang,
        reply_instructions=reply_instructions,
        max_output_tokens=360,
        media_parts=media_parts,
        media_context=media_context,
        chat_id=chat_id,
        message_id=reply_to_message_id,
    )
    if decision_provider is None:
        decision_provider = _fallback_channel_post_comment(
            channel_post=channel_post,
            recent_context=recent_context,
            lang=lang,
            reply_instructions=reply_instructions,
            max_output_tokens=360,
        )
    decision, provider_name = decision_provider

    answer_text = fit_llm_output(decision.reply_text, max_chars=900)
    answer_html = normalize_llm_output_for_telegram_html(answer_text)
    sent = bot.send_message(chat_id, answer_html, reply_to_message_id=reply_to_message_id)
    bot_message_id = sent.get("message_id") if isinstance(sent, dict) else None
    if bot_message_id:
        repo.record_agent_reply(
            chat_id=chat_id,
            bot_message_id=bot_message_id,
            trigger_message_id=reply_to_message_id,
            trigger_kind="channel_post",
            reason=f"{decision.reason or 'I judged this linked-channel post as worth a short discussion starter.'}",
            answer_text=answer_text,
            user_message=user_text,
            current_user_message=user_text,
            confidence=decision.confidence,
            media_metadata=media_metadata,
        )
    logger.info(
        "Group agent handled linked channel post",
        extra={
            "chat_id": chat_id,
            "message_id": reply_to_message_id,
            "trigger_kind": "channel_post",
            "confidence": decision.confidence,
            "provider": provider_name,
            "reason": decision.reason,
        },
    )
    return True


def process_proactive_candidate_task(
    *,
    repo: GroupMemoryRepository,
    bot: TelegramClient,
    body: dict[str, Any],
) -> bool:
    """Finalize a delayed proactive candidate after humans had time to answer."""
    try:
        chat_id = int(body["chat_id"])
        trigger_message_id = int(body["trigger_message_id"])
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "PROCESS_PROACTIVE_CANDIDATE missing required field",
            extra={"error": str(exc)},
        )
        return False

    user_text = str(body.get("user_text") or "").strip()
    candidate_kind = str(body.get("candidate_kind") or "proactive")
    media_ref = body.get("media_ref") if isinstance(body.get("media_ref"), dict) else None
    if not user_text and not (candidate_kind == "channel_post" and media_ref):
        _log_proactive_silent("missing_user_text", chat_id=chat_id, message_id=trigger_message_id)
        return False

    if not repo.is_agent_enabled(chat_id):
        _log_proactive_silent("agent_disabled", chat_id=chat_id, message_id=trigger_message_id)
        return False

    skip_reason = _channel_post_proactive_skip_reason(user_text) if candidate_kind == "channel_post" else None
    if skip_reason is not None:
        _log_proactive_silent(
            "original_no_longer_useful",
            chat_id=chat_id,
            message_id=trigger_message_id,
            original_skip_reason=skip_reason,
            candidate_kind=candidate_kind,
        )
        return False

    if candidate_kind == "channel_post":
        return maybe_comment_on_channel_post(
            repo=repo,
            bot=bot,
            chat_id=chat_id,
            reply_to_message_id=trigger_message_id,
            user_text=user_text,
            lang=str(body.get("lang") or get_chat_lang(chat_id)),
            trigger_user_id=body.get("trigger_user_id"),
            trigger_username=body.get("trigger_username"),
            trigger_display_name=body.get("trigger_display_name"),
            trigger_sender_type=body.get("trigger_sender_type"),
            media_ref=media_ref,
        )

    return maybe_answer_proactively(
        repo=repo,
        bot=bot,
        chat_id=chat_id,
        reply_to_message_id=trigger_message_id,
        user_text=user_text,
        lang=str(body.get("lang") or get_chat_lang(chat_id)),
        trigger_user_id=body.get("trigger_user_id"),
        trigger_username=str(body.get("trigger_username") or "") or None,
        trigger_display_name=str(body.get("trigger_display_name") or "") or None,
    )


def answer_group_question(
    *,
    repo: GroupMemoryRepository,
    bot: TelegramClient,
    chat_id: int,
    reply_to_message_id: int,
    user_text: str,
    lang: str,
    retrieval_query: str | None = None,
    requester_user_id: int | str | None = None,
    requester_username: str | None = None,
    requester_display_name: str | None = None,
    current_user_message: str | None = None,
    source_message_context: str | None = None,
    parent_bot_message_id: int | str | None = None,
    media_parts: list[dict[str, Any]] | None = None,
    media_context: str = "",
    media_metadata: dict[str, Any] | None = None,
    raise_on_unavailable: bool = False,
) -> bool:
    """Generate and send a group-context reply for an explicit question."""
    current_user_message = user_text if current_user_message is None else current_user_message
    guarded_answer = _guardrail_reply(user_text, lang)
    if guarded_answer:
        answer_html = normalize_llm_output_for_telegram_html(guarded_answer)
        sent = bot.send_message(chat_id, answer_html, reply_to_message_id=reply_to_message_id)
        bot_message_id = sent.get("message_id") if isinstance(sent, dict) else None
        if bot_message_id:
            repo.record_agent_reply(
                chat_id=chat_id,
                bot_message_id=bot_message_id,
                trigger_message_id=reply_to_message_id,
                trigger_kind="explicit",
                reason="Guardrail blocked a subjective ranking or persistent future-answer directive.",
                answer_text=guarded_answer,
                user_message=user_text,
                current_user_message=current_user_message,
                source_message_context=source_message_context,
                parent_bot_message_id=parent_bot_message_id,
                media_metadata=media_metadata,
            )
        return True

    ignored_usernames = {AGENT_BOT_USERNAME} if AGENT_BOT_USERNAME else set()
    memory_bundle = build_agent_memory_context(
        repo=repo,
        chat_id=chat_id,
        user_text=user_text,
        retrieval_query=retrieval_query,
        requester_user_id=requester_user_id,
        requester_username=requester_username,
        requester_display_name=requester_display_name,
        ignored_usernames=ignored_usernames,
        recent_limit=AGENT_RECENT_CONTEXT_LIMIT,
        semantic_limit=8,
        recent_context_fn=format_recent_context,
        long_term_context_fn=format_long_term_memory_context,
        semantic_retrieval_fn=retrieve_relevant_memories,
        semantic_context_fn=format_semantic_memory_context,
        user_profile_context_fn=format_user_profile_context,
        requester_profile_context_fn=format_requester_profile_context,
    )
    logger.info(
        "Group agent memory retrieval context prepared",
        extra={
            "chat_id": chat_id,
            "candidate_count": len(memory_bundle.candidates),
            "retrieval_source_count": len(memory_bundle.retrieval_sources),
            "semantic_context_item_count": (
                len(memory_bundle.semantic_memory_context.splitlines()) if memory_bundle.semantic_memory_context else 0
            ),
            "semantic_context_chars": len(memory_bundle.semantic_memory_context),
            "self_reference": memory_bundle.intent.is_self_reference,
            "requester_filter_applied": bool(memory_bundle.intent.is_self_reference and requester_user_id is not None),
            "target_username_count": len(memory_bundle.intent.target_usernames),
            "retrieval_query_chars": len((retrieval_query or user_text).strip()),
        },
    )
    style_profile = _load_chat_style_profile(repo, chat_id)
    reply_policy = _reply_policy(
        user_text,
        style_profile=style_profile,
        low_confidence_retrieval=_has_low_confidence_retrieval(memory_bundle.retrieval_sources),
    )

    try:
        answer, provider_name = _generate_group_chat_reply(
            user_message=user_text,
            recent_context=memory_bundle.recent_context,
            long_term_memory_context=memory_bundle.long_term_memory_context,
            semantic_memory_context=memory_bundle.semantic_memory_context,
            user_profile_context=memory_bundle.user_profile_context,
            requester_profile_context=memory_bundle.requester_profile_context,
            reply_instructions=reply_policy.instructions,
            max_output_tokens=reply_policy.max_output_tokens,
            lang=lang,
            media_parts=media_parts,
            media_context=media_context,
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            proactive=False,
        )
    except (GeminiUnavailableError, ZerdeProviderError) as exc:
        logger.warning(
            "Group agent reply provider chain unavailable",
            extra={
                "chat_id": chat_id,
                "reply_to_message_id": reply_to_message_id,
                "error_type": exc.__class__.__name__,
                "error_message": str(exc)[:500],
            },
        )
        if raise_on_unavailable:
            raise
        bot.send_message(
            chat_id,
            get_translated_text("ask_agent_unavailable", lang),
            reply_to_message_id=reply_to_message_id,
        )
        return True
    except Exception:
        logger.exception("Group agent failed", extra={"chat_id": chat_id})
        if raise_on_unavailable:
            raise
        return False

    answer_text = fit_llm_output(answer, max_chars=reply_policy.max_chars)
    answer_html = normalize_llm_output_for_telegram_html(answer_text)
    sent = bot.send_message(chat_id, answer_html, reply_to_message_id=reply_to_message_id)
    bot_message_id = sent.get("message_id") if isinstance(sent, dict) else None
    if bot_message_id:
        media_reply_metadata = dict(media_metadata or {})
        if media_reply_metadata and not media_reply_metadata.get("media_summary"):
            media_reply_metadata["media_summary"] = _media_summary_from_metadata(answer_text, media_reply_metadata)
        repo.record_agent_reply(
            chat_id=chat_id,
            bot_message_id=bot_message_id,
            trigger_message_id=reply_to_message_id,
            trigger_kind="explicit",
            reason=(
                "I was mentioned, replied to, or called through /ask, "
                "so I answered with recent, semantic, and trusted memory context."
            ),
            answer_text=answer_text,
            user_message=user_text,
            current_user_message=current_user_message,
            source_message_context=source_message_context,
            parent_bot_message_id=parent_bot_message_id,
            requester_user_id=requester_user_id,
            requester_username=requester_username,
            requester_display_name=requester_display_name,
            retrieval_sources=memory_bundle.retrieval_sources,
            media_metadata=media_reply_metadata or None,
        )
    logger.info(
        "Group agent explicit reply generated",
        extra={
            "chat_id": chat_id,
            "reply_to_message_id": reply_to_message_id,
            "provider": provider_name,
            "lang": lang,
        },
    )
    return True
