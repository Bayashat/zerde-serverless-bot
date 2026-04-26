"""Bot Lambda: API Gateway webhook and SQS consumer (single function, one warm path)."""

import time
from typing import Any

from app import get_bot, get_captcha_repo, get_dispatcher
from core.logger import LoggerAdapter, get_logger
from services.sqs_task_router import process_sqs_event
from webhook import handle_event
from zerde_common.logging_utils import api_gateway_event_summary

logger = LoggerAdapter(get_logger(__name__), {})
logger.info("Bot Lambda initialized")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any] | None:
    """Route API Gateway or SQS events. Exceptions on SQS bubble up for retry/DLQ."""
    request_id = getattr(context, "aws_request_id", "unknown")
    logger.extra["request_id"] = request_id
    records = event.get("Records")
    if records and len(records) > 0 and records[0].get("eventSource") == "aws:sqs":
        log_extra: dict = api_gateway_event_summary(event)
        log_extra["lambda_request_id"] = request_id
        logger.info("Bot Lambda handler called (SQS)", extra=log_extra)
        started = time.monotonic()
        try:
            process_sqs_event(event, get_bot(), get_captcha_repo())
        finally:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            logger.info(
                "Bot SQS batch finished",
                extra={
                    "lambda_request_id": request_id,
                    "latency_ms": elapsed_ms,
                    "record_count": len(records),
                },
            )
        return None

    log_extra_api: dict = api_gateway_event_summary(event)
    log_extra_api["lambda_request_id"] = request_id
    logger.info("Bot Lambda handler called", extra=log_extra_api)
    return handle_event(event, get_dispatcher(), get_bot())
