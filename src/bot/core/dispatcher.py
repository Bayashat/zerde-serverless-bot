"""Event Dispatcher and Execution Context for Telegram updates."""

from typing import Any, Callable

from aws_lambda_powertools import Logger
from core.translations import get_translated_text
from services.repositories import SQSClient, StatsRepository, VoteRepository
from services.telegram import TelegramClient

logger = Logger()

HandlerFunc = Callable[["Context"], None]


# ── Context ─────────────────────────────────────────────────────────────────


class Context:
    """Wraps a single Telegram Update and provides helper methods.

    This is the main object passed to every command / callback handler.
    """

    def __init__(
        self,
        update: dict[str, Any],
        bot: TelegramClient,
        stats_repo: StatsRepository | None = None,
        sqs_repo: SQSClient | None = None,
        vote_repo: VoteRepository | None = None,
    ):
        self._update = update
        self.bot = bot
        self.stats_repo = stats_repo
        self.sqs_repo = sqs_repo
        self.vote_repo = vote_repo

        self.callback_query = update.get("callback_query")
        if self.callback_query:
            self.message = self.callback_query.get("message", {})
            self.user_data = self.callback_query.get("from", {})
            self.callback_query_id = self.callback_query.get("id")
            self.callback_data = (self.callback_query.get("data") or "").strip()
        else:
            self.callback_query_id = None
            self.callback_data = ""
            self.message = update.get("message", {})
            self.user_data = self.message.get("from", {})

        self.text = self.message.get("text", "").strip()
        self.reply_to_message = self.message.get("reply_to_message")

    @property
    def user_id(self) -> int | None:
        return self.user_data.get("id")

    @property
    def username(self) -> str | None:
        return self.user_data.get("username")

    @property
    def first_name(self) -> str | None:
        return self.user_data.get("first_name")

    @property
    def lang_code(self) -> str:
        return self.user_data.get("language_code", "kk")

    @property
    def message_id(self) -> int | None:
        return self.message.get("message_id")

    @property
    def chat_id(self) -> int | None:
        return self.message.get("chat", {}).get("id")

    def reply(
        self,
        text: str,
        reply_to_message_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
        link_preview_disable: bool | None = None,
    ) -> dict[str, Any]:
        """Shorthand to reply in the current chat."""
        if self.chat_id:
            return self.bot.send_message(
                self.chat_id,
                text,
                reply_markup=reply_markup,
                reply_to_message_id=reply_to_message_id,
                link_preview_disable=link_preview_disable,
            )
        return {}


# ── Dispatcher ──────────────────────────────────────────────────────────────


class Dispatcher:
    """Decorator-based router that dispatches Telegram updates to handlers."""

    def __init__(
        self,
        bot: TelegramClient,
        stats_repo: StatsRepository | None = None,
        sqs_repo: SQSClient | None = None,
        vote_repo: VoteRepository | None = None,
    ):
        self.bot = bot
        self.stats_repo = stats_repo
        self.sqs_repo = sqs_repo
        self.vote_repo = vote_repo

        self.command_handlers: dict[str, HandlerFunc] = {}
        self.new_chat_members_handler: HandlerFunc | None = None
        self.callback_query_handler: HandlerFunc | None = None

    def command(self, command_name: str):
        """Decorator to register a command handler (e.g. ``@dp.command("start")``)."""

        def decorator(func: HandlerFunc):
            clean_name = command_name.lstrip("/")
            self.command_handlers[f"/{clean_name}"] = func
            logger.info(f"Registered command handler: /{clean_name}")
            return func

        return decorator

    def on_new_chat_members(self, func: HandlerFunc):
        """Decorator to register handler for ``message.new_chat_members``."""
        self.new_chat_members_handler = func
        logger.info("Registered new_chat_members handler")
        return func

    def on_callback_query(self, func: HandlerFunc):
        """Decorator to register handler for ``callback_query`` updates."""
        self.callback_query_handler = func
        logger.info("Registered callback_query handler")
        return func

    def process_update(self, update: dict[str, Any]):
        """Route a single Telegram update to the appropriate handler."""
        ctx = Context(update, self.bot, self.stats_repo, self.sqs_repo, self.vote_repo)

        member = ctx.bot.get_chat_member(ctx.chat_id, ctx.user_id)
        logger.info("Member info", extra={"member": member})
        if (
            member.get("status") not in ("member", "restricted", "administrator", "creator")
            or member.get("is_member") is False
        ):
            if ctx.callback_query_id:
                ctx.bot.answer_callback_query(
                    ctx.callback_query_id,
                    text=get_translated_text("not_in_group"),
                    show_alert=True,
                )
            return

        if ctx.callback_query and self.callback_query_handler:
            logger.info("Dispatching to callback_query handler")
            try:
                self.callback_query_handler(ctx)
            except Exception as e:
                logger.exception("Error in callback_query handler", extra={"error": e})
            return

        if ctx.message.get("new_chat_members") and self.new_chat_members_handler:
            logger.info("Dispatching to new_chat_members handler")
            try:
                self.new_chat_members_handler(ctx)
            except Exception as e:
                logger.exception("Error in new_chat_members handler", extra={"error": e})
            return

        if ctx.text and ctx.text.startswith("/"):
            command_key = ctx.text.split()[0].split("@")[0]
            if command_key in self.command_handlers:
                handler = self.command_handlers[command_key]
                logger.info(f"Dispatching to command handler: {command_key}")
                try:
                    handler(ctx)
                except Exception as e:
                    logger.exception(
                        f"Error in command handler {command_key}",
                        extra={"error": e},
                    )
                    ctx.reply(get_translated_text("error_occurred", lang_code=ctx.lang_code))
                return

        return
