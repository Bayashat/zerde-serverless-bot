"""Captcha verification: grid image challenge, answer checking, timeout kick."""

import re
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

# Allow typing the captcha answer but block all media to prevent spam
_TEXT_ONLY_PERMISSIONS: dict[str, bool] = {
    "can_send_messages": True,
    "can_send_audios": False,
    "can_send_documents": False,
    "can_send_photos": False,
    "can_send_videos": False,
    "can_send_video_notes": False,
    "can_send_voice_notes": False,
    "can_send_polls": False,
    "can_send_other_messages": False,
    "can_add_web_page_previews": False,
}

_CAPTCHA_BLOCKED_PERMISSIONS = tuple(key for key, value in _TEXT_ONLY_PERMISSIONS.items() if value is False)


def _delete_timeout_messages(
    bot: TelegramClient,
    chat_id: int | str,
    message_ids: list[int],
) -> None:
    for message_id in message_ids:
        try:
            bot.delete_message(chat_id, message_id, ignore_not_found=True)
        except Exception as e:
            logger.warning("Failed to delete captcha timeout message %s: %s", message_id, e)


def _challenge_matches_timeout_task(
    challenge: dict[str, Any],
    join_message_id: int,
    verification_message_id: int,
) -> bool:
    return int(challenge.get("join_msg_id", 0)) == int(join_message_id) and int(
        challenge.get("verify_msg_id", 0)
    ) == int(verification_message_id)


def _is_captcha_text_only_restricted(member: dict[str, Any]) -> bool:
    if (member.get("status") or "").lower() != "restricted":
        return False
    if member.get("can_send_messages") is not True:
        return False
    return all(member.get(permission) is False for permission in _CAPTCHA_BLOCKED_PERMISSIONS)


def _delete_pending_state(captcha_repo: Any, chat_id: int | str, user_id: int) -> None:
    if not captcha_repo:
        return
    try:
        captcha_repo.delete_pending(chat_id, user_id)
    except Exception as e:
        logger.warning("Failed to clean up captcha state on timeout: %s", e)


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
    should_cleanup_state = False
    try:
        challenge = None
        if captcha_repo:
            challenge = captcha_repo.get_challenge(chat_id, user_id)
            if challenge is None:
                should_cleanup_state = True
                logger.info("Captcha timeout state missing. Ignoring timeout.", extra={"user_id": user_id})
                return
            if not _challenge_matches_timeout_task(challenge, join_message_id, verification_message_id):
                logger.info(
                    "Stale captcha timeout task ignored",
                    extra={
                        "user_id": user_id,
                        "task_join_message_id": join_message_id,
                        "task_verification_message_id": verification_message_id,
                    },
                )
                return
            if challenge.get("status") == "verified":
                should_cleanup_state = True
                wrong_message_ids = list(challenge.get("wrong_msg_ids", []))
                _delete_timeout_messages(bot, chat_id, [verification_message_id, *wrong_message_ids])
                logger.info("User %s already verified. Ignoring timeout.", user_id)
                return
            if challenge.get("status") != "pending":
                logger.warning(
                    "Captcha timeout state has unexpected status; ignoring timeout",
                    extra={"user_id": user_id, "captcha_status": challenge.get("status")},
                )
                return
        else:
            member = bot.get_chat_member(chat_id, user_id)
            if not _is_captcha_text_only_restricted(member):
                return

        logger.info("User %s timed out. Kicking.", user_id)
        bot.kick_chat_member(chat_id, user_id)
        should_cleanup_state = True
        wrong_message_ids = list(challenge.get("wrong_msg_ids", [])) if challenge else []
        _delete_timeout_messages(bot, chat_id, [join_message_id, verification_message_id, *wrong_message_ids])
    except Exception as e:
        logger.exception("Timeout task error (user may have left or message deleted): %s", e)
        raise
    finally:
        if should_cleanup_state:
            _delete_pending_state(captcha_repo, chat_id, user_id)


def handle_new_member(ctx: Context) -> None:
    """Mute new members, send grid image captcha, save state, queue timeout."""
    try:
        members = ctx.message.get("new_chat_members", [])
        for member in members:
            if member.get("is_bot"):
                continue

            user_id = member.get("id")
            ctx.bot.restrict_chat_member(ctx.chat_id, user_id, _TEXT_ONLY_PERMISSIONS)

            image_bytes, expected = generate_grid_captcha()
            mention = format_mention(user_id, member.get("username"), member.get("first_name", "User"))
            caption = get_translated_text(
                "captcha_image_challenge",
                ctx.lang_code,
                MENTION=mention,
                TIMEOUT=CAPTCHA_TIMEOUT_SECONDS,
            )

            try:
                sent_message = ctx.bot.send_photo(ctx.chat_id, image_bytes, caption=caption)
            except Exception:
                ctx.bot.restrict_chat_member(ctx.chat_id, user_id, _FULL_PERMISSIONS)
                raise
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


def _delete_all_captcha_messages(ctx: Context, pending: dict, extra_ids: list[int] | None = None) -> None:
    """Delete join message, captcha image, all error messages, and any extra IDs."""
    ids_to_delete = [pending["join_msg_id"], pending["verify_msg_id"]]
    ids_to_delete += pending.get("wrong_msg_ids", [])
    if extra_ids:
        ids_to_delete += extra_ids
    for msg_id in ids_to_delete:
        try:
            ctx.bot.delete_message(ctx.chat_id, msg_id, ignore_not_found=True)
        except Exception:
            pass


def _handle_wrong_captcha_attempt(ctx: Context, pending: dict) -> None:
    """Delete the user's message, increment attempts, and kick after max failures."""
    new_attempts = ctx.captcha_repo.increment_attempts(ctx.chat_id, ctx.user_id)
    remaining = CAPTCHA_MAX_ATTEMPTS - new_attempts

    try:
        ctx.bot.delete_message(ctx.chat_id, ctx.message_id, ignore_not_found=True)
    except Exception:
        pass

    if remaining <= 0:
        ctx.captcha_repo.delete_pending(ctx.chat_id, ctx.user_id)
        _delete_all_captcha_messages(ctx, pending)
        ctx.bot.kick_chat_member(ctx.chat_id, ctx.user_id)
        logger.info("User %s kicked after %d wrong captcha attempts.", ctx.user_id, new_attempts)
        return

    error_msg = ctx.reply(
        get_translated_text("captcha_wrong_answer", ctx.lang_code, ATTEMPTS_LEFT=remaining),
        reply_to_message_id=pending["verify_msg_id"],
    )
    if error_msg and error_msg.get("message_id"):
        ctx.captcha_repo.append_wrong_message(ctx.chat_id, ctx.user_id, error_msg["message_id"])
    logger.info("User %s wrong captcha attempt %d/%d.", ctx.user_id, new_attempts, CAPTCHA_MAX_ATTEMPTS)


def handle_captcha_answer(ctx: Context) -> None:
    """Check plain-text message from restricted user against their captcha answer."""
    if not ctx.captcha_repo or not ctx.user_id or not ctx.chat_id:
        return

    pending = ctx.captcha_repo.get_pending(ctx.chat_id, ctx.user_id)
    if not pending:
        return  # not a pending captcha user — ignore

    expected = pending["expected"]
    answer = ctx.text.strip()

    # Any non-answer text from a pending user is treated as a failed captcha attempt.
    if not re.match(rf"^\d{{{len(expected)}}}$", answer):
        _handle_wrong_captcha_attempt(ctx, pending)
        return

    if answer == expected:
        # ── Correct ─────────────────────────────────────────────────────────
        ctx.bot.restrict_chat_member(ctx.chat_id, ctx.user_id, _FULL_PERMISSIONS)
        ctx.captcha_repo.mark_verified(ctx.chat_id, ctx.user_id)

        # Delete captcha image, wrong-answer messages, and user's answer — keep system join message
        ids_to_delete = [pending["verify_msg_id"], ctx.message_id] + pending.get("wrong_msg_ids", [])
        for msg_id in ids_to_delete:
            try:
                ctx.bot.delete_message(ctx.chat_id, msg_id, ignore_not_found=True)
            except Exception:
                pass

        if ctx.stats_repo:
            ctx.stats_repo.increment_verified_users(ctx.chat_id)

        logger.info("User %s passed captcha.", ctx.user_id)

    else:
        # ── Wrong answer ─────────────────────────────────────────────────────
        _handle_wrong_captcha_attempt(ctx, pending)
