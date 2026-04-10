"""SQS processor for SPAM_CHECK tasks: Layer-2 Groq classification and enforcement."""

from core.logger import LoggerAdapter, get_logger
from services.repositories.stats import StatsRepository
from services.spam.enforcer import SpamEnforcer
from services.spam.groq_detector import GroqSpamDetector
from services.telegram import TelegramClient

logger = LoggerAdapter(get_logger(__name__), {})

_UNCERTAIN_SPAM_MSG = "⚠️ Suspicious message detected, but confidence is low — admins please check."
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
                reason=f"groq_spam:{result.confidence:.2f}",
            )
        elif result.label == "SPAM":
            # Low-confidence SPAM: alert admins without taking automated action
            try:
                bot.send_message(chat_id, _UNCERTAIN_SPAM_MSG)
            except Exception as e:
                logger.warning("Failed to send uncertain spam alert", extra={"error": e})

    except Exception as e:
        logger.error(
            "Unexpected error in process_spam_check_task",
            extra={"chat_id": chat_id, "user_id": user_id, "error": e},
            exc_info=True,
        )
