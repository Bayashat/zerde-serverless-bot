"""Shared dependency wiring at the Lambda application boundaries."""

from unittest.mock import MagicMock, patch

import app
import main
import pytest


@pytest.mark.parametrize("quiz_enabled", [False, True])
def test_app_dispatcher_reuses_and_injects_shared_dependencies(monkeypatch, quiz_enabled) -> None:
    bot = MagicMock()
    captcha = MagicMock()
    memory = MagicMock()
    sqs = MagicMock()
    quiz, invoker = MagicMock(), MagicMock()

    monkeypatch.setattr(app, "MEMORY_TABLE_NAME", "memory-table")
    monkeypatch.setattr(app, "QUIZ_TABLE_NAME", "quiz-table" if quiz_enabled else "")
    monkeypatch.setattr(app, "QUIZ_LAMBDA_NAME", "quiz-lambda" if quiz_enabled else "")
    monkeypatch.setattr(app, "_quiz_repo", None)
    monkeypatch.setattr(app, "_bot", None)
    monkeypatch.setattr(app, "_captcha_repo", None)
    monkeypatch.setattr(app, "_memory_repo", None)
    monkeypatch.setattr(app, "_sqs_repo", None)
    monkeypatch.setattr(app, "_dispatcher", None)

    with (
        patch.object(app, "TelegramClient", return_value=bot),
        patch.object(app, "CaptchaRepository", return_value=captcha),
        patch("services.repositories.explicit_context_repository.ExplicitContextRepository", return_value=memory),
        patch.object(app, "SQSClient", return_value=sqs),
        patch.object(app, "StatsRepository", return_value=MagicMock()),
        patch.object(app, "VoteRepository", return_value=MagicMock()),
        patch.object(app, "QuizRepository", return_value=quiz),
        patch.object(app, "LambdaInvoker", return_value=invoker),
    ):
        dispatcher = app.get_dispatcher()

    assert dispatcher.bot is bot
    assert dispatcher.captcha_repo is captcha
    assert dispatcher.memory_repo is memory
    assert dispatcher.sqs_repo is sqs
    assert dispatcher.quiz_repo is (quiz if quiz_enabled else None)
    assert dispatcher.lambda_invoker is (invoker if quiz_enabled else None)
    assert app.get_dispatcher() is dispatcher
    assert app.get_sqs_repo() is sqs


def test_main_sqs_boundary_passes_shared_dependencies() -> None:
    event = {
        "Records": [
            {
                "eventSource": "aws:sqs",
                "messageId": "mid-1",
                "body": "{}",
            }
        ]
    }
    bot = MagicMock()
    captcha = MagicMock()
    memory = MagicMock()
    sqs = MagicMock()
    context = MagicMock(aws_request_id="request-1")

    with (
        patch.object(main, "get_bot", return_value=bot),
        patch.object(main, "get_captcha_repo", return_value=captcha),
        patch.object(main, "get_memory_repo", return_value=memory),
        patch.object(main, "get_sqs_repo", return_value=sqs),
        patch.object(main, "get_quiz_repo", return_value=None),
        patch.object(main, "process_sqs_event") as process,
    ):
        assert main.lambda_handler(event, context) is None

    process.assert_called_once_with(
        event,
        bot,
        captcha,
        memory,
        sqs_repo=sqs,
        memory_ingestion=None,
        quiz_repo=None,
    )
