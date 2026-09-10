"""Telegram media helpers for explicit multimodal /ask requests."""

from __future__ import annotations

import base64
import os
from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping, Sequence

from core.config import (
    MULTIMODAL_ENABLED,
    MULTIMODAL_INLINE_MAX_BYTES,
    MULTIMODAL_MAX_DOWNLOAD_BYTES,
    MULTIMODAL_TEXT_FILE_MAX_CHARS,
)
from core.logger import LoggerAdapter, get_logger
from services.telegram import TelegramAPIError, TelegramFileTooLargeError
from services.telegram_actor import actor_display_name, actor_sender_type, actor_username, message_actor
from zerde_common.logging_utils import truncate_log_text

logger = LoggerAdapter(get_logger(__name__), {})

IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
AUDIO_MIME_TYPES = {
    "audio/ogg",
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
}
VIDEO_MIME_TYPES = {
    "video/mp4",
    "video/mpeg",
    "video/mov",
    "video/quicktime",
    "video/avi",
    "video/x-msvideo",
    "video/x-flv",
    "video/mpg",
    "video/webm",
    "video/wmv",
    "video/x-ms-wmv",
    "video/3gpp",
}
PDF_MIME_TYPES = {"application/pdf"}
TEXT_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "application/json",
    "application/x-yaml",
    "application/yaml",
    "text/yaml",
    "text/x-yaml",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_EXTENSIONS = {".ogg", ".oga", ".mp3", ".mpeg", ".wav", ".m4a", ".mp4"}
TEXT_EXTENSIONS = {".txt", ".md", ".log", ".json", ".yaml", ".yml"}
CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".sql",
    ".sh",
    ".bash",
    ".zsh",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".xml",
    ".html",
    ".css",
}
SUPPORTED_MEDIA_TYPES = {
    "photo",
    "image_document",
    "video",
    "voice",
    "audio",
    "pdf",
    "text_file",
    "code_file",
}
TEXT_MEDIA_TYPES = {"text_file", "code_file"}
MAX_MEDIA_REFS_PER_REQUEST = 4


class MediaError(Exception):
    """Base class for explicit multimodal media preparation errors."""

    retryable = False


class MediaDisabledError(MediaError):
    """Raised when multimodal handling is disabled by configuration."""


class MediaUnsupportedError(MediaError):
    """Raised when a media reference is unsupported or malformed."""


class MediaTooLargeError(MediaError):
    """Raised when media exceeds configured download or inline limits."""


class MediaUnavailableError(MediaError):
    """Raised when Telegram cannot return the media file."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message, retryable)
        self.retryable = retryable


@dataclass(frozen=True)
class MediaReference:
    """Serializable Telegram media reference for SQS payloads."""

    media_type: str
    file_id: str
    file_unique_id: str | None = None
    file_size: int | None = None
    mime_type: str | None = None
    file_name: str | None = None
    caption: str | None = None
    duration_seconds: int | None = None
    media_group_id: str | None = None
    source_message_id: int | None = None
    source_user_id: int | str | None = None
    source_username: str | None = None
    source_display_name: str | None = None
    source_sender_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a compact JSON-serializable representation."""
        return {key: value for key, value in asdict(self).items() if value not in (None, "")}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MediaReference":
        """Build a reference from a trusted SQS dictionary."""
        return cls(
            media_type=str(value.get("media_type") or ""),
            file_id=str(value.get("file_id") or ""),
            file_unique_id=_optional_str(value.get("file_unique_id")),
            file_size=_optional_int(value.get("file_size")),
            mime_type=_normalise_mime(value.get("mime_type")),
            file_name=_optional_str(value.get("file_name")),
            caption=_optional_str(value.get("caption")),
            duration_seconds=_optional_int(value.get("duration_seconds")),
            media_group_id=_optional_str(value.get("media_group_id"), limit=160),
            source_message_id=_optional_int(value.get("source_message_id")),
            source_user_id=_optional_int(value.get("source_user_id")),
            source_username=_optional_str(value.get("source_username")),
            source_display_name=_optional_str(value.get("source_display_name")),
            source_sender_type=_optional_str(value.get("source_sender_type")),
        )


@dataclass(frozen=True)
class PreparedMedia:
    """Gemini-ready media payload plus safe metadata for prompt/reply storage."""

    media_parts: list[dict[str, Any]]
    media_context: str
    agent_reply_metadata: dict[str, Any]
    downloaded_bytes: int = 0
    content_mode: str = ""


@dataclass(frozen=True)
class PreparedMediaCollection:
    """Gemini-ready result for one or more independently bounded media items."""

    media_parts: list[dict[str, Any]]
    media_context: str
    agent_reply_metadata: dict[str, Any]
    downloaded_bytes: int
    requested_count: int
    prepared_count: int
    skipped_count: int
    skipped_reasons: dict[str, int]
    content_modes: list[str]


def _optional_str(value: Any, *, limit: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit] if limit else text


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalise_mime(value: Any) -> str | None:
    text = _optional_str(value)
    return text.lower() if text else None


def _extension(file_name: str | None) -> str:
    return os.path.splitext((file_name or "").lower())[1]


def _display_name(actor: Mapping[str, Any]) -> str | None:
    first = str(actor.get("first_name") or "").strip()
    last = str(actor.get("last_name") or "").strip()
    title = str(actor.get("title") or "").strip()
    username = str(actor.get("username") or "").strip()
    full = " ".join(part for part in (first, last) if part)
    return _optional_str(full or title or (f"@{username}" if username else ""), limit=80)


def _source_fields(message: Mapping[str, Any]) -> dict[str, Any]:
    actor = message_actor(message)
    return {
        "source_message_id": _optional_int(message.get("message_id")),
        "source_user_id": actor.get("id"),
        "source_username": _optional_str(actor_username(actor), limit=160),
        "source_display_name": _optional_str(actor_display_name(actor) or _display_name(actor), limit=80),
        "source_sender_type": actor_sender_type(actor),
        "media_group_id": _optional_str(message.get("media_group_id"), limit=160),
    }


def _caption(message: Mapping[str, Any]) -> str | None:
    return _optional_str(message.get("caption"), limit=500)


def _media_ref_from_message(message: Mapping[str, Any]) -> MediaReference | None:
    photo_sizes = message.get("photo")
    if isinstance(photo_sizes, list) and photo_sizes:
        candidates = [item for item in photo_sizes if isinstance(item, Mapping) and item.get("file_id")]
        if candidates:
            largest = max(
                candidates,
                key=lambda item: (
                    _optional_int(item.get("file_size")) or 0,
                    (_optional_int(item.get("width")) or 0) * (_optional_int(item.get("height")) or 0),
                ),
            )
            return MediaReference(
                media_type="photo",
                file_id=str(largest["file_id"]),
                file_unique_id=_optional_str(largest.get("file_unique_id")),
                file_size=_optional_int(largest.get("file_size")),
                mime_type="image/jpeg",
                caption=_caption(message),
                **_source_fields(message),
            )

    video = message.get("video")
    if isinstance(video, Mapping) and video.get("file_id"):
        file_name = _optional_str(video.get("file_name"), limit=240)
        mime_type = _normalise_mime(video.get("mime_type")) or _video_mime_from_extension(file_name)
        if mime_type in VIDEO_MIME_TYPES:
            return MediaReference(
                media_type="video",
                file_id=str(video["file_id"]),
                file_unique_id=_optional_str(video.get("file_unique_id")),
                file_size=_optional_int(video.get("file_size")),
                mime_type=mime_type,
                file_name=file_name,
                caption=_caption(message),
                duration_seconds=_optional_int(video.get("duration")),
                **_source_fields(message),
            )

    voice = message.get("voice")
    if isinstance(voice, Mapping) and voice.get("file_id"):
        mime_type = _normalise_mime(voice.get("mime_type")) or "audio/ogg"
        if mime_type in AUDIO_MIME_TYPES:
            return MediaReference(
                media_type="voice",
                file_id=str(voice["file_id"]),
                file_unique_id=_optional_str(voice.get("file_unique_id")),
                file_size=_optional_int(voice.get("file_size")),
                mime_type=mime_type,
                caption=_caption(message),
                **_source_fields(message),
            )

    audio = message.get("audio")
    if isinstance(audio, Mapping) and audio.get("file_id"):
        file_name = _optional_str(audio.get("file_name"), limit=240)
        mime_type = _normalise_mime(audio.get("mime_type"))
        if (mime_type and mime_type in AUDIO_MIME_TYPES) or _extension(file_name) in AUDIO_EXTENSIONS:
            return MediaReference(
                media_type="audio",
                file_id=str(audio["file_id"]),
                file_unique_id=_optional_str(audio.get("file_unique_id")),
                file_size=_optional_int(audio.get("file_size")),
                mime_type=mime_type or _audio_mime_from_extension(file_name),
                file_name=file_name,
                caption=_caption(message),
                **_source_fields(message),
            )

    document = message.get("document")
    if isinstance(document, Mapping) and document.get("file_id"):
        file_name = _optional_str(document.get("file_name"), limit=240)
        mime_type = _normalise_mime(document.get("mime_type"))
        ext = _extension(file_name)
        media_type: str | None = None
        if (mime_type and mime_type in IMAGE_MIME_TYPES) or ext in IMAGE_EXTENSIONS:
            media_type = "image_document"
            mime_type = mime_type or _image_mime_from_extension(ext)
        elif (mime_type and mime_type in PDF_MIME_TYPES) or ext == ".pdf":
            media_type = "pdf"
            mime_type = mime_type or "application/pdf"
        elif (mime_type and mime_type in TEXT_MIME_TYPES) or ext in TEXT_EXTENSIONS:
            media_type = "text_file"
            mime_type = mime_type or _text_mime_from_extension(ext)
        elif ext in CODE_EXTENSIONS:
            media_type = "code_file"
            mime_type = mime_type or "text/plain"

        if media_type:
            return MediaReference(
                media_type=media_type,
                file_id=str(document["file_id"]),
                file_unique_id=_optional_str(document.get("file_unique_id")),
                file_size=_optional_int(document.get("file_size")),
                mime_type=mime_type,
                file_name=file_name,
                caption=_caption(message),
                **_source_fields(message),
            )

    return None


def _image_mime_from_extension(ext: str) -> str:
    if ext == ".png":
        return "image/png"
    if ext == ".webp":
        return "image/webp"
    return "image/jpeg"


def _audio_mime_from_extension(file_name: str | None) -> str:
    ext = _extension(file_name)
    if ext == ".mp3":
        return "audio/mpeg"
    if ext == ".wav":
        return "audio/wav"
    if ext in {".m4a", ".mp4"}:
        return "audio/mp4"
    return "audio/ogg"


def _video_mime_from_extension(file_name: str | None) -> str:
    ext = _extension(file_name)
    return {
        ".avi": "video/avi",
        ".flv": "video/x-flv",
        ".m4v": "video/mp4",
        ".mov": "video/quicktime",
        ".mpeg": "video/mpeg",
        ".mpg": "video/mpeg",
        ".webm": "video/webm",
        ".wmv": "video/x-ms-wmv",
        ".3gp": "video/3gpp",
    }.get(ext, "video/mp4")


def _text_mime_from_extension(ext: str) -> str:
    if ext == ".json":
        return "application/json"
    if ext in {".yaml", ".yml"}:
        return "application/x-yaml"
    if ext == ".md":
        return "text/markdown"
    return "text/plain"


def detect_media_reference(message: Mapping[str, Any], *, prefer_reply: bool = True) -> MediaReference | None:
    """Return the first supported media reference, preferring reply-to media."""
    messages: list[Mapping[str, Any]] = []
    reply = message.get("reply_to_message")
    if prefer_reply and isinstance(reply, Mapping):
        messages.append(reply)
    messages.append(message)
    for candidate in messages:
        ref = _media_ref_from_message(candidate)
        if ref is not None:
            return ref
    return None


def detect_media_references(
    message: Mapping[str, Any],
    *,
    prefer_reply: bool = True,
    media_group_loader: Callable[[str], Sequence[Mapping[str, Any]]] | None = None,
    max_items: int = MAX_MEDIA_REFS_PER_REQUEST,
) -> list[MediaReference]:
    """Return bounded media refs, expanding a Telegram album when available.

    Telegram replies point to one concrete message even when the client renders
    that message as part of an album. The optional loader supplies metadata-only
    sibling references previously observed under the same ``media_group_id``.
    The directly replied-to item remains first, followed by album siblings in
    message order.
    """
    candidates: list[Mapping[str, Any]] = []
    reply = message.get("reply_to_message")
    if prefer_reply and isinstance(reply, Mapping):
        candidates.append(reply)
    candidates.append(message)

    for candidate in candidates:
        direct_ref = _media_ref_from_message(candidate)
        group_id = _optional_str(candidate.get("media_group_id"), limit=160)
        refs: list[MediaReference] = [direct_ref] if direct_ref is not None else []
        if group_id and media_group_loader is not None:
            try:
                loaded = media_group_loader(group_id)
            except Exception as exc:
                logger.warning(
                    "Telegram media group lookup failed; using direct media only",
                    extra={"media_group_id": group_id, "error_type": exc.__class__.__name__},
                )
            else:
                siblings: list[MediaReference] = []
                for value in loaded:
                    if not isinstance(value, Mapping):
                        continue
                    ref = MediaReference.from_mapping(value)
                    if ref.media_type in SUPPORTED_MEDIA_TYPES and ref.file_id:
                        siblings.append(ref)
                siblings.sort(key=lambda item: item.source_message_id if item.source_message_id is not None else 0)
                refs.extend(siblings)

        deduped: list[MediaReference] = []
        seen: set[tuple[int | None, str]] = set()
        for ref in refs:
            identity = (ref.source_message_id, ref.file_unique_id or ref.file_id)
            if identity in seen:
                continue
            seen.add(identity)
            deduped.append(ref)
            if len(deduped) >= max(1, max_items):
                break
        if deduped:
            return deduped
    return []


def observe_media_group(repo: Any, update: Mapping[str, Any]) -> None:
    """Persist metadata-only album membership for later explicit replies."""
    if not MULTIMODAL_ENABLED or repo is None:
        return
    message = update.get("message")
    if not isinstance(message, Mapping):
        return
    group_id = _optional_str(message.get("media_group_id"), limit=160)
    chat_id = (message.get("chat") or {}).get("id") if isinstance(message.get("chat"), Mapping) else None
    if not group_id or chat_id is None:
        return
    ref = _media_ref_from_message(message)
    if ref is None:
        return
    try:
        repo.store_media_group_item(
            chat_id=chat_id,
            media_group_id=group_id,
            message_id=message.get("message_id"),
            media_ref=ref.to_dict(),
            created_at=_optional_int(message.get("date")),
        )
        logger.info(
            "Telegram media group item stored",
            extra={
                "chat_id": chat_id,
                "media_group_id": group_id,
                **media_reference_log_extra(ref),
            },
        )
    except Exception as exc:
        logger.warning(
            "Telegram media group item could not be stored",
            extra={
                "chat_id": chat_id,
                "media_group_id": group_id,
                "media_type": ref.media_type,
                "error_type": exc.__class__.__name__,
            },
        )


def has_any_media(message: Mapping[str, Any], *, prefer_reply: bool = True) -> bool:
    """Return True when the current or replied message contains Telegram media."""
    media_fields = ("photo", "voice", "audio", "document", "video", "animation", "sticker")
    messages: list[Mapping[str, Any]] = []
    reply = message.get("reply_to_message")
    if prefer_reply and isinstance(reply, Mapping):
        messages.append(reply)
    messages.append(message)
    return any(any(candidate.get(field) for field in media_fields) for candidate in messages)


def default_question_for_media(ref: MediaReference) -> str:
    """Default internal task when a user replies to media with only /ask."""
    if ref.media_type in {"photo", "image_document"}:
        return "Explain what is shown in this image. If it is technical, highlight the likely issue and next step."
    if ref.media_type in {"voice", "audio"}:
        return "Transcribe or summarize this audio, then explain the important point if useful."
    if ref.media_type == "video":
        return "Explain what happens in this video and summarize its important visual and spoken details."
    if ref.media_type == "pdf":
        return "Summarize the key points in this PDF, focusing on what matters for the current technical discussion."
    return "Summarize or explain this file, focusing on the technical meaning and likely next step."


def default_question_for_media_refs(refs: Sequence[MediaReference]) -> str:
    """Return a natural default request for one item or a Telegram album."""
    if len(refs) == 1:
        return default_question_for_media(refs[0])
    return "Analyze these related media items together and summarize the important visual, spoken, and textual details."


def media_retrieval_query(base_query: str, ref: MediaReference) -> str:
    """Build a compact retrieval query from the question and safe media metadata only."""
    parts = [base_query.strip()] if base_query.strip() else [default_question_for_media(ref)]
    if ref.caption:
        parts.append(f"Media caption: {ref.caption[:300]}")
    if ref.file_name:
        parts.append(f"File name: {ref.file_name[:180]}")
    if ref.source_display_name or ref.source_username:
        parts.append(f"Media source: {ref.source_display_name or ref.source_username}")
    return "\n\n".join(part for part in parts if part)


def media_references_retrieval_query(base_query: str, refs: Sequence[MediaReference]) -> str:
    """Build one compact retrieval query for a media collection."""
    if not refs:
        return base_query.strip()
    parts = [base_query.strip()] if base_query.strip() else [default_question_for_media_refs(refs)]
    captions: list[str] = []
    file_names: list[str] = []
    sources: list[str] = []
    for ref in refs:
        if ref.caption and ref.caption not in captions:
            captions.append(ref.caption)
        if ref.file_name and ref.file_name not in file_names:
            file_names.append(ref.file_name)
        source = ref.source_display_name or ref.source_username
        if source and source not in sources:
            sources.append(source)
    if captions:
        parts.append("Media captions: " + " | ".join(value[:300] for value in captions[:4]))
    if file_names:
        parts.append("Media files: " + ", ".join(value[:180] for value in file_names[:4]))
    if sources:
        parts.append("Media sources: " + ", ".join(sources[:4]))
    return "\n\n".join(part for part in parts if part)


def media_reference_log_extra(ref: Mapping[str, Any] | MediaReference) -> dict[str, Any]:
    """Return safe structured log fields for a media reference.

    Telegram ``file_id`` is intentionally excluded because it can be used to
    download the media again. Captions are represented only by length/presence.
    """
    media = ref if isinstance(ref, MediaReference) else MediaReference.from_mapping(ref)
    fields: dict[str, Any] = {
        "media_type": media.media_type,
        "has_caption": bool(media.caption),
        "caption_chars": len(media.caption or ""),
    }
    for key in (
        "file_unique_id",
        "file_size",
        "mime_type",
        "file_name",
        "duration_seconds",
        "media_group_id",
        "source_message_id",
        "source_user_id",
        "source_username",
        "source_display_name",
        "source_sender_type",
    ):
        value = getattr(media, key)
        if value not in (None, ""):
            if key == "file_name":
                fields[key] = str(value)[:180]
            elif key == "source_display_name":
                fields[key] = str(value)[:80]
            else:
                fields[key] = value
    return fields


def media_references_log_extra(refs: Sequence[Mapping[str, Any] | MediaReference]) -> dict[str, Any]:
    """Return safe aggregate log fields without reusable Telegram file ids."""
    media = [value if isinstance(value, MediaReference) else MediaReference.from_mapping(value) for value in refs]
    group_ids = [ref.media_group_id for ref in media if ref.media_group_id]
    return {
        "media_item_count": len(media),
        "media_types": list(dict.fromkeys(ref.media_type for ref in media)),
        "media_group_id": group_ids[0] if group_ids else None,
        "media_source_message_ids": [ref.source_message_id for ref in media if ref.source_message_id is not None],
    }


def media_reference_context(ref: MediaReference) -> str:
    """Render compact media metadata for the Gemini text prompt."""
    lines = [
        "Explicit media context:",
        f"- media_type: {ref.media_type}",
    ]
    if ref.mime_type:
        lines.append(f"- mime_type: {ref.mime_type}")
    if ref.file_name:
        lines.append(f"- file_name: {ref.file_name[:180]}")
    if ref.file_size is not None:
        lines.append(f"- file_size_bytes: {ref.file_size}")
    if ref.duration_seconds is not None:
        lines.append(f"- duration_seconds: {ref.duration_seconds}")
    if ref.media_group_id:
        lines.append(f"- media_group_id: {ref.media_group_id}")
    if ref.caption:
        lines.append(f"- caption: {truncate_log_text(ref.caption, max_chars=500)}")
    if ref.source_message_id is not None:
        lines.append(f"- source_message_id: {ref.source_message_id}")
    if ref.source_user_id is not None:
        lines.append(f"- source_user_id: {ref.source_user_id}")
    if ref.source_username:
        lines.append(f"- source_username: @{ref.source_username.lstrip('@')}")
    if ref.source_display_name:
        lines.append(f"- source_display_name: {ref.source_display_name[:80]}")
    if ref.source_sender_type:
        lines.append(f"- source_sender_type: {ref.source_sender_type[:80]}")
    return "\n".join(lines)


def agent_reply_media_metadata(ref: MediaReference, *, media_summary: str | None = None) -> dict[str, Any]:
    """Return safe short-lived media metadata for AGENT_REPLY# continuity."""
    item: dict[str, Any] = {
        "media_type": ref.media_type,
        "media_analysis_available": True,
    }
    for key in (
        "file_unique_id",
        "file_size",
        "mime_type",
        "file_name",
        "caption",
        "duration_seconds",
        "media_group_id",
        "source_message_id",
        "source_user_id",
        "source_username",
        "source_display_name",
        "source_sender_type",
    ):
        value = getattr(ref, key)
        if value not in (None, ""):
            if key == "caption":
                item[key] = str(value)[:500]
            elif key == "file_name":
                item[key] = str(value)[:180]
            else:
                item[key] = value
    if media_summary:
        item["media_summary"] = media_summary[:900]
    return item


def media_summary_from_answer(answer_text: str, ref: MediaReference) -> str:
    """Create a bounded continuity summary from the model answer."""
    answer = " ".join((answer_text or "").split())
    prefix = ref.media_type.replace("_", " ")
    if ref.file_name:
        prefix = f"{prefix} {ref.file_name[:120]}"
    if not answer:
        return prefix[:180]
    return f"{prefix}: {answer[:760]}"


def _validate_ref(ref: MediaReference) -> None:
    if ref.media_type not in SUPPORTED_MEDIA_TYPES or not ref.file_id:
        raise MediaUnsupportedError("Unsupported or malformed media reference")
    if ref.file_size is not None and ref.file_size > MULTIMODAL_MAX_DOWNLOAD_BYTES:
        raise MediaTooLargeError(f"Media exceeds {MULTIMODAL_MAX_DOWNLOAD_BYTES} bytes")
    if (
        ref.media_type not in TEXT_MEDIA_TYPES
        and ref.file_size is not None
        and ref.file_size > MULTIMODAL_INLINE_MAX_BYTES
    ):
        raise MediaTooLargeError(f"Media exceeds inline Gemini limit of {MULTIMODAL_INLINE_MAX_BYTES} bytes")


def _decode_text_file(data: bytes, *, max_chars: int) -> tuple[str, bool]:
    text = data.decode("utf-8", errors="replace").replace("\x00", "")
    truncated = len(text) > max_chars
    return text[:max_chars], truncated


def _gemini_parts_for_download(ref: MediaReference, data: bytes) -> tuple[list[dict[str, Any]], str, str]:
    context = media_reference_context(ref)
    if ref.media_type in TEXT_MEDIA_TYPES:
        text, truncated = _decode_text_file(data, max_chars=MULTIMODAL_TEXT_FILE_MAX_CHARS)
        truncation_note = "\nThe file content is truncated to the configured character limit." if truncated else ""
        file_label = ref.file_name or ref.media_type
        part_text = f"Attached {ref.media_type.replace('_', ' ')} content ({file_label}):\n" f"{text}{truncation_note}"
        return (
            [{"text": part_text}],
            f"{context}\n- content_mode: bounded_text\n- truncated: {str(truncated).lower()}",
            "bounded_text",
        )

    if len(data) > MULTIMODAL_INLINE_MAX_BYTES:
        raise MediaTooLargeError(f"Media exceeds inline Gemini limit of {MULTIMODAL_INLINE_MAX_BYTES} bytes")
    mime_type = ref.mime_type or ("image/jpeg" if ref.media_type == "photo" else "application/octet-stream")
    inline_part = {
        "inline_data": {
            "mime_type": mime_type,
            "data": base64.b64encode(data).decode("ascii"),
        }
    }
    return [inline_part], f"{context}\n- content_mode: inline_data", "inline_data"


def prepare_media_for_gemini(bot: Any, media_ref: Mapping[str, Any] | MediaReference) -> PreparedMedia:
    """Download explicit media in the async worker and build Gemini parts."""
    if not MULTIMODAL_ENABLED:
        raise MediaDisabledError("Multimodal support is disabled")
    ref = media_ref if isinstance(media_ref, MediaReference) else MediaReference.from_mapping(media_ref)
    _validate_ref(ref)

    try:
        file_info = bot.get_file(ref.file_id)
        file_path = str(file_info.get("file_path") or "")
        remote_size = _optional_int(file_info.get("file_size"))
        if remote_size is not None and remote_size > MULTIMODAL_MAX_DOWNLOAD_BYTES:
            raise MediaTooLargeError(f"Media exceeds {MULTIMODAL_MAX_DOWNLOAD_BYTES} bytes")
        if (
            ref.media_type not in TEXT_MEDIA_TYPES
            and remote_size is not None
            and remote_size > MULTIMODAL_INLINE_MAX_BYTES
        ):
            raise MediaTooLargeError(f"Media exceeds inline Gemini limit of {MULTIMODAL_INLINE_MAX_BYTES} bytes")
        data = bot.download_file(file_path, max_bytes=MULTIMODAL_MAX_DOWNLOAD_BYTES)
    except TelegramFileTooLargeError as exc:
        raise MediaTooLargeError(str(exc)) from exc
    except TelegramAPIError as exc:
        retryable = exc.status >= 500
        raise MediaUnavailableError("Telegram could not return media", retryable) from exc
    except MediaError:
        raise
    except Exception as exc:
        logger.warning("Telegram media download failed", extra={"error_type": exc.__class__.__name__})
        raise MediaUnavailableError("Telegram media download failed", False) from exc

    if len(data) > MULTIMODAL_MAX_DOWNLOAD_BYTES:
        raise MediaTooLargeError(f"Media exceeds {MULTIMODAL_MAX_DOWNLOAD_BYTES} bytes")
    parts, context, content_mode = _gemini_parts_for_download(ref, data)
    return PreparedMedia(
        media_parts=parts,
        media_context=context,
        agent_reply_metadata=agent_reply_media_metadata(ref),
        downloaded_bytes=len(data),
        content_mode=content_mode,
    )


def _collection_agent_reply_metadata(refs: Sequence[MediaReference]) -> dict[str, Any]:
    if len(refs) == 1:
        return agent_reply_media_metadata(refs[0])
    captions = [ref.caption for ref in refs if ref.caption]
    group_ids = [ref.media_group_id for ref in refs if ref.media_group_id]
    item: dict[str, Any] = {
        "media_type": "media_group",
        "media_types": ",".join(dict.fromkeys(ref.media_type for ref in refs)),
        "media_item_count": len(refs),
        "media_analysis_available": True,
    }
    if captions:
        item["caption"] = captions[0][:500]
    if group_ids:
        item["media_group_id"] = group_ids[0][:160]
    return item


def prepare_media_collection_for_gemini(
    bot: Any,
    media_refs: Sequence[Mapping[str, Any] | MediaReference],
) -> PreparedMediaCollection:
    """Prepare a bounded collection while allowing safe partial album success."""
    if not MULTIMODAL_ENABLED:
        raise MediaDisabledError("Multimodal support is disabled")
    refs = [
        value if isinstance(value, MediaReference) else MediaReference.from_mapping(value)
        for value in media_refs[:MAX_MEDIA_REFS_PER_REQUEST]
    ]
    if not refs:
        raise MediaUnsupportedError("No supported media references")

    parts: list[dict[str, Any]] = []
    contexts: list[str] = []
    prepared_refs: list[MediaReference] = []
    content_modes: list[str] = []
    skipped_reasons: dict[str, int] = {}
    downloaded_bytes = 0
    retryable_errors: list[MediaUnavailableError] = []

    def skip(reason: str) -> None:
        skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1

    for ref in refs:
        if ref.file_size is not None and downloaded_bytes + ref.file_size > MULTIMODAL_MAX_DOWNLOAD_BYTES:
            skip("aggregate_too_large")
            continue
        try:
            prepared = prepare_media_for_gemini(bot, ref)
        except MediaTooLargeError:
            skip("too_large")
            continue
        except MediaUnsupportedError:
            skip("unsupported")
            continue
        except MediaUnavailableError as exc:
            skip("unavailable")
            if exc.retryable:
                retryable_errors.append(exc)
            continue
        if downloaded_bytes + prepared.downloaded_bytes > MULTIMODAL_MAX_DOWNLOAD_BYTES:
            skip("aggregate_too_large")
            continue
        prepared_refs.append(ref)
        downloaded_bytes += prepared.downloaded_bytes
        parts.extend(prepared.media_parts)
        contexts.append(f"Media item {len(prepared_refs)}:\n{prepared.media_context}")
        content_modes.append(prepared.content_mode)

    if not prepared_refs:
        if retryable_errors:
            raise retryable_errors[0]
        if skipped_reasons.get("too_large") or skipped_reasons.get("aggregate_too_large"):
            raise MediaTooLargeError("Every media item exceeds configured limits")
        if skipped_reasons.get("unavailable"):
            raise MediaUnavailableError("Telegram could not return any media", False)
        raise MediaUnsupportedError("No media item could be prepared")

    if skipped_reasons:
        contexts.append(
            "Some related media items could not be analyzed: "
            + ", ".join(f"{reason}={count}" for reason, count in sorted(skipped_reasons.items()))
            + ". Do not claim details from skipped items."
        )
    return PreparedMediaCollection(
        media_parts=parts,
        media_context="\n\n".join(contexts),
        agent_reply_metadata=_collection_agent_reply_metadata(prepared_refs),
        downloaded_bytes=downloaded_bytes,
        requested_count=len(refs),
        prepared_count=len(prepared_refs),
        skipped_count=sum(skipped_reasons.values()),
        skipped_reasons=skipped_reasons,
        content_modes=content_modes,
    )
