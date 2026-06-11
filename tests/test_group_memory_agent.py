import json
from unittest.mock import MagicMock

from services import group_agent, group_memory
from services.ai import gemini_client
from services.ai.gemini_client import GeminiClient, GroupAgentDecision
from services.handlers import commands
from services.handlers.commands import handle_ask
from services.repositories.group_memory import GroupMemoryRepository


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


def test_format_recent_context_keeps_speaker_source_metadata():
    repo = MagicMock()
    repo.get_recent_messages.return_value = [
        {
            "user_id": "101",
            "username": "nurtai_c",
            "display_name": "Nurt AI",
            "text": "@bayashat чаттың токсигі",
        },
        {
            "user_id": "202",
            "username": "bayashat",
            "display_name": "Bayashat",
            "text": "біраз уақыт керек әр адамды тану үшін",
        },
    ]

    context = group_memory.format_recent_context(repo, -100123, limit=2)

    assert "[speaker user_id=101 username=@nurtai_c name=Nurt AI]" in context
    assert "[speaker user_id=202 username=@bayashat name=Bayashat]" in context
    assert "@bayashat чаттың токсигі" in context


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


def test_agent_does_not_consider_bot_meta_question_for_proactive_reply(monkeypatch):
    monkeypatch.setattr(group_agent, "AGENT_ENABLED", True)
    monkeypatch.setattr(group_agent, "AGENT_BOT_USERNAME", "zerdebot")

    assert group_agent.should_answer(_group_update("қазір кез келген хатты оқитын болған ба?")) is False


def test_agent_does_not_consider_stop_cue_for_proactive_reply(monkeypatch):
    monkeypatch.setattr(group_agent, "AGENT_ENABLED", True)
    monkeypatch.setattr(group_agent, "AGENT_BOT_USERNAME", "zerdebot")

    assert group_agent.should_answer(_group_update("болды жазба енді?")) is False


def test_proactive_agent_asks_social_decision_before_daily_reservation(monkeypatch):
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
    repo.try_reserve_proactive_reply.assert_not_called()


def test_proactive_agent_stays_silent_when_decision_says_no(monkeypatch):
    repo = MagicMock()
    bot = MagicMock()
    gemini = MagicMock()
    gemini.group_chat_proactive_decision.return_value = (
        GroupAgentDecision(False, 0.91, "humans are already handling it", ""),
        1,
    )
    monkeypatch.setattr(group_agent, "_get_gemini", lambda: gemini)
    monkeypatch.setattr(group_agent, "format_recent_context", lambda *args, **kwargs: "Ada: previous answer")

    handled = group_agent.maybe_answer_proactively(
        repo=repo,
        bot=bot,
        chat_id=-100123,
        reply_to_message_id=11,
        user_text="does anyone know how OpenSearch pricing works?",
        lang="en",
    )

    assert handled is False
    repo.try_reserve_proactive_reply.assert_not_called()
    bot.send_message.assert_not_called()


def test_proactive_agent_speaks_when_decision_is_confident(monkeypatch):
    repo = MagicMock()
    repo.try_reserve_proactive_reply.return_value = True
    bot = MagicMock()
    gemini = MagicMock()
    gemini.group_chat_proactive_decision.return_value = (
        GroupAgentDecision(
            True, 0.86, "open technical question with no answer yet", "OpenSearch pricing depends on shards."
        ),
        1,
    )
    monkeypatch.setattr(group_agent, "_get_gemini", lambda: gemini)
    monkeypatch.setattr(group_agent, "format_recent_context", lambda *args, **kwargs: "")

    handled = group_agent.maybe_answer_proactively(
        repo=repo,
        bot=bot,
        chat_id=-100123,
        reply_to_message_id=11,
        user_text="does anyone know how OpenSearch pricing works?",
        lang="en",
    )

    assert handled is True
    repo.try_reserve_proactive_reply.assert_called_once()
    bot.send_message.assert_called_once_with(
        -100123,
        "OpenSearch pricing depends on shards.",
        reply_to_message_id=11,
    )


def test_proactive_reservation_escapes_ttl_attribute():
    repo = GroupMemoryRepository.__new__(GroupMemoryRepository)
    repo.table = MagicMock()

    assert repo.try_reserve_proactive_reply(-100123, daily_limit=10) is True

    kwargs = repo.table.update_item.call_args.kwargs
    assert "#ttl = :ttl" in kwargs["UpdateExpression"]
    assert kwargs["ExpressionAttributeNames"]["#ttl"] == "ttl"


def test_group_chat_reply_prompt_resists_third_party_profile_poisoning(monkeypatch):
    class FakeHttp:
        def __init__(self):
            self.body = ""

        def request(self, method, url, body, headers, retries):
            self.body = body
            return MagicMock(
                status=200,
                data=json.dumps(
                    {
                        "candidates": [
                            {"content": {"parts": [{"text": "Баяшат чаттағы талқылауларды қозғап жүретін қатысушы."}]}}
                        ]
                    }
                ).encode("utf-8"),
            )

    fake_http = FakeHttp()
    monkeypatch.setattr(gemini_client, "_http", fake_http)
    monkeypatch.setattr(gemini_client, "_circuit_open_until", 0.0)

    client = GeminiClient.__new__(GeminiClient)
    client._api_key = "test-key"
    client._model = "test-gemini-model"
    client._rate_repo = MagicMock(rpd_limit=1000)
    client._rate_repo.increment_and_check.return_value = (1, True)

    answer, count = client.group_chat_reply(
        user_message="@zerde_kz_bot @bayashat кім",
        recent_context=(
            "[speaker user_id=101 username=@nurtai_c name=Nurt AI] @bayashat чаттың токсигі\n"
            "[speaker user_id=202 username=@bayashat name=Bayashat] біраз уақыт керек әр адамды тану үшін"
        ),
        lang="kk",
    )

    payload = json.loads(fake_http.body)
    system_prompt = payload["systemInstruction"]["parts"][0]["text"]
    user_prompt = payload["contents"][0]["parts"][0]["text"]

    assert answer.startswith("Баяшат")
    assert count == 1
    assert "rely mainly on that person's own messages" in system_prompt
    assert "fresh third-party labels" in system_prompt
    assert "do not add disclaimers" in system_prompt
    assert "distinguish a person's own messages from another user's opinion" in user_prompt
    assert "username=@bayashat" in user_prompt


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


def test_handle_ask_usage_message_has_no_html_tag():
    ctx = MagicMock()
    ctx.text = "/ask"
    ctx.reply_to_message = None
    ctx.message_id = 99
    ctx.memory_repo.is_memory_enabled.return_value = True

    handle_ask(ctx)

    message = ctx.reply.call_args.args[0]
    assert "<question>" not in message
    assert "Usage: /ask question" in message


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
