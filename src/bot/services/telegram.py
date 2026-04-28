"""Telegram Bot API client."""

import json
import time
from typing import Any

import urllib3
from core.config import KICK_BAN_DURATION_SECONDS, MAX_EXPLAIN_MEDIA_BYTES, TELEGRAM_API_BASE, get_bot_token
from core.logger import LoggerAdapter, get_logger
from zerde_common.logging_utils import truncate_log_text

logger = LoggerAdapter(get_logger(__name__), {})

http = urllib3.PoolManager(maxsize=4, timeout=urllib3.Timeout(total=10))
# Longer timeout for Telegram file downloads (large PDFs under MAX_EXPLAIN_MEDIA_BYTES).
_file_http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(connect=10, read=120))


class TelegramAPIError(Exception):
    """Raised when the Telegram API returns an error response."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(status, body)


class TelegramClient:
    """HTTP wrapper around the Telegram Bot API."""

    def __init__(self) -> None:
        self.bot_token = get_bot_token()
        self.api_base = f"{TELEGRAM_API_BASE}{self.bot_token}"
        self._file_base_url = f"https://api.telegram.org/file/bot{self.bot_token}/"
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
                    "status": e.status,
                    "response_preview": truncate_log_text(e.body),
                },
            )
            raise
        except Exception as e:
            logger.error(
                "Failed to send message",
                extra={"chat_id": chat_id, "error": str(e)},
            )
            raise

    def send_photo(
        self,
        chat_id: int | str,
        photo: bytes,
        caption: str | None = None,
        parse_mode: str = "HTML",
    ) -> dict[str, Any]:
        """Send a photo (as multipart/form-data) to Telegram. Returns Message object."""
        url = f"{self.api_base}/sendPhoto"
        fields: dict[str, Any] = {
            "chat_id": str(chat_id),
            "photo": ("captcha.png", photo, "image/png"),
        }
        if caption:
            fields["caption"] = caption
            fields["parse_mode"] = parse_mode
        try:
            resp = http.request("POST", url, fields=fields)
            body = resp.data.decode("utf-8")
            if resp.status >= 400:
                raise TelegramAPIError(resp.status, body)
            return json.loads(body).get("result", {})
        except TelegramAPIError as e:
            logger.error(
                "Failed to send photo",
                extra={
                    "chat_id": chat_id,
                    "status": e.status,
                    "response_preview": truncate_log_text(e.body),
                },
            )
            raise
        except Exception as e:
            logger.error("Failed to send photo", extra={"chat_id": chat_id, "error": str(e)})
            raise

    def set_message_reaction(
        self,
        chat_id: int | str,
        message_id: int,
        emoji: str,
    ) -> None:
        """Set a single emoji reaction on a message (Bot API 7.0+)."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "reaction": [{"type": "emoji", "emoji": emoji}],
        }
        self._post("setMessageReaction", payload)

    def clear_message_reaction(self, chat_id: int | str, message_id: int) -> None:
        """Remove all reactions the bot set on a message."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "reaction": [],
        }
        self._post("setMessageReaction", payload)

    def send_chat_action(self, chat_id: int | str, action: str = "typing") -> None:
        """Broadcast a chat action (typing, upload_document, …).

        Clients show the indicator for a few seconds per call; repeat for long tasks.
        Failures are logged and ignored so optional UX does not break handlers.
        """
        payload: dict[str, Any] = {"chat_id": chat_id, "action": action}
        try:
            self._post("sendChatAction", payload)
        except TelegramAPIError as e:
            logger.debug(
                "sendChatAction failed",
                extra={"chat_id": chat_id, "action": action, "status": e.status},
            )
        except Exception as e:
            logger.debug("sendChatAction failed", extra={"error": str(e)})

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
        except Exception as e:
            logger.error(
                "Failed to answer callback query",
                extra={"error": str(e)},
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
        except Exception as e:
            logger.error(
                "Failed to restrict chat member",
                extra={"user_id": user_id, "error": str(e)},
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
        except Exception as e:
            logger.error(
                "Failed to kick chat member",
                extra={"user_id": user_id, "error": str(e)},
            )
            raise

    def get_chat(self, chat_id: int | str) -> dict[str, Any]:
        """Return chat metadata (``title``, ``type``, ``username``, …) from ``getChat``."""
        payload: dict[str, Any] = {"chat_id": chat_id}
        result = self._post("getChat", payload)
        return result.get("result", {})

    def get_chat_member(self, chat_id: int | str, user_id: int) -> dict[str, Any]:
        """Get chat member info (use ``result['status']`` for admin check)."""
        payload = {"chat_id": chat_id, "user_id": user_id}
        try:
            result = self._post("getChatMember", payload)
            res = result.get("result", {})
            logger.debug(
                "Chat member info",
                extra={"user_id": user_id, "member_status": res.get("status")},
            )
            return res
        except Exception as e:
            logger.error(
                "Failed to get chat member",
                extra={"user_id": user_id, "error": str(e)},
            )
            raise

    def delete_message(self, chat_id: int | str, message_id: int) -> None:
        """Delete a message from Telegram."""
        payload = {"chat_id": chat_id, "message_id": message_id}
        try:
            self._post("deleteMessage", payload)
        except Exception as e:
            logger.error(
                "Failed to delete message",
                extra={"message_id": message_id, "error": str(e)},
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
                    "status": e.status,
                    "response_preview": truncate_log_text(e.body),
                },
            )
            raise
        except Exception as e:
            logger.error(
                "Failed to edit message text",
                extra={"message_id": message_id, "error": str(e)},
            )
            raise

    def get_file(self, file_id: str) -> dict[str, Any]:
        """Resolve ``file_id`` via ``getFile``; result includes ``file_path`` for download."""
        payload: dict[str, Any] = {"file_id": file_id}
        result = self._post("getFile", payload)
        return result.get("result", {})

    def download_file(self, file_path: str, *, max_bytes: int = MAX_EXPLAIN_MEDIA_BYTES) -> bytes:
        """Download a file from Telegram CDN using ``file_path`` from ``get_file``.

        Raises:
            TelegramAPIError: HTTP error from Telegram.
            ValueError: reported or observed size exceeds ``max_bytes``.
        """
        url = f"{self._file_base_url}{file_path}"
        resp = _file_http.request("GET", url, preload_content=False, retries=False)
        try:
            if resp.status >= 400:
                body = resp.data.decode("utf-8", errors="replace") if resp.data else ""
                raise TelegramAPIError(resp.status, body)

            cl = resp.headers.get("Content-Length")
            if cl is not None:
                try:
                    content_len = int(cl)
                except ValueError:
                    content_len = None
                if content_len is not None and content_len > max_bytes:
                    raise ValueError(f"File too large: Content-Length {content_len} > max_bytes {max_bytes}")

            buffer = bytearray()
            total = 0
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"File exceeds max_bytes={max_bytes}")
                buffer.extend(chunk)
            return bytes(buffer)
        finally:
            resp.release_conn()
