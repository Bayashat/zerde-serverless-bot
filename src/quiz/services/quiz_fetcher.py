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

CATEGORY_POOL = ["code", "Linux", "Docker", "DevOps", "networking", "security"]

_ANSWER_KEYS = ["answer_a", "answer_b", "answer_c", "answer_d"]
_CORRECT_KEYS = ["answer_a_correct", "answer_b_correct", "answer_c_correct", "answer_d_correct"]


def parse_question(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a single QuizAPI response into a validated question dict.

    Returns None if the question is invalid (missing options, no correct answer, etc.).
    """
    question_text = (raw.get("question") or "").strip()
    if not question_text:
        return None

    answers = raw.get("answers", {})
    options = [answers.get(k) for k in _ANSWER_KEYS]
    if not all(options):
        return None

    correct_answers = raw.get("correct_answers", {})
    correct_idx = None
    for i, key in enumerate(_CORRECT_KEYS):
        if correct_answers.get(key) == "true":
            if correct_idx is not None:
                return None  # Multiple correct answers — skip
            correct_idx = i

    if correct_idx is None:
        return None

    return {
        "question": question_text,
        "options": options,
        "correct_option_id": correct_idx,
        "explanation": (raw.get("explanation") or "").strip() or None,
    }


class QuizFetcher:
    """Fetches and validates questions from QuizAPI.io."""

    def _get_available_categories(self, last_category: str | None) -> list[str]:
        """Return category pool excluding last used category."""
        if last_category and last_category in CATEGORY_POOL:
            return [c for c in CATEGORY_POOL if c != last_category]
        return CATEGORY_POOL

    def fetch_question(self, last_category: str | None) -> tuple[dict[str, Any], str] | None:
        """Fetch a valid question from QuizAPI.io with category rotation.

        Returns (parsed_question, category) or None if all categories exhausted.
        """
        available = self._get_available_categories(last_category)
        random.shuffle(available)

        for category in available:
            question = self._try_category(category)
            if question:
                logger.info("Fetched question", extra={"category": category})
                return question, category

        logger.error("All categories exhausted, no valid question found")
        return None

    def _try_category(self, category: str) -> dict[str, Any] | None:
        """Try to fetch a valid question for a given category."""
        params = {
            "apiKey": QUIZAPI_KEY,
            "tags": category,
            "limit": "5",
            "multiple": "true",
        }
        url = f"{QUIZAPI_BASE}?{urlencode(params)}"

        try:
            resp = http.request("GET", url)
            if resp.status != 200:
                logger.warning(
                    "QuizAPI request failed",
                    extra={"status": resp.status, "category": category},
                )
                return None

            questions = json.loads(resp.data.decode("utf-8"))
            for raw in questions:
                parsed = parse_question(raw)
                if parsed:
                    return parsed

        except Exception as e:
            logger.error("QuizAPI request error", extra={"error": str(e), "category": category})

        return None
