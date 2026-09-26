"""Tests for SQS task routing and failure propagation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from services.memory_cutover import EXPLICIT_CONTEXT_VERSION
from services.repositories.captcha import CaptchaRepository
from services.sqs_task_router import process_sqs_event, process_vector_sqs_event


def _record(body: dict) -> dict:
    return {"messageId": "mid-1", "body": json.dumps(body)}


@pytest.mark.parametrize("task", ["PROCESS_CONTEST_TTL_SWEEP", "PROCESS_CONTEST_TTL_RECOVERY"])
@pytest.mark.parametrize("router", ["main", "vector"])
@pytest.mark.parametrize(
    "chat_fields", [{}, {"chat_id": None}, {"chat_id": "obsolete-invalid-chat"}, {"chat_id": -1001}]
)
def test_retired_contest_tasks_ack_without_any_dependency_or_chat_lookup(task, router, chat_fields):
    body = {
        "task_type": task,
        "root_message_id": 11,
        "start_key": {"pk": "CONTEST_TTL_OUTBOX", "sk": "old"},
        **chat_fields,
    }
    dependencies = [MagicMock() for _ in range(6)]
    bot, captcha, memory, sqs, ingestion, quiz = dependencies
    with patch("services.sqs_task_router.is_configured_group_chat") as configured:
        if router == "main":
            process_sqs_event(
                {"Records": [_record(body)]},
                bot,
                captcha,
                memory,
                sqs_repo=sqs,
                memory_ingestion=ingestion,
                quiz_repo=quiz,
            )
        else:
            process_vector_sqs_event({"Records": [_record(body)]}, memory)
    configured.assert_not_called()
    assert all(not dependency.mock_calls for dependency in dependencies)


def test_retired_contest_task_does_not_skip_other_records_in_mixed_batch():
    records = [
        _record({"task_type": "PROCESS_CONTEST_TTL_RECOVERY"}),
        _record({"task_type": "SPAM_CHECK", "chat_id": -1001}),
    ]
    bot, captcha = MagicMock(), MagicMock()
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=True),
        patch("services.sqs_task_router.process_spam_check_task", return_value="rejected") as spam,
    ):
        process_sqs_event({"Records": records}, bot, captcha)
    spam.assert_called_once_with(bot, {"task_type": "SPAM_CHECK", "chat_id": -1001}, captcha_repo=captcha)


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
        "context_version": EXPLICIT_CONTEXT_VERSION,
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
        memory_repo = MagicMock()
        process_sqs_event({"Records": [_record(body)]}, bot, captcha, memory_repo)
    mock_ps.assert_called_once_with(bot, body, captcha_repo=captcha)


def test_vector_sqs_router_ignores_main_tasks() -> None:
    body = {
        "task_type": "PROCESS_GROUP_ASK",
        "context_version": EXPLICIT_CONTEXT_VERSION,
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
        "context_version": EXPLICIT_CONTEXT_VERSION,
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


@pytest.mark.parametrize(
    "task_type",
    [
        "PROCESS_PROACTIVE_CANDIDATE",
        "PROCESS_AMBIENT_REACTION",
        "PROCESS_GROUP_MEMORY",
        "PROCESS_DAILY_GROUP_SUMMARIES",
        "PROCESS_VECTOR_MEMORY",
        "PROCESS_VECTOR_MEMORY_BACKFILL",
    ],
)
@pytest.mark.parametrize("router", ["main", "vector"])
def test_retired_memory_and_social_tasks_need_no_modules_or_dependencies(task_type, router):
    dependencies = [MagicMock() for _ in range(4)]
    bot, captcha, memory, sqs = dependencies
    body = {"task_type": task_type, "chat_id": "invalid-retired-chat", "text": "old payload"}
    with patch("services.sqs_task_router.is_configured_group_chat", side_effect=AssertionError("no chat lookup")):
        if router == "main":
            process_sqs_event({"Records": [_record(body)]}, bot, captcha, memory, sqs_repo=sqs)
        else:
            process_vector_sqs_event({"Records": [_record(body)]}, memory)
    assert all(not dependency.mock_calls for dependency in dependencies)
