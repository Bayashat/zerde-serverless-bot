"""Exercise the real command, invoker and JSON sink with only external IO stubbed."""

import io
import json
import logging
from unittest.mock import Mock

import pytest
from core.dispatcher import Context
from core.logger import LoggerAdapter
from services.handlers import commands
from services.repositories import lambda_invoker
from zerde_common.logger import JSONFormatter


@pytest.fixture
def command_logs(monkeypatch):
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JSONFormatter())
    logger = logging.Logger("quiz-command-log-test", logging.DEBUG)
    logger.addHandler(handler)
    adapter = LoggerAdapter(logger, {})
    monkeypatch.setattr(commands, "logger", adapter)
    monkeypatch.setattr(lambda_invoker, "logger", adapter)
    return output


@pytest.mark.parametrize("topic", ["private arbitrary topic", "құпия тақырып", "私人主题 несколько слов"])
def test_quiz_command_logs_length_but_delivers_the_complete_topic(topic, command_logs, mock_bot):
    invoker = lambda_invoker.LambdaInvoker()
    invoker._client = Mock()
    ctx = Context(
        {
            "message": {
                "message_id": 17,
                "chat": {"id": -100123, "type": "supergroup"},
                "from": {"id": 3},
                "text": f"/genquiz@zerde_dev_bot {topic} easy ru",
            }
        },
        mock_bot,
        lambda_invoker=invoker,
    )

    commands.handle_quiz_generate(ctx)

    invoker._client.invoke.assert_called_once_with(
        FunctionName=commands.QUIZ_LAMBDA_NAME,
        InvocationType="Event",
        Payload=json.dumps(
            {
                "action": "on_demand",
                "chat_id": "-100123",
                "topic": topic,
                "lang": "ru",
                "difficulty": "easy",
                "reply_to_message_id": 17,
            }
        ).encode(),
    )
    emitted = command_logs.getvalue()
    record = json.loads(emitted)
    assert topic not in emitted
    assert "topic" not in record
    assert record["topic_chars"] == len(topic)
    assert record["lang"] == "ru" and record["difficulty"] == "easy"
    assert record["message"] == "Invoking quiz lambda on-demand"
    mock_bot.send_message.assert_not_called()


@pytest.mark.parametrize("chain", ["cause", "context"])
def test_async_invocation_failure_omits_content_and_exception_chain(chain, command_logs):
    private = "arbitrary private diagnostic content"
    fake_token = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ_fake_token"

    def fail(**_):
        try:
            raise ValueError(f"{private} {fake_token}")
        except ValueError as cause:
            if chain == "cause":
                raise RuntimeError(private) from cause
            raise RuntimeError(private)

    invoker = lambda_invoker.LambdaInvoker()
    invoker._client = Mock()
    invoker._client.invoke.side_effect = fail

    assert invoker.invoke_async("quiz-test-function", {"topic": private}) is False

    invoker._client.invoke.assert_called_once()
    emitted = command_logs.getvalue()
    record = json.loads(emitted)
    assert private not in emitted and fake_token not in emitted
    assert "exception" not in record
    assert set(record) == {"timestamp", "level", "message", "location", "function_name", "error_type"}
    assert record["message"] == "Async Lambda invocation failed"
    assert record["function_name"] == "quiz-test-function"
    assert record["error_type"] == "RuntimeError"


def test_async_acceptance_keeps_original_single_call_contract(command_logs):
    invoker = lambda_invoker.LambdaInvoker()
    invoker._client = Mock()
    payload = {"topic": "private complete topic"}

    assert invoker.invoke_async("quiz-test-function", payload) is True

    invoker._client.invoke.assert_called_once_with(
        FunctionName="quiz-test-function", InvocationType="Event", Payload=json.dumps(payload).encode()
    )
    assert command_logs.getvalue() == ""
