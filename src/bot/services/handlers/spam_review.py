"""Admin callbacks for low-confidence spam review alerts."""

import re
import time

from core.config import SPAM_REVIEW_BAN_PREFIX, SPAM_REVIEW_IGNORE_PREFIX
from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.repositories.spam import SpamRepository
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

    try:
        repo = SpamRepository()
        action, case = _resolve_case(repo, ctx)
    except Exception as exc:
        logger.warning("Spam review lookup failed", extra={"error_type": type(exc).__name__})
        _answer_failure(ctx)
        return
    if not action or not case or str(case["chat_id"]) != str(ctx.chat_id):
        ctx.bot.answer_callback_query(ctx.callback_query_id, text=get_translated_text("unknown_action", ctx.lang_code))
        return

    owner = None
    try:
        owner, case = repo.claim(case["case_id"])
        if case["state"] not in {"clean", "blocked", "ignored"}:
            # A lease is temporary; the administrator's selected action must survive
            # a crash between Telegram success and the decision's terminal write.
            if case.get("selected_action") and case["selected_action"] != action:
                _answer_failure(ctx)
                return
            if not case.get("selected_action"):
                repo.update(case["case_id"], owner, {"selected_action": action})
            if action == "ban":
                target = int(case.get("review_target_user_id") or case["user_id"])
                result = SpamEnforcer(ctx.bot, repo).enforce(
                    chat_id=ctx.chat_id,
                    user_id=target,
                    message_id=int(case["message_id"]),
                    reason="admin_review",
                    permanent=True,
                    retry_failed=True,
                )
                if not result.banned:
                    repo.update(case["case_id"], owner, {"enforcement_error": result.reason})
                    _answer_failure(ctx)
                    return
                repo.update(case["case_id"], owner, {"state": "blocked", "ban_confirmed": True})
                case = {**case, "state": "blocked", "ban_confirmed": True}
            elif case.get("guest_bot"):
                repo.update(case["case_id"], owner, {"state": "ignored"})
                case = {**case, "state": "ignored"}
            else:
                repo.finish_clean(case, owner, reviewed=True)
                case = {**case, "state": "clean"}
        if case.get("ban_confirmed"):
            ctx.bot.answer_callback_query(
                ctx.callback_query_id, text=get_translated_text("spam_review_banned_toast", ctx.lang_code)
            )
            _replace_review_alert(ctx, get_translated_text("spam_review_banned_notice", ctx.lang_code))
        elif case["state"] in {"clean", "ignored"}:
            ctx.bot.answer_callback_query(
                ctx.callback_query_id, text=get_translated_text("spam_review_ignored_toast", ctx.lang_code)
            )
            _delete_review_alert(ctx)
        else:
            _answer_failure(ctx)
    except Exception as exc:
        logger.warning("Spam review not completed; administrator can retry", extra={"error_type": type(exc).__name__})
        _answer_failure(ctx)
    finally:
        if owner:
            repo.release(case["case_id"], owner)


def _answer_failure(ctx: Context) -> None:
    ctx.bot.answer_callback_query(
        ctx.callback_query_id,
        text=get_translated_text("spam_review_action_failed", ctx.lang_code),
        show_alert=True,
    )


def _resolve_case(repo: SpamRepository, ctx: Context) -> tuple[str | None, dict]:
    for action, prefix in (("ban", SPAM_REVIEW_BAN_PREFIX), ("ignore", SPAM_REVIEW_IGNORE_PREFIX)):
        if ctx.callback_data.startswith(prefix):
            raw = ctx.callback_data.removeprefix(prefix)
            if re.fullmatch(r"[0-9a-f]{32}", raw):
                case = repo.get("decision#" + raw)
                if case.get("ttl") and int(case["ttl"]) <= int(time.time()):
                    return None, {}
                return action, case
    # Previously sent alerts carry IDs. They remain reviewable but cannot learn.
    action, target_user_id, target_message_id = _parse_callback_data(ctx.callback_data)
    if not action or target_user_id <= 0 or target_message_id <= 0:
        return None, {}
    return action, repo.ensure_case(
        {
            "chat_id": ctx.chat_id,
            "user_id": target_user_id,
            "message_id": target_message_id,
            "text": "legacy admin review",
        }
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


def _delete_review_alert(ctx: Context) -> None:
    try:
        ctx.bot.delete_message(ctx.chat_id, ctx.message_id, ignore_not_found=True)
    except Exception as e:
        logger.warning(
            "Failed to delete spam review alert",
            extra={"chat_id": ctx.chat_id, "message_id": ctx.message_id, "error": e},
        )
