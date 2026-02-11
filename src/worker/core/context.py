"""
Execution Context for a single Telegram Update.
"""

from typing import Any

from repositories.sqs_repo import SQSClient
from repositories.stats_repository import StatsRepository
from repositories.telegram_client import TelegramClient
from repositories.vote_repository import VoteRepository


class Context:
    """
    Wraps the Telegram Update object and provides helper methods.
    This is the main object passed to command handlers.
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
        self._bot = bot
        self.stats_repo = stats_repo
        self.sqs_repo = sqs_repo
        self.vote_repo = vote_repo

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

        # Handle text safely
        self.text = self.message.get("text", "").strip()

        # Handle reply_to_message
        self.reply_to_message = self.message.get("reply_to_message")

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
        return self.user_data.get("language_code", "kk")

    @property
    def message_id(self) -> int | None:
        return self.message.get("message_id")

    def reply(
        self,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        reply_to_message_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Shorthand to reply to the current message.
        Example: ctx.reply("Hello!")
        """
        if self.chat_id:
            return self._bot.send_message(
                self.chat_id, text, reply_markup=reply_markup, reply_to_message_id=reply_to_message_id
            )
        return {}
