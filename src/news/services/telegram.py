"""Telegram message sending utilities for the News Lambda."""

import json
import re
import time
from typing import Optional

import urllib3
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

TELEGRAM_MAX_LENGTH = 4096
TELEGRAM_CAPTION_MAX_LENGTH = 1024

_JSON_HEADERS = {"Content-Type": "application/json"}
http = urllib3.PoolManager(maxsize=4, timeout=urllib3.Timeout(total=10))


def sanitize_html(text: str) -> str:
    """Sanitize text for Telegram HTML parse mode without double-escaping."""
    if not text:
        return ""
    text = re.sub(r"&(?!\w+;|#[0-9]+;|#x[0-9a-fA-F]+;)", "&amp;", text)
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    for tag in ["b", "/b", "blockquote", "/blockquote"]:
        text = text.replace(f"&lt;{tag}&gt;", f"<{tag}>")
    text = re.sub(r"&lt;a\s+href=\"([^\"]*)\"&gt;", r'<a href="\1">', text)
    text = text.replace("&lt;/a&gt;", "</a>")
    return text


def truncate_message(text: str, max_length: int = TELEGRAM_MAX_LENGTH) -> str:
    """Truncate text to Telegram's maximum message length."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


class TelegramSender:
    """Thin HTTP wrapper around the Telegram Bot API for the News Lambda."""

    def __init__(self, bot_token: str) -> None:
        self._base_url = f"https://api.telegram.org/bot{bot_token}"

    def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: Optional[str] = "HTML",
        max_retries: int = 3,
    ) -> tuple[bool, Optional[int]]:
        """Send a message with truncation and exponential-backoff retry."""
        url = f"{self._base_url}/sendMessage"
        safe_text = truncate_message(text)
        payload: dict = {
            "chat_id": chat_id,
            "text": safe_text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        body_bytes = json.dumps(payload).encode("utf-8")

        for attempt in range(max_retries):
            try:
                resp = http.request("POST", url, body=body_bytes, headers=_JSON_HEADERS)
                if resp.status < 400:
                    logger.info(f"Message sent to {chat_id} on attempt {attempt + 1}")
                    return True, 200

                status_code = resp.status
                response_text = resp.data.decode("utf-8")
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries} to {chat_id} failed (HTTPError) "
                    f"(status_code={status_code}, response_text={response_text})"
                )

                if status_code == 429:
                    retry_delay = 2 ** (attempt + 1)
                    try:
                        resp_json = json.loads(response_text)
                        retry_after = resp_json.get("parameters", {}).get("retry_after")
                        if isinstance(retry_after, (int, float)) and retry_after > 0:
                            retry_delay = retry_after
                    except (ValueError, KeyError):
                        pass
                    if attempt == max_retries - 1:
                        logger.error(f"Rate limited (429) for {chat_id}, max retries reached")
                        return False, status_code
                    logger.warning(f"Rate limited, sleeping for {retry_delay}s")
                    time.sleep(retry_delay)
                    continue

                if 400 <= status_code < 500:
                    logger.error(f"Non-retryable HTTP {status_code} for {chat_id}, giving up")
                    return False, status_code

                if attempt == max_retries - 1:
                    logger.error(f"Failed to send to {chat_id} after {max_retries} attempts")
                    return False, status_code
                time.sleep(2 ** (attempt + 1))

            except Exception as e:
                error_type = type(e).__name__
                logger.warning(f"Attempt {attempt + 1}/{max_retries} to {chat_id} failed (network: {error_type})")
                if attempt == max_retries - 1:
                    logger.error(f"Failed to send to {chat_id} after {max_retries} attempts")
                    return False, None
                time.sleep(2 ** (attempt + 1))
        return False, None

    def send_message_with_photo(
        self,
        chat_id: str,
        message: str,
        image_url: Optional[str] = None,
    ) -> bool:
        """Send a photo with caption, or fall back to text-only if no image."""
        if not image_url:
            return self.send_message(chat_id, message)[0]

        url = f"{self._base_url}/sendPhoto"
        caption = truncate_message(message, TELEGRAM_CAPTION_MAX_LENGTH)
        payload: dict = {
            "chat_id": chat_id,
            "photo": image_url,
            "caption": caption,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            resp = http.request("POST", url, body=json.dumps(payload), headers=_JSON_HEADERS)
            if resp.status != 200:
                logger.error(
                    "Send photo failed",
                    extra={"status": resp.status, "body": resp.data.decode("utf-8")},
                )
                return False
            logger.info("Photo sent", extra={"chat_id": chat_id})
            return True
        except Exception as e:
            logger.error("Failed to send photo", extra={"chat_id": chat_id, "error": str(e)})
            return False
