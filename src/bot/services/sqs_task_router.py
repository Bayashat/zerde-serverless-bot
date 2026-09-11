"""SQS record routing for real-time bot work and vector indexing work."""

from __future__ import annotations

import json
import time
from typing import Any

from core.config import is_configured_group_chat
from core.logger import LoggerAdapter, get_logger
from services.handlers import process_group_ask_task, process_timeout_task
from services.memory_cutover import RETIRED_TASK_TYPES, is_current_explicit_task
from services.repositories.captcha import CaptchaRepository
from services.repositories.group_memory import GroupMemoryRepository
from services.repositories.sqs import SQSClient
from services.spam.processor import process_spam_check_task
from services.telegram import TelegramClient

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
    *,
    sqs_repo: SQSClient | None = None,
    memory_ingestion=None,
    quiz_repo=None,
) -> None:
    """Process main bot SQS tasks. Vector tasks are handled by the vector-indexer Lambda."""
    logger.debug(
        "Received SQS batch",
        extra={"record_count": len(event.get("Records", []))},
    )

    for record in event["Records"]:
        try:
            body = _load_task_body(record)
            task_type = body.get("task_type")
            if task_type in RETIRED_TASK_TYPES or (
                task_type == "PROCESS_GROUP_ASK" and not is_current_explicit_task(body)
            ):
                logger.info("Discarded retired task", extra={"task_type": task_type})
                continue
            if _should_skip_unconfigured_chat(body):
                continue

            t0 = time.monotonic()
            if task_type == "CHECK_TIMEOUT":
                body["_captcha_repo"] = captcha_repo
                body["_sqs_repo"] = sqs_repo or SQSClient()
                process_timeout_task(bot, body)
            elif task_type in {"PROCESS_QUIZ_ANSWER", "PROCESS_QUIZ_ANSWER_RECOVERY"}:
                from services.quiz_answers import process_quiz_answer_task, recover_quiz_answers

                if quiz_repo is None:
                    raise RuntimeError("Quiz answer repository is unavailable")
                if task_type == "PROCESS_QUIZ_ANSWER":
                    process_quiz_answer_task(repo=quiz_repo, body=body)
                else:
                    if body != {"schema": 2, "task_type": "PROCESS_QUIZ_ANSWER_RECOVERY"}:
                        raise ValueError("Unsupported quiz recovery envelope")
                    recover_quiz_answers(repo=quiz_repo, sqs_repo=sqs_repo or SQSClient())
            elif task_type == "SPAM_CHECK":
                outcome = process_spam_check_task(bot, body, captcha_repo=captcha_repo, memory_repo=None)
                if outcome == "clean" and body.get("source_ref") and memory_ingestion is not None:
                    # Persisted CLEAN plus staged original source authorize admission.
                    # The moderation task's text is never used as the source body.
                    case = memory_ingestion.moderation_repo.ensure_case(body)
                    memory_ingestion.promote_clean(case["case_id"])
            elif task_type == "PROCESS_GROUP_ASK":
                if memory_repo is None:
                    raise RuntimeError("PROCESS_GROUP_ASK requires memory_repo")
                process_group_ask_task(repo=memory_repo, bot=bot, body=body)
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
            task_type = body.get("task_type")
            if task_type in RETIRED_TASK_TYPES or (
                task_type == "PROCESS_GROUP_ASK" and not is_current_explicit_task(body)
            ):
                logger.info("Discarded retired task", extra={"task_type": task_type})
                continue
            if _should_skip_unconfigured_chat(body):
                continue
            t0 = time.monotonic()
            logger.warning("Unsupported vector task ignored", extra={"task_type": task_type})
            _log_task_completed(record, body, task_type, t0)

        except Exception as e:
            _log_task_failure(record, e)
            raise

    logger.info("Vector SQS batch processing completed")
