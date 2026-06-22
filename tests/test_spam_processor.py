"""Tests for process_spam_check_task with mocked GroqSpamDetector and SpamEnforcer."""

from unittest.mock import MagicMock, patch

import pytest
from core.config import TELEGRAM_CHANNEL_POST_ACTOR_USER_ID
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


def _make_result(
    label: str,
    confidence: float,
    error: bool = False,
    reason: str | None = None,
) -> SpamCheckResult:
    if reason is None:
        reason = "job_offer" if label == "SPAM" else "not_spam"
    return SpamCheckResult(label=label, confidence=confidence, reason=reason, error=error)


# ---------------------------------------------------------------------------
# GroqSpamDetector is lazy-loaded via _get_detector(); patch the getter to
# return a MagicMock with a stubbed classify() implementation.
# ---------------------------------------------------------------------------


@patch("services.spam.processor.StatsRepository")
@patch("services.spam.processor.SpamEnforcer")
@patch("services.spam.processor._get_detector")
def test_spam_high_confidence_calls_enforce(mock_get_detector, mock_enforcer_cls, mock_stats_cls, mock_bot):
    mock_detector = MagicMock()
    mock_get_detector.return_value = mock_detector
    mock_detector.classify.return_value = _make_result("SPAM", 0.95, reason="job_offer")
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
@patch("services.spam.processor._get_detector")
def test_not_spam_does_not_call_enforce(mock_get_detector, mock_enforcer_cls, mock_stats_cls, mock_bot):
    mock_detector = MagicMock()
    mock_get_detector.return_value = mock_detector
    mock_detector.classify.return_value = _make_result("NOT_SPAM", 0.98)
    mock_enforcer = mock_enforcer_cls.return_value

    process_spam_check_task(mock_bot, _BODY)

    mock_enforcer.enforce.assert_not_called()


@patch("services.spam.processor.StatsRepository")
@patch("services.spam.processor.SpamEnforcer")
@patch("services.spam.processor._get_detector")
def test_spam_low_confidence_does_not_enforce(mock_get_detector, mock_enforcer_cls, mock_stats_cls, mock_bot):
    mock_detector = MagicMock()
    mock_get_detector.return_value = mock_detector
    mock_detector.classify.return_value = _make_result("SPAM", 0.70)
    mock_enforcer = mock_enforcer_cls.return_value

    process_spam_check_task(mock_bot, _BODY)

    mock_enforcer.enforce.assert_not_called()


@patch("services.spam.processor.StatsRepository")
@patch("services.spam.processor.SpamEnforcer")
@patch("services.spam.processor._get_detector")
def test_api_error_does_not_enforce(mock_get_detector, mock_enforcer_cls, mock_stats_cls, mock_bot):
    mock_detector = MagicMock()
    mock_get_detector.return_value = mock_detector
    mock_detector.classify.return_value = _make_result("NOT_SPAM", 0.0, error=True)
    mock_enforcer = mock_enforcer_cls.return_value

    process_spam_check_task(mock_bot, _BODY)

    mock_enforcer.enforce.assert_not_called()


@patch("services.spam.processor._get_detector")
@patch("services.spam.processor.is_chat_admin_or_creator", return_value=True)
def test_skips_chat_admin_before_groq(mock_is_admin, mock_get_detector, mock_bot):
    mock_get_detector.return_value = MagicMock()
    process_spam_check_task(mock_bot, _BODY)
    mock_get_detector.return_value.classify.assert_not_called()


@patch("services.spam.processor._get_detector")
def test_skips_channel_discussion_actor_before_groq(mock_get_detector, mock_bot):
    mock_get_detector.return_value = MagicMock()
    body = {**_BODY, "user_id": TELEGRAM_CHANNEL_POST_ACTOR_USER_ID}
    process_spam_check_task(mock_bot, body)
    mock_get_detector.return_value.classify.assert_not_called()


@patch("services.spam.processor._get_detector")
def test_skips_pending_captcha_before_groq(mock_get_detector, mock_bot):
    mock_get_detector.return_value = MagicMock()
    captcha_repo = MagicMock()
    captcha_repo.get_pending.return_value = {"expected": "3719"}

    process_spam_check_task(mock_bot, _BODY, captcha_repo=captcha_repo)

    captcha_repo.get_pending.assert_called_once_with(_BODY["chat_id"], _BODY["user_id"])
    mock_get_detector.return_value.classify.assert_not_called()


@patch("services.spam.processor._get_detector")
def test_malformed_body_does_not_raise(mock_get_detector, mock_bot):
    # Missing required keys
    for bad_body in [{}, {"task_type": "SPAM_CHECK"}, None]:
        try:
            process_spam_check_task(mock_bot, bad_body)
        except Exception as e:
            pytest.fail(f"process_spam_check_task raised {e!r} for body={bad_body!r}")


@patch("services.spam.processor.StatsRepository")
@patch("services.spam.processor.SpamEnforcer")
@patch("services.spam.processor.get_chat_lang", return_value="en")
@patch("services.spam.processor._get_detector")
def test_spam_low_confidence_sends_alert(
    mock_get_detector,
    _mock_lang,
    mock_enforcer_cls,
    mock_stats_cls,
    mock_bot,
):
    mock_detector = MagicMock()
    mock_get_detector.return_value = mock_detector
    mock_detector.classify.return_value = _make_result("SPAM", 0.70, reason="dm_redirect_scam")
    mock_bot.get_chat_member.return_value = {"status": "member", "user": {"username": "suspicious_user"}}

    process_spam_check_task(mock_bot, _BODY)

    mock_bot.send_message.assert_called_once()
    args = mock_bot.send_message.call_args[0]
    kwargs = mock_bot.send_message.call_args.kwargs
    assert args[0] == _BODY["chat_id"]
    assert isinstance(args[1], str)
    assert "@suspicious_user" in args[1]
    assert "DM redirect scam" in args[1]
    assert "70%" in args[1]
    assert kwargs["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "spam_ban:111222333:42"
    assert kwargs["reply_markup"]["inline_keyboard"][0][1]["callback_data"] == "spam_ignore:111222333:42"


@patch("services.spam.processor.StatsRepository")
@patch("services.spam.processor.SpamEnforcer")
@patch("services.spam.processor.get_chat_lang", return_value="en")
@patch("services.spam.processor._get_detector")
def test_money_only_high_confidence_spam_sends_review_not_auto_ban(
    mock_get_detector,
    _mock_lang,
    mock_enforcer_cls,
    mock_stats_cls,
    mock_bot,
) -> None:
    mock_detector = MagicMock()
    mock_get_detector.return_value = mock_detector
    mock_detector.classify.return_value = _make_result("SPAM", 0.95, reason="selling_services")
    mock_bot.get_chat_member.return_value = {"status": "member", "user": {"username": "fafnirdragon"}}
    body = {
        **_BODY,
        "text": "Смекта 2000тг деп куткарам.",
        "triggered_rules": ["money_pattern"],
        "rule_score": 0.3,
        "message_context": {
            "current_message": "Смекта 2000тг деп куткарам.",
            "triggered_rules": ["money_pattern"],
            "rule_score": 0.3,
        },
    }

    process_spam_check_task(mock_bot, body)

    mock_enforcer_cls.return_value.enforce.assert_not_called()
    mock_bot.send_message.assert_called_once()
    assert "@fafnirdragon" in mock_bot.send_message.call_args[0][1]
    assert "selling digital services" in mock_bot.send_message.call_args[0][1]


@patch("services.spam.processor.StatsRepository")
@patch("services.spam.processor.SpamEnforcer")
@patch("services.spam.processor.get_chat_lang", return_value="en")
@patch("services.spam.processor._get_detector")
def test_job_rule_alone_high_confidence_spam_sends_review_not_auto_ban(
    mock_get_detector,
    _mock_lang,
    mock_enforcer_cls,
    mock_stats_cls,
    mock_bot,
) -> None:
    mock_detector = MagicMock()
    mock_get_detector.return_value = mock_detector
    mock_detector.classify.return_value = _make_result("SPAM", 0.95, reason="job_offer")
    mock_bot.get_chat_member.return_value = {"status": "member", "user": {"username": "maybe_recruiter"}}
    body = {
        **_BODY,
        "text": "работа удаленно",
        "triggered_rules": ["job_offer"],
        "rule_score": 0.25,
        "message_context": {
            "current_message": "работа удаленно",
            "triggered_rules": ["job_offer"],
            "rule_score": 0.25,
        },
    }

    process_spam_check_task(mock_bot, body)

    mock_enforcer_cls.return_value.enforce.assert_not_called()
    mock_bot.send_message.assert_called_once()


@patch("services.spam.processor.StatsRepository")
@patch("services.spam.processor.SpamEnforcer")
@patch("services.spam.processor.get_chat_lang", return_value="en")
@patch("services.spam.processor.get_spam_review_admin_mentions", return_value=("bayashat", "yeskabyl"))
@patch("services.spam.processor._get_detector")
def test_spam_review_alert_mentions_configured_admins(
    mock_get_detector,
    _mock_mentions,
    _mock_lang,
    mock_enforcer_cls,
    mock_stats_cls,
    mock_bot,
) -> None:
    mock_detector = MagicMock()
    mock_get_detector.return_value = mock_detector
    mock_detector.classify.return_value = _make_result("SPAM", 0.70, reason="dm_redirect_scam")
    mock_bot.get_chat_member.return_value = {"status": "member", "user": {"username": "suspicious_user"}}

    process_spam_check_task(mock_bot, _BODY)

    text = mock_bot.send_message.call_args[0][1]
    assert text.startswith("@bayashat @yeskabyl\n")
    mock_enforcer_cls.return_value.enforce.assert_not_called()


@patch("services.spam.processor.StatsRepository")
@patch("services.spam.processor.SpamEnforcer")
@patch("services.spam.processor._get_detector")
def test_spam_processor_adds_bounded_recent_context(
    mock_get_detector,
    mock_enforcer_cls,
    mock_stats_cls,
    mock_bot,
) -> None:
    mock_detector = MagicMock()
    mock_get_detector.return_value = mock_detector
    mock_detector.classify.return_value = _make_result("NOT_SPAM", 0.98)
    memory_repo = MagicMock()
    memory_repo.get_recent_messages.return_value = [
        {"message_id": 1, "display_name": "Aman", "text": "ФГДС жасап кету керек."},
        {"message_id": 2, "display_name": "Lio", "text": "За что."},
    ]

    process_spam_check_task(mock_bot, _BODY, memory_repo=memory_repo)

    memory_repo.get_recent_messages.assert_called_once_with(_BODY["chat_id"], limit=12)
    classifier_input = mock_detector.classify.call_args[0][0]
    assert "CURRENT_MESSAGE:" in classifier_input
    assert "RECENT_GROUP_MESSAGES" in classifier_input
    assert "Aman: ФГДС жасап кету керек." in classifier_input
    mock_enforcer_cls.return_value.enforce.assert_not_called()


@patch("services.spam.processor.StatsRepository")
@patch("services.spam.processor.SpamEnforcer")
@patch("services.spam.processor.get_chat_lang", return_value="en")
@patch("services.spam.processor._get_detector")
def test_spam_low_confidence_alert_uses_clickable_mention_without_username(
    mock_get_detector,
    _mock_lang,
    mock_enforcer_cls,
    mock_stats_cls,
    mock_bot,
):
    mock_detector = MagicMock()
    mock_get_detector.return_value = mock_detector
    mock_detector.classify.return_value = _make_result("SPAM", 0.70, reason="dm_redirect_scam")
    mock_bot.get_chat_member.return_value = {
        "status": "member",
        "user": {"first_name": "Алена <bad>", "last_name": "Coney"},
    }

    process_spam_check_task(mock_bot, _BODY)

    text = mock_bot.send_message.call_args[0][1]
    assert '<a href="tg://user?id=111222333">Алена &lt;bad&gt; Coney</a>' in text
    assert "ID:111222333" not in text
    mock_enforcer_cls.return_value.enforce.assert_not_called()
