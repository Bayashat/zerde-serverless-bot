"""SQS message client."""

import json

import boto3
from aws_lambda_powertools import Logger
from repositories import QUEUE_URL

logger = Logger()

_SQS_CLIENT = boto3.client("sqs")


class SQSClient:
    """Client for sending raw updates to SQS."""

    def __init__(self) -> None:
        self.queue_url = QUEUE_URL
        self.sqs_client = _SQS_CLIENT

        logger.debug(f"SQS client initialized with queue URL: {self.queue_url}")

    def send_timeout_task(
        self,
        chat_id: int,
        user_id: int,
        message_id: int,
        delay_seconds: int = 60,
    ) -> None:
        """
        Send a delayed message to SQS to check verification timeout.
        """
        payload = {
            "task_type": "CHECK_TIMEOUT",
            "chat_id": chat_id,
            "user_id": user_id,
            "message_id": message_id,
        }
        try:
            self.sqs_client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(payload),
                DelaySeconds=delay_seconds,
            )
            logger.debug(
                "Queued timeout task",
                extra={"chat_id": chat_id, "user_id": user_id, "message_id": message_id, "delay": delay_seconds},
            )
        except Exception as e:
            logger.exception("Failed to send timeout task to SQS", extra={"error": e})
            raise
