"""PROCESS_EXPLAIN worker idempotency on SQS redelivery."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.handlers import wtf as wtf_mod


@patch("services.handlers.wtf._get_task_repo")
@patch("services.handlers.wtf._execute_explain_and_reply")
def test_process_explain_task_skips_when_already_completed(
    mock_exec: MagicMock,
    mock_get_repo: MagicMock,
) -> None:
    repo = MagicMock()
    repo.is_completed.return_value = True
    mock_get_repo.return_value = repo

    wtf_mod.process_explain_task(
        MagicMock(),
        {
            "update_id": 99,
            "chat_id": -100,
            "reply_to_message_id": 1,
            "term": "lambda",
            "lang": "en",
            "style": "normal",
        },
    )

    mock_exec.assert_not_called()
    repo.mark_completed.assert_not_called()
