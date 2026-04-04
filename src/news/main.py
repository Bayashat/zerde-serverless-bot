"""News Lambda: Daily IT news digest entry point."""

from typing import Any

from aws_lambda_powertools import Logger
from core.config import BOT_TOKEN
from services.ai_client import create_ai_client
from services.digest import DigestService
from services.news_fetcher import NewsFetcher
from services.telegram import TelegramSender

logger = Logger()

# Module-level initialization: warm across Lambda invocations.
_fetcher = NewsFetcher()
_ai_client = create_ai_client()
_sender = TelegramSender(BOT_TOKEN)
_digest_svc = DigestService(_fetcher, _ai_client, _sender)
logger.info("News Lambda initialized")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """EventBridge scheduled handler — delegates to DigestService."""
    logger.info("News Lambda handler called", extra={"event": event})
    return _digest_svc.run(event)
