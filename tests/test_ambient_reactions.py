import json
from decimal import Decimal
from unittest.mock import MagicMock

from services import ambient_reactions
from services.ai import ambient_reaction_classifier, gemini_client
from services.ai.ambient_reaction_classifier import FallbackAmbientReactionClassifier
from services.ai.gemini_client import GeminiClient
from services.ambient_reactions import (
    AmbientReactionContext,
    build_ambient_reaction_task_payload,
    evaluate_ambient_reaction_rate_limit,
    format_ambient_reaction_prompt_context,
    gather_ambient_reaction_context,
    is_ambient_reaction_eligible,
    process_ambient_reaction_task,
    validate_ambient_reaction_decision,
)
from services.repositories import sqs as sqs_module
from services.repositories.group_memory import GroupMemoryRepository
from services.repositories.sqs import SQSClient
from zerde_common.ai_errors import ProviderRateLimitError


def _update(text: str = "This DynamoDB migration note is actually useful") -> dict:
    return {
        "update_id": 123,
        "message": {
            "message_id": 11,
            "date": 1_700_000_000,
            "text": text,
            "chat": {"id": -100123, "type": "supergroup"},
            "from": {"id": 42, "first_name": "Ada", "username": "ada", "is_bot": False},
        },
    }


def _linked_channel_update(text: str = "1958 жылы Texas Instruments-та монолитті идея пайда болды.") -> dict:
    update = _update(text)
    update["message"]["from"] = {"id": 777000, "is_bot": False, "first_name": "Telegram"}
    update["message"]["sender_chat"] = {
        "id": -1001037498558,
        "title": "Тимурдан Инфо | it&tech",
        "username": "timurdaninfo",
        "type": "channel",
    }
    update["message"]["is_automatic_forward"] = True
    return update


def test_ambient_reaction_eligibility_filters_non_candidates() -> None:
    assert is_ambient_reaction_eligible(_update("This Terraform note is practical and useful")) is True

    private_update = _update("This Terraform note is practical and useful")
    private_update["message"]["chat"]["type"] = "private"
    assert is_ambient_reaction_eligible(private_update) is False

    bot_update = _update("This Terraform note is practical and useful")
    bot_update["message"]["from"]["is_bot"] = True
    assert is_ambient_reaction_eligible(bot_update) is False

    assert is_ambient_reaction_eligible(_update("/ask what is S3 Vectors?")) is True
    assert is_ambient_reaction_eligible(_update("😂😂😂")) is False
    assert is_ambient_reaction_eligible(_update("https://example.com/path")) is False
    assert is_ambient_reaction_eligible(_update("I need a lawyer for this court case")) is True
    assert is_ambient_reaction_eligible(_update("you are an idiot and should shut up")) is True

    media_update = _update("This Terraform note is practical and useful")
    media_update["message"]["photo"] = [{"file_id": "photo"}]
    assert is_ambient_reaction_eligible(media_update) is False


def test_ambient_reaction_payload_uses_linked_channel_actor() -> None:
    update = _linked_channel_update()

    payload = build_ambient_reaction_task_payload(update)

    assert payload is not None
    assert payload["user_id"] == -1001037498558
    assert payload["display_name"] == "Тимурдан Инфо | it&tech"
    assert payload["username"] == "timurdaninfo"
    assert payload["sender_type"] == "channel"
    assert payload["force_reaction"] is True


def test_ambient_reaction_payload_allows_linked_channel_media_without_caption() -> None:
    update = _linked_channel_update("")
    del update["message"]["text"]
    update["message"]["photo"] = [{"file_id": "photo-id", "file_size": 100}]

    payload = build_ambient_reaction_task_payload(update)

    assert payload is not None
    assert payload["force_reaction"] is True
    assert payload["text"] == "Official linked-channel media post without text caption."


def test_ambient_reaction_context_formats_linked_channel_sender_type() -> None:
    _, _, current = format_ambient_reaction_prompt_context(
        AmbientReactionContext(
            previous_messages=(),
            reply_chain=(),
            current_message={
                "message_id": 11,
                "user_id": "-1001037498558",
                "sender_type": "channel",
                "username": "timurdaninfo",
                "display_name": "Тимурдан Инфо | it&tech",
                "text": "Monolithic idea post",
            },
        )
    )

    assert "[speaker sender_type=channel username=@timurdaninfo name=Тимурдан Инфо | it&tech" in current


def test_validate_ambient_reaction_decision_accepts_only_allowed_contract() -> None:
    valid = validate_ambient_reaction_decision(
        json.dumps(
            {
                "should_react": True,
                "emoji": "🤣",
                "confidence": 0.91,
                "category": "humor",
                "reason": "Clear joke.",
            }
        ),
        confidence_threshold=0.80,
    )
    assert valid is not None
    assert valid.should_react is True
    assert valid.emoji == "🤣"

    assert validate_ambient_reaction_decision("not json") is None
    assert (
        validate_ambient_reaction_decision(
            {"should_react": True, "emoji": "😂", "confidence": 0.95, "category": "humor", "reason": "wrong emoji"}
        )
        is None
    )
    assert (
        validate_ambient_reaction_decision(
            {"should_react": False, "emoji": "👀", "confidence": 0.2, "category": "none", "reason": "no"}
        )
        is None
    )

    low = validate_ambient_reaction_decision(
        {"should_react": True, "emoji": "👀", "confidence": 0.79, "category": "interesting", "reason": "maybe"},
        confidence_threshold=0.80,
    )
    assert low is not None
    assert low.should_react is False
    assert low.emoji is None


def test_ambient_reaction_rate_limit_cooldowns_and_caps() -> None:
    now = 1_700_000_000
    assert (
        evaluate_ambient_reaction_rate_limit(
            [{"created_at": now - 60, "user_id": "7"}],
            user_id=42,
            now=now,
            min_gap_per_chat_seconds=300,
        ).reason
        == "chat_cooldown"
    )
    assert (
        evaluate_ambient_reaction_rate_limit(
            [{"created_at": now - 600, "user_id": "42"}],
            user_id=42,
            now=now,
            min_gap_per_chat_seconds=300,
            min_gap_per_user_seconds=1200,
        ).reason
        == "user_cooldown"
    )
    assert (
        evaluate_ambient_reaction_rate_limit(
            [{"created_at": now - 600, "user_id": "1"}, {"created_at": now - 700, "user_id": "2"}],
            user_id=42,
            now=now,
            min_gap_per_chat_seconds=300,
            min_gap_per_user_seconds=300,
            max_per_chat_per_hour=2,
        ).reason
        == "chat_hourly_limit"
    )
    assert (
        evaluate_ambient_reaction_rate_limit(
            [{"created_at": now - 4000, "user_id": str(idx)} for idx in range(3)],
            user_id=42,
            now=now,
            min_gap_per_chat_seconds=300,
            min_gap_per_user_seconds=300,
            max_per_chat_per_hour=10,
            max_per_chat_per_day=3,
        ).reason
        == "chat_daily_limit"
    )
    assert evaluate_ambient_reaction_rate_limit([], user_id=42, now=now).allowed is True


def test_gather_ambient_reaction_context_limits_previous_and_reply_chain() -> None:
    repo = MagicMock()
    repo.get_recent_messages.return_value = [
        {
            "message_id": idx,
            "created_at": 1_700_000_000 + idx,
            "user_id": str(idx),
            "display_name": f"User {idx}",
            "text": f"previous message {idx}",
        }
        for idx in range(1, 20)
    ]

    context = gather_ambient_reaction_context(
        repo=repo,
        chat_id=-100123,
        current_message_id=19,
        current_user_id=42,
        current_display_name="Ada",
        current_text="Current message has a strong useful signal",
        current_created_at=1_700_000_019,
        reply_chain=[
            {"message_id": 18, "user_id": 7, "display_name": "Grace", "text": "reply one"},
            {"message_id": 17, "user_id": 8, "display_name": "Linus", "text": "reply two"},
            {"message_id": 16, "user_id": 9, "display_name": "Ken", "text": "reply three"},
            {"message_id": 15, "user_id": 10, "display_name": "Extra", "text": "reply four"},
        ],
    )

    assert len(context.reply_chain) == 3
    assert len(context.previous_messages) == 10
    assert len(context.previous_messages) + len(context.reply_chain) + 1 <= 15
    assert context.previous_messages[0]["message_id"] == 6
    assert {item["message_id"] for item in context.previous_messages}.isdisjoint({16, 17, 18})
    assert context.current_message["message_id"] == 19


def test_ambient_reaction_payload_ignores_reply_media_captions() -> None:
    update = _update("This DynamoDB migration note is practical and useful")
    update["message"]["reply_to_message"] = {
        "message_id": 10,
        "date": 1_700_000_000,
        "caption": "caption should not become reaction context",
        "photo": [{"file_id": "photo-id"}],
        "chat": {"id": -100123, "type": "supergroup"},
        "from": {"id": 7, "first_name": "Grace", "is_bot": False},
    }

    payload = ambient_reactions.build_ambient_reaction_task_payload(update)

    assert payload is not None
    assert "reply_chain" not in payload


def test_process_ambient_reaction_task_sets_reaction_and_records_event(monkeypatch) -> None:
    monkeypatch.setattr(ambient_reactions, "AMBIENT_REACTIONS_ENABLED", True)
    repo = MagicMock()
    repo.get_recent_ambient_reactions.return_value = []
    repo.get_recent_messages.return_value = []
    bot = MagicMock()
    classifier = MagicMock()
    classifier.ambient_reaction_decision.return_value = (
        json.dumps(
            {
                "should_react": True,
                "emoji": "👍",
                "confidence": 0.92,
                "category": "useful",
                "reason": "High-quality practical message.",
            }
        ),
        "gemini",
    )
    monkeypatch.setattr(ambient_reactions, "_get_classifier", lambda: classifier)
    monkeypatch.setattr(ambient_reactions.time, "time", lambda: 1_700_000_100)

    handled = process_ambient_reaction_task(
        repo=repo,
        bot=bot,
        body={
            "chat_id": -100123,
            "message_id": 11,
            "user_id": 42,
            "display_name": "Ada",
            "text": "This DynamoDB migration note is practical and useful",
            "lang": "en",
            "created_at": 1_700_000_000,
        },
    )

    assert handled is True
    bot.set_message_reaction.assert_called_once_with(-100123, 11, "👍")
    repo.record_ambient_reaction.assert_called_once()
    assert repo.record_ambient_reaction.call_args.kwargs["emoji"] == "👍"


def test_process_forced_linked_channel_reaction_bypasses_rate_limit_and_classifier_skip(monkeypatch) -> None:
    monkeypatch.setattr(ambient_reactions, "AMBIENT_REACTIONS_ENABLED", True)
    repo = MagicMock()
    repo.get_recent_ambient_reactions.side_effect = AssertionError("forced reaction should not read rate-limit rows")
    repo.get_recent_messages.return_value = []
    bot = MagicMock()
    classifier = MagicMock()
    classifier.ambient_reaction_decision.return_value = (
        json.dumps(
            {
                "should_react": False,
                "emoji": None,
                "confidence": 0.2,
                "category": "none",
                "reason": "Would normally skip.",
            }
        ),
        "gemini",
    )
    monkeypatch.setattr(ambient_reactions, "_get_classifier", lambda: classifier)
    monkeypatch.setattr(ambient_reactions.time, "time", lambda: 1_700_000_100)

    handled = process_ambient_reaction_task(
        repo=repo,
        bot=bot,
        body={
            "chat_id": -100123,
            "message_id": 11,
            "user_id": -1001037498558,
            "display_name": "Тимурдан Инфо | it&tech",
            "sender_type": "channel",
            "text": "Official linked-channel media post without text caption.",
            "lang": "kk",
            "created_at": 1_700_000_000,
            "force_reaction": True,
        },
    )

    assert handled is True
    bot.set_message_reaction.assert_called_once_with(-100123, 11, "👀")
    repo.record_ambient_reaction.assert_called_once()
    assert repo.record_ambient_reaction.call_args.kwargs["category"] == "interesting"


def test_process_ambient_reaction_task_allows_command_and_sensitive_text(monkeypatch) -> None:
    monkeypatch.setattr(ambient_reactions, "AMBIENT_REACTIONS_ENABLED", True)
    repo = MagicMock()
    repo.get_recent_ambient_reactions.return_value = []
    repo.get_recent_messages.return_value = []
    bot = MagicMock()
    classifier = MagicMock()
    classifier.ambient_reaction_decision.return_value = (
        json.dumps(
            {
                "should_react": True,
                "emoji": "🤔",
                "confidence": 0.91,
                "category": "thoughtful",
                "reason": "The command text asks a thoughtful practical question.",
            }
        ),
        "deepseek",
    )
    monkeypatch.setattr(ambient_reactions, "_get_classifier", lambda: classifier)
    monkeypatch.setattr(ambient_reactions.time, "time", lambda: 1_700_000_100)

    handled = process_ambient_reaction_task(
        repo=repo,
        bot=bot,
        body={
            "chat_id": -100123,
            "message_id": 12,
            "user_id": 42,
            "display_name": "Ada",
            "text": "/ask I need a lawyer for this court case architecture note",
            "lang": "en",
            "created_at": 1_700_000_000,
        },
    )

    assert handled is True
    bot.set_message_reaction.assert_called_once_with(-100123, 12, "🤔")
    classifier.ambient_reaction_decision.assert_called_once()


def test_sqs_client_sends_ambient_reaction_task(monkeypatch) -> None:
    fake_client = MagicMock()
    monkeypatch.setattr(sqs_module, "_SQS_CLIENT", fake_client)
    sqs = SQSClient.__new__(SQSClient)
    sqs.queue_url = "queue-url"

    sqs.send_ambient_reaction_task(
        update_id=123,
        chat_id=-100123,
        message_id=11,
        user_id=42,
        display_name="Ada",
        username="ada",
        text="This DynamoDB migration note is useful",
        lang="en",
        created_at=1_700_000_000,
        reply_chain=[{"message_id": 10, "text": "previous"}],
        force_reaction=True,
    )

    kwargs = fake_client.send_message.call_args.kwargs
    payload = json.loads(kwargs["MessageBody"])
    assert kwargs["QueueUrl"] == "queue-url"
    assert payload["task_type"] == "PROCESS_AMBIENT_REACTION"
    assert payload["chat_id"] == -100123
    assert payload["message_id"] == 11
    assert payload["user_id"] == 42
    assert payload["reply_chain"][0]["message_id"] == 10
    assert payload["force_reaction"] is True


def test_gemini_ambient_reaction_prompt_returns_json_text(monkeypatch) -> None:
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
                            {
                                "content": {
                                    "parts": [
                                        {
                                            "text": json.dumps(
                                                {
                                                    "should_react": False,
                                                    "emoji": None,
                                                    "confidence": 0.31,
                                                    "category": "none",
                                                    "reason": "Ordinary message.",
                                                }
                                            )
                                        }
                                    ]
                                }
                            }
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

    raw, count = client.ambient_reaction_decision(
        current_message="[speaker user_id=42] This is an ordinary status update",
        previous_context="[speaker user_id=7] previous context",
        reply_context="[reply_depth=1] replied message",
        lang="en",
    )

    payload = json.loads(fake_http.body)
    system_prompt = payload["systemInstruction"]["parts"][0]["text"]
    user_prompt = payload["contents"][0]["parts"][0]["text"]
    assert json.loads(raw)["should_react"] is False
    assert count == 1
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert "Most messages should receive no reaction" in system_prompt
    assert "Use only these allowed emoji exactly: 🤣 👍 🤔 ❤️ 👀" in system_prompt
    assert "not automatic skips" in system_prompt
    assert "Commands may be considered" in user_prompt
    assert "Previous local group context" in user_prompt
    assert "Reply context" in user_prompt


def test_process_ambient_reaction_task_skips_invalid_classifier_output(monkeypatch) -> None:
    monkeypatch.setattr(ambient_reactions, "AMBIENT_REACTIONS_ENABLED", True)
    repo = MagicMock()
    repo.get_recent_ambient_reactions.return_value = []
    repo.get_recent_messages.return_value = []
    bot = MagicMock()
    classifier = MagicMock()
    classifier.ambient_reaction_decision.return_value = ("not json", "gemini")
    monkeypatch.setattr(ambient_reactions, "_get_classifier", lambda: classifier)

    handled = process_ambient_reaction_task(
        repo=repo,
        bot=bot,
        body={
            "chat_id": -100123,
            "message_id": 11,
            "user_id": 42,
            "display_name": "Ada",
            "text": "This DynamoDB migration note is practical and useful",
            "lang": "en",
        },
    )

    assert handled is False
    bot.set_message_reaction.assert_not_called()
    repo.record_ambient_reaction.assert_not_called()


def test_process_ambient_reaction_task_skips_when_groq_classifiers_fail(monkeypatch) -> None:
    monkeypatch.setattr(ambient_reactions, "AMBIENT_REACTIONS_ENABLED", True)
    repo = MagicMock()
    repo.get_recent_ambient_reactions.return_value = []
    repo.get_recent_messages.return_value = []
    bot = MagicMock()
    classifier = MagicMock()
    classifier.ambient_reaction_decision.side_effect = ProviderRateLimitError("all groq models rate limited")
    monkeypatch.setattr(ambient_reactions, "_get_classifier", lambda: classifier)

    handled = process_ambient_reaction_task(
        repo=repo,
        bot=bot,
        body={
            "chat_id": -100123,
            "message_id": 11,
            "user_id": 42,
            "display_name": "Ada",
            "text": "This DynamoDB migration note is practical and useful",
            "lang": "en",
        },
    )

    assert handled is False
    bot.set_message_reaction.assert_not_called()
    repo.record_ambient_reaction.assert_not_called()


def test_process_ambient_reaction_task_caps_decision_context(monkeypatch) -> None:
    monkeypatch.setattr(ambient_reactions, "AMBIENT_REACTIONS_ENABLED", True)
    monkeypatch.setattr(ambient_reactions, "AMBIENT_REACTIONS_DECISION_CONTEXT_CHARS", 180)
    repo = MagicMock()
    repo.get_recent_ambient_reactions.return_value = []
    repo.get_recent_messages.return_value = [
        {
            "message_id": idx,
            "user_id": idx,
            "display_name": f"User {idx}",
            "text": f"very long previous technical context line {idx} " + ("x" * 80),
            "created_at": 1_700_000_000 + idx,
        }
        for idx in range(1, 15)
    ]
    bot = MagicMock()
    classifier = MagicMock()
    classifier.ambient_reaction_decision.return_value = (
        json.dumps(
            {
                "should_react": False,
                "emoji": None,
                "confidence": 0.25,
                "category": "none",
                "reason": "No strong signal.",
            }
        ),
        "groq:fast",
    )
    monkeypatch.setattr(ambient_reactions, "_get_classifier", lambda: classifier)

    handled = process_ambient_reaction_task(
        repo=repo,
        bot=bot,
        body={
            "chat_id": -100123,
            "message_id": 99,
            "user_id": 42,
            "display_name": "Ada",
            "text": "This DynamoDB migration note is practical and useful",
            "lang": "en",
            "created_at": 1_700_000_100,
        },
    )

    assert handled is False
    kwargs = classifier.ambient_reaction_decision.call_args.kwargs
    assert len(kwargs["previous_context"]) + len(kwargs["reply_context"]) <= 180
    assert "line 14" in kwargs["previous_context"]
    bot.set_message_reaction.assert_not_called()


def test_ambient_reaction_classifier_factory_builds_groq_model_pool(monkeypatch) -> None:
    monkeypatch.setattr(ambient_reaction_classifier, "get_groq_api_key", lambda: "groq-key")
    monkeypatch.setattr(
        ambient_reaction_classifier,
        "AMBIENT_REACTIONS_DECISION_GROQ_MODELS",
        ("model-a", "model-b"),
    )

    classifier = ambient_reaction_classifier.create_ambient_reaction_classifier()

    assert classifier is not None
    assert [provider.provider_name for provider in classifier._providers] == ["groq:model-a", "groq:model-b"]


def test_ambient_reaction_classifier_falls_back_to_secondary_groq_model_on_rate_limit() -> None:
    primary = MagicMock()
    primary.provider_name = "groq:model-a"
    primary.ambient_reaction_decision.side_effect = ProviderRateLimitError("rate limited")
    secondary = MagicMock()
    secondary.provider_name = "groq:model-b"
    secondary.ambient_reaction_decision.return_value = json.dumps(
        {
            "should_react": False,
            "emoji": None,
            "confidence": 0.2,
            "category": "none",
            "reason": "No strong signal.",
        }
    )
    classifier = FallbackAmbientReactionClassifier([primary, secondary])

    raw, provider = classifier.ambient_reaction_decision(
        current_message="[speaker user_id=42] ordinary update",
        previous_context="",
        reply_context="",
        lang="kk",
    )

    assert json.loads(raw)["should_react"] is False
    assert provider == "groq:model-b"
    primary.ambient_reaction_decision.assert_called_once()
    secondary.ambient_reaction_decision.assert_called_once()


def test_ambient_reaction_classifier_falls_back_to_secondary_groq_model_on_bad_json() -> None:
    primary = MagicMock()
    primary.provider_name = "groq:model-a"
    primary.ambient_reaction_decision.return_value = "not json"
    secondary = MagicMock()
    secondary.provider_name = "groq:model-b"
    secondary.ambient_reaction_decision.return_value = json.dumps(
        {
            "should_react": False,
            "emoji": None,
            "confidence": 0.2,
            "category": "none",
            "reason": "No strong signal.",
        }
    )
    classifier = FallbackAmbientReactionClassifier([primary, secondary])

    raw, provider = classifier.ambient_reaction_decision(
        current_message="[speaker user_id=42] ordinary update",
        previous_context="",
        reply_context="",
        lang="kk",
    )

    assert json.loads(raw)["should_react"] is False
    assert provider == "groq:model-b"
    primary.ambient_reaction_decision.assert_called_once()
    secondary.ambient_reaction_decision.assert_called_once()


def test_record_ambient_reaction_persists_short_ttl(monkeypatch) -> None:
    repo = GroupMemoryRepository.__new__(GroupMemoryRepository)
    repo.table = MagicMock()
    monkeypatch.setattr("services.repositories.group_memory.time.time", lambda: 1_700_000_000)

    repo.record_ambient_reaction(
        chat_id=-100123,
        user_id=42,
        message_id=11,
        emoji="👀",
        category="interesting",
        confidence=0.87,
    )

    item = repo.table.put_item.call_args.kwargs["Item"]
    assert item["sk"].startswith("AMBIENT_REACTION#")
    assert item["kind"] == "ambient_reaction"
    assert item["ttl"] == 1_700_000_000 + 7 * 24 * 60 * 60
    assert item["confidence"] == Decimal("0.87")
