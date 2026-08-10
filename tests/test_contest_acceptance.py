"""Target-perspective contest transcript using Telegram-shaped updates."""

from __future__ import annotations

import time
from copy import deepcopy
from unittest.mock import MagicMock, patch

from core.dispatcher import Dispatcher
from services.contest import REDRAW_LIMIT_KK, ContestService
from services.handlers import register_handlers
from services.repositories.contest import RegistrationResult

CHAT_ID = -100123
CHANNEL_ID = -100456
ROOT_ID = 11
OWNER_ID = 42
BOT_ID = 9000


class AcceptanceContestRepository:
    """Small stateful double; DynamoDB conditions are covered by repository tests."""

    def __init__(self) -> None:
        self.contest: dict | None = None
        self.participants: dict[str, dict] = {}
        self.rules_alias: dict[int, int] = {}

    def get_contest(self, chat_id, root_message_id, *, consistent=False):
        if self.contest and int(root_message_id) == int(self.contest["root_message_id"]):
            return deepcopy(self.contest)
        return None

    def create_contest(self, **kwargs) -> bool:
        if self.contest:
            return False
        self.contest = {
            **kwargs,
            "chat_id": str(kwargs["chat_id"]),
            "source_channel_id": str(kwargs["source_channel_id"]),
            "status": "CREATING",
            "participant_count": 0,
            "draw_count": 0,
            "winner_user_ids": [],
            "winners": [],
        }
        return True

    def begin_creation_attempt(
        self,
        chat_id,
        root_message_id,
        *,
        attempt_id,
        stale_before,
        now,
    ) -> bool:
        assert self.contest and self.contest["status"] == "CREATING"
        if self.contest.get("creation_attempt_id"):
            return False
        self.contest["creation_attempt_id"] = attempt_id
        return True

    def release_creation_attempt(self, chat_id, root_message_id, *, attempt_id) -> bool:
        assert self.contest
        if self.contest.get("creation_attempt_id") != attempt_id:
            return False
        self.contest.pop("creation_attempt_id", None)
        return True

    def activate_contest(self, chat_id, root_message_id, rules_message_id, *, attempt_id) -> bool:
        assert self.contest and self.contest["status"] == "CREATING"
        assert self.contest["creation_attempt_id"] == attempt_id
        self.contest["status"] = "OPEN"
        self.contest["rules_message_id"] = rules_message_id
        self.contest.pop("creation_attempt_id", None)
        self.rules_alias[int(rules_message_id)] = int(root_message_id)
        return True

    def fail_creation(self, chat_id, root_message_id, *, attempt_id) -> bool:
        assert self.contest
        assert self.contest["creation_attempt_id"] == attempt_id
        self.contest["status"] = "CREATION_FAILED"
        return True

    def resolve_contest_by_anchor(self, chat_id, anchor_message_id):
        if not self.contest:
            return None
        anchor = int(anchor_message_id)
        if anchor == int(self.contest["root_message_id"]) or self.rules_alias.get(anchor) == ROOT_ID:
            return deepcopy(self.contest)
        return None

    def register_participant(self, **kwargs) -> RegistrationResult:
        assert self.contest
        if self.contest["status"] != "OPEN":
            return RegistrationResult.CLOSED
        user_id = str(kwargs["user_id"])
        if user_id in self.participants:
            return RegistrationResult.DUPLICATE
        self.participants[user_id] = {
            **kwargs,
            "chat_id": str(kwargs["chat_id"]),
            "user_id": user_id,
        }
        self.contest["participant_count"] += 1
        return RegistrationResult.REGISTERED

    def iter_participants(self, chat_id, root_message_id):
        yield from (deepcopy(value) for value in self.participants.values())

    def begin_first_draw(self, chat_id, root_message_id, *, attempt_id) -> bool:
        assert self.contest
        if self.contest["status"] != "OPEN":
            return False
        self.contest["status"] = "DRAWING"
        self.contest["pending_draw_number"] = 1
        self.contest["draw_attempt_id"] = attempt_id
        return True

    def begin_redraw(self, chat_id, root_message_id, *, expected_draw_count, attempt_id) -> bool:
        assert self.contest
        if self.contest["status"] != "DRAWN" or self.contest["draw_count"] != expected_draw_count:
            return False
        self.contest["status"] = "DRAWING"
        self.contest["pending_draw_number"] = expected_draw_count + 1
        self.contest["draw_attempt_id"] = attempt_id
        return True

    def abort_draw(self, chat_id, root_message_id, *, draw_number, attempt_id) -> bool:
        assert self.contest
        if self.contest.get("draw_attempt_id") != attempt_id:
            return False
        self.contest["status"] = "OPEN" if draw_number == 1 else "DRAWN"
        self.contest.pop("pending_draw_number", None)
        self.contest.pop("draw_attempt_id", None)
        return True

    def complete_draw(
        self,
        chat_id,
        root_message_id,
        *,
        draw_number,
        attempt_id,
        participant,
        frozen_participant_count,
    ) -> bool:
        assert self.contest and self.contest["status"] == "DRAWING"
        if self.contest.get("draw_attempt_id") != attempt_id:
            return False
        if participant["user_id"] in self.contest["winner_user_ids"]:
            return False
        winner = {
            key: participant[key]
            for key in ("user_id", "entry_message_id", "username", "first_name", "last_name", "text")
            if participant.get(key) is not None
        }
        winner.update({"draw_number": draw_number, "selected_at": int(time.time())})
        self.contest["status"] = "DRAWN"
        self.contest["draw_count"] = draw_number
        self.contest["winner_user_ids"].append(participant["user_id"])
        self.contest["winners"].append(winner)
        self.contest["frozen_participant_count"] = frozen_participant_count
        self.contest["announcement_state"] = "PENDING"
        self.contest["ttl_sweep_status"] = "PENDING"
        self.contest.setdefault("expires_at", int(time.time()) + 30 * 24 * 60 * 60)
        self.contest.pop("pending_draw_number", None)
        self.contest.pop("draw_attempt_id", None)
        return True

    def mark_announcement_sent(
        self,
        chat_id,
        root_message_id,
        *,
        draw_number,
        announcement_message_id,
    ) -> bool:
        assert self.contest
        self.contest["announcement_state"] = "SENT"
        self.contest["winners"][draw_number - 1]["announcement_message_id"] = announcement_message_id
        return True

    @staticmethod
    def is_logically_expired(contest, *, now=None) -> bool:
        return bool(contest.get("expires_at") and int(contest["expires_at"]) <= int(now or time.time()))


def _root() -> dict:
    return {
        "message_id": ROOT_ID,
        "caption": "Үш сыйлық бар! #конкурс",
        "date": 100,
        "chat": {"id": CHAT_ID, "type": "supergroup"},
        "from": {"id": 777000, "is_bot": False, "first_name": "Telegram"},
        "sender_chat": {"id": CHANNEL_ID, "type": "channel", "title": "Official"},
        "is_automatic_forward": True,
        "forward_origin": {"type": "channel", "message_id": 7},
        "photo": [{"file_id": "photo-id"}],
    }


def _entry(user_id: int, message_id: int, *, reply_id: int = ROOT_ID) -> dict:
    return {
        "message_id": message_id,
        "message_thread_id": ROOT_ID,
        "reply_to_message": {"message_id": reply_id},
        "text": "Мен қатысамын!",
        "date": 200 + message_id,
        "chat": {"id": CHAT_ID, "type": "supergroup"},
        "from": {
            "id": user_id,
            "is_bot": False,
            "username": f"user{user_id}",
            "first_name": f"User {user_id}",
        },
    }


def _command(action: str, message_id: int, anchor: int) -> dict:
    return {
        "message": {
            "message_id": message_id,
            "text": f"/contest {action}",
            "chat": {"id": CHAT_ID, "type": "supergroup"},
            "from": {"id": OWNER_ID, "is_bot": False, "first_name": "Owner"},
            "reply_to_message": {"message_id": anchor},
        }
    }


def test_full_public_flow_has_equal_unique_chances_and_three_distinct_results(mock_stats_repo, mock_vote_repo) -> None:
    repo = AcceptanceContestRepository()
    bot = MagicMock()
    sqs = MagicMock()
    next_bot_message_id = iter(range(1000, 1100))
    bot.send_message.side_effect = lambda *args, **kwargs: {"message_id": next(next_bot_message_id)}
    bot.get_chat.return_value = {"linked_chat_id": CHANNEL_ID}
    bot.get_me.return_value = {"id": BOT_ID}
    bot.get_chat_member.side_effect = lambda chat_id, user_id: {
        "status": "administrator" if user_id == BOT_ID else "creator"
    }
    service = ContestService(repo, bot, sqs)

    service.observe_update({"message": _root()})
    assert repo.contest and repo.contest["status"] == "OPEN"
    rules_message_id = int(repo.contest["rules_message_id"])
    assert bot.send_message.call_args_list[0].kwargs["reply_to_message_id"] == ROOT_ID
    assert "осы бастапқы жазбаға тікелей жауап" in bot.send_message.call_args_list[0].args[1]

    service.observe_update({"message": _entry(OWNER_ID, 12)})
    service.observe_update({"message": _entry(OWNER_ID, 15)})  # duplicate user
    service.observe_update({"message": _entry(43, 13)})
    service.observe_update({"message": _entry(44, 14)})
    service.observe_update({"message": _entry(45, 16, reply_id=13)})  # nested reply

    assert list(repo.participants) == [str(OWNER_ID), "43", "44"]
    assert [item.args[2] for item in bot.set_message_reaction.call_args_list] == ["🎉", "🎉", "🎉"]
    assert [item.args[1] for item in bot.set_message_reaction.call_args_list] == [12, 13, 14]

    dispatcher = Dispatcher(
        bot,
        mock_stats_repo,
        sqs,
        mock_vote_repo,
        contest_repo=repo,
    )
    register_handlers(dispatcher)

    with patch(
        "services.contest.secrets.randbelow",
        side_effect=lambda upper: 0 if upper == 1 else upper - 1,
    ):
        dispatcher.process_update(_command("draw", 30, rules_message_id))
        dispatcher.process_update(_command("redraw", 31, ROOT_ID))
        dispatcher.process_update(_command("redraw", 32, rules_message_id))
        dispatcher.process_update(_command("redraw", 33, ROOT_ID))

    assert repo.contest["status"] == "DRAWN"
    assert repo.contest["draw_count"] == 3
    assert repo.contest["winner_user_ids"] == [str(OWNER_ID), "43", "44"]
    assert repo.contest["frozen_participant_count"] == 3

    winner_calls = [
        item for item in bot.send_message.call_args_list if item.args and "Жеңімпаз анықталды" in item.args[1]
    ]
    assert [item.kwargs["reply_to_message_id"] for item in winner_calls] == [12, 13, 14]
    assert all("Қатысушылар саны: <b>3</b>" in item.args[1] for item in winner_calls)
    assert [f"Ұтыс: <b>{number}/3</b>" in item.args[1] for number, item in enumerate(winner_calls, 1)] == [
        True,
        True,
        True,
    ]
    assert bot.send_message.call_args_list[-1].args[1] == REDRAW_LIMIT_KK
