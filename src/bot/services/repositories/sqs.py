"""SQS client for asynchronous bot tasks."""

import json

import boto3
from core.config import QUEUE_URL
from core.logger import LoggerAdapter, get_logger
from services.memory_cutover import EXPLICIT_CONTEXT_VERSION
from services.telegram_media import media_reference_log_extra, media_references_log_extra

logger = LoggerAdapter(get_logger(__name__), {})

_SQS_CLIENT = None
_MAX_SQS_DELAY_SECONDS = 900


def _get_sqs_client():
    global _SQS_CLIENT
    if _SQS_CLIENT is None:
        _SQS_CLIENT = boto3.client("sqs")
    from services.memory_v2.cost_meter import register_client

    register_client(_SQS_CLIENT)
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
        *,
        generation: str | None = None,
    ) -> None:
        """Send a delayed message to SQS to check verification timeout."""
        payload = {
            "task_type": "CHECK_TIMEOUT",
            "chat_id": chat_id,
            "user_id": user_id,
            "join_message_id": join_message_id,
            "verification_message_id": verification_message_id,
        }
        if generation is not None:
            payload["generation"] = generation
        try:
            self.sqs_client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(payload),
                DelaySeconds=max(0, min(_MAX_SQS_DELAY_SECONDS, int(delay_seconds))),
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

    def send_quiz_answer_task(self, poll_id, user_id, delay_seconds=0):
        from services.repositories._quiz_answers import _identity

        _identity(poll_id, user_id)
        payload = {"schema": 2, "task_type": "PROCESS_QUIZ_ANSWER", "poll_id": poll_id, "user_id": str(user_id)}
        self.sqs_client.send_message(
            QueueUrl=self.queue_url, MessageBody=json.dumps(payload), DelaySeconds=max(0, min(900, int(delay_seconds)))
        )

    def send_group_ask_task(
        self,
        *,
        update_id: int,
        chat_id: int,
        reply_to_message_id: int,
        user_text: str,
        lang: str,
        retrieval_query: str | None = None,
        requester_user_id: int | str | None = None,
        requester_username: str | None = None,
        requester_display_name: str | None = None,
        current_user_message: str | None = None,
        request_sent_at: int | None = None,
        source_message_context: str | None = None,
        parent_bot_message_id: int | str | None = None,
        media_ref: dict[str, object] | None = None,
        media_refs: list[dict[str, object]] | None = None,
    ) -> None:
        """Enqueue an explicit agent request for async group-agent answering."""
        payload: dict[str, object] = {
            "task_type": "PROCESS_GROUP_ASK",
            "context_version": EXPLICIT_CONTEXT_VERSION,
            "update_id": update_id,
            "chat_id": chat_id,
            "reply_to_message_id": reply_to_message_id,
            "user_text": user_text,
            "lang": lang,
        }
        from services.memory_v2.explicit_request_gate import capture_configured

        gate = capture_configured(chat_id, requester_user_id, reply_to_message_id, request_sent_at)
        if gate is not None:
            payload["request_gate"] = gate
        if retrieval_query:
            payload["retrieval_query"] = retrieval_query
        if requester_user_id is not None:
            payload["requester_user_id"] = requester_user_id
        if requester_username:
            payload["requester_username"] = requester_username
        if requester_display_name:
            payload["requester_display_name"] = requester_display_name
        if current_user_message:
            payload["current_user_message"] = current_user_message
        if source_message_context:
            payload["source_message_context"] = source_message_context
        if parent_bot_message_id is not None:
            payload["parent_bot_message_id"] = parent_bot_message_id
        if media_refs:
            payload["media_refs"] = media_refs
        elif media_ref:
            payload["media_ref"] = media_ref
        try:
            self.sqs_client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(payload),
            )
            queued_refs = media_refs or ([media_ref] if media_ref else [])
            media_log = media_references_log_extra(queued_refs) if queued_refs else {}
            if len(queued_refs) == 1:
                media_log.update(media_reference_log_extra(queued_refs[0]))
            logger.info(
                "Queued group ask task",
                extra={
                    "update_id": update_id,
                    "chat_id": chat_id,
                    "reply_to_message_id": reply_to_message_id,
                    "has_media": bool(queued_refs),
                    **media_log,
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
        rule_score: float | None = None,
        message_context: dict[str, object] | None = None,
        source_ref: dict[str, object] | None = None,
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
        if rule_score is not None:
            payload["rule_score"] = float(rule_score)
        if message_context:
            payload["message_context"] = message_context
        if source_ref is not None:
            from services.memory_v2.models import SourceRef

            payload["source_ref"] = SourceRef(**source_ref).as_dict()
        try:
            self.sqs_client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(payload),
            )
            logger.info(
                "Queued spam check task",
                extra={
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "message_id": message_id,
                    "rules": triggered_rules,
                    "score": rule_score,
                    "has_message_context": bool(message_context),
                },
            )
        except Exception as e:
            logger.exception("Failed to send spam check task to SQS", extra={"error": e})
            raise
