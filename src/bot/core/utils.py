"""Shared utility helpers."""


def format_mention(user_id: int, username: str | None, first_name: str = "User") -> str:
    """Build a Telegram user mention (prefers @username when available)."""
    if username:
        return f"@{username}"
    return f'<a href="tg://user?id={user_id}">{first_name}</a>'
