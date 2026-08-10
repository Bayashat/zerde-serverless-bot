"""Owner/admin command boundary for Telegram contests."""

from __future__ import annotations

from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from services.contest import (
    ADMIN_ONLY_KK,
    CONTEST_ERROR_KK,
    ORPHANED_KK,
    OWNER_ONLY_KK,
    PERSONAL_ACCOUNT_REQUIRED_KK,
    REPLY_ANCHOR_REQUIRED_KK,
    UNKNOWN_SUBCOMMAND_KK,
    AnnouncementOrphanedError,
    ContestRetryRequiredError,
    ContestService,
)

logger = LoggerAdapter(get_logger(__name__), {})

_OWNER_COMMANDS = {"draw", "redraw", "cancel"}
_ALL_COMMANDS = {*_OWNER_COMMANDS, "status"}


def _subcommand(text: str) -> str:
    parts = text.split(maxsplit=1)
    return parts[1].strip().casefold() if len(parts) == 2 else ""


def _reply(ctx: Context, text: str) -> None:
    ctx.reply(text, ctx.message_id)


def handle_contest(ctx: Context) -> None:
    """Handle ``/contest draw|redraw|status|cancel`` in fixed Kazakh."""
    if ctx.user_id is None or ctx.user_data.get("is_bot") is True or bool(ctx.message.get("sender_chat")):
        _reply(ctx, PERSONAL_ACCOUNT_REQUIRED_KK)
        return

    action = _subcommand(ctx.text)
    if action not in _ALL_COMMANDS:
        _reply(ctx, UNKNOWN_SUBCOMMAND_KK)
        return
    if ctx.contest_repo is None:
        _reply(ctx, CONTEST_ERROR_KK)
        return

    reply = ctx.reply_to_message
    anchor_message_id = reply.get("message_id") if isinstance(reply, dict) else None
    if not isinstance(anchor_message_id, int) or ctx.chat_id is None or ctx.message_id is None:
        _reply(ctx, REPLY_ANCHOR_REQUIRED_KK)
        return
    try:
        contest = ctx.contest_repo.resolve_contest_by_anchor(ctx.chat_id, anchor_message_id)
    except Exception as exc:
        logger.exception(
            "Failed to resolve contest command anchor",
            extra={"chat_id": ctx.chat_id, "anchor_message_id": anchor_message_id},
        )
        raise ContestRetryRequiredError("Contest anchor lookup requires retry") from exc
    if not contest:
        _reply(ctx, REPLY_ANCHOR_REQUIRED_KK)
        return

    try:
        member = ctx.bot.get_chat_member(ctx.chat_id, int(ctx.user_id))
        member_status = str(member.get("status") or "").casefold()
    except Exception:
        logger.exception(
            "Failed to verify contest command authorization",
            extra={"chat_id": ctx.chat_id, "user_id": ctx.user_id, "action": action},
        )
        _reply(ctx, ADMIN_ONLY_KK if action == "status" else OWNER_ONLY_KK)
        return

    if action == "status":
        if member_status not in {"creator", "administrator"}:
            _reply(ctx, ADMIN_ONLY_KK)
            return
    elif member_status != "creator":
        _reply(ctx, OWNER_ONLY_KK)
        return

    root_message_id = int(contest["root_message_id"])
    service = ContestService(ctx.contest_repo, ctx.bot, ctx.sqs_repo)
    try:
        if action == "draw":
            service.draw(
                chat_id=ctx.chat_id,
                root_message_id=root_message_id,
                command_message_id=ctx.message_id,
            )
        elif action == "redraw":
            service.draw(
                chat_id=ctx.chat_id,
                root_message_id=root_message_id,
                command_message_id=ctx.message_id,
                redraw=True,
            )
        elif action == "cancel":
            service.cancel(
                chat_id=ctx.chat_id,
                root_message_id=root_message_id,
                command_message_id=ctx.message_id,
            )
        else:
            service.status(
                chat_id=ctx.chat_id,
                root_message_id=root_message_id,
                command_message_id=ctx.message_id,
            )
    except AnnouncementOrphanedError:
        _reply(ctx, ORPHANED_KK)
    except ContestRetryRequiredError:
        # Let the webhook return 5xx so Telegram redelivers the exact command.
        raise
    except Exception:
        logger.exception(
            "Contest command failed",
            extra={"chat_id": ctx.chat_id, "root_message_id": root_message_id, "action": action},
        )
        _reply(ctx, CONTEST_ERROR_KK)
