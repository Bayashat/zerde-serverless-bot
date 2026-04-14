"""Linked channel → discussion messages: never treat as normal member spam."""

from typing import Any

from core.config import TELEGRAM_CHANNEL_POST_ACTOR_USER_ID


def should_skip_spam_for_channel_discussion_mirror(msg: dict[str, Any]) -> bool:
    """Return True for channel posts mirrored into the linked discussion supergroup.

    ``from.id`` is ``TELEGRAM_CHANNEL_POST_ACTOR_USER_ID``, which is not a real
    member, so ``get_chat_member`` admin checks do not apply. Telegram sets
    ``is_automatic_forward`` for the automatic mirror; ``sender_chat`` with
    type ``channel`` is used as a fallback when the flag is absent.
    """
    if msg.get("is_automatic_forward"):
        return True
    from_user = msg.get("from")
    if not isinstance(from_user, dict):
        return False
    if from_user.get("id") != TELEGRAM_CHANNEL_POST_ACTOR_USER_ID:
        return False
    sender_chat = msg.get("sender_chat")
    return isinstance(sender_chat, dict) and sender_chat.get("type") == "channel"
