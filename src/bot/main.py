"""Bot webhook Lambda: API Gateway entry point only."""

from typing import Any

from app import get_bot, get_dispatcher
from core.logger import LoggerAdapter, get_logger
from webhook import handle_event
from zerde_common.logging_utils import api_gateway_event_summary

logger = LoggerAdapter(get_logger(__name__), {})
logger.info("Bot webhook Lambda initialized")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any] | None:
    """Webhook Lambda handler routing API Gateway events into the bot dispatcher."""
    request_id = getattr(context, "aws_request_id", "unknown")
    logger.extra["request_id"] = request_id
    log_extra: dict = api_gateway_event_summary(event)
    log_extra["lambda_request_id"] = request_id
    logger.info("Bot Lambda handler called", extra=log_extra)
    return handle_event(event, get_dispatcher(), get_bot())
