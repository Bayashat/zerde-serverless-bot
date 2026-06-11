from unittest.mock import MagicMock

from services import group_agent, group_memory
from services.handlers import commands
from services.handlers.commands import handle_ask


def _group_update(text: str = "hello @ZerdeBot") -> dict:
    return {
        "message": {
            "message_id": 11,
            "date": 1_700_000_000,
            "text": text,
            "chat": {"id": -100123, "type": "supergroup"},
            "from": {"id": 42, "first_name": "Ada", "username": "ada", "is_bot": False},
        }
    }


def test_observe_update_stores_opted_in_group_message(monkeypatch):
    repo = MagicMock()
    repo.is_memory_enabled.return_value = True
    monkeypatch.setattr(group_memory, "GROUP_MEMORY_ENABLED", True)

    group_memory.observe_update(repo, _group_update("we discussed OpenSearch today"))

    repo.store_message.assert_called_once()
    kwargs = repo.store_message.call_args.kwargs
    assert kwargs["chat_id"] == -100123
    assert kwargs["message_id"] == 11
    assert kwargs["user_id"] == 42
    assert kwargs["display_name"] == "Ada"
    assert kwargs["text"] == "we discussed OpenSearch today"


def test_observe_update_skips_when_chat_has_not_opted_in(monkeypatch):
    repo = MagicMock()
    repo.is_memory_enabled.return_value = False
    monkeypatch.setattr(group_memory, "GROUP_MEMORY_ENABLED", True)

    group_memory.observe_update(repo, _group_update("normal message"))

    repo.store_message.assert_not_called()


def test_agent_should_answer_mention_when_enabled(monkeypatch):
    monkeypatch.setattr(group_agent, "AGENT_ENABLED", True)
    monkeypatch.setattr(group_agent, "AGENT_BOT_USERNAME", "zerdebot")

    assert group_agent.should_answer(_group_update("hey @ZerdeBot what did we decide?")) is True


def test_agent_should_not_answer_plain_chatter(monkeypatch):
    monkeypatch.setattr(group_agent, "AGENT_ENABLED", True)
    monkeypatch.setattr(group_agent, "AGENT_BOT_USERNAME", "zerdebot")

    assert group_agent.should_answer(_group_update("just talking to the group")) is False


def test_agent_can_consider_open_question_when_enabled(monkeypatch):
    monkeypatch.setattr(group_agent, "AGENT_ENABLED", True)
    monkeypatch.setattr(group_agent, "AGENT_BOT_USERNAME", "zerdebot")

    assert group_agent.should_answer(_group_update("does anyone know how OpenSearch pricing works?")) is True


def test_proactive_agent_respects_daily_limit(monkeypatch):
    repo = MagicMock()
    repo.is_agent_enabled.return_value = True
    repo.try_reserve_proactive_reply.return_value = False
    monkeypatch.setattr(group_agent, "AGENT_ENABLED", True)
    monkeypatch.setattr(group_agent, "AGENT_BOT_USERNAME", "zerdebot")

    handled = group_agent.handle_update(
        repo=repo,
        bot=MagicMock(),
        update=_group_update("does anyone know how OpenSearch pricing works?"),
    )

    assert handled is False
    repo.try_reserve_proactive_reply.assert_called_once()


def test_handle_ask_uses_group_context_answer(monkeypatch):
    ctx = MagicMock()
    ctx.text = "/ask what happened yesterday?"
    ctx.chat_id = -100123
    ctx.message_id = 99
    ctx.lang_code = "en"
    ctx.memory_repo.is_memory_enabled.return_value = True
    answer = MagicMock(return_value=True)
    monkeypatch.setattr("services.handlers.commands.answer_group_question", answer)

    handle_ask(ctx)

    answer.assert_called_once_with(
        repo=ctx.memory_repo,
        bot=ctx.bot,
        chat_id=-100123,
        reply_to_message_id=99,
        user_text="what happened yesterday?",
        lang="en",
    )
    ctx.reply.assert_not_called()


def _command_ctx(*, user_id: int = 42, status: str = "member") -> MagicMock:
    ctx = MagicMock()
    ctx.chat_id = -100123
    ctx.user_id = user_id
    ctx.message_id = 99
    ctx.lang_code = "en"
    ctx.memory_repo.get_chat_settings.return_value = {"memory_enabled": True, "agent_enabled": False}
    ctx.bot.get_chat_member.return_value = {"status": status}
    return ctx


def test_memory_on_rejects_plain_group_admin(monkeypatch):
    monkeypatch.setattr(commands, "ADMIN_USER_ID", 1)
    monkeypatch.setattr(commands, "GROUP_MEMORY_ENABLED", True)
    ctx = _command_ctx(user_id=42, status="administrator")

    commands.handle_memory_on(ctx)

    ctx.memory_repo.set_chat_settings.assert_not_called()
    ctx.reply.assert_called_once()


def test_memory_on_allows_group_owner(monkeypatch):
    monkeypatch.setattr(commands, "ADMIN_USER_ID", 1)
    monkeypatch.setattr(commands, "GROUP_MEMORY_ENABLED", True)
    ctx = _command_ctx(user_id=42, status="creator")

    commands.handle_memory_on(ctx)

    ctx.memory_repo.set_chat_settings.assert_called_once_with(-100123, memory_enabled=True)


def test_memory_on_allows_bot_owner(monkeypatch):
    monkeypatch.setattr(commands, "ADMIN_USER_ID", 1)
    monkeypatch.setattr(commands, "GROUP_MEMORY_ENABLED", True)
    ctx = _command_ctx(user_id=1, status="member")

    commands.handle_memory_on(ctx)

    ctx.memory_repo.set_chat_settings.assert_called_once_with(-100123, memory_enabled=True)


def test_memory_status_allows_group_admin(monkeypatch):
    monkeypatch.setattr(commands, "ADMIN_USER_ID", 1)
    ctx = _command_ctx(user_id=42, status="administrator")

    commands.handle_memory_status(ctx)

    ctx.memory_repo.get_chat_settings.assert_called_once_with(-100123)


def test_forget_group_allows_only_bot_owner(monkeypatch):
    monkeypatch.setattr(commands, "ADMIN_USER_ID", 1)
    admin_ctx = _command_ctx(user_id=42, status="creator")

    commands.handle_forget_group(admin_ctx)

    admin_ctx.memory_repo.delete_chat_memory.assert_not_called()

    owner_ctx = _command_ctx(user_id=1, status="member")
    owner_ctx.memory_repo.delete_chat_memory.return_value = 3

    commands.handle_forget_group(owner_ctx)

    owner_ctx.memory_repo.delete_chat_memory.assert_called_once_with(-100123)
