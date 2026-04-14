"""Tests for SpamEnforcer notification target rendering."""

from unittest.mock import MagicMock

from core.config import TELEGRAM_CHANNEL_POST_ACTOR_USER_ID
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


def test_enforce_skips_channel_discussion_actor() -> None:
    bot = MagicMock()
    stats_repo = MagicMock()

    SpamEnforcer(bot, stats_repo).enforce(
        chat_id=-1001234567890,
        user_id=TELEGRAM_CHANNEL_POST_ACTOR_USER_ID,
        message_id=42,
        reason="rules:external_mention",
    )

    bot.delete_message.assert_not_called()
    bot.kick_chat_member.assert_not_called()
    stats_repo.increment_total_bans.assert_not_called()
    bot.send_message.assert_not_called()


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


def test_translate_reason_rules_prefix_uses_rules_translation() -> None:
    """Any reason starting with 'rules:' should map to 'spam_reason_rules'."""
    bot = MagicMock()
    bot.get_chat_member.return_value = {"status": "member", "user": {"username": "spammer"}}
    stats_repo = MagicMock()

    enforcer = SpamEnforcer(bot, stats_repo)
    enforcer.enforce(
        chat_id=-1001234567890,
        user_id=12345,
        message_id=42,
        reason="rules:external_mention",
    )

    sent_text = bot.send_message.call_args[0][1]
    # English: "matched spam rules"
    assert "matched spam rules" in sent_text


def test_translate_reason_known_code_uses_specific_translation() -> None:
    """Known reason codes should map to their specific translations."""
    bot = MagicMock()
    bot.get_chat_member.return_value = {"status": "member", "user": {"username": "spammer"}}
    stats_repo = MagicMock()

    enforcer = SpamEnforcer(bot, stats_repo)
    enforcer.enforce(
        chat_id=-1001234567890,
        user_id=12345,
        message_id=42,
        reason="job_offer",
    )

    sent_text = bot.send_message.call_args[0][1]
    # English: "job/income offer"
    assert "job/income offer" in sent_text


def test_translate_reason_unknown_code_uses_fallback() -> None:
    """Unknown reason codes should fall back to 'spam_reason_unknown'."""
    bot = MagicMock()
    bot.get_chat_member.return_value = {"status": "member", "user": {"username": "spammer"}}
    stats_repo = MagicMock()

    enforcer = SpamEnforcer(bot, stats_repo)
    enforcer.enforce(
        chat_id=-1001234567890,
        user_id=12345,
        message_id=42,
        reason="nonexistent_reason_code",
    )

    sent_text = bot.send_message.call_args[0][1]
    # English: "unknown reason"
    assert "unknown reason" in sent_text


def test_translate_reason_all_known_codes() -> None:
    """Test all known reason codes map to their translations."""
    bot = MagicMock()
    bot.get_chat_member.return_value = {"status": "member", "user": {"username": "spammer"}}
    stats_repo = MagicMock()

    known_reasons = [
        ("job_offer", "job/income offer"),
        ("vpn_ad", "VPN advertisement"),
        ("referral_promo", "referral/promotional link"),
        ("selling_services", "selling digital services"),
        ("commercial", "commercial/promotional content"),
        ("suspicious_link", "suspicious link"),
    ]

    enforcer = SpamEnforcer(bot, stats_repo)

    for reason_code, expected_text in known_reasons:
        bot.reset_mock()
        bot.get_chat_member.return_value = {"status": "member", "user": {"username": "spammer"}}

        enforcer.enforce(
            chat_id=-1001234567890,
            user_id=12345,
            message_id=42,
            reason=reason_code,
        )

        sent_text = bot.send_message.call_args[0][1]
        assert expected_text in sent_text, f"Expected '{expected_text}' for reason '{reason_code}'"
