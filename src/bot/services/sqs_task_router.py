"""SQS record routing for real-time bot work and vector indexing work."""

from __future__ import annotations

import json
import time
from typing import Any

from core.config import is_configured_group_chat
from core.logger import LoggerAdapter, get_logger
from services.group_memory_processor import process_daily_group_summaries_task, process_group_memory_task
from services.handlers import process_group_ask_task, process_timeout_task
from services.repositories.captcha import CaptchaRepository
from services.repositories.group_memory import GroupMemoryRepository
from services.spam.processor import process_spam_check_task
from services.telegram import TelegramClient
from services.vector_memory import process_vector_memory_backfill_task, process_vector_memory_task

logger = LoggerAdapter(get_logger(__name__), {})


def _load_task_body(record: dict[str, Any]) -> dict[str, Any]:
    return json.loads(record["body"])


def _should_skip_unconfigured_chat(body: dict[str, Any]) -> bool:
    task_chat_id = body.get("chat_id")
    if task_chat_id is None:
        return False
    if is_configured_group_chat(int(task_chat_id)):
        return False
    logger.debug("Skipping SQS task from non-whitelisted chat", extra={"chat_id": task_chat_id})
    return True


def _log_task_completed(record: dict[str, Any], body: dict[str, Any], task_type: str | None, started_at: float) -> None:
    elapsed_ms = int((time.monotonic() - started_at) * 1000)
    logger.info(
        "SQS task record completed",
        extra={
            "task_type": task_type,
            "latency_ms": elapsed_ms,
            "message_id": record.get("messageId"),
            "chat_id": body.get("chat_id"),
        },
    )


def _log_task_failure(record: dict[str, Any], exc: Exception) -> None:
    logger.error(
        "Critical error processing SQS record",
        extra={
            "message_id": record.get("messageId"),
            "error": exc,
        },
        exc_info=True,
    )


def process_sqs_event(
    event: dict[str, Any],
    bot: TelegramClient,
    captcha_repo: CaptchaRepository,
    memory_repo: GroupMemoryRepository | None = None,
) -> None:
    """Process main bot SQS tasks. Vector tasks are handled by the vector-indexer Lambda."""
    logger.debug(
        "Received SQS batch",
        extra={"record_count": len(event.get("Records", []))},
    )

    for record in event["Records"]:
        try:
            body = _load_task_body(record)
            if _should_skip_unconfigured_chat(body):
                continue

            task_type = body.get("task_type")
            t0 = time.monotonic()
            if task_type == "CHECK_TIMEOUT":
                body["_captcha_repo"] = captcha_repo
                process_timeout_task(bot, body)
            elif task_type == "SPAM_CHECK":
                process_spam_check_task(bot, body, captcha_repo=captcha_repo)
            elif task_type == "PROCESS_GROUP_ASK":
                if memory_repo is None:
                    raise RuntimeError("PROCESS_GROUP_ASK requires memory_repo")
                process_group_ask_task(repo=memory_repo, bot=bot, body=body)
            elif task_type == "PROCESS_GROUP_MEMORY":
                process_group_memory_task(body, repo=memory_repo)
            elif task_type == "PROCESS_DAILY_GROUP_SUMMARIES":
                process_daily_group_summaries_task(body, repo=memory_repo)
            else:
                logger.warning(
                    "Unexpected SQS record: unsupported task_type, ignoring",
                    extra={"task_type": task_type},
                )
            _log_task_completed(record, body, task_type, t0)

        except Exception as e:
            _log_task_failure(record, e)
            raise

    logger.info("SQS batch processing completed")


def process_vector_sqs_event(
    event: dict[str, Any],
    memory_repo: GroupMemoryRepository | None = None,
) -> None:
    """Process vector memory SQS tasks only. Failures bubble up for retry/DLQ."""
    logger.debug(
        "Received vector SQS batch",
        extra={"record_count": len(event.get("Records", []))},
    )

    for record in event["Records"]:
        try:
            body = _load_task_body(record)
            if _should_skip_unconfigured_chat(body):
                continue

            task_type = body.get("task_type")
            t0 = time.monotonic()
            if task_type == "PROCESS_VECTOR_MEMORY":
                process_vector_memory_task(body, repo=memory_repo)
            elif task_type == "PROCESS_VECTOR_MEMORY_BACKFILL":
                process_vector_memory_backfill_task(body, repo=memory_repo)
            else:
                logger.warning(
                    "Unexpected vector SQS record: unsupported task_type, ignoring",
                    extra={"task_type": task_type},
                )
            _log_task_completed(record, body, task_type, t0)

        except Exception as e:
            _log_task_failure(record, e)
            raise

    logger.info("Vector SQS batch processing completed")
