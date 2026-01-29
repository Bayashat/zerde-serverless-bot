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
    logger.info("Received event", event=event)
    try:
        # Verify webhook secret token (security check)
        if not verify_webhook_secret_token(event):
            logger.warning("Webhook secret token verification failed")
            return create_response(200, {"ok": False, "error": "Unauthorized"})

        # Parse API Gateway event body
        try:
            body = parse_api_gateway_event(event)
            logger.debug("Parsed API Gateway event")
        except ValueError as e:
            logger.warning(f"Failed to parse API Gateway event: {e}")
            return create_response(200, {"message": "Invalid request"})

        # Check if the event is relevant to the bot
        if not is_event_relevant_to_bot(body):
            logger.warning("Event is not relevant to the bot")
            return create_response(200, {"message": "Event is not relevant to the bot"})

        # Send event body to SQS
        sqs_client.send_telegram_update(body)

    except Exception as e:
        logger.error(f"Unexpected error in handler: {str(e)}", exc_info=True)

    # Always return 200 to prevent Telegram retries
    return create_response(200, {"message": "Webhook received"})
