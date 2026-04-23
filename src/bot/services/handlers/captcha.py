"""Captcha verification: grid image challenge, answer checking, timeout kick."""

from typing import Any

from core.config import CAPTCHA_MAX_ATTEMPTS, CAPTCHA_TIMEOUT_SECONDS
from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from core.utils import format_mention
from services.captcha_image import generate_grid_captcha
from services.telegram import TelegramClient

logger = LoggerAdapter(get_logger(__name__), {})

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
    """Process CHECK_TIMEOUT task: kick user if still restricted, clean up captcha state."""
    chat_id = task_data.get("chat_id")
    user_id = task_data.get("user_id")
    join_message_id = task_data.get("join_message_id")
    verification_message_id = task_data.get("verification_message_id")
    captcha_repo = task_data.get("_captcha_repo")

    if not all([chat_id, user_id, join_message_id, verification_message_id]):
        logger.warning("Timeout task missing required fields", task_data=task_data)
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
    finally:
        if captcha_repo:
            try:
                captcha_repo.delete_pending(chat_id, user_id)
            except Exception as e:
                logger.warning("Failed to clean up captcha state on timeout: %s", e)


def handle_new_member(ctx: Context) -> None:
    """Mute new members, send grid image captcha, save state, queue timeout."""
    try:
        members = ctx.message.get("new_chat_members", [])
        for member in members:
            if member.get("is_bot"):
                continue

            user_id = member.get("id")
            ctx.bot.restrict_chat_member(ctx.chat_id, user_id, {"can_send_messages": False})

            image_bytes, expected = generate_grid_captcha()
            mention = format_mention(user_id, member.get("username"), member.get("first_name", "User"))
            caption = get_translated_text(
                "captcha_image_challenge",
                ctx.lang_code,
                MENTION=mention,
                TIMEOUT=CAPTCHA_TIMEOUT_SECONDS,
            )

            sent_message = ctx.bot.send_photo(ctx.chat_id, image_bytes, caption=caption)
            msg_id = sent_message.get("message_id") if sent_message else None

            if msg_id is not None:
                if ctx.captcha_repo:
                    ctx.captcha_repo.save_pending(
                        ctx.chat_id,
                        user_id,
                        expected=expected,
                        join_msg_id=ctx.message_id,
                        verify_msg_id=msg_id,
                    )

                if ctx.sqs_repo:
                    ctx.sqs_repo.send_timeout_task(
                        ctx.chat_id,
                        user_id,
                        join_message_id=ctx.message_id,
                        verification_message_id=msg_id,
                        delay_seconds=CAPTCHA_TIMEOUT_SECONDS,
                    )
                    logger.info("Sent delayed timeout task", extra={"user_id": user_id})

            if ctx.stats_repo:
                ctx.stats_repo.increment_total_joins(ctx.chat_id)

    except Exception as e:
        logger.exception(f"handle_new_member error: {e}")
        if ctx.chat_id:
            ctx.reply(get_translated_text("error_occurred", ctx.lang_code), ctx.message_id)


def handle_captcha_answer(ctx: Context) -> None:
    """Check plain-text message from restricted user against their captcha answer."""
    if not ctx.captcha_repo or not ctx.user_id or not ctx.chat_id:
        return

    pending = ctx.captcha_repo.get_pending(ctx.chat_id, ctx.user_id)
    if not pending:
        return  # not a pending captcha user — ignore

    answer = ctx.text.strip()
    expected = pending["expected"]

    if answer == expected:
        # ── Correct ─────────────────────────────────────────────────────────
        ctx.bot.restrict_chat_member(ctx.chat_id, ctx.user_id, _FULL_PERMISSIONS)
        ctx.captcha_repo.delete_pending(ctx.chat_id, ctx.user_id)

        try:
            ctx.bot.delete_message(ctx.chat_id, pending["join_msg_id"])
            ctx.bot.delete_message(ctx.chat_id, pending["verify_msg_id"])
            ctx.bot.delete_message(ctx.chat_id, ctx.message_id)
        except Exception as e:
            logger.warning("Failed to delete captcha messages: %s", e)

        mention = format_mention(ctx.user_id, ctx.username, ctx.first_name)
        ctx.reply(get_translated_text("welcome_verified", ctx.lang_code, MENTION=mention))

        if ctx.stats_repo:
            ctx.stats_repo.increment_verified_users(ctx.chat_id)

        logger.info("User %s passed captcha.", ctx.user_id)

    else:
        # ── Wrong answer ─────────────────────────────────────────────────────
        new_attempts = ctx.captcha_repo.increment_attempts(ctx.chat_id, ctx.user_id)
        remaining = CAPTCHA_MAX_ATTEMPTS - new_attempts

        try:
            ctx.bot.delete_message(ctx.chat_id, ctx.message_id)
        except Exception:
            pass

        if remaining <= 0:
            ctx.captcha_repo.delete_pending(ctx.chat_id, ctx.user_id)
            ctx.reply(get_translated_text("captcha_failed_kicked", ctx.lang_code))
            ctx.bot.kick_chat_member(ctx.chat_id, ctx.user_id)
            try:
                ctx.bot.delete_message(ctx.chat_id, pending["join_msg_id"])
                ctx.bot.delete_message(ctx.chat_id, pending["verify_msg_id"])
            except Exception:
                pass
            logger.info("User %s kicked after %d wrong captcha attempts.", ctx.user_id, new_attempts)
        else:
            ctx.reply(
                get_translated_text("captcha_wrong_answer", ctx.lang_code, ATTEMPTS_LEFT=remaining),
                reply_to_message_id=pending["verify_msg_id"],
            )
            logger.info("User %s wrong captcha attempt %d/%d.", ctx.user_id, new_attempts, CAPTCHA_MAX_ATTEMPTS)
