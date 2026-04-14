"""Tests for linked channel → discussion spam skip helper."""

from core.config import TELEGRAM_CHANNEL_POST_ACTOR_USER_ID
from services.spam.channel_post import should_skip_spam_for_channel_discussion_mirror


def test_skips_when_is_automatic_forward() -> None:
    msg = {
        "is_automatic_forward": True,
        "from": {"id": TELEGRAM_CHANNEL_POST_ACTOR_USER_ID, "first_name": "Telegram"},
        "text": "job ad with @user and https://example.com",
    }
    assert should_skip_spam_for_channel_discussion_mirror(msg) is True


def test_skips_channel_actor_with_sender_chat_fallback() -> None:
    msg = {
        "from": {"id": TELEGRAM_CHANNEL_POST_ACTOR_USER_ID, "first_name": "Telegram"},
        "sender_chat": {"id": -1001037498558, "type": "channel", "title": "News"},
        "text": "content",
    }
    assert should_skip_spam_for_channel_discussion_mirror(msg) is True


def test_does_not_skip_normal_member() -> None:
    msg = {
        "from": {"id": 424242, "first_name": "Human"},
        "text": "hello",
    }
    assert should_skip_spam_for_channel_discussion_mirror(msg) is False


def test_does_not_skip_actor_without_sender_chat() -> None:
    msg = {
        "from": {"id": TELEGRAM_CHANNEL_POST_ACTOR_USER_ID, "first_name": "Telegram"},
        "text": "rare edge",
    }
    assert should_skip_spam_for_channel_discussion_mirror(msg) is False
