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
    from services.quiz_generator import CATEGORY_POOL, SUBTOPIC_POOL, QuizGenerator, question_fingerprint  # noqa: E402
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

    def test_correct_option_must_not_be_obviously_longest(self):
        gen = _make_generator()
        _mock_response(
            gen,
            _make_valid_data(
                question="Which cache setting reduces stale reads?",
                options=[
                    "A very detailed cache invalidation strategy with multiple explicit guarantees",
                    "Short TTL",
                    "Read replica",
                    "Hash index",
                ],
                correct_index=0,
            ),
        )

        result = gen.generate_question("system-design", "en", "medium")
        assert result is None

    def test_question_must_not_leak_correct_answer_terms(self):
        gen = _make_generator()
        _mock_response(
            gen,
            _make_valid_data(
                question="A team needs cache invalidation for stale reads. What should they configure?",
                options=["Cache invalidation", "Read replica", "Hash index", "Message queue"],
                correct_index=0,
            ),
        )

        result = gen.generate_question("system-design", "en", "medium")
        assert result is None

    def test_medium_prompt_requires_applied_scenario(self):
        gen = _make_generator()
        _mock_response(gen, _make_valid_data())

        result = gen.generate_question("cloud", "en", "medium")

        assert result is not None
        prompt = gen._provider.generate_json.call_args.args[0]
        assert "L3 applied scenario" in prompt
        assert "specific scenario" in prompt
        assert "Avoid generic textbook-definition questions" in prompt

    def test_interactive_generation_passes_fast_provider_mode(self):
        gen = _make_generator()
        _mock_response(gen, _make_valid_data())

        result = gen.generate_question("cloud", "en", "medium", interactive=True)

        assert result is not None
        assert gen._provider.generate_json.call_args.kwargs["interactive"] is True

    def test_subtopic_prompt_stays_on_topic_path(self):
        gen = _make_generator()
        _mock_response(gen, _make_valid_data(question="Why can Lambda cold starts happen?"))

        result = gen.generate_question("cloud", "en", "medium", "Lambda / cold start")

        assert result is not None
        assert result["subtopic"] == "Lambda / cold start"
        assert result["fingerprint"] == question_fingerprint("Why can Lambda cold starts happen?")
        prompt = gen._provider.generate_json.call_args.args[0]
        assert "cloud / Lambda / cold start" in prompt
        assert "Stay tightly within the requested topic path" in prompt


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
            "system-design",
        }
        assert set(CATEGORY_POOL) == expected

    def test_every_category_has_subtopics(self):
        assert set(SUBTOPIC_POOL) == set(CATEGORY_POOL)
        assert all(len(subtopics) >= 6 for subtopics in SUBTOPIC_POOL.values())
