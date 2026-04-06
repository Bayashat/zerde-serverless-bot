# src/quiz/services/quiz_generator.py
"""Gemini-based IT quiz question generator with multi-language support."""

import json

from core.config import GEMINI_API_KEY, LLM_MODEL
from core.logger import LoggerAdapter, get_logger
from google import genai
from google.genai import types

logger = LoggerAdapter(get_logger(__name__), {})

_OPTION_MAX_LEN = 100
_QUESTION_MAX_LEN = 300

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

_LANG_NAMES = {
    "kk": "Kazakh (Cyrillic script)",
    "zh": "Simplified Chinese",
    "ru": "Russian",
}


class QuizGenerator:
    """Generates IT quiz questions directly in the target language via Gemini."""

    def __init__(self) -> None:
        self._client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("QuizGenerator initialized", extra={"model": LLM_MODEL})

    def generate_question(self, category: str, lang: str) -> dict | None:
        """Generate a quiz question for the given category in the target language.

        Returns a dict with keys: question, options, correct_option_index, explanation.
        Returns None if generation or validation fails.
        """
        lang_name = _LANG_NAMES.get(lang, lang)
        prompt = (
            f"You are an IT quiz question writer for a developer community.\n"
            f"Generate exactly 1 multiple-choice IT quiz question about the topic: {category}.\n\n"
            "LANGUAGE RULES:\n"
            f"1. Write the question text, all 4 answer options, and the explanation entirely in {lang_name}.\n"
            "2. Keep well-known technical terms in English where natural "
            "(e.g. Python, Docker, AWS, SQL, HTML, CSS, Git, Linux, CI/CD, API).\n"
            "3. CRITICAL LENGTH CONSTRAINTS (hard Telegram API limits):\n"
            "   - Question text: at most 300 characters.\n"
            "   - Each option: at most 100 characters. Abbreviate aggressively if needed.\n"
            "   - Explanation: at most 200 characters.\n\n"
            "CONTENT RULES:\n"
            "4. Provide exactly 4 answer options.\n"
            "5. Exactly 1 option must be correct.\n"
            "6. Difficulty: Easy.\n\n"
            "Respond ONLY with a JSON object in this exact format:\n"
            '{"question": "...", "options": ["opt1", "opt2", "opt3", "opt4"], '
            '"correct_option_index": 0, "explanation": "..."}\n\n'
            "correct_option_index must be the 0-based index of the correct option in the options array."
        )

        try:
            response = self._client.models.generate_content(
                model=LLM_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    response_mime_type="application/json",
                ),
            )
            data = json.loads(response.text)
            return self._validate(data, category, lang)

        except Exception:
            logger.error(
                "Question generation failed",
                extra={"category": category, "lang": lang},
                exc_info=True,
            )
            return None

    def _validate(self, data: dict, category: str, lang: str) -> dict | None:
        """Validate Gemini response shape and Telegram length limits."""
        question = (data.get("question") or "").strip()
        options = data.get("options", [])
        correct_index = data.get("correct_option_index")
        explanation = (data.get("explanation") or "").strip() or None

        if not question:
            logger.warning("Generated question is empty", extra={"category": category, "lang": lang})
            return None

        if len(question) > _QUESTION_MAX_LEN:
            logger.warning(
                "Generated question exceeds Telegram limit",
                extra={"length": len(question), "category": category, "lang": lang},
            )
            return None

        if not isinstance(options, list) or len(options) != 4:
            logger.warning(
                "Generated options count invalid",
                extra={"got": len(options) if isinstance(options, list) else "n/a", "category": category},
            )
            return None

        for i, opt in enumerate(options):
            if not isinstance(opt, str) or not opt.strip():
                logger.warning("Option is empty or non-string", extra={"index": i, "category": category})
                return None
            if len(opt.strip()) > _OPTION_MAX_LEN:
                logger.warning(
                    "Option exceeds Telegram limit",
                    extra={"index": i, "length": len(opt.strip()), "category": category},
                )
                return None

        if not isinstance(correct_index, int) or isinstance(correct_index, bool) or not (0 <= correct_index <= 3):
            logger.warning(
                "correct_option_index invalid",
                extra={"value": correct_index, "category": category},
            )
            return None

        return {
            "question": question,
            "options": [opt.strip() for opt in options],
            "correct_option_index": correct_index,
            "explanation": explanation,
        }
