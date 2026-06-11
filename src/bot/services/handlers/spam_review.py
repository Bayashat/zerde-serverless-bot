"""Admin callbacks for low-confidence spam review alerts."""

from core.config import SPAM_REVIEW_BAN_PREFIX, SPAM_REVIEW_IGNORE_PREFIX
from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.repositories.stats import StatsRepository
from services.spam.chat_member import is_chat_admin_or_creator
from services.spam.enforcer import SpamEnforcer

logger = LoggerAdapter(get_logger(__name__), {})


def handle_spam_review_callback(ctx: Context) -> None:
    """Let admins act on low-confidence spam alerts from inline buttons."""
    if not _is_admin(ctx):
        ctx.bot.answer_callback_query(
            ctx.callback_query_id,
            text=get_translated_text("spam_review_admin_only", ctx.lang_code),
            show_alert=True,
        )
        return

    action, target_user_id, target_message_id = _parse_callback_data(ctx.callback_data)
    if not action:
        ctx.bot.answer_callback_query(ctx.callback_query_id, text=get_translated_text("unknown_action", ctx.lang_code))
        return

    if action == "ban":
        stats_repo = ctx.stats_repo or StatsRepository()
        SpamEnforcer(ctx.bot, stats_repo).enforce(
            chat_id=ctx.chat_id,
            user_id=target_user_id,
            message_id=target_message_id,
            reason="admin_review",
        )
        ctx.bot.answer_callback_query(
            ctx.callback_query_id,
            text=get_translated_text("spam_review_banned_toast", ctx.lang_code),
        )
        _replace_review_alert(ctx, get_translated_text("spam_review_banned_notice", ctx.lang_code))
        logger.info(
            "Admin confirmed spam review ban",
            extra={"chat_id": ctx.chat_id, "admin_user_id": ctx.user_id, "target_user_id": target_user_id},
        )
        return

    ctx.bot.answer_callback_query(
        ctx.callback_query_id,
        text=get_translated_text("spam_review_ignored_toast", ctx.lang_code),
    )
    _replace_review_alert(ctx, get_translated_text("spam_review_ignored_notice", ctx.lang_code))
    logger.info(
        "Admin ignored spam review alert",
        extra={"chat_id": ctx.chat_id, "admin_user_id": ctx.user_id, "target_user_id": target_user_id},
    )


def is_spam_review_callback(callback_data: str) -> bool:
    return callback_data.startswith((SPAM_REVIEW_BAN_PREFIX, SPAM_REVIEW_IGNORE_PREFIX))


def _is_admin(ctx: Context) -> bool:
    if not ctx.chat_id or not ctx.user_id:
        return False
    return is_chat_admin_or_creator(ctx.bot, ctx.chat_id, ctx.user_id)


def _parse_callback_data(callback_data: str) -> tuple[str | None, int, int]:
    if callback_data.startswith(SPAM_REVIEW_BAN_PREFIX):
        action = "ban"
        raw = callback_data.removeprefix(SPAM_REVIEW_BAN_PREFIX)
    elif callback_data.startswith(SPAM_REVIEW_IGNORE_PREFIX):
        action = "ignore"
        raw = callback_data.removeprefix(SPAM_REVIEW_IGNORE_PREFIX)
    else:
        return None, 0, 0

    try:
        target_user_id, target_message_id = raw.split(":", maxsplit=1)
        return action, int(target_user_id), int(target_message_id)
    except (TypeError, ValueError):
        return None, 0, 0


def _replace_review_alert(ctx: Context, text: str) -> None:
    try:
        ctx.bot.edit_message_text(ctx.chat_id, ctx.message_id, text)
    except Exception as e:
        logger.warning(
            "Failed to replace spam review alert",
            extra={"chat_id": ctx.chat_id, "message_id": ctx.message_id, "error": e},
        )
