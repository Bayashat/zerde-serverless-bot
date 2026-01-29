import base64
import hmac
import json
from typing import Any

from aws_lambda_powertools import Logger
from services import WEBHOOK_SECRET_TOKEN

logger = Logger()


def verify_webhook_secret_token(event: dict[str, Any]) -> bool:
    """
    Verify Telegram webhook secret token from X-Telegram-Bot-Api-Secret-Token header.

    Telegram sends a secret token with each webhook request to verify authenticity.
    This prevents spoofed requests from reaching the bot.
    """
    # Get headers from API Gateway event
    headers = event.get("headers", {})
    received_token = headers.get("x-telegram-bot-api-secret-token") or headers.get("X-Telegram-Bot-Api-Secret-Token")

    if not received_token:
        logger.warning("Missing X-Telegram-Bot-Api-Secret-Token header")
        return False

    # Use constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(received_token, WEBHOOK_SECRET_TOKEN):
        logger.warning("Webhook secret token mismatch")
        return False

    logger.debug("Webhook secret token verified successfully")
    return True


def parse_api_gateway_event(event: dict[str, Any]) -> dict[str, Any]:
    """
    Parse API Gateway event and extract Telegram webhook payload.
    """
    body = event.get("body")
    if not body:
        raise ValueError("Missing body in API Gateway event")

    # Handle base64 encoding (if API Gateway REST API is used)
    is_base64 = event.get("isBase64Encoded", False)
    if is_base64:
        body = base64.b64decode(body).decode("utf-8")

    # Parse JSON body (API Gateway may pass it as string)
    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in body: {e}") from e

    return body


def create_response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """
    Create API Gateway response format.
    """
    logger.debug(f"Creating response: {body}")
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
        },
        "body": json.dumps(body),
    }


def is_event_relevant_to_bot(body: dict[str, Any]) -> bool:
    """
    Check if the event is relevant to the bot.
    """
    is_relevant = False

    if "callback_query" in body:
        is_relevant = True
    elif "message" in body:
        msg = body["message"]

        if "new_chat_members" in msg:
            is_relevant = True

        # commands with /
        text_content = msg.get("text") or msg.get("caption") or ""
        if text_content.strip().startswith("/"):
            is_relevant = True
    return is_relevant
