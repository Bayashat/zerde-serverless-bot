"""Bot Lambda: Unified entrypoint for API Gateway and SQS events."""

from typing import Any

from core.config import QUIZ_LAMBDA_NAME, QUIZ_TABLE_NAME
from core.dispatcher import Dispatcher
from core.logger import LoggerAdapter, get_logger
from services.handlers import register_handlers
from services.repositories import (
    CaptchaRepository,
    LambdaInvoker,
    QuizRepository,
    SQSClient,
    StatsRepository,
    VoteRepository,
)
from services.telegram import TelegramClient
from webhook import handle_event

logger = LoggerAdapter(get_logger(__name__), {})

_bot = TelegramClient()
_stats_repo = StatsRepository()
_sqs_repo = SQSClient()
_vote_repo = VoteRepository()
_captcha_repo = CaptchaRepository()
_quiz_repo = QuizRepository() if QUIZ_TABLE_NAME else None
_lambda_invoker = LambdaInvoker() if QUIZ_LAMBDA_NAME else None
_dispatcher = Dispatcher(
    _bot,
    _stats_repo,
    _sqs_repo,
    _vote_repo,
    _quiz_repo,
    _lambda_invoker,
    captcha_repo=_captcha_repo,
)
register_handlers(_dispatcher)
logger.info("Bot Lambda initialized and handlers registered")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any] | None:
    """Unified Lambda handler routing by event source."""
    request_id = getattr(context, "aws_request_id", "unknown")
    logger.extra["request_id"] = request_id
    logger.info("Bot Lambda handler called", extra={"event": event})
    return handle_event(event, _dispatcher, _bot)
