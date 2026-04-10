"""Spam enforcer: deletes the message, bans the user, and notifies the group."""

from core.config import get_chat_lang
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.repositories.stats import StatsRepository
from services.spam.chat_member import is_chat_admin_or_creator
from services.telegram import TelegramClient

logger = LoggerAdapter(get_logger(__name__), {})


class SpamEnforcer:
    """Deletes a spam message, bans the sender, and notifies the group."""

    def __init__(self, bot: TelegramClient, stats_repo: StatsRepository) -> None:
        self.bot = bot
        self.stats_repo = stats_repo

    def enforce(self, chat_id: int, user_id: int, message_id: int, reason: str) -> None:
        """Delete message + ban user + notify group. Logs each action; never raises."""
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
        target = self._resolve_target(chat_id, user_id)

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
            self.stats_repo.increment_total_bans(chat_id)
        except Exception as e:
            logger.warning(
                "Failed to increment ban counter",
                extra={"chat_id": chat_id, "error": e},
            )

        try:
            lang = get_chat_lang(chat_id)
            notice = get_translated_text("spam_enforced_notice", lang, TARGET=target)
            self.bot.send_message(chat_id, notice)
        except Exception as e:
            logger.warning(
                "Failed to send spam enforcement notice",
                extra={"chat_id": chat_id, "error": e},
            )

    def _resolve_target(self, chat_id: int, user_id: int) -> str:
        """Resolve a human-readable target mention for notifications."""
        try:
            member = self.bot.get_chat_member(chat_id, user_id)
            user = member.get("user", {}) if isinstance(member, dict) else {}
            username = user.get("username")
            if username:
                return f"@{username}"
        except Exception as e:
            logger.debug(
                "Failed to resolve spam target username",
                extra={"chat_id": chat_id, "user_id": user_id, "error": e},
            )
        return f"ID:{user_id}"
