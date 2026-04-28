"""SQS record routing: captcha timeout, /wtf async explain, Groq spam check."""

from __future__ import annotations

import json
import time
from typing import Any

from core.config import is_configured_group_chat
from core.logger import LoggerAdapter, get_logger
from services.handlers import process_explain_task, process_timeout_task
from services.repositories.captcha import CaptchaRepository
from services.spam.processor import process_spam_check_task
from services.telegram import TelegramClient

logger = LoggerAdapter(get_logger(__name__), {})


def process_sqs_event(
    event: dict[str, Any],
    bot: TelegramClient,
    captcha_repo: CaptchaRepository,
) -> None:
    """Process one Lambda invocation carrying SQS ``Records``."""
    logger.debug(
        "Received SQS batch",
        extra={"record_count": len(event.get("Records", []))},
    )

    for record in event["Records"]:
        try:
            body = json.loads(record["body"])

            task_chat_id = body.get("chat_id")
            if task_chat_id is not None and not is_configured_group_chat(int(task_chat_id)):
                logger.debug("Skipping SQS task from non-whitelisted chat", extra={"chat_id": task_chat_id})
                continue

            task_type = body.get("task_type")
            t0 = time.monotonic()
            if task_type == "CHECK_TIMEOUT":
                body["_captcha_repo"] = captcha_repo
                process_timeout_task(bot, body)
            elif task_type == "PROCESS_EXPLAIN":
                process_explain_task(bot, body)
            elif task_type == "SPAM_CHECK":
                process_spam_check_task(bot, body)
            else:
                logger.warning(
                    "Unexpected SQS record: unsupported task_type, ignoring",
                    extra={"task_type": task_type},
                )
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.info(
                "SQS task record completed",
                extra={
                    "task_type": task_type,
                    "latency_ms": elapsed_ms,
                    "message_id": record.get("messageId"),
                    "chat_id": task_chat_id,
                },
            )

        except Exception as e:
            logger.error(
                "Critical error processing SQS record",
                extra={
                    "message_id": record.get("messageId"),
                    "error": e,
                },
                exc_info=True,
            )
            raise

    logger.info("SQS batch processing completed")
