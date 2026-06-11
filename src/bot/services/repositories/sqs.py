"""SQS client for asynchronous bot tasks."""

import json

import boto3
from core.config import QUEUE_URL
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

_SQS_CLIENT = None


def _get_sqs_client():
    global _SQS_CLIENT
    if _SQS_CLIENT is None:
        _SQS_CLIENT = boto3.client("sqs")
    return _SQS_CLIENT


class SQSClient:
    """Sends asynchronous bot tasks to SQS."""

    def __init__(self) -> None:
        self.queue_url = QUEUE_URL
        logger.debug(f"SQS client initialized with queue URL: {self.queue_url}")

    @property
    def sqs_client(self):
        return _get_sqs_client()

    def send_timeout_task(
        self,
        chat_id: int,
        user_id: int,
        join_message_id: int,
        verification_message_id: int,
        delay_seconds: int = 120,
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

    def send_group_ask_task(
        self,
        *,
        update_id: int,
        chat_id: int,
        reply_to_message_id: int,
        user_text: str,
        lang: str,
    ) -> None:
        """Enqueue an explicit /ask request for async group-agent answering."""
        payload: dict[str, object] = {
            "task_type": "PROCESS_GROUP_ASK",
            "update_id": update_id,
            "chat_id": chat_id,
            "reply_to_message_id": reply_to_message_id,
            "user_text": user_text,
            "lang": lang,
        }
        try:
            self.sqs_client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(payload),
            )
            logger.info(
                "Queued group ask task",
                extra={
                    "update_id": update_id,
                    "chat_id": chat_id,
                    "reply_to_message_id": reply_to_message_id,
                },
            )
        except Exception as e:
            logger.exception("Failed to send group ask task to SQS", extra={"error": e, "update_id": update_id})
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

    def send_group_memory_task(
        self,
        *,
        chat_id: int,
        message_id: int,
        user_id: int,
        display_name: str,
        username: str | None,
        text: str,
        created_at: int | None = None,
    ) -> None:
        """Enqueue a group message for async long-term memory processing."""
        payload: dict[str, object] = {
            "task_type": "PROCESS_GROUP_MEMORY",
            "chat_id": chat_id,
            "message_id": message_id,
            "user_id": user_id,
            "display_name": display_name,
            "text": text,
        }
        if username:
            payload["username"] = username
        if created_at:
            payload["created_at"] = created_at

        try:
            self.sqs_client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(payload),
            )
            logger.info(
                "Queued group memory task",
                extra={"chat_id": chat_id, "message_id": message_id, "user_id": user_id},
            )
        except Exception as e:
            logger.exception("Failed to send group memory task to SQS", extra={"error": e, "chat_id": chat_id})
            raise

    def send_daily_group_summaries_task(
        self,
        *,
        chat_ids: list[int | str],
        summary_date: str | None = None,
    ) -> None:
        """Enqueue daily summary generation for all configured memory-enabled groups."""
        payload: dict[str, object] = {
            "task_type": "PROCESS_DAILY_GROUP_SUMMARIES",
            "chat_ids": [str(chat_id) for chat_id in chat_ids],
        }
        if summary_date:
            payload["summary_date"] = summary_date

        try:
            self.sqs_client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(payload),
            )
            logger.info("Queued daily group summaries task", extra={"chat_count": len(chat_ids)})
        except Exception as e:
            logger.exception("Failed to send daily group summaries task", extra={"error": e})
            raise
