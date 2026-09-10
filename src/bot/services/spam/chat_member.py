"""Chat membership helpers for spam flows."""

from core.logger import LoggerAdapter, get_logger
from services.telegram import TelegramClient

logger = LoggerAdapter(get_logger(__name__), {})


def is_chat_admin_or_creator(bot: TelegramClient, chat_id: int, user_id: int, *, raise_on_error: bool = False) -> bool:
    """Return True if the user is an administrator or the group creator.

    Authorization callers deny on lookup errors. Moderation workers opt into
    raising, so unknown membership cannot be classified or acted on as ordinary.
    """
    try:
        member = bot.get_chat_member(chat_id, user_id)
        if not isinstance(member, dict) or member.get("status") not in {
            "member",
            "administrator",
            "creator",
            "restricted",
            "left",
            "kicked",
        }:
            if raise_on_error:
                raise RuntimeError("Cannot verify chat membership")
            return False
        return member.get("status") in ("administrator", "creator")
    except Exception as e:
        if raise_on_error:
            raise
        logger.debug(
            "get_chat_member failed for admin check",
            extra={"chat_id": chat_id, "user_id": user_id, "error": e},
        )
        return False
