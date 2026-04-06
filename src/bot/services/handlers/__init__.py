"""Handler registration: wires domain handlers to the Dispatcher."""

from core.config import (
    VERIFY_PREFIX,
    VOTEBAN_AGAINST_PREFIX,
    VOTEBAN_FOR_PREFIX,
)
from core.dispatcher import Context, Dispatcher
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.handlers.captcha import (
    handle_new_member,
    handle_verify_callback,
    process_timeout_task,
)
from services.handlers.commands import (
    handle_help,
    handle_ping,
    handle_start,
    handle_stats,
    handle_support,
)
from services.handlers.quiz import handle_poll_answer, handle_quizstats
from services.handlers.voteban import handle_vote_callback, handle_voteban_command
from services.handlers.wtf import handle_wtf

__all__ = ["register_handlers", "process_timeout_task"]

logger = LoggerAdapter(get_logger(__name__), {})


def register_handlers(dp: Dispatcher) -> None:
    """Register all command, callback-query, and new-member handlers."""
    dp.on_new_chat_members(handle_new_member)

    @dp.on_callback_query
    def route_callback(ctx: Context) -> None:
        try:
            if ctx.callback_data.startswith(VERIFY_PREFIX):
                handle_verify_callback(ctx)
            elif ctx.callback_data.startswith((VOTEBAN_FOR_PREFIX, VOTEBAN_AGAINST_PREFIX)):
                handle_vote_callback(ctx)
            elif ctx.callback_query_id:
                ctx.bot.answer_callback_query(
                    ctx.callback_query_id,
                    text=get_translated_text("unknown_action"),
                )
        except Exception as e:
            logger.exception(f"Callback handler error: {e}")
            if ctx.callback_query_id:
                try:
                    ctx.bot.answer_callback_query(ctx.callback_query_id, text="An error occurred.")
                except Exception:
                    pass

    dp.command("start")(handle_start)
    dp.command("help")(handle_help)
    dp.command("support")(handle_support)
    dp.command("ping")(handle_ping)
    dp.command("stats")(handle_stats)
    dp.command("voteban")(handle_voteban_command)
    dp.command("wtf")(handle_wtf)
    dp.on_poll_answer(handle_poll_answer)
    dp.command("quizstats")(handle_quizstats)
