"""Chat membership helpers for spam flows."""

from core.logger import LoggerAdapter, get_logger
from services.telegram import TelegramClient

logger = LoggerAdapter(get_logger(__name__), {})


def is_chat_admin_or_creator(bot: TelegramClient, chat_id: int, user_id: int) -> bool:
    """Return True if the user is an administrator or the group creator.

    On API errors, returns False so enforcement behaviour falls back to the previous path.
    """
    try:
        member = bot.get_chat_member(chat_id, user_id)
        if not isinstance(member, dict):
            return False
        return member.get("status") in ("administrator", "creator")
    except Exception as e:
        logger.debug(
            "get_chat_member failed for admin check",
            extra={"chat_id": chat_id, "user_id": user_id, "error": e},
        )
        return False
