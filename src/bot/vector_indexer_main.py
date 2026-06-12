"""Vector indexer Lambda: consumes only vector memory SQS tasks."""

from __future__ import annotations

import time
from typing import Any

from core.logger import LoggerAdapter, get_logger
from services.sqs_task_router import process_vector_sqs_event
from zerde_common.logging_utils import api_gateway_event_summary

logger = LoggerAdapter(get_logger(__name__), {})
logger.info("Vector indexer Lambda initialized")


def lambda_handler(event: dict[str, Any], context: Any) -> None:
    """Process vector-memory SQS batches. Exceptions bubble up for retry/DLQ."""
    request_id = getattr(context, "aws_request_id", "unknown")
    logger.extra["request_id"] = request_id
    records = event.get("Records", [])
    log_extra: dict = api_gateway_event_summary(event)
    log_extra["lambda_request_id"] = request_id
    logger.info("Vector indexer Lambda handler called", extra=log_extra)
    started = time.monotonic()
    try:
        process_vector_sqs_event(event)
    finally:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "Vector indexer SQS batch finished",
            extra={
                "lambda_request_id": request_id,
                "latency_ms": elapsed_ms,
                "record_count": len(records),
            },
        )
