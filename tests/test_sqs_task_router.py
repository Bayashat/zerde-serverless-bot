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


def test_process_proactive_candidate_routes() -> None:
    body = {
        "task_type": "PROCESS_PROACTIVE_CANDIDATE",
        "chat_id": -1001,
        "trigger_message_id": 3,
        "trigger_user_id": 42,
        "user_text": "does anyone know how k8s pricing works?",
        "lang": "en",
    }
    memory_repo = MagicMock()
    bot = MagicMock()
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=True),
        patch("services.sqs_task_router.process_proactive_candidate_task") as mock_pc,
    ):
        process_sqs_event({"Records": [_record(body)]}, bot, MagicMock(), memory_repo)
    mock_pc.assert_called_once_with(repo=memory_repo, bot=bot, body=body)


def test_process_ambient_reaction_routes() -> None:
    body = {
        "task_type": "PROCESS_AMBIENT_REACTION",
        "chat_id": -1001,
        "message_id": 3,
        "user_id": 42,
        "text": "This OpenSearch debugging note is useful",
        "lang": "en",
    }
    memory_repo = MagicMock()
    bot = MagicMock()
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=True),
        patch("services.sqs_task_router.process_ambient_reaction_task") as mock_ar,
    ):
        process_sqs_event({"Records": [_record(body)]}, bot, MagicMock(), memory_repo)
    mock_ar.assert_called_once_with(repo=memory_repo, bot=bot, body=body)


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
    mock_ps.assert_called_once_with(bot, body, captcha_repo=captcha, memory_repo=memory_repo)


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


def test_daily_summary_task_does_not_share_contest_recovery_failure_domain() -> None:
    body = {
        "task_type": "PROCESS_DAILY_GROUP_SUMMARIES",
        "chat_ids": [-1001],
    }
    contest_repo = MagicMock()
    sqs_repo = MagicMock()
    memory_repo = MagicMock()
    with patch("services.sqs_task_router.process_daily_group_summaries_task") as summary:
        process_sqs_event(
            {"Records": [_record(body)]},
            MagicMock(),
            MagicMock(),
            memory_repo,
            contest_repo=contest_repo,
            sqs_repo=sqs_repo,
        )

    sqs_repo.send_contest_ttl_recovery_task.assert_not_called()
    summary.assert_called_once_with(body, repo=memory_repo)


def test_process_contest_ttl_recovery_routes_with_existing_dependencies() -> None:
    body = {
        "task_type": "PROCESS_CONTEST_TTL_RECOVERY",
        "start_key": {
            "pk": "CONTEST_TTL_OUTBOX",
            "sk": "CHAT#-1001#ROOT#0000000000011",
        },
    }
    contest_repo = MagicMock()
    sqs_repo = MagicMock()
    with patch("services.sqs_task_router.process_contest_ttl_recovery_task") as recovery:
        process_sqs_event(
            {"Records": [_record(body)]},
            MagicMock(),
            MagicMock(),
            contest_repo=contest_repo,
            sqs_repo=sqs_repo,
        )

    recovery.assert_called_once_with(body, repo=contest_repo, sqs_repo=sqs_repo)


def test_contest_ttl_recovery_failure_bubbles_for_independent_queue_retry() -> None:
    body = {"task_type": "PROCESS_CONTEST_TTL_RECOVERY"}
    with (
        patch(
            "services.sqs_task_router.process_contest_ttl_recovery_task",
            side_effect=RuntimeError("recovery boom"),
        ),
        pytest.raises(RuntimeError, match="recovery boom"),
    ):
        process_sqs_event(
            {"Records": [_record(body)]},
            MagicMock(),
            MagicMock(),
            contest_repo=MagicMock(),
            sqs_repo=MagicMock(),
        )


def test_process_contest_ttl_sweep_routes_with_existing_dependencies() -> None:
    body = {
        "task_type": "PROCESS_CONTEST_TTL_SWEEP",
        "chat_id": -1001,
        "root_message_id": 11,
    }
    contest_repo = MagicMock()
    sqs_repo = MagicMock()
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=True),
        patch("services.sqs_task_router.process_contest_ttl_sweep_task") as sweep,
    ):
        process_sqs_event(
            {"Records": [_record(body)]},
            MagicMock(),
            MagicMock(),
            contest_repo=contest_repo,
            sqs_repo=sqs_repo,
        )
    sweep.assert_called_once_with(body, repo=contest_repo, sqs_repo=sqs_repo)


def test_contest_ttl_sweep_failure_bubbles_for_queue_retry() -> None:
    body = {
        "task_type": "PROCESS_CONTEST_TTL_SWEEP",
        "chat_id": -1001,
        "root_message_id": 11,
    }
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=True),
        patch(
            "services.sqs_task_router.process_contest_ttl_sweep_task",
            side_effect=RuntimeError("sweep boom"),
        ),
        pytest.raises(RuntimeError, match="sweep boom"),
    ):
        process_sqs_event(
            {"Records": [_record(body)]},
            MagicMock(),
            MagicMock(),
            contest_repo=MagicMock(),
            sqs_repo=MagicMock(),
        )


def test_contest_ttl_cleanup_survives_chat_configuration_removal() -> None:
    body = {
        "task_type": "PROCESS_CONTEST_TTL_SWEEP",
        "chat_id": -1001,
        "root_message_id": 11,
    }
    contest_repo = MagicMock()
    sqs_repo = MagicMock()
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=False),
        patch("services.sqs_task_router.process_contest_ttl_sweep_task") as sweep,
    ):
        process_sqs_event(
            {"Records": [_record(body)]},
            MagicMock(),
            MagicMock(),
            contest_repo=contest_repo,
            sqs_repo=sqs_repo,
        )
    sweep.assert_called_once_with(body, repo=contest_repo, sqs_repo=sqs_repo)


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
