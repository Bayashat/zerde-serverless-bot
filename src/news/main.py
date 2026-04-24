"""News Lambda: Daily IT news digest entry point."""

from typing import Any

from core.config import get_bot_token
from core.logger import LoggerAdapter, get_logger
from services.ai_client import create_ai_client
from services.digest import DigestService
from services.news_fetcher import NewsFetcher
from services.telegram import TelegramSender
from zerde_common.logging_utils import api_gateway_event_summary

logger = LoggerAdapter(get_logger(__name__), {})

_digest_svc: DigestService | None = None
logger.info("News Lambda initialized")


def _get_digest_service() -> DigestService:
    """Build the digest service on first invocation; reuse clients across warm invocations."""
    global _digest_svc
    if _digest_svc is None:
        _fetcher = NewsFetcher()
        _ai_client = create_ai_client()
        _sender = TelegramSender(get_bot_token())
        _digest_svc = DigestService(_fetcher, _ai_client, _sender)
    return _digest_svc


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """EventBridge scheduled handler — delegates to DigestService."""
    request_id = getattr(context, "aws_request_id", "unknown")
    logger.extra["request_id"] = request_id
    ex = api_gateway_event_summary(event) if isinstance(event, dict) else {"event_type": "non_dict"}
    ex["lambda_request_id"] = request_id
    logger.info("News Lambda handler called", extra=ex)
    return _get_digest_service().run(event)
