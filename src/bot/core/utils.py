"""Shared utility helpers."""

from html import escape

from core.config import get_chat_lang
from core.translations import get_translated_text


def format_mention(
    user_id: int,
    username: str | None,
    first_name: str = "User",
    last_name: str | None = None,
) -> str:
    """Build a Telegram user mention (prefers @username when available)."""
    if username:
        return f"@{escape(username)}"
    display_name = " ".join(part for part in [first_name, last_name] if part).strip() or "User"
    return f'<a href="tg://user?id={user_id}">{escape(display_name)}</a>'


def check_membership(ctx) -> bool:
    member = ctx.bot.get_chat_member(ctx.chat_id, ctx.user_id)
    if (
        member.get("status") not in ("member", "restricted", "administrator", "creator")
        or member.get("is_member") is False
    ):
        if ctx.callback_query_id:
            ctx.bot.answer_callback_query(
                ctx.callback_query_id,
                text=get_translated_text("not_in_group", get_chat_lang(ctx.chat_id)),
                show_alert=True,
            )
        return False
    return True
