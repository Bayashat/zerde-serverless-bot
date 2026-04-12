"""Aggregate user-visible text for spam screening (quote, external_reply, etc.)."""

from typing import Any

_SPAM_SEGMENT_SEP = "\n\n---\n"


def collect_spam_screen_text(msg: dict[str, Any]) -> str:
    """Build one string for rule + AI spam checks.

    Merges the message body (text or caption), quoted post text (``quote.text``),
    and external reply context (channel title / @username from ``external_reply``).
    """
    segments: list[str] = []

    primary = msg.get("text") or msg.get("caption") or ""
    if primary:
        segments.append(primary)

    quote = msg.get("quote")
    if isinstance(quote, dict):
        qt = quote.get("text")
        if isinstance(qt, str) and qt.strip():
            segments.append(qt.strip())

    ext = msg.get("external_reply")
    if isinstance(ext, dict):
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
        if isinstance(chat, dict):
            title = chat.get("title")
            if isinstance(title, str) and title.strip():
                segments.append(title.strip())
            username = chat.get("username")
            if isinstance(username, str) and username.strip():
                segments.append(f"@{username.strip()}")

    return _SPAM_SEGMENT_SEP.join(segments)
