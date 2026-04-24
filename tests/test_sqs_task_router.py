"""Tests for SQS task routing and failure propagation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from services.repositories.captcha import CaptchaRepository
from services.sqs_task_router import process_sqs_event


def _record(body: dict) -> dict:
    return {"messageId": "mid-1", "body": json.dumps(body)}


def test_check_timeout_routes_and_injects_captcha_repo() -> None:
    body = {
        "task_type": "CHECK_TIMEOUT",
        "chat_id": -1001,
        "user_id": 42,
        "join_message_id": 1,
        "verification_message_id": 2,
    }
    captcha = MagicMock(spec=CaptchaRepository)
    bot = MagicMock()
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=True),
        patch("services.sqs_task_router.process_timeout_task") as mock_pt,
    ):
        process_sqs_event({"Records": [_record(body)]}, bot, captcha)
    mock_pt.assert_called_once()
    passed = mock_pt.call_args[0][1]
    assert passed["_captcha_repo"] is captcha


def test_process_explain_routes() -> None:
    body = {
        "task_type": "PROCESS_EXPLAIN",
        "chat_id": -1001,
        "update_id": 99,
        "reply_to_message_id": 3,
        "term": "k8s",
        "lang": "kk",
        "style": "normal",
    }
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=True),
        patch("services.sqs_task_router.process_explain_task") as mock_pe,
    ):
        process_sqs_event({"Records": [_record(body)]}, MagicMock(), MagicMock())
    mock_pe.assert_called_once()


def test_spam_check_routes() -> None:
    body = {
        "task_type": "SPAM_CHECK",
        "chat_id": -1001,
        "user_id": 7,
        "message_id": 8,
        "text": "hello",
        "triggered_rules": [],
    }
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=True),
        patch("services.sqs_task_router.process_spam_check_task") as mock_ps,
    ):
        process_sqs_event({"Records": [_record(body)]}, MagicMock(), MagicMock())
    mock_ps.assert_called_once()


def test_non_whitelisted_chat_skips_handlers() -> None:
    body = {
        "task_type": "SPAM_CHECK",
        "chat_id": 999999999,
        "user_id": 1,
        "message_id": 1,
        "text": "x",
        "triggered_rules": [],
    }
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=False),
        patch("services.sqs_task_router.process_spam_check_task") as mock_ps,
    ):
        process_sqs_event({"Records": [_record(body)]}, MagicMock(), MagicMock())
    mock_ps.assert_not_called()


def test_handler_failure_reraises_for_sqs_retry() -> None:
    body = {
        "task_type": "PROCESS_EXPLAIN",
        "chat_id": -1001,
        "update_id": 1,
        "reply_to_message_id": 1,
        "term": "x",
        "lang": "kk",
        "style": "normal",
    }
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=True),
        patch(
            "services.sqs_task_router.process_explain_task",
            side_effect=RuntimeError("boom"),
        ),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            process_sqs_event({"Records": [_record(body)]}, MagicMock(), MagicMock())
