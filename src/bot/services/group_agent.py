"""Context-aware group chat agent helpers."""

from __future__ import annotations

import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable

from core.config import (
    AGENT_BOT_ID,
    AGENT_BOT_USERNAME,
    get_chat_lang,
    get_gemini_api_key,
)
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.ai.gemini_client import (
    GeminiClient,
    GeminiRPDExhaustedError,
    GeminiUnavailableError,
)
from services.ai.group_chat_reply_fallback import (
    FallbackGroupChatReplyProvider,
    create_group_chat_reply_fallback_provider,
)
from services.ai.telegram_html import (
    fit_llm_output,
    normalize_llm_output_for_telegram_html,
)
from services.bot_identity import is_self_bot_user
from services.explicit_context import extract_message_text, format_message_reference, normalise_chat_style_profile
from services.memory_safety import (
    looks_like_future_answer_directive,
    looks_like_subjective_person_ranking_question,
)
from services.repositories.explicit_context_repository import ExplicitContextRepository
from services.repositories.sqs import SQSClient
from services.telegram import TelegramClient
from services.telegram_actor import (
    actor_display_name,
    is_linked_channel_discussion_post,
)
from services.telegram_media import (
    detect_media_references,
    has_any_media,
    media_reference_log_extra,
    media_references_log_extra,
    media_references_retrieval_query,
)
from zerde_common.ai_errors import ProviderResponseError, ZerdeProviderError

logger = LoggerAdapter(get_logger(__name__), {})

_agent_gemini: GeminiClient | None = None
_group_chat_reply_fallback: FallbackGroupChatReplyProvider | None = None

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


def _get_gemini() -> GeminiClient | None:
    global _agent_gemini
    if get_gemini_api_key() and _agent_gemini is None:
        _agent_gemini = GeminiClient()
    return _agent_gemini


def _get_group_chat_reply_fallback() -> FallbackGroupChatReplyProvider | None:
    global _group_chat_reply_fallback
    if _group_chat_reply_fallback is None:
        _group_chat_reply_fallback = create_group_chat_reply_fallback_provider()
    return _group_chat_reply_fallback


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


def _compact_query_text(text: str, *, limit: int) -> str:
    return " ".join((text or "").split())[:limit]


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
    before_attempt: Callable[[], None] | None = None,
) -> tuple[str, str] | None:
    gemini = _get_gemini()
    if not gemini:
        logger.info(
            "Group agent Gemini reply skipped because Gemini is not configured",
            extra={"chat_id": chat_id, "reply_to_message_id": reply_to_message_id},
        )
        return None

    max_attempts = max(1, int(GROUP_CHAT_REPLY_GEMINI_MAX_ATTEMPTS))
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        if before_attempt is not None:
            before_attempt()
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
                **({"before_attempt": before_attempt} if before_attempt is not None else {}),
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
    before_attempt: Callable[[], None] | None = None,
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
        **({"before_attempt": before_attempt} if before_attempt is not None else {}),
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
    before_attempt: Callable[[], None] | None = None,
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
        **({"before_attempt": before_attempt} if before_attempt is not None else {}),
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
        **({"before_attempt": before_attempt} if before_attempt is not None else {}),
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


def build_explicit_question_context(
    repo: ExplicitContextRepository,
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
        # Telegram may quote pre-cutover bot facts; use only the current question.
        return ExplicitQuestionContext(user_text=text, current_user_message=text, retrieval_query=text)

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


def _compose_reply_instructions(
    base_instruction: str,
    *,
    style_profile: Mapping[str, Any],
) -> str:
    parts = [base_instruction, _style_instruction(style_profile)]
    return " ".join(part for part in parts if part)


def _reply_policy(
    user_text: str,
    *,
    style_profile: Mapping[str, Any] | None = None,
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


def _trigger_kind(update: dict[str, Any]) -> str | None:
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    if (message.get("chat") or {}).get("type") not in {"group", "supergroup"}:
        return None
    if is_linked_channel_discussion_post(message) or not _is_plain_text_message(update):
        return None
    text = extract_message_text(message)
    if _mentions_bot(text) or (_replies_to_bot(message) and _reply_to_bot_followup_skip_reason(text) is None):
        return "explicit"
    return None


def _log_skipped_reply_to_bot_followup(update: dict[str, Any]) -> None:
    if not _is_plain_text_message(update):
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
    repo: ExplicitContextRepository | None,
    bot: TelegramClient,
    update: dict[str, Any],
    sqs_repo: SQSClient | None = None,
) -> bool:
    """Handle explicit mentions and requested followups independently of learning.

    Ordinary chatter and channel mirrors never enqueue automatic interactions.
    """
    trigger_kind = _trigger_kind(update)
    if trigger_kind is None:
        _log_skipped_reply_to_bot_followup(update)
        return False
    if repo is None:
        return False

    message = update["message"]
    chat_id = message["chat"]["id"]
    message_id = message["message_id"]

    media_refs = detect_media_references(
        message,
        media_group_loader=lambda media_group_id: repo.get_media_group_refs(chat_id, media_group_id),
    )
    if media_refs:
        media_log = media_references_log_extra(media_refs)
        if len(media_refs) == 1:
            media_log.update(media_reference_log_extra(media_refs[0]))
        if sqs_repo is None:
            logger.warning(
                "Group agent explicit media request could not be queued",
                extra={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "reason": "missing_sqs_repo",
                    **media_log,
                },
            )
            bot.send_message(
                chat_id,
                get_translated_text("ask_agent_unavailable", get_chat_lang(chat_id)),
                reply_to_message_id=message_id,
            )
            return True

        question_context = build_explicit_question_context(repo, chat_id, message)
        retrieval_query = media_references_retrieval_query(question_context.retrieval_query, media_refs)
        requester = message.get("from") or {}
        try:
            bot.set_message_reaction(chat_id, message_id, "👀")
        except Exception:
            logger.debug(
                "Failed to react to explicit media request before enqueue",
                extra={"chat_id": chat_id, "message_id": message_id},
            )
        try:
            sqs_repo.send_group_ask_task(
                update_id=update.get("update_id") or message_id,
                chat_id=chat_id,
                reply_to_message_id=message_id,
                user_text=question_context.user_text,
                retrieval_query=retrieval_query,
                lang=get_chat_lang(chat_id),
                requester_user_id=requester.get("id"),
                request_sent_at=message.get("date"),
                requester_username=requester.get("username"),
                requester_display_name=actor_display_name(requester),
                current_user_message=question_context.current_user_message,
                source_message_context=question_context.source_message_context,
                parent_bot_message_id=question_context.parent_bot_message_id,
                media_refs=[media_ref.to_dict() for media_ref in media_refs],
            )
        except Exception:
            logger.exception(
                "Failed to enqueue explicit media request",
                extra={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    **media_log,
                },
            )
            bot.send_message(
                chat_id,
                get_translated_text("ask_agent_unavailable", get_chat_lang(chat_id)),
                reply_to_message_id=message_id,
            )
            return True

        logger.info(
            "Group agent explicit media request queued",
            extra={
                "chat_id": chat_id,
                "message_id": message_id,
                "update_id": update.get("update_id"),
                "media_source": (
                    "media_group"
                    if len(media_refs) > 1
                    else "current_message" if media_refs[0].source_message_id == message_id else "reply_to_message"
                ),
                **media_log,
            },
        )
        return True

    if has_any_media(message):
        logger.info(
            "Group agent explicit media unsupported",
            extra={
                "chat_id": chat_id,
                "message_id": message_id,
                "update_id": update.get("update_id"),
            },
        )
        bot.send_message(
            chat_id,
            get_translated_text("ask_media_unsupported", get_chat_lang(chat_id)),
            reply_to_message_id=message_id,
        )
        return True

    from services.memory_v2.public_answers import MemoryPublicRetryRequiredError, try_memory_answer

    if try_memory_answer(message, question=extract_message_text(message), lang=get_chat_lang(chat_id)):
        return True
    question_context = build_explicit_question_context(repo, chat_id, message)
    from services.memory_v2.explicit_delivery import configured_delivery
    from services.memory_v2.explicit_request_gate import capture_configured
    from services.memory_v2.models import MemoryConflict, MemoryInputError, MemoryUnavailable

    actor = (message.get("from") or {}).get("id")
    try:
        gate = capture_configured(chat_id, actor, message_id, message.get("date"))
        body = {"chat_id": chat_id, "requester_user_id": actor, "reply_to_message_id": message_id, "request_gate": gate}
        with configured_delivery(repo, bot, body) as (delivery, _):
            handled = answer_group_question(
                repo=repo,
                bot=delivery,
                chat_id=chat_id,
                reply_to_message_id=message_id,
                user_text=question_context.user_text,
                retrieval_query=question_context.retrieval_query,
                lang=get_chat_lang(chat_id),
                requester_user_id=(message.get("from") or {}).get("id"),
                requester_username=(message.get("from") or {}).get("username"),
                requester_display_name=actor_display_name(message.get("from") or {}),
                current_user_message=question_context.current_user_message,
                source_message_context=question_context.source_message_context,
                parent_bot_message_id=question_context.parent_bot_message_id,
            )
    except (MemoryConflict, MemoryInputError, MemoryUnavailable):
        return True
    except Exception:
        raise MemoryPublicRetryRequiredError("Explicit answer state requires redelivery") from None
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


def _plain_reply_instructions(policy: ReplyPolicy) -> str:
    """One prompt owner for runtime answers and the strict evaluation serializer."""
    return (
        policy.instructions + " No long-term memory is provided for this request. "
        "You have no tool to search message history or fetch profiles in this response. "
        "Missing context does not tell you whether stored information exists or what someone said before. "
        "Do not claim the database or chat history is empty, that a person never shared something, "
        "or that their data was erased. Do not promise to search history or retrieve profiles yourself. "
        "Do not claim to know personal or group facts absent from this explicit request. "
        "When evidence is missing, say you cannot verify it from the context available for this request "
        "and invite the user to provide the relevant message or quotation."
    )


def answer_group_question(
    *,
    repo: ExplicitContextRepository,
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
    from services.memory_v2.explicit_delivery import ExplicitDelivery

    before_attempt = bot.check if isinstance(bot, ExplicitDelivery) else None
    current_user_message = user_text if current_user_message is None else current_user_message
    guarded_answer = _guardrail_reply(user_text, lang)
    if guarded_answer:
        answer_html = normalize_llm_output_for_telegram_html(guarded_answer)
        bot.send_message(chat_id, answer_html, reply_to_message_id=reply_to_message_id)
        return True

    style_profile = normalise_chat_style_profile(None)
    reply_policy = _reply_policy(
        user_text,
        style_profile=style_profile,
    )

    try:
        answer, provider_name = _generate_group_chat_reply(
            user_message=user_text,
            recent_context="",
            long_term_memory_context="",
            semantic_memory_context="",
            user_profile_context="",
            requester_profile_context="",
            reply_instructions=_plain_reply_instructions(reply_policy),
            max_output_tokens=reply_policy.max_output_tokens,
            lang=lang,
            media_parts=media_parts,
            media_context=media_context,
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            **({"before_attempt": before_attempt} if before_attempt is not None else {}),
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
        if raise_on_unavailable or before_attempt is not None:
            raise
        return False

    answer_text = fit_llm_output(answer, max_chars=reply_policy.max_chars)
    answer_html = normalize_llm_output_for_telegram_html(answer_text)
    bot.send_message(chat_id, answer_html, reply_to_message_id=reply_to_message_id)
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
