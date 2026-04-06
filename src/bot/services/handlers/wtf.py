"""/wtf command: explain a tech term in humorous Kazakh via Groq API."""

from core.config import GROQ_API_KEY
from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.ai.groq_client import GroqAPIError, GroqClient

logger = LoggerAdapter(get_logger(__name__), {})

_groq: GroqClient | None = GroqClient() if GROQ_API_KEY else None


def _extract_term(ctx: Context) -> str:
    """Extract the term from command args or reply_to_message text."""
    parts = ctx.text.split(maxsplit=1)
    if len(parts) > 1:
        return parts[1].strip()

    if ctx.reply_to_message:
        return (ctx.reply_to_message.get("text") or "").strip()

    return ""


def handle_wtf(ctx: Context) -> None:
    """Handle /wtf — explain a tech term with humor."""
    lang = ctx.lang_code

    if not _groq:
        ctx.reply(get_translated_text("wtf_not_configured", lang), ctx.message_id)
        return

    term = _extract_term(ctx)
    if not term:
        ctx.reply(get_translated_text("wtf_usage", lang), ctx.message_id)
        return

    try:
        explanation = _groq.explain_term(term)
        ctx.reply(explanation, ctx.message_id)
    except GroqAPIError:
        logger.exception("Groq API call failed for /wtf")
        ctx.reply(get_translated_text("wtf_api_error", lang), ctx.message_id)
    except Exception:
        logger.exception("Unexpected error in /wtf handler")
        ctx.reply(get_translated_text("wtf_unexpected_error", lang), ctx.message_id)
