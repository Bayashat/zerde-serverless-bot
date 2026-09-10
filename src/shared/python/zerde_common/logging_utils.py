"""Safe, size-bounded logging helpers for API Gateway, Telegram, and LLM text."""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import quote, quote_plus

_DEFAULT_MAX_EXTRA = 512
_DEFAULT_LLM_PREVIEW = 200
_REDACTED = "[REDACTED]"
_SECRET_NAME_RE = re.compile(
    r"(?:token|secret|password|passwd|api_?key|access_?key(?:_?id)?|authorization|cookie|credential|signature)$", re.I
)
_CONTENT_FIELDS = {
    "body",
    "body_preview",
    "caption",
    "contact",
    "data",
    "description",
    "display_name",
    "document",
    "event",
    "file_id",
    "file_name",
    "file_path",
    "file_ref",
    "file_unique_id",
    "first_name",
    "last_name",
    "media_group_id",
    "media_ref",
    "media_refs",
    "payload",
    "phone_number",
    "photo",
    "prompt",
    "request_body",
    "response",
    "response_body",
    "response_preview",
    "response_text",
    "source_display_name",
    "source_username",
    "telegram_update",
    "telegram_update_json",
    "text",
    "user_message",
    "username",
    "video",
    "voice",
}
_TELEGRAM_FILE_URL_RE = re.compile(r"(?:https?://[^\s\"'<>]+)?/file/bot[^\s\"'<>]+", re.I)
_TELEGRAM_BOT_PATH_RE = re.compile(r"(/bot)[^/\s\"'<>?]+(?=/[A-Za-z])")
_TELEGRAM_TOKEN_RE = re.compile(r"(?<![\w])\d{5,}:[A-Za-z0-9_-]{20,}")
_CREDENTIAL_VALUE_RE = re.compile(
    r"((?:[\w-]*(?:token|secret|password|passwd|api[_-]?key|access[_-]?key(?:[_-]?id)?|signature|credential)"
    r"|authorization|cookie|key)[\"']?\s*[:=]\s*)"
    r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|(?:(?:Bearer|Basic)\s+)?[^\s\"'&,;}]+)",
    re.I,
)
_AUTH_SCHEME_RE = re.compile(r"\b(Bearer|Basic)\s+[^\s\"'&,;}]+", re.I)
_PROVIDER_KEY_RE = re.compile(r"\b(?:AIza[A-Za-z0-9_-]{20,}|gsk_[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{20,})")
_TELEGRAM_UPDATE_TYPES = (
    "message",
    "edited_message",
    "channel_post",
    "edited_channel_post",
    "business_connection",
    "business_message",
    "edited_business_message",
    "deleted_business_messages",
    "message_reaction",
    "message_reaction_count",
    "inline_query",
    "chosen_inline_result",
    "callback_query",
    "shipping_query",
    "pre_checkout_query",
    "purchased_paid_media",
    "poll",
    "poll_answer",
    "my_chat_member",
    "chat_member",
    "chat_join_request",
    "chat_boost",
    "removed_chat_boost",
)


def redact_log_text(text: str) -> str:
    """Redact credentials at emission time, including lazily loaded SSM env values."""
    # Read the current environment rather than caching: SSM secrets arrive after logger setup.
    values = {value for name, value in os.environ.items() if _SECRET_NAME_RE.search(name) and len(value) >= 4}
    variants = {variant for value in values for variant in (value, quote(value, safe=""), quote_plus(value))}
    text = _TELEGRAM_FILE_URL_RE.sub("[REDACTED_TELEGRAM_FILE_URL]", text)
    text = _TELEGRAM_BOT_PATH_RE.sub(r"\1[REDACTED]", text)
    text = _TELEGRAM_TOKEN_RE.sub(_REDACTED, text)
    for value in sorted(variants, key=len, reverse=True):
        text = text.replace(value, _REDACTED)
    text = _CREDENTIAL_VALUE_RE.sub(lambda match: match.group(1) + _REDACTED, text)
    text = _AUTH_SCHEME_RE.sub(lambda match: match.group(1) + " [REDACTED]", text)
    return _PROVIDER_KEY_RE.sub(_REDACTED, text)


def sanitize_log_value(value: Any, *, _depth: int = 0) -> Any:
    """Copy structured log fields without raw content or credentials; never mutate callers."""
    if _depth >= 12:
        return "[OMITTED_NESTED_VALUE]"
    if isinstance(value, dict):
        return {
            redact_log_text(str(key)): (
                _REDACTED
                if _SECRET_NAME_RE.search(str(key)) or str(key).lower() in _CONTENT_FIELDS
                else sanitize_log_value(item, _depth=_depth + 1)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [sanitize_log_value(item, _depth=_depth + 1) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_log_text(str(value))


def truncate_log_text(text: str | None, max_chars: int = _DEFAULT_MAX_EXTRA) -> str:
    """Bound diagnostic text; use metadata-only helpers for user/model content."""
    if text is None:
        return ""
    t = redact_log_text(str(text)).replace("\n", " ").strip()
    if len(t) <= max_chars:
        return t
    return f"{t[:max_chars]}…(truncated,{len(t)} chars)"


def api_gateway_event_summary(event: dict[str, Any]) -> dict[str, Any]:
    """HTTP API v2 (payload format 2.0) style event summary; no raw headers or secrets."""
    if not isinstance(event, dict):
        return {"event_type": "unknown", "raw_type": type(event).__name__}
    rc = event.get("requestContext") or {}
    http = rc.get("http") or event.get("http") or {}
    if http or event.get("rawPath") is not None or "routeKey" in event:
        return {
            "event_type": "api_gateway",
            "route_key": event.get("routeKey"),
            "method": http.get("method"),
            "path": http.get("path") or event.get("rawPath"),
            "request_id": (rc.get("requestId") or event.get("requestContext", {}).get("requestId")),
        }
    if event.get("Records"):
        r0 = (event.get("Records") or [{}])[0]
        if isinstance(r0, dict) and (r0.get("eventSource") == "aws: sqs" or "body" in r0):
            return {
                "event_type": "sqs",
                "record_count": len(event["Records"]),
                "first_message_id": r0.get("messageId"),
            }
    if event.get("source") == "aws.events" or event.get("resources"):
        return {
            "event_type": "scheduled",
            "id": event.get("id"),
            "detail_type": event.get("detail-type") or event.get("detailType"),
        }
    # EventBridge direct input (custom JSON from CDK) — e.g. quiz digest / news runs
    if "chat_ids" in event and "lang" in event:
        cids = event.get("chat_ids")
        n = len(cids) if isinstance(cids, list) else None
        return {
            "event_type": "scheduled_job",
            "lang": event.get("lang"),
            "action": event.get("action"),
            "chat_id_count": n,
        }
    return {"event_type": "unknown_dict", "key_count": len(event)}


def llm_text_log_fields(
    text: str | None,
    *,
    max_preview: int = _DEFAULT_LLM_PREVIEW,
) -> dict[str, Any]:
    """Log output size only; ``max_preview`` is retained for caller compatibility."""
    return {"response_chars": len(str(text)) if text else 0}


def safe_json_dumps_for_log(obj: Any, max_chars: int = _DEFAULT_MAX_EXTRA) -> str:
    """Serialize for logs with a hard char cap (errors, Telegram error descriptions)."""
    try:
        raw = json.dumps(sanitize_log_value(obj), default=str, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        return f"<json_error:{type(e).__name__}>"
    return truncate_log_text(raw, max_chars)


def telegram_update_log_extra(update: dict[str, Any]) -> dict[str, Any]:
    """Return allowlisted metadata only; never serialize a Telegram Update or its text."""
    event_type = next((kind for kind in _TELEGRAM_UPDATE_TYPES if kind in update), "unknown")
    extra: dict[str, Any] = {"event_type": event_type}
    if type(update.get("update_id")) is int:
        extra["update_id"] = update["update_id"]
    event = update.get(event_type)
    if isinstance(event, dict):
        for field in ("text", "caption", "data"):
            if isinstance(event.get(field), str):
                extra[f"{field}_chars"] = len(event[field])
        for field in ("entities", "caption_entities", "new_chat_members", "photo"):
            if isinstance(event.get(field), list):
                extra[f"{field}_count"] = len(event[field])
    return extra
