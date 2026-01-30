"""SQS message client."""

import json
from typing import Any

import boto3
from aws_lambda_powertools import Logger
from repositories import QUEUE_URL

logger = Logger()

_SQS_CLIENT = boto3.client("sqs")


class SQSClient:
    """Client for sending raw updates to SQS."""

    def __init__(self) -> None:
        """Initialize SQS client."""
        self.queue_url = QUEUE_URL
        self.sqs_client = _SQS_CLIENT

        logger.info("SQS client initialized with queue URL", extra={"queue_url": self.queue_url})

    def send_telegram_update(self, update_payload: dict[str, Any]) -> None:
        """
        Push the raw Telegram update to SQS for asynchronous processing.

        Args:
            update_payload: The full JSON body received from Telegram Webhook.

        Raises:
            Exception: Propagates boto3 exceptions to be handled by the caller.
        """
        try:
            self.sqs_client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(update_payload),
            )

            update_id = update_payload.get("update_id", "unknown")
            logger.info("Successfully queued update", extra={"update_id": update_id})

        except Exception as e:
            logger.exception("Failed to send update to SQS", extra={"error": e})
            raise e
