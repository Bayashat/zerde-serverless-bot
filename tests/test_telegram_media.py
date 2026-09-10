import pytest
from services.telegram_media import (
    MediaReference,
    MediaTooLargeError,
    agent_reply_media_metadata,
    detect_media_reference,
    detect_media_references,
    media_reference_context,
    prepare_media_collection_for_gemini,
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


def test_detect_media_reference_detects_video_with_album_metadata():
    ref = detect_media_reference(
        {
            "message_id": 90,
            "media_group_id": "album-1",
            "video": {
                "file_id": "video-id",
                "file_unique_id": "video-u",
                "mime_type": "video/mp4",
                "file_size": 1234,
                "duration": 18,
            },
        }
    )

    assert ref is not None
    assert ref.media_type == "video"
    assert ref.mime_type == "video/mp4"
    assert ref.duration_seconds == 18
    assert ref.media_group_id == "album-1"


def test_detect_media_references_expands_reply_album_and_keeps_target_first():
    refs = detect_media_references(
        {
            "reply_to_message": {
                "message_id": 90,
                "media_group_id": "album-1",
                "video": {"file_id": "video-id", "file_unique_id": "video-u", "mime_type": "video/mp4"},
            }
        },
        media_group_loader=lambda group_id: [
            {
                "media_type": "video",
                "file_id": "video-id",
                "file_unique_id": "video-u",
                "source_message_id": 90,
                "media_group_id": group_id,
            },
            {
                "media_type": "photo",
                "file_id": "photo-id",
                "file_unique_id": "photo-u",
                "source_message_id": 91,
                "media_group_id": group_id,
            },
        ],
    )

    assert [ref.media_type for ref in refs] == ["video", "photo"]
    assert [ref.source_message_id for ref in refs] == [90, 91]


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


def test_media_reference_context_preserves_caption_words_that_resemble_log_secrets():
    caption = "Please inspect this diagram: monkey=banana, key=middle C, token=bear."
    ref = detect_media_reference({"photo": [{"file_id": "photo-id"}], "caption": caption})

    context = media_reference_context(ref)

    assert f"- caption: {caption}" in context


@pytest.mark.parametrize("caption_length", [499, 500, 501])
def test_media_reference_context_keeps_caption_normalization_and_size_limit(caption_length):
    normalized_caption = "a b" + "c" * (caption_length - 3)
    ref = MediaReference(
        media_type="photo",
        file_id="photo-id",
        caption="  a\nb" + "c" * (caption_length - 3) + "  ",
    )

    context = media_reference_context(ref)

    expected_caption = normalized_caption[:500]
    if caption_length > 500:
        expected_caption += f"…(truncated,{caption_length} chars)"
    assert f"- caption: {expected_caption}" in context.splitlines()


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


def test_prepare_media_collection_skips_oversized_video_and_keeps_photo(monkeypatch):
    monkeypatch.setattr("services.telegram_media.MULTIMODAL_INLINE_MAX_BYTES", 5)
    refs = detect_media_references(
        {
            "reply_to_message": {
                "message_id": 90,
                "media_group_id": "album-1",
                "video": {
                    "file_id": "video-id",
                    "file_unique_id": "video-u",
                    "mime_type": "video/mp4",
                    "file_size": 10,
                },
            }
        },
        media_group_loader=lambda group_id: [
            {
                "media_type": "photo",
                "file_id": "photo-id",
                "file_unique_id": "photo-u",
                "file_size": 4,
                "mime_type": "image/jpeg",
                "source_message_id": 91,
                "media_group_id": group_id,
            }
        ],
    )

    prepared = prepare_media_collection_for_gemini(_media_bot(b"test"), refs)

    assert prepared.prepared_count == 1
    assert prepared.skipped_count == 1
    assert prepared.skipped_reasons == {"too_large": 1}
    assert prepared.media_parts == [{"inline_data": {"mime_type": "image/jpeg", "data": "dGVzdA=="}}]
    assert prepared.agent_reply_metadata["media_type"] == "photo"
    assert "Do not claim details from skipped items" in prepared.media_context


def test_prepare_media_collection_builds_multiple_parts_and_compact_group_metadata(monkeypatch):
    monkeypatch.setattr("services.telegram_media.MULTIMODAL_INLINE_MAX_BYTES", 20)
    refs = detect_media_references(
        {
            "reply_to_message": {
                "message_id": 90,
                "media_group_id": "album-1",
                "video": {
                    "file_id": "video-id",
                    "file_unique_id": "video-u",
                    "mime_type": "video/mp4",
                    "file_size": 4,
                },
            }
        },
        media_group_loader=lambda group_id: [
            {
                "media_type": "photo",
                "file_id": "photo-id",
                "file_unique_id": "photo-u",
                "file_size": 4,
                "mime_type": "image/jpeg",
                "source_message_id": 91,
                "media_group_id": group_id,
            }
        ],
    )

    prepared = prepare_media_collection_for_gemini(_media_bot(b"test"), refs)

    assert prepared.prepared_count == 2
    assert len(prepared.media_parts) == 2
    assert prepared.agent_reply_metadata["media_type"] == "media_group"
    assert prepared.agent_reply_metadata["media_types"] == "video,photo"
    assert prepared.agent_reply_metadata["media_item_count"] == 2
    assert prepared.agent_reply_metadata["media_group_id"] == "album-1"


def _media_bot(data: bytes):
    class Bot:
        def get_file(self, file_id):
            return {"file_path": f"photos/{file_id}.jpg", "file_size": len(data)}

        def download_file(self, file_path, *, max_bytes):
            assert file_path.startswith("photos/") or file_path.endswith(".jpg")
            assert len(data) <= max_bytes
            return data

    return Bot()
