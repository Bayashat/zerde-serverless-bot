"""Tests for QuizService on-demand poll persistence."""

import os
import sys
from unittest.mock import MagicMock

from tests import quiz_support

quiz_env = quiz_support.quiz_env

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


def test_leaderboard_groups_tied_scores_on_one_line() -> None:
    svc = _make_service()

    text = svc.build_leaderboard_text(
        "en",
        [
            {"SK": "USER#1", "first_name": "Bayashat", "week_score": 15},
            {"SK": "USER#2", "first_name": "Lio", "week_score": 15},
            {"SK": "USER#3", "first_name": "Adilet", "week_score": 13},
            {"SK": "USER#4", "first_name": "Yesbol", "week_score": 12},
            {"SK": "USER#5", "first_name": "Alikhan", "week_score": 12},
        ],
    )

    assert '<a href="tg://user?id=1">Bayashat</a>, <a href="tg://user?id=2">Lio</a> — <b>15</b>' in text
    assert '🥈 <a href="tg://user?id=3">Adilet</a> — <b>13</b>' in text
    assert '<a href="tg://user?id=4">Yesbol</a>, <a href="tg://user?id=5">Alikhan</a> — <b>12</b>' in text


def test_leaderboard_escapes_user_names() -> None:
    svc = _make_service()

    text = svc.build_leaderboard_text("en", [{"SK": "USER#1", "first_name": "A&B", "week_score": 1}])

    assert '<a href="tg://user?id=1">A&amp;B</a> — <b>1</b>' in text


def test_ai_on_demand_quiz_has_primary_lookup_and_stable_retry(quiz_env):
    env = quiz_env
    assert env.svc.process_on_demand_quiz("-100123", "en", "python", "medium", request_id=42)["status"] == "ok"
    assert env.bot.lookup_poll("poll-0")["record_key"] == "REQUEST#42"
    assert env.svc.process_on_demand_quiz("-100123", "kk", "python", "medium", request_id=42)["status"] == "ok"
    assert len(env.sent) == 1


def test_missing_stable_command_id_rejects_before_generation(quiz_env):
    assert quiz_env.svc.process_on_demand_quiz("-100123", "en", "python", "medium")["retryable"] is False
    quiz_env.svc._generator.generate_question.assert_not_called()


def test_interactive_generation_and_failure_feedback(quiz_env):
    env = quiz_env
    env.svc._generator.generate_question.return_value = None
    result = env.svc.process_on_demand_quiz_with_feedback("-100123", "en", "python", "medium", reply_to_message_id=42)
    assert result["reason"] == "no valid question"
    env.svc._generator.generate_question.assert_called_once_with("python", "en", "medium", interactive=True)
    assert env.svc._sender.send_message.call_args.kwargs["reply_to_message_id"] == 42
