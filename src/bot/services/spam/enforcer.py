"""Spam enforcer: deletes the message, bans the user, and updates moderation stats."""

from core.config import TELEGRAM_CHANNEL_POST_ACTOR_USER_ID
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from core.utils import format_mention
from services.repositories.stats import StatsRepository
from services.spam.chat_member import is_chat_admin_or_creator
from services.telegram import TelegramClient

logger = LoggerAdapter(get_logger(__name__), {})


class SpamEnforcer:
    """Deletes a spam message, bans the sender, and updates moderation stats."""

    def __init__(self, bot: TelegramClient, stats_repo: StatsRepository) -> None:
        self.bot = bot
        self.stats_repo = stats_repo

    def enforce(self, chat_id: int, user_id: int, message_id: int, reason: str) -> None:
        """Delete message + ban user + update stats. Logs each action; never raises."""
        if user_id == TELEGRAM_CHANNEL_POST_ACTOR_USER_ID:
            logger.info(
                "Skipping spam enforcement for channel discussion mirror actor",
                extra={"chat_id": chat_id, "user_id": user_id, "reason": reason},
            )
            return

        if is_chat_admin_or_creator(self.bot, chat_id, user_id):
            logger.info(
                "Skipping spam enforcement for administrator/creator",
                extra={"chat_id": chat_id, "user_id": user_id, "reason": reason},
            )
            return

        logger.info(
            "Enforcing spam action",
            extra={"chat_id": chat_id, "user_id": user_id, "message_id": message_id, "reason": reason},
        )

        try:
            self.bot.delete_message(chat_id, message_id)
        except Exception as e:
            logger.warning(
                "Failed to delete spam message",
                extra={"chat_id": chat_id, "message_id": message_id, "error": e},
            )

        try:
            self.bot.kick_chat_member(chat_id, user_id)
        except Exception as e:
            logger.warning(
                "Failed to ban spam user",
                extra={"chat_id": chat_id, "user_id": user_id, "error": e},
            )

        try:
            self.stats_repo.increment_spam_bans(chat_id)
        except Exception as e:
            logger.warning(
                "Failed to increment spam ban counter",
                extra={"chat_id": chat_id, "error": e},
            )

    def _translate_reason(self, reason: str, lang: str) -> str:
        return translate_spam_reason(reason, lang)


def resolve_spam_target_mention(bot: TelegramClient, chat_id: int, user_id: int) -> str:
    """Resolve a clickable Telegram mention for spam review notices."""
    try:
        member = bot.get_chat_member(chat_id, user_id)
        user = member.get("user", {}) if isinstance(member, dict) else {}
        return format_mention(
            user_id=user_id,
            username=user.get("username"),
            first_name=user.get("first_name") or "User",
            last_name=user.get("last_name"),
        )
    except Exception as e:
        logger.debug(
            "Failed to resolve spam target mention",
            extra={"chat_id": chat_id, "user_id": user_id, "error": e},
        )
    return format_mention(user_id=user_id, username=None, first_name="User")


def translate_spam_reason(reason: str, lang: str) -> str:
    """Translate detector/rule reason codes into user-facing moderation reasons."""
    if reason.startswith("rules:"):
        reason = _primary_rule_reason(reason)

    reason_key = f"spam_reason_{reason}"
    translated = get_translated_text(reason_key, lang)

    if translated == reason_key:
        return get_translated_text("spam_reason_unknown", lang)

    return translated


def _primary_rule_reason(reason: str) -> str:
    rules = {rule.strip() for rule in reason.removeprefix("rules:").split(",") if rule.strip()}
    priority = [
        ("vpn_pattern", "vpn_ad"),
        ("money_and_dm_redirect", "dm_redirect_scam"),
        ("dm_redirect", "dm_redirect_scam"),
        ("money_and_scam_hook", "dm_redirect_scam"),
        ("scam_hook", "dm_redirect_scam"),
        ("job_offer", "job_offer"),
        ("money_pattern", "job_offer"),
        ("external_url", "suspicious_link"),
        ("cis_spam_obfuscation", "suspicious_link"),
        ("external_mention", "referral_promo"),
        ("promo_words", "referral_promo"),
        ("short_text_with_contact", "referral_promo"),
    ]
    for rule, reason_code in priority:
        if rule in rules:
            return reason_code
    return "rules"
