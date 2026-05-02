"""Tests for quiz service orchestration."""

import os
import sys
from unittest.mock import MagicMock

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


def test_process_on_demand_quiz_persists_poll_for_answer_lookup() -> None:
    service = QuizService.__new__(QuizService)
    service._generator = MagicMock()
    service._sender = MagicMock()
    service._repo = MagicMock()

    service._generator.generate_question.return_value = {
        "question": "What is S3?",
        "options": ["Storage", "Compute", "Network", "Database"],
        "correct_option_index": 0,
        "explanation": "S3 stores objects.",
        "difficulty": "easy",
        "points": 1,
    }
    service._generator.get_rpd_status.return_value = (99, 100)
    service._sender.send_quiz_poll.return_value = {
        "message_id": 123,
        "poll": {"id": "poll-123"},
    }

    result = service.process_on_demand_quiz("chat-1", "en", "cloud", "easy")

    assert result["status"] == "ok"
    service._repo.save_on_demand_quiz_record.assert_called_once_with(
        chat_id="chat-1",
        question="What is S3?",
        options=["Storage", "Compute", "Network", "Database"],
        correct_option_id=0,
        explanation="S3 stores objects.",
        category="cloud",
        lang="en",
        poll_id="poll-123",
        message_id=123,
        difficulty="easy",
        points=1,
    )
