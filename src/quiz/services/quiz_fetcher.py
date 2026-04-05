"""QuizAPI.io client with category rotation."""

import json
import random
from typing import Any
from urllib.parse import urlencode

import urllib3
from core.config import QUIZAPI_KEY
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(total=10))

QUIZAPI_BASE = "https://quizapi.io/api/v1/questions"

CATEGORY_POOL = [
    "programming",
    "ai",
    "cicd",
    "cloud",
    "containers",
    "cybersecurity",
    "data-structures",
    "database",
    "devops",
]

_ANSWER_KEYS = ["answer_a", "answer_b", "answer_c", "answer_d"]
_CORRECT_KEYS = ["answer_a_correct", "answer_b_correct", "answer_c_correct", "answer_d_correct"]


def parse_question(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a single QuizAPI response into a validated question dict.

    Returns None if the question is invalid (missing options, no correct answer, etc.).
    """

    # {
    #   "id": "ques_xyz789",
    #   "text": "What is the typeof null in JavaScript?",
    #   "type": "MULTIPLE_CHOICE",
    #   "difficulty": "MEDIUM",
    #   "explanation": "typeof null returns 'object' due to a legacy bug.",
    #   "category": "Programming",
    #   "tags": ["javascript", "fundamentals"],
    #   "quizId": "quiz_abc123",
    #   "quizTitle": "JavaScript Essentials",
    #   "answers": [
    #     { "id": "ans_1", "text": "null", "isCorrect": false },
    #     { "id": "ans_2", "text": "object", "isCorrect": true },
    #     { "id": "ans_3", "text": "undefined", "isCorrect": false },
    #     { "id": "ans_4", "text": "string", "isCorrect": false }
    #   ]
    # }
    question_text = (raw.get("text") or "").strip()
    if not question_text:
        return None

    answers = raw.get("answers", [])
    # options = [answers.get(k) for k in _ANSWER_KEYS]
    options = [{"text": answer.get("text"), "id": answer.get("id")} for answer in answers]
    if not all(opt.get("text") for opt in options):
        return None

    # correct_id = [answer.get("id") for answer in answers if answer.get("isCorrect") == True]
    correct_index = [i for i, answer in enumerate(answers) if answer.get("isCorrect") is True]
    if len(correct_index) != 1:
        return None

    return {
        "question": question_text,
        "options": options,
        "correct_option_ids": correct_index,
        "explanation": (raw.get("explanation") or "").strip() or None,
    }


class QuizFetcher:
    """Fetches and validates questions from QuizAPI.io."""

    def fetch_question(self, category_queue: list[str]) -> tuple[dict[str, Any], str, list[str]] | None:
        """Fetch a valid question using the category queue ("deck of cards").

        Returns (parsed_question, used_category, remaining_queue) or None.
        """
        if not category_queue:
            category_queue = list(CATEGORY_POOL)
            random.shuffle(category_queue)
            logger.info("New category round started", extra={"queue": category_queue})

        remaining = list(category_queue)
        restarted = False
        while remaining:
            category = remaining.pop(0)
            question = self._try_category(category)
            if question:
                logger.info("Fetched question", extra={"category": category})
                return question, category, remaining

            if not remaining and not restarted:
                restarted = True
                remaining = list(CATEGORY_POOL)
                random.shuffle(remaining)
                logger.warning("Queue exhausted, starting fresh category round")

        logger.error("All categories exhausted after retry, no valid question found")
        return None

    def _try_category(self, category: str) -> dict[str, Any] | None:
        """Try to fetch a valid question for a given category."""
        params = {"tags": category, "limit": "5", "difficulty": "EASY", "type": "MULTIPLE_CHOICE"}
        url = f"{QUIZAPI_BASE}?{urlencode(params)}"
        headers = {
            "Authorization": f"Bearer {QUIZAPI_KEY}",
        }

        try:
            resp = http.request("GET", url, headers=headers)
            if resp.status != 200:
                logger.warning(
                    "QuizAPI request failed",
                    extra={"status": resp.status, "category": category},
                )
                return None

            questions = json.loads(resp.data.decode("utf-8"))
            for raw in questions.get("data", []):
                parsed = parse_question(raw)
                if parsed:
                    return parsed

        except Exception as e:
            logger.error("QuizAPI request error", extra={"error": str(e), "category": category})

        return None
