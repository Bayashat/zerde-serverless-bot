"""Shared utility helpers."""

from core.translations import get_translated_text


def format_mention(user_id: int, username: str | None, first_name: str = "User") -> str:
    """Build a Telegram user mention (prefers @username when available)."""
    if username:
        return f"@{username}"
    return f'<a href="tg://user?id={user_id}">{first_name}</a>'


def check_membership(ctx) -> bool:
    member = ctx.bot.get_chat_member(ctx.chat_id, ctx.user_id)
    if (
        member.get("status") not in ("member", "restricted", "administrator", "creator")
        or member.get("is_member") is False
    ):
        if ctx.callback_query_id:
            ctx.bot.answer_callback_query(
                ctx.callback_query_id,
                text=get_translated_text("not_in_group"),
                show_alert=True,
            )
        return False
    return True
