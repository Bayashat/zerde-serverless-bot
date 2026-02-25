"""
Event Dispatcher.
Handles routing of updates to registered functions using decorators.
"""

from typing import Any, Callable

from aws_lambda_powertools import Logger
from repositories.stats_repository import StatsRepository
from repositories.telegram_client import TelegramClient
from repositories.vote_repository import VoteRepository
from services.message_formatter import get_translated_text

from .context import Context

logger = Logger()

HandlerFunc = Callable[[Context], None]


class Dispatcher:
    """
    Event Dispatcher.
    Handles routing of updates to registered functions using decorators.
    """

    def __init__(
        self,
        bot: TelegramClient,
        stats_repo: StatsRepository | None = None,
        sqs_repo: Any = None,
        vote_repo: VoteRepository | None = None,
    ):
        self.bot = bot
        self.stats_repo = stats_repo
        self.sqs_repo = sqs_repo
        self.vote_repo = vote_repo

        # Registry for handlers
        self.command_handlers: dict[str, HandlerFunc] = {}
        self.new_chat_members_handler: HandlerFunc | None = None
        self.callback_query_handler: HandlerFunc | None = None

    def command(self, command_name: str):
        """
        Decorator to register a command handler.
        Usage:
            @dp.command("start")
            def handle_start(ctx): ...
        """

        def decorator(func: HandlerFunc):
            # Normalize command name (remove / if present)
            clean_name = command_name.lstrip("/")
            self.command_handlers[f"/{clean_name}"] = func
            logger.info(f"Registered command handler: /{clean_name}")
            return func

        return decorator

    def on_new_chat_members(self, func: HandlerFunc):
        """Decorator to register handler for message.new_chat_members."""
        self.new_chat_members_handler = func
        logger.info("Registered new_chat_members handler")
        return func

    def on_callback_query(self, func: HandlerFunc):
        """Decorator to register handler for callback_query updates."""
        self.callback_query_handler = func
        logger.info("Registered callback_query handler")
        return func

    def process_update(self, update: dict[str, Any]):
        """
        Main entry point to process a single Telegram update.
        """
        ctx = Context(update, self.bot, self.stats_repo, self.sqs_repo, self.vote_repo)

        # --- Routing Logic ---
        # 1. Callback query (e.g. inline button "verify")
        if "callback_query" in update and self.callback_query_handler:
            logger.info("Dispatching to callback_query handler")
            try:
                self.callback_query_handler(ctx)
            except Exception as e:
                logger.exception("Error in callback_query handler", extra={"error": e})
            return

        # 2. New chat members (join verification)
        message = update.get("message", {})
        if message.get("new_chat_members") and self.new_chat_members_handler:
            logger.info("Dispatching to new_chat_members handler")
            try:
                self.new_chat_members_handler(ctx)
            except Exception as e:
                logger.exception("Error in new_chat_members handler", extra={"error": e})
            return

        # 3. Command (e.g. /stats, /start)
        text = ctx.text
        if text and text.startswith("/"):
            command_key = text.split()[0].split("@")[0]
            if command_key in self.command_handlers:
                handler = self.command_handlers[command_key]
                logger.info(f"Dispatching to command handler: {command_key}")
                try:
                    handler(ctx)
                except Exception as e:
                    logger.exception(f"Error in command handler {command_key}", extra={"error": e})
                    ctx.reply(get_translated_text("error_occurred", lang_code=ctx.lang_code))
                return

        # 4. Default handler
        return
