"""Telegram message sending utilities for the news lambda."""

import re
import time
from typing import Optional

import requests
from aws_lambda_powertools import Logger

logger = Logger()

TELEGRAM_MAX_LENGTH = 4096
TELEGRAM_CAPTION_MAX_LENGTH = 1024


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
    """Truncate text to Telegram's maximum message length (4096 chars)."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def send_telegram_message(
    bot_token: str,
    chat_id: str,
    text: str,
    parse_mode: Optional[str] = "HTML",
    max_retries: int = 3,
) -> tuple[bool, Optional[int]]:
    """
    Send a single message to a Telegram chat with truncation and retry.

    Retries up to max_retries times with exponential backoff (2s, 4s, 8s).
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    safe_text = truncate_message(text)
    payload: dict = {"chat_id": chat_id, "text": safe_text, "disable_web_page_preview": True}
    if parse_mode:
        payload["parse_mode"] = parse_mode

    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info(f"Message sent to {chat_id} on attempt {attempt + 1}")
            return True, 200
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else None
            response_text = e.response.text if e.response is not None else None
            error_type = type(e).__name__

            logger.warning(
                f"Attempt {attempt + 1}/{max_retries} to {chat_id} failed ({error_type}) "
                f"(status_code={status_code}, response_text={response_text})"
            )

            if status_code == 429:
                retry_delay = 2 ** (attempt + 1)
                try:
                    resp_json = e.response.json()
                    retry_after = resp_json.get("parameters", {}).get("retry_after")
                    if isinstance(retry_after, (int, float)) and retry_after > 0:
                        retry_delay = retry_after
                except ValueError:
                    pass

                if attempt == max_retries - 1:
                    logger.error(f"Rate limited (429) for {chat_id}, max retries reached")
                    return False, status_code

                logger.warning(f"Rate limited, sleeping for {retry_delay}s")
                time.sleep(retry_delay)
                continue

            if status_code is not None and 400 <= status_code < 500:
                logger.error(f"Non-retryable HTTP {status_code} for {chat_id}, giving up")
                return False, status_code

            if attempt == max_retries - 1:
                logger.error(f"Failed to send to {chat_id} after {max_retries} attempts")
                return False, status_code
            time.sleep(2 ** (attempt + 1))

        except requests.exceptions.RequestException as e:
            error_type = type(e).__name__
            logger.warning(f"Attempt {attempt + 1}/{max_retries} to {chat_id} failed (network: {error_type})")
            if attempt == max_retries - 1:
                logger.error(f"Failed to send to {chat_id} after {max_retries} attempts")
                return False, None
            time.sleep(2 ** (attempt + 1))
    return False, None


def send_media_group(bot_token: str, chat_id: str, image_urls: list[str], caption: str) -> bool:
    """Send multiple images as an album with a single caption (max 3 photos, caption on first)."""

    valid_images = [url for url in image_urls if url and url.startswith("http")]
    if not valid_images:
        success, _ = send_telegram_message(bot_token, chat_id, caption)
        return success

    url = f"https://api.telegram.org/bot{bot_token}/sendMediaGroup"
    media = []

    for i, img_url in enumerate(valid_images[:3]):
        item = {"type": "photo", "media": img_url}
        if i == 0:
            item["caption"] = caption
            item["parse_mode"] = "HTML"
        media.append(item)

    try:
        resp = requests.post(url, json={"chat_id": chat_id, "media": media})
        if resp.status_code != 200:
            logger.error("Media group send failed", extra={"status": resp.status_code, "body": resp.text})
            return False
        logger.info("Media group sent", extra={"chat_id": chat_id, "photo_count": len(media)})
        return True
    except Exception as e:
        logger.error("Failed to send media group", extra={"chat_id": chat_id, "error": str(e)})
        return False
