"""
Execution Context for a single Telegram Update.
"""

from typing import TYPE_CHECKING, Any

from repositories.telegram_client import TelegramClient

if TYPE_CHECKING:
    from repositories.sqs_repo import SQSClient
    from repositories.stats_repository import StatsRepository


class Context:
    """
    Wraps the Telegram Update object and provides helper methods.
    This is the main object passed to command handlers.
    """

    def __init__(
        self,
        update: dict[str, Any],
        bot: TelegramClient,
        stats_repo: "StatsRepository | None" = None,
        sqs_repo: "SQSClient | None" = None,
    ):
        self._update = update
        self._bot = bot
        self.stats_repo = stats_repo
        self.sqs_repo = sqs_repo

        # Support both message and callback_query updates
        self.callback_query = update.get("callback_query")
        if self.callback_query:
            self.message = self.callback_query.get("message", {})
            self.chat_id = self.message.get("chat", {}).get("id")
            self.user_data = self.callback_query.get("from", {})
            self.callback_query_id = self.callback_query.get("id")
            self.callback_data = (self.callback_query.get("data") or "").strip()
        else:
            self.callback_query_id = None
            self.callback_data = ""
            self.message = update.get("message", {})
            self.chat_id = self.message.get("chat", {}).get("id")
            self.user_data = self.message.get("from", {})

        # Handle text safely (some messages might be photos/files)
        self.text = self.message.get("text", "").strip()

        # Parse arguments: "/stock AAPL" -> args=["AAPL"]
        self.args = []
        if self.text and self.text.startswith("/"):
            parts = self.text.split()
            if len(parts) > 1:
                self.args = parts[1:]

    @property
    def user_id(self) -> int | None:
        """Return the user's telegram ID."""
        return self.user_data.get("id")

    @property
    def username(self) -> str | None:
        return self.user_data.get("username")

    @property
    def first_name(self) -> str | None:
        return self.user_data.get("first_name")

    @property
    def lang_code(self) -> str:
        """Return user's language code, defaulting to 'en'."""
        return self.user_data.get("language_code", "en")

    @property
    def message_id(self) -> int | None:
        """Return the message ID (for edit/delete)."""
        return self.message.get("message_id")

    def reply(self, text: str, **kwargs) -> None:
        """
        Shorthand to reply to the current message.
        Example: ctx.reply("Hello!")
        """
        if self.chat_id:
            self._bot.send_message(self.chat_id, text, **kwargs)
