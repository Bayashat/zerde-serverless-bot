"""Tests for SpamEnforcer notification target rendering."""

from unittest.mock import MagicMock

from services.spam.enforcer import SpamEnforcer


def test_enforce_notice_uses_username_when_available() -> None:
    bot = MagicMock()
    bot.get_chat_member.return_value = {"status": "member", "user": {"username": "spam_user"}}
    stats_repo = MagicMock()

    SpamEnforcer(bot, stats_repo).enforce(
        chat_id=-1001234567890,
        user_id=12345,
        message_id=42,
        reason="rules:external_mention",
    )

    sent_text = bot.send_message.call_args[0][1]
    assert "@spam_user" in sent_text


def test_enforce_notice_falls_back_to_user_id_when_username_missing() -> None:
    bot = MagicMock()
    bot.get_chat_member.return_value = {"status": "member", "user": {}}
    stats_repo = MagicMock()

    SpamEnforcer(bot, stats_repo).enforce(
        chat_id=-1001234567890,
        user_id=12345,
        message_id=42,
        reason="rules:external_mention",
    )

    sent_text = bot.send_message.call_args[0][1]
    assert "ID:12345" in sent_text


def test_enforce_skips_administrator() -> None:
    bot = MagicMock()
    bot.get_chat_member.return_value = {"status": "administrator", "user": {"username": "admin_user"}}
    stats_repo = MagicMock()

    SpamEnforcer(bot, stats_repo).enforce(
        chat_id=-1001234567890,
        user_id=999,
        message_id=42,
        reason="rules:vpn_pattern",
    )

    bot.delete_message.assert_not_called()
    bot.kick_chat_member.assert_not_called()
    stats_repo.increment_total_bans.assert_not_called()
    bot.send_message.assert_not_called()
