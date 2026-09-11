"""Telegram sendPoll wrapper for quiz polls."""

import json
from typing import Any

import urllib3
from core.config import TELEGRAM_API_BASE, get_bot_token
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

http = urllib3.PoolManager(maxsize=4, timeout=urllib3.Timeout(total=10))


class PollSendRejected(RuntimeError):
    """Telegram positively rejected the request; a later retry may be safe."""

    def __init__(self, status):
        self.status = status
        super().__init__("Telegram rejected the quiz poll")


class PollSendUnknown(RuntimeError):
    """Telegram may have accepted the poll; do not automatically send it again."""


class QuizSender:
    """Sends Telegram quiz polls to chat groups."""

    def __init__(self) -> None:
        self._base_url = f"{TELEGRAM_API_BASE}{get_bot_token()}"

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
                retries=False,
            )
            if resp.status >= 400:
                body = resp.data.decode("utf-8")
                logger.error(
                    "sendMessage failed",
                    extra={"chat_id": chat_id, "status": resp.status, "response_chars": len(body)},
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
        question_parse_mode: str | None = None,
    ) -> dict[str, Any]:
        """One transport attempt; distinguish a confirmed rejection from an unknown send."""
        url = f"{self._base_url}/sendPoll"
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "question": question,
            "options": [{"text": opt} for opt in options],
            "type": "quiz",
            "is_anonymous": False,
            "correct_option_ids": [correct_option_id],
            "allows_multiple_answers": False,
            "allows_revoting": False,
            "shuffle_options": True,
            "open_period": 3600 * 5,
        }
        if explanation:
            payload["explanation"] = explanation[:200]  # Telegram limit
        if question_parse_mode:
            payload["question_parse_mode"] = question_parse_mode

        try:
            resp = http.request(
                "POST",
                url,
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                retries=False,
            )
            if resp.status >= 500:
                raise PollSendUnknown("Telegram returned an uncertain server error")
            result = json.loads(resp.data.decode("utf-8"))
            if 400 <= resp.status < 500 and result.get("ok") is False and result.get("error_code") == resp.status:
                raise PollSendRejected(resp.status)
            if result.get("ok") is not True or not isinstance(result.get("result"), dict):
                raise PollSendUnknown("Telegram response has no confirmed poll result")
            logger.info("Quiz poll sent", extra={"chat_id": chat_id})
            return result["result"]
        except (PollSendRejected, PollSendUnknown):
            raise
        except Exception as exc:
            logger.warning("sendPoll outcome unknown", extra={"chat_id": chat_id, "error_type": type(exc).__name__})
            raise PollSendUnknown("Telegram poll transport outcome is unknown") from exc
