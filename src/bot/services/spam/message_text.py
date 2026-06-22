"""Aggregate user-visible text and bounded context for spam screening."""

from typing import Any

_SPAM_SEGMENT_SEP = "\n\n---\n"
_CONTEXT_TEXT_LIMIT = 1200
_RECENT_TEXT_LIMIT = 360
_FORMATTED_CONTEXT_LIMIT = 6000


def collect_spam_screen_text(msg: dict[str, Any]) -> str:
    """Build one string for rule + AI spam checks.

    Merges the message body (text or caption), quoted post text (``quote.text``),
    and external reply context (channel title / @username from ``external_reply``).
    """
    segments: list[str] = []

    primary = _message_text(msg)
    if primary:
        segments.append(primary)

    quote_text = _quote_text(msg)
    if quote_text:
        segments.append(quote_text)

    external_text = _external_reply_text(msg)
    if external_text:
        segments.append(external_text)

    return _SPAM_SEGMENT_SEP.join(segments)


def build_spam_context_payload(
    msg: dict[str, Any],
    *,
    rule_score: float | None = None,
    triggered_rules: list[str] | None = None,
) -> dict[str, Any]:
    """Build a compact, JSON-serializable context payload for async AI review."""
    payload: dict[str, Any] = {
        "current_message": _truncate_text(_message_text(msg), _CONTEXT_TEXT_LIMIT),
        "triggered_rules": list(triggered_rules or []),
    }
    if rule_score is not None:
        payload["rule_score"] = float(rule_score)

    reply = msg.get("reply_to_message")
    if isinstance(reply, dict):
        reply_text = _message_text(reply)
        if reply_text:
            payload["reply_to_message"] = {
                "message_id": reply.get("message_id"),
                "from": _sender_label(reply),
                "text": _truncate_text(reply_text, _CONTEXT_TEXT_LIMIT),
            }

    quote_text = _quote_text(msg)
    if quote_text:
        payload["quote"] = _truncate_text(quote_text, _CONTEXT_TEXT_LIMIT)

    external_text = _external_reply_text(msg)
    if external_text:
        payload["external_reply"] = _truncate_text(external_text, _CONTEXT_TEXT_LIMIT)

    return payload


def format_spam_ai_context(
    *,
    text: str,
    message_context: dict[str, Any] | None = None,
    recent_context: list[dict[str, Any]] | None = None,
    rule_score: float | None = None,
    triggered_rules: list[str] | None = None,
) -> str:
    """Render bounded structured context for the Groq spam classifier."""
    context = message_context or {}
    current_message = _truncate_text(str(context.get("current_message") or text or ""), _CONTEXT_TEXT_LIMIT)
    score = rule_score if rule_score is not None else context.get("rule_score")
    rules = triggered_rules if triggered_rules is not None else context.get("triggered_rules") or []

    lines: list[str] = [
        "Classify only CURRENT_MESSAGE. Use the other sections only as context.",
        "",
        "CURRENT_MESSAGE:",
        current_message or "(empty)",
        "",
        "RULE_SIGNAL:",
        f"score={score if score is not None else 'unknown'}; triggered_rules={list(rules)}",
    ]

    _append_context_block(lines, "REPLY_TO_MESSAGE", context.get("reply_to_message"))
    _append_context_block(lines, "QUOTE_CONTEXT", context.get("quote"))
    _append_context_block(lines, "EXTERNAL_REPLY_CONTEXT", context.get("external_reply"))

    recent = list(recent_context or [])[-8:]
    if recent:
        lines.extend(["", "RECENT_GROUP_MESSAGES (oldest to newest; context only):"])
        for item in recent:
            speaker = str(item.get("display_name") or item.get("username") or item.get("user_id") or "User")
            item_text = _truncate_text(str(item.get("text") or ""), _RECENT_TEXT_LIMIT)
            if item_text:
                lines.append(f"- {speaker}: {item_text}")

    rendered = "\n".join(lines).strip()
    if len(rendered) > _FORMATTED_CONTEXT_LIMIT:
        return rendered[:_FORMATTED_CONTEXT_LIMIT].rstrip() + "\n[truncated]"
    return rendered


def _append_context_block(lines: list[str], label: str, value: Any) -> None:
    if not value:
        return
    if isinstance(value, dict):
        speaker = value.get("from")
        text = value.get("text") or ""
        rendered = f"{speaker}: {text}" if speaker else str(text)
    else:
        rendered = str(value)
    rendered = _truncate_text(rendered, _CONTEXT_TEXT_LIMIT)
    if rendered:
        lines.extend(["", f"{label}:", rendered])


def _message_text(msg: dict[str, Any]) -> str:
    value = msg.get("text") or msg.get("caption") or ""
    return value.strip() if isinstance(value, str) else ""


def _quote_text(msg: dict[str, Any]) -> str:
    quote = msg.get("quote")
    if not isinstance(quote, dict):
        return ""
    value = quote.get("text")
    return value.strip() if isinstance(value, str) else ""


def _external_reply_text(msg: dict[str, Any]) -> str:
    ext = msg.get("external_reply")
    if not isinstance(ext, dict):
        return ""

    chat: dict[str, Any] | None = None
    origin = ext.get("origin")
    if isinstance(origin, dict):
        ch = origin.get("chat")
        if isinstance(ch, dict):
            chat = ch
    if chat is None:
        ch = ext.get("chat")
        if isinstance(ch, dict):
            chat = ch
    if not isinstance(chat, dict):
        return ""

    segments: list[str] = []
    title = chat.get("title")
    if isinstance(title, str) and title.strip():
        segments.append(title.strip())
    username = chat.get("username")
    if isinstance(username, str) and username.strip():
        segments.append(f"@{username.strip().lstrip('@')}")
    return "\n".join(segments)


def _sender_label(msg: dict[str, Any]) -> str:
    user = msg.get("from")
    if isinstance(user, dict):
        username = user.get("username")
        if isinstance(username, str) and username.strip():
            return f"@{username.strip().lstrip('@')}"
        first_name = user.get("first_name")
        last_name = user.get("last_name")
        parts = [part.strip() for part in (first_name, last_name) if isinstance(part, str) and part.strip()]
        if parts:
            return " ".join(parts)
    sender_tag = msg.get("sender_tag")
    if isinstance(sender_tag, str) and sender_tag.strip():
        return sender_tag.strip()
    return "User"


def _truncate_text(text: str, limit: int) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + "..."
