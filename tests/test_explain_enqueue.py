"""Enqueue failure releases DynamoDB reservation so the user can retry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.handlers import wtf as wtf_mod


@patch("services.handlers.wtf._get_task_repo")
@patch("services.handlers.wtf._get_gemini")
@patch("services.handlers.wtf._get_fallback")
def test_sqs_send_failure_releases_reservation(
    _mock_fb: MagicMock,
    _mock_g: MagicMock,
    mock_get_repo: MagicMock,
) -> None:
    task_repo = MagicMock()
    task_repo.try_reserve_update.return_value = True
    mock_get_repo.return_value = task_repo

    sqs = MagicMock()
    sqs.send_explain_task.side_effect = RuntimeError("sqs down")

    ctx = MagicMock()
    ctx.text = "/wtf testterm"
    ctx.chat_id = 1
    ctx.message_id = 2
    ctx.update_id = 424242
    ctx.sqs_repo = sqs
    ctx.message = {}
    ctx.reply = MagicMock()

    with (
        patch("services.handlers.wtf.get_chat_lang", return_value="kk"),
        patch("services.handlers.wtf._react_processing"),
        patch("services.handlers.wtf._send_typing_once"),
    ):
        wtf_mod.handle_wtf(ctx)

    task_repo.try_reserve_update.assert_called_once_with(424242)
    task_repo.release_reservation.assert_called_once_with(424242)
    assert not task_repo.mark_enqueued.called
    ctx.reply.assert_called_once()
