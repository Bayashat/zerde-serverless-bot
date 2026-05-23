"""Tests for weekly leaderboard / season week counter orchestration."""

import os
import sys
from unittest.mock import MagicMock, patch

_zerde = os.path.join(os.path.dirname(__file__), "..", "src", "shared", "python")
if _zerde not in sys.path:
    sys.path.insert(0, _zerde)

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
    for mod_name, mod in _saved_modules.items():
        sys.modules[mod_name] = mod


@patch("services.quiz_service.QuizRepository")
@patch("services.quiz_service.QuizSender")
@patch("services.quiz_service.QuizGenerator")
def test_leaderboard_skips_score_reset_when_season_increment_fails(
    _mock_gen: MagicMock,
    mock_sender_cls: MagicMock,
    mock_repo_cls: MagicMock,
) -> None:
    repo = MagicMock()
    mock_repo_cls.return_value = repo
    sender = MagicMock()
    mock_sender_cls.return_value = sender
    sender.send_message.return_value = {"message_id": 1}

    repo.get_leaderboard.return_value = [
        {"SK": "USER#42", "first_name": "Ada", "week_score": 5},
    ]
    repo.increment_season_week_count.return_value = 0

    service = QuizService()
    result = service.process_leaderboard(["-1001"], "en")

    repo.increment_season_wins.assert_not_called()
    repo.reset_week_scores.assert_not_called()
    assert result["sent"] == 1
    assert result["failed"] == [{"chat_id": "-1001", "step": "increment_season_week"}]
