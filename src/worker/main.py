"""Worker Lambda: Processes SQS messages."""

import json
from typing import Any

from aws_lambda_powertools import Logger
from core.dispatcher import Dispatcher
from repositories.sqs_repo import SQSClient
from repositories.stats_repository import StatsRepository
from repositories.telegram_client import TelegramClient
from services.handlers import process_timeout_task, register_handlers

logger = Logger()

# --- Initialization (Singleton Pattern) ---
# Initialize these OUTSIDE the handler to reuse connections across warm starts
_bot = TelegramClient()
_stats_repo = StatsRepository()
_sqs_repo = SQSClient()
_dispatcher = Dispatcher(_bot, _stats_repo, _sqs_repo)

# Register the user's handlers
register_handlers(_dispatcher)
logger.info("Dispatcher initialized and handlers registered")


def handle_timeout_task(body: dict[str, Any]) -> None:
    """Dispatch CHECK_TIMEOUT task to handler logic."""
    process_timeout_task(_bot, body)


def lambda_handler(event: dict[str, Any], context: Any) -> None:
    """
    SQS Event Handler. Routes by task_type: CHECK_TIMEOUT vs standard Telegram update.
    """
    logger.info("Received batch", count=len(event.get("Records", [])))

    for record in event["Records"]:
        try:
            body = json.loads(record["body"])

            if body.get("task_type") == "CHECK_TIMEOUT":
                handle_timeout_task(body)
            else:
                _dispatcher.process_update(body)

        except Exception as e:
            logger.error(
                f"Critical error processing record {record.get('messageId')}: {e}",
                exc_info=True,
            )

    logger.info("Batch processing completed")
