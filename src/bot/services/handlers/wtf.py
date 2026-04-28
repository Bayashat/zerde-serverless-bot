"""Async /wtf and /explain handlers with SQS offload and dedup."""

from __future__ import annotations

import time
from typing import Callable, cast

from core.config import get_chat_lang, get_deepseek_api_key, get_gemini_api_key
from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.ai.deepseek_client import DeepSeekAPIError, DeepSeekClient, DeepSeekRateLimitError
from services.ai.gemini_client import GeminiClient, GeminiRPDExhaustedError, GeminiUnavailableError
from services.ai.telegram_html import normalize_llm_output_for_telegram_html
from services.ai.wtf_prompts import WTFPromptStyle
from services.explain_multimodal import extract_reply_media
from services.repositories.explain_tasks import ExplainTaskRepository
from services.telegram import TelegramAPIError, TelegramClient
from zerde_common.logging_utils import truncate_log_text

logger = LoggerAdapter(get_logger(__name__), {})

_WTF_PROCESSING_REACTION = "✍️"
_WTF_ERROR_REACTION = "🤡"

_FALLBACK_RATE_LIMIT_ERRORS = (DeepSeekRateLimitError,)
_FALLBACK_API_ERRORS = (DeepSeekAPIError,)

_FallbackClient = DeepSeekClient


_gemini: GeminiClient | None = None
_fallback: _FallbackClient | None = None
_task_repo: ExplainTaskRepository | None = None


def _get_gemini() -> GeminiClient | None:
    global _gemini
    if get_gemini_api_key() and _gemini is None:
        _gemini = GeminiClient()
    return _gemini


def _get_fallback() -> _FallbackClient | None:
    global _fallback
    if get_deepseek_api_key() and _fallback is None:
        _fallback = DeepSeekClient()
    return _fallback


def _get_task_repo() -> ExplainTaskRepository:
    global _task_repo
    if _task_repo is None:
        _task_repo = ExplainTaskRepository()
    return _task_repo


def _extract_term(ctx: Context) -> str:
    parts = ctx.text.split(maxsplit=1)
    if len(parts) > 1:
        return parts[1].strip()
    if ctx.reply_to_message:
        return (ctx.reply_to_message.get("text") or "").strip()
    # External replies (cross-chat forwards) have no reply_to_message;
    # Telegram instead populates `quote.text` with the selected fragment.
    quote_text = (ctx.message.get("quote") or {}).get("text") or ""
    if quote_text:
        return quote_text.strip()
    return ""


def _build_rpd_footer(lang: str, used_count: int | None = None) -> str:
    gemini = _get_gemini()
    if not gemini:
        return ""
    # Prefer the count returned by explain_term() to avoid a second DynamoDB read.
    # Falls back to a live read only on the fallback/error path where count is unavailable.
    remaining = max(0, gemini.rpd_limit - used_count) if used_count is not None else gemini.remaining_rpd
    logger.info("RPD limit", extra={"remaining": remaining, "total": gemini.rpd_limit})
    return get_translated_text(
        "wtf_rpd_footer",
        lang,
        remaining=remaining,
        total=gemini.rpd_limit,
    )


def _react_processing(ctx: Context, reaction: str = _WTF_PROCESSING_REACTION) -> None:
    try:
        ctx.bot.set_message_reaction(ctx.chat_id, ctx.message_id, reaction)
    except TelegramAPIError as e:
        logger.warning(
            "setMessageReaction failed for /wtf",
            extra={
                "status": e.status,
                "body_preview": truncate_log_text(e.body, 200),
                "reaction": reaction,
            },
        )


def _send_typing_once(ctx: Context) -> None:
    if ctx.chat_id is not None:
        ctx.bot.send_chat_action(ctx.chat_id, "typing")


def _send_reply(bot: TelegramClient, chat_id: int, reply_to_message_id: int, text: str) -> None:
    bot.send_message(chat_id, text, reply_to_message_id=reply_to_message_id)


def _fallback_explain_and_reply(
    *,
    send_reply: Callable[[str], None],
    term: str,
    lang: str,
    style: WTFPromptStyle,
    send_daily_quota_notice: bool,
) -> None:
    fallback = _get_fallback()
    assert fallback is not None
    gemini = _get_gemini()

    if send_daily_quota_notice and gemini is not None:
        send_reply(get_translated_text("wtf_fallback_notice", lang, total=gemini.rpd_limit))

    try:
        explanation = fallback.explain_term(term, lang, style=style)
    except _FALLBACK_RATE_LIMIT_ERRORS:
        logger.warning("Fallback API rate limit hit for /wtf", extra={"provider": "deepseek"})
        send_reply(get_translated_text("wtf_fallback_rate_limit", lang))
        return
    except (*_FALLBACK_API_ERRORS, Exception):
        logger.exception("Fallback API failed for /wtf", extra={"provider": "deepseek"})
        send_reply(get_translated_text("wtf_api_error", lang))
        return

    intro_key = "wtf_fallback_takeover_intro" if style == "angry" else "explain_fallback_takeover_intro"
    intro = get_translated_text(intro_key, lang)
    explanation_html = normalize_llm_output_for_telegram_html(explanation)
    send_reply(f"{intro}\n<blockquote>{explanation_html}</blockquote>" + _build_rpd_footer(lang))


def _execute_explain_and_reply(
    *,
    bot: TelegramClient,
    chat_id: int,
    reply_to_message_id: int,
    term: str,
    lang: str,
    style: WTFPromptStyle,
) -> None:
    def send_reply(text: str) -> None:
        _send_reply(bot, chat_id, reply_to_message_id, text)

    gemini = _get_gemini()
    fallback = _get_fallback()

    if not gemini and not fallback:
        send_reply(get_translated_text("wtf_not_configured", lang))
        return

    if not gemini and fallback:
        try:
            explanation = fallback.explain_term(term, lang, style=style)
        except _FALLBACK_RATE_LIMIT_ERRORS:
            send_reply(get_translated_text("wtf_fallback_rate_limit", lang))
            return
        except (*_FALLBACK_API_ERRORS, Exception):
            logger.exception("Fallback failed for explainer command (fallback-only mode)")
            send_reply(get_translated_text("wtf_api_error", lang))
            return
        intro_key = "wtf_fallback_takeover_intro" if style == "angry" else "explain_fallback_takeover_intro"
        intro = get_translated_text(intro_key, lang)
        explanation_html = normalize_llm_output_for_telegram_html(explanation)
        send_reply(f"{intro}\n\n<blockquote>{explanation_html}</blockquote>" + _build_rpd_footer(lang))
        return

    if gemini and not fallback:
        try:
            explanation, used_count = gemini.explain_term(term, lang, style=style)
        except GeminiRPDExhaustedError:
            send_reply(get_translated_text("wtf_gemini_exhausted_no_fallback", lang))
            return
        except GeminiUnavailableError:
            send_reply(get_translated_text("wtf_api_error", lang))
            return
        explanation_html = normalize_llm_output_for_telegram_html(explanation)
        send_reply("<blockquote>" + explanation_html + "</blockquote>" + _build_rpd_footer(lang, used_count))
        return

    assert gemini is not None and fallback is not None

    try:
        explanation, used_count = gemini.explain_term(term, lang, style=style)
    except GeminiRPDExhaustedError:
        _fallback_explain_and_reply(
            send_reply=send_reply,
            term=term,
            lang=lang,
            style=style,
            send_daily_quota_notice=True,
        )
        return
    except GeminiUnavailableError:
        logger.warning("Gemini unavailable for explainer command, using fallback without daily notice")
        _fallback_explain_and_reply(
            send_reply=send_reply,
            term=term,
            lang=lang,
            style=style,
            send_daily_quota_notice=False,
        )
        return

    explanation_html = normalize_llm_output_for_telegram_html(explanation)
    send_reply("<blockquote>" + explanation_html + "</blockquote>" + _build_rpd_footer(lang, used_count))


def _execute_multimodal_explain_and_reply(
    *,
    bot: TelegramClient,
    chat_id: int,
    reply_to_message_id: int,
    lang: str,
    file_id: str,
    mime_type: str,
    media_kind: str,
    extra_user_text: str,
    task_source: str,
) -> None:
    """Download Telegram file and call Gemini multimodal (no DeepSeek)."""

    def send_reply(text: str) -> None:
        _send_reply(bot, chat_id, reply_to_message_id, text)

    gemini = _get_gemini()
    if not gemini:
        send_reply(get_translated_text("explain_multimodal_gemini_required", lang))
        return

    try:
        meta = bot.get_file(file_id)
        path = meta.get("file_path")
        if not path:
            logger.error("getFile missing file_path", extra={"file_id": file_id[:32]})
            send_reply(get_translated_text("wtf_api_error", lang))
            return
        raw = bot.download_file(str(path))
    except ValueError:
        logger.warning("Telegram file exceeds size limit", extra={"file_id": file_id[:32], "task_source": task_source})
        send_reply(get_translated_text("explain_media_file_too_large", lang))
        return
    except TelegramAPIError as e:
        logger.warning(
            "Telegram getFile/download failed",
            extra={"status": e.status, "task_source": task_source, "preview": truncate_log_text(e.body, 120)},
        )
        send_reply(get_translated_text("wtf_api_error", lang))
        return

    try:
        explanation, used_count = gemini.explain_media(
            media_kind=media_kind,
            file_bytes=raw,
            mime_type=mime_type,
            lang=lang,
            extra_user_text=extra_user_text,
        )
    except GeminiRPDExhaustedError:
        send_reply(get_translated_text("wtf_gemini_exhausted_no_fallback", lang))
        return
    except GeminiUnavailableError:
        send_reply(get_translated_text("wtf_api_error", lang))
        return

    explanation_html = normalize_llm_output_for_telegram_html(explanation)
    send_reply("<blockquote>" + explanation_html + "</blockquote>" + _build_rpd_footer(lang, used_count))


def _enqueue_term_explain(
    ctx: Context,
    *,
    style: WTFPromptStyle,
    command_name: str,
    usage_key: str,
    allow_media: bool = False,
) -> None:
    lang = get_chat_lang(ctx.chat_id)

    if not get_gemini_api_key() and not get_deepseek_api_key():
        _react_processing(ctx, _WTF_ERROR_REACTION)
        ctx.reply(get_translated_text("wtf_not_configured", lang), ctx.message_id)
        return

    if allow_media and ctx.reply_to_message:
        media = extract_reply_media(ctx.reply_to_message)
        if media:
            if not get_gemini_api_key():
                _react_processing(ctx, _WTF_ERROR_REACTION)
                ctx.reply(get_translated_text("explain_multimodal_gemini_required", lang), ctx.message_id)
                return
            if ctx.chat_id is None or ctx.message_id is None or ctx.update_id is None or ctx.sqs_repo is None:
                _react_processing(ctx, _WTF_ERROR_REACTION)
                logger.error(
                    "Missing context for async explain media enqueue",
                    extra={"chat_id": ctx.chat_id, "message_id": ctx.message_id, "update_id": ctx.update_id},
                )
                ctx.reply(get_translated_text("wtf_unexpected_error", lang), ctx.message_id)
                return

            media_kind, fid, mime = media
            extra = _extract_term(ctx)

            logger.info(
                "Received explain media command",
                extra={
                    "command": command_name,
                    "media_kind": media_kind,
                    "lang": lang,
                    "chat_id": ctx.chat_id,
                    "update_id": ctx.update_id,
                },
            )

            task_repo = _get_task_repo()
            if not task_repo.try_reserve_update(ctx.update_id):
                _react_processing(ctx, _WTF_ERROR_REACTION)
                logger.info(
                    "Duplicate explain media update skipped",
                    extra={"update_id": ctx.update_id, "chat_id": ctx.chat_id},
                )
                return

            _react_processing(ctx, _WTF_PROCESSING_REACTION)
            _send_typing_once(ctx)

            try:
                ctx.sqs_repo.send_explain_task(
                    update_id=ctx.update_id,
                    chat_id=ctx.chat_id,
                    reply_to_message_id=ctx.message_id,
                    term=extra,
                    lang=lang,
                    style=style,
                    file_id=fid,
                    mime_type=mime,
                    media_kind=media_kind,
                    task_source="explain_reply",
                )
                task_repo.mark_enqueued(ctx.update_id)
            except Exception:
                logger.exception("Failed to enqueue explain media task", extra={"update_id": ctx.update_id})
                try:
                    task_repo.release_reservation(ctx.update_id)
                except Exception:
                    logger.exception(
                        "Failed to release explain media reservation",
                        extra={"update_id": ctx.update_id},
                    )
                ctx.reply(get_translated_text("wtf_unexpected_error", lang), ctx.message_id)
            return

    term = _extract_term(ctx)
    if not term:
        _react_processing(ctx, _WTF_ERROR_REACTION)
        ctx.reply(get_translated_text(usage_key, lang), ctx.message_id)
        return

    if ctx.chat_id is None or ctx.message_id is None or ctx.update_id is None or ctx.sqs_repo is None:
        _react_processing(ctx, _WTF_ERROR_REACTION)
        logger.error(
            "Missing context for async explain enqueue",
            extra={"chat_id": ctx.chat_id, "message_id": ctx.message_id, "update_id": ctx.update_id},
        )
        ctx.reply(get_translated_text("wtf_unexpected_error", lang), ctx.message_id)
        return

    logger.info(
        "Received explain command",
        extra={
            "command": command_name,
            "term": term[:120],
            "lang": lang,
            "chat_id": ctx.chat_id,
            "update_id": ctx.update_id,
        },
    )

    task_repo = _get_task_repo()
    if not task_repo.try_reserve_update(ctx.update_id):
        _react_processing(ctx, _WTF_ERROR_REACTION)
        logger.info("Duplicate explain update skipped", extra={"update_id": ctx.update_id, "chat_id": ctx.chat_id})
        return

    _react_processing(ctx, _WTF_PROCESSING_REACTION)
    _send_typing_once(ctx)

    try:
        ctx.sqs_repo.send_explain_task(
            update_id=ctx.update_id,
            chat_id=ctx.chat_id,
            reply_to_message_id=ctx.message_id,
            term=term,
            lang=lang,
            style=style,
            task_source="explain_text",
        )
        task_repo.mark_enqueued(ctx.update_id)
    except Exception:
        logger.exception("Failed to enqueue explain task", extra={"update_id": ctx.update_id})
        try:
            task_repo.release_reservation(ctx.update_id)
        except Exception:
            logger.exception(
                "Failed to release explain reservation after enqueue error",
                extra={"update_id": ctx.update_id},
            )
        ctx.reply(get_translated_text("wtf_unexpected_error", lang), ctx.message_id)


def process_explain_task(bot: TelegramClient, body: dict[str, object]) -> None:
    """Process a previously enqueued async explain task from SQS."""
    started = time.monotonic()

    try:
        update_id = int(body["update_id"])
        chat_id = int(body["chat_id"])
        reply_to_message_id = int(body["reply_to_message_id"])
        term = str(body.get("term", "")).strip()
        lang = str(body["lang"]).strip()
        style = str(body["style"]).strip()
    except (KeyError, TypeError, ValueError):
        logger.exception("Invalid PROCESS_EXPLAIN payload", extra={"body": body})
        return

    file_id = body.get("file_id")
    has_media = isinstance(file_id, str) and bool(file_id.strip())
    task_source = str(body.get("task_source", "explain_text"))

    if not has_media and not term:
        logger.warning("PROCESS_EXPLAIN received empty term", extra={"update_id": update_id})
        return

    if style not in {"angry", "normal"}:
        logger.warning("PROCESS_EXPLAIN received invalid style", extra={"update_id": update_id, "style": style})
        return

    media_kind = ""
    mime_type = "application/octet-stream"
    if has_media:
        media_kind = str(body.get("media_kind") or "").strip()
        if media_kind not in {"voice", "audio", "photo", "document"}:
            logger.warning(
                "PROCESS_EXPLAIN invalid media_kind",
                extra={"update_id": update_id, "media_kind": media_kind},
            )
            _get_task_repo().mark_completed(update_id)
            return
        mime_type = str(body.get("mime_type") or "application/octet-stream").strip() or "application/octet-stream"

    try:
        if has_media:
            _execute_multimodal_explain_and_reply(
                bot=bot,
                chat_id=chat_id,
                reply_to_message_id=reply_to_message_id,
                lang=lang,
                file_id=str(file_id).strip(),
                mime_type=mime_type,
                media_kind=media_kind,
                extra_user_text=term,
                task_source=task_source,
            )
        else:
            _execute_explain_and_reply(
                bot=bot,
                chat_id=chat_id,
                reply_to_message_id=reply_to_message_id,
                term=term,
                lang=lang,
                style=cast(WTFPromptStyle, style),
            )
        _get_task_repo().mark_completed(update_id)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "PROCESS_EXPLAIN completed",
            extra={
                "update_id": update_id,
                "chat_id": chat_id,
                "provider_latency_ms": elapsed_ms,
                "task_source": task_source,
                "has_media": has_media,
            },
        )
    except Exception:
        logger.exception("PROCESS_EXPLAIN failed", extra={"update_id": update_id, "chat_id": chat_id})
        raise


def handle_wtf(ctx: Context) -> None:
    _enqueue_term_explain(ctx, style="angry", command_name="/wtf", usage_key="wtf_usage")


def handle_explain(ctx: Context) -> None:
    _enqueue_term_explain(
        ctx,
        style="normal",
        command_name="/explain",
        usage_key="explain_usage",
        allow_media=True,
    )
