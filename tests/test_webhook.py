"""Tests for webhook event parsing and routing."""

import json

from webhook import (
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


def test_not_relevant_plain_text():
    body = {"message": {"text": "hello world", "chat": {"id": 1}}}
    assert is_event_relevant_to_bot(body) is False


def test_create_response():
    resp = create_response(200, {"message": "ok"})
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["message"] == "ok"
