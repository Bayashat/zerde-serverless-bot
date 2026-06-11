"""High-level helpers for observing Telegram updates into group memory."""

from __future__ import annotations

from typing import Any

from core.config import GROUP_MEMORY_ENABLED, GROUP_MEMORY_RECENT_LIMIT
from core.logger import LoggerAdapter, get_logger
from services.repositories.group_memory import GroupMemoryRepository

logger = LoggerAdapter(get_logger(__name__), {})


def extract_message_text(message: dict[str, Any]) -> str:
    """Return visible text/caption worth storing for group context."""
    text = message.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    caption = message.get("caption")
    if isinstance(caption, str) and caption.strip():
        return caption.strip()
    return ""


def display_name(user: dict[str, Any]) -> str:
    """Build a compact display name for prompts and memory profiles."""
    first = (user.get("first_name") or "").strip()
    last = (user.get("last_name") or "").strip()
    username = (user.get("username") or "").strip()
    full = " ".join(part for part in (first, last) if part)
    if full:
        return full[:80]
    if username:
        return f"@{username}"[:80]
    return str(user.get("id") or "Unknown")


def is_storable_group_message(update: dict[str, Any]) -> bool:
    message = update.get("message")
    if not isinstance(message, dict):
        return False
    chat = message.get("chat") or {}
    if chat.get("type") not in {"group", "supergroup"}:
        return False
    user = message.get("from") or {}
    if user.get("is_bot"):
        return False
    text = extract_message_text(message)
    return bool(text and not text.startswith("/"))


def observe_update(repo: GroupMemoryRepository | None, update: dict[str, Any]) -> None:
    """Persist a human group message when global and per-chat memory are enabled."""
    if not GROUP_MEMORY_ENABLED or repo is None or not is_storable_group_message(update):
        return

    message = update["message"]
    chat_id = message["chat"]["id"]
    if not repo.is_memory_enabled(chat_id):
        return

    user = message.get("from") or {}
    user_id = user.get("id")
    message_id = message.get("message_id")
    text = extract_message_text(message)
    if not all([chat_id, user_id, message_id, text]):
        return

    try:
        repo.store_message(
            chat_id=chat_id,
            message_id=message_id,
            user_id=user_id,
            display_name=display_name(user),
            username=user.get("username"),
            text=text,
            created_at=message.get("date"),
        )
        logger.debug("Stored group memory message", extra={"chat_id": chat_id, "message_id": message_id})
    except Exception:
        logger.exception("Failed to store group memory message", extra={"chat_id": chat_id, "message_id": message_id})


def format_recent_context(repo: GroupMemoryRepository, chat_id: int | str, *, limit: int | None = None) -> str:
    """Render recent messages as compact prompt context."""
    messages = repo.get_recent_messages(chat_id, limit=limit or GROUP_MEMORY_RECENT_LIMIT)
    lines: list[str] = []
    for item in messages:
        name = str(item.get("display_name") or item.get("username") or item.get("user_id") or "Unknown")
        text = str(item.get("text") or "").replace("\n", " ").strip()
        if text:
            lines.append(f"{name}: {text[:700]}")
    return "\n".join(lines)
