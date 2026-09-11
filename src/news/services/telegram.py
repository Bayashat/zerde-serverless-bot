"""Telegram message sending utilities for the News Lambda."""

import json
import re
from typing import NamedTuple

from core.logger import LoggerAdapter, get_logger
from services.deadline import request_bytes

logger = LoggerAdapter(get_logger(__name__), {})

TELEGRAM_MAX_LENGTH = 4096
TELEGRAM_CAPTION_MAX_LENGTH = 1024

_JSON_HEADERS = {"Content-Type": "application/json"}


def sanitize_html(text: str) -> str:
    """Sanitize text for Telegram HTML parse mode without double-escaping."""
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"&(?!\w+;|#[0-9]+;|#x[0-9a-fA-F]+;)", "&amp;", text)
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    for tag in [
        "b",
        "/b",
        "i",
        "/i",
        "u",
        "/u",
        "s",
        "/s",
        "code",
        "/code",
        "pre",
        "/pre",
        "blockquote",
        "/blockquote",
    ]:
        text = text.replace(f"&lt;{tag}&gt;", f"<{tag}>")
    text = re.sub(r"&lt;a\s+href=\"([^\"]*)\"&gt;", r'<a href="\1">', text)
    text = re.sub(r"&lt;a\s+href='([^']*)'&gt;", r'<a href="\1">', text)
    text = text.replace("&lt;/a&gt;", "</a>")
    return text


def truncate_message(text: str, max_length: int = TELEGRAM_MAX_LENGTH) -> str:
    """Truncate text to Telegram's maximum message length."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


class SendResult(NamedTuple):
    state: str
    message_id: int | None = None
    status: int | None = None
    retry_after: int = 0


def prepare_step(text: str, image_url: str = "") -> dict:
    """Freeze the actual text/photo variants before computing the manifest hash."""
    if not isinstance(text, str) or not text.strip() or not isinstance(image_url, str):
        raise ValueError("News content must have nonempty text and a string image URL")
    safe = sanitize_html(text)
    return {
        "text": truncate_message(safe),
        "caption": truncate_message(safe, TELEGRAM_CAPTION_MAX_LENGTH),
        "image_url": image_url,
    }


class TelegramSender:
    """One cancellable HTTP attempt; only an actual Telegram message is confirmed."""

    def __init__(self, bot_token: str) -> None:
        self._base_url = f"https://api.telegram.org/bot{bot_token}"

    async def send_step(self, chat_id, step, mode, deadline):
        if mode == "photo":
            method = "sendPhoto"
            payload = {
                "chat_id": chat_id,
                "photo": step["image_url"],
                "parse_mode": "HTML",
                "caption": step["caption"],
            }
        else:
            method = "sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": step["text"],
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
        try:
            status, body = await request_bytes(
                "POST",
                f"{self._base_url}/{method}",
                deadline=deadline,
                cap=10,
                max_bytes=128000,
                headers=_JSON_HEADERS,
                payload=payload,
            )
            data = json.loads(body)
            result = data.get("result")
            if (
                200 <= status < 300
                and data.get("ok") is True
                and isinstance(result, dict)
                and type(result.get("message_id")) is int
                and result["message_id"] > 0
                and str((result.get("chat") or {}).get("id")) == str(chat_id)
            ):
                return SendResult("SENT", result["message_id"], status)
            logger.warning(
                "News Telegram send not confirmed",
                extra={"chat_id": chat_id, "status": status, "response_chars": len(body)},
            )
            if data.get("ok") is False and 400 <= status < 500:
                delay = (data.get("parameters") or {}).get("retry_after", 0)
                delay = delay if type(delay) is int and 0 < delay <= 86400 else 60
                return SendResult("RETRYABLE" if status == 429 else "REJECTED", status=status, retry_after=delay)
            return SendResult("UNKNOWN", status=status)
        except Exception as exc:
            logger.warning("News Telegram result unknown", extra={"chat_id": chat_id, "error_type": type(exc).__name__})
            return SendResult("UNKNOWN")
