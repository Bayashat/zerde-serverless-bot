"""Telegram Bot API client."""

from typing import Any

import requests
from aws_lambda_powertools import Logger
from repositories import BOT_TOKEN, TELEGRAM_API_BASE

logger = Logger()


class TelegramClient:
    """Client for Telegram Bot API operations."""

    def __init__(self) -> None:
        """Initialize Telegram client."""
        self.bot_token = BOT_TOKEN
        self.api_base = f"{TELEGRAM_API_BASE}{self.bot_token}"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "AWS-Serverless-Telegram-Bot/1.0"})

    def send_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: dict[str, Any] | None = None,
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

        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json().get("result", {})
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Failed to send message to {chat_id}: {e}",
                extra={"response": e.response.text if e.response else "No response"},
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
            logger.error(f"Failed to answer callback query: {e}")
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
            logger.error(f"Failed to restrict chat member {user_id}: {e}")
            raise

    def edit_message_text(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        """Edit a bot's message text (and optional reply_markup)."""
        url = f"{self.api_base}/editMessageText"
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to edit message {message_id}: {e}")
            raise

    def ban_chat_member(self, chat_id: int | str, user_id: int) -> None:
        """Ban (kick) a chat member. Use to remove users who did not verify in time."""
        url = f"{self.api_base}/banChatMember"
        payload = {"chat_id": chat_id, "user_id": user_id}
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to ban chat member {user_id}: {e}")
            raise

    def unban_chat_member(self, chat_id: int | str, user_id: int) -> None:
        """
        Unban a user. Used immediately after banning to achieve a 'kick' effect
        (remove from group but allow re-joining).
        """
        url = f"{self.api_base}/unbanChatMember"
        payload = {
            "chat_id": chat_id,
            "user_id": user_id,
            "only_if_banned": True,  # 或者 False，通常 True 就够了，因为刚 Ban 完
        }
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            # Unban 失败不应该阻断流程，记录日志即可
            logger.warning(f"Failed to unban chat member {user_id} (soft kick might remain as ban): {e}")

    def get_chat_member(self, chat_id: int | str, user_id: int) -> dict[str, Any]:
        """Get chat member info; use result['status'] for admin check (creator/administrator)."""
        url = f"{self.api_base}/getChatMember"
        payload = {"chat_id": chat_id, "user_id": user_id}
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json().get("result", {})
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get chat member {user_id}: {e}")
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
            logger.error(f"Failed to delete message {message_id}: {e}")
            raise
