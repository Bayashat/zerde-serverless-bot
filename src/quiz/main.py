# src/quiz/main.py
"""Quiz Lambda: Daily tech quiz entry point."""

import random
from typing import Any

from core.logger import LoggerAdapter, get_logger
from services.quiz_generator import CATEGORY_POOL, QuizGenerator
from services.quiz_sender import QuizSender
from services.repository import QuizRepository

logger = LoggerAdapter(get_logger(__name__), {})

_generator = QuizGenerator()
_sender = QuizSender()
_repo = QuizRepository()
logger.info("Quiz Lambda initialized")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """EventBridge scheduled handler — generate question and send quiz polls."""
    request_id = getattr(context, "aws_request_id", "unknown")
    logger.extra["request_id"] = request_id
    logger.info("Quiz Lambda handler called", extra={"event": event})

    chat_ids = event.get("chat_ids", [])
    lang = event.get("lang", "kk")
    if not chat_ids:
        logger.warning("No chat_ids in event payload")
        return {"status": "skipped", "reason": "no chat_ids"}

    # Deck-of-cards category rotation
    category_queue = _repo.get_category_queue()
    if not category_queue:
        category_queue = list(CATEGORY_POOL)
        random.shuffle(category_queue)
        logger.info("New category round started", extra={"queue": category_queue})

    remaining = list(category_queue)
    generated = None
    used_category = None
    restarted = False

    while remaining:
        category = remaining.pop(0)
        question = _generator.generate_question(category, lang)
        if question:
            generated = question
            used_category = category
            logger.info("Question generated", extra={"category": category, "lang": lang})
            break
        if not remaining and not restarted:
            restarted = True
            remaining = list(CATEGORY_POOL)
            random.shuffle(remaining)
            logger.warning("Queue exhausted, starting fresh category round")

    if not generated:
        logger.error("Failed to generate a valid question after all categories")
        return {"status": "error", "reason": "no valid question"}

    # Send quiz poll to each chat
    sent_count = 0
    for chat_id in chat_ids:
        poll_result = _sender.send_quiz_poll(
            chat_id=chat_id,
            question=generated["question"],
            options=generated["options"],
            correct_option_id=generated["correct_option_index"],
            explanation=generated.get("explanation"),
        )
        if poll_result:
            poll_id = str(poll_result.get("poll", {}).get("id", ""))
            message_id = poll_result.get("message_id", 0)
            _repo.save_quiz_record(
                chat_id=chat_id,
                question=generated["question"],
                options=generated["options"],
                correct_option_id=generated["correct_option_index"],
                explanation=generated.get("explanation"),
                category=used_category,
                lang=lang,
                poll_id=poll_id,
                message_id=message_id,
            )
            sent_count += 1

    if sent_count > 0:
        _repo.save_category_queue(remaining, used_category)

    logger.info("Quiz Lambda completed", extra={"sent": sent_count, "total": len(chat_ids)})
    return {"status": "ok", "sent": sent_count, "total": len(chat_ids)}
