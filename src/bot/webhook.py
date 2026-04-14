"""Webhook event handling: API Gateway / SQS routing and HTTP utilities."""

import base64
import hmac
import json
from typing import Any

from core.config import (
    CHAT_LANG_MAP,
    WEBHOOK_SECRET_TOKEN,
    get_chat_lang,
)
from core.dispatcher import Dispatcher
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.handlers import process_explain_task, process_timeout_task
from services.repositories.sqs import SQSClient
from services.repositories.stats import StatsRepository
from services.spam import RuleBasedSpamFilter, SpamEnforcer, collect_spam_screen_text, process_spam_check_task
from services.spam.channel_post import should_skip_spam_for_channel_discussion_mirror
from services.spam.chat_member import is_chat_admin_or_creator
from services.telegram import TelegramClient

logger = LoggerAdapter(get_logger(__name__), {})

_sqs_client = SQSClient()


# ── Public entry point (called by main.lambda_handler) ──────────────────────


def handle_event(
    event: dict[str, Any],
    dispatcher: Dispatcher,
    bot: TelegramClient,
) -> dict[str, Any] | None:
    """Route a raw Lambda event to the correct handler by source."""
    event_type = _detect_event_type(event)
    logger.debug("Detected event type", extra={"event_type": event_type})

    if event_type == "api_gateway":
        return _handle_api_gateway(event, dispatcher, bot)
    elif event_type == "sqs":
        _handle_sqs(event, bot)
    else:
        logger.warning("Unknown event type received", extra={"event": event})

    return None


# ── Event-type detection ────────────────────────────────────────────────────


def _detect_event_type(event: dict[str, Any]) -> str:
    """Detect which AWS service triggered this Lambda invocation."""
    if "Records" in event and event["Records"] and event["Records"][0].get("eventSource") == "aws:sqs":
        return "sqs"
    if "headers" in event or "requestContext" in event:
        return "api_gateway"
    return "unknown"


# ── API Gateway handler ────────────────────────────────────────────────────


def _handle_api_gateway(
    event: dict[str, Any],
    dispatcher: Dispatcher,
    bot: TelegramClient,
) -> dict[str, Any]:
    """Synchronous webhook handler: validate -> process -> return 200 OK."""
    try:
        if not verify_webhook_secret_token(event):
            return create_response(200, {"ok": False, "error": "Unauthorized"})

        try:
            body = parse_api_gateway_event(event)
            logger.info("API Gateway event parsed successfully")
        except ValueError as e:
            logger.error("Failed to parse API Gateway event", extra={"error": e})
            return create_response(200, {"message": "Invalid request"})

        chat_id, chat_type = _extract_chat_context(body)

        # Private chats are not supported: always return guidance text.
        if chat_type == "private":
            dispatcher.bot.send_message(
                chat_id,
                get_translated_text("private_message", get_chat_lang(chat_id)),
            )
            return create_response(200, {"message": "ok"})

        # Only allow configured group chats.
        if chat_type in {"group", "supergroup"} and not _is_chat_whitelisted(chat_id):
            dispatcher.bot.send_message(
                chat_id,
                get_translated_text("private_message", get_chat_lang(chat_id)),
            )
            logger.info("Blocked event from non-whitelisted chat", extra={"chat_id": chat_id})
            return create_response(200, {"message": "ok"})

        if _should_screen_for_spam(body):
            _run_spam_screening(body, bot, _sqs_client)

        if not is_event_relevant_to_bot(body):
            logger.info("Event not relevant to bot, ignoring")
            return create_response(200, {"message": "Not relevant"})

        if body.get("task_type") == "CHECK_TIMEOUT":
            process_timeout_task(bot, body)
        else:
            dispatcher.process_update(body)

    except Exception as e:
        logger.exception("Unexpected error in webhook handler", extra={"error": e})

    return create_response(200, {"message": "Webhook received"})


# ── SQS handler ────────────────────────────────────────────────────────────


def _handle_sqs(event: dict[str, Any], bot: TelegramClient) -> None:
    """Process SQS batch -- only CHECK_TIMEOUT tasks are expected."""
    logger.debug(
        "Received SQS batch",
        extra={"record_count": len(event.get("Records", []))},
    )

    for record in event["Records"]:
        try:
            body = json.loads(record["body"])

            task_type = body.get("task_type")
            if task_type == "CHECK_TIMEOUT":
                process_timeout_task(bot, body)
            elif task_type == "PROCESS_EXPLAIN":
                process_explain_task(bot, body)
            elif task_type == "SPAM_CHECK":
                process_spam_check_task(bot, body)
            else:
                logger.warning(
                    "Unexpected SQS record: unsupported task_type, ignoring",
                    extra={"task_type": task_type, "body": body},
                )

        except Exception as e:
            logger.error(
                "Critical error processing SQS record",
                extra={
                    "message_id": record.get("messageId"),
                    "error": e,
                },
                exc_info=True,
            )

    logger.info("SQS batch processing completed")


# ── HTTP / webhook utilities ────────────────────────────────────────────────


def verify_webhook_secret_token(event: dict[str, Any]) -> bool:
    """Verify Telegram webhook secret token (constant-time comparison)."""
    headers = event.get("headers", {})
    received_token = headers.get("x-telegram-bot-api-secret-token") or headers.get("X-Telegram-Bot-Api-Secret-Token")

    if not received_token:
        logger.critical("Missing X-Telegram-Bot-Api-Secret-Token header")
        return False

    if not hmac.compare_digest(received_token, WEBHOOK_SECRET_TOKEN):
        logger.critical("Webhook secret token mismatch")
        return False

    logger.info("Webhook secret token verified successfully")
    return True


def parse_api_gateway_event(event: dict[str, Any]) -> dict[str, Any]:
    """Extract Telegram webhook payload from an API Gateway event."""
    body = event.get("body")
    if not body:
        raise ValueError("Missing body in API Gateway event")

    if event.get("isBase64Encoded", False):
        body = base64.b64decode(body).decode("utf-8")

    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in body: {e}") from e

    return body


def create_response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Build an API Gateway-compatible HTTP response."""
    logger.debug("Creating response", extra={"body": body})
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _extract_chat_context(body: dict[str, Any]) -> tuple[int | None, str | None]:
    """Extract (chat_id, chat_type) from common Telegram update shapes."""
    message = body.get("message") or body.get("edited_message")
    if isinstance(message, dict):
        chat = message.get("chat", {})
        return chat.get("id"), chat.get("type")

    callback_query = body.get("callback_query", {})
    callback_message = callback_query.get("message", {})
    if isinstance(callback_message, dict):
        chat = callback_message.get("chat", {})
        return chat.get("id"), chat.get("type")

    return None, None


def _is_chat_whitelisted(chat_id: int | None) -> bool:
    """Return whether chat is explicitly configured in CHAT_LANG_MAP."""
    if chat_id is None:
        return False
    return str(chat_id) in CHAT_LANG_MAP


def _should_screen_for_spam(body: dict[str, Any]) -> bool:
    """Return True for non-command, non-bot regular messages that should be spam-screened."""
    if "message" not in body:
        return False
    msg = body["message"]
    if should_skip_spam_for_channel_discussion_mirror(msg):
        return False
    if "new_chat_members" in msg:
        return False
    if msg.get("from", {}).get("is_bot", False):
        return False
    primary = msg.get("text") or msg.get("caption") or ""
    if primary.strip().startswith("/"):
        return False
    combined = collect_spam_screen_text(msg)
    if not combined.strip():
        return False
    return True


def _run_spam_screening(body: dict[str, Any], bot: TelegramClient, sqs_repo: SQSClient) -> None:
    """Layer-1 spam screening: score message and enforce or enqueue. Never raises."""
    try:
        msg = body["message"]
        combined = collect_spam_screen_text(msg)
        if not combined.strip():
            return
        user_id: int = msg["from"]["id"]
        message_id: int = msg["message_id"]
        chat_id: int = msg["chat"]["id"]

        if is_chat_admin_or_creator(bot, chat_id, user_id):
            logger.info(
                "Spam screening skipped (sender is administrator or creator)",
                extra={"chat_id": chat_id, "user_id": user_id, "message_id": message_id},
            )
            return

        score, triggered_rules = RuleBasedSpamFilter().check(combined, user_id, chat_id)
        if score > 0.8:
            logger.info(
                "Rule-based spam detected, enforcing",
                extra={"chat_id": chat_id, "user_id": user_id, "score": score, "rules": triggered_rules},
            )
            SpamEnforcer(bot, StatsRepository()).enforce(
                chat_id=chat_id,
                user_id=user_id,
                message_id=message_id,
                reason=f"rules:{','.join(triggered_rules)}",
            )
            return
        if score > 0.3:
            logger.info(
                "Ambiguous spam score, queuing for AI check",
                extra={"chat_id": chat_id, "user_id": user_id, "score": score, "rules": triggered_rules},
            )
            sqs_repo.send_spam_check_task(
                chat_id=chat_id,
                user_id=user_id,
                message_id=message_id,
                text=combined,
                triggered_rules=triggered_rules,
            )
            return
        if triggered_rules:
            logger.info(
                "Spam screening below AI threshold (no automatic action)",
                extra={"chat_id": chat_id, "user_id": user_id, "score": score, "rules": triggered_rules},
            )
    except Exception as e:
        logger.error("Spam screening error, continuing normal flow", extra={"error": e})


def is_event_relevant_to_bot(body: dict[str, Any]) -> bool:
    """Return True if the Telegram update warrants processing."""
    if "poll_answer" in body:
        return True

    if "callback_query" in body:
        return True

    if "message" in body:
        msg = body["message"]
        if "new_chat_members" in msg:
            return True
        text_content = msg.get("text") or msg.get("caption") or ""
        if text_content.strip().startswith("/"):
            return True

    return False
