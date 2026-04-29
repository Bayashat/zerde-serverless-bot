"""Multimodal /explain helpers and PROCESS_EXPLAIN media branch."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.explain_multimodal import document_auto_allowed, extract_reply_media
from services.handlers import wtf as wtf_mod


def test_extract_reply_media_voice() -> None:
    msg = {"voice": {"file_id": "abc", "mime_type": "audio/ogg"}}
    assert extract_reply_media(msg) == ("voice", "abc", "audio/ogg")


def test_extract_reply_media_voice_default_mime() -> None:
    msg = {"voice": {"file_id": "x"}}
    assert extract_reply_media(msg) == ("voice", "x", "audio/ogg")


def test_extract_reply_media_photo_largest() -> None:
    msg = {
        "photo": [
            {"file_id": "s", "width": 60, "height": 60, "file_size": 100},
            {"file_id": "l", "width": 200, "height": 200, "file_size": 5000},
        ]
    }
    kind, fid, mime = extract_reply_media(msg)
    assert kind == "photo"
    assert fid == "l"
    assert mime == "image/jpeg"


def test_document_auto_allowed_pdf() -> None:
    ok, reason = document_auto_allowed({"mime_type": "application/pdf", "file_size": 100})
    assert ok is True
    assert reason is None


def test_document_auto_allowed_rejects_zip() -> None:
    ok, reason = document_auto_allowed({"mime_type": "application/zip", "file_size": 10})
    assert ok is False
    assert reason == "explain_document_mime_not_supported"


@patch("services.handlers.wtf._get_task_repo")
@patch("services.handlers.wtf._execute_multimodal_explain_and_reply")
def test_process_explain_task_media_skips_empty_term_check(
    mock_exec: MagicMock,
    mock_get_repo: MagicMock,
) -> None:
    repo = MagicMock()
    mock_get_repo.return_value = repo
    bot = MagicMock()
    body: dict = {
        "update_id": 1,
        "chat_id": -100,
        "reply_to_message_id": 9,
        "term": "",
        "lang": "en",
        "style": "normal",
        "file_id": "AgAD",
        "mime_type": "image/jpeg",
        "media_kind": "photo",
        "task_source": "explain_reply",
    }
    wtf_mod.process_explain_task(bot, body)
    mock_exec.assert_called_once()
    repo.mark_completed.assert_called_once_with(1)
