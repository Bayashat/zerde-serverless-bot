"""Tests for Gemini-based quiz question generator."""

import os
import sys
from unittest.mock import MagicMock

_zerde = os.path.join(os.path.dirname(__file__), "..", "src", "shared", "python")
if _zerde not in sys.path:
    sys.path.insert(0, _zerde)

os.environ.setdefault("BOT_TOKEN", "test-bot-token")
os.environ.setdefault("TABLE_NAME", "test-quiz-table")
os.environ.setdefault("QUIZ_TABLE_NAME", "test-quiz-table")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("QUIZ_LLM_RPD", "1000")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-deepseek-key")

_quiz_dir = os.path.join(os.path.dirname(__file__), "..", "src", "quiz")
_saved_modules: dict[str, object] = {}

try:
    for mod_name in list(sys.modules):
        if mod_name in ("core", "services") or mod_name.startswith(("core.", "services.")):
            _saved_modules[mod_name] = sys.modules.pop(mod_name)

    sys.path.insert(0, _quiz_dir)
    from services.quiz_generator import CATEGORY_POOL, QuizGenerator  # noqa: E402
finally:
    if _quiz_dir in sys.path:
        sys.path.remove(_quiz_dir)
    for mod_name in list(sys.modules):
        if mod_name in ("core", "services") or mod_name.startswith(("core.", "services.")):
            sys.modules.pop(mod_name, None)
    sys.modules.update(_saved_modules)


def _make_valid_data(
    question: str = "What is Docker?",
    options: list | None = None,
    correct_index: int = 0,
    explanation: str = "Docker is a container platform.",
) -> dict:
    if options is None:
        options = ["A container platform", "A virtual machine", "A database", "A cloud provider"]
    return {
        "question": question,
        "options": options,
        "correct_option_index": correct_index,
        "explanation": explanation,
    }


def _make_generator() -> QuizGenerator:
    gen = QuizGenerator.__new__(QuizGenerator)
    gen._provider = MagicMock()
    return gen


def _mock_response(gen: QuizGenerator, data: dict) -> None:
    gen._provider.generate_json.return_value = data


class TestQuizGeneratorValidation:
    # def test_valid_response_returns_dict(self):
    #     gen = _make_generator()
    #     _mock_response(gen, _make_valid_data())

    #     result = gen.generate_question("programming", "kk")

    #     assert result is not None
    #     assert result["question"] == "What is Docker?"
    #     assert result["options"] == ["A container platform", "A virtual machine", "A database", "A cloud provider"]
    #     assert result["correct_option_index"] == 0
    #     assert result["explanation"] == "Docker is a container platform."

    def test_option_over_100_chars_returns_none(self):
        gen = _make_generator()
        _mock_response(gen, _make_valid_data(options=["A" * 101, "B", "C", "D"]))

        result = gen.generate_question("cloud", "ru")
        assert result is None

    def test_question_over_300_chars_returns_none(self):
        gen = _make_generator()
        _mock_response(gen, _make_valid_data(question="Q" * 301))

        result = gen.generate_question("devops", "zh")
        assert result is None

    def test_invalid_json_returns_none(self):
        gen = _make_generator()
        gen._provider.generate_json.return_value = "this is not json"

        result = gen.generate_question("database", "kk")
        assert result is None

    def test_missing_options_field_returns_none(self):
        gen = _make_generator()
        _mock_response(gen, {"question": "Q?", "correct_option_index": 0, "explanation": "E."})

        result = gen.generate_question("ai", "kk")
        assert result is None

    def test_wrong_option_count_returns_none(self):
        gen = _make_generator()
        _mock_response(gen, _make_valid_data(options=["A", "B", "C"]))  # only 3

        result = gen.generate_question("programming", "kk")
        assert result is None

    def test_correct_index_out_of_range_returns_none(self):
        gen = _make_generator()
        _mock_response(gen, _make_valid_data(correct_index=4))

        result = gen.generate_question("containers", "ru")
        assert result is None

    def test_correct_index_negative_returns_none(self):
        gen = _make_generator()
        _mock_response(gen, _make_valid_data(correct_index=-1))

        result = gen.generate_question("cicd", "kk")
        assert result is None

    def test_correct_index_boolean_returns_none(self):
        gen = _make_generator()
        data = _make_valid_data()
        data["correct_option_index"] = True  # bool, not int — must be rejected
        _mock_response(gen, data)

        result = gen.generate_question("programming", "kk")
        assert result is None

    def test_gemini_exception_returns_none(self):
        gen = _make_generator()
        gen._provider.generate_json.side_effect = Exception("API error")

        result = gen.generate_question("devops", "zh")
        assert result is None

    def test_empty_question_returns_none(self):
        gen = _make_generator()
        _mock_response(gen, _make_valid_data(question=""))

        result = gen.generate_question("programming", "kk")
        assert result is None

    def test_empty_option_returns_none(self):
        gen = _make_generator()
        _mock_response(gen, _make_valid_data(options=["A", "", "C", "D"]))

        result = gen.generate_question("cloud", "kk")
        assert result is None


_BANKED_QUESTION = {
    "question": "What does S3 stand for?",
    "options": ["Simple Storage Service", "Secure Server System", "Scalable SQL Service", "Static Site Storage"],
    "correct_option_index": 0,
    "explanation": "S3 = Simple Storage Service.",
    "difficulty": "easy",
    "points": 1,
    "source_label": "AWS CLF-C02 Practice Exam",
}


class TestTranslateQuestion:
    def test_en_lang_returns_original_unchanged(self):
        gen = _make_generator()
        result = gen.translate_question(_BANKED_QUESTION, "en")
        assert result is _BANKED_QUESTION

    def test_successful_translation_merges_non_text_fields(self):
        gen = _make_generator()
        gen._provider.generate_json.return_value = {
            "question": "S3 нені білдіреді?",
            "options": ["Қарапайым сақтау қызметі", "Қауіпсіз сервер", "SQL қызметі", "Статикалық сайт"],
            "explanation": "S3 = Қарапайым Сақтау Қызметі.",
        }

        result = gen.translate_question(_BANKED_QUESTION, "kk")

        assert result is not None
        assert result["question"] == "S3 нені білдіреді?"
        assert len(result["options"]) == 4
        # Non-text fields preserved from original
        assert result["correct_option_index"] == 0
        assert result["difficulty"] == "easy"
        assert result["points"] == 1
        assert result["source_label"] == "AWS CLF-C02 Practice Exam"

    def test_non_dict_provider_response_returns_none(self):
        gen = _make_generator()
        gen._provider.generate_json.return_value = "not a dict"

        result = gen.translate_question(_BANKED_QUESTION, "ru")
        assert result is None

    def test_provider_exception_returns_none(self):
        gen = _make_generator()
        gen._provider.generate_json.side_effect = Exception("provider down")

        result = gen.translate_question(_BANKED_QUESTION, "kk")
        assert result is None

    def test_translated_question_too_long_returns_none(self):
        gen = _make_generator()
        gen._provider.generate_json.return_value = {
            "question": "Q" * 301,
            "options": ["A", "B", "C", "D"],
            "explanation": "E.",
        }

        result = gen.translate_question(_BANKED_QUESTION, "kk")
        assert result is None

    def test_translated_option_too_long_returns_none(self):
        gen = _make_generator()
        gen._provider.generate_json.return_value = {
            "question": "Valid?",
            "options": ["A" * 101, "B", "C", "D"],
            "explanation": "E.",
        }

        result = gen.translate_question(_BANKED_QUESTION, "zh")
        assert result is None

    def test_wrong_option_count_returns_none(self):
        gen = _make_generator()
        gen._provider.generate_json.return_value = {
            "question": "Valid?",
            "options": ["A", "B", "C"],  # only 3
            "explanation": "E.",
        }

        result = gen.translate_question(_BANKED_QUESTION, "ru")
        assert result is None

    def test_empty_option_returns_none(self):
        gen = _make_generator()
        gen._provider.generate_json.return_value = {
            "question": "Valid?",
            "options": ["A", "", "C", "D"],
            "explanation": "E.",
        }

        result = gen.translate_question(_BANKED_QUESTION, "kk")
        assert result is None


class TestCategoryPool:
    def test_category_pool_has_expected_entries(self):
        expected = {
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
        }
        assert set(CATEGORY_POOL) == expected
