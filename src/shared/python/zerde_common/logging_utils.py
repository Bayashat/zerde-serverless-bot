"""Safe, size-bounded logging helpers for API Gateway, Telegram, and LLM text."""

from __future__ import annotations

import json
from typing import Any

_DEFAULT_MAX_EXTRA = 512
_DEFAULT_LLM_PREVIEW = 200


def truncate_log_text(text: str | None, max_chars: int = _DEFAULT_MAX_EXTRA) -> str:
    """Return a string safe for log ``extra=`` (length bounded, never the full untrusted body)."""
    if text is None:
        return ""
    t = str(text).replace("\n", " ").strip()
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
    keys_preview = list(event.keys())[:12]
    return {"event_type": "unknown_dict", "keys": keys_preview}


def _preview(text: str, max_preview: int) -> str:
    t = text.replace("\n", " ").strip()
    if len(t) <= max_preview:
        return t
    return t[:max_preview] + "…"


def llm_text_log_fields(
    text: str | None,
    *,
    max_preview: int = _DEFAULT_LLM_PREVIEW,
) -> dict[str, Any]:
    """Fields for logging LLM text without dumping full model output to CloudWatch."""
    if not text:
        return {"response_chars": 0, "response_preview": ""}
    s = str(text)
    return {
        "response_chars": len(s),
        "response_preview": _preview(s, max_preview),
    }


def safe_json_dumps_for_log(obj: Any, max_chars: int = _DEFAULT_MAX_EXTRA) -> str:
    """Serialize for logs with a hard char cap (errors, Telegram error descriptions)."""
    try:
        raw = json.dumps(obj, default=str, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        return f"<json_error:{e}>"
    return truncate_log_text(raw, max_chars)
