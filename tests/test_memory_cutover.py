"""Cutover regression: replayed legacy work has no data or social side effects."""

import json
import time
from unittest.mock import MagicMock

import pytest
from services import group_agent
from services.handlers.commands import process_group_ask_task
from services.memory_cutover import EXPLICIT_CONTEXT_VERSION, RETIRED_TASK_TYPES
from services.sqs_task_router import process_sqs_event, process_vector_sqs_event


@pytest.mark.parametrize("task_type", sorted(RETIRED_TASK_TYPES) + ["PROCESS_GROUP_ASK"])
def test_old_task_replay_cannot_read_write_or_speak(task_type, monkeypatch):
    # Deliberately incomplete payload: retirement precedes source/client access.
    event = {"Records": [{"body": json.dumps({"task_type": task_type, "user_text": "OLD SECRET"})}]}
    bot, repo = MagicMock(), MagicMock()
    process_sqs_event(event, bot, MagicMock(), repo)
    process_vector_sqs_event(event, repo)
    assert bot.mock_calls == []
    assert repo.mock_calls == []


@pytest.mark.parametrize("version", [None, "old", "unknown-future"])
def test_explicit_worker_rejects_unknown_context_before_download(version):
    repo, bot = MagicMock(), MagicMock()
    process_group_ask_task(repo=repo, bot=bot, body={"context_version": version, "media_ref": {"file_id": "old"}})
    assert repo.mock_calls == []
    assert bot.mock_calls == []


@pytest.mark.parametrize("condition", ["legacy", "expired", "with_sources", "missing", "read_failure"])
def test_old_reply_text_cannot_bypass_memory_retirement(monkeypatch, condition):
    monkeypatch.setattr(group_agent, "AGENT_BOT_ID", 999)
    item = {
        "context_version": EXPLICIT_CONTEXT_VERSION,
        "ttl": int(time.time()) + 60,
        "answer_text": "OLD PERSONAL FACT",
        "source_message_context": "OLD SOURCE",
    }
    if condition == "legacy":
        item.pop("context_version")
    elif condition == "expired":
        item["ttl"] = int(time.time()) - 1
    elif condition == "with_sources":
        item["retrieval_sources"] = [{"source_sk": "USER_FACT#old"}]
    elif condition == "missing":
        item = {}
    repo = MagicMock()
    repo.get_agent_reply_explanation.return_value = item
    if condition == "read_failure":
        repo.get_agent_reply_explanation.side_effect = RuntimeError("unavailable")
    message = {
        "text": "explain why?",
        "reply_to_message": {
            "message_id": 10,
            "from": {"is_bot": True, "id": 999},
            "text": "OLD PERSONAL FACT FROM TELEGRAM",
        },
    }
    context = group_agent.build_explicit_question_context(repo, -1001, message)
    assert context.user_text == "explain why?"
    assert context.retrieval_query == "explain why?"
    assert not context.source_message_context


def test_explicit_generation_never_invokes_legacy_retrieval(monkeypatch):
    repo, bot = MagicMock(), MagicMock()
    bot.send_message.return_value = {"message_id": 100}
    retrieve = MagicMock(side_effect=AssertionError("legacy retrieval called"))
    generate = MagicMock(return_value=("I do not know.", "synthetic"))
    monkeypatch.setattr(group_agent, "build_agent_memory_context", retrieve)
    monkeypatch.setattr(group_agent, "_generate_group_chat_reply", generate)
    assert group_agent.answer_group_question(
        repo=repo, bot=bot, chat_id=-1001, reply_to_message_id=11, user_text="Where does Ada work?", lang="en"
    )
    retrieve.assert_not_called()
    for name in [
        "recent_context",
        "long_term_memory_context",
        "semantic_memory_context",
        "user_profile_context",
        "requester_profile_context",
    ]:
        assert generate.call_args.kwargs[name] == ""
    assert repo.record_agent_reply.call_args.kwargs["context_version"] == EXPLICIT_CONTEXT_VERSION
    assert repo.record_agent_reply.call_args.kwargs["retrieval_sources"] == []
