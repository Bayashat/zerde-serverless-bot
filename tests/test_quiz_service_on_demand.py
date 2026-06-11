"""Tests for QuizService on-demand poll persistence."""

import os
import sys
from unittest.mock import MagicMock

_zerde = os.path.join(os.path.dirname(__file__), "..", "src", "shared", "python")
if _zerde not in sys.path:
    sys.path.insert(0, _zerde)

os.environ.setdefault("BOT_TOKEN", "test-bot-token")
os.environ.setdefault("TABLE_NAME", "test-quiz-table")
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
    from services.quiz_service import QuizService  # noqa: E402
finally:
    if _quiz_dir in sys.path:
        sys.path.remove(_quiz_dir)
    for mod_name in list(sys.modules):
        if mod_name in ("core", "services") or mod_name.startswith(("core.", "services.")):
            sys.modules.pop(mod_name, None)
    sys.modules.update(_saved_modules)


def _make_service() -> QuizService:
    svc = QuizService.__new__(QuizService)
    svc._generator = MagicMock()
    svc._sender = MagicMock()
    svc._repo = MagicMock()
    svc._repo.save_quiz_record.return_value = True
    return svc


def _question(points: int = 3) -> dict:
    return {
        "question": "What is Python?",
        "options": ["Language", "Database", "Cloud", "Protocol"],
        "correct_option_index": 0,
        "explanation": "Python is a language.",
        "difficulty": "medium",
        "points": points,
    }


def test_ai_on_demand_quiz_saves_poll_lookup_record() -> None:
    svc = _make_service()
    question = _question(points=3)
    svc._generator.generate_question.return_value = question
    svc._sender.send_quiz_poll.return_value = {"poll": {"id": "poll-ai"}, "message_id": 321}

    result = svc.process_on_demand_quiz("-100123", "kk", "python", "medium")

    assert result == {"status": "ok", "sent": 1, "total": 1}
    svc._repo.save_quiz_record.assert_called_once_with(
        chat_id="-100123",
        question="What is Python?",
        options=question["options"],
        correct_option_id=0,
        explanation="Python is a language.",
        category="python",
        lang="kk",
        poll_id="poll-ai",
        message_id=321,
        difficulty="medium",
        points=3,
        subtopic=None,
        fingerprint=None,
        record_key="ONDEMAND#poll-ai",
    )


def test_on_demand_quiz_uses_interactive_ai_generation() -> None:
    svc = _make_service()
    question = _question(points=3)
    svc._generator.generate_question.return_value = question
    svc._sender.send_quiz_poll.return_value = {"poll": {"id": "poll-ai"}, "message_id": 321}

    result = svc.process_on_demand_quiz("-100123", "kk", "python", "medium", interactive=True)

    assert result["status"] == "ok"
    svc._generator.generate_question.assert_called_once_with("python", "kk", "medium", interactive=True)


def test_on_demand_quiz_with_feedback_replies_on_generation_failure() -> None:
    svc = _make_service()
    svc._generator.generate_question.return_value = None
    svc._sender.send_message.return_value = {"message_id": 777}

    result = svc.process_on_demand_quiz_with_feedback(
        "-100123",
        "en",
        "python",
        "medium",
        reply_to_message_id=42,
    )

    assert result == {"status": "error", "reason": "no valid question"}
    svc._sender.send_message.assert_called_once()
    assert svc._sender.send_message.call_args.args[0] == "-100123"
    assert "Failed to generate quiz" in svc._sender.send_message.call_args.args[1]
    assert svc._sender.send_message.call_args.kwargs["reply_to_message_id"] == 42


def test_banked_on_demand_quiz_saves_lookup_before_committing_queue() -> None:
    svc = _make_service()
    banked = {
        **_question(points=1),
        "source_label": "AWS CLF-C02 Practice Exam",
    }
    svc._pick_banked_question_for_genquiz = MagicMock(return_value=(banked, ["aws-clf-c02::next"]))
    svc._sender.send_quiz_poll.return_value = {"poll": {"id": "poll-bank"}, "message_id": 654}

    result = svc.process_on_demand_quiz("-100123", "en", "aws", "easy")

    assert result == {"status": "ok", "sent": 1, "total": 1}
    svc._repo.save_quiz_record.assert_called_once()
    save_call_index = [c[0] for c in svc._repo.method_calls].index("save_quiz_record")
    queue_call_index = [c[0] for c in svc._repo.method_calls].index("save_genquiz_question_queue")
    assert save_call_index < queue_call_index

    kwargs = svc._repo.save_quiz_record.call_args.kwargs
    assert kwargs["chat_id"] == "-100123"
    assert kwargs["poll_id"] == "poll-bank"
    assert kwargs["record_key"] == "ONDEMAND#poll-bank"
    assert kwargs["category"] == "cloud"
    assert "AWS CLF-C02 Practice Exam" in kwargs["question"]


def test_banked_on_demand_quiz_does_not_commit_queue_when_lookup_save_fails() -> None:
    svc = _make_service()
    svc._repo.save_quiz_record.return_value = False
    svc._pick_banked_question_for_genquiz = MagicMock(return_value=(_question(points=1), ["next"]))
    svc._sender.send_quiz_poll.return_value = {"poll": {"id": "poll-bank"}, "message_id": 654}

    result = svc.process_on_demand_quiz("-100123", "en", "aws", "easy")

    assert result == {"status": "error", "reason": "failed to save poll record"}
    svc._repo.save_genquiz_question_queue.assert_not_called()
