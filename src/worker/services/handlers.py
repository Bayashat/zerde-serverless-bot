"""
User Logic Handlers.
This is where developers add their custom business logic.
"""

from typing import Any

from aws_lambda_powertools import Logger
from core.context import Context
from core.dispatcher import Dispatcher
from repositories.telegram_client import TelegramClient
from services import VERIFY_PREFIX
from services.message_formatter import get_translated_text

logger = Logger()


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

        if status in ("member", "administrator", "creator"):
            logger.info("User %s already verified. Ignoring timeout.", user_id)
            return

        if status == "restricted" or not can_send:
            logger.info("User %s timed out. Kicking.", user_id)
            bot.ban_chat_member(chat_id, user_id)

            # 2. 立刻解封 (Unban) -> 这样就变成了“踢出”而不是“拉黑”
            # 给一点点微小的延迟确保 Telegram 处理完 Ban 并不是必须的，
            # 但为了保险，直接调用即可，API 顺序通常是有保证的。
            bot.unban_chat_member(chat_id, user_id)
            try:
                bot.delete_message(chat_id, message_id)
            except Exception as e:
                logger.warning("Failed to delete verification message %s: %s", message_id, e)
            return

        # left / kicked / unknown: do nothing
        logger.debug("User %s status=%s, no action.", user_id, status)
    except Exception as e:
        logger.exception("Timeout task error (user may have left or message deleted): %s", e)


def register_handlers(dp: Dispatcher):
    """
    Register all your handlers here.
    """

    @dp.on_new_chat_members
    def handle_new_member(ctx: Context) -> None:
        """Mute new members, send verification message with inline button, increment total_joins."""
        try:
            members = ctx.message.get("new_chat_members", [])
            chat_id = ctx.chat_id
            if not chat_id:
                return
            bot = ctx._bot
            for member in members:
                if member.get("is_bot"):
                    continue
                user_id = member.get("id")
                if not user_id:
                    continue
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
        """
        mention = f'<a href="tg://user?id={ctx.user_id}">{ctx.user_data.get("first_name", "User")}</a>'
        try:
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
            bot.restrict_chat_member(
                chat_id,
                target_user_id,
                {
                    "can_send_messages": True,
                    "can_send_audios": True,
                    "can_send_documents": True,
                    "can_send_photos": True,
                    "can_send_videos": True,
                    "can_send_voice_notes": True,
                    "can_send_polls": True,
                    "can_invite_users": True,
                },
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
                ctx.reply(get_translated_text("stats_error"))
                return
            member = ctx._bot.get_chat_member(chat_id, user_id)
            status = (member.get("status") or "").lower()
            if status not in ("creator", "administrator"):
                ctx.reply(get_translated_text("stats_admin_only"))
                return
            if not ctx.stats_repo:
                ctx.reply(get_translated_text("stats_error"))
                return
            stats = ctx.stats_repo.get_stats(chat_id)
            total = stats["total_joins"]
            verified = stats["verified_users"]
            start_date = stats.get("started_at", "N/A")
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
            ctx.reply(get_translated_text("stats_error"))

    @dp.command("start")
    def handle_start(ctx: Context):
        # Using our multi-language helper
        msg = get_translated_text("start_message", lang_code=ctx.lang_code)
        ctx.reply(msg)

    @dp.command("help")
    def handle_help(ctx: Context):
        msg = get_translated_text("help_message", lang_code=ctx.lang_code)
        ctx.reply(msg)

    @dp.command("support")
    def handle_support(ctx: Context):
        msg = get_translated_text("support_message", lang_code=ctx.lang_code)
        ctx.reply(msg)

    # Example of a custom command logic
    @dp.command("ping")
    def handle_ping(ctx: Context):
        ctx.reply("🏓 Pong! Serverless is fast.")
