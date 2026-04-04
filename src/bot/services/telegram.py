"""Telegram Bot API client."""

import json
import time
from typing import Any

import urllib3
from core.config import BOT_TOKEN, KICK_BAN_DURATION_SECONDS, TELEGRAM_API_BASE
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

http = urllib3.PoolManager(maxsize=4, timeout=urllib3.Timeout(total=10))


class TelegramAPIError(Exception):
    """Raised when the Telegram API returns an error response."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(status, body)


class TelegramClient:
    """HTTP wrapper around the Telegram Bot API."""

    def __init__(self) -> None:
        self.bot_token = BOT_TOKEN
        self.api_base = f"{TELEGRAM_API_BASE}{self.bot_token}"
        logger.info("TelegramClient initialized", extra={"api_base": TELEGRAM_API_BASE})

    def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST JSON to the Telegram Bot API and return the parsed result."""
        url = f"{self.api_base}/{method}"
        resp = http.request(
            "POST",
            url,
            body=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        body = resp.data.decode("utf-8")
        if resp.status >= 400:
            raise TelegramAPIError(resp.status, body)
        return json.loads(body)

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
        payload: dict[str, Any] = {
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
            result = self._post("sendMessage", payload)
            return result.get("result", {})
        except TelegramAPIError as e:
            logger.error(
                "Failed to send message",
                extra={
                    "chat_id": chat_id,
                    "error": str(e),
                    "response": e.body,
                },
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.error(
                "Failed to send message",
                extra={
                    "chat_id": chat_id,
                    "error": str(e),
                    "response": "No response",
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
        payload: dict[str, Any] = {
            "callback_query_id": callback_query_id,
        }
        if text:
            payload["text"] = text
        if show_alert:
            payload["show_alert"] = True
        try:
            self._post("answerCallbackQuery", payload)
        except (TelegramAPIError, Exception) as e:
            logger.error(
                "Failed to answer callback query",
                extra={"error": str(e)},
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
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "user_id": user_id,
            "permissions": permissions,
        }
        try:
            self._post("restrictChatMember", payload)
        except (TelegramAPIError, Exception) as e:
            logger.error(
                "Failed to restrict chat member",
                extra={"user_id": user_id, "error": str(e)},
                exc_info=True,
            )
            raise

    def kick_chat_member(self, chat_id: int | str, user_id: int) -> None:
        """Kick (temp-ban) a chat member."""
        until_date = int(time.time()) + KICK_BAN_DURATION_SECONDS
        payload = {
            "chat_id": chat_id,
            "user_id": user_id,
            "until_date": until_date,
        }
        try:
            self._post("banChatMember", payload)
        except (TelegramAPIError, Exception) as e:
            logger.error(
                "Failed to kick chat member",
                extra={"user_id": user_id, "error": str(e)},
                exc_info=True,
            )
            raise

    def get_chat_member(self, chat_id: int | str, user_id: int) -> dict[str, Any]:
        """Get chat member info (use ``result['status']`` for admin check)."""
        payload = {"chat_id": chat_id, "user_id": user_id}
        try:
            result = self._post("getChatMember", payload)
            logger.debug(
                "Chat member info",
                extra={"user_id": user_id, "response": result},
            )
            return result.get("result", {})
        except (TelegramAPIError, Exception) as e:
            logger.error(
                "Failed to get chat member",
                extra={"user_id": user_id, "error": str(e)},
                exc_info=True,
            )
            raise

    def delete_message(self, chat_id: int | str, message_id: int) -> None:
        """Delete a message from Telegram."""
        payload = {"chat_id": chat_id, "message_id": message_id}
        try:
            self._post("deleteMessage", payload)
        except (TelegramAPIError, Exception) as e:
            logger.error(
                "Failed to delete message",
                extra={"message_id": message_id, "error": str(e)},
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
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }

        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            result = self._post("editMessageText", payload)
            return result.get("result", {})
        except TelegramAPIError as e:
            logger.error(
                "Failed to edit message text",
                extra={
                    "message_id": message_id,
                    "error": str(e),
                    "response": e.body,
                },
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.error(
                "Failed to edit message text",
                extra={
                    "message_id": message_id,
                    "error": str(e),
                    "response": "No response",
                },
                exc_info=True,
            )
            raise
