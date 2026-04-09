"""Quiz Lambda: Daily tech quiz entry point."""

from typing import Any

from core.logger import LoggerAdapter, get_logger
from services.quiz_service import QuizService

logger = LoggerAdapter(get_logger(__name__), {})
logger.info("Quiz Lambda initialized")

_quiz_service = QuizService()


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """EventBridge scheduled handler — generate question and send quiz polls."""
    request_id = getattr(context, "aws_request_id", "unknown")
    logger.extra["request_id"] = request_id
    logger.info("Quiz Lambda handler called", extra={"event": event})

    chat_ids = event.get("chat_ids", [])
    lang = event.get("lang", "kk")

    if event.get("action") == "leaderboard":
        return _quiz_service.process_leaderboard(chat_ids, lang)

    if event.get("action") == "on_demand":
        chat_id = event.get("chat_id", "")
        topic = event.get("topic", "programming")
        difficulty = event.get("difficulty", "medium")
        include_rpd_footer = bool(event.get("include_rpd_footer", False))
        reply_to_message_id = event.get("reply_to_message_id")
        if not chat_id:
            return {"status": "error", "reason": "missing chat_id"}
        return _quiz_service.process_on_demand_quiz_with_feedback(
            chat_id,
            lang,
            topic,
            difficulty,
            include_rpd_footer=include_rpd_footer,
            reply_to_message_id=reply_to_message_id if isinstance(reply_to_message_id, int) else None,
        )

    return _quiz_service.process_daily_quiz(chat_ids, lang)
