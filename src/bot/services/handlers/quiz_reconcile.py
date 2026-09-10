"""A live group administrator may attach an already delivered own-bot poll."""

import re

from core.config import QUIZ_LAMBDA_NAME, is_configured_group_chat
from core.translations import get_translated_text


def handle_quiz_reconcile(ctx):
    usage = get_translated_text("quiz_reconcile_usage", ctx.lang_code)
    parts = ctx.text.split()
    if len(parts) != 3 or not ctx.chat_id or not is_configured_group_chat(ctx.chat_id):
        ctx.reply(usage, ctx.message_id)
        return
    key, generation = parts[1:]
    if len(key) > 200 or not re.fullmatch(r"[A-Za-z0-9_:#-]+", key) or not re.fullmatch(r"[a-f0-9]{32}", generation):
        ctx.reply(usage, ctx.message_id)
        return
    member = ctx.bot.get_chat_member(ctx.chat_id, ctx.user_id)
    if str((member.get("user") or {}).get("id")) != str(ctx.user_id) or member.get("status") not in {
        "administrator",
        "creator",
    }:
        ctx.reply(get_translated_text("quiz_reconcile_admin", ctx.lang_code), ctx.message_id)
        return
    reply = ctx.reply_to_message or {}
    bot_id = ctx.bot.get_me().get("id")
    if (
        not isinstance(bot_id, int)
        or not reply.get("poll")
        or (reply.get("from") or {}).get("id") != bot_id
        or str((reply.get("chat") or {}).get("id")) != str(ctx.chat_id)
        or not QUIZ_LAMBDA_NAME
        or ctx.lambda_invoker is None
    ):
        ctx.reply(usage, ctx.message_id)
        return
    # No arbitrary event/action forwarding: the authenticated adapter constructs this envelope.
    result = ctx.lambda_invoker.invoke(
        QUIZ_LAMBDA_NAME,
        {
            "action": "reconcile",
            "chat_id": str(ctx.chat_id),
            "request_key": key,
            "generation": generation,
            "poll_message": reply,
            "bot_user_id": bot_id,
        },
    )
    state = result.get("status") if isinstance(result, dict) else None
    key = "quiz_reconcile_ok" if state == "ok" else "quiz_reconcile_unknown"
    ctx.reply(get_translated_text(key, ctx.lang_code), ctx.message_id)
