"""Gemini-based translator for quiz questions (English → Kazakh)."""

import json
from typing import Any

from core.config import GEMINI_API_KEY, LLM_MODEL
from core.logger import LoggerAdapter, get_logger
from google import genai
from google.genai import types

_OPTION_MAX_LEN = 100
_QUESTION_MAX_LEN = 300

logger = LoggerAdapter(get_logger(__name__), {})


class QuizTranslator:
    """Translates quiz question text, options, and explanation to Kazakh via Gemini."""

    def __init__(self) -> None:
        self._client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("QuizTranslator initialized", extra={"model": LLM_MODEL})

    def translate_question(self, question: dict[str, Any]) -> dict[str, Any]:
        """Translate a parsed question dict from English to Kazakh.

        Returns a new dict with translated text fields. On failure, returns the
        original question unchanged (graceful degradation).
        """
        option_texts = [opt["text"] for opt in question["options"]]
        payload = {
            "question": question["question"],
            "options": option_texts,
            "explanation": question.get("explanation") or "",
        }

        prompt = (
            "You are a professional English → Kazakh translator specializing in IT and programming.\n"
            "Translate the following IT quiz question, answer options, and explanation from English "
            "into Kazakh (Cyrillic script).\n\n"
            "RULES:\n"
            "1. Keep well-known technical terms in English where natural "
            "(e.g. Python, JavaScript, Docker, API, SQL, HTML, CSS, Git, AWS, Linux, CI/CD).\n"
            "2. Translate the question stem, all option texts, and the explanation fully into Kazakh.\n"
            "3. Preserve the EXACT order and count of options.\n"
            "4. If an option is a single code keyword or symbol (e.g. `null`, `object`, `true`), "
            "keep it as-is without translation.\n"
            "5. CRITICAL LENGTH CONSTRAINT: Each option MUST be at most 100 characters. "
            "This is a hard Telegram API limit. If a translated option would exceed 100 characters, "
            "shorten it aggressively — abbreviate, drop filler words, or paraphrase more concisely. "
            "NEVER return an option longer than 100 characters.\n"
            "6. The question text must be at most 300 characters (Telegram limit).\n\n"
            "Respond ONLY with a JSON object in this exact format:\n"
            '{"question": "...", "options": ["opt1", "opt2", ...], "explanation": "..."}\n\n'
            f"DATA:\n{json.dumps(payload, ensure_ascii=False)}"
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

            translated_q = (data.get("question") or "").strip()
            translated_opts = data.get("options", [])
            translated_expl = (data.get("explanation") or "").strip() or None

            if not translated_q or len(translated_opts) != len(question["options"]):
                logger.warning(
                    "Translation response invalid, falling back to English",
                    extra={
                        "got_options": len(translated_opts),
                        "expected_options": len(question["options"]),
                    },
                )
                return question

            for i, text in enumerate(translated_opts):
                if len(text) > _OPTION_MAX_LEN:
                    logger.warning(
                        "Truncating option exceeding Telegram limit",
                        extra={"index": i, "length": len(text), "text": text[:120]},
                    )
                    translated_opts[i] = text[: _OPTION_MAX_LEN - 1] + "…"

            if len(translated_q) > _QUESTION_MAX_LEN:
                logger.warning("Truncating question exceeding Telegram limit", extra={"length": len(translated_q)})
                translated_q = translated_q[: _QUESTION_MAX_LEN - 1] + "…"

            translated_option_dicts = [
                {"text": text, "id": opt["id"]} for text, opt in zip(translated_opts, question["options"])
            ]

            result = {
                "question": translated_q,
                "options": translated_option_dicts,
                "correct_option_ids": question["correct_option_ids"],
                "explanation": translated_expl,
            }
            logger.info("Question translated to Kazakh", extra={"question": translated_q[:60]})
            return result

        except Exception:
            logger.error("Translation failed, falling back to English", exc_info=True)
            return question
