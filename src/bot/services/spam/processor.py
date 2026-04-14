"""SQS processor for SPAM_CHECK tasks: Layer-2 Groq classification and enforcement."""

from core.config import get_chat_lang
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.repositories.stats import StatsRepository
from services.spam.chat_member import is_chat_admin_or_creator
from services.spam.enforcer import SpamEnforcer
from services.spam.groq_detector import GroqSpamDetector
from services.telegram import TelegramClient

logger = LoggerAdapter(get_logger(__name__), {})

_CONFIDENCE_THRESHOLD = 0.85


def process_spam_check_task(bot: TelegramClient, body: dict) -> None:
    """Process a SPAM_CHECK SQS task: classify with Groq and enforce if confident."""
    try:
        chat_id: int = body["chat_id"]
        user_id: int = body["user_id"]
        message_id: int = body["message_id"]
        text: str = body["text"]
    except (KeyError, TypeError) as e:
        logger.error("Malformed SPAM_CHECK body, skipping", extra={"error": e, "body": body})
        return

    if is_chat_admin_or_creator(bot, chat_id, user_id):
        logger.info(
            "Skipping SPAM_CHECK for administrator/creator",
            extra={"chat_id": chat_id, "user_id": user_id},
        )
        return

    try:
        detector = GroqSpamDetector()
        result = detector.classify(text)

        logger.info(
            "Groq spam check result",
            extra={
                "chat_id": chat_id,
                "user_id": user_id,
                "message_id": message_id,
                "label": result.label,
                "confidence": result.confidence,
                "error": result.error,
            },
        )

        if result.error:
            return

        if result.label == "SPAM" and result.confidence > _CONFIDENCE_THRESHOLD:
            SpamEnforcer(bot, StatsRepository()).enforce(
                chat_id=chat_id,
                user_id=user_id,
                message_id=message_id,
                reason=result.reason,
            )
        elif result.label == "SPAM":
            # Low-confidence SPAM: alert admins without taking automated action
            try:
                target = _resolve_target(bot, chat_id, user_id)
                lang = get_chat_lang(chat_id)
                notice = get_translated_text("spam_uncertain_notice", lang, TARGET=target)
                bot.send_message(chat_id, notice)
            except Exception as e:
                logger.warning("Failed to send uncertain spam alert", extra={"error": e})

    except Exception as e:
        logger.error(
            "Unexpected error in process_spam_check_task",
            extra={"chat_id": chat_id, "user_id": user_id, "error": e},
            exc_info=True,
        )


def _resolve_target(bot: TelegramClient, chat_id: int, user_id: int) -> str:
    """Resolve a human-readable target mention for uncertain spam alerts."""
    try:
        member = bot.get_chat_member(chat_id, user_id)
        user = member.get("user", {}) if isinstance(member, dict) else {}
        username = user.get("username")
        if username:
            return f"@{username}"
    except Exception as e:
        logger.debug(
            "Failed to resolve uncertain spam target username",
            extra={"chat_id": chat_id, "user_id": user_id, "error": e},
        )
    return f"ID:{user_id}"
