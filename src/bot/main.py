"""Bot Lambda: Unified entrypoint for API Gateway and SQS events."""

from typing import Any

from aws_lambda_powertools import Logger
from core.dispatcher import Dispatcher
from services.handlers import register_handlers
from services.repositories import SQSClient, StatsRepository, VoteRepository
from services.telegram import TelegramClient
from webhook import handle_event

logger = Logger()

# Module-level initialization: captured by SnapStart snapshot after first cold start.
_bot = TelegramClient()
_stats_repo = StatsRepository()
_sqs_repo = SQSClient()
_vote_repo = VoteRepository()
_dispatcher = Dispatcher(_bot, _stats_repo, _sqs_repo, _vote_repo)
register_handlers(_dispatcher)
logger.info("Bot Lambda initialized and handlers registered")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any] | None:
    """Unified Lambda handler routing by event source."""
    logger.info("Bot Lambda handler called", extra={"event": event})
    return handle_event(event, _dispatcher, _bot)
