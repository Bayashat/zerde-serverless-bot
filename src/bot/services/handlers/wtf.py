"""/wtf command: explain a tech term via Gemini (primary) with Groq fallback."""

from core.config import GEMINI_API_KEY, GROQ_API_KEY, get_chat_lang
from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.ai.gemini_client import (
    GeminiClient,
    GeminiRPDExhaustedError,
    GeminiUnavailableError,
)
from services.ai.groq_client import GroqAPIError, GroqClient
from services.telegram import TelegramAPIError

logger = LoggerAdapter(get_logger(__name__), {})

_WTF_PROCESSING_REACTION = "✍️"

_gemini: GeminiClient | None = GeminiClient() if GEMINI_API_KEY else None
_groq: GroqClient | None = GroqClient() if GROQ_API_KEY else None


def _extract_term(ctx: Context) -> str:
    """Extract the term from command args or reply_to_message text."""
    parts = ctx.text.split(maxsplit=1)
    if len(parts) > 1:
        return parts[1].strip()

    if ctx.reply_to_message:
        return (ctx.reply_to_message.get("text") or "").strip()

    return ""


def _build_rpd_footer(lang: str) -> str:
    """Build footer showing Gemini RPD usage from the shared DynamoDB counter."""
    if not _gemini:
        return ""
    return get_translated_text("wtf_rpd_footer", lang, remaining=_gemini.remaining_rpd, total=_gemini.rpd_limit)


def _react_processing(ctx: Context) -> None:
    """Acknowledge the /wtf message with a reaction so the user sees we're working."""
    try:
        ctx.bot.set_message_reaction(ctx.chat_id, ctx.message_id, _WTF_PROCESSING_REACTION)
    except TelegramAPIError as e:
        logger.warning(
            "setMessageReaction failed for /wtf",
            extra={"status": e.status, "body": e.body[:200]},
        )


def _clear_processing_reaction(ctx: Context) -> None:
    """Remove the processing reaction after the reply is sent or on error."""
    if ctx.chat_id is None or ctx.message_id is None:
        return
    try:
        ctx.bot.clear_message_reaction(ctx.chat_id, ctx.message_id)
    except TelegramAPIError as e:
        logger.warning(
            "clearMessageReaction failed for /wtf",
            extra={"status": e.status, "body": e.body[:200]},
        )


def _send_typing_once(ctx: Context) -> None:
    """Show the typing indicator once (optional UX; failures are ignored in TelegramClient)."""
    if ctx.chat_id is not None:
        ctx.bot.send_chat_action(ctx.chat_id, "typing")


def _build_groq_takeover_intro(lang: str) -> str:
    """Build a playful intro shown when Groq handles the explanation."""
    return get_translated_text("wtf_groq_takeover_intro", lang)


def _groq_explain_and_reply(
    ctx: Context,
    term: str,
    lang: str,
    *,
    send_daily_quota_notice: bool,
) -> None:
    """Call Groq and send the explanation + RPD footer.

    If *send_daily_quota_notice* is True, send ``wtf_fallback_notice`` in a
    separate message first (Gemini daily RPD exhausted only).
    """
    assert _groq is not None

    if send_daily_quota_notice and _gemini is not None:
        ctx.reply(
            get_translated_text("wtf_fallback_notice", lang, total=_gemini.rpd_limit),
            ctx.message_id,
        )

    try:
        explanation = _groq.explain_term(term, lang)
    except (GroqAPIError, Exception):
        logger.exception("Groq failed for /wtf")
        ctx.reply(get_translated_text("wtf_api_error", lang), ctx.message_id)
        return

    intro = _build_groq_takeover_intro(lang)
    ctx.reply(f"{intro}\n\n<blockquote>{explanation}</blockquote>" + _build_rpd_footer(lang), ctx.message_id)


def handle_wtf(ctx: Context) -> None:
    """Handle /wtf: peek RPD, then Gemini or Groq with correct fallback messaging."""
    lang = get_chat_lang(ctx.chat_id)

    if not _gemini and not _groq:
        ctx.reply(get_translated_text("wtf_not_configured", lang), ctx.message_id)
        return

    term = _extract_term(ctx)
    if not term:
        ctx.reply(get_translated_text("wtf_usage", lang), ctx.message_id)
        return

    _react_processing(ctx)
    _send_typing_once(ctx)
    try:
        # Groq only (Gemini not configured)
        if not _gemini and _groq:
            try:
                explanation = _groq.explain_term(term, lang)
            except (GroqAPIError, Exception):
                logger.exception("Groq failed for /wtf (Groq-only mode)")
                ctx.reply(get_translated_text("wtf_api_error", lang), ctx.message_id)
                return
            intro = _build_groq_takeover_intro(lang)
            ctx.reply(f"{intro}\n\n{explanation}" + _build_rpd_footer(lang), ctx.message_id)
            return

        # Gemini only (no Groq fallback)
        if _gemini and not _groq:
            if _gemini.remaining_rpd <= 0:
                ctx.reply(
                    get_translated_text("wtf_gemini_exhausted_no_groq", lang),
                    ctx.message_id,
                )
                return
            try:
                explanation = _gemini.explain_term(term, lang)
            except GeminiRPDExhaustedError:
                ctx.reply(
                    get_translated_text("wtf_gemini_exhausted_no_groq", lang),
                    ctx.message_id,
                )
                return
            except GeminiUnavailableError:
                ctx.reply(get_translated_text("wtf_api_error", lang), ctx.message_id)
                return
            ctx.reply(explanation + _build_rpd_footer(lang), ctx.message_id)
            return

        # Both Gemini and Groq configured
        assert _gemini is not None and _groq is not None

        if _gemini.remaining_rpd <= 0:
            _groq_explain_and_reply(ctx, term, lang, send_daily_quota_notice=True)
            return

        try:
            explanation = _gemini.explain_term(term, lang)
        except GeminiRPDExhaustedError:
            _groq_explain_and_reply(ctx, term, lang, send_daily_quota_notice=True)
            return
        except GeminiUnavailableError:
            logger.warning("Gemini unavailable for /wtf, using Groq without daily notice")
            _groq_explain_and_reply(ctx, term, lang, send_daily_quota_notice=False)
            return

        ctx.reply(explanation + _build_rpd_footer(lang), ctx.message_id)

    except Exception:
        logger.exception("Unexpected error in /wtf handler")
        ctx.reply(get_translated_text("wtf_unexpected_error", lang), ctx.message_id)
    finally:
        # _clear_processing_reaction(ctx)
        pass
