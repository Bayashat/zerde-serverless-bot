"""Captcha verification: new-member mute, 'I am human' button, timeout kick."""

from typing import Any

from aws_lambda_powertools import Logger
from core.config import CAPTCHA_TIMEOUT_SECONDS, VERIFY_PREFIX
from core.dispatcher import Context
from core.translations import get_translated_text
from core.utils import format_mention
from services.telegram import TelegramClient

logger = Logger()

_FULL_PERMISSIONS: dict[str, bool] = {
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


def process_timeout_task(bot: TelegramClient, task_data: dict[str, Any]) -> None:
    """Process CHECK_TIMEOUT task: kick user if still restricted."""
    chat_id = task_data.get("chat_id")
    user_id = task_data.get("user_id")
    join_message_id = task_data.get("join_message_id")
    verification_message_id = task_data.get("verification_message_id")
    if not all([chat_id, user_id, join_message_id, verification_message_id]):
        logger.warning(
            "Timeout task missing required fields",
            task_data=task_data,
        )
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
            bot.delete_message(chat_id, join_message_id)
            bot.delete_message(chat_id, verification_message_id)
        except Exception as e:
            logger.warning("Failed to delete join/verification messages: %s", e)
    except Exception as e:
        logger.exception("Timeout task error (user may have left or message deleted): %s", e)


def handle_new_member(ctx: Context) -> None:
    """Mute new members, send verification button, increment total_joins."""
    try:
        members = ctx.message.get("new_chat_members", [])
        for member in members:
            if member.get("is_bot"):
                continue

            user_id = member.get("id")
            ctx.bot.restrict_chat_member(ctx.chat_id, user_id, {"can_send_messages": False})

            mention = format_mention(user_id, member.get("username"), member.get("first_name", "User"))
            text = get_translated_text("welcome_verification", MENTION=mention)

            reply_markup = {
                "inline_keyboard": [
                    [
                        {
                            "text": "Мен адаммын",
                            "callback_data": f"{VERIFY_PREFIX}{user_id}-{ctx.message_id}",
                        }
                    ]
                ]
            }
            sent_message = ctx.reply(
                text,
                ctx.message_id,
                reply_markup,
            )
            msg_id = sent_message.get("message_id") if sent_message else None

            if msg_id is not None and ctx.sqs_repo:
                ctx.sqs_repo.send_timeout_task(
                    ctx.chat_id,
                    user_id,
                    join_message_id=ctx.message_id,
                    verification_message_id=msg_id,
                    delay_seconds=CAPTCHA_TIMEOUT_SECONDS,
                )
                logger.info(
                    "Sent delayed timeout task",
                    extra={"user_id": user_id},
                )
            if ctx.stats_repo:
                ctx.stats_repo.increment_total_joins(ctx.chat_id)
    except Exception as e:
        logger.exception(f"handle_new_member error: {e}")
        if ctx.chat_id:
            ctx.reply(get_translated_text("error_occurred"), ctx.message_id)


def handle_verify_callback(ctx: Context) -> None:
    """Handle captcha verification callback query."""
    payload = ctx.callback_data[len(VERIFY_PREFIX) :].split("-")
    payload_user_id = int(payload[0].strip())
    join_message_id = payload[1].strip()

    if ctx.user_id != payload_user_id:
        if ctx.callback_query_id:
            ctx.bot.answer_callback_query(
                ctx.callback_query_id,
                text=get_translated_text("only_user_may_verify"),
                show_alert=True,
            )
        return

    ctx.bot.restrict_chat_member(ctx.chat_id, payload_user_id, _FULL_PERMISSIONS)

    mention = format_mention(ctx.user_id, ctx.username, ctx.first_name)
    ctx.bot.answer_callback_query(
        ctx.callback_query_id,
        text=get_translated_text("verification_successful", MENTION=mention),
    )
    try:
        ctx.bot.delete_message(ctx.chat_id, join_message_id)
        ctx.bot.delete_message(ctx.chat_id, ctx.message_id)
    except Exception:
        logger.exception(f"Failed to delete verification message: {ctx.message_id}")

    ctx.reply(
        get_translated_text("welcome_verified", MENTION=mention),
    )

    if ctx.stats_repo:
        ctx.stats_repo.increment_verified_users(ctx.chat_id)

    logger.info("User %s verified.", payload_user_id)
