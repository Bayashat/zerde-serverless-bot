"""Captcha verification: grid image challenge, answer checking, timeout kick."""

import time
from typing import Any

from core.config import CAPTCHA_MAX_ATTEMPTS, CAPTCHA_TIMEOUT_SECONDS
from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from core.utils import format_mention
from services.captcha_image import generate_grid_captcha
from services.repositories.captcha import (
    TERMINAL_STATUSES,
    CaptchaBusyError,
    CaptchaRetryRequiredError,
    action_completed,
)
from services.repositories.sqs import SQSClient
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


def _delete_messages(bot: TelegramClient, chat_id: int | str, message_ids: list[int]) -> None:
    # Cleanup is best effort; it must not undo a durable verification decision.
    for message_id in dict.fromkeys(int(value) for value in message_ids if value):
        try:
            bot.delete_message(chat_id, message_id, ignore_not_found=True)
        except Exception:
            logger.warning("Captcha message cleanup failed", extra={"chat_id": chat_id, "message_id": message_id})


def _is_captcha_text_only_restricted(member: dict[str, Any]) -> bool:
    return (
        member.get("status") == "restricted"
        and member.get("can_send_messages") is True
        and all(member.get(permission) is False for permission in _CAPTCHA_BLOCKED_PERMISSIONS)
    )


def _matches_task(challenge: dict[str, Any], task: dict[str, Any]) -> bool:
    if int(challenge["join_msg_id"]) != int(task.get("join_message_id") or 0):
        return False
    if task.get("generation"):
        return challenge.get("generation") == task["generation"]
    # Old CHECK_TIMEOUT messages may still be in SQS/DLQ. Never fall back to
    # inspecting permissions without proving the exact old challenge identity.
    return bool(task.get("verification_message_id")) and int(challenge.get("verify_msg_id", 0)) == int(
        task["verification_message_id"]
    )


def _schedule_recovery(sqs_repo, chat_id, user_id, challenge, *, delay_seconds=None) -> None:
    remaining = max(1, int(challenge.get("expires_at", 0)) - int(time.time()))
    sqs_repo.send_timeout_task(
        chat_id,
        user_id,
        join_message_id=int(challenge["join_msg_id"]),
        verification_message_id=int(challenge.get("verify_msg_id", 0)),
        generation=challenge.get("generation"),
        delay_seconds=remaining if delay_seconds is None else delay_seconds,
    )


def _cleanup_decision(bot, chat_id, challenge) -> None:
    ids = [challenge.get("verify_msg_id"), challenge.get("answer_msg_id"), *challenge.get("wrong_msg_ids", [])]
    if challenge.get("status") == "rejected":
        ids.append(challenge["join_msg_id"])
    _delete_messages(bot, chat_id, ids)


def _apply_decision(repo, bot, chat_id, user_id, challenge, *, stats_repo=None):
    """Reconcile a durable decision; ambiguous Telegram results remain pending.

    A live lease protects against a newer join replacing this generation. A
    readback avoids repeating an already-applied kick/unrestrict after a lost
    response. Telegram and DynamoDB cannot provide an atomic exactly-once send.
    """
    if challenge.get("status") not in TERMINAL_STATUSES or action_completed(challenge):
        return challenge
    member = bot.get_chat_member(chat_id, user_id)
    if not isinstance(member, dict) or member.get("status") not in {
        "member",
        "restricted",
        "left",
        "kicked",
        "administrator",
        "creator",
    }:
        raise CaptchaRetryRequiredError("Captcha member state could not be verified")
    repo.assert_owned(challenge)
    outcome = "already_applied_or_permissions_changed"
    if _is_captcha_text_only_restricted(member):
        if challenge["status"] == "rejected":
            bot.kick_chat_member(chat_id, user_id)
            outcome = "kicked"
        else:
            bot.restrict_chat_member(chat_id, user_id, _FULL_PERMISSIONS)
            outcome = "unrestricted"
    # Never override an administrator's different restriction or promotion.
    challenge = repo.save(challenge, action_done=True, action_result=outcome, completed_at=int(time.time()))
    if challenge["status"] == "verified" and stats_repo:
        try:
            stats_repo.increment_verified_users(chat_id)
        except Exception:
            logger.warning("Captcha verification stats update failed", extra={"chat_id": chat_id})
    _cleanup_decision(bot, chat_id, challenge)
    return challenge


def process_timeout_task(bot: TelegramClient, task_data: dict[str, Any]) -> None:
    """Decide timeout or resume an action for this exact generation only."""
    chat_id, user_id = task_data.get("chat_id"), task_data.get("user_id")
    if not chat_id or not user_id or not task_data.get("join_message_id"):
        raise ValueError("Captcha timeout task lacks challenge identity")
    repo = task_data.get("_captcha_repo")
    if repo is None:
        raise CaptchaRetryRequiredError("Captcha timeout requires its state repository")
    challenge = repo.get_challenge(chat_id, user_id)
    if not challenge or not _matches_task(challenge, task_data):
        logger.info("Ignoring missing or superseded captcha timeout", extra={"chat_id": chat_id, "user_id": user_id})
        return
    if action_completed(challenge):
        _cleanup_decision(bot, chat_id, challenge)
        return
    sqs_repo = task_data.get("_sqs_repo") or SQSClient()
    try:
        owned = repo.acquire(challenge)
    except CaptchaBusyError as exc:
        _schedule_recovery(sqs_repo, chat_id, user_id, challenge, delay_seconds=exc.retry_after)
        return
    try:
        status = owned.get("status", "pending")
        if status == "pending":
            expires_at = int(owned.get("expires_at", owned.get("ttl", 0)))
            if expires_at > int(time.time()):
                _schedule_recovery(sqs_repo, chat_id, user_id, owned, delay_seconds=expires_at - int(time.time()))
                return
            owned = repo.save(owned, status="rejected", decision_reason="timeout", decided_at=int(time.time()))
        elif status in {"preparing", "creating"}:
            # A crash before activation must restore permissions, never kick a
            # person who may not have received a usable challenge.
            owned = repo.save(
                owned, status="cancelled", decision_reason="creation_incomplete", decided_at=int(time.time())
            )
        elif status not in TERMINAL_STATUSES:
            raise ValueError("Unknown captcha lifecycle state")
        _apply_decision(repo, bot, chat_id, user_id, owned)
    finally:
        repo.release(owned)


def _create_challenge(ctx: Context, member: dict[str, Any]) -> None:
    repo, sqs_repo = ctx.captcha_repo, ctx.sqs_repo
    if repo is None or sqs_repo is None:
        raise CaptchaRetryRequiredError("Captcha creation requires state and recovery queue")
    user_id = int(member["id"])
    challenge = repo.prepare(ctx.chat_id, user_id, int(ctx.message_id))
    if challenge is None or action_completed(challenge) or challenge.get("status") == "pending":
        return
    owned = repo.acquire(challenge)
    try:
        if owned["status"] != "preparing":
            if owned["status"] == "creating":
                owned = repo.save(owned, status="cancelled", decision_reason="creation_incomplete")
            _apply_decision(repo, ctx.bot, ctx.chat_id, user_id, owned, stats_repo=ctx.stats_repo)
            return
        # No member is restricted until durable state AND a recovery message
        # exist. If enqueue response is lost, duplicates are identity-scoped.
        _schedule_recovery(sqs_repo, ctx.chat_id, user_id, owned)
        image_bytes, expected = generate_grid_captcha()
        owned = repo.save(owned, status="creating", expected=expected)
        try:
            repo.assert_owned(owned)
            ctx.bot.restrict_chat_member(ctx.chat_id, user_id, _TEXT_ONLY_PERMISSIONS)
            mention = format_mention(user_id, member.get("username"), member.get("first_name", "User"))
            caption = get_translated_text(
                "captcha_image_challenge", ctx.lang_code, MENTION=mention, TIMEOUT=CAPTCHA_TIMEOUT_SECONDS
            )
            sent = ctx.bot.send_photo(ctx.chat_id, image_bytes, caption=caption)
            verify_msg_id = sent.get("message_id") if isinstance(sent, dict) else None
            if not isinstance(verify_msg_id, int) or verify_msg_id <= 0:
                raise RuntimeError("Captcha image delivery has no confirmed message id")
            owned = repo.save(
                owned,
                status="pending",
                verify_msg_id=verify_msg_id,
                expires_at=int(time.time()) + CAPTCHA_TIMEOUT_SECONDS,
            )
        except Exception:
            # A successful write whose response was lost can already be PENDING.
            # Never overwrite that state with a stale snapshot. Failed reads or
            # writes propagate; the pre-existing queue message recovers later.
            actual = repo.get_challenge(ctx.chat_id, user_id)
            if actual and actual.get("lease_owner") == owned["lease_owner"] and actual.get("status") == "pending":
                owned = actual
            else:
                if actual and actual.get("lease_owner") == owned["lease_owner"]:
                    owned = actual
                owned = repo.save(owned, status="cancelled", decision_reason="creation_failed")
                _apply_decision(repo, ctx.bot, ctx.chat_id, user_id, owned)
                logger.warning("Captcha creation cancelled; permissions reconciled", extra={"chat_id": ctx.chat_id})
                return
        if ctx.stats_repo:
            try:
                ctx.stats_repo.increment_total_joins(ctx.chat_id)
            except Exception:
                logger.warning("Captcha join stats update failed", extra={"chat_id": ctx.chat_id})
    finally:
        repo.release(owned)


def handle_new_member(ctx: Context) -> None:
    """Start/recover each join independently; failed joins request redelivery."""
    failures = []
    for member in ctx.message.get("new_chat_members", []):
        if member.get("is_bot"):
            continue
        try:
            _create_challenge(ctx, member)
        except Exception as exc:
            failures.append(exc)
    if failures:
        raise CaptchaRetryRequiredError("Captcha join processing requires retry") from failures[0]


def handle_captcha_answer(ctx: Context) -> None:
    """Persist an immutable decision before any kick or unrestriction."""
    if not ctx.captcha_repo or not ctx.user_id or not ctx.chat_id:
        return
    try:
        _handle_captcha_answer(ctx)
    except Exception as exc:
        raise CaptchaRetryRequiredError("Captcha answer processing requires retry") from exc


def _handle_captcha_answer(ctx: Context) -> None:
    repo = ctx.captcha_repo
    challenge = repo.get_pending(ctx.chat_id, ctx.user_id)
    if not challenge:
        return
    # Telegram message ids identify the input's generation, including edits of
    # old messages delivered after a rejoin. Messages sent before the challenge
    # photo cannot be answers to it and must not consume attempts or be deleted.
    answer_boundary = max(int(challenge.get("join_msg_id", 0)), int(challenge.get("verify_msg_id", 0)))
    if not ctx.message_id or int(ctx.message_id) <= answer_boundary:
        return
    owned = repo.acquire(challenge)
    try:
        status = owned.get("status", "pending")
        if status in TERMINAL_STATUSES:
            _apply_decision(repo, ctx.bot, ctx.chat_id, ctx.user_id, owned, stats_repo=ctx.stats_repo)
            return
        if status != "pending":
            raise CaptchaRetryRequiredError("Captcha challenge is not ready")
        now = int(time.time())
        if int(owned.get("expires_at", owned.get("ttl", 0))) <= now:
            owned = repo.save(owned, status="rejected", decision_reason="timeout", decided_at=now)
        elif ctx.message_id not in owned.get("handled_message_ids", []):
            handled = [*owned.get("handled_message_ids", []), ctx.message_id]
            if ctx.text.strip() == owned["expected"]:
                owned = repo.save(
                    owned,
                    status="verified",
                    decision_reason="correct_answer",
                    decided_at=now,
                    handled_message_ids=handled,
                    answer_msg_id=ctx.message_id,
                )
            else:
                attempts = int(owned.get("attempts", 0)) + 1
                changes = {
                    "attempts": attempts,
                    "handled_message_ids": handled,
                    "wrong_msg_ids": [*owned.get("wrong_msg_ids", []), ctx.message_id],
                }
                if attempts >= CAPTCHA_MAX_ATTEMPTS:
                    changes.update(status="rejected", decision_reason="wrong_attempts", decided_at=now)
                owned = repo.save(owned, **changes)
                _delete_messages(ctx.bot, ctx.chat_id, [ctx.message_id])
                if attempts < CAPTCHA_MAX_ATTEMPTS:
                    try:
                        reply = ctx.reply(
                            get_translated_text(
                                "captcha_wrong_answer", ctx.lang_code, ATTEMPTS_LEFT=CAPTCHA_MAX_ATTEMPTS - attempts
                            ),
                            reply_to_message_id=int(owned["verify_msg_id"]),
                        )
                    except Exception:
                        logger.warning(
                            "Captcha wrong-answer notice could not be completed", extra={"chat_id": ctx.chat_id}
                        )
                        return
                    if reply and reply.get("message_id"):
                        owned = repo.save(owned, wrong_msg_ids=[*owned["wrong_msg_ids"], reply["message_id"]])
                    return
        _apply_decision(repo, ctx.bot, ctx.chat_id, ctx.user_id, owned, stats_repo=ctx.stats_repo)
    finally:
        repo.release(owned)
