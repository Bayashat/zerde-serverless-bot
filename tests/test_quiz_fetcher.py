"""Tests for QuizAPI.io fetcher and category rotation."""

import os
import sys

os.environ.setdefault("BOT_TOKEN", "test-bot-token")
os.environ.setdefault("QUIZAPI_KEY", "test-quiz-api-key")
os.environ.setdefault("QUIZ_TABLE_NAME", "test-quiz-table")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "quiz"))

from services.quiz_fetcher import CATEGORY_POOL, QuizFetcher, parse_question  # noqa: E402


class TestParseQuestion:
    """Test QuizAPI response parsing and filtering."""

    def test_valid_question_parsed(self):
        raw = {
            "question": "What does HTML stand for?",
            "answers": {
                "answer_a": "Hyper Text Markup Language",
                "answer_b": "High Tech Modern Language",
                "answer_c": "Home Tool Markup Language",
                "answer_d": "Hyper Transfer Markup Language",
            },
            "correct_answers": {
                "answer_a_correct": "true",
                "answer_b_correct": "false",
                "answer_c_correct": "false",
                "answer_d_correct": "false",
            },
            "explanation": "HTML is Hyper Text Markup Language.",
        }
        result = parse_question(raw)
        assert result is not None
        assert result["question"] == "What does HTML stand for?"
        assert len(result["options"]) == 4
        assert result["correct_option_id"] == 0
        assert result["explanation"] == "HTML is Hyper Text Markup Language."

    def test_missing_option_filtered_out(self):
        raw = {
            "question": "Incomplete question",
            "answers": {
                "answer_a": "Option A",
                "answer_b": None,
                "answer_c": "Option C",
                "answer_d": "Option D",
            },
            "correct_answers": {
                "answer_a_correct": "true",
                "answer_b_correct": "false",
                "answer_c_correct": "false",
                "answer_d_correct": "false",
            },
        }
        result = parse_question(raw)
        assert result is None

    def test_no_correct_answer_filtered_out(self):
        raw = {
            "question": "No correct answer",
            "answers": {
                "answer_a": "A",
                "answer_b": "B",
                "answer_c": "C",
                "answer_d": "D",
            },
            "correct_answers": {
                "answer_a_correct": "false",
                "answer_b_correct": "false",
                "answer_c_correct": "false",
                "answer_d_correct": "false",
            },
        }
        result = parse_question(raw)
        assert result is None

    def test_empty_question_text_filtered_out(self):
        raw = {
            "question": "",
            "answers": {
                "answer_a": "A",
                "answer_b": "B",
                "answer_c": "C",
                "answer_d": "D",
            },
            "correct_answers": {
                "answer_a_correct": "true",
                "answer_b_correct": "false",
                "answer_c_correct": "false",
                "answer_d_correct": "false",
            },
        }
        result = parse_question(raw)
        assert result is None


class TestCategoryRotation:
    """Test category selection avoids yesterday's category."""

    def test_excludes_last_category(self):
        fetcher = QuizFetcher.__new__(QuizFetcher)
        available = fetcher._get_available_categories("Linux")
        assert "Linux" not in available
        assert len(available) == len(CATEGORY_POOL) - 1

    def test_all_available_when_no_last_category(self):
        fetcher = QuizFetcher.__new__(QuizFetcher)
        available = fetcher._get_available_categories(None)
        assert len(available) == len(CATEGORY_POOL)

    def test_excludes_unknown_category_gracefully(self):
        fetcher = QuizFetcher.__new__(QuizFetcher)
        available = fetcher._get_available_categories("NonExistent")
        assert len(available) == len(CATEGORY_POOL)
