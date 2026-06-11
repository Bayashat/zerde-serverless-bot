"""Context-aware group chat agent helpers."""

from __future__ import annotations

import re
from typing import Any

from core.config import (
    AGENT_BOT_USERNAME,
    AGENT_DAILY_PROACTIVE_LIMIT,
    AGENT_ENABLED,
    AGENT_RECENT_CONTEXT_LIMIT,
    get_chat_lang,
    get_gemini_api_key,
)
from core.logger import LoggerAdapter, get_logger
from services.ai.gemini_client import GeminiClient, GeminiRPDExhaustedError, GeminiUnavailableError
from services.ai.telegram_html import normalize_llm_output_for_telegram_html
from services.group_memory import extract_message_text, format_recent_context
from services.repositories.group_memory import GroupMemoryRepository
from services.telegram import TelegramClient

logger = LoggerAdapter(get_logger(__name__), {})

_agent_gemini: GeminiClient | None = None


def _get_gemini() -> GeminiClient | None:
    global _agent_gemini
    if get_gemini_api_key() and _agent_gemini is None:
        _agent_gemini = GeminiClient()
    return _agent_gemini


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
    return bool(sender.get("is_bot"))


def _looks_like_open_question(text: str) -> bool:
    lowered = text.lower()
    question_mark = "?" in text or "？" in text
    cue_words = (
        "how ",
        "why ",
        "what ",
        "кто",
        "как",
        "почему",
        "怎么",
        "为什么",
        "қалай",
        "неге",
    )
    return len(text) >= 12 and (question_mark or any(word in lowered for word in cue_words))


def _trigger_kind(update: dict[str, Any]) -> str | None:
    if not AGENT_ENABLED or not _is_plain_text_message(update):
        return None
    message = update["message"]
    text = extract_message_text(message)
    if _mentions_bot(text) or _replies_to_bot(message):
        return "explicit"
    if _looks_like_open_question(text):
        return "proactive"
    return None


def should_answer(update: dict[str, Any]) -> bool:
    """Return True when the agent policy allows considering an answer."""
    return _trigger_kind(update) is not None


def handle_update(
    *,
    repo: GroupMemoryRepository | None,
    bot: TelegramClient,
    update: dict[str, Any],
) -> bool:
    """Answer an explicit group chat prompt with recent group context.

    Returns True when the agent handled the update and the dispatcher should not
    continue routing it as a plain message.
    """
    trigger_kind = _trigger_kind(update)
    if repo is None or trigger_kind is None:
        return False

    message = update["message"]
    chat_id = message["chat"]["id"]
    if not repo.is_agent_enabled(chat_id):
        return False
    if trigger_kind == "proactive" and not repo.try_reserve_proactive_reply(
        chat_id,
        daily_limit=AGENT_DAILY_PROACTIVE_LIMIT,
    ):
        return False

    return answer_group_question(
        repo=repo,
        bot=bot,
        chat_id=chat_id,
        reply_to_message_id=message["message_id"],
        user_text=extract_message_text(message),
        lang=get_chat_lang(chat_id),
    )


def answer_group_question(
    *,
    repo: GroupMemoryRepository,
    bot: TelegramClient,
    chat_id: int,
    reply_to_message_id: int,
    user_text: str,
    lang: str,
) -> bool:
    """Generate and send a group-context reply for an explicit question."""
    gemini = _get_gemini()
    if not gemini:
        return False

    recent_context = format_recent_context(repo, chat_id, limit=AGENT_RECENT_CONTEXT_LIMIT)

    try:
        answer, _ = gemini.group_chat_reply(
            user_message=user_text,
            recent_context=recent_context,
            lang=lang,
        )
    except GeminiRPDExhaustedError:
        bot.send_message(chat_id, "AI daily quota is exhausted for today.", reply_to_message_id=reply_to_message_id)
        return True
    except GeminiUnavailableError:
        logger.warning("Group agent Gemini call unavailable", extra={"chat_id": chat_id})
        return False
    except Exception:
        logger.exception("Group agent failed", extra={"chat_id": chat_id})
        return False

    answer_html = normalize_llm_output_for_telegram_html(answer)
    bot.send_message(chat_id, answer_html, reply_to_message_id=reply_to_message_id)
    return True
