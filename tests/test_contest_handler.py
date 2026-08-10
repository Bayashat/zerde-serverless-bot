"""Dispatcher-level contest command and authorization tests."""

from unittest.mock import MagicMock, patch

import pytest
from core.dispatcher import Dispatcher
from services.contest import (
    ADMIN_ONLY_KK,
    OWNER_ONLY_KK,
    PERSONAL_ACCOUNT_REQUIRED_KK,
    REPLY_ANCHOR_REQUIRED_KK,
    ContestRetryRequiredError,
)
from services.handlers import register_handlers

CHAT_ID = -100123
ROOT_ID = 11
RULES_ID = 88


def _dispatcher(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo, contest_repo):
    dispatcher = Dispatcher(
        mock_bot,
        mock_stats_repo,
        mock_sqs_repo,
        mock_vote_repo,
        contest_repo=contest_repo,
    )
    register_handlers(dispatcher)
    return dispatcher


def _command(action: str, *, anchor: int = ROOT_ID, sender_chat: dict | None = None) -> dict:
    message = {
        "message_id": 30,
        "text": f"/contest {action}",
        "chat": {"id": CHAT_ID, "type": "supergroup"},
        "from": {"id": 42, "is_bot": False, "first_name": "Owner"},
        "reply_to_message": {"message_id": anchor},
    }
    if sender_chat:
        message["sender_chat"] = sender_chat
    return {"message": message}


def test_creator_can_draw_via_rules_alias(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo) -> None:
    repo = MagicMock()
    repo.resolve_contest_by_anchor.return_value = {
        "chat_id": str(CHAT_ID),
        "root_message_id": ROOT_ID,
        "status": "OPEN",
    }
    mock_bot.get_chat_member.return_value = {"status": "creator"}
    dispatcher = _dispatcher(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo, repo)

    with patch("services.handlers.contest.ContestService.draw") as draw:
        dispatcher.process_update(_command("draw", anchor=RULES_ID))

    repo.resolve_contest_by_anchor.assert_called_once_with(CHAT_ID, RULES_ID)
    draw.assert_called_once_with(
        chat_id=CHAT_ID,
        root_message_id=ROOT_ID,
        command_message_id=30,
    )


def test_administrator_can_view_status_but_cannot_draw(
    mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo
) -> None:
    repo = MagicMock()
    repo.resolve_contest_by_anchor.return_value = {"root_message_id": ROOT_ID, "status": "OPEN"}
    mock_bot.get_chat_member.return_value = {"status": "administrator"}
    dispatcher = _dispatcher(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo, repo)

    with patch("services.handlers.contest.ContestService.status") as status:
        dispatcher.process_update(_command("status"))
    status.assert_called_once()

    mock_bot.send_message.reset_mock()
    with patch("services.handlers.contest.ContestService.draw") as draw:
        dispatcher.process_update(_command("draw"))
    draw.assert_not_called()
    mock_bot.send_message.assert_called_once_with(
        CHAT_ID,
        OWNER_ONLY_KK,
        reply_markup=None,
        reply_to_message_id=30,
        link_preview_disable=None,
    )


def test_member_cannot_view_status(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo) -> None:
    repo = MagicMock()
    repo.resolve_contest_by_anchor.return_value = {"root_message_id": ROOT_ID, "status": "OPEN"}
    mock_bot.get_chat_member.return_value = {"status": "member"}
    dispatcher = _dispatcher(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo, repo)

    dispatcher.process_update(_command("status"))

    mock_bot.send_message.assert_called_once_with(
        CHAT_ID,
        ADMIN_ONLY_KK,
        reply_markup=None,
        reply_to_message_id=30,
        link_preview_disable=None,
    )


def test_anonymous_sender_and_wrong_reply_anchor_are_rejected(
    mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo
) -> None:
    repo = MagicMock()
    dispatcher = _dispatcher(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo, repo)

    dispatcher.process_update(_command("draw", sender_chat={"id": CHAT_ID, "type": "supergroup"}))
    mock_bot.send_message.assert_called_once_with(
        CHAT_ID,
        PERSONAL_ACCOUNT_REQUIRED_KK,
        reply_markup=None,
        reply_to_message_id=30,
        link_preview_disable=None,
    )
    mock_bot.get_chat_member.assert_not_called()

    mock_bot.send_message.reset_mock()
    repo.resolve_contest_by_anchor.return_value = None
    dispatcher.process_update(_command("draw", anchor=999))
    mock_bot.send_message.assert_called_once_with(
        CHAT_ID,
        REPLY_ANCHOR_REQUIRED_KK,
        reply_markup=None,
        reply_to_message_id=30,
        link_preview_disable=None,
    )
    mock_bot.get_chat_member.assert_not_called()


def test_transient_anchor_lookup_failure_requests_webhook_redelivery(
    mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo
) -> None:
    repo = MagicMock()
    repo.resolve_contest_by_anchor.side_effect = RuntimeError("DynamoDB unavailable")
    dispatcher = _dispatcher(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo, repo)

    with pytest.raises(ContestRetryRequiredError):
        dispatcher.process_update(_command("draw"))

    mock_bot.send_message.assert_not_called()
    mock_bot.get_chat_member.assert_not_called()
