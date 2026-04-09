"""/wtf and /explain commands: explain tech terms via Gemini with fallback.

Usage: ``/wtf <term>`` or reply to a message with ``/wtf``. Explanation language comes from
``CHAT_LANG_MAP`` for the current chat (see ``get_chat_lang``).

Gemini RPD counts and remaining quota use the US Pacific calendar day
(America/Los_Angeles), aligned with Google's daily RPD reset at midnight PT.
"""

from core.config import DEEPSEEK_API_KEY, GEMINI_API_KEY, LLAMA_API_KEY, WTF_FALLBACK_PROVIDER, get_chat_lang
from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.ai.deepseek_client import DeepSeekAPIError, DeepSeekClient, DeepSeekRateLimitError
from services.ai.gemini_client import (
    GeminiClient,
    GeminiRPDExhaustedError,
    GeminiUnavailableError,
)
from services.ai.llama_client import LlamaAPIError, LlamaClient, LlamaRateLimitError
from services.ai.wtf_prompts import WTFPromptStyle
from services.telegram import TelegramAPIError

logger = LoggerAdapter(get_logger(__name__), {})

_WTF_PROCESSING_REACTION = "✍️"

_FALLBACK_RATE_LIMIT_ERRORS = (LlamaRateLimitError, DeepSeekRateLimitError)
_FALLBACK_API_ERRORS = (LlamaAPIError, DeepSeekAPIError)

_FallbackClient = DeepSeekClient | LlamaClient


def _make_fallback() -> _FallbackClient | None:
    """Select fallback client based on WTF_FALLBACK_PROVIDER; auto-detect if key is missing."""
    if WTF_FALLBACK_PROVIDER == "deepseek" and DEEPSEEK_API_KEY:
        return DeepSeekClient()
    if WTF_FALLBACK_PROVIDER == "llama" and LLAMA_API_KEY:
        return LlamaClient()
    # Auto-detect: prefer DeepSeek, then Llama
    if DEEPSEEK_API_KEY:
        return DeepSeekClient()
    if LLAMA_API_KEY:
        return LlamaClient()
    return None


_gemini: GeminiClient | None = GeminiClient() if GEMINI_API_KEY else None
_fallback: _FallbackClient | None = _make_fallback()


def _extract_term(ctx: Context) -> str:
    """Extract the term from command args or reply_to_message text."""
    parts = ctx.text.split(maxsplit=1)
    if len(parts) > 1:
        return parts[1].strip()

    if ctx.reply_to_message:
        return (ctx.reply_to_message.get("text") or "").strip()

    return ""


def _build_rpd_footer(lang: str) -> str:
    """Build footer showing Gemini RPD usage (DynamoDB counter; day = Pacific time)."""
    if not _gemini:
        return ""
    return get_translated_text(
        "wtf_rpd_footer",
        lang,
        remaining=_gemini.remaining_rpd,
        total=_gemini.rpd_limit,
    )


def _react_processing(ctx: Context) -> None:
    """Acknowledge the /wtf message with a reaction so the user sees we're working."""
    try:
        ctx.bot.set_message_reaction(ctx.chat_id, ctx.message_id, _WTF_PROCESSING_REACTION)
    except TelegramAPIError as e:
        logger.warning(
            "setMessageReaction failed for /wtf",
            extra={"status": e.status, "body": e.body[:200]},
        )


def _send_typing_once(ctx: Context) -> None:
    """Show the typing indicator once (optional UX; failures are ignored in TelegramClient)."""
    if ctx.chat_id is not None:
        ctx.bot.send_chat_action(ctx.chat_id, "typing")


def _fallback_explain_and_reply(
    ctx: Context,
    term: str,
    lang: str,
    style: WTFPromptStyle,
    *,
    send_daily_quota_notice: bool,
) -> None:
    """Call the configured fallback client and send the explanation + RPD footer.

    If *send_daily_quota_notice* is True, send ``wtf_fallback_notice`` first
    (Gemini daily RPD exhausted only).
    """
    assert _fallback is not None

    if send_daily_quota_notice and _gemini is not None:
        ctx.reply(
            get_translated_text("wtf_fallback_notice", lang, total=_gemini.rpd_limit),
            ctx.message_id,
        )

    try:
        explanation = _fallback.explain_term(term, lang, style=style)
    except _FALLBACK_RATE_LIMIT_ERRORS:
        logger.warning("Fallback API rate limit hit for /wtf", extra={"provider": WTF_FALLBACK_PROVIDER})
        ctx.reply(get_translated_text("wtf_fallback_rate_limit", lang), ctx.message_id)
        return
    except (*_FALLBACK_API_ERRORS, Exception):
        logger.exception("Fallback API failed for /wtf", extra={"provider": WTF_FALLBACK_PROVIDER})
        ctx.reply(get_translated_text("wtf_api_error", lang), ctx.message_id)
        return

    intro_key = "wtf_fallback_takeover_intro" if style == "angry" else "explain_fallback_takeover_intro"
    intro = get_translated_text(intro_key, lang)
    ctx.reply(f"{intro}\n<blockquote>{explanation}</blockquote>" + _build_rpd_footer(lang), ctx.message_id)


def _handle_term_explain(ctx: Context, *, style: WTFPromptStyle, command_name: str, usage_key: str) -> None:
    """Handle shared term-explainer flow with style-specific prompts."""
    lang = get_chat_lang(ctx.chat_id)

    if not _gemini and not _fallback:
        ctx.reply(get_translated_text("wtf_not_configured", lang), ctx.message_id)
        return

    term = _extract_term(ctx)
    if not term:
        ctx.reply(get_translated_text(usage_key, lang), ctx.message_id)
        return

    logger.info(command_name, extra={"term": term[:120], "lang": lang, "chat_id": ctx.chat_id})

    _react_processing(ctx)
    _send_typing_once(ctx)
    try:
        # Fallback only (Gemini not configured)
        if not _gemini and _fallback:
            try:
                explanation = _fallback.explain_term(term, lang, style=style)
            except _FALLBACK_RATE_LIMIT_ERRORS:
                logger.warning("Fallback rate limit hit for explainer command (fallback-only mode)")
                ctx.reply(get_translated_text("wtf_fallback_rate_limit", lang), ctx.message_id)
                return
            except (*_FALLBACK_API_ERRORS, Exception):
                logger.exception("Fallback failed for explainer command (fallback-only mode)")
                ctx.reply(get_translated_text("wtf_api_error", lang), ctx.message_id)
                return
            intro_key = "wtf_fallback_takeover_intro" if style == "angry" else "explain_fallback_takeover_intro"
            intro = get_translated_text(intro_key, lang)
            ctx.reply(f"{intro}\n\n<blockquote>{explanation}</blockquote>" + _build_rpd_footer(lang), ctx.message_id)
            return

        # Gemini only (no fallback configured)
        if _gemini and not _fallback:
            if _gemini.remaining_rpd <= 0:
                ctx.reply(
                    get_translated_text("wtf_gemini_exhausted_no_fallback", lang),
                    ctx.message_id,
                )
                return
            try:
                explanation = _gemini.explain_term(term, lang, style=style)
            except GeminiRPDExhaustedError:
                ctx.reply(
                    get_translated_text("wtf_gemini_exhausted_no_fallback", lang),
                    ctx.message_id,
                )
                return
            except GeminiUnavailableError:
                ctx.reply(get_translated_text("wtf_api_error", lang), ctx.message_id)
                return
            ctx.reply("<blockquote>" + explanation + "</blockquote>" + _build_rpd_footer(lang), ctx.message_id)
            return

        # Both Gemini and fallback configured
        assert _gemini is not None and _fallback is not None

        if _gemini.remaining_rpd <= 0:
            _fallback_explain_and_reply(ctx, term, lang, style, send_daily_quota_notice=True)
            return

        try:
            explanation = _gemini.explain_term(term, lang, style=style)
        except GeminiRPDExhaustedError:
            _fallback_explain_and_reply(ctx, term, lang, style, send_daily_quota_notice=True)
            return
        except GeminiUnavailableError:
            logger.warning("Gemini unavailable for explainer command, using fallback without daily notice")
            _fallback_explain_and_reply(ctx, term, lang, style, send_daily_quota_notice=False)
            return

        ctx.reply("<blockquote>" + explanation + "</blockquote>" + _build_rpd_footer(lang), ctx.message_id)

    except Exception:
        logger.exception("Unexpected error in explainer handler")
        ctx.reply(get_translated_text("wtf_unexpected_error", lang), ctx.message_id)


def handle_wtf(ctx: Context) -> None:
    """Handle /wtf using the angry prompt style."""
    _handle_term_explain(ctx, style="angry", command_name="/wtf", usage_key="wtf_usage")


def handle_explain(ctx: Context) -> None:
    """Handle /explain using the normal prompt style."""
    _handle_term_explain(ctx, style="normal", command_name="/explain", usage_key="explain_usage")
