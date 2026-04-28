"""Pure helpers for /explain reply media and document-auto eligibility."""

from __future__ import annotations

from typing import Any

from core.config import DOCUMENT_AUTO_SUMMARY_MIMES, MAX_EXPLAIN_MEDIA_BYTES


def extract_reply_media(reply_msg: dict[str, Any]) -> tuple[str, str, str] | None:
    """If *reply_msg* carries voice, audio, or photo, return ``(media_kind, file_id, mime_type)``."""
    if "voice" in reply_msg:
        v = reply_msg["voice"]
        fid = v.get("file_id")
        if not fid:
            return None
        mime = v.get("mime_type") or "audio/ogg"
        return ("voice", str(fid), str(mime))
    if "audio" in reply_msg:
        a = reply_msg["audio"]
        fid = a.get("file_id")
        if not fid:
            return None
        mime = a.get("mime_type") or "audio/mpeg"
        return ("audio", str(fid), str(mime))
    photos = reply_msg.get("photo")
    if isinstance(photos, list) and photos:
        best = max(
            photos,
            key=lambda p: (p.get("file_size") or 0, (p.get("width") or 0) * (p.get("height") or 0)),
        )
        fid = best.get("file_id")
        if not fid:
            return None
        mime = str(best.get("mime_type") or "image/jpeg")
        return ("photo", str(fid), mime)
    return None


def document_auto_allowed(document: dict[str, Any]) -> tuple[bool, str | None]:
    """Return ``(allowed, reason_key)`` where *reason_key* is a translation key when not allowed."""
    mime = (document.get("mime_type") or "").strip().lower()
    if not mime:
        return False, "explain_document_mime_not_supported"
    if mime not in DOCUMENT_AUTO_SUMMARY_MIMES:
        return False, "explain_document_mime_not_supported"
    size = document.get("file_size")
    if isinstance(size, int) and size > MAX_EXPLAIN_MEDIA_BYTES:
        return False, "explain_media_file_too_large"
    return True, None
