"""Quiz Lambda: Daily tech quiz entry point."""

from typing import Any

from core.logger import LoggerAdapter, get_logger
from services.quiz_fetcher import QuizFetcher
from services.quiz_sender import QuizSender
from services.repository import QuizRepository

logger = LoggerAdapter(get_logger(__name__), {})

_fetcher = QuizFetcher()
_sender = QuizSender()
_repo = QuizRepository()
logger.info("Quiz Lambda initialized")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """EventBridge scheduled handler — fetch question and send quiz polls."""
    request_id = getattr(context, "aws_request_id", "unknown")
    logger.extra["request_id"] = request_id
    logger.info("Quiz Lambda handler called", extra={"event": event})

    chat_ids = event.get("chat_ids", [])
    if not chat_ids:
        logger.warning("No chat_ids in event payload")
        return {"status": "skipped", "reason": "no chat_ids"}

    # Fetch question with category rotation
    last_category = _repo.get_last_category()
    result = _fetcher.fetch_question(last_category)
    if not result:
        logger.error("Failed to fetch a valid question")
        return {"status": "error", "reason": "no valid question"}

    question, category = result
    logger.info("Question fetched", extra={"category": category, "question": question["question"][:50]})

    # Send quiz poll to each chat
    sent_count = 0
    for chat_id in chat_ids:
        poll_result = _sender.send_quiz_poll(
            chat_id=chat_id,
            question=question["question"],
            options=question["options"],
            correct_option_id=question["correct_option_id"],
            explanation=question.get("explanation"),
        )
        if poll_result:
            poll_id = str(poll_result.get("poll", {}).get("id", ""))
            message_id = poll_result.get("message_id", 0)
            _repo.save_quiz_record(chat_id, question, category, poll_id, message_id)
            sent_count += 1

    # Update last category after successful sends
    if sent_count > 0:
        _repo.save_last_category(category)

    logger.info("Quiz Lambda completed", extra={"sent": sent_count, "total": len(chat_ids)})
    return {"status": "ok", "sent": sent_count, "total": len(chat_ids)}
