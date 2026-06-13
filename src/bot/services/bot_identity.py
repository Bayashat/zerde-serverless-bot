"""Helpers for identifying this Telegram bot in update payloads."""

from __future__ import annotations

import os
from typing import Any


def normalise_username(username: Any) -> str:
    return str(username or "").strip().lstrip("@").lower()


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def configured_bot_id(explicit_bot_id: Any = None) -> int | None:
    """Return the best-known id for this bot without logging or exposing tokens."""
    bot_id = _coerce_int(explicit_bot_id)
    if bot_id is not None:
        return bot_id

    bot_id = _coerce_int(os.environ.get("AGENT_BOT_ID"))
    if bot_id is not None:
        return bot_id

    token = os.environ.get("BOT_TOKEN") or ""
    token_id = token.split(":", 1)[0] if ":" in token else ""
    return _coerce_int(token_id)


def is_self_bot_user(
    user: dict[str, Any] | None,
    *,
    bot_id: Any = None,
    bot_username: str | None = None,
) -> bool:
    """Return True when a Telegram ``from`` user object is this bot."""
    if not isinstance(user, dict) or not user.get("is_bot"):
        return False

    expected_bot_id = configured_bot_id(bot_id)
    sender_id = _coerce_int(user.get("id"))
    if expected_bot_id is not None and sender_id is not None:
        return sender_id == expected_bot_id

    expected_username = normalise_username(
        bot_username if bot_username is not None else os.environ.get("AGENT_BOT_USERNAME")
    )
    actual_username = normalise_username(user.get("username"))
    return bool(expected_username and actual_username and expected_username == actual_username)
