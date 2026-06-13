"""Linked channel → discussion messages: never treat as normal member spam."""

from typing import Any

from services.telegram_actor import is_linked_channel_discussion_post


def should_skip_spam_for_channel_discussion_mirror(msg: dict[str, Any]) -> bool:
    """Return True for channel posts mirrored into the linked discussion supergroup.

    ``from.id`` is ``TELEGRAM_CHANNEL_POST_ACTOR_USER_ID``, which is not a real
    member, so ``get_chat_member`` admin checks do not apply. Telegram sets
    ``is_automatic_forward`` for the automatic mirror; ``sender_chat`` with
    type ``channel`` is used as a fallback when the flag is absent.
    """
    return is_linked_channel_discussion_post(msg)
