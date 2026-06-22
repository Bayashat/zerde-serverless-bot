"""SQS client for asynchronous bot tasks."""

import json

import boto3
from core.config import QUEUE_URL, VECTOR_MEMORY_QUEUE_URL
from core.logger import LoggerAdapter, get_logger
from services.repositories.group_memory import GroupMemoryRepository
from services.telegram_media import media_reference_log_extra

logger = LoggerAdapter(get_logger(__name__), {})

_SQS_CLIENT = None
_MAX_SQS_DELAY_SECONDS = 900


def _get_sqs_client():
    global _SQS_CLIENT
    if _SQS_CLIENT is None:
        _SQS_CLIENT = boto3.client("sqs")
    return _SQS_CLIENT


class SQSClient:
    """Sends asynchronous bot tasks to SQS."""

    def __init__(self) -> None:
        self.queue_url = QUEUE_URL
        self.vector_queue_url = VECTOR_MEMORY_QUEUE_URL or QUEUE_URL
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
        retrieval_query: str | None = None,
        requester_user_id: int | str | None = None,
        requester_username: str | None = None,
        requester_display_name: str | None = None,
        current_user_message: str | None = None,
        source_message_context: str | None = None,
        parent_bot_message_id: int | str | None = None,
        media_ref: dict[str, object] | None = None,
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
        if media_ref:
            payload["media_ref"] = media_ref
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
                    "has_media": bool(media_ref),
                    **(media_reference_log_extra(media_ref) if media_ref else {}),
                },
            )
        except Exception as e:
            logger.exception("Failed to send group ask task to SQS", extra={"error": e, "update_id": update_id})
            raise

    def send_proactive_candidate_task(
        self,
        *,
        update_id: int | None = None,
        chat_id: int,
        trigger_message_id: int,
        trigger_user_id: int | str | None = None,
        user_text: str,
        lang: str,
        candidate_kind: str = "proactive",
        trigger_username: str | None = None,
        trigger_display_name: str | None = None,
        trigger_sender_type: str | None = None,
        media_ref: dict[str, object] | None = None,
        created_at: int | None = None,
        delay_seconds: int = 45,
    ) -> None:
        """Enqueue a delayed proactive candidate for final social-timing evaluation."""
        delay_seconds = max(0, min(_MAX_SQS_DELAY_SECONDS, int(delay_seconds)))
        payload: dict[str, object] = {
            "task_type": "PROCESS_PROACTIVE_CANDIDATE",
            "chat_id": chat_id,
            "trigger_message_id": trigger_message_id,
            "user_text": user_text,
            "lang": lang,
            "candidate_kind": candidate_kind,
        }
        if update_id is not None:
            payload["update_id"] = update_id
        if trigger_user_id is not None:
            payload["trigger_user_id"] = trigger_user_id
        if trigger_username:
            payload["trigger_username"] = trigger_username
        if trigger_display_name:
            payload["trigger_display_name"] = trigger_display_name
        if trigger_sender_type:
            payload["trigger_sender_type"] = trigger_sender_type
        if media_ref:
            payload["media_ref"] = media_ref
        if created_at:
            payload["created_at"] = created_at

        try:
            media_log = media_reference_log_extra(media_ref) if media_ref else {}
            self.sqs_client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(payload),
                DelaySeconds=delay_seconds,
            )
            logger.info(
                "Queued proactive candidate task",
                extra={
                    "update_id": update_id,
                    "chat_id": chat_id,
                    "trigger_message_id": trigger_message_id,
                    "candidate_kind": candidate_kind,
                    "delay": delay_seconds,
                    "has_media": bool(media_ref),
                    **media_log,
                },
            )
        except Exception as e:
            logger.exception(
                "Failed to send proactive candidate task to SQS",
                extra={"error": e, "update_id": update_id, "chat_id": chat_id},
            )
            raise

    def send_ambient_reaction_task(
        self,
        *,
        chat_id: int,
        message_id: int,
        user_id: int | str,
        display_name: str,
        text: str,
        lang: str,
        sender_type: str | None = None,
        update_id: int | None = None,
        username: str | None = None,
        created_at: int | None = None,
        reply_chain: list[dict[str, object]] | None = None,
        force_reaction: bool = False,
    ) -> None:
        """Enqueue a sampled ambient reaction candidate for async classification."""
        payload: dict[str, object] = {
            "task_type": "PROCESS_AMBIENT_REACTION",
            "chat_id": chat_id,
            "message_id": message_id,
            "user_id": user_id,
            "display_name": display_name,
            "text": text,
            "lang": lang,
        }
        if sender_type:
            payload["sender_type"] = sender_type
        if update_id is not None:
            payload["update_id"] = update_id
        if username:
            payload["username"] = username
        if created_at:
            payload["created_at"] = created_at
        if reply_chain:
            payload["reply_chain"] = reply_chain
        if force_reaction:
            payload["force_reaction"] = True

        try:
            self.sqs_client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(payload),
            )
            logger.info(
                "Queued ambient reaction task",
                extra={
                    "update_id": update_id,
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "has_reply_chain": bool(reply_chain),
                },
            )
        except Exception as e:
            logger.exception(
                "Failed to send ambient reaction task to SQS",
                extra={"error": e, "update_id": update_id, "chat_id": chat_id},
            )
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
        is_reply: bool = False,
        has_mention: bool = False,
    ) -> None:
        """Enqueue a group message for async long-term memory processing."""
        payload: dict[str, object] = {
            "task_type": "PROCESS_GROUP_MEMORY",
            "chat_id": chat_id,
            "message_id": message_id,
            "user_id": user_id,
            "display_name": display_name,
            "text": text,
            "is_reply": bool(is_reply),
            "has_mention": bool(has_mention),
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

    def send_vector_memory_task(
        self,
        *,
        chat_id: int | str,
        source_sk: str,
        reason: str | None = None,
    ) -> None:
        """Enqueue vector indexing for one already-stored long-term memory item."""
        if not GroupMemoryRepository.is_vectorizable_sk(source_sk):
            logger.info(
                "Skipped vector memory task for non-vectorizable key",
                extra={"chat_id": chat_id, "source_sk": source_sk},
            )
            return
        payload: dict[str, object] = {
            "task_type": "PROCESS_VECTOR_MEMORY",
            "chat_id": chat_id,
            "source_sk": source_sk,
        }
        if reason:
            payload["reason"] = reason
        try:
            self.sqs_client.send_message(
                QueueUrl=getattr(self, "vector_queue_url", self.queue_url),
                MessageBody=json.dumps(payload),
            )
            logger.info("Queued vector memory task", extra={"chat_id": chat_id, "source_sk": source_sk})
        except Exception as e:
            logger.exception("Failed to send vector memory task to SQS", extra={"error": e, "chat_id": chat_id})
            raise

    def send_vector_memory_backfill_task(
        self,
        *,
        chat_id: int | str,
        limit: int = 50,
        start_key: dict | None = None,
    ) -> None:
        """Enqueue one page of vector-memory backfill for a chat."""
        payload: dict[str, object] = {
            "task_type": "PROCESS_VECTOR_MEMORY_BACKFILL",
            "chat_id": chat_id,
            "limit": limit,
        }
        if start_key:
            payload["start_key"] = start_key
        try:
            self.sqs_client.send_message(
                QueueUrl=getattr(self, "vector_queue_url", self.queue_url),
                MessageBody=json.dumps(payload),
            )
            logger.info(
                "Queued vector memory backfill task",
                extra={
                    "chat_id": chat_id,
                    "limit": limit,
                    "has_start_key": bool(start_key),
                    "start_sk": str(start_key.get("sk") or "") if start_key else "",
                    "start_prefix": str(start_key.get("__vector_prefix") or "") if start_key else "",
                },
            )
        except Exception as e:
            logger.exception(
                "Failed to send vector memory backfill task to SQS", extra={"error": e, "chat_id": chat_id}
            )
            raise
