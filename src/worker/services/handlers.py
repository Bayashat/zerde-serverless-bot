"""
Custom logic handlers.
"""

from typing import Any

from aws_lambda_powertools import Logger
from core.context import Context
from core.dispatcher import Dispatcher
from repositories.telegram_client import TelegramClient
from services import (
    VERIFY_PREFIX,
    VOTEBAN_AGAINST_PREFIX,
    VOTEBAN_FOR_PREFIX,
    VOTEBAN_FORGIVE_THRESHOLD,
    VOTEBAN_THRESHOLD,
)
from services.message_formatter import get_translated_text

logger = Logger()


def send_private_msg(bot: TelegramClient, chat_id: str | int) -> None:
    """
    Send private message to the user.
    """
    if not chat_id:
        logger.exception("Chat ID is required")
        return
    text = get_translated_text("private_message")
    bot.send_message(chat_id, text)


def process_timeout_task(bot: TelegramClient, task_data: dict[str, Any]) -> None:
    """
    Process CHECK_TIMEOUT task: if user still restricted, kick and delete verification msg.
    """
    chat_id = task_data.get("chat_id")
    user_id = task_data.get("user_id")
    message_id = task_data.get("message_id")
    if chat_id is None or user_id is None or message_id is None:
        logger.warning("Timeout task missing chat_id/user_id/message_id", task_data=task_data)
        return
    try:
        member = bot.get_chat_member(chat_id, user_id)
        status = (member.get("status") or "").lower()
        can_send = member.get("can_send_messages", True)

        if status in ("member", "administrator", "creator") or can_send:
            logger.info("User %s already verified. Ignoring timeout.", user_id)
            return
        logger.info("User %s timed out. Kicking.", user_id)
        bot.kick_chat_member(chat_id, user_id)
        try:
            bot.delete_message(chat_id, message_id)
        except Exception as e:
            logger.warning("Failed to delete verification message %s: %s", message_id, e)
        return
    except Exception as e:
        logger.exception("Timeout task error (user may have left or message deleted): %s", e)


def register_handlers(dp: Dispatcher):
    """
    Register all the handlers here.
    """

    @dp.on_new_chat_members
    def handle_new_member(ctx: Context) -> None:
        """Mute new members, send verification message with inline button, increment total_joins."""
        try:
            members = ctx.message.get("new_chat_members", [])
            chat_id = ctx.chat_id
            bot = ctx._bot
            for member in members:
                if member.get("is_bot"):
                    continue
                user_id = member.get("id")
                # Mute immediately
                bot.restrict_chat_member(
                    chat_id,
                    user_id,
                    {"can_send_messages": False},
                )
                # Send verification message with inline button
                first_name = member.get("first_name", "User")
                mention = f'<a href="tg://user?id={user_id}">{first_name}</a>'
                text = get_translated_text("welcome_verification", MENTION=mention)
                reply_markup = {
                    "inline_keyboard": [
                        [
                            {
                                "text": "Мен адаммын / I am human",
                                "callback_data": f"{VERIFY_PREFIX}{user_id}",
                            }
                        ]
                    ]
                }
                sent_message = bot.send_message(chat_id, text, reply_markup=reply_markup)
                msg_id = sent_message.get("message_id") if sent_message else None
                if msg_id is not None and ctx.sqs_repo:
                    ctx.sqs_repo.send_timeout_task(chat_id, user_id, msg_id, delay_seconds=60)
                    logger.info("Sent delayed timeout task", extra={"user_id": user_id})
                if ctx.stats_repo:
                    ctx.stats_repo.increment_total_joins(chat_id)
        except Exception as e:
            logger.exception(f"handle_new_member error: {e}")
            if ctx.chat_id:
                ctx.reply(get_translated_text("error_occurred"))

    @dp.on_callback_query
    def handle_verification(ctx: Context) -> None:
        """
        Handle callback queries:
        1. Verification button (verify_{user_id})
        2. Vote-to-ban buttons (voteban_for_{user_id}, voteban_against_{user_id})
        """
        try:
            # Handle verification callback
            if ctx.callback_data.startswith(VERIFY_PREFIX):
                payload_user_id = ctx.callback_data[len(VERIFY_PREFIX) :].strip()
                if not payload_user_id.isdigit():
                    if ctx.callback_query_id:
                        ctx._bot.answer_callback_query(ctx.callback_query_id, text=get_translated_text("invalid_data"))
                    return
                target_user_id = int(payload_user_id)
                if ctx.user_id != target_user_id:
                    if ctx.callback_query_id:
                        ctx._bot.answer_callback_query(
                            ctx.callback_query_id,
                            text=get_translated_text("only_user_may_verify"),
                            show_alert=True,
                        )
                    return
                chat_id = ctx.chat_id
                msg_id = ctx.message_id
                if not chat_id or msg_id is None:
                    if ctx.callback_query_id:
                        ctx._bot.answer_callback_query(
                            ctx.callback_query_id, text=get_translated_text("error_occurred")
                        )
                    return
                bot = ctx._bot
                # Unmute: grant standard permissions
                full_permissions = {
                    "can_send_messages": True,
                    "can_send_audios": True,
                    "can_send_documents": True,
                    "can_send_photos": True,
                    "can_send_videos": True,
                    "can_send_video_notes": True,
                    "can_send_voice_notes": True,
                    "can_send_polls": True,
                    "can_send_other_messages": True,
                    "can_add_web_page_previews": True,
                }
                bot.restrict_chat_member(
                    chat_id,
                    target_user_id,
                    full_permissions,
                )
                # Create mention for this verified user
                mention = f'<a href="tg://user?id={ctx.user_id}">{ctx.user_data.get("first_name", "User")}</a>'
                bot.answer_callback_query(
                    ctx.callback_query_id, text=get_translated_text("verification_successful", MENTION=mention)
                )
                try:
                    bot.delete_message(chat_id, msg_id)
                except Exception:
                    logger.exception(f"Failed to delete verification message: {msg_id}")

                bot.send_message(chat_id, get_translated_text("welcome_verified", MENTION=mention))

                if ctx.stats_repo:
                    ctx.stats_repo.increment_verified_users(chat_id)

                logger.info("User %s verified.", target_user_id)
                return

            # Handle vote-to-ban callbacks
            if ctx.callback_data.startswith(VOTEBAN_FOR_PREFIX) or ctx.callback_data.startswith(VOTEBAN_AGAINST_PREFIX):
                vote_for = ctx.callback_data.startswith(VOTEBAN_FOR_PREFIX)
                prefix = VOTEBAN_FOR_PREFIX if vote_for else VOTEBAN_AGAINST_PREFIX
                target_user_id_str = ctx.callback_data[len(prefix) :].strip()

                if not target_user_id_str.isdigit():
                    if ctx.callback_query_id:
                        ctx._bot.answer_callback_query(ctx.callback_query_id, text=get_translated_text("invalid_data"))
                    return

                target_user_id = int(target_user_id_str)
                chat_id = ctx.chat_id
                if not chat_id or not ctx.vote_repo:
                    if ctx.callback_query_id:
                        ctx._bot.answer_callback_query(
                            ctx.callback_query_id, text=get_translated_text("error_occurred")
                        )
                    return

                # Add vote
                result = ctx.vote_repo.add_vote(chat_id, target_user_id, ctx.user_id, vote_for)

                if result["already_voted"]:
                    ctx._bot.answer_callback_query(
                        ctx.callback_query_id,
                        text=get_translated_text("voteban_already_voted", lang_code=ctx.lang_code),
                        show_alert=True,
                    )
                    return

                # Answer callback
                ctx._bot.answer_callback_query(
                    ctx.callback_query_id,
                    text=get_translated_text("voteban_vote_recorded", lang_code=ctx.lang_code),
                )

                votes_for = result["votes_for"]
                votes_against = result["votes_against"]

                # Check if threshold is reached
                if votes_for >= VOTEBAN_THRESHOLD:
                    # Ban the user
                    try:
                        # Get session to retrieve target info
                        session = ctx.vote_repo.get_vote_session(chat_id, target_user_id)
                        target_username = session.get("target_username")
                        target_first_name = session.get("target_first_name", "User")

                        # Format target mention
                        if target_username:
                            target_mention = f"@{target_username}"
                        else:
                            target_mention = f'<a href="tg://user?id={target_user_id}">{target_first_name}</a>'

                        ctx._bot.kick_chat_member(chat_id, target_user_id)

                        # Send ban notification
                        ctx._bot.send_message(
                            chat_id,
                            get_translated_text(
                                "voteban_banned",
                                lang_code=ctx.lang_code,
                                TARGET=target_mention,
                                VOTES_FOR=votes_for,
                            ),
                        )

                        # Delete vote message and session
                        msg_id = ctx.message_id
                        if msg_id:
                            try:
                                ctx._bot.delete_message(chat_id, msg_id)
                            except Exception:
                                logger.exception(f"Failed to delete vote message: {msg_id}")

                        ctx.vote_repo.delete_vote_session(chat_id, target_user_id)
                        logger.info("User %s banned by vote.", target_user_id)
                    except Exception as e:
                        logger.exception(f"Failed to ban user: {e}")
                    return

                # Check if forgiven
                if votes_against >= VOTEBAN_FORGIVE_THRESHOLD:
                    # Cancel the vote - get session to retrieve target info
                    session = ctx.vote_repo.get_vote_session(chat_id, target_user_id)
                    target_username = session.get("target_username")
                    target_first_name = session.get("target_first_name", "User")

                    # Format target mention
                    if target_username:
                        target_mention = f"@{target_username}"
                    else:
                        target_mention = f'<a href="tg://user?id={target_user_id}">{target_first_name}</a>'

                    ctx._bot.send_message(
                        chat_id,
                        get_translated_text(
                            "voteban_forgiven",
                            lang_code=ctx.lang_code,
                            TARGET=target_mention,
                            VOTES_AGAINST=votes_against,
                        ),
                    )

                    # Delete vote message and session
                    msg_id = ctx.message_id
                    if msg_id:
                        try:
                            ctx._bot.delete_message(chat_id, msg_id)
                        except Exception:
                            logger.exception(f"Failed to delete vote message: {msg_id}")

                    ctx.vote_repo.delete_vote_session(chat_id, target_user_id)
                    logger.info("User %s forgiven by vote.", target_user_id)
                    return

                # Update vote message with new counts
                msg_id = ctx.message_id
                if msg_id:
                    try:
                        # Get session to retrieve stored user info
                        session = ctx.vote_repo.get_vote_session(chat_id, target_user_id)
                        target_username = session.get("target_username")
                        target_first_name = session.get("target_first_name", "User")
                        initiator_user_id = session.get("initiator_user_id")

                        # Format target mention
                        if target_username:
                            target_mention = f"@{target_username}"
                        else:
                            target_mention = f'<a href="tg://user?id={target_user_id}">{target_first_name}</a>'

                        # Format initiator mention using stored info
                        initiator_username = session.get("initiator_username")
                        initiator_first_name = session.get("initiator_first_name", "User")
                        if initiator_username:
                            initiator_mention = f"@{initiator_username}"
                        elif initiator_user_id:
                            initiator_mention = f'<a href="tg://user?id={initiator_user_id}">{initiator_first_name}</a>'
                        else:
                            initiator_mention = "Someone"

                        updated_text = get_translated_text(
                            "voteban_initiated",
                            lang_code=ctx.lang_code,
                            INITIATOR=initiator_mention,
                            TARGET=target_mention,
                            THRESHOLD=VOTEBAN_THRESHOLD,
                            VOTES_FOR=votes_for,
                            VOTES_AGAINST=votes_against,
                        )

                        # Update message
                        ctx._bot.edit_message_text(
                            chat_id,
                            msg_id,
                            updated_text,
                            reply_markup={
                                "inline_keyboard": [
                                    [
                                        {
                                            "text": "👍 Ban",
                                            "callback_data": f"{VOTEBAN_FOR_PREFIX}{target_user_id}",
                                        },
                                        {
                                            "text": "👎 Forgive",
                                            "callback_data": f"{VOTEBAN_AGAINST_PREFIX}{target_user_id}",
                                        },
                                    ]
                                ]
                            },
                        )
                    except Exception as e:
                        logger.exception(f"Failed to update vote message: {e}")

                return

            # Unknown callback
            if ctx.callback_query_id:
                ctx._bot.answer_callback_query(ctx.callback_query_id, text=get_translated_text("unknown_action"))

        except Exception as e:
            logger.exception(f"handle_verification error: {e}")
            if ctx.callback_query_id:
                try:
                    ctx._bot.answer_callback_query(ctx.callback_query_id, text="Verification failed.")
                except Exception:
                    pass

    @dp.command("stats")
    def handle_stats(ctx: Context) -> None:
        """Admin-only: reply with top stats (total joins, verified, activity level) in Kazakh."""
        try:
            chat_id = ctx.chat_id
            user_id = ctx.user_id
            if not chat_id or user_id is None:
                ctx.reply(get_translated_text("stats_error", lang_code=ctx.lang_code))
                return
            member = ctx._bot.get_chat_member(chat_id, user_id)
            status = (member.get("status") or "").lower()
            if status not in ("creator", "administrator"):
                ctx.reply(get_translated_text("stats_admin_only", lang_code=ctx.lang_code))
                return
            stats = ctx.stats_repo.get_stats(chat_id)
            total = stats["total_joins"]
            verified = stats["verified_users"]
            start_date = stats.get("started_at")
            if total == 0:
                activity_level_percentage = 0
            else:
                activity_level_percentage = int(min(100, 100 * verified / max(1, total)))

            if activity_level_percentage < 30:
                level_key = "activity_low"
            elif activity_level_percentage < 70:
                level_key = "activity_medium"
            else:
                level_key = "activity_high"
            activity_level = get_translated_text(level_key, lang_code=ctx.lang_code)
            msg = get_translated_text(
                "stats_message",
                lang_code=ctx.lang_code,
                start_date=start_date,
                total=total,
                verified=verified,
                activity_level=activity_level,
            )
            ctx.reply(msg)
        except Exception as e:
            logger.exception(f"handle_stats error: {e}")
            ctx.reply(get_translated_text("stats_error", lang_code=ctx.lang_code))

    @dp.command("start")
    def handle_start(ctx: Context):
        ctx.reply(get_translated_text("start_message", lang_code=ctx.lang_code))

    @dp.command("help")
    def handle_help(ctx: Context):
        ctx.reply(get_translated_text("help_message", lang_code=ctx.lang_code))

    @dp.command("support")
    def handle_support(ctx: Context):
        ctx.reply(get_translated_text("support_message", lang_code=ctx.lang_code))

    # Example of a custom command logic
    @dp.command("ping")
    def handle_ping(ctx: Context):
        ctx.reply("🏓 Pong! Serverless is fast.")

    @dp.command("voteban")
    def handle_voteban(ctx: Context) -> None:
        """Start a vote to ban a user (reply to their message)."""
        try:
            # Check if this is a reply to a message
            if not ctx.reply_to_message:
                ctx.reply(get_translated_text("voteban_usage", lang_code=ctx.lang_code))
                return

            # Get target user from replied message
            target_user = ctx.reply_to_message.get("from", {})
            target_user_id = target_user.get("id")
            target_username = target_user.get("username")
            target_first_name = target_user.get("first_name", "User")

            if not target_user_id:
                ctx.reply(get_translated_text("voteban_usage", lang_code=ctx.lang_code))
                return

            # Check if user is trying to ban themselves
            if target_user_id == ctx.user_id:
                ctx.reply(get_translated_text("voteban_self", lang_code=ctx.lang_code))
                return

            # Check if target is an admin
            chat_id = ctx.chat_id
            if not chat_id:
                return
            member = ctx._bot.get_chat_member(chat_id, target_user_id)
            status = (member.get("status") or "").lower()
            if status in ("creator", "administrator"):
                ctx.reply(get_translated_text("voteban_admin", lang_code=ctx.lang_code))
                return

            # Format target mention
            if target_username:
                target_mention = f"@{target_username}"
            else:
                target_mention = f'<a href="tg://user?id={target_user_id}">{target_first_name}</a>'

            # Format initiator mention
            initiator_username = ctx.username
            initiator_first_name = ctx.first_name or "User"
            if initiator_username:
                initiator_mention = f"@{initiator_username}"
            else:
                initiator_mention = f'<a href="tg://user?id={ctx.user_id}">{initiator_first_name}</a>'

            # Create inline keyboard with vote buttons
            reply_markup = {
                "inline_keyboard": [
                    [
                        {
                            "text": "👍 Ban",
                            "callback_data": f"{VOTEBAN_FOR_PREFIX}{target_user_id}",
                        },
                        {
                            "text": "👎 Forgive",
                            "callback_data": f"{VOTEBAN_AGAINST_PREFIX}{target_user_id}",
                        },
                    ]
                ]
            }

            text = get_translated_text(
                "voteban_initiated",
                lang_code=ctx.lang_code,
                INITIATOR=initiator_mention,
                TARGET=target_mention,
                THRESHOLD=VOTEBAN_THRESHOLD,
                VOTES_FOR=1,  # Initiator's vote
                VOTES_AGAINST=0,
            )

            # Send vote message as reply to target's message
            sent_message = ctx.reply(
                text,
                reply_markup=reply_markup,
                reply_to_message_id=ctx.reply_to_message.get("message_id"),
            )

            # Create vote session with initiator's vote
            if ctx.vote_repo and sent_message:
                message_id = sent_message.get("message_id")
                if message_id:
                    ctx.vote_repo.create_vote_session(
                        chat_id,
                        target_user_id,
                        message_id,
                        ctx.user_id,
                        initiator_username=initiator_username,
                        initiator_first_name=initiator_first_name,
                        target_username=target_username,
                        target_first_name=target_first_name,
                    )
                    logger.info(
                        "Vote session created",
                        extra={
                            "chat_id": chat_id,
                            "target_user_id": target_user_id,
                            "initiator_user_id": ctx.user_id,
                        },
                    )
        except Exception as e:
            logger.exception(f"handle_voteban error: {e}")
            ctx.reply(get_translated_text("error_occurred", lang_code=ctx.lang_code))
