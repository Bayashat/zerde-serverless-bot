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

_bot = TelegramClient()
_stats_repo = StatsRepository()
_sqs_repo = SQSClient()
_dispatcher = Dispatcher(_bot, _stats_repo, _sqs_repo)

register_handlers(_dispatcher)
logger.info("Dispatcher initialized and handlers registered")


def lambda_handler(event: dict[str, Any], context: Any) -> None:
    """
    SQS Event Handler. Routes by task_type: timeout vs standard Telegram update.
    """
    logger.debug("Received batch", extra={"event": event})

    for record in event["Records"]:
        try:
            body = json.loads(record["body"])

            if body.get("task_type") == "CHECK_TIMEOUT":
                process_timeout_task(_bot, body)
            else:
                _dispatcher.process_update(body)

        except Exception as e:
            logger.error(
                "Critical error processing record",
                extra={"message_id": record.get("messageId"), "error": e},
                exc_info=True,
            )

    logger.info("Batch processing completed")
