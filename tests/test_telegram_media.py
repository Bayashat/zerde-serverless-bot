import pytest
from services.telegram_media import (
    MediaTooLargeError,
    agent_reply_media_metadata,
    detect_media_reference,
    prepare_media_for_gemini,
)


def test_detect_media_reference_selects_largest_photo():
    ref = detect_media_reference(
        {
            "reply_to_message": {
                "message_id": 8,
                "from": {"id": 42, "first_name": "Ada", "username": "ada"},
                "photo": [
                    {"file_id": "small", "file_unique_id": "u-small", "width": 90, "height": 90, "file_size": 1000},
                    {
                        "file_id": "large",
                        "file_unique_id": "u-large",
                        "width": 1280,
                        "height": 720,
                        "file_size": 50_000,
                    },
                ],
            },
            "text": "/ask what is this?",
        }
    )

    assert ref is not None
    assert ref.media_type == "photo"
    assert ref.file_id == "large"
    assert ref.file_unique_id == "u-large"
    assert ref.source_message_id == 8
    assert ref.source_username == "ada"


def test_detect_media_reference_detects_voice_and_audio():
    voice_ref = detect_media_reference({"voice": {"file_id": "voice-id", "mime_type": "audio/ogg", "file_size": 123}})
    audio_ref = detect_media_reference(
        {"audio": {"file_id": "audio-id", "mime_type": "audio/mpeg", "file_name": "clip.mp3"}}
    )

    assert voice_ref is not None
    assert voice_ref.media_type == "voice"
    assert voice_ref.mime_type == "audio/ogg"
    assert audio_ref is not None
    assert audio_ref.media_type == "audio"
    assert audio_ref.file_name == "clip.mp3"


def test_detect_media_reference_detects_pdf_and_text_code_documents():
    pdf_ref = detect_media_reference(
        {"document": {"file_id": "pdf-id", "file_name": "spec.pdf", "mime_type": "application/pdf"}}
    )
    text_ref = detect_media_reference(
        {"document": {"file_id": "log-id", "file_name": "deploy.log", "mime_type": "text/plain"}}
    )
    code_ref = detect_media_reference({"document": {"file_id": "code-id", "file_name": "handler.py"}})

    assert pdf_ref is not None
    assert pdf_ref.media_type == "pdf"
    assert text_ref is not None
    assert text_ref.media_type == "text_file"
    assert code_ref is not None
    assert code_ref.media_type == "code_file"


def test_detect_media_reference_rejects_unsupported_document():
    ref = detect_media_reference(
        {"document": {"file_id": "archive-id", "file_name": "dump.zip", "mime_type": "application/zip"}}
    )

    assert ref is None


def test_prepare_media_for_gemini_builds_bounded_text_part(monkeypatch):
    monkeypatch.setattr("services.telegram_media.MULTIMODAL_TEXT_FILE_MAX_CHARS", 12)
    ref = detect_media_reference(
        {"document": {"file_id": "log-id", "file_name": "deploy.log", "mime_type": "text/plain"}}
    )
    bot = _media_bot(b"line one\nline two\nline three")

    prepared = prepare_media_for_gemini(bot, ref)

    assert prepared.media_parts == [
        {
            "text": (
                "Attached text file content (deploy.log):\n"
                "line one\nlin\nThe file content is truncated to the configured character limit."
            )
        }
    ]
    assert "bounded_text" in prepared.media_context
    assert prepared.content_mode == "bounded_text"
    assert prepared.downloaded_bytes == len(b"line one\nline two\nline three")
    assert prepared.agent_reply_metadata["file_name"] == "deploy.log"
    assert "file_id" not in agent_reply_media_metadata(ref)


def test_prepare_media_for_gemini_builds_inline_data(monkeypatch):
    monkeypatch.setattr("services.telegram_media.MULTIMODAL_INLINE_MAX_BYTES", 20)
    ref = detect_media_reference({"photo": [{"file_id": "photo-id", "file_unique_id": "u1", "file_size": 4}]})
    bot = _media_bot(b"test")

    prepared = prepare_media_for_gemini(bot, ref)

    assert prepared.media_parts == [{"inline_data": {"mime_type": "image/jpeg", "data": "dGVzdA=="}}]
    assert "inline_data" in prepared.media_context
    assert prepared.content_mode == "inline_data"
    assert prepared.downloaded_bytes == 4
    assert prepared.agent_reply_metadata["file_unique_id"] == "u1"
    assert "file_id" not in prepared.agent_reply_metadata


def test_prepare_media_for_gemini_enforces_inline_limit(monkeypatch):
    monkeypatch.setattr("services.telegram_media.MULTIMODAL_INLINE_MAX_BYTES", 3)
    ref = detect_media_reference({"photo": [{"file_id": "photo-id", "file_size": 4}]})
    bot = _media_bot(b"test")

    with pytest.raises(MediaTooLargeError):
        prepare_media_for_gemini(bot, ref)


def _media_bot(data: bytes):
    class Bot:
        def get_file(self, file_id):
            return {"file_path": f"photos/{file_id}.jpg", "file_size": len(data)}

        def download_file(self, file_path, *, max_bytes):
            assert file_path.startswith("photos/") or file_path.endswith(".jpg")
            assert len(data) <= max_bytes
            return data

    return Bot()
