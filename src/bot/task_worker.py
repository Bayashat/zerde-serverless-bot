"""Bot task-worker Lambda: SQS consumer entry point only."""

import time
from typing import Any

from app import get_bot, get_captcha_repo
from core.logger import LoggerAdapter, get_logger
from services.sqs_task_router import process_sqs_event
from zerde_common.logging_utils import api_gateway_event_summary

logger = LoggerAdapter(get_logger(__name__), {})
logger.info("Bot task-worker Lambda initialized")


def lambda_handler(event: dict[str, Any], context: Any) -> None:
    """Process SQS tasks. Exceptions bubble up so SQS retry/DLQ semantics stay intact."""
    request_id = getattr(context, "aws_request_id", "unknown")
    logger.extra["request_id"] = request_id
    log_extra = api_gateway_event_summary(event)
    log_extra["lambda_request_id"] = request_id
    logger.info("Bot task-worker handler called", extra=log_extra)
    started = time.monotonic()
    try:
        process_sqs_event(event, get_bot(), get_captcha_repo())
    finally:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "Bot task-worker batch finished",
            extra={
                "lambda_request_id": request_id,
                "latency_ms": elapsed_ms,
                "record_count": len(event.get("Records", [])),
            },
        )
