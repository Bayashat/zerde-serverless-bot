"""Vote-to-ban: initiate votes and process for/against callbacks."""

from typing import Any

from core.config import (
    VOTEBAN_AGAINST_PREFIX,
    VOTEBAN_FOR_PREFIX,
    VOTEBAN_FORGIVE_THRESHOLD,
    VOTEBAN_THRESHOLD,
)
from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from core.utils import format_mention

logger = LoggerAdapter(get_logger(__name__), {})


def _format_voter_list(voter_info_list: list[dict[str, Any]]) -> str:
    """Format a list of voter info dicts into a comma-separated mention string."""
    mentions = [
        format_mention(
            v["id"],
            v.get("username") or None,
            v.get("first_name") or "User",
        )
        for v in voter_info_list
    ]
    return ", ".join(mentions) if mentions else "—"


def _vote_keyboard(target_user_id: int, votes_for: int, votes_against: int) -> dict:
    """Build the inline keyboard with current vote counts."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": f"🔫 Ban ({votes_for}/{VOTEBAN_THRESHOLD})",
                    "callback_data": f"{VOTEBAN_FOR_PREFIX}{target_user_id}",
                },
                {
                    "text": f"👼 Forgive ({votes_against}/{VOTEBAN_FORGIVE_THRESHOLD})",
                    "callback_data": f"{VOTEBAN_AGAINST_PREFIX}{target_user_id}",
                },
            ]
        ]
    }


def handle_voteban_command(ctx: Context) -> None:
    """Start a vote to ban a user (reply to their message)."""
    try:
        if not ctx.reply_to_message:
            ctx.reply(
                get_translated_text("voteban_usage", ctx.lang_code),
                ctx.message_id,
            )
            return

        target_user = ctx.reply_to_message.get("from", {})
        target_user_id = target_user.get("id")
        target_username = target_user.get("username")
        target_first_name = target_user.get("first_name", "User")

        if not target_user_id:
            ctx.reply(
                get_translated_text("voteban_usage", ctx.lang_code),
                ctx.message_id,
            )
            return

        if target_user_id == ctx.user_id:
            ctx.reply(
                get_translated_text("voteban_self", ctx.lang_code),
                ctx.message_id,
            )
            return

        member = ctx.bot.get_chat_member(ctx.chat_id, target_user_id)
        status = (member.get("status") or "").lower()
        if status in ("creator", "administrator"):
            ctx.reply(
                get_translated_text("voteban_admin", ctx.lang_code),
                ctx.message_id,
            )
            return

        target_mention = format_mention(target_user_id, target_username, target_first_name)
        initiator_mention = format_mention(ctx.user_id, ctx.username, ctx.first_name)

        reply_markup = _vote_keyboard(target_user_id, votes_for=1, votes_against=0)

        text = get_translated_text(
            "voteban_initiated",
            INITIATOR=initiator_mention,
            TARGET=target_mention,
        )

        sent_message = ctx.reply(
            text,
            reply_to_message_id=ctx.reply_to_message.get("message_id"),
            reply_markup=reply_markup,
        )

        if ctx.vote_repo and sent_message:
            sent_message_id = sent_message.get("message_id")
            logger.info(
                "Context reply to message id",
                extra={"reply_to_message_id": ctx.reply_to_message.get("message_id")},
            )
            if sent_message_id:
                ctx.vote_repo.create_vote_session(
                    chat_id=ctx.chat_id,
                    target_user_id=target_user_id,
                    reply_message_id=ctx.reply_to_message.get("message_id"),
                    sent_message_id=sent_message_id,
                    initiator_user_id=ctx.user_id,
                    initiator_username=ctx.username,
                    initiator_first_name=ctx.first_name,
                    target_username=target_username,
                    target_first_name=target_first_name,
                )
                logger.info(
                    "Vote session created",
                    extra={
                        "chat_id": ctx.chat_id,
                        "target_user_id": target_user_id,
                        "initiator_user_id": ctx.user_id,
                    },
                )
    except Exception as e:
        logger.exception(f"handle_voteban error: {e}")
        ctx.reply(
            get_translated_text("error_occurred", ctx.lang_code),
            ctx.message_id,
        )


def handle_vote_callback(ctx: Context) -> None:
    """Process a vote-for or vote-against callback."""
    vote_for = ctx.callback_data.startswith(VOTEBAN_FOR_PREFIX)
    prefix = VOTEBAN_FOR_PREFIX if vote_for else VOTEBAN_AGAINST_PREFIX

    target_user_id = int(ctx.callback_data[len(prefix) :].strip())

    result = ctx.vote_repo.add_vote(
        ctx.chat_id,
        target_user_id,
        ctx.user_id,
        vote_for,
        voter_username=ctx.username,
        voter_first_name=ctx.first_name,
    )

    if result["already_voted"]:
        ctx.bot.answer_callback_query(
            ctx.callback_query_id,
            text=get_translated_text("voteban_already_voted", ctx.lang_code),
            show_alert=True,
        )
        return

    ctx.bot.answer_callback_query(
        ctx.callback_query_id,
        text=get_translated_text("voteban_vote_recorded", ctx.lang_code),
    )

    votes_for = result["votes_for"]
    votes_against = result["votes_against"]

    if votes_for >= VOTEBAN_THRESHOLD:
        _finalize_ban(ctx, target_user_id, votes_for)
        return

    if votes_against >= VOTEBAN_FORGIVE_THRESHOLD:
        _finalize_forgive(ctx, target_user_id, votes_against)
        return

    _update_vote_message(ctx, target_user_id, votes_for, votes_against)


# ── Private helpers ──────────────────────────────────────────────────────────


def _finalize_ban(ctx: Context, target_user_id: int, votes_for: int) -> None:
    """Execute a ban after the vote threshold is reached."""
    try:
        session = ctx.vote_repo.get_vote_session(ctx.chat_id, target_user_id)
        target_mention = format_mention(
            target_user_id,
            session.get("target_username"),
            session.get("target_first_name", "User"),
        )

        voters_for_mention = _format_voter_list(session.get("votes_for_info", []))

        ctx.bot.kick_chat_member(ctx.chat_id, target_user_id)
        ctx.bot.send_message(
            ctx.chat_id,
            get_translated_text(
                "voteban_banned",
                TARGET=target_mention,
                VOTES_FOR=votes_for,
                VOTERS_FOR=voters_for_mention,
            ),
        )

        sent_message_id = session.get("reply_message_id")
        logger.info(
            "Deleting vote message and user's reply message",
            extra={"msg_id": ctx.message_id, "sent_message_id": sent_message_id},
        )
        if ctx.message_id and sent_message_id:
            try:
                ctx.bot.delete_message(ctx.chat_id, ctx.message_id)
                ctx.bot.delete_message(ctx.chat_id, sent_message_id)
            except Exception:
                logger.exception(f"Failed to delete vote message: {ctx.message_id}")

        ctx.vote_repo.delete_vote_session(ctx.chat_id, target_user_id)
        if ctx.stats_repo:
            ctx.stats_repo.increment_total_bans(ctx.chat_id)
        logger.info("User %s banned by vote.", target_user_id)
    except Exception as e:
        logger.exception(f"Failed to ban user: {e}")


def _finalize_forgive(ctx: Context, target_user_id: int, votes_against: int) -> None:
    """Cancel a voteban after the forgive threshold is reached."""
    session = ctx.vote_repo.get_vote_session(ctx.chat_id, target_user_id)
    target_mention = format_mention(
        target_user_id,
        session.get("target_username"),
        session.get("target_first_name", "User"),
    )

    voters_against_mention = _format_voter_list(session.get("votes_against_info", []))

    ctx.bot.send_message(
        ctx.chat_id,
        get_translated_text(
            "voteban_forgiven",
            TARGET=target_mention,
            VOTES_AGAINST=votes_against,
            VOTERS_AGAINST=voters_against_mention,
        ),
    )

    sent_message_id = int(session.get("sent_message_id"))
    if ctx.message_id and sent_message_id:
        try:
            ctx.bot.delete_message(ctx.chat_id, ctx.message_id)
            ctx.bot.delete_message(ctx.chat_id, sent_message_id)
        except Exception:
            logger.exception(f"Failed to delete vote message: {ctx.message_id}")

    ctx.vote_repo.delete_vote_session(ctx.chat_id, target_user_id)
    logger.info("User %s forgiven by vote.", target_user_id)


def _update_vote_message(
    ctx: Context,
    target_user_id: int,
    votes_for: int,
    votes_against: int,
) -> None:
    """Update the inline vote message with current tallies."""
    try:
        session = ctx.vote_repo.get_vote_session(ctx.chat_id, target_user_id)
        target_mention = format_mention(
            target_user_id,
            session.get("target_username"),
            session.get("target_first_name", "User"),
        )

        initiator_user_id = session.get("initiator_user_id")
        if initiator_user_id:
            initiator_mention = format_mention(
                initiator_user_id,
                session.get("initiator_username"),
                session.get("initiator_first_name", "User"),
            )
        else:
            initiator_mention = "Someone"

        updated_text = get_translated_text(
            "voteban_initiated",
            ctx.lang_code,
            INITIATOR=initiator_mention,
            TARGET=target_mention,
            # THRESHOLD=VOTEBAN_THRESHOLD,
            # VOTES_FOR=votes_for,
            # VOTES_AGAINST=votes_against,
        )

        ctx.bot.edit_message_text(
            ctx.chat_id,
            ctx.message_id,
            updated_text,
            reply_markup=_vote_keyboard(target_user_id, votes_for, votes_against),
        )
    except Exception as e:
        logger.exception(f"Failed to update vote message: {e}")
