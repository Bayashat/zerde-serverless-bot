"""Automatic document summarization when a user uploads a supported file."""

from __future__ import annotations

from core.config import (
    TELEGRAM_CHANNEL_POST_ACTOR_USER_ID,
    get_chat_lang,
    get_gemini_api_key,
)
from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.explain_multimodal import document_auto_allowed
from services.repositories.explain_tasks import ExplainTaskRepository
from services.telegram import TelegramAPIError
from zerde_common.logging_utils import truncate_log_text

logger = LoggerAdapter(get_logger(__name__), {})

_PROCESSING_REACTION = "✍️"
_ERROR_REACTION = "🤡"

_task_repo: ExplainTaskRepository | None = None


def _get_task_repo() -> ExplainTaskRepository:
    global _task_repo
    if _task_repo is None:
        _task_repo = ExplainTaskRepository()
    return _task_repo


def _react(ctx: Context, emoji: str) -> None:
    try:
        ctx.bot.set_message_reaction(ctx.chat_id, ctx.message_id, emoji)
    except TelegramAPIError as e:
        logger.warning(
            "setMessageReaction failed for document auto",
            extra={
                "status": e.status,
                "body_preview": truncate_log_text(e.body, 200),
                "reaction": emoji,
            },
        )


def handle_document_auto_summary(ctx: Context) -> None:
    """Queue async Gemini summary for an uploaded document (no /command)."""
    lang = get_chat_lang(ctx.chat_id)
    if not get_gemini_api_key():
        return

    if not ctx.chat_id or not ctx.message_id or ctx.update_id is None or ctx.sqs_repo is None:
        return

    from_user = ctx.message.get("from") or {}
    if from_user.get("is_bot"):
        return
    if from_user.get("id") == TELEGRAM_CHANNEL_POST_ACTOR_USER_ID:
        return

    doc = ctx.message.get("document")
    if not isinstance(doc, dict):
        return

    allowed, reason_key = document_auto_allowed(doc)
    if not allowed:
        if reason_key:
            _react(ctx, _ERROR_REACTION)
            ctx.reply(get_translated_text(reason_key, lang), ctx.message_id)
        return

    file_id = doc.get("file_id")
    if not file_id:
        return

    mime = (doc.get("mime_type") or "application/octet-stream").strip()
    task_repo = _get_task_repo()
    if not task_repo.try_reserve_update(ctx.update_id):
        logger.info(
            "Duplicate document-auto update skipped",
            extra={"update_id": ctx.update_id, "chat_id": ctx.chat_id},
        )
        return

    _react(ctx, _PROCESSING_REACTION)
    caption = (ctx.message.get("caption") or "").strip()

    try:
        ctx.sqs_repo.send_explain_task(
            update_id=ctx.update_id,
            chat_id=ctx.chat_id,
            reply_to_message_id=ctx.message_id,
            term=caption,
            lang=lang,
            style="normal",
            file_id=str(file_id),
            mime_type=mime,
            media_kind="document",
            task_source="document_auto",
        )
        task_repo.mark_enqueued(ctx.update_id)
    except Exception:
        logger.exception("Failed to enqueue document auto task", extra={"update_id": ctx.update_id})
        try:
            task_repo.release_reservation(ctx.update_id)
        except Exception:
            logger.exception(
                "Failed to release document-auto reservation",
                extra={"update_id": ctx.update_id},
            )
        _react(ctx, _ERROR_REACTION)
        ctx.reply(get_translated_text("wtf_unexpected_error", lang), ctx.message_id)
