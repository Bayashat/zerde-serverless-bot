# src/quiz/services/quiz_generator.py
"""IT quiz question generator with provider-agnostic LLM backend."""

from core.logger import LoggerAdapter, get_logger
from services.llm_provider import QuizLLMProvider

logger = LoggerAdapter(get_logger(__name__), {})

_OPTION_MAX_LEN = 100
_QUESTION_MAX_LEN = 300

DIFFICULTY_POINTS: dict[str, int] = {
    "easy": 1,
    "easy_medium": 2,
    "medium": 3,
    "medium_hard": 4,
    "hard": 5,
    "expert": 5,
}

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
    "networking",
]

_LANG_NAMES = {
    "kk": "Kazakh (Cyrillic script)",
    "zh": "Simplified Chinese",
    "ru": "Russian",
}


class QuizGenerator:
    """Generates IT quiz questions via an injected LLM provider."""

    def __init__(self, provider: QuizLLMProvider) -> None:
        self._provider = provider
        logger.info("QuizGenerator initialized")

    def get_rpd_status(self) -> tuple[int | None, int | None]:
        """Return provider RPD status when available."""
        return self._provider.get_rpd_status()

    def generate_question(self, category: str, lang: str, difficulty: str = "easy") -> dict | None:
        """Generate a quiz question for the given category, language, and difficulty.

        Returns a dict with keys: question, options, correct_option_index, explanation,
        difficulty, points.
        Returns None if generation or validation fails.
        """
        lang_name = _LANG_NAMES.get(lang, lang)
        difficulty_label = difficulty.capitalize()
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
            f"6. Difficulty: {difficulty_label}. "
            "easy=basic recall, medium=applied knowledge, hard=advanced/edge cases, "
            "expert=deep internals/tricky.\n\n"
            "Respond ONLY with a JSON object in this exact format:\n"
            '{"question": "...", "options": ["opt1", "opt2", "opt3", "opt4"], '
            '"correct_option_index": 0, "explanation": "..."}\n\n'
            "correct_option_index must be the 0-based index of the correct option in the options array."
        )

        try:
            data = self._provider.generate_json(prompt, temperature=0.3)
            return self._validate(data, category, lang, difficulty)

        except Exception:
            logger.error(
                "Question generation failed",
                extra={"category": category, "lang": lang, "difficulty": difficulty},
                exc_info=True,
            )
            return None

    def translate_question(self, question: dict, lang: str) -> dict | None:
        """Translate a banked (English) question dict into *lang*.

        Translates: question text, all 4 options, explanation.
        Non-text fields (correct_option_index, difficulty, points, source_label) are
        copied unchanged.

        Returns the translated dict on success, or None if translation/validation fails
        (caller should fall back to the original English question).
        """
        if lang == "en":
            return question

        lang_name = _LANG_NAMES.get(lang, lang)
        prompt = (
            f"Translate the following IT quiz question into {lang_name}.\n"
            "Rules:\n"
            "1. Keep well-known technical terms in English "
            "(e.g. AWS, S3, EC2, IAM, VPC, Docker, Kubernetes, Python, SQL, API, CLI).\n"
            "2. CRITICAL LENGTH LIMITS (hard Telegram API limits):\n"
            "   - question: at most 300 characters.\n"
            "   - Each option: at most 100 characters. Abbreviate aggressively if needed.\n"
            "   - explanation: at most 200 characters.\n"
            "3. Preserve the original meaning exactly — do NOT change the correct answer.\n"
            "4. Respond ONLY with a JSON object in this exact format:\n"
            '   {"question": "...", "options": ["opt1","opt2","opt3","opt4"], "explanation": "..."}\n\n'
            "Source question (English):\n"
            f"question: {question['question']}\n"
            f"options: {question['options']}\n"
            f"explanation: {question.get('explanation') or ''}"
        )

        try:
            data = self._provider.generate_json(prompt, temperature=0.1)
            if not isinstance(data, dict):
                logger.warning(
                    "Translation provider returned non-dict",
                    extra={"lang": lang, "type": type(data).__name__},
                )
                return None
            return self._validate_translation(data, question, lang)
        except Exception:
            logger.error(
                "Question translation failed",
                extra={"lang": lang},
                exc_info=True,
            )
            return None

    def _validate_translation(self, data: dict, original: dict, lang: str) -> dict | None:
        """Validate translated content and merge with non-text original fields."""
        q_text = (data.get("question") or "").strip()
        options = data.get("options", [])
        explanation = (data.get("explanation") or "").strip() or None

        if not q_text or len(q_text) > _QUESTION_MAX_LEN:
            logger.warning(
                "Translated question empty or too long",
                extra={"lang": lang, "length": len(q_text)},
            )
            return None

        if not isinstance(options, list) or len(options) != 4:
            logger.warning("Translated options count invalid", extra={"lang": lang})
            return None

        for i, opt in enumerate(options):
            if not isinstance(opt, str) or not opt.strip():
                logger.warning("Translated option empty", extra={"lang": lang, "index": i})
                return None
            if len(opt.strip()) > _OPTION_MAX_LEN:
                logger.warning(
                    "Translated option too long",
                    extra={"lang": lang, "index": i, "length": len(opt.strip())},
                )
                return None

        return {
            **original,
            "question": q_text,
            "options": [opt.strip() for opt in options],
            "explanation": explanation,
        }

    def _validate(self, data: dict, category: str, lang: str, difficulty: str = "easy") -> dict | None:
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
            "difficulty": difficulty,
            "points": DIFFICULTY_POINTS.get(difficulty, 1),
        }
