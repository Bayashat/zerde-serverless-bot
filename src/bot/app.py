"""Lazy application wiring for bot Lambda entry points."""

from __future__ import annotations

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

logger = LoggerAdapter(get_logger(__name__), {})

_bot: TelegramClient | None = None
_captcha_repo: CaptchaRepository | None = None
_dispatcher: Dispatcher | None = None


def get_bot() -> TelegramClient:
    """Return a singleton Telegram client, initialized only when an entry point needs it."""
    global _bot
    if _bot is None:
        _bot = TelegramClient()
    return _bot


def get_captcha_repo() -> CaptchaRepository:
    """Return a singleton captcha repository for webhook and SQS timeout tasks."""
    global _captcha_repo
    if _captcha_repo is None:
        _captcha_repo = CaptchaRepository()
    return _captcha_repo


def get_dispatcher() -> Dispatcher:
    """Wire the webhook dispatcher lazily and reuse it across warm invocations."""
    global _dispatcher
    if _dispatcher is None:
        dispatcher = Dispatcher(
            get_bot(),
            StatsRepository(),
            SQSClient(),
            VoteRepository(),
            QuizRepository() if QUIZ_TABLE_NAME else None,
            LambdaInvoker() if QUIZ_LAMBDA_NAME else None,
            captcha_repo=get_captcha_repo(),
        )
        register_handlers(dispatcher)
        _dispatcher = dispatcher
        logger.info("Bot dispatcher initialized and handlers registered")
    return _dispatcher
