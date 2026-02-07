"""
Custom logic handlers.
"""

from typing import Any

from aws_lambda_powertools import Logger
from core.context import Context
from core.dispatcher import Dispatcher
from repositories.telegram_client import TelegramClient
from repositories.vote_repository import VOTES_THRESHOLD
from services import VERIFY_PREFIX, VOTE_BAN_PREFIX, VOTE_FORGIVE_PREFIX
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


def handle_vote_callback(ctx: Context, vote_type: str) -> None:
    """
    Handle vote button callbacks (ban or forgive).
    """
    try:
        # Extract vote_key from callback_data
        prefix = VOTE_BAN_PREFIX if vote_type == "ban" else VOTE_FORGIVE_PREFIX
        vote_key = ctx.callback_data[len(prefix) :].strip()

        if not ctx.vote_repo:
            ctx._bot.answer_callback_query(ctx.callback_query_id, text=get_translated_text("error_occurred"))
            return

        # Check if vote session exists
        vote_session = ctx.vote_repo.get_vote_session(vote_key)
        if not vote_session:
            ctx._bot.answer_callback_query(
                ctx.callback_query_id, text=get_translated_text("vote_ban_session_not_found"), show_alert=True
            )
            return

        # Add the vote
        result = ctx.vote_repo.add_vote(vote_key, ctx.user_id, vote_type)

        # Answer the callback
        ctx._bot.answer_callback_query(ctx.callback_query_id, text=get_translated_text("vote_recorded"))

        # Update the message with new vote counts
        initiator_user_id = vote_session["initiator_user_id"]
        target_user_id = vote_session["target_user_id"]

        # Get initiator info
        initiator_info = ctx._bot.get_chat_member(ctx.chat_id, initiator_user_id)
        initiator_first_name = initiator_info.get("user", {}).get("first_name", "User")
        initiator_mention = f'<a href="tg://user?id={initiator_user_id}">{initiator_first_name}</a>'

        # Get target info
        target_info = ctx._bot.get_chat_member(ctx.chat_id, target_user_id)
        target_first_name = target_info.get("user", {}).get("first_name", "User")
        target_mention = f'<a href="tg://user?id={target_user_id}">{target_first_name}</a>'

        ban_count = result["ban_votes"]
        forgive_count = result["forgive_votes"]

        # Check if ban threshold is reached
        if ban_count >= VOTES_THRESHOLD:
            # Ban the user
            try:
                ctx._bot.kick_chat_member(ctx.chat_id, target_user_id)
                # Delete the vote session
                ctx.vote_repo.delete_vote_session(vote_key)
                # Update message to show success
                ctx._bot.edit_message_text(
                    ctx.chat_id,
                    ctx.message_id,
                    get_translated_text("vote_ban_success", lang_code=ctx.lang_code),
                )
                logger.info(f"User {target_user_id} banned by vote in chat {ctx.chat_id}")
            except Exception as e:
                logger.exception(f"Failed to ban user: {e}")
        else:
            # Update vote counts in the message
            updated_text = get_translated_text(
                "vote_ban_initiated",
                lang_code=ctx.lang_code,
                INITIATOR=initiator_mention,
                TARGET=target_mention,
                BAN_COUNT=ban_count,
                FORGIVE_COUNT=forgive_count,
                THRESHOLD=VOTES_THRESHOLD,
            )
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": "🚫 Ban", "callback_data": f"{VOTE_BAN_PREFIX}{vote_key}"},
                        {"text": "💚 Forgive / Кешіру", "callback_data": f"{VOTE_FORGIVE_PREFIX}{vote_key}"},
                    ]
                ]
            }
            ctx._bot.edit_message_text(ctx.chat_id, ctx.message_id, updated_text, reply_markup=reply_markup)
    except Exception as e:
        logger.exception(f"handle_vote_callback error: {e}")
        if ctx.callback_query_id:
            try:
                ctx._bot.answer_callback_query(ctx.callback_query_id, text=get_translated_text("error_occurred"))
            except Exception:
                pass


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
        Verify user from button click:
        unmute, answer callback, delete verification msg, send welcome, increment verified.
        Also handle vote-to-ban callbacks.
        """
        mention = f'<a href="tg://user?id={ctx.user_id}">{ctx.user_data.get("first_name", "User")}</a>'
        try:
            # Handle vote-to-ban callbacks
            if ctx.callback_data.startswith(VOTE_BAN_PREFIX):
                handle_vote_callback(ctx, "ban")
                return
            elif ctx.callback_data.startswith(VOTE_FORGIVE_PREFIX):
                handle_vote_callback(ctx, "forgive")
                return

            # Handle verification callbacks
            if not ctx.callback_data.startswith(VERIFY_PREFIX):
                if ctx.callback_query_id:
                    ctx._bot.answer_callback_query(ctx.callback_query_id, text=get_translated_text("unknown_action"))
                return
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
                    ctx._bot.answer_callback_query(ctx.callback_query_id, text=get_translated_text("error_occurred"))
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
            if total < 10:
                level_key = "activity_low"
            elif total < 100:
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
    def handle_voteban(ctx: Context):
        """
        Initiate a vote-to-ban session.
        User must reply to another user's message.
        """
        try:
            # Check if this is a reply to another message
            if not ctx.reply_to_message:
                ctx.reply(get_translated_text("vote_ban_reply_required", lang_code=ctx.lang_code))
                return

            target_user = ctx.reply_to_message.get("from", {})
            target_user_id = target_user.get("id")
            target_first_name = target_user.get("first_name", "User")

            if not target_user_id:
                ctx.reply(get_translated_text("error_occurred", lang_code=ctx.lang_code))
                return

            # Cannot ban yourself
            if target_user_id == ctx.user_id:
                ctx.reply(get_translated_text("vote_ban_cannot_ban_self", lang_code=ctx.lang_code))
                return

            # Cannot ban admins or bots
            if target_user.get("is_bot"):
                ctx.reply(get_translated_text("error_occurred", lang_code=ctx.lang_code))
                return

            # Check if target is admin
            try:
                member = ctx._bot.get_chat_member(ctx.chat_id, target_user_id)
                status = (member.get("status") or "").lower()
                if status in ("creator", "administrator"):
                    ctx.reply(get_translated_text("vote_ban_cannot_ban_admin", lang_code=ctx.lang_code))
                    return
            except Exception as e:
                logger.warning(f"Failed to check target user status: {e}")

            # Create mention strings
            initiator_mention = f'<a href="tg://user?id={ctx.user_id}">{ctx.user_data.get("first_name", "User")}</a>'
            target_mention = f'<a href="tg://user?id={target_user_id}">{target_first_name}</a>'

            # Send vote message
            text = get_translated_text(
                "vote_ban_initiated",
                lang_code=ctx.lang_code,
                INITIATOR=initiator_mention,
                TARGET=target_mention,
                BAN_COUNT=0,
                FORGIVE_COUNT=0,
                THRESHOLD=VOTES_THRESHOLD,
            )

            # We need to create the vote session first to get the vote_key
            # Use a temporary message to get message_id
            temp_msg = ctx._bot.send_message(
                ctx.chat_id, text, reply_to_message_id=ctx.reply_to_message.get("message_id")
            )
            message_id = temp_msg.get("message_id")

            if not message_id or not ctx.vote_repo:
                ctx.reply(get_translated_text("error_occurred", lang_code=ctx.lang_code))
                return

            # Create vote session
            vote_key = ctx.vote_repo.create_vote_session(ctx.chat_id, target_user_id, ctx.user_id, message_id)

            # Update the message with buttons
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": "🚫 Ban", "callback_data": f"{VOTE_BAN_PREFIX}{vote_key}"},
                        {"text": "💚 Forgive / Кешіру", "callback_data": f"{VOTE_FORGIVE_PREFIX}{vote_key}"},
                    ]
                ]
            }

            ctx._bot.edit_message_text(ctx.chat_id, message_id, text, reply_markup=reply_markup)

            logger.info(f"Vote-to-ban session created: {vote_key}")

        except Exception as e:
            logger.exception(f"handle_voteban error: {e}")
            ctx.reply(get_translated_text("error_occurred", lang_code=ctx.lang_code))
