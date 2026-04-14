"""Tests for process_spam_check_task with mocked GroqSpamDetector and SpamEnforcer."""

from unittest.mock import MagicMock, patch

import pytest
from services.spam.groq_detector import SpamCheckResult
from services.spam.processor import process_spam_check_task

_BODY = {
    "task_type": "SPAM_CHECK",
    "chat_id": -1001234567890,
    "user_id": 111222333,
    "message_id": 42,
    "text": "ОНЛАЙН РАБОТА C ДОХОДОМ ОТ 230$! @spam_bot",
    "triggered_rules": ["external_mention", "money_pattern"],
}


@pytest.fixture
def mock_bot():
    return MagicMock()


def _make_result(label, confidence, error=False, reason="job_offer"):
    return SpamCheckResult(label=label, confidence=confidence, reason=reason, error=error)


@patch("services.spam.processor.StatsRepository")
@patch("services.spam.processor.SpamEnforcer")
@patch("services.spam.processor.GroqSpamDetector")
def test_spam_high_confidence_calls_enforce(mock_detector_cls, mock_enforcer_cls, mock_stats_cls, mock_bot):
    mock_detector_cls.return_value.classify.return_value = _make_result("SPAM", 0.95, reason="job_offer")
    mock_enforcer = mock_enforcer_cls.return_value

    process_spam_check_task(mock_bot, _BODY)

    mock_enforcer.enforce.assert_called_once_with(
        chat_id=_BODY["chat_id"],
        user_id=_BODY["user_id"],
        message_id=_BODY["message_id"],
        reason="job_offer",
    )


@patch("services.spam.processor.StatsRepository")
@patch("services.spam.processor.SpamEnforcer")
@patch("services.spam.processor.GroqSpamDetector")
def test_not_spam_does_not_call_enforce(mock_detector_cls, mock_enforcer_cls, mock_stats_cls, mock_bot):
    mock_detector_cls.return_value.classify.return_value = _make_result("NOT_SPAM", 0.98)
    mock_enforcer = mock_enforcer_cls.return_value

    process_spam_check_task(mock_bot, _BODY)

    mock_enforcer.enforce.assert_not_called()


@patch("services.spam.processor.StatsRepository")
@patch("services.spam.processor.SpamEnforcer")
@patch("services.spam.processor.GroqSpamDetector")
def test_spam_low_confidence_does_not_enforce(mock_detector_cls, mock_enforcer_cls, mock_stats_cls, mock_bot):
    mock_detector_cls.return_value.classify.return_value = _make_result("SPAM", 0.70)
    mock_enforcer = mock_enforcer_cls.return_value

    process_spam_check_task(mock_bot, _BODY)

    mock_enforcer.enforce.assert_not_called()


@patch("services.spam.processor.StatsRepository")
@patch("services.spam.processor.SpamEnforcer")
@patch("services.spam.processor.GroqSpamDetector")
def test_api_error_does_not_enforce(mock_detector_cls, mock_enforcer_cls, mock_stats_cls, mock_bot):
    mock_detector_cls.return_value.classify.return_value = _make_result("NOT_SPAM", 0.0, error=True)
    mock_enforcer = mock_enforcer_cls.return_value

    process_spam_check_task(mock_bot, _BODY)

    mock_enforcer.enforce.assert_not_called()


@patch("services.spam.processor.GroqSpamDetector")
@patch("services.spam.processor.is_chat_admin_or_creator", return_value=True)
def test_skips_chat_admin_before_groq(mock_is_admin, mock_detector_cls, mock_bot):
    process_spam_check_task(mock_bot, _BODY)
    mock_detector_cls.assert_not_called()


@patch("services.spam.processor.GroqSpamDetector")
def test_malformed_body_does_not_raise(mock_detector_cls, mock_bot):
    # Missing required keys
    for bad_body in [{}, {"task_type": "SPAM_CHECK"}, None]:
        try:
            process_spam_check_task(mock_bot, bad_body)
        except Exception as e:
            pytest.fail(f"process_spam_check_task raised {e!r} for body={bad_body!r}")


@patch("services.spam.processor.StatsRepository")
@patch("services.spam.processor.SpamEnforcer")
@patch("services.spam.processor.GroqSpamDetector")
def test_spam_low_confidence_sends_alert(mock_detector_cls, mock_enforcer_cls, mock_stats_cls, mock_bot):
    mock_detector_cls.return_value.classify.return_value = _make_result("SPAM", 0.70)
    mock_bot.get_chat_member.return_value = {"status": "member", "user": {"username": "suspicious_user"}}

    process_spam_check_task(mock_bot, _BODY)

    mock_bot.send_message.assert_called_once()
    args = mock_bot.send_message.call_args[0]
    assert args[0] == _BODY["chat_id"]
    assert isinstance(args[1], str)
    assert "@suspicious_user" in args[1]
