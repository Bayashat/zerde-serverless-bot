"""Telegram sendPoll wrapper for quiz polls."""

import json
from typing import Any

import urllib3
from core.config import BOT_TOKEN, TELEGRAM_API_BASE
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

http = urllib3.PoolManager(maxsize=4, timeout=urllib3.Timeout(total=10))


class QuizSender:
    """Sends Telegram quiz polls to chat groups."""

    def __init__(self) -> None:
        self._base_url = f"{TELEGRAM_API_BASE}{BOT_TOKEN}"

    def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "HTML",
        reply_to_message_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Send a text message to a chat. Returns the Telegram response result or None on failure."""
        url = f"{self._base_url}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        try:
            resp = http.request(
                "POST",
                url,
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            if resp.status >= 400:
                body = resp.data.decode("utf-8")
                logger.error(
                    "sendMessage failed",
                    extra={"chat_id": chat_id, "status": resp.status, "body": body},
                )
                return None
            result = json.loads(resp.data.decode("utf-8"))
            return result.get("result")
        except Exception as e:
            logger.error("sendMessage error", extra={"chat_id": chat_id, "error": str(e)})
            return None

    def send_quiz_poll(
        self,
        chat_id: str,
        question: str,
        options: list[str],
        correct_option_id: int,
        explanation: str | None = None,
    ) -> dict[str, Any] | None:
        """Send a quiz poll to a chat. Returns the Telegram response result or None on failure."""
        url = f"{self._base_url}/sendPoll"
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "question": question,
            "options": [{"text": opt} for opt in options],
            "type": "quiz",
            "is_anonymous": False,
            "correct_option_id": correct_option_id,
            "shuffle_options": True,
            "open_period": 3600 * 5,
        }
        if explanation:
            payload["explanation"] = explanation[:200]  # Telegram limit

        try:
            resp = http.request(
                "POST",
                url,
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            if resp.status >= 400:
                body = resp.data.decode("utf-8")
                logger.error(
                    "sendPoll failed",
                    extra={"chat_id": chat_id, "status": resp.status, "body": body},
                )
                return None

            result = json.loads(resp.data.decode("utf-8"))
            logger.info("Quiz poll sent", extra={"chat_id": chat_id})
            return result.get("result")

        except Exception as e:
            logger.error("sendPoll error", extra={"chat_id": chat_id, "error": str(e)})
            return None
