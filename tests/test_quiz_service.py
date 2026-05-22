from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_zerde = os.path.join(_ROOT, "src", "shared", "python")
if _zerde not in sys.path:
    sys.path.insert(0, _zerde)

os.environ.setdefault("BOT_TOKEN", "test-bot-token")
os.environ.setdefault("TABLE_NAME", "test-quiz-table")
os.environ.setdefault("QUIZ_TABLE_NAME", "test-quiz-table")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("QUIZ_LLM_RPD", "1000")

_quiz_dir = os.path.join(_ROOT, "src", "quiz")
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


def _bank_item() -> dict:
    return {
        "question": "What does S3 stand for?",
        "options": ["Simple Storage Service", "Secure Server System", "Scalable SQL Service", "Static Site Storage"],
        "correct_option_id": 0,
        "explanation": "S3 = Simple Storage Service.",
    }


def _service() -> QuizService:
    service = QuizService.__new__(QuizService)
    service._repo = MagicMock()
    service._sender = MagicMock()
    service._generator = MagicMock()
    service.get_difficulty = MagicMock(return_value="easy")
    service.build_announcement = MagicMock(return_value="announcement")
    return service


def test_pick_banked_question_defers_queue_persistence_until_delivery() -> None:
    service = _service()
    service._repo.get_question_queue.return_value = ["aws-clf-c02::q1", "aws-clf-c02::q2"]
    service._repo.get_bank_question.return_value = _bank_item()

    question, remaining = service._pick_banked_question_for_chat("cloud", "-100", "easy")

    assert question is not None
    assert question["question"] == "What does S3 stand for?"
    assert remaining == ["aws-clf-c02::q2"]
    service._repo.save_question_queue.assert_not_called()


def test_daily_quiz_saves_banked_question_queue_after_poll_success() -> None:
    service = _service()
    pending_queue = ["aws-clf-c02::q2"]
    banked = {
        "question": "What does S3 stand for?",
        "options": ["Simple Storage Service", "Secure Server System", "Scalable SQL Service", "Static Site Storage"],
        "correct_option_index": 0,
        "explanation": "S3 = Simple Storage Service.",
        "difficulty": "easy",
        "points": 1,
        "source_label": "AWS CLF-C02 Practice Exam",
    }
    service._pick_category_for_chat = MagicMock(return_value=("cloud", []))
    service._pick_banked_question_for_chat = MagicMock(return_value=(banked, pending_queue))
    service._sender.send_message.return_value = True
    service._sender.send_quiz_poll.return_value = {"poll": {"id": "poll-1"}, "message_id": 10}

    result = service.process_daily_quiz(["-100"], "en")

    assert result["sent"] == 1
    service._repo.save_quiz_record.assert_called_once()
    service._repo.save_question_queue.assert_called_once_with("cloud", "-100", pending_queue)


def test_daily_quiz_keeps_banked_question_queue_when_poll_fails() -> None:
    service = _service()
    pending_queue = ["aws-clf-c02::q2"]
    banked = {
        "question": "What does S3 stand for?",
        "options": ["Simple Storage Service", "Secure Server System", "Scalable SQL Service", "Static Site Storage"],
        "correct_option_index": 0,
        "explanation": "S3 = Simple Storage Service.",
        "difficulty": "easy",
        "points": 1,
        "source_label": "AWS CLF-C02 Practice Exam",
    }
    service._pick_category_for_chat = MagicMock(return_value=("cloud", []))
    service._pick_banked_question_for_chat = MagicMock(return_value=(banked, pending_queue))
    service._sender.send_message.return_value = True
    service._sender.send_quiz_poll.return_value = None

    result = service.process_daily_quiz(["-100"], "en")

    assert result["sent"] == 0
    service._repo.save_quiz_record.assert_not_called()
    service._repo.save_question_queue.assert_not_called()
