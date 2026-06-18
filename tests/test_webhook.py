"""Tests for webhook event parsing and routing."""

import json
from unittest.mock import MagicMock, patch

from webhook import (
    _handle_api_gateway,
    create_response,
    is_event_relevant_to_bot,
    parse_api_gateway_event,
    verify_webhook_secret_token,
)


def test_verify_valid_token():
    event = {"headers": {"x-telegram-bot-api-secret-token": "test-webhook-secret"}}
    assert verify_webhook_secret_token(event) is True


def test_verify_invalid_token():
    event = {"headers": {"x-telegram-bot-api-secret-token": "wrong-token"}}
    assert verify_webhook_secret_token(event) is False


def test_verify_missing_token():
    event = {"headers": {}}
    assert verify_webhook_secret_token(event) is False


def test_parse_json_body():
    body_dict = {"update_id": 123, "message": {"text": "/start"}}
    event = {"body": json.dumps(body_dict), "isBase64Encoded": False}
    result = parse_api_gateway_event(event)
    assert result["update_id"] == 123


def test_is_relevant_command():
    body = {"message": {"text": "/start", "chat": {"id": 1}}}
    assert is_event_relevant_to_bot(body) is True


def test_is_relevant_callback():
    body = {"callback_query": {"data": "verify_123"}}
    assert is_event_relevant_to_bot(body) is True


def test_is_relevant_new_members():
    body = {"message": {"new_chat_members": [{"id": 1}], "chat": {"id": 1}}}
    assert is_event_relevant_to_bot(body) is True


def test_relevant_plain_text():
    # Plain text is now routed for captcha answer checking
    body = {"message": {"text": "hello world", "chat": {"id": 1}}}
    assert is_event_relevant_to_bot(body) is True


def test_is_relevant_document_only():
    body = {"message": {"document": {"file_id": "AgADx"}, "chat": {"id": 1}}}
    assert is_event_relevant_to_bot(body) is True


def test_is_relevant_linked_channel_photo_post():
    body = {
        "message": {
            "message_id": 11,
            "photo": [{"file_id": "photo-id"}],
            "chat": {"id": -100123, "type": "supergroup"},
            "from": {"id": 777000, "is_bot": False, "first_name": "Telegram"},
            "sender_chat": {"id": -100456, "type": "channel", "title": "Official Channel"},
            "is_automatic_forward": True,
        }
    }
    assert is_event_relevant_to_bot(body) is True


def test_create_response():
    resp = create_response(200, {"message": "ok"})
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["message"] == "ok"


def test_rule_filter_external_mention_requires_risk_signal_with_at():
    """Layer-1: ``@`` alone does not add ``external_mention``; needs vpn/money/job/mixed-script."""
    from services.spam.rule_filter import RuleBasedSpamFilter

    f = RuleBasedSpamFilter()
    _, rules_plain = f.check("hello @someone", 1, -1001)
    assert "external_mention" not in rules_plain

    _, rules_risky = f.check("впн реклама @bad", 1, -1001)
    assert "external_mention" in rules_risky


def test_pending_captcha_message_skips_spam_screening():
    body = {
        "message": {
            "message_id": 10,
            "text": "Работаееет",
            "external_reply": {
                "origin": {
                    "type": "channel",
                    "chat": {"id": -1004414999335, "title": "NordVPN - Бесплатный ВПН", "type": "channel"},
                },
                "chat": {"id": -1004414999335, "title": "NordVPN - Бесплатный ВПН", "type": "channel"},
            },
            "quote": {"text": "NordVPN — бесплатный ВПН, YouTube и Telegram летают"},
            "chat": {"id": -100123, "type": "supergroup"},
            "from": {"id": 42, "is_bot": False},
        }
    }
    event = {
        "headers": {"x-telegram-bot-api-secret-token": "test-webhook-secret"},
        "body": json.dumps(body),
    }
    dispatcher = MagicMock()
    dispatcher.captcha_repo.get_pending.return_value = {"expected": "3719"}
    screener = MagicMock()
    screener.should_screen.return_value = True

    with (
        patch("webhook._spam_screening", return_value=screener),
        patch("webhook.is_configured_group_chat", return_value=True),
        patch("webhook.observe_group_memory_update") as observe_memory,
        patch("webhook.maybe_enqueue_ambient_reaction") as ambient_reaction,
        patch("webhook.handle_group_agent_update") as group_agent,
    ):
        _handle_api_gateway(event, dispatcher, MagicMock())

    screener.run.assert_not_called()
    observe_memory.assert_not_called()
    ambient_reaction.assert_not_called()
    group_agent.assert_not_called()
    dispatcher.process_update.assert_called_once_with(body)


def test_enforced_spam_short_circuits_normal_group_flows():
    body = {
        "message": {
            "message_id": 10,
            "text": "vpn реклама @spam_bot",
            "chat": {"id": -100123, "type": "supergroup"},
            "from": {"id": 42, "is_bot": False},
        }
    }
    event = {
        "headers": {"x-telegram-bot-api-secret-token": "test-webhook-secret"},
        "body": json.dumps(body),
    }
    dispatcher = MagicMock()
    dispatcher.captcha_repo.get_pending.return_value = None
    screener = MagicMock()
    screener.should_screen.return_value = True
    screener.run.return_value = "enforced"

    with (
        patch("webhook._spam_screening", return_value=screener),
        patch("webhook.is_configured_group_chat", return_value=True),
        patch("webhook.observe_group_memory_update") as observe_memory,
        patch("webhook.maybe_enqueue_ambient_reaction") as ambient_reaction,
        patch("webhook.handle_group_agent_update") as group_agent,
    ):
        resp = _handle_api_gateway(event, dispatcher, MagicMock())

    assert json.loads(resp["body"])["message"] == "ok"
    screener.run.assert_called_once_with(body)
    observe_memory.assert_not_called()
    ambient_reaction.assert_not_called()
    group_agent.assert_not_called()
    dispatcher.process_update.assert_not_called()


def test_queued_spam_short_circuits_normal_group_flows():
    body = {
        "message": {
            "message_id": 10,
            "text": "Кому интересно, скину про инвестиции",
            "chat": {"id": -100123, "type": "supergroup"},
            "from": {"id": 42, "is_bot": False},
        }
    }
    event = {
        "headers": {"x-telegram-bot-api-secret-token": "test-webhook-secret"},
        "body": json.dumps(body),
    }
    dispatcher = MagicMock()
    dispatcher.captcha_repo.get_pending.return_value = None
    screener = MagicMock()
    screener.should_screen.return_value = True
    screener.run.return_value = "queued"

    with (
        patch("webhook._spam_screening", return_value=screener),
        patch("webhook.is_configured_group_chat", return_value=True),
        patch("webhook.observe_group_memory_update") as observe_memory,
        patch("webhook.maybe_enqueue_ambient_reaction") as ambient_reaction,
        patch("webhook.handle_group_agent_update") as group_agent,
    ):
        resp = _handle_api_gateway(event, dispatcher, MagicMock())

    assert json.loads(resp["body"])["message"] == "ok"
    screener.run.assert_called_once_with(body)
    observe_memory.assert_not_called()
    ambient_reaction.assert_not_called()
    group_agent.assert_not_called()
    dispatcher.process_update.assert_not_called()
