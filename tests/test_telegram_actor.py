from core.config import TELEGRAM_CHANNEL_POST_ACTOR_USER_ID
from services.telegram_actor import (
    actor_display_name,
    actor_sender_type,
    actor_username,
    is_linked_channel_discussion_post,
    message_actor,
)


def test_linked_channel_discussion_post_prefers_sender_chat_actor() -> None:
    message = {
        "is_automatic_forward": True,
        "from": {"id": TELEGRAM_CHANNEL_POST_ACTOR_USER_ID, "first_name": "Telegram", "is_bot": False},
        "sender_chat": {
            "id": -1001037498558,
            "title": "Тимурдан Инфо | it&tech",
            "username": "timurdaninfo",
            "type": "channel",
        },
    }

    actor = message_actor(message)

    assert is_linked_channel_discussion_post(message) is True
    assert actor["id"] == -1001037498558
    assert actor_display_name(actor) == "Тимурдан Инфо | it&tech"
    assert actor_username(actor) == "timurdaninfo"
    assert actor_sender_type(actor) == "channel"


def test_normal_message_actor_uses_from_user() -> None:
    message = {
        "from": {"id": 42, "first_name": "Ada", "username": "ada", "is_bot": False},
        "sender_chat": {"id": -1001, "title": "Channel", "type": "channel"},
    }

    actor = message_actor(message)

    assert is_linked_channel_discussion_post(message) is False
    assert actor["id"] == 42
    assert actor_display_name(actor) == "Ada"
    assert actor_username(actor) == "ada"
    assert actor_sender_type(actor) == "user"
