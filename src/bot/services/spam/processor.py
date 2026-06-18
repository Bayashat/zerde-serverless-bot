"""SQS processor for SPAM_CHECK tasks: Layer-2 Groq classification and enforcement."""

from core.config import (
    SPAM_AI_CONFIDENCE_THRESHOLD,
    SPAM_REVIEW_BAN_PREFIX,
    SPAM_REVIEW_IGNORE_PREFIX,
    TELEGRAM_CHANNEL_POST_ACTOR_USER_ID,
    get_chat_lang,
)
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.repositories.captcha import CaptchaRepository
from services.repositories.stats import StatsRepository
from services.spam.chat_member import is_chat_admin_or_creator
from services.spam.enforcer import SpamEnforcer, resolve_spam_target_mention, translate_spam_reason
from services.spam.groq_detector import GroqSpamDetector
from services.telegram import TelegramClient

logger = LoggerAdapter(get_logger(__name__), {})

_detector: GroqSpamDetector | None = None


def _get_detector() -> GroqSpamDetector:
    global _detector
    if _detector is None:
        _detector = GroqSpamDetector()
    return _detector


def process_spam_check_task(
    bot: TelegramClient,
    body: dict,
    captcha_repo: CaptchaRepository | None = None,
) -> None:
    """Process a SPAM_CHECK SQS task: classify with Groq and enforce if confident."""
    try:
        chat_id: int = body["chat_id"]
        user_id: int = body["user_id"]
        message_id: int = body["message_id"]
        text: str = body["text"]
    except (KeyError, TypeError) as e:
        logger.error("Malformed SPAM_CHECK body, skipping", extra={"error": e, "body": body})
        return

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
        result = _get_detector().classify(text)

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

        if result.label == "SPAM" and result.confidence >= SPAM_AI_CONFIDENCE_THRESHOLD:
            SpamEnforcer(bot, StatsRepository()).enforce(
                chat_id=chat_id,
                user_id=user_id,
                message_id=message_id,
                reason=result.reason,
            )
        elif result.label == "SPAM":
            # Low-confidence SPAM: alert admins without taking automated action
            try:
                target = resolve_spam_target_mention(bot, chat_id, user_id)
                lang = get_chat_lang(chat_id)
                reason = translate_spam_reason(result.reason, lang)
                confidence = int(result.confidence * 100)
                notice = get_translated_text(
                    "spam_uncertain_notice",
                    lang,
                    TARGET=target,
                    REASON=reason,
                    CONFIDENCE=confidence,
                )
                bot.send_message(
                    chat_id,
                    notice,
                    reply_markup=_spam_review_keyboard(user_id, message_id, lang),
                )
            except Exception as e:
                logger.warning("Failed to send uncertain spam alert", extra={"error": e})

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
