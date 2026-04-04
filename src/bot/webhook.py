"""Webhook event handling: API Gateway / SQS routing and HTTP utilities."""

import base64
import hmac
import json
from typing import Any

from aws_lambda_powertools import Logger
from core.config import WEBHOOK_SECRET_TOKEN
from core.dispatcher import Dispatcher
from core.translations import get_translated_text
from services.handlers import process_timeout_task
from services.telegram import TelegramClient

logger = Logger()


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
    elif event_type == "sqs":
        _handle_sqs(event, bot)
    else:
        logger.warning("Unknown event type received", extra={"event": event})

    return None


# ── Event-type detection ────────────────────────────────────────────────────


def _detect_event_type(event: dict[str, Any]) -> str:
    """Detect which AWS service triggered this Lambda invocation."""
    if "Records" in event and event["Records"] and event["Records"][0].get("eventSource") == "aws:sqs":
        return "sqs"
    if "headers" in event or "requestContext" in event:
        return "api_gateway"
    return "unknown"


# ── API Gateway handler ────────────────────────────────────────────────────


def _handle_api_gateway(
    event: dict[str, Any],
    dispatcher: Dispatcher,
    bot: TelegramClient,
) -> dict[str, Any]:
    """Synchronous webhook handler: validate -> process -> return 200 OK."""
    try:
        if not verify_webhook_secret_token(event):
            return create_response(200, {"ok": False, "error": "Unauthorized"})

        try:
            body = parse_api_gateway_event(event)
            logger.info("API Gateway event parsed successfully")
        except ValueError as e:
            logger.error("Failed to parse API Gateway event", extra={"error": e})
            return create_response(200, {"message": "Invalid request"})

        if not is_event_relevant_to_bot(body):
            logger.info("Event not relevant to bot, ignoring")
            return create_response(200, {"message": "Not relevant"})

        message = body.get("message", {})
        if message is not None:
            chat_type = message.get("chat", {}).get("type")
            if chat_type == "private":
                chat_id = message.get("chat", {}).get("id")
                dispatcher.bot.send_message(chat_id, get_translated_text("private_message"))
                return create_response(200, {"message": "ok"})

        if body.get("task_type") == "CHECK_TIMEOUT":
            process_timeout_task(bot, body)
        else:
            dispatcher.process_update(body)

    except Exception as e:
        logger.exception("Unexpected error in webhook handler", extra={"error": e})

    return create_response(200, {"message": "Webhook received"})


# ── SQS handler ────────────────────────────────────────────────────────────


def _handle_sqs(event: dict[str, Any], bot: TelegramClient) -> None:
    """Process SQS batch -- only CHECK_TIMEOUT tasks are expected."""
    logger.debug(
        "Received SQS batch",
        extra={"record_count": len(event.get("Records", []))},
    )

    for record in event["Records"]:
        try:
            body = json.loads(record["body"])

            if body.get("task_type") == "CHECK_TIMEOUT":
                process_timeout_task(bot, body)
            else:
                logger.warning(
                    "Unexpected SQS record: not a CHECK_TIMEOUT task, ignoring",
                    extra={"body": body},
                )

        except Exception as e:
            logger.error(
                "Critical error processing SQS record",
                extra={
                    "message_id": record.get("messageId"),
                    "error": e,
                },
                exc_info=True,
            )

    logger.info("SQS batch processing completed")


# ── HTTP / webhook utilities ────────────────────────────────────────────────


def verify_webhook_secret_token(event: dict[str, Any]) -> bool:
    """Verify Telegram webhook secret token (constant-time comparison)."""
    headers = event.get("headers", {})
    received_token = headers.get("x-telegram-bot-api-secret-token") or headers.get("X-Telegram-Bot-Api-Secret-Token")

    if not received_token:
        logger.critical("Missing X-Telegram-Bot-Api-Secret-Token header")
        return False

    if not hmac.compare_digest(received_token, WEBHOOK_SECRET_TOKEN):
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


def is_event_relevant_to_bot(body: dict[str, Any]) -> bool:
    """Return True if the Telegram update warrants processing."""
    if "callback_query" in body:
        return True

    if "message" in body:
        msg = body["message"]
        if "new_chat_members" in msg:
            return True
        text_content = msg.get("text") or msg.get("caption") or ""
        if text_content.strip().startswith("/"):
            return True

    return False
