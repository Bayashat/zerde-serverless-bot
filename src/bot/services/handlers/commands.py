"""Simple bot commands: /start, /help, /support, /ping, /stats, /genquiz."""

from core.config import ADMIN_USER_ID, QUIZ_LAMBDA_NAME, VALID_DIFFICULTIES, VALID_LANGS
from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text

logger = LoggerAdapter(get_logger(__name__), {})


def handle_start(ctx: Context) -> None:
    ctx.reply(get_translated_text("start_message", ctx.lang_code), ctx.message_id)


def handle_help(ctx: Context) -> None:
    ctx.reply(get_translated_text("help_message", ctx.lang_code), ctx.message_id)


def handle_support(ctx: Context) -> None:
    ctx.reply(
        get_translated_text("support_message", ctx.lang_code),
        ctx.message_id,
    )


def handle_ping(ctx: Context) -> None:
    ctx.reply("🏓 Pong! Serverless is fast.", ctx.message_id)


def handle_stats(ctx: Context) -> None:
    """Admin-only: reply with group statistics."""
    try:
        member = ctx.bot.get_chat_member(ctx.chat_id, ctx.user_id)
        status = (member.get("status") or "").lower()
        if status not in ("creator", "administrator"):
            ctx.reply(
                get_translated_text("stats_admin_only", ctx.lang_code),
                ctx.message_id,
            )
            return

        stats: dict = ctx.stats_repo.get_stats(ctx.chat_id)
        total = stats["total_joins"]
        verified = stats["verified_users"]
        banned = stats["total_bans"]
        start_date = stats["started_at"]

        activity_level_percentage = int(min(100, 100 * verified / max(1, total)))
        if activity_level_percentage < 30:
            level_key = "activity_low"
        elif activity_level_percentage < 70:
            level_key = "activity_medium"
        else:
            level_key = "activity_high"

        activity_level = get_translated_text(level_key, ctx.lang_code)
        msg = get_translated_text(
            "stats_message",
            ctx.lang_code,
            start_date=start_date,
            total=total,
            verified=verified,
            banned=banned,
            activity_level=activity_level,
        )
        ctx.reply(msg, ctx.message_id)
    except Exception as e:
        logger.exception(f"handle_stats error: {e}")
        ctx.reply(
            get_translated_text("stats_error", ctx.lang_code),
            ctx.message_id,
        )


def handle_quiz_generate(ctx: Context) -> None:
    """Admin-only: generate and send an on-demand quiz poll to the current chat.

    Usage: /genquiz <topic> <lang> <difficulty>
    Example: /genquiz backend kk hard
    """
    if ctx.user_id != ADMIN_USER_ID:
        return

    if not QUIZ_LAMBDA_NAME or not ctx.lambda_invoker:
        ctx.reply(get_translated_text("genquiz_lambda_not_configured", ctx.lang_code), ctx.message_id)
        return

    parts = ctx.text.split()
    if len(parts) != 4:
        ctx.reply(get_translated_text("genquiz_usage", ctx.lang_code), ctx.message_id)
        return

    _, topic, lang, difficulty = parts

    if lang not in VALID_LANGS:
        langs_str = ", ".join(sorted(VALID_LANGS))
        ctx.reply(get_translated_text("genquiz_invalid_lang", ctx.lang_code, langs=langs_str), ctx.message_id)
        return

    if difficulty not in VALID_DIFFICULTIES:
        diffs_str = ", ".join(sorted(VALID_DIFFICULTIES))
        ctx.reply(
            get_translated_text("genquiz_invalid_difficulty", ctx.lang_code, difficulties=diffs_str), ctx.message_id
        )
        return

    logger.info(
        "Invoking quiz lambda on-demand",
        extra={"topic": topic, "lang": lang, "difficulty": difficulty, "chat_id": ctx.chat_id},
    )

    result = ctx.lambda_invoker.invoke(
        QUIZ_LAMBDA_NAME,
        {
            "action": "on_demand",
            "chat_id": str(ctx.chat_id),
            "topic": topic,
            "lang": lang,
            "difficulty": difficulty,
        },
    )

    if result.get("status") != "ok":
        reason = result.get("reason", "unknown error")
        ctx.reply(get_translated_text("genquiz_failed", ctx.lang_code, reason=reason), ctx.message_id)
        logger.error("On-demand quiz failed", extra={"result": result})
