"""Tests for layer-1 spam screening outcomes."""

from unittest.mock import MagicMock, patch

from services.spam.screening_service import SpamScreeningService


def _body(text: str = "vpn реклама @spam_bot") -> dict:
    return {
        "message": {
            "message_id": 42,
            "text": text,
            "chat": {"id": -1001234567890, "type": "supergroup"},
            "from": {"id": 12345, "is_bot": False},
        }
    }


@patch("services.spam.screening_service.StatsRepository")
@patch("services.spam.screening_service.SpamEnforcer")
@patch("services.spam.screening_service.is_chat_admin_or_creator", return_value=False)
def test_rule_enforced_spam_returns_enforced(_mock_admin, mock_enforcer_cls, _mock_stats_cls) -> None:
    sqs = MagicMock()
    service = SpamScreeningService(MagicMock(), sqs)

    outcome = service.run(_body())

    assert outcome == "enforced"
    mock_enforcer_cls.return_value.enforce.assert_called_once()
    sqs.send_spam_check_task.assert_not_called()


@patch("services.spam.screening_service.RuleBasedSpamFilter")
@patch("services.spam.screening_service.is_chat_admin_or_creator", return_value=False)
def test_ambiguous_spam_returns_queued(_mock_admin, mock_filter_cls) -> None:
    mock_filter_cls.return_value.check.return_value = (0.35, ["finance_soft_lead_bait"])
    sqs = MagicMock()
    service = SpamScreeningService(MagicMock(), sqs)

    outcome = service.run(_body("Кому интересно, скину про инвестиции"))

    assert outcome == "queued"
    sqs.send_spam_check_task.assert_called_once()
    kwargs = sqs.send_spam_check_task.call_args.kwargs
    assert kwargs["rule_score"] == 0.35
    assert kwargs["message_context"]["current_message"] == "Кому интересно, скину про инвестиции"
    assert kwargs["message_context"]["triggered_rules"] == ["finance_soft_lead_bait"]


@patch("services.spam.screening_service.RuleBasedSpamFilter")
@patch("services.spam.screening_service.is_chat_admin_or_creator", return_value=False)
def test_queued_spam_payload_includes_reply_context(_mock_admin, mock_filter_cls) -> None:
    mock_filter_cls.return_value.check.return_value = (0.3, ["money_pattern"])
    sqs = MagicMock()
    service = SpamScreeningService(MagicMock(), sqs)
    body = _body("Смекта 2000тг деп куткарам.")
    body["message"]["reply_to_message"] = {
        "message_id": 41,
        "from": {"id": 7, "first_name": "Ruslanuly", "username": "yeskabyl"},
        "text": "заблокировал(а) Grand Theft Auto VI [IHN] (@fafnirdragon)",
    }

    outcome = service.run(body)

    assert outcome == "queued"
    context = sqs.send_spam_check_task.call_args.kwargs["message_context"]
    assert context["current_message"] == "Смекта 2000тг деп куткарам."
    assert context["reply_to_message"]["from"] == "@yeskabyl"
    assert "заблокировал" in context["reply_to_message"]["text"]


@patch("services.spam.screening_service.RuleBasedSpamFilter")
@patch("services.spam.screening_service.is_chat_admin_or_creator", return_value=False)
def test_clean_message_returns_none(_mock_admin, mock_filter_cls) -> None:
    mock_filter_cls.return_value.check.return_value = (0.0, [])
    service = SpamScreeningService(MagicMock(), MagicMock())

    assert service.run(_body("обычный разговор")) == "none"


@patch("services.spam.screening_service.RuleBasedSpamFilter")
@patch("services.spam.screening_service.is_chat_admin_or_creator", return_value=False)
def test_screening_exception_returns_error(_mock_admin, mock_filter_cls) -> None:
    mock_filter_cls.return_value.check.side_effect = RuntimeError("boom")
    service = SpamScreeningService(MagicMock(), MagicMock())

    assert service.run(_body()) == "error"
