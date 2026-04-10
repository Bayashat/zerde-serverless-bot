"""Spam enforcer: silently deletes the message and bans the user."""

from core.logger import LoggerAdapter, get_logger
from services.repositories.stats import StatsRepository
from services.telegram import TelegramClient

logger = LoggerAdapter(get_logger(__name__), {})


class SpamEnforcer:
    """Deletes a spam message and bans the sender. Never raises."""

    def __init__(self, bot: TelegramClient, stats_repo: StatsRepository) -> None:
        self.bot = bot
        self.stats_repo = stats_repo

    def enforce(self, chat_id: int, user_id: int, message_id: int, reason: str) -> None:
        """Delete message + ban user. Logs each action; never raises."""
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
            self.stats_repo.increment_total_bans(chat_id)
        except Exception as e:
            logger.warning(
                "Failed to increment ban counter",
                extra={"chat_id": chat_id, "error": e},
            )
