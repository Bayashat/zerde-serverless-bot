"""SQS PROCESS_EXPLAIN idempotency: no duplicate Gemini/Telegram on retry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.handlers import wtf as wtf_mod


@patch("services.handlers.wtf._get_task_repo")
@patch("services.handlers.wtf._execute_explain_and_reply")
def test_process_explain_skips_when_already_completed(mock_exec: MagicMock, mock_get_repo: MagicMock) -> None:
    repo = MagicMock()
    repo.get_status.return_value = "completed"
    mock_get_repo.return_value = repo

    body = {
        "update_id": 99,
        "chat_id": -100,
        "reply_to_message_id": 1,
        "term": "docker",
        "lang": "en",
        "style": "normal",
    }
    wtf_mod.process_explain_task(MagicMock(), body)

    mock_exec.assert_not_called()
    repo.try_claim_processing.assert_not_called()


@patch("services.handlers.wtf._get_task_repo")
@patch("services.handlers.wtf._execute_explain_and_reply")
def test_process_explain_reconciles_sent_without_resending(mock_exec: MagicMock, mock_get_repo: MagicMock) -> None:
    repo = MagicMock()
    repo.get_status.return_value = "sent"
    mock_get_repo.return_value = repo

    body = {
        "update_id": 100,
        "chat_id": -100,
        "reply_to_message_id": 1,
        "term": "docker",
        "lang": "en",
        "style": "normal",
    }
    wtf_mod.process_explain_task(MagicMock(), body)

    mock_exec.assert_not_called()
    repo.mark_completed.assert_called_once_with(100)
    repo.mark_reply_sent.assert_not_called()


@patch("services.handlers.wtf._get_task_repo")
@patch("services.handlers.wtf._execute_explain_and_reply")
def test_process_explain_marks_sent_then_completed_on_success(mock_exec: MagicMock, mock_get_repo: MagicMock) -> None:
    repo = MagicMock()
    repo.get_status.return_value = "enqueued"
    repo.try_claim_processing.return_value = True
    mock_get_repo.return_value = repo

    body = {
        "update_id": 101,
        "chat_id": -100,
        "reply_to_message_id": 1,
        "term": "kubernetes",
        "lang": "en",
        "style": "angry",
    }
    wtf_mod.process_explain_task(MagicMock(), body)

    mock_exec.assert_called_once()
    repo.try_claim_processing.assert_called_once_with(101)
    repo.mark_reply_sent.assert_called_once_with(101)
    repo.mark_completed.assert_called_once_with(101)


@patch("services.handlers.wtf._get_task_repo")
@patch("services.handlers.wtf._execute_explain_and_reply")
def test_process_explain_releases_claim_on_failure(mock_exec: MagicMock, mock_get_repo: MagicMock) -> None:
    repo = MagicMock()
    repo.get_status.return_value = "enqueued"
    repo.try_claim_processing.return_value = True
    mock_get_repo.return_value = repo
    mock_exec.side_effect = RuntimeError("gemini down")

    body = {
        "update_id": 102,
        "chat_id": -100,
        "reply_to_message_id": 1,
        "term": "lambda",
        "lang": "en",
        "style": "normal",
    }

    try:
        wtf_mod.process_explain_task(MagicMock(), body)
    except RuntimeError:
        pass

    repo.release_processing.assert_called_once_with(102)
    repo.mark_reply_sent.assert_not_called()
    repo.mark_completed.assert_not_called()
