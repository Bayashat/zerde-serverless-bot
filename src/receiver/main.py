"""Receiver Lambda: HTTP API entrypoint for Telegram webhook."""

from typing import Any

from aws_lambda_powertools import Logger
from repositories.sqs_repo import SQSClient
from services.api_gateway_utils import (
    create_response,
    is_event_relevant_to_bot,
    parse_api_gateway_event,
    verify_webhook_secret_token,
)

logger = Logger()

sqs_client = SQSClient()


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Handle incoming Telegram webhook requests.

    Validates the secret token, then pushes the message to SQS for async processing.
    Returns 200 OK immediately to Telegram to prevent retries.

    Args:
        event: API Gateway HTTP API event
        context: Lambda context

    Returns:
        API Gateway HTTP API response
    """
    logger.info("Received event", extra={"event": event})
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
            logger.error("Event is not relevant to the bot", extra={"body": body})
            return create_response(200, {"message": "Event is not relevant to the bot"})

        sqs_client.send_telegram_update(body)
        logger.info("Telegram update queued successfully")

    except Exception as e:
        logger.exception("Unexpected error in handler", extra={"error": e})

    return create_response(200, {"message": "Webhook received"})
