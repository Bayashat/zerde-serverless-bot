"""Tests for dispatcher routing logic."""

from core.dispatcher import Dispatcher


def test_command_routing(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo):
    """Commands should route to the correct registered handler."""
    dp = Dispatcher(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo)

    handler_called = {}

    @dp.command("start")
    def handle_start(ctx):
        handler_called["start"] = True

    @dp.command("help")
    def handle_help(ctx):
        handler_called["help"] = True

    update = {
        "message": {
            "message_id": 1,
            "from": {"id": 123, "first_name": "Test", "language_code": "en"},
            "chat": {"id": -100123, "type": "supergroup"},
            "text": "/start",
        }
    }

    dp.process_update(update)
    assert handler_called.get("start") is True
    assert "help" not in handler_called


def test_callback_query_routing(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo):
    """Callback queries should route to callback handler with membership check."""
    dp = Dispatcher(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo)

    callback_received = {}

    @dp.on_callback_query
    def handle_cb(ctx):
        callback_received["data"] = ctx.callback_data

    update = {
        "callback_query": {
            "id": "cb_123",
            "from": {"id": 456, "first_name": "Test", "language_code": "en"},
            "message": {
                "message_id": 10,
                "chat": {"id": -100123, "type": "supergroup"},
            },
            "data": "verify_456",
        }
    }

    # Mock: user IS a member
    mock_bot.get_chat_member.return_value = {"status": "member"}
    dp.process_update(update)
    assert callback_received.get("data") == "verify_456"


def test_callback_query_non_member_blocked(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo):
    """Callback queries from non-members should be blocked."""
    dp = Dispatcher(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo)

    callback_received = {}

    @dp.on_callback_query
    def handle_cb(ctx):
        callback_received["called"] = True

    update = {
        "callback_query": {
            "id": "cb_789",
            "from": {"id": 789, "first_name": "Outsider", "language_code": "en"},
            "message": {
                "message_id": 10,
                "chat": {"id": -100123, "type": "supergroup"},
            },
            "data": "voteban_for_999",
        }
    }

    # Mock: user is NOT a member
    mock_bot.get_chat_member.return_value = {"status": "left"}
    dp.process_update(update)
    assert "called" not in callback_received
    mock_bot.answer_callback_query.assert_called_once()


def test_new_chat_members_routing(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo):
    """New chat member events should route to the registered handler."""
    dp = Dispatcher(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo)

    new_member_called = {}

    @dp.on_new_chat_members
    def handle_new(ctx):
        new_member_called["triggered"] = True

    update = {
        "message": {
            "message_id": 5,
            "from": {"id": 111, "first_name": "Joiner", "language_code": "en"},
            "chat": {"id": -100123, "type": "supergroup"},
            "new_chat_members": [{"id": 222, "first_name": "NewUser", "is_bot": False}],
        }
    }

    dp.process_update(update)
    assert new_member_called.get("triggered") is True


def test_unknown_command_ignored(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo):
    """Unregistered commands should be silently ignored."""
    dp = Dispatcher(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo)

    @dp.command("start")
    def handle_start(ctx):
        pass

    update = {
        "message": {
            "message_id": 1,
            "from": {"id": 123, "first_name": "Test", "language_code": "en"},
            "chat": {"id": -100123, "type": "supergroup"},
            "text": "/nonexistent",
        }
    }

    # Should not raise
    dp.process_update(update)


def test_document_message_routing(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo):
    """Standalone document updates should hit the document handler (after command check)."""
    dp = Dispatcher(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo)

    doc_called = {}

    @dp.on_document_message
    def handle_doc(ctx):
        doc_called["file_id"] = ctx.message["document"]["file_id"]

    update = {
        "update_id": 9001,
        "message": {
            "message_id": 3,
            "from": {"id": 123, "first_name": "Test", "language_code": "en"},
            "chat": {"id": -100123, "type": "supergroup"},
            "document": {"file_id": "QQQ", "mime_type": "application/pdf", "file_size": 50},
        },
    }

    dp.process_update(update)
    assert doc_called.get("file_id") == "QQQ"


def test_caption_command_routes_before_document(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo):
    """Caption starting with / should be treated as a command, not document-auto."""
    dp = Dispatcher(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo)

    cmd_called = {}
    doc_called = {}

    @dp.command("start")
    def handle_start(ctx):
        cmd_called["yes"] = True

    @dp.on_document_message
    def handle_doc(ctx):
        doc_called["yes"] = True

    update = {
        "update_id": 9002,
        "message": {
            "message_id": 4,
            "from": {"id": 123, "first_name": "Test", "language_code": "en"},
            "chat": {"id": -100123, "type": "supergroup"},
            "caption": "/start",
            "document": {"file_id": "ZZZ", "mime_type": "application/pdf", "file_size": 10},
        },
    }

    dp.process_update(update)
    assert cmd_called.get("yes") is True
    assert "yes" not in doc_called
