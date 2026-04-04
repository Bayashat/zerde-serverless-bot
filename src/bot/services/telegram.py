"""Telegram Bot API client."""

import time
from typing import Any

import requests
from aws_lambda_powertools import Logger
from core.config import BOT_TOKEN, KICK_BAN_DURATION_SECONDS, TELEGRAM_API_BASE

logger = Logger()


class TelegramClient:
    """HTTP wrapper around the Telegram Bot API."""

    def __init__(self) -> None:
        self.bot_token = BOT_TOKEN
        self.api_base = f"{TELEGRAM_API_BASE}{self.bot_token}"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Zerde Telegram Bot/1.0"})
        logger.info("TelegramClient initialized", extra={"api_base": TELEGRAM_API_BASE})

    def send_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: dict[str, Any] | None = None,
        reply_to_message_id: int | None = None,
        link_preview_disable: bool | None = None,
    ) -> dict[str, Any]:
        """Send message to Telegram. Returns the sent Message object."""
        url = f"{self.api_base}/sendMessage"

        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }

        if reply_markup:
            payload["reply_markup"] = reply_markup

        if reply_to_message_id:
            reply_parameters = {"message_id": reply_to_message_id}
            payload["reply_parameters"] = reply_parameters

        if link_preview_disable:
            payload["link_preview_options"] = {"is_disabled": True}

        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json().get("result", {})
        except requests.exceptions.RequestException as e:
            logger.error(
                "Failed to send message",
                extra={
                    "chat_id": chat_id,
                    "error": e,
                    "response": (e.response.text if e.response else "No response"),
                },
                exc_info=True,
            )
            raise

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> None:
        """Answer callback query (dismisses the loading spinner)."""
        url = f"{self.api_base}/answerCallbackQuery"
        payload: dict[str, Any] = {
            "callback_query_id": callback_query_id,
        }
        if text:
            payload["text"] = text
        if show_alert:
            payload["show_alert"] = True
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(
                "Failed to answer callback query",
                extra={"error": e},
                exc_info=True,
            )
            raise

    def restrict_chat_member(
        self,
        chat_id: int | str,
        user_id: int,
        permissions: dict[str, bool],
    ) -> None:
        """Restrict or unrestrict a chat member via ChatPermissions."""
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
            logger.error(
                "Failed to restrict chat member",
                extra={"user_id": user_id, "error": e},
                exc_info=True,
            )
            raise

    def kick_chat_member(self, chat_id: int | str, user_id: int) -> None:
        """Kick (temp-ban) a chat member."""
        url = f"{self.api_base}/banChatMember"
        until_date = int(time.time()) + KICK_BAN_DURATION_SECONDS
        payload = {
            "chat_id": chat_id,
            "user_id": user_id,
            "until_date": until_date,
        }
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(
                "Failed to kick chat member",
                extra={"user_id": user_id, "error": e},
                exc_info=True,
            )
            raise

    def get_chat_member(self, chat_id: int | str, user_id: int) -> dict[str, Any]:
        """Get chat member info (use ``result['status']`` for admin check)."""
        url = f"{self.api_base}/getChatMember"
        payload = {"chat_id": chat_id, "user_id": user_id}
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logger.debug(
                "Chat member info",
                extra={"user_id": user_id, "response": response.json()},
            )
            return response.json().get("result", {})
        except requests.exceptions.RequestException as e:
            logger.error(
                "Failed to get chat member",
                extra={"user_id": user_id, "error": e},
                exc_info=True,
            )
            raise

    def delete_message(self, chat_id: int | str, message_id: int) -> None:
        """Delete a message from Telegram."""
        url = f"{self.api_base}/deleteMessage"
        payload = {"chat_id": chat_id, "message_id": message_id}
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(
                "Failed to delete message",
                extra={"message_id": message_id, "error": e},
                exc_info=True,
            )
            raise

    def edit_message_text(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Edit text of an existing message."""
        url = f"{self.api_base}/editMessageText"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }

        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json().get("result", {})
        except requests.exceptions.RequestException as e:
            logger.error(
                "Failed to edit message text",
                extra={
                    "message_id": message_id,
                    "error": e,
                    "response": (e.response.text if e.response else "No response"),
                },
                exc_info=True,
            )
            raise
