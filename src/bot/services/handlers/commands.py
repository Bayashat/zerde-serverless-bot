"""Simple bot commands: /start, /help, /support, /ping, /stats, /genquiz."""

from core.config import (
    ADMIN_USER_ID,
    AGENT_ENABLED,
    GROUP_MEMORY_ENABLED,
    QUIZ_LAMBDA_NAME,
    VALID_DIFFICULTIES,
    VALID_LANGS,
    get_chat_lang,
)
from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.group_agent import answer_group_question
from services.handlers.quiz import react_genquiz_processing

logger = LoggerAdapter(get_logger(__name__), {})


def _is_admin_user(ctx: Context) -> bool:
    return ctx.user_id == ADMIN_USER_ID


def _chat_member_status(ctx: Context) -> str:
    try:
        member = ctx.bot.get_chat_member(ctx.chat_id, ctx.user_id)
        return (member.get("status") or "").lower()
    except Exception:
        logger.exception("Failed to verify chat member status", extra={"chat_id": ctx.chat_id, "user_id": ctx.user_id})
        return ""


def _is_chat_admin(ctx: Context) -> bool:
    return _is_admin_user(ctx) or _chat_member_status(ctx) in ("creator", "administrator")


def _is_chat_owner_or_admin_user(ctx: Context) -> bool:
    return _is_admin_user(ctx) or _chat_member_status(ctx) == "creator"


def _require_chat_admin(ctx: Context) -> bool:
    if _is_chat_admin(ctx):
        return True
    ctx.reply(get_translated_text("stats_admin_only", ctx.lang_code), ctx.message_id)
    return False


def _require_chat_owner_or_admin_user(ctx: Context) -> bool:
    if _is_chat_owner_or_admin_user(ctx):
        return True
    ctx.reply("Only the group owner or bot owner can change group memory settings.", ctx.message_id)
    return False


def _require_admin_user(ctx: Context) -> bool:
    if _is_admin_user(ctx):
        return True
    ctx.reply("Only the bot owner can do that.", ctx.message_id)
    return False


def _require_memory_repo(ctx: Context) -> bool:
    if ctx.memory_repo:
        return True
    ctx.reply("Group memory storage is not configured for this deployment.", ctx.message_id)
    return False


def _parse_genquiz_args(text: str, chat_id: int | str) -> tuple[str, str, str] | None:
    """Parse ``/genquiz`` args: ``topic`` [, ``difficulty`` [, ``lang``]].

    Order is fixed: topic (words), then optional difficulty, then optional lang.
    Defaults: difficulty ``medium``, lang from ``CHAT_LANG_MAP`` / ``DEFAULT_LANG``.
    """
    parts = text.split()
    if len(parts) < 2:
        return None
    tokens = parts[1:]
    if len(tokens) == 1:
        return (tokens[0], "medium", get_chat_lang(chat_id))

    lang: str | None = None
    difficulty: str | None = None

    if tokens[-1] in VALID_LANGS:
        lang = tokens.pop()

    if len(tokens) >= 2 and tokens[-1] in VALID_DIFFICULTIES:
        difficulty = tokens.pop()

    topic = " ".join(tokens).strip()
    if not topic:
        return None

    return (
        topic,
        difficulty or "medium",
        lang or get_chat_lang(chat_id),
    )


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
        if not _require_chat_admin(ctx):
            return

        stats: dict = ctx.stats_repo.get_stats(ctx.chat_id)
        total = stats["total_joins"]
        verified = stats["verified_users"]
        banned = stats["total_bans"]
        spam_banned = stats["spam_bans"]
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
            spam_banned=spam_banned,
            activity_level=activity_level,
        )
        ctx.reply(msg, ctx.message_id)
    except Exception as e:
        logger.exception(f"handle_stats error: {e}")
        ctx.reply(
            get_translated_text("stats_error", ctx.lang_code),
            ctx.message_id,
        )


def handle_memory_on(ctx: Context) -> None:
    if not _require_memory_repo(ctx):
        return
    if not GROUP_MEMORY_ENABLED:
        ctx.reply("Group memory is disabled by deployment config.", ctx.message_id)
        return
    if not _require_chat_owner_or_admin_user(ctx):
        return
    ctx.memory_repo.set_chat_settings(ctx.chat_id, memory_enabled=True)
    ctx.reply("Group memory is now on. I will remember recent non-command messages for context.", ctx.message_id)


def handle_memory_off(ctx: Context) -> None:
    if not _require_memory_repo(ctx):
        return
    if not _require_chat_owner_or_admin_user(ctx):
        return
    ctx.memory_repo.set_chat_settings(ctx.chat_id, memory_enabled=False, agent_enabled=False)
    ctx.reply("Group memory is now off. Existing stored memory is kept until TTL or /forget_group.", ctx.message_id)


def handle_agent_on(ctx: Context) -> None:
    if not _require_memory_repo(ctx):
        return
    if not AGENT_ENABLED:
        ctx.reply("The group agent is disabled by deployment config.", ctx.message_id)
        return
    if not _require_chat_owner_or_admin_user(ctx):
        return
    ctx.memory_repo.set_chat_settings(ctx.chat_id, memory_enabled=True, agent_enabled=True)
    ctx.reply("Group agent is now on. I will answer when mentioned or replied to.", ctx.message_id)


def handle_agent_off(ctx: Context) -> None:
    if not _require_memory_repo(ctx):
        return
    if not _require_chat_owner_or_admin_user(ctx):
        return
    ctx.memory_repo.set_chat_settings(ctx.chat_id, agent_enabled=False)
    ctx.reply("Group agent is now off. Memory can remain on for commands and future context.", ctx.message_id)


def handle_memory_status(ctx: Context) -> None:
    if not _require_memory_repo(ctx):
        return
    if not _require_chat_admin(ctx):
        return
    settings = ctx.memory_repo.get_chat_settings(ctx.chat_id)
    memory = "on" if settings["memory_enabled"] else "off"
    agent = "on" if settings["agent_enabled"] else "off"
    ctx.reply(f"Group memory: {memory}\nGroup agent: {agent}", ctx.message_id)


def handle_ask(ctx: Context) -> None:
    if not _require_memory_repo(ctx):
        return
    parts = ctx.text.split(maxsplit=1)
    question = parts[1].strip() if len(parts) > 1 else ""
    if not question and ctx.reply_to_message:
        question = (ctx.reply_to_message.get("text") or ctx.reply_to_message.get("caption") or "").strip()
    if not question:
        ctx.reply("Usage: /ask question or reply to a message with /ask", ctx.message_id)
        return
    if not ctx.memory_repo.is_memory_enabled(ctx.chat_id):
        ctx.reply("Group memory is off. Ask an admin to run /memory_on first.", ctx.message_id)
        return
    handled = answer_group_question(
        repo=ctx.memory_repo,
        bot=ctx.bot,
        chat_id=ctx.chat_id,
        reply_to_message_id=ctx.message_id,
        user_text=question,
        lang=ctx.lang_code,
    )
    if not handled:
        ctx.reply("AI agent is not available right now.", ctx.message_id)


def handle_forget_group(ctx: Context) -> None:
    if not _require_memory_repo(ctx):
        return
    if not _require_admin_user(ctx):
        return
    deleted = ctx.memory_repo.delete_chat_memory(ctx.chat_id)
    ctx.reply(f"Deleted {deleted} memory items for this group.", ctx.message_id)


def handle_quiz_generate(ctx: Context) -> None:
    """Generate and send an on-demand quiz poll to the current chat (open to all users).

    Usage: ``/genquiz <topic>`` [, ``<difficulty>`` [, ``<lang>``]] — fixed order;
    omitted difficulty defaults to ``medium``, omitted lang to this chat's default.
    """
    if not QUIZ_LAMBDA_NAME or not ctx.lambda_invoker:
        react_genquiz_processing(ctx, "🤡")
        ctx.reply(get_translated_text("genquiz_lambda_not_configured", ctx.lang_code), ctx.message_id)
        return

    parsed = _parse_genquiz_args(ctx.text, ctx.chat_id)
    if parsed is None:
        react_genquiz_processing(ctx, "🤡")
        ctx.reply(get_translated_text("genquiz_usage", ctx.lang_code), ctx.message_id)
        return

    topic, difficulty, lang = parsed

    if lang not in VALID_LANGS:
        react_genquiz_processing(ctx, "🤡")
        langs_str = ", ".join(sorted(VALID_LANGS))
        ctx.reply(get_translated_text("genquiz_invalid_lang", ctx.lang_code, langs=langs_str), ctx.message_id)
        return

    if difficulty not in VALID_DIFFICULTIES:
        diffs_str = ", ".join(sorted(VALID_DIFFICULTIES))
        ctx.reply(
            get_translated_text("genquiz_invalid_difficulty", ctx.lang_code, difficulties=diffs_str), ctx.message_id
        )
        return

    react_genquiz_processing(ctx)

    logger.info(
        "Invoking quiz lambda on-demand",
        extra={"topic": topic, "lang": lang, "difficulty": difficulty, "chat_id": ctx.chat_id},
    )

    accepted = ctx.lambda_invoker.invoke_async(
        QUIZ_LAMBDA_NAME,
        {
            "action": "on_demand",
            "chat_id": str(ctx.chat_id),
            "topic": topic,
            "lang": lang,
            "difficulty": difficulty,
            "reply_to_message_id": ctx.message_id,
        },
    )
    if not accepted:
        msg = get_translated_text("genquiz_failed", ctx.lang_code, reason="failed to start generation")
        ctx.reply(msg, ctx.message_id)
        return
