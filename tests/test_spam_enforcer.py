"""Tests for SpamEnforcer moderation behavior and mention rendering."""

from unittest.mock import MagicMock

from core.config import TELEGRAM_CHANNEL_POST_ACTOR_USER_ID
from services.spam.enforcer import SpamEnforcer, resolve_spam_target_mention, translate_spam_reason

from tests import spam_fakes


def test_high_confidence_enforcement_is_silent() -> None:
    bot = MagicMock()
    bot.get_chat_member.return_value = {"status": "member", "user": {"username": "spam_user"}}
    from tests.spam_fakes import MemorySpamRepository

    stats_repo = MemorySpamRepository()

    SpamEnforcer(bot, stats_repo).enforce(
        chat_id=-1001234567890,
        user_id=12345,
        message_id=42,
        reason="rules:external_mention",
    )

    bot.delete_message.assert_called_once_with(-1001234567890, 42, ignore_not_found=True)
    assert bot.kick_chat_member.call_args.args == (-1001234567890, 12345)
    assert bot.kick_chat_member.call_args.kwargs["until_date"] > 0
    bot.ban_chat_member.assert_not_called()
    assert stats_repo.ban_count == 1
    bot.send_message.assert_not_called()


def test_permanent_enforcement_uses_permanent_ban() -> None:
    bot = MagicMock()
    bot.get_chat_member.return_value = {"status": "member", "user": {"username": "spam_user"}}
    from tests.spam_fakes import MemorySpamRepository

    stats_repo = MemorySpamRepository()

    SpamEnforcer(bot, stats_repo).enforce(
        chat_id=-1001234567890,
        user_id=12345,
        message_id=42,
        reason="admin_review",
        permanent=True,
    )

    bot.delete_message.assert_called_once_with(-1001234567890, 42, ignore_not_found=True)
    bot.kick_chat_member.assert_not_called()
    bot.ban_chat_member.assert_called_once_with(-1001234567890, 12345)
    assert stats_repo.ban_count == 1


def test_target_mention_uses_username_when_available() -> None:
    bot = MagicMock()
    bot.get_chat_member.return_value = {"status": "member", "user": {"username": "spam_user"}}

    assert resolve_spam_target_mention(bot, -1001234567890, 12345) == "@spam_user"


def test_target_mention_falls_back_to_clickable_user_link() -> None:
    bot = MagicMock()
    bot.get_chat_member.return_value = {
        "status": "member",
        "user": {"first_name": "Алена <bad>", "last_name": "Coney"},
    }

    mention = resolve_spam_target_mention(bot, -1001234567890, 12345)

    assert mention == '<a href="tg://user?id=12345">Алена &lt;bad&gt; Coney</a>'
    assert "ID:12345" not in mention


def test_enforce_skips_channel_discussion_actor() -> None:
    bot = MagicMock()
    from tests.spam_fakes import MemorySpamRepository

    stats_repo = MemorySpamRepository()

    SpamEnforcer(bot, stats_repo).enforce(
        chat_id=-1001234567890,
        user_id=TELEGRAM_CHANNEL_POST_ACTOR_USER_ID,
        message_id=42,
        reason="rules:external_mention",
    )

    bot.delete_message.assert_not_called()
    bot.kick_chat_member.assert_not_called()
    assert stats_repo.ban_count == 0
    bot.send_message.assert_not_called()


def test_enforce_skips_administrator() -> None:
    bot = MagicMock()
    bot.get_chat_member.return_value = {"status": "administrator", "user": {"username": "admin_user"}}
    from tests.spam_fakes import MemorySpamRepository

    stats_repo = MemorySpamRepository()

    SpamEnforcer(bot, stats_repo).enforce(
        chat_id=-1001234567890,
        user_id=999,
        message_id=42,
        reason="rules:vpn_pattern",
    )

    bot.delete_message.assert_not_called()
    bot.kick_chat_member.assert_not_called()
    assert stats_repo.ban_count == 0
    bot.send_message.assert_not_called()


def test_translate_reason_rules_prefix_uses_rules_translation() -> None:
    assert translate_spam_reason("rules:external_mention", "en") == "referral/promotional link"


def test_translate_reason_rules_prefix_uses_specific_highest_priority_reason() -> None:
    assert translate_spam_reason("rules:external_mention,vpn_pattern,job_offer", "en") == "VPN advertisement"


def test_translate_reason_known_code_uses_specific_translation() -> None:
    assert translate_spam_reason("job_offer", "en") == "job/income offer"


def test_translate_reason_unknown_code_uses_fallback() -> None:
    assert translate_spam_reason("nonexistent_reason_code", "en") == "unknown reason"


def test_translate_reason_all_known_codes() -> None:
    known_reasons = [
        ("job_offer", "job/income offer"),
        ("dm_redirect_scam", "DM redirect scam"),
        ("vpn_ad", "VPN advertisement"),
        ("referral_promo", "referral/promotional link"),
        ("selling_services", "selling digital services"),
        ("account_sale", "account/access sale"),
        ("crypto_investment", "crypto/investment promotion"),
        ("phishing", "phishing or malware"),
        ("adult_gambling", "adult/gambling promotion"),
        ("commercial", "commercial/promotional content"),
        ("suspicious_link", "suspicious link"),
        ("admin_review", "admin-reviewed spam"),
    ]

    for reason_code, expected_text in known_reasons:
        assert translate_spam_reason(reason_code, "en") == expected_text


spam_repo = spam_fakes.spam_repo
