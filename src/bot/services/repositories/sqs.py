"""SQS client for deferred timeout tasks."""

import json

import boto3
from core.config import QUEUE_URL
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

_SQS_CLIENT = boto3.client("sqs")


class SQSClient:
    """Sends delayed CHECK_TIMEOUT tasks to SQS."""

    def __init__(self) -> None:
        self.queue_url = QUEUE_URL
        self.sqs_client = _SQS_CLIENT
        logger.debug(f"SQS client initialized with queue URL: {self.queue_url}")

    def send_timeout_task(
        self,
        chat_id: int,
        user_id: int,
        join_message_id: int,
        verification_message_id: int,
        delay_seconds: int = 60,
    ) -> None:
        """Send a delayed message to SQS to check verification timeout."""
        payload = {
            "task_type": "CHECK_TIMEOUT",
            "chat_id": chat_id,
            "user_id": user_id,
            "join_message_id": join_message_id,
            "verification_message_id": verification_message_id,
        }
        try:
            self.sqs_client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(payload),
                DelaySeconds=delay_seconds,
            )
            logger.debug(
                "Queued timeout task",
                extra={
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "join_message_id": join_message_id,
                    "verification_message_id": verification_message_id,
                    "delay": delay_seconds,
                },
            )
        except Exception as e:
            logger.exception("Failed to send timeout task to SQS", extra={"error": e})
            raise

    def send_explain_task(
        self,
        *,
        update_id: int,
        chat_id: int,
        reply_to_message_id: int,
        term: str,
        lang: str,
        style: str,
    ) -> None:
        """Send async explain task for /wtf or /explain processing."""
        payload = {
            "task_type": "PROCESS_EXPLAIN",
            "update_id": update_id,
            "chat_id": chat_id,
            "reply_to_message_id": reply_to_message_id,
            "term": term,
            "lang": lang,
            "style": style,
        }
        try:
            self.sqs_client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(payload),
            )
            logger.info(
                "Queued explain task",
                extra={
                    "update_id": update_id,
                    "chat_id": chat_id,
                    "style": style,
                },
            )
        except Exception as e:
            logger.exception("Failed to send explain task to SQS", extra={"error": e, "update_id": update_id})
            raise

    def send_spam_check_task(
        self,
        *,
        chat_id: int,
        user_id: int,
        message_id: int,
        text: str,
        triggered_rules: list[str],
    ) -> None:
        """Enqueue a SPAM_CHECK task for async Layer-2 Groq classification."""
        payload = {
            "task_type": "SPAM_CHECK",
            "chat_id": chat_id,
            "user_id": user_id,
            "message_id": message_id,
            "text": text,
            "triggered_rules": triggered_rules,
        }
        try:
            self.sqs_client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(payload),
            )
            logger.info(
                "Queued spam check task",
                extra={"chat_id": chat_id, "user_id": user_id, "message_id": message_id},
            )
        except Exception as e:
            logger.exception("Failed to send spam check task to SQS", extra={"error": e})
