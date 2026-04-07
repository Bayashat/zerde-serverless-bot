"""/wtf command: explain a tech term via Gemini (primary) with Groq fallback."""

from core.config import GEMINI_API_KEY, GROQ_API_KEY, get_chat_lang
from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.ai.gemini_client import GeminiClient, GeminiRateLimitError
from services.ai.groq_client import GroqAPIError, GroqClient

logger = LoggerAdapter(get_logger(__name__), {})

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


def handle_wtf(ctx: Context) -> None:
    """Handle /wtf -- Gemini primary, Groq fallback, RPD footer."""
    lang = get_chat_lang(ctx.chat_id)

    if not _gemini and not _groq:
        ctx.reply(get_translated_text("wtf_not_configured", lang), ctx.message_id)
        return

    term = _extract_term(ctx)
    if not term:
        ctx.reply(get_translated_text("wtf_usage", lang), ctx.message_id)
        return

    fallback_used = False
    explanation = ""

    try:
        if _gemini:
            explanation = _gemini.explain_term(term, lang)
        elif _groq:
            explanation = _groq.explain_term(term, lang)
            fallback_used = True
    except GeminiRateLimitError:
        logger.warning("Gemini rate-limited for /wtf, falling back to Groq")
        if _groq:
            try:
                explanation = _groq.explain_term(term, lang)
                fallback_used = True
            except (GroqAPIError, Exception):
                logger.exception("Groq fallback also failed for /wtf")
                ctx.reply(get_translated_text("wtf_api_error", lang), ctx.message_id)
                return
        else:
            ctx.reply(get_translated_text("wtf_api_error", lang), ctx.message_id)
            return
    except (GroqAPIError, RuntimeError):
        logger.exception("AI API call failed for /wtf")
        ctx.reply(get_translated_text("wtf_api_error", lang), ctx.message_id)
        return
    except Exception:
        logger.exception("Unexpected error in /wtf handler")
        ctx.reply(get_translated_text("wtf_unexpected_error", lang), ctx.message_id)
        return

    parts: list[str] = []
    if fallback_used:
        parts.append(get_translated_text("wtf_fallback_notice", lang))
    parts.append(explanation)
    parts.append(_build_rpd_footer(lang))

    ctx.reply("".join(parts), ctx.message_id)
