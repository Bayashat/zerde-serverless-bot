"""Tests for SQS task routing and failure propagation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from services.repositories.captcha import CaptchaRepository
from services.sqs_task_router import process_sqs_event, process_vector_sqs_event


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


def test_process_group_ask_routes() -> None:
    body = {
        "task_type": "PROCESS_GROUP_ASK",
        "chat_id": -1001,
        "update_id": 99,
        "reply_to_message_id": 3,
        "user_text": "what is k8s?",
        "lang": "kk",
    }
    memory_repo = MagicMock()
    bot = MagicMock()
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=True),
        patch("services.sqs_task_router.process_group_ask_task") as mock_pa,
    ):
        process_sqs_event({"Records": [_record(body)]}, bot, MagicMock(), memory_repo)
    mock_pa.assert_called_once_with(repo=memory_repo, bot=bot, body=body)


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
        captcha = MagicMock()
        bot = MagicMock()
        process_sqs_event({"Records": [_record(body)]}, bot, captcha)
    mock_ps.assert_called_once_with(bot, body, captcha_repo=captcha)


def test_process_group_memory_routes() -> None:
    body = {
        "task_type": "PROCESS_GROUP_MEMORY",
        "chat_id": -1001,
        "user_id": 7,
        "message_id": 8,
        "display_name": "Ada",
        "text": "Tomorrow we deploy the memory processor",
    }
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=True),
        patch("services.sqs_task_router.process_group_memory_task") as mock_pm,
    ):
        process_sqs_event({"Records": [_record(body)]}, MagicMock(), MagicMock())
    mock_pm.assert_called_once_with(body, repo=None)


def test_process_daily_group_summaries_routes() -> None:
    body = {
        "task_type": "PROCESS_DAILY_GROUP_SUMMARIES",
        "chat_ids": [-1001, -1002],
        "summary_date": "2026-06-10",
    }
    with patch("services.sqs_task_router.process_daily_group_summaries_task") as mock_pd:
        process_sqs_event({"Records": [_record(body)]}, MagicMock(), MagicMock())
    mock_pd.assert_called_once_with(body, repo=None)


def test_process_vector_memory_routes() -> None:
    body = {
        "task_type": "PROCESS_VECTOR_MEMORY",
        "chat_id": -1001,
        "source_sk": "EVENT#1#2",
    }
    memory_repo = MagicMock()
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=True),
        patch("services.sqs_task_router.process_vector_memory_task") as mock_pv,
    ):
        process_vector_sqs_event({"Records": [_record(body)]}, memory_repo)
    mock_pv.assert_called_once_with(body, repo=memory_repo)


def test_process_vector_memory_backfill_routes() -> None:
    body = {
        "task_type": "PROCESS_VECTOR_MEMORY_BACKFILL",
        "chat_id": -1001,
        "limit": 25,
    }
    memory_repo = MagicMock()
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=True),
        patch("services.sqs_task_router.process_vector_memory_backfill_task") as mock_pb,
    ):
        process_vector_sqs_event({"Records": [_record(body)]}, memory_repo)
    mock_pb.assert_called_once_with(body, repo=memory_repo)


def test_main_sqs_router_ignores_vector_tasks() -> None:
    body = {
        "task_type": "PROCESS_VECTOR_MEMORY",
        "chat_id": -1001,
        "source_sk": "EVENT#1#2",
    }
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=True),
        patch("services.sqs_task_router.process_vector_memory_task") as mock_pv,
    ):
        process_sqs_event({"Records": [_record(body)]}, MagicMock(), MagicMock(), MagicMock())
    mock_pv.assert_not_called()


def test_vector_sqs_router_ignores_main_tasks() -> None:
    body = {
        "task_type": "PROCESS_GROUP_ASK",
        "chat_id": -1001,
        "update_id": 99,
        "reply_to_message_id": 3,
        "user_text": "what is k8s?",
        "lang": "kk",
    }
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=True),
        patch("services.sqs_task_router.process_group_ask_task") as mock_pa,
    ):
        process_vector_sqs_event({"Records": [_record(body)]}, MagicMock())
    mock_pa.assert_not_called()


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
        "task_type": "PROCESS_GROUP_ASK",
        "chat_id": -1001,
        "update_id": 1,
        "reply_to_message_id": 1,
        "user_text": "x",
        "lang": "kk",
    }
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=True),
        patch(
            "services.sqs_task_router.process_group_ask_task",
            side_effect=RuntimeError("boom"),
        ),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            process_sqs_event({"Records": [_record(body)]}, MagicMock(), MagicMock(), MagicMock())


def test_vector_handler_failure_reraises_for_sqs_retry() -> None:
    body = {
        "task_type": "PROCESS_VECTOR_MEMORY",
        "chat_id": -1001,
        "source_sk": "EVENT#1#2",
    }
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=True),
        patch(
            "services.sqs_task_router.process_vector_memory_task",
            side_effect=RuntimeError("vector boom"),
        ),
    ):
        with pytest.raises(RuntimeError, match="vector boom"):
            process_vector_sqs_event({"Records": [_record(body)]}, MagicMock())
