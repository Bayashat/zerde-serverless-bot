"""Leaderboard and season finale state machine tests."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

_zerde = os.path.join(os.path.dirname(__file__), "..", "src", "shared", "python")
if _zerde not in sys.path:
    sys.path.insert(0, _zerde)

os.environ.setdefault("TABLE_NAME", "test-quiz-table")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("QUIZ_LLM_RPD", "1000")
os.environ.setdefault("BOT_TOKEN", "test-bot-token")

_quiz_dir = os.path.join(os.path.dirname(__file__), "..", "src", "quiz")
_saved_modules: dict[str, object] = {}

try:
    for mod_name in list(sys.modules):
        if mod_name in ("core", "services") or mod_name.startswith(("core.", "services.")):
            _saved_modules[mod_name] = sys.modules.pop(mod_name)

    sys.path.insert(0, _quiz_dir)
    import services.quiz_service as quiz_service_mod  # noqa: E402
    from services.quiz_service import QuizService  # noqa: E402
finally:
    if _quiz_dir in sys.path:
        sys.path.remove(_quiz_dir)
    for mod_name in list(sys.modules):
        if mod_name in ("core", "services") or mod_name.startswith(("core.", "services.")):
            sys.modules.pop(mod_name, None)
    sys.modules.update(_saved_modules)


def _service_with_mocks() -> tuple[QuizService, MagicMock, MagicMock, MagicMock]:
    service = QuizService.__new__(QuizService)
    service._repo = MagicMock()
    service._sender = MagicMock()
    service._generator = MagicMock()
    return service, service._repo, service._sender, service._generator


@patch.object(quiz_service_mod, "get_translated_text", side_effect=lambda key, *_a, **_k: key)
def test_pending_season_finale_retries_without_advancing_state(_mock_t: MagicMock) -> None:
    service, repo, sender, _gen = _service_with_mocks()
    repo.get_leaderboard.return_value = [{"SK": "USER#1", "first_name": "A", "week_score": 5}]
    repo.get_season_week_count.return_value = 4
    repo.get_season_leaderboard.return_value = [{"SK": "USER#1", "first_name": "A", "season_wins": 2}]
    sender.send_message.side_effect = [True, False]

    result = service.process_leaderboard(["chat1"], "en")

    assert result["sent"] == 1
    repo.increment_season_wins.assert_not_called()
    repo.increment_season_week_count.assert_not_called()
    repo.reset_season_wins.assert_not_called()
    repo.reset_season_week_count.assert_not_called()
    repo.reset_week_scores.assert_called_once_with("chat1")
    assert result["failed"] == [{"chat_id": "chat1", "step": "send_season_message"}]


@patch.object(quiz_service_mod, "get_translated_text", side_effect=lambda key, *_a, **_k: key)
def test_season_finale_failure_does_not_reset_season_state(_mock_t: MagicMock) -> None:
    service, repo, sender, _gen = _service_with_mocks()
    repo.get_leaderboard.return_value = [{"SK": "USER#2", "first_name": "B", "week_score": 3}]
    repo.get_season_week_count.return_value = 3
    repo.increment_season_week_count.return_value = 4
    repo.get_season_leaderboard.return_value = [{"SK": "USER#2", "first_name": "B", "season_wins": 4}]
    sender.send_message.side_effect = [True, False]

    result = service.process_leaderboard(["chat1"], "en")

    repo.increment_season_wins.assert_called_once()
    repo.increment_season_week_count.assert_called_once_with("chat1")
    repo.reset_season_wins.assert_not_called()
    repo.reset_season_week_count.assert_not_called()
    repo.reset_week_scores.assert_called_once_with("chat1")
    assert result["failed"] == [{"chat_id": "chat1", "step": "send_season_message"}]
