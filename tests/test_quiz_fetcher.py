"""Tests for QuizAPI.io fetcher and category rotation.

The quiz_fetcher module lives in src/quiz/ which has its own core.config
and core.logger packages. Since conftest.py adds src/bot to sys.path
(which also has core.*), we must temporarily override sys.path ordering
to load the quiz module cleanly.
"""

import os
import sys

# Env vars needed by src/quiz/core/config.py
os.environ.setdefault("BOT_TOKEN", "test-bot-token")
os.environ.setdefault("QUIZAPI_KEY", "test-quiz-api-key")
os.environ.setdefault("QUIZ_TABLE_NAME", "test-quiz-table")

# Save and temporarily replace conflicting core.* modules so that
# src/quiz/core is resolved instead of src/bot/core.
_quiz_dir = os.path.join(os.path.dirname(__file__), "..", "src", "quiz")

_saved_modules = {}
for mod_name in list(sys.modules):
    if mod_name in ("core", "services") or mod_name.startswith(("core.", "services.")):
        _saved_modules[mod_name] = sys.modules.pop(mod_name)

sys.path.insert(0, _quiz_dir)

from services.quiz_fetcher import (  # noqa: E402
    CATEGORY_POOL,
    QuizFetcher,
    parse_question,
)

# Restore original modules so bot tests still work
sys.path.remove(_quiz_dir)
for mod_name in list(sys.modules):
    if mod_name in ("core", "services") or mod_name.startswith(("core.", "services.")):
        del sys.modules[mod_name]
sys.modules.update(_saved_modules)


def _make_raw(
    text: str = "What does HTML stand for?",
    answers: list | None = None,
    explanation: str | None = "HTML is Hyper Text Markup Language.",
) -> dict:
    """Build a QuizAPI-style raw question dict for tests."""
    if answers is None:
        answers = [
            {"id": "ans_1", "text": "Hyper Text Markup Language", "isCorrect": True},
            {"id": "ans_2", "text": "High Tech Modern Language", "isCorrect": False},
            {"id": "ans_3", "text": "Home Tool Markup Language", "isCorrect": False},
            {"id": "ans_4", "text": "Hyper Transfer Markup Language", "isCorrect": False},
        ]
    raw: dict = {"text": text, "answers": answers}
    if explanation is not None:
        raw["explanation"] = explanation
    return raw


class TestParseQuestion:
    """Test QuizAPI response parsing and filtering."""

    def test_valid_question_parsed(self):
        result = parse_question(_make_raw())
        assert result is not None
        assert result["question"] == "What does HTML stand for?"
        assert len(result["options"]) == 4
        assert result["correct_option_ids"] == [0]
        assert result["explanation"] == "HTML is Hyper Text Markup Language."

    def test_missing_option_filtered_out(self):
        answers = [
            {"id": "ans_1", "text": "Option A", "isCorrect": True},
            {"id": "ans_2", "text": None, "isCorrect": False},
            {"id": "ans_3", "text": "Option C", "isCorrect": False},
            {"id": "ans_4", "text": "Option D", "isCorrect": False},
        ]
        result = parse_question(_make_raw(answers=answers))
        assert result is None

    def test_no_correct_answer_filtered_out(self):
        answers = [
            {"id": "ans_1", "text": "A", "isCorrect": False},
            {"id": "ans_2", "text": "B", "isCorrect": False},
            {"id": "ans_3", "text": "C", "isCorrect": False},
            {"id": "ans_4", "text": "D", "isCorrect": False},
        ]
        result = parse_question(_make_raw(answers=answers))
        assert result is None

    def test_empty_question_text_filtered_out(self):
        result = parse_question(_make_raw(text=""))
        assert result is None


class TestCategoryQueue:
    """Test deck-of-cards category queue rotation."""

    def test_empty_queue_generates_full_shuffled_deck(self):
        fetcher = QuizFetcher.__new__(QuizFetcher)
        fetcher._try_category = lambda cat: {
            "question": "Q",
            "options": [],
            "correct_option_ids": [0],
            "explanation": None,
        }

        result = fetcher.fetch_question([])
        assert result is not None
        _, category, remaining = result
        assert category in CATEGORY_POOL
        assert len(remaining) == len(CATEGORY_POOL) - 1
        assert category not in remaining

    def test_pops_first_from_queue(self):
        fetcher = QuizFetcher.__new__(QuizFetcher)
        fetcher._try_category = lambda cat: {
            "question": "Q",
            "options": [],
            "correct_option_ids": [0],
            "explanation": None,
        }

        queue = ["cicd", "cloud", "devops"]
        result = fetcher.fetch_question(queue)
        assert result is not None
        _, category, remaining = result
        assert category == "cicd"
        assert remaining == ["cloud", "devops"]

    def test_skips_failed_category_tries_next(self):
        fetcher = QuizFetcher.__new__(QuizFetcher)
        fetcher._try_category = lambda cat: (
            {"question": "Q", "options": [], "correct_option_ids": [0], "explanation": None} if cat == "cloud" else None
        )

        queue = ["cicd", "cloud", "devops"]
        result = fetcher.fetch_question(queue)
        assert result is not None
        _, category, remaining = result
        assert category == "cloud"
        assert remaining == ["devops"]

    def test_all_categories_fail_returns_none(self):
        fetcher = QuizFetcher.__new__(QuizFetcher)
        fetcher._try_category = lambda cat: None

        result = fetcher.fetch_question(["cicd", "cloud"])
        assert result is None
