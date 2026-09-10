"""Lazy application wiring for bot Lambda entry points."""

from __future__ import annotations

from core.config import MEMORY_TABLE_NAME, MEMORY_V2_TABLE_NAME, QUIZ_LAMBDA_NAME, QUIZ_TABLE_NAME
from core.dispatcher import Dispatcher
from core.logger import LoggerAdapter, get_logger
from services.handlers import register_handlers
from services.memory_v2.runtime import get_memory_ingestion  # noqa: F401 -- public bot composition export
from services.repositories import (
    CaptchaRepository,
    ContestRepository,
    GroupMemoryRepository,
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
_memory_repo: GroupMemoryRepository | None = None
_memory_v2_repo = None
_contest_repo: ContestRepository | None = None
_sqs_repo: SQSClient | None = None
_quiz_repo: QuizRepository | None = None
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


def get_memory_repo() -> GroupMemoryRepository | None:
    """Return a singleton group-memory repository when memory storage is configured."""
    global _memory_repo
    if not MEMORY_TABLE_NAME:
        return None
    if _memory_repo is None:
        _memory_repo = GroupMemoryRepository()
    return _memory_repo


def get_memory_v2_repo():
    """Independent lazy V2 storage. A configured table does not activate learning."""
    global _memory_v2_repo
    if not MEMORY_V2_TABLE_NAME:
        return None
    if _memory_v2_repo is None:
        from services.memory_v2.runtime import get_memory_v2_repo as get_configured_repo

        _memory_v2_repo = get_configured_repo()
    return _memory_v2_repo


def get_contest_repo() -> ContestRepository | None:
    """Return the contest truth owner when the shared memory table is configured."""
    global _contest_repo
    if not MEMORY_TABLE_NAME:
        return None
    if _contest_repo is None:
        _contest_repo = ContestRepository()
    return _contest_repo


def get_sqs_repo() -> SQSClient:
    """Return the shared main-queue client used by webhook and SQS continuations."""
    global _sqs_repo
    if _sqs_repo is None:
        _sqs_repo = SQSClient()
    return _sqs_repo


def get_quiz_repo():
    global _quiz_repo
    if not QUIZ_TABLE_NAME:
        return None
    if _quiz_repo is None:
        _quiz_repo = QuizRepository()
    return _quiz_repo


def get_dispatcher() -> Dispatcher:
    """Wire the webhook dispatcher lazily and reuse it across warm invocations."""
    global _dispatcher
    if _dispatcher is None:
        dispatcher = Dispatcher(
            get_bot(),
            StatsRepository(),
            get_sqs_repo(),
            VoteRepository(),
            get_quiz_repo(),
            LambdaInvoker() if QUIZ_LAMBDA_NAME else None,
            captcha_repo=get_captcha_repo(),
            memory_repo=get_memory_repo(),
            contest_repo=get_contest_repo(),
        )
        register_handlers(dispatcher)
        _dispatcher = dispatcher
        logger.info("Bot dispatcher initialized and handlers registered")
    return _dispatcher
