"""Contest dependency wiring at the Lambda application boundaries."""

from unittest.mock import MagicMock, patch

import app
import main


def test_app_dispatcher_reuses_and_injects_contest_and_queue_dependencies(monkeypatch) -> None:
    bot = MagicMock()
    captcha = MagicMock()
    memory = MagicMock()
    contest = MagicMock()
    sqs = MagicMock()

    monkeypatch.setattr(app, "MEMORY_TABLE_NAME", "memory-table")
    monkeypatch.setattr(app, "QUIZ_TABLE_NAME", "")
    monkeypatch.setattr(app, "QUIZ_LAMBDA_NAME", "")
    monkeypatch.setattr(app, "_bot", None)
    monkeypatch.setattr(app, "_captcha_repo", None)
    monkeypatch.setattr(app, "_memory_repo", None)
    monkeypatch.setattr(app, "_contest_repo", None)
    monkeypatch.setattr(app, "_sqs_repo", None)
    monkeypatch.setattr(app, "_dispatcher", None)

    with (
        patch.object(app, "TelegramClient", return_value=bot),
        patch.object(app, "CaptchaRepository", return_value=captcha),
        patch.object(app, "GroupMemoryRepository", return_value=memory),
        patch.object(app, "ContestRepository", return_value=contest),
        patch.object(app, "SQSClient", return_value=sqs),
        patch.object(app, "StatsRepository", return_value=MagicMock()),
        patch.object(app, "VoteRepository", return_value=MagicMock()),
    ):
        dispatcher = app.get_dispatcher()

    assert dispatcher.bot is bot
    assert dispatcher.captcha_repo is captcha
    assert dispatcher.memory_repo is memory
    assert dispatcher.contest_repo is contest
    assert dispatcher.sqs_repo is sqs
    assert app.get_dispatcher() is dispatcher
    assert app.get_contest_repo() is contest
    assert app.get_sqs_repo() is sqs


def test_main_sqs_boundary_passes_contest_and_shared_queue_dependencies() -> None:
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
    contest = MagicMock()
    sqs = MagicMock()
    context = MagicMock(aws_request_id="request-1")

    with (
        patch.object(main, "get_bot", return_value=bot),
        patch.object(main, "get_captcha_repo", return_value=captcha),
        patch.object(main, "get_memory_repo", return_value=memory),
        patch.object(main, "get_contest_repo", return_value=contest),
        patch.object(main, "get_sqs_repo", return_value=sqs),
        patch.object(main, "process_sqs_event") as process,
    ):
        assert main.lambda_handler(event, context) is None

    process.assert_called_once_with(
        event,
        bot,
        captcha,
        memory,
        contest_repo=contest,
        sqs_repo=sqs,
    )
