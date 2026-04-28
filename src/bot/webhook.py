"""Webhook event handling: API Gateway / SQS routing and HTTP utilities."""

import base64
import hmac
import json
from typing import Any

from core.config import (
    get_chat_lang,
    get_webhook_secret_token,
    is_configured_group_chat,
)
from core.dispatcher import Dispatcher
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.handlers import process_timeout_task
from services.repositories.sqs import SQSClient
from services.spam.screening_service import SpamScreeningService
from services.telegram import TelegramClient

logger = LoggerAdapter(get_logger(__name__), {})

_sqs_client = SQSClient()
_spam_screening = SpamScreeningService


# ── Public entry point (called by main.lambda_handler) ──────────────────────


def handle_event(
    event: dict[str, Any],
    dispatcher: Dispatcher,
    bot: TelegramClient,
) -> dict[str, Any] | None:
    """Route a raw Lambda event to the correct handler by source."""
    event_type = _detect_event_type(event)
    logger.debug("Detected event type", extra={"event_type": event_type})

    if event_type == "api_gateway":
        return _handle_api_gateway(event, dispatcher, bot)
    logger.warning("Unknown event type received", extra={"event": event})

    return None


# ── Event-type detection ───────────────────────────────────────────────────


def _detect_event_type(event: dict[str, Any]) -> str:
    """Detect which AWS service triggered this Lambda invocation."""
    if "Records" in event and event["Records"] and event["Records"][0].get("eventSource") == "aws:sqs":
        return "unknown"
    if "headers" in event or "requestContext" in event:
        return "api_gateway"
    return "unknown"


# ── API Gateway handler ──────────────────────────────────────────────────


def _handle_api_gateway(
    event: dict[str, Any],
    dispatcher: Dispatcher,
    bot: TelegramClient,
) -> dict[str, Any]:
    """Synchronous webhook handler: validate -> process -> return 200 OK."""
    screener = _spam_screening(bot, _sqs_client)
    try:
        if not verify_webhook_secret_token(event):
            return create_response(200, {"ok": False, "error": "Unauthorized"})

        try:
            body = parse_api_gateway_event(event)
            logger.info("API Gateway event parsed successfully")
        except ValueError as e:
            logger.error("Failed to parse API Gateway event", extra={"error": e})
            return create_response(200, {"message": "Invalid request"})

        chat_id, chat_type = _extract_chat_context(body)

        if chat_type == "private":
            dispatcher.bot.send_message(
                chat_id,
                get_translated_text("private_message", get_chat_lang(chat_id)),
            )
            return create_response(200, {"message": "ok"})

        if chat_type in {"group", "supergroup"} and not is_configured_group_chat(chat_id):
            logger.debug("Silently ignoring event from non-whitelisted chat", extra={"chat_id": chat_id})
            return create_response(200, {"message": "ok"})

        if screener.should_screen(body):
            screener.run(body)

        if not is_event_relevant_to_bot(body):
            logger.info("Event not relevant to bot, ignoring")
            return create_response(200, {"message": "Not relevant"})

        if body.get("task_type") == "CHECK_TIMEOUT":
            body["_captcha_repo"] = dispatcher.captcha_repo
            process_timeout_task(bot, body)
        else:
            dispatcher.process_update(body)

    except Exception as e:
        logger.exception("Unexpected error in webhook handler", extra={"error": e})

    return create_response(200, {"message": "Webhook received"})


# ── HTTP / webhook utilities ────────────────────────────────────────────


def verify_webhook_secret_token(event: dict[str, Any]) -> bool:
    """Verify Telegram webhook secret token (constant-time comparison)."""
    headers = event.get("headers", {})
    received_token = headers.get("x-telegram-bot-api-secret-token") or headers.get("X-Telegram-Bot-Api-Secret-Token")

    if not received_token:
        logger.critical("Missing X-Telegram-Bot-Api-Secret-Token header")
        return False

    if not hmac.compare_digest(received_token, get_webhook_secret_token()):
        logger.critical("Webhook secret token mismatch")
        return False

    logger.info("Webhook secret token verified successfully")
    return True


def parse_api_gateway_event(event: dict[str, Any]) -> dict[str, Any]:
    """Extract Telegram webhook payload from an API Gateway event."""
    body = event.get("body")
    if not body:
        raise ValueError("Missing body in API Gateway event")

    if event.get("isBase64Encoded", False):
        body = base64.b64decode(body).decode("utf-8")

    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in body: {e}") from e

    return body


def create_response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Build an API Gateway-compatible HTTP response."""
    logger.debug("Creating response", extra={"body": body})
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _extract_chat_context(body: dict[str, Any]) -> tuple[int | None, str | None]:
    """Extract (chat_id, chat_type) from common Telegram update shapes."""
    message = body.get("message") or body.get("edited_message")
    if isinstance(message, dict):
        chat = message.get("chat", {})
        return chat.get("id"), chat.get("type")

    callback_query = body.get("callback_query", {})
    callback_message = callback_query.get("message", {})
    if isinstance(callback_message, dict):
        chat = callback_message.get("chat", {})
        return chat.get("id"), chat.get("type")

    return None, None


def is_event_relevant_to_bot(body: dict[str, Any]) -> bool:
    """Return True if the Telegram update warrants processing."""
    if "poll_answer" in body:
        return True

    if "callback_query" in body:
        return True

    if "message" in body:
        msg = body["message"]
        if "new_chat_members" in msg:
            return True
        if msg.get("document"):
            return True
        text_content = msg.get("text") or ""
        if text_content.strip():
            return True

    return False
