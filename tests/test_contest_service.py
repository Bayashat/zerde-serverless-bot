"""Contest recognition, fairness, and Telegram evidence tests."""

import json
from unittest.mock import ANY, MagicMock, call, patch

import pytest
from services.contest import (
    BOT_ADMIN_REQUIRED_KK,
    CONTEST_EXPIRED_KK,
    ENTRY_PHRASE,
    NO_PARTICIPANTS_KK,
    NO_REMAINING_CANDIDATES_KK,
    RULES_MESSAGE_KK,
    TELEGRAM_UPDATE_RETENTION_SECONDS,
    AnnouncementOrphanedError,
    ContestRetryRequiredError,
    ContestService,
    ContestTTLWorker,
    has_contest_marker,
    is_entry_message,
    process_contest_ttl_recovery_task,
)
from services.repositories.contest import RegistrationResult
from services.repositories.sqs import SQSClient
from services.telegram import TelegramAPIError

CHAT_ID = -100123
CHANNEL_ID = -100456
ROOT_ID = 11


def _root_message(content_key: str = "text", content: str = "Сыйлық #КоНкУрС") -> dict:
    return {
        "message_id": ROOT_ID,
        content_key: content,
        "date": 100,
        "chat": {"id": CHAT_ID, "type": "supergroup"},
        "from": {"id": 777000, "is_bot": False, "first_name": "Telegram"},
        "sender_chat": {"id": CHANNEL_ID, "type": "channel", "title": "Official"},
        "is_automatic_forward": True,
        "forward_origin": {"type": "channel", "message_id": 7},
    }


def _entry(user_id: int = 42, message_id: int = 12, text: str = "Мен ҚАТЫСАМЫН!") -> dict:
    return {
        "message_id": message_id,
        "message_thread_id": ROOT_ID,
        "reply_to_message": {"message_id": ROOT_ID},
        "text": text,
        "date": 200,
        "chat": {"id": CHAT_ID, "type": "supergroup"},
        "from": {
            "id": user_id,
            "is_bot": False,
            "username": f"user{user_id}",
            "first_name": "User",
            "last_name": str(user_id),
        },
    }


def _participant(user_id: int, message_id: int) -> dict:
    return {
        "user_id": str(user_id),
        "entry_message_id": message_id,
        "username": f"user{user_id}",
        "first_name": "User",
        "last_name": str(user_id),
        "text": ENTRY_PHRASE,
        "accepted_at": 200,
    }


def _winner(participant: dict, draw_number: int) -> dict:
    return {**participant, "draw_number": draw_number, "selected_at": 300}


def _service(repo: MagicMock | None = None, bot: MagicMock | None = None, sqs: MagicMock | None = None):
    repo = repo or MagicMock()
    bot = bot or MagicMock()
    sqs = sqs or MagicMock()
    repo.is_logically_expired.return_value = False
    bot.send_message.return_value = {"message_id": 999}
    return ContestService(repo, bot, sqs), repo, bot, sqs


def test_marker_is_standalone_case_insensitive_and_accepts_media_caption() -> None:
    assert has_contest_marker(_root_message())
    assert has_contest_marker(_root_message("caption", "Фото: #КОНКУРС!"))
    assert not has_contest_marker(_root_message(content="prefix#конкурс"))
    assert not has_contest_marker(_root_message(content="##конкурс"))
    assert not has_contest_marker(_root_message(content="#конкурстық"))


def test_entry_shape_requires_personal_direct_text_reply() -> None:
    assert is_entry_message(_entry(text="қатысамынба"))

    nested = _entry()
    nested["reply_to_message"] = {"message_id": 99}
    assert not is_entry_message(nested)

    caption = _entry()
    caption.pop("text")
    caption["caption"] = ENTRY_PHRASE
    assert not is_entry_message(caption)

    anonymous = _entry()
    anonymous["sender_chat"] = {"id": CHAT_ID, "type": "supergroup"}
    assert not is_entry_message(anonymous)

    bot_entry = _entry()
    bot_entry["from"]["is_bot"] = True
    assert not is_entry_message(bot_entry)


def test_official_linked_root_creates_fail_closed_then_posts_rules() -> None:
    service, repo, bot, _ = _service()
    creating = {"chat_id": str(CHAT_ID), "root_message_id": ROOT_ID, "status": "CREATING"}
    repo.get_contest.side_effect = [None, creating]
    repo.create_contest.return_value = True
    repo.activate_contest.return_value = True
    bot.get_chat.return_value = {"linked_chat_id": CHANNEL_ID}
    bot.get_me.return_value = {"id": 9000}
    bot.get_chat_member.return_value = {"status": "administrator"}
    bot.send_message.return_value = {"message_id": 88}

    service.observe_update({"message": _root_message()})

    repo.create_contest.assert_called_once_with(
        chat_id=CHAT_ID,
        root_message_id=ROOT_ID,
        source_channel_id=CHANNEL_ID,
        source_channel_title="Official",
        source_channel_username=None,
        source_channel_post_id=7,
        created_at=100,
    )
    bot.send_message.assert_called_once_with(
        str(CHAT_ID),
        RULES_MESSAGE_KK,
        reply_to_message_id=ROOT_ID,
        link_preview_disable=True,
    )
    repo.activate_contest.assert_called_once_with(str(CHAT_ID), ROOT_ID, 88, attempt_id=ANY)


def test_unlinked_or_non_admin_root_never_opens_contest() -> None:
    service, repo, bot, _ = _service()
    bot.get_chat.return_value = {"linked_chat_id": -100999}

    service.observe_update({"message": _root_message()})

    repo.create_contest.assert_not_called()

    repo.reset_mock()
    bot.reset_mock()
    bot.get_chat.return_value = {"linked_chat_id": CHANNEL_ID}
    bot.get_me.return_value = {"id": 9000}
    bot.get_chat_member.return_value = {"status": "member"}
    repo.get_contest.return_value = None

    service.observe_update({"message": _root_message()})

    repo.create_contest.assert_not_called()
    bot.send_message.assert_called_once_with(CHAT_ID, BOT_ADMIN_REQUIRED_KK, reply_to_message_id=ROOT_ID)


def test_definite_rules_failure_marks_creation_failed() -> None:
    service, repo, bot, _ = _service()
    creating = {"chat_id": str(CHAT_ID), "root_message_id": ROOT_ID, "status": "CREATING"}
    repo.get_contest.side_effect = [None, creating]
    repo.create_contest.return_value = True
    bot.get_chat.return_value = {"linked_chat_id": CHANNEL_ID}
    bot.get_me.return_value = {"id": 9000}
    bot.get_chat_member.return_value = {"status": "administrator"}
    bot.send_message.side_effect = TelegramAPIError(400, "Bad Request: message to be replied not found")

    service.observe_update({"message": _root_message()})

    repo.fail_creation.assert_called_once_with(str(CHAT_ID), ROOT_ID, attempt_id=ANY)
    repo.activate_contest.assert_not_called()


def test_concurrent_creation_loser_never_sends_or_fails_winner_attempt() -> None:
    service, repo, bot, _ = _service()
    repo.begin_creation_attempt.return_value = False

    with pytest.raises(ContestRetryRequiredError):
        service._activate_creating({"chat_id": str(CHAT_ID), "root_message_id": ROOT_ID, "status": "CREATING"})

    bot.send_message.assert_not_called()
    repo.fail_creation.assert_not_called()
    repo.activate_contest.assert_not_called()


def test_transient_creation_delivery_failure_releases_lease_and_propagates_for_retry() -> None:
    service, repo, bot, _ = _service()
    repo.begin_creation_attempt.return_value = True
    bot.get_me.return_value = {"id": 9000}
    bot.get_chat_member.return_value = {"status": "administrator"}
    bot.send_message.side_effect = TelegramAPIError(429, "Too Many Requests")

    with pytest.raises(TelegramAPIError):
        service._activate_creating({"chat_id": str(CHAT_ID), "root_message_id": ROOT_ID, "status": "CREATING"})

    repo.release_creation_attempt.assert_called_once_with(str(CHAT_ID), ROOT_ID, attempt_id=ANY)
    repo.fail_creation.assert_not_called()


def test_first_direct_entry_is_stored_once_and_gets_check_reaction() -> None:
    service, repo, bot, _ = _service()
    repo.get_contest.return_value = {
        "chat_id": str(CHAT_ID),
        "root_message_id": ROOT_ID,
        "status": "OPEN",
    }
    repo.register_participant.return_value = RegistrationResult.REGISTERED

    service.observe_update({"message": _entry()})

    repo.register_participant.assert_called_once_with(
        chat_id=CHAT_ID,
        root_message_id=ROOT_ID,
        user_id=42,
        entry_message_id=12,
        username="user42",
        first_name="User",
        last_name="42",
        text="Мен ҚАТЫСАМЫН!",
        accepted_at=200,
    )
    bot.set_message_reaction.assert_called_once_with(CHAT_ID, 12, "🎉")

    bot.reset_mock()
    repo.register_participant.return_value = RegistrationResult.DUPLICATE
    service.observe_update({"message": _entry(message_id=13)})
    bot.set_message_reaction.assert_not_called()

    repo.register_participant.return_value = RegistrationResult.REPLAY
    service.observe_update({"message": _entry(message_id=12)})
    bot.set_message_reaction.assert_called_once_with(CHAT_ID, 12, "🎉")


def test_early_direct_entry_retries_until_original_root_activation_finishes() -> None:
    service, repo, bot, _ = _service()
    opened = {
        "chat_id": str(CHAT_ID),
        "root_message_id": ROOT_ID,
        "status": "OPEN",
        "rules_message_id": 88,
    }
    repo.register_participant.return_value = RegistrationResult.REGISTERED
    entry = _entry()
    entry["reply_to_message"] = _root_message()

    repo.get_contest.return_value = None
    with (
        patch("services.contest.time.time", return_value=200),
        pytest.raises(ContestRetryRequiredError),
    ):
        service.observe_update({"message": entry})

    repo.create_contest.assert_not_called()
    repo.register_participant.assert_not_called()

    repo.get_contest.return_value = opened
    service.observe_update({"message": entry})

    repo.register_participant.assert_called_once()
    bot.set_message_reaction.assert_called_once_with(CHAT_ID, 12, "🎉")


def test_backlogged_early_entry_still_retries_within_telegram_retention() -> None:
    service, repo, _, _ = _service()
    repo.get_contest.return_value = None
    entry = _entry()
    entry["reply_to_message"] = _root_message()

    with (
        patch(
            "services.contest.time.time",
            return_value=entry["date"] + TELEGRAM_UPDATE_RETENTION_SECONDS - 1,
        ),
        pytest.raises(ContestRetryRequiredError),
    ):
        service.observe_update({"message": entry})

    repo.create_contest.assert_not_called()
    repo.register_participant.assert_not_called()


def test_embedded_root_stops_retrying_after_telegram_retention() -> None:
    service, repo, _, _ = _service()
    repo.get_contest.return_value = None
    entry = _entry()
    entry["reply_to_message"] = _root_message()

    with patch(
        "services.contest.time.time",
        return_value=entry["date"] + TELEGRAM_UPDATE_RETENTION_SECONDS + 1,
    ):
        service.observe_update({"message": entry})

    repo.create_contest.assert_not_called()
    repo.register_participant.assert_not_called()


@pytest.mark.parametrize("root_mutation", ["edited", "historical"])
def test_embedded_root_never_backfills_edited_or_historical_post(root_mutation: str) -> None:
    service, repo, bot, _ = _service()
    repo.get_contest.return_value = None
    entry = _entry()
    root = _root_message()
    if root_mutation == "edited":
        root["edit_date"] = 150
    else:
        entry["date"] = 10_000
    entry["reply_to_message"] = root

    with patch("services.contest.time.time", return_value=10_000 if root_mutation == "historical" else 200):
        service.observe_update({"message": entry})

    repo.create_contest.assert_not_called()
    repo.register_participant.assert_not_called()
    bot.set_message_reaction.assert_not_called()


def test_first_draw_freezes_full_set_and_replies_to_saved_winner_comment() -> None:
    service, repo, bot, sqs = _service()
    one = _participant(1, 21)
    two = _participant(2, 22)
    open_contest = {"chat_id": str(CHAT_ID), "root_message_id": ROOT_ID, "status": "OPEN", "draw_count": 0}
    drawn = {
        **open_contest,
        "status": "DRAWN",
        "draw_count": 1,
        "frozen_participant_count": 2,
        "winner_user_ids": ["2"],
        "winners": [_winner(two, 1)],
        "announcement_state": "PENDING",
        "expires_at": 9_999_999_999,
        "ttl_sweep_status": "PENDING",
    }
    repo.get_contest.side_effect = [open_contest, drawn]
    repo.begin_first_draw.return_value = True
    repo.iter_participants.return_value = [one, two]
    repo.complete_draw.return_value = True
    bot.send_message.return_value = {"message_id": 901}

    with patch("services.contest.secrets.randbelow", side_effect=[0, 0]) as randbelow:
        service.draw(chat_id=CHAT_ID, root_message_id=ROOT_ID, command_message_id=30)

    assert randbelow.call_args_list == [call(1), call(2)]
    repo.complete_draw.assert_called_once_with(
        CHAT_ID,
        ROOT_ID,
        draw_number=1,
        attempt_id=ANY,
        participant=two,
        frozen_participant_count=2,
    )
    sent = bot.send_message.call_args
    assert sent.kwargs["reply_to_message_id"] == 22
    assert "Қатысушылар саны: <b>2</b>" in sent.args[1]
    assert "Ұтыс: <b>1/3</b>" in sent.args[1]
    repo.mark_announcement_sent.assert_called_once_with(
        str(CHAT_ID), ROOT_ID, draw_number=1, announcement_message_id=901
    )
    sqs.send_contest_ttl_sweep_task.assert_called_once_with(chat_id=CHAT_ID, root_message_id=ROOT_ID)


def test_zero_person_draw_reopens_and_keeps_contest_available() -> None:
    service, repo, bot, _ = _service()
    repo.get_contest.return_value = {
        "chat_id": str(CHAT_ID),
        "root_message_id": ROOT_ID,
        "status": "OPEN",
        "draw_count": 0,
    }
    repo.begin_first_draw.return_value = True
    repo.iter_participants.return_value = []

    service.draw(chat_id=CHAT_ID, root_message_id=ROOT_ID, command_message_id=30)

    repo.abort_draw.assert_called_once_with(CHAT_ID, ROOT_ID, draw_number=1, attempt_id=ANY)
    repo.complete_draw.assert_not_called()
    bot.send_message.assert_called_once_with(CHAT_ID, NO_PARTICIPANTS_KK, reply_to_message_id=30)


def test_one_person_draw_selects_the_only_participant_normally() -> None:
    service, repo, bot, _ = _service()
    only = _participant(1, 21)
    open_contest = {
        "chat_id": str(CHAT_ID),
        "root_message_id": ROOT_ID,
        "status": "OPEN",
        "participant_count": 1,
        "draw_count": 0,
    }
    drawn = {
        **open_contest,
        "status": "DRAWN",
        "draw_count": 1,
        "frozen_participant_count": 1,
        "winner_user_ids": ["1"],
        "winners": [_winner(only, 1)],
        "announcement_state": "PENDING",
        "expires_at": 9_999_999_999,
        "ttl_sweep_status": "PENDING",
    }
    repo.get_contest.side_effect = [open_contest, drawn]
    repo.begin_first_draw.return_value = True
    repo.iter_participants.return_value = [only]
    repo.complete_draw.return_value = True

    with patch("services.contest.secrets.randbelow", return_value=0) as randbelow:
        service.draw(chat_id=CHAT_ID, root_message_id=ROOT_ID, command_message_id=30)

    randbelow.assert_called_once_with(1)
    repo.complete_draw.assert_called_once_with(
        CHAT_ID,
        ROOT_ID,
        draw_number=1,
        attempt_id=ANY,
        participant=only,
        frozen_participant_count=1,
    )
    assert bot.send_message.call_args.kwargs["reply_to_message_id"] == 21


def test_drawing_crash_resumes_the_same_attempt_token() -> None:
    service, repo, _, _ = _service()
    only = _participant(1, 21)
    drawing = {
        "chat_id": str(CHAT_ID),
        "root_message_id": ROOT_ID,
        "status": "DRAWING",
        "draw_count": 0,
        "pending_draw_number": 1,
        "draw_attempt_id": "persisted-attempt",
    }
    drawn = {
        **drawing,
        "status": "DRAWN",
        "draw_count": 1,
        "frozen_participant_count": 1,
        "winner_user_ids": ["1"],
        "winners": [_winner(only, 1)],
        "announcement_state": "PENDING",
        "expires_at": 9_999_999_999,
        "ttl_sweep_status": "PENDING",
    }
    repo.get_contest.side_effect = [drawing, drawn]
    repo.iter_participants.return_value = [only]
    repo.complete_draw.return_value = True

    service.draw(chat_id=CHAT_ID, root_message_id=ROOT_ID, command_message_id=30)

    repo.begin_first_draw.assert_not_called()
    assert repo.complete_draw.call_args.kwargs["attempt_id"] == "persisted-attempt"


def test_same_attempt_completion_conflict_aborts_instead_of_sticking_drawing() -> None:
    service, repo, _, _ = _service()
    only = _participant(1, 21)
    open_contest = {
        "chat_id": str(CHAT_ID),
        "root_message_id": ROOT_ID,
        "status": "OPEN",
        "draw_count": 0,
    }
    still_drawing = {
        **open_contest,
        "status": "DRAWING",
        "pending_draw_number": 1,
        "draw_attempt_id": "fixed-attempt",
    }
    repo.get_contest.side_effect = [open_contest, still_drawing]
    repo.begin_first_draw.return_value = True
    repo.iter_participants.return_value = [only]
    repo.complete_draw.return_value = False

    with (
        patch("services.contest.secrets.token_hex", return_value="fixed-attempt"),
        patch("services.contest.secrets.randbelow", return_value=0),
        pytest.raises(RuntimeError, match="completion condition failed"),
    ):
        service.draw(chat_id=CHAT_ID, root_message_id=ROOT_ID, command_message_id=30)

    repo.abort_draw.assert_called_once_with(
        CHAT_ID,
        ROOT_ID,
        draw_number=1,
        attempt_id="fixed-attempt",
    )


def test_redraw_excludes_previous_winner_and_preserves_frozen_count() -> None:
    service, repo, bot, _ = _service()
    one = _participant(1, 21)
    two = _participant(2, 22)
    drawn_once = {
        "chat_id": str(CHAT_ID),
        "root_message_id": ROOT_ID,
        "status": "DRAWN",
        "draw_count": 1,
        "frozen_participant_count": 2,
        "winner_user_ids": ["1"],
        "winners": [_winner(one, 1)],
        "announcement_state": "SENT",
        "expires_at": 9_999_999_999,
    }
    drawn_twice = {
        **drawn_once,
        "draw_count": 2,
        "winner_user_ids": ["1", "2"],
        "winners": [_winner(one, 1), _winner(two, 2)],
        "announcement_state": "PENDING",
    }
    repo.get_contest.side_effect = [drawn_once, drawn_twice]
    repo.iter_participants.return_value = [one, two]
    repo.begin_redraw.return_value = True
    repo.complete_draw.return_value = True

    with patch("services.contest.secrets.randbelow", return_value=0) as randbelow:
        service.draw(chat_id=CHAT_ID, root_message_id=ROOT_ID, command_message_id=31, redraw=True)

    randbelow.assert_called_once_with(1)
    repo.complete_draw.assert_called_once_with(
        CHAT_ID,
        ROOT_ID,
        draw_number=2,
        attempt_id=ANY,
        participant=two,
        frozen_participant_count=2,
    )


def test_redraw_without_remaining_candidate_preserves_existing_winner() -> None:
    service, repo, bot, _ = _service()
    only = _participant(1, 21)
    drawn = {
        "chat_id": str(CHAT_ID),
        "root_message_id": ROOT_ID,
        "status": "DRAWN",
        "draw_count": 1,
        "frozen_participant_count": 1,
        "winner_user_ids": ["1"],
        "winners": [_winner(only, 1)],
        "announcement_state": "SENT",
        "expires_at": 9_999_999_999,
        "ttl_sweep_status": "COMPLETE",
    }
    repo.get_contest.return_value = drawn
    repo.begin_redraw.return_value = True
    repo.iter_participants.return_value = [only]

    service.draw(chat_id=CHAT_ID, root_message_id=ROOT_ID, command_message_id=31, redraw=True)

    repo.abort_draw.assert_called_once_with(
        CHAT_ID,
        ROOT_ID,
        draw_number=2,
        attempt_id=ANY,
    )
    repo.complete_draw.assert_not_called()
    bot.send_message.assert_called_once_with(
        CHAT_ID,
        NO_REMAINING_CANDIDATES_KK,
        reply_to_message_id=31,
    )


def test_redraw_crossing_fixed_expiry_aborts_before_selection_commit() -> None:
    service, repo, bot, _ = _service()
    one = _participant(1, 21)
    two = _participant(2, 22)
    contest = {
        "chat_id": str(CHAT_ID),
        "root_message_id": ROOT_ID,
        "status": "DRAWN",
        "draw_count": 1,
        "frozen_participant_count": 2,
        "winner_user_ids": ["1"],
        "winners": [_winner(one, 1)],
        "announcement_state": "SENT",
        "expires_at": 500,
    }
    repo.get_contest.return_value = contest
    repo.iter_participants.return_value = [one, two]
    repo.begin_redraw.return_value = True
    repo.is_logically_expired.side_effect = [False, True]

    service.draw(chat_id=CHAT_ID, root_message_id=ROOT_ID, command_message_id=31, redraw=True)

    repo.complete_draw.assert_not_called()
    repo.abort_draw.assert_called_once_with(CHAT_ID, ROOT_ID, draw_number=2, attempt_id=ANY)
    bot.send_message.assert_called_once_with(CHAT_ID, CONTEST_EXPIRED_KK, reply_to_message_id=31)


def test_pending_announcement_replays_same_winner_without_reselection() -> None:
    service, repo, bot, sqs = _service()
    one = _participant(1, 21)
    pending = {
        "chat_id": str(CHAT_ID),
        "root_message_id": ROOT_ID,
        "status": "DRAWN",
        "draw_count": 1,
        "frozen_participant_count": 1,
        "winner_user_ids": ["1"],
        "winners": [_winner(one, 1)],
        "announcement_state": "PENDING",
        "expires_at": 9_999_999_999,
        "ttl_sweep_status": "PENDING",
    }
    repo.get_contest.return_value = pending

    with patch("services.contest.secrets.randbelow") as randbelow:
        service.draw(chat_id=CHAT_ID, root_message_id=ROOT_ID, command_message_id=31, redraw=True)

    randbelow.assert_not_called()
    repo.begin_redraw.assert_not_called()
    assert bot.send_message.call_args_list[0].kwargs["reply_to_message_id"] == 21
    assert bot.send_message.call_args_list[1].kwargs["reply_to_message_id"] == 31
    sqs.send_contest_ttl_sweep_task.assert_called_once_with(chat_id=CHAT_ID, root_message_id=ROOT_ID)


def test_first_ttl_enqueue_failure_does_not_block_persisted_winner_announcement() -> None:
    service, repo, bot, sqs = _service()
    only = _participant(1, 21)
    open_contest = {
        "chat_id": str(CHAT_ID),
        "root_message_id": ROOT_ID,
        "status": "OPEN",
        "draw_count": 0,
    }
    drawn = {
        **open_contest,
        "status": "DRAWN",
        "draw_count": 1,
        "frozen_participant_count": 1,
        "winner_user_ids": ["1"],
        "winners": [_winner(only, 1)],
        "announcement_state": "PENDING",
        "expires_at": 9_999_999_999,
        "ttl_sweep_status": "PENDING",
    }
    repo.get_contest.side_effect = [open_contest, drawn]
    repo.begin_first_draw.return_value = True
    repo.iter_participants.return_value = [only]
    repo.complete_draw.return_value = True
    sqs.send_contest_ttl_sweep_task.side_effect = RuntimeError("SQS unavailable")

    service.draw(chat_id=CHAT_ID, root_message_id=ROOT_ID, command_message_id=30)

    repo.complete_draw.assert_called_once()
    repo.mark_announcement_sent.assert_called_once_with(
        str(CHAT_ID),
        ROOT_ID,
        draw_number=1,
        announcement_message_id=999,
    )
    assert bot.send_message.call_args.kwargs["reply_to_message_id"] == 21


def test_repeated_cancel_recovers_missed_ttl_enqueue_without_extending_expiry() -> None:
    service, repo, bot, sqs = _service()
    cancelled = {
        "chat_id": str(CHAT_ID),
        "root_message_id": ROOT_ID,
        "status": "CANCELLED",
        "expires_at": 9_999_999_999,
        "ttl_sweep_status": "PENDING",
    }
    repo.get_contest.return_value = cancelled
    repo.cancel_contest.return_value = None

    service.cancel(chat_id=CHAT_ID, root_message_id=ROOT_ID, command_message_id=32)

    sqs.send_contest_ttl_sweep_task.assert_called_once_with(chat_id=CHAT_ID, root_message_id=ROOT_ID)
    repo.cancel_contest.assert_called_once_with(CHAT_ID, ROOT_ID)
    assert bot.send_message.call_args.kwargs["reply_to_message_id"] == 32


def test_status_is_independent_from_cleanup_queue_availability() -> None:
    service, repo, bot, sqs = _service()
    repo.get_contest.return_value = {
        "chat_id": str(CHAT_ID),
        "root_message_id": ROOT_ID,
        "status": "DRAWN",
        "draw_count": 1,
        "frozen_participant_count": 7,
        "expires_at": 9_999_999_999,
        "ttl_sweep_status": "PENDING",
    }
    sqs.send_contest_ttl_sweep_task.side_effect = RuntimeError("SQS unavailable")

    service.status(chat_id=CHAT_ID, root_message_id=ROOT_ID, command_message_id=33)

    sqs.send_contest_ttl_sweep_task.assert_not_called()
    assert "Бірегей қатысушылар: <b>7</b>" in bot.send_message.call_args.args[1]


def test_deleted_winner_comment_falls_back_to_root_with_safe_bounded_snapshot() -> None:
    service, repo, bot, _ = _service()
    participant = _participant(1, 21)
    participant.pop("username")
    participant["first_name"] = "&" * 200
    participant["last_name"] = '"' * 200
    participant["text"] = '"' * (4096 - len(ENTRY_PHRASE)) + ENTRY_PHRASE
    winner = _winner(participant, 1)
    contest = {
        "chat_id": str(CHAT_ID),
        "root_message_id": ROOT_ID,
        "status": "DRAWN",
        "draw_count": 1,
        "frozen_participant_count": 1,
        "winners": [winner],
        "announcement_state": "PENDING",
    }
    bot.send_message.side_effect = [
        TelegramAPIError(400, "Bad Request: message to be replied not found"),
        {"message_id": 902},
    ]

    service._announce_winner(contest, winner)

    assert bot.send_message.call_args_list[0].kwargs["reply_to_message_id"] == 21
    fallback = bot.send_message.call_args_list[1]
    assert fallback.kwargs["reply_to_message_id"] == ROOT_ID
    assert "&quot;" in fallback.args[1]
    assert ENTRY_PHRASE in fallback.args[1].casefold()
    assert len(fallback.args[1]) < 4096
    repo.mark_announcement_sent.assert_called_once()


def test_missing_winner_and_root_marks_terminal_orphan_without_unanchored_send() -> None:
    service, repo, bot, _ = _service()
    winner = _winner(_participant(1, 21), 1)
    contest = {
        "chat_id": str(CHAT_ID),
        "root_message_id": ROOT_ID,
        "status": "DRAWN",
        "draw_count": 1,
        "frozen_participant_count": 1,
        "winners": [winner],
        "announcement_state": "PENDING",
    }
    missing = TelegramAPIError(400, "Bad Request: message to be replied not found")
    bot.send_message.side_effect = [missing, missing]

    with pytest.raises(AnnouncementOrphanedError):
        service._announce_winner(contest, winner)

    assert bot.send_message.call_args_list == [
        call(
            str(CHAT_ID),
            bot.send_message.call_args_list[0].args[1],
            reply_to_message_id=21,
            link_preview_disable=True,
        ),
        call(
            str(CHAT_ID),
            bot.send_message.call_args_list[1].args[1],
            reply_to_message_id=ROOT_ID,
            link_preview_disable=True,
        ),
    ]
    repo.mark_orphaned.assert_called_once_with(str(CHAT_ID), ROOT_ID, draw_number=1)


def test_ttl_sweep_persists_cursor_before_requeue_and_finishes_alias_last() -> None:
    _, repo, _, sqs = _service()
    worker = ContestTTLWorker(repo, sqs)
    contest = {
        "chat_id": str(CHAT_ID),
        "root_message_id": ROOT_ID,
        "rules_message_id": 88,
        "expires_at": 999,
        "ttl_sweep_status": "PENDING",
    }
    page = [{"pk": "CHAT#-100123", "sk": "participant"}]
    cursor = {"pk": "CHAT#-100123", "sk": "participant"}
    repo.get_contest.return_value = contest
    repo.participant_page.return_value = (page, cursor)

    worker.process({"chat_id": CHAT_ID, "root_message_id": ROOT_ID})

    repo.stamp_participant_ttl.assert_called_once_with(page, 999)
    repo.record_ttl_sweep_progress.assert_called_once_with(
        CHAT_ID,
        ROOT_ID,
        expected_start_key=None,
        expected_version=0,
        next_start_key=cursor,
    )
    sqs.send_contest_ttl_sweep_task.assert_called_once_with(chat_id=CHAT_ID, root_message_id=ROOT_ID)
    repo.complete_ttl_sweep.assert_not_called()

    repo.reset_mock()
    sqs.reset_mock()
    repo.get_contest.return_value = contest
    repo.participant_page.return_value = (page, None)
    worker.process({"chat_id": CHAT_ID, "root_message_id": ROOT_ID})
    repo.complete_ttl_sweep.assert_called_once_with(
        CHAT_ID,
        ROOT_ID,
        rules_message_id=88,
        expires_at=999,
        expected_start_key=None,
        expected_version=0,
    )


def test_stale_ttl_worker_does_not_enqueue_a_regressed_cursor() -> None:
    _, repo, _, sqs = _service()
    worker = ContestTTLWorker(repo, sqs)
    repo.get_contest.return_value = {
        "chat_id": str(CHAT_ID),
        "root_message_id": ROOT_ID,
        "expires_at": 999,
        "ttl_sweep_status": "PENDING",
        "ttl_sweep_version": 2,
        "ttl_sweep_cursor": {"pk": "CHAT#-100123", "sk": "current"},
    }
    repo.participant_page.return_value = (
        [{"pk": "CHAT#-100123", "sk": "participant"}],
        {"pk": "CHAT#-100123", "sk": "next"},
    )
    repo.record_ttl_sweep_progress.return_value = False

    worker.process({"chat_id": CHAT_ID, "root_message_id": ROOT_ID})

    sqs.send_contest_ttl_sweep_task.assert_not_called()


def test_contest_ttl_queue_payload_uses_dynamo_cursor_as_single_truth() -> None:
    sqs = SQSClient.__new__(SQSClient)
    sqs.queue_url = "queue-url"
    sqs.vector_queue_url = "vector-url"
    sqs_client = MagicMock()
    sqs.__dict__["sqs_client"] = sqs_client
    with patch.object(SQSClient, "sqs_client", sqs_client):
        sqs.send_contest_ttl_sweep_task(
            chat_id=CHAT_ID,
            root_message_id=ROOT_ID,
        )

    payload = json.loads(sqs_client.send_message.call_args.kwargs["MessageBody"])
    assert payload == {
        "task_type": "PROCESS_CONTEST_TTL_SWEEP",
        "chat_id": CHAT_ID,
        "root_message_id": ROOT_ID,
    }


def test_ttl_recovery_replays_one_bounded_outbox_page_then_enqueues_continuation() -> None:
    repo = MagicMock()
    sqs = MagicMock()
    cursor = {
        "pk": "CONTEST_TTL_OUTBOX",
        "sk": "CHAT#-100123#ROOT#0000000000011",
    }
    repo.ttl_outbox_page.return_value = (
        [{"chat_id": str(CHAT_ID), "root_message_id": ROOT_ID}],
        cursor,
    )

    process_contest_ttl_recovery_task({}, repo=repo, sqs_repo=sqs)

    repo.ttl_outbox_page.assert_called_once_with(limit=100, start_key=None)
    sqs.send_contest_ttl_sweep_task.assert_called_once_with(
        chat_id=CHAT_ID,
        root_message_id=ROOT_ID,
    )
    sqs.send_contest_ttl_recovery_task.assert_called_once_with(start_key=cursor)


def test_ttl_recovery_resumes_supplied_cursor_and_stops_at_last_page() -> None:
    repo = MagicMock()
    sqs = MagicMock()
    cursor = {
        "pk": "CONTEST_TTL_OUTBOX",
        "sk": "CHAT#-100123#ROOT#0000000000011",
    }
    repo.ttl_outbox_page.return_value = ([], None)

    process_contest_ttl_recovery_task(
        {"start_key": cursor},
        repo=repo,
        sqs_repo=sqs,
    )

    repo.ttl_outbox_page.assert_called_once_with(limit=100, start_key=cursor)
    sqs.send_contest_ttl_sweep_task.assert_not_called()
    sqs.send_contest_ttl_recovery_task.assert_not_called()


def test_daily_ttl_recovery_send_failure_bubbles_without_consuming_marker() -> None:
    repo = MagicMock()
    sqs = MagicMock()
    repo.ttl_outbox_page.return_value = (
        [{"chat_id": str(CHAT_ID), "root_message_id": ROOT_ID}],
        None,
    )
    sqs.send_contest_ttl_sweep_task.side_effect = RuntimeError("SQS unavailable")

    with pytest.raises(RuntimeError, match="SQS unavailable"):
        process_contest_ttl_recovery_task({}, repo=repo, sqs_repo=sqs)

    repo.ttl_outbox_page.assert_called_once_with(limit=100, start_key=None)


def test_contest_ttl_recovery_queue_payload_carries_only_its_page_cursor() -> None:
    sqs = SQSClient.__new__(SQSClient)
    sqs.queue_url = "queue-url"
    sqs.vector_queue_url = "vector-url"
    sqs_client = MagicMock()
    sqs.__dict__["sqs_client"] = sqs_client
    cursor = {
        "pk": "CONTEST_TTL_OUTBOX",
        "sk": "CHAT#-100123#ROOT#0000000000011",
    }

    with patch.object(SQSClient, "sqs_client", sqs_client):
        sqs.send_contest_ttl_recovery_task(start_key=cursor)

    assert json.loads(sqs_client.send_message.call_args.kwargs["MessageBody"]) == {
        "task_type": "PROCESS_CONTEST_TTL_RECOVERY",
        "start_key": cursor,
    }
