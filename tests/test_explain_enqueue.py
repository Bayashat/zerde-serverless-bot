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


@patch("services.handlers.wtf.get_deepseek_api_key", return_value="sk")
@patch("services.handlers.wtf.get_gemini_api_key", return_value="gk")
@patch("services.handlers.wtf._get_task_repo")
@patch("services.handlers.wtf._get_gemini")
@patch("services.handlers.wtf._get_fallback")
def test_wtf_reply_to_photo_uses_caption_as_term(
    _mock_fallback: MagicMock,
    _mock_gemini: MagicMock,
    mock_get_repo: MagicMock,
    _mock_gemini_key: MagicMock,
    _mock_deepseek_key: MagicMock,
) -> None:
    """Channel auto-forwards often have caption instead of body text on photo posts."""
    task_repo = MagicMock()
    task_repo.try_reserve_update.return_value = True
    mock_get_repo.return_value = task_repo

    sqs = MagicMock()
    ctx = MagicMock()
    ctx.text = "/wtf@zerde_kz_bot"
    ctx.reply_to_message = {
        "message_id": 36737,
        "caption": "Ну блять, тест",
        "photo": [{"file_id": "AgAC...", "width": 1, "height": 1}],
    }
    ctx.chat_id = 1
    ctx.message_id = 2
    ctx.update_id = 900001
    ctx.sqs_repo = sqs
    ctx.message = {}
    ctx.reply = MagicMock()

    with (
        patch("services.handlers.wtf.get_chat_lang", return_value="kk"),
        patch("services.handlers.wtf._react_processing"),
        patch("services.handlers.wtf._send_typing_once"),
    ):
        wtf_mod.handle_wtf(ctx)

    sqs.send_explain_task.assert_called_once()
    kwargs = sqs.send_explain_task.call_args.kwargs
    assert kwargs["term"] == "Ну блять, тест"
    task_repo.mark_enqueued.assert_called_once_with(900001)
