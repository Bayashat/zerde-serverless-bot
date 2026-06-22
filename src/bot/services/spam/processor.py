"""SQS processor for SPAM_CHECK tasks: Layer-2 Groq classification and enforcement."""

import re
from html import escape
from typing import Any

from core.config import (
    SPAM_AI_CONFIDENCE_THRESHOLD,
    SPAM_REVIEW_BAN_PREFIX,
    SPAM_REVIEW_IGNORE_PREFIX,
    TELEGRAM_CHANNEL_POST_ACTOR_USER_ID,
    get_chat_lang,
    get_spam_review_admin_mentions,
)
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.repositories.captcha import CaptchaRepository
from services.repositories.group_memory import GroupMemoryRepository
from services.repositories.stats import StatsRepository
from services.spam.chat_member import is_chat_admin_or_creator
from services.spam.enforcer import SpamEnforcer, resolve_spam_target_mention, translate_spam_reason
from services.spam.groq_detector import GroqSpamDetector
from services.spam.message_text import format_spam_ai_context
from services.telegram import TelegramClient

logger = LoggerAdapter(get_logger(__name__), {})

_detector: GroqSpamDetector | None = None
_RECENT_CONTEXT_QUERY_LIMIT = 12
_RECENT_CONTEXT_RENDER_LIMIT = 8
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")
_STRONG_AUTO_ENFORCE_RULES = frozenset(
    {
        "external_url",
        "external_mention",
        "vpn_pattern",
        "dm_redirect",
        "money_and_dm_redirect",
        "scam_hook",
        "money_and_scam_hook",
        "finance_soft_lead_bait",
        "short_text_with_contact",
    }
)


def _get_detector() -> GroqSpamDetector:
    global _detector
    if _detector is None:
        _detector = GroqSpamDetector()
    return _detector


def process_spam_check_task(
    bot: TelegramClient,
    body: dict,
    captcha_repo: CaptchaRepository | None = None,
    memory_repo: GroupMemoryRepository | None = None,
) -> None:
    """Process a SPAM_CHECK SQS task: classify with Groq and enforce if confident."""
    try:
        chat_id: int = body["chat_id"]
        user_id: int = body["user_id"]
        message_id: int = body["message_id"]
        text: str = str(body["text"])
    except (KeyError, TypeError) as e:
        logger.error("Malformed SPAM_CHECK body, skipping", extra={"error": e, "body": body})
        return

    triggered_rules = _normalise_triggered_rules(body.get("triggered_rules"))
    rule_score = _coerce_float(body.get("rule_score"))
    message_context = body.get("message_context") if isinstance(body.get("message_context"), dict) else {}

    if user_id == TELEGRAM_CHANNEL_POST_ACTOR_USER_ID:
        logger.info(
            "Skipping SPAM_CHECK for channel discussion mirror actor",
            extra={"chat_id": chat_id, "message_id": message_id},
        )
        return

    if _has_pending_captcha(captcha_repo, chat_id, user_id):
        logger.info(
            "Skipping SPAM_CHECK for pending captcha user",
            extra={"chat_id": chat_id, "user_id": user_id, "message_id": message_id},
        )
        return

    if is_chat_admin_or_creator(bot, chat_id, user_id):
        logger.info(
            "Skipping SPAM_CHECK for administrator/creator",
            extra={"chat_id": chat_id, "user_id": user_id},
        )
        return

    try:
        recent_context = _load_recent_context(memory_repo, chat_id, message_id)
        classifier_input = format_spam_ai_context(
            text=text,
            message_context=message_context,
            recent_context=recent_context,
            rule_score=rule_score,
            triggered_rules=triggered_rules,
        )
        result = _get_detector().classify(classifier_input)
        strong_signal = _has_strong_auto_enforce_signal(triggered_rules)
        auto_enforce = result.label == "SPAM" and result.confidence >= SPAM_AI_CONFIDENCE_THRESHOLD and strong_signal

        logger.info(
            "Groq spam check result",
            extra={
                "chat_id": chat_id,
                "user_id": user_id,
                "message_id": message_id,
                "label": result.label,
                "confidence": result.confidence,
                "reason": result.reason,
                "error": result.error,
                "rules": triggered_rules,
                "rule_score": rule_score,
                "strong_auto_enforce_signal": strong_signal,
                "auto_enforce": auto_enforce,
                "recent_context_count": len(recent_context),
            },
        )

        if result.error:
            return

        if auto_enforce:
            SpamEnforcer(bot, StatsRepository()).enforce(
                chat_id=chat_id,
                user_id=user_id,
                message_id=message_id,
                reason=result.reason,
            )
        elif result.label == "SPAM":
            # Low-confidence or weak-signal SPAM: alert admins without taking automated action.
            _send_spam_review_alert(bot, chat_id, user_id, message_id, result.reason, result.confidence)

    except Exception as e:
        logger.error(
            "Unexpected error in process_spam_check_task",
            extra={"chat_id": chat_id, "user_id": user_id, "error": e},
            exc_info=True,
        )


def _has_pending_captcha(captcha_repo: CaptchaRepository | None, chat_id: int, user_id: int) -> bool:
    if not captcha_repo:
        return False
    try:
        return captcha_repo.get_pending(chat_id, user_id) is not None
    except Exception as e:
        logger.warning(
            "Failed to check pending captcha before SPAM_CHECK",
            extra={"chat_id": chat_id, "user_id": user_id, "error": e},
        )
        return False


def _send_spam_review_alert(
    bot: TelegramClient,
    chat_id: int,
    user_id: int,
    message_id: int,
    result_reason: str,
    confidence: float,
) -> None:
    try:
        target = resolve_spam_target_mention(bot, chat_id, user_id)
        lang = get_chat_lang(chat_id)
        reason = translate_spam_reason(result_reason, lang)
        confidence_pct = int(confidence * 100)
        notice = get_translated_text(
            "spam_uncertain_notice",
            lang,
            TARGET=target,
            REASON=reason,
            CONFIDENCE=confidence_pct,
        )
        admin_mentions = _format_admin_mentions(chat_id)
        if admin_mentions:
            notice = f"{admin_mentions}\n{notice}"
        bot.send_message(
            chat_id,
            notice,
            reply_markup=_spam_review_keyboard(user_id, message_id, lang),
        )
    except Exception as e:
        logger.warning("Failed to send uncertain spam alert", extra={"error": e})


def _load_recent_context(
    memory_repo: GroupMemoryRepository | None,
    chat_id: int,
    current_message_id: int,
) -> list[dict[str, Any]]:
    if memory_repo is None:
        return []
    try:
        items = memory_repo.get_recent_messages(chat_id, limit=_RECENT_CONTEXT_QUERY_LIMIT)
    except Exception as e:
        logger.warning(
            "Failed to load recent context for SPAM_CHECK",
            extra={"chat_id": chat_id, "message_id": current_message_id, "error": e},
        )
        return []

    recent: list[dict[str, Any]] = []
    for item in items:
        if str(item.get("message_id")) == str(current_message_id):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        recent.append(
            {
                "message_id": item.get("message_id"),
                "user_id": item.get("user_id"),
                "username": item.get("username"),
                "display_name": item.get("display_name"),
                "text": text,
            }
        )
    return recent[-_RECENT_CONTEXT_RENDER_LIMIT:]


def _normalise_triggered_rules(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rules: list[str] = []
    seen: set[str] = set()
    for item in value:
        rule = str(item or "").strip()
        if rule and rule not in seen:
            seen.add(rule)
            rules.append(rule)
    return rules


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_strong_auto_enforce_signal(triggered_rules: list[str]) -> bool:
    rules = set(triggered_rules)
    if rules & _STRONG_AUTO_ENFORCE_RULES:
        return True
    return "job_offer" in rules and bool(
        rules & {"money_pattern", "external_mention", "external_url", "dm_redirect", "scam_hook"}
    )


def _format_admin_mentions(chat_id: int) -> str:
    mentions: list[str] = []
    for raw_username in get_spam_review_admin_mentions(chat_id):
        username = str(raw_username or "").strip().lstrip("@")
        if not username or not _USERNAME_RE.fullmatch(username):
            continue
        mentions.append(f"@{escape(username)}")
    return " ".join(mentions)


def _spam_review_keyboard(user_id: int, message_id: int, lang: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {
                    "text": get_translated_text("spam_review_ban_button", lang),
                    "callback_data": f"{SPAM_REVIEW_BAN_PREFIX}{user_id}:{message_id}",
                },
                {
                    "text": get_translated_text("spam_review_ignore_button", lang),
                    "callback_data": f"{SPAM_REVIEW_IGNORE_PREFIX}{user_id}:{message_id}",
                },
            ]
        ]
    }
