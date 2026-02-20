"""Telegram Bot API client."""

import time
from typing import Any

import requests
from aws_lambda_powertools import Logger
from repositories import BOT_TOKEN, TELEGRAM_API_BASE

logger = Logger()


class TelegramClient:
    """Client for Telegram Bot API operations."""

    def __init__(self) -> None:
        self.bot_token = BOT_TOKEN
        self.api_base = f"{TELEGRAM_API_BASE}{self.bot_token}"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Zerde Telegram Bot/1.0"})

    def send_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: dict[str, Any] | None = None,
        reply_to_message_id: int | None = None
    ) -> dict[str, Any]:
        """Send message to Telegram. Returns the sent Message object from API."""
        url = f"{self.api_base}/sendMessage"

        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }

        if reply_markup:
            payload["reply_markup"] = reply_markup

        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id

        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json().get("result", {})
        except requests.exceptions.RequestException as e:
            logger.error(
                "Failed to send message",
                extra={"chat_id": chat_id, "error": e, "response": e.response.text if e.response else "No response"},
                exc_info=True,
            )
            raise

    def answer_callback_query(self, callback_query_id: str, text: str | None = None, show_alert: bool = False) -> None:
        """Answer callback query (must be called to dismiss loading state).

        Args:
            callback_query_id: Callback query ID from the update.
            text: Optional short message to show to the user.
            show_alert: If True, show text as alert instead of notification.
        """
        url = f"{self.api_base}/answerCallbackQuery"
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        if show_alert:
            payload["show_alert"] = True
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error("Failed to answer callback query", extra={"error": e}, exc_info=True)
            raise

    def restrict_chat_member(
        self,
        chat_id: int | str,
        user_id: int,
        permissions: dict[str, bool],
    ) -> None:
        """Restrict or unrestrict a chat member via ChatPermissions.

        Args:
            chat_id: Target chat ID.
            user_id: Target user ID.
            permissions: Dict of permission names to bool, e.g.
                {"can_send_messages": True, "can_send_audios": True, ...}.
        """
        url = f"{self.api_base}/restrictChatMember"
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "user_id": user_id,
            "permissions": permissions,
        }
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error("Failed to restrict chat member", extra={"user_id": user_id, "error": e}, exc_info=True)
            raise

    def kick_chat_member(self, chat_id: int | str, user_id: int) -> None:
        """Kick a chat member. Use to remove users who did not verify in time."""
        url = f"{self.api_base}/banChatMember"
        until_date = int(time.time()) + 31
        payload = {"chat_id": chat_id, "user_id": user_id, "until_date": until_date}
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error("Failed to kick chat member", extra={"user_id": user_id, "error": e}, exc_info=True)
            raise

    def get_chat_member(self, chat_id: int | str, user_id: int) -> dict[str, Any]:
        """Get chat member info; use result['status'] for admin check (creator/administrator)."""
        url = f"{self.api_base}/getChatMember"
        payload = {"chat_id": chat_id, "user_id": user_id}
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logger.debug("Chat member info", extra={"user_id": user_id, "response": response.json()})
            return response.json().get("result", {})
        except requests.exceptions.RequestException as e:
            logger.error("Failed to get chat member", extra={"user_id": user_id, "error": e}, exc_info=True)
            raise

    def delete_message(self, chat_id: int | str, message_id: int) -> None:
        """Delete message from Telegram.

        Args:
            chat_id: Telegram chat ID (int or str).
            message_id: Message ID.
        """
        url = f"{self.api_base}/deleteMessage"
        payload = {"chat_id": chat_id, "message_id": message_id}
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error("Failed to delete message", extra={"message_id": message_id, "error": e}, exc_info=True)
            raise
