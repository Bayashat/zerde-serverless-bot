"""Separate Lambda import namespaces, real Moto table, fake Telegram and clock."""

import importlib
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import boto3
import pytest
from moto import mock_aws

_quiz_dir = str(Path(__file__).resolve().parents[1] / "src" / "quiz")
os.environ.setdefault("QUIZ_LLM_RPD", "1000")
_saved = {
    name: module
    for name, module in list(sys.modules.items())
    if name in {"core", "services"} or name.startswith(("core.", "services."))
}
try:
    for name in _saved:
        sys.modules.pop(name)
    sys.path.insert(0, _quiz_dir)
    publication = importlib.import_module("services._publication")
    service_module = importlib.import_module("services.quiz_service")
    sender_module = importlib.import_module("services.quiz_sender")
    QuizService = service_module.QuizService
    PublicationRepository = service_module.QuizRepository
finally:
    sys.path.remove(_quiz_dir)
    for name in list(sys.modules):
        if name in {"core", "services"} or name.startswith(("core.", "services.")):
            sys.modules.pop(name)
    sys.modules.update(_saved)


def question():
    return {
        "question": "What is Python?",
        "options": ["Language", "Database", "Cloud", "Protocol"],
        "correct_option_index": 0,
        "explanation": "Python is a language.",
        "difficulty": "medium",
        "points": 3,
    }


@pytest.fixture
def quiz_env(monkeypatch):
    from services.quiz_answers import process_quiz_answer_task
    from services.repositories import _quiz_answers, quiz

    with mock_aws():
        db = boto3.resource("dynamodb", region_name="eu-central-1")
        table = db.create_table(
            TableName="quiz-protocol",
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"} for key in ("PK", "SK", "poll_id")],
            BillingMode="PAY_PER_REQUEST",
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "PollIdIndex",
                    "KeySchema": [{"AttributeName": "poll_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        )
        clock = SimpleNamespace(now=int(time.time()))
        monkeypatch.setattr(publication, "time", SimpleNamespace(time=lambda: clock.now))
        monkeypatch.setattr(service_module, "time", SimpleNamespace(time=lambda: clock.now, monotonic=time.monotonic))
        monkeypatch.setattr(_quiz_answers, "time", SimpleNamespace(time=lambda: clock.now))
        monkeypatch.setattr(quiz, "get_dynamodb", lambda: db)
        monkeypatch.setattr(quiz, "time", SimpleNamespace(time=lambda: clock.now))
        monkeypatch.setattr(quiz, "QUIZ_TABLE_NAME", table.name)
        import services.quiz_answers as answer_worker

        monkeypatch.setattr(answer_worker, "time", SimpleNamespace(time=lambda: clock.now))
        repo = PublicationRepository.__new__(PublicationRepository)
        repo._table = table
        svc = QuizService.__new__(QuizService)
        svc._repo, svc._generator, svc._sender = repo, Mock(), Mock()
        svc._generator.generate_question.return_value = question()
        svc._generator.translate_question.side_effect = lambda value, *args, **kwargs: value
        sent = []

        def receipt(*, chat_id, question, options, correct_option_id, **kwargs):
            result = {
                "message_id": 100 + len(sent),
                "date": clock.now,
                "from": {"id": 999, "is_bot": True},
                "chat": {"id": int(chat_id)},
                "poll": {
                    "id": f"poll-{len(sent)}",
                    "type": "quiz",
                    "is_anonymous": False,
                    "allows_multiple_answers": False,
                    "allows_revoting": False,
                    "question": question,
                    "options": [{"text": text} for text in options],
                    "correct_option_ids": [correct_option_id],
                },
            }
            sent.append(result)
            return result

        svc._sender.send_quiz_poll.side_effect = receipt
        bot_repo = quiz.QuizRepository()

        def answer(poll_id="poll-0", user_id=7, option=0, update_id=1):
            return bot_repo.persist_answer(
                {"poll_id": poll_id, "user": {"id": user_id, "first_name": "Test"}, "option_ids": [option]}, update_id
            )

        def process(poll_id="poll-0", user_id="7"):
            return process_quiz_answer_task(
                repo=bot_repo,
                body={"schema": 2, "task_type": "PROCESS_QUIZ_ANSWER", "poll_id": poll_id, "user_id": user_id},
            )

        yield SimpleNamespace(
            repo=repo,
            bot=bot_repo,
            table=table,
            svc=svc,
            clock=clock,
            sent=sent,
            answer=answer,
            process=process,
            receipt=receipt,
        )
