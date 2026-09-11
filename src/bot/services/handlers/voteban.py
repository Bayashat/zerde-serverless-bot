"""Generation-bound votes; database decisions precede recoverable Telegram effects."""

import json
import re
import time
from typing import Any

from core.config import (
    KICK_BAN_DURATION_SECONDS,
    VOTEBAN_AGAINST_PREFIX,
    VOTEBAN_FOR_PREFIX,
    VOTEBAN_FORGIVE_THRESHOLD,
    VOTEBAN_THRESHOLD,
)
from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from core.utils import format_mention
from services.repositories.votes import VoteBusyError, VoteSessionError
from services.telegram import TelegramAPIError

logger = LoggerAdapter(get_logger(__name__), {})


def _format_voter_list(voter_info_list: list[dict[str, Any]]) -> str:
    return (
        ", ".join(
            format_mention(v["id"], v.get("username") or None, v.get("first_name") or "User") for v in voter_info_list
        )
        or "—"
    )


def _mention(session, role):
    return format_mention(
        int(session[f"{role}_user_id"]),
        session.get(f"{role}_username") or None,
        session.get(f"{role}_first_name") or "User",
    )


def _text(ctx, session):
    return get_translated_text(
        "voteban_initiated", ctx.lang_code, INITIATOR=_mention(session, "initiator"), TARGET=_mention(session, "target")
    )


def _vote_keyboard(session):
    suffix = f'{session["target_user_id"]}:{session["generation"]}'
    return {
        "inline_keyboard": [
            [
                {
                    "text": f'🔫 Ban ({len(session["votes_for"])}/{VOTEBAN_THRESHOLD})',
                    "callback_data": VOTEBAN_FOR_PREFIX + suffix,
                },
                {
                    "text": f'👼 Forgive ({len(session["votes_against"])}/{VOTEBAN_FORGIVE_THRESHOLD})',
                    "callback_data": VOTEBAN_AGAINST_PREFIX + suffix,
                },
            ]
        ]
    }


def _message_id(result):
    value = result.get("message_id") if isinstance(result, dict) else None
    if type(value) is not int or value <= 0:
        raise RuntimeError("Telegram did not confirm a message identity")
    return value


def handle_voteban_command(ctx: Context) -> None:
    """Repeated commands resume the existing generation, including pending outcomes."""
    try:
        target = (ctx.reply_to_message or {}).get("from") or {}
        target_id = target.get("id")
        if type(target_id) is not int or target_id <= 0:
            ctx.reply(get_translated_text("voteban_usage", ctx.lang_code), ctx.message_id)
            return
        if target_id == ctx.user_id:
            ctx.reply(get_translated_text("voteban_self", ctx.lang_code), ctx.message_id)
            return
        old = ctx.vote_repo.get_vote_session(ctx.chat_id, target_id)
        recovering = old.get("status") in {"BAN_PENDING", "FORGIVE_PENDING", "BANNED", "FORGIVEN", "UNCONFIRMED"}
        if not recovering or old.get("effects_complete"):
            status = ctx.bot.get_chat_member(ctx.chat_id, target_id).get("status")
            if status in {"creator", "administrator"}:
                ctx.reply(get_translated_text("voteban_admin", ctx.lang_code), ctx.message_id)
                return
            if status not in {"member", "restricted", "left", "kicked"}:
                raise RuntimeError("Target membership is unknown")
        session = ctx.vote_repo.create_vote_session(
            chat_id=ctx.chat_id,
            chat_type=ctx.message.get("chat", {}).get("type", ""),
            target_user_id=target_id,
            command_message_id=ctx.message_id,
            command_date=int(ctx.message.get("date", 0)),
            reply_message_id=ctx.reply_to_message["message_id"],
            initiator_user_id=ctx.user_id,
            initiator_username=ctx.username,
            initiator_first_name=ctx.first_name,
            target_username=target.get("username"),
            target_first_name=target.get("first_name") or "User",
        )
        _resume(ctx, session)
    except VoteSessionError:
        ctx.reply(get_translated_text("voteban_expired", ctx.lang_code), ctx.message_id)
    except Exception as exc:
        logger.warning("Vote command could not finish", extra={"error_type": type(exc).__name__})
        ctx.reply(get_translated_text("voteban_retry", ctx.lang_code), ctx.message_id)


def handle_vote_callback(ctx: Context) -> None:
    """Reject legacy, forged and stale buttons before any write or Telegram effect."""
    try:
        match = re.fullmatch(r"(voteban_for_|voteban_against_)([1-9][0-9]*):([a-f0-9]{16})", ctx.callback_data)
        if not match:
            raise VoteSessionError("Unversioned or malformed vote button")
        session, verdict = ctx.vote_repo.add_vote(
            ctx.chat_id,
            int(match[2]),
            ctx.user_id,
            match[1] == VOTEBAN_FOR_PREFIX,
            generation=match[3],
            sent_message_id=ctx.message_id,
            for_threshold=VOTEBAN_THRESHOLD,
            against_threshold=VOTEBAN_FORGIVE_THRESHOLD,
            voter_username=ctx.username,
            voter_first_name=ctx.first_name,
        )
        _resume(ctx, session)  # An already-recorded vote can still recover an unfinished decision.
        key = {
            "already_voted": "voteban_already_voted",
            "pending": "voteban_closed",
            "recorded": "voteban_vote_recorded",
        }[verdict]
    except VoteSessionError:
        key = "voteban_expired"
    except Exception as exc:
        logger.warning("Vote callback could not finish", extra={"error_type": type(exc).__name__})
        key = "voteban_retry"
    ctx.bot.answer_callback_query(
        ctx.callback_query_id, text=get_translated_text(key, ctx.lang_code), show_alert=key != "voteban_vote_recorded"
    )


def _resume(ctx, session):
    if session.get("effects_complete"):
        return
    owner, session = ctx.vote_repo.claim(session["chat_id"], session["target_user_id"], session["generation"])
    try:
        if session["status"] == "CREATING":
            if int(session["expires_at"]) <= int(time.time()):
                raise VoteSessionError("Unpublished vote expired")
            # A lost response or failed binding leaves only an inert message, never a live orphan keyboard.
            sent_id = _message_id(
                ctx.bot.send_message(
                    session["chat_id"], _text(ctx, session), reply_to_message_id=int(session["reply_message_id"])
                )
            )
            ctx.vote_repo.bind_message(session, owner, sent_id, for_threshold=VOTEBAN_THRESHOLD)
        # One effects lease serializes keyboard edits and terminal cleanup. Votes use independent revision CAS.
        for _ in range(3):
            session = ctx.vote_repo.get_vote_session(session["chat_id"], session["target_user_id"])
            if session["status"] != "OPEN":
                _finish(ctx, session, owner)
                return
            if int(session["expires_at"]) <= int(time.time()):
                raise VoteSessionError("Vote expired")
            _render(ctx, session)
            latest = ctx.vote_repo.get_vote_session(session["chat_id"], session["target_user_id"])
            if latest["status"] == "OPEN" and latest["revision"] == session["revision"]:
                return
        # Persisted votes/decision remain retryable if traffic keeps changing during this bounded render pass.
        raise VoteBusyError("Votes changed during rendering; retry to resume")
    finally:
        ctx.vote_repo.release(session, owner)


def _render(ctx, session):
    try:
        result = ctx.bot.edit_message_text(
            session["chat_id"],
            int(session["sent_message_id"]),
            _text(ctx, session),
            reply_markup=_vote_keyboard(session),
        )
        if _message_id(result) != int(session["sent_message_id"]):
            raise RuntimeError("Telegram edited an unexpected message")
    except TelegramAPIError as exc:
        # Replaying the same render is success only for Telegram's specific structured error.
        try:
            description = json.loads(exc.body).get("description", "")
        except (ValueError, TypeError, AttributeError):
            description = ""
        if exc.status != 400 or not description.startswith("Bad Request: message is not modified"):
            raise


def _save(ctx, session, owner, **fields):
    ctx.vote_repo.update_effects(session, owner, fields)
    session.update(fields)


def _finish(ctx, session, owner):
    if session["status"] == "FORGIVE_PENDING":
        _save(ctx, session, owner, status="FORGIVEN")
    elif session["status"] == "BAN_PENDING":
        _attempt_ban(ctx, session, owner)
    if session["status"] not in {"BANNED", "FORGIVEN", "UNCONFIRMED"}:
        raise VoteSessionError("Vote is not ready to finish")
    if not session.get("notice_message_id"):
        if session["status"] == "BANNED":
            text = get_translated_text(
                "voteban_banned",
                ctx.lang_code,
                TARGET=_mention(session, "target"),
                VOTES_FOR=len(session["votes_for"]),
                VOTERS_FOR=_format_voter_list(session["votes_for_info"]),
            )
        elif session["status"] == "FORGIVEN":
            text = get_translated_text(
                "voteban_forgiven",
                ctx.lang_code,
                TARGET=_mention(session, "target"),
                VOTES_AGAINST=len(session["votes_against"]),
                VOTERS_AGAINST=_format_voter_list(session["votes_against_info"]),
            )
        else:
            text = get_translated_text("voteban_unconfirmed", ctx.lang_code, TARGET=_mention(session, "target"))
        sent_id = _message_id(ctx.bot.send_message(session["chat_id"], text))
        _save(ctx, session, owner, notice_message_id=sent_id)
    # Only stored identities can be removed; never fall back to an incoming callback message.
    if not session.get("vote_deleted"):
        ctx.bot.delete_message(session["chat_id"], int(session["sent_message_id"]), ignore_not_found=True)
        _save(ctx, session, owner, vote_deleted=True)
    if session["status"] == "BANNED" and not session.get("target_deleted"):
        ctx.bot.delete_message(session["chat_id"], int(session["reply_message_id"]), ignore_not_found=True)
        _save(ctx, session, owner, target_deleted=True)
    ctx.vote_repo.complete_effects(session, owner)


def _attempt_ban(ctx, session, owner):
    if session.get("chat_type") != "supergroup":
        # Telegram ignores until_date in basic groups; this feature must remain a temporary ban.
        _save(ctx, session, owner, status="UNCONFIRMED", outcome_reason="temporary_ban_unsupported_chat")
        return
    now = int(time.time())
    deadline = int(session.get("ban_until", 0))
    if (deadline and deadline - now <= 40) or (not deadline and int(session["expires_at"]) <= now):
        _save(ctx, session, owner, status="UNCONFIRMED", outcome_reason="execution_window_expired")
        return
    member_status = ctx.bot.get_chat_member(session["chat_id"], int(session["target_user_id"])).get("status")
    if member_status in {"creator", "administrator", "kicked"}:
        # An existing ban, including an earlier lost response, does not prove this vote caused it.
        _save(ctx, session, owner, status="UNCONFIRMED", outcome_reason="membership_changed")
        return
    if member_status not in {"member", "restricted", "left"}:
        raise RuntimeError("Target membership is unknown")
    if not deadline:
        duration = max(60, KICK_BAN_DURATION_SECONDS)
        if duration > 365 * 86400:  # Telegram treats dates beyond 366 days as permanent.
            _save(ctx, session, owner, status="UNCONFIRMED", outcome_reason="unsafe_temporary_duration")
            return
        deadline = int(time.time()) + duration
        _save(ctx, session, owner, ban_until=deadline)
    if deadline - int(time.time()) <= 40:
        _save(ctx, session, owner, status="UNCONFIRMED", outcome_reason="execution_window_expired")
        return
    ctx.bot.kick_chat_member(session["chat_id"], int(session["target_user_id"]), until_date=deadline)
    # The adapter requires ok:true/result:true. A lost API/DB acknowledgement stays unconfirmed, not counted twice.
    ctx.vote_repo.confirm_ban(session, owner)
    session["status"] = "BANNED"
