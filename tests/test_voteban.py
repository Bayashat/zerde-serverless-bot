"""Voteban lifecycle through the real DynamoDB resource SDK and synthetic Telegram only."""

from unittest.mock import MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError
from core.dispatcher import Context
from moto import mock_aws
from services.handlers import voteban as handler
from services.repositories import votes
from services.telegram import TelegramAPIError, TelegramClient

CHAT = -100123
TARGET = 42
NOW = 1800000000


@pytest.fixture
def clock(monkeypatch):
    value = [NOW]
    monkeypatch.setattr(votes.time, "time", lambda: value[0])
    return value


@pytest.fixture
def repo(monkeypatch, clock):
    with mock_aws():
        resource = boto3.resource(
            "dynamodb", region_name="eu-central-1", aws_access_key_id="fake", aws_secret_access_key="fake"
        )
        resource.create_table(
            TableName="vote-test-stats",
            KeySchema=[{"AttributeName": "stat_key", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "stat_key", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setattr(votes, "get_dynamodb", lambda: resource)
        monkeypatch.setattr(votes, "STATS_TABLE_NAME", "vote-test-stats")
        yield votes.VoteRepository()


@pytest.fixture
def bot():
    client = MagicMock()
    client.get_chat_member.return_value = {"status": "member"}
    client.send_message.return_value = {"message_id": 777}
    client.edit_message_text.side_effect = lambda chat, mid, *args, **kwargs: {"message_id": mid}
    return client


def create(repo, *, command=10, date=NOW, initiator=1):
    return repo.create_vote_session(
        chat_id=CHAT,
        chat_type="supergroup",
        target_user_id=TARGET,
        command_message_id=command,
        command_date=date,
        reply_message_id=5,
        initiator_user_id=initiator,
        target_first_name="Target",
        initiator_first_name="Voter",
    )


def opened(repo):
    session = create(repo)
    owner, session = repo.claim(CHAT, TARGET, session["generation"])
    repo.bind_message(session, owner, 777, for_threshold=5)
    repo.release(session, owner)
    return repo.get_vote_session(CHAT, TARGET)


def vote(repo, session, voter, *, yes=True, ban=5, forgive=3, chat=CHAT, message=777, generation=None):
    return repo.add_vote(
        chat,
        TARGET,
        voter,
        yes,
        generation=generation or session["generation"],
        sent_message_id=message,
        for_threshold=ban,
        against_threshold=forgive,
    )


def command_ctx(repo, bot, *, message_id=10, date=NOW):
    return Context(
        {
            "message": {
                "message_id": message_id,
                "date": date,
                "chat": {"id": CHAT, "type": "supergroup"},
                "from": {"id": 1, "first_name": "Voter"},
                "text": "/voteban",
                "reply_to_message": {"message_id": 5, "from": {"id": TARGET, "first_name": "Target"}},
            }
        },
        bot,
        vote_repo=repo,
    )


def callback_ctx(repo, bot, session, *, voter=2, yes=True, message=777, generation=None):
    return Context(
        {
            "callback_query": {
                "id": "callback",
                "from": {"id": voter, "first_name": "Voter"},
                "message": {"message_id": message, "chat": {"id": CHAT, "type": "supergroup"}},
                "data": f'voteban_{"for" if yes else "against"}_{TARGET}:' f'{generation or session["generation"]}',
            }
        },
        bot,
        vote_repo=repo,
    )


def pending(repo):
    session = opened(repo)
    for voter in (2, 3, 4, 5):
        session, _ = vote(repo, session, voter)
    return session


def counter(repo):
    return repo._table.get_item(Key={"stat_key": str(CHAT)}).get("Item", {}).get("total_bans", 0)


def test_create_and_repeated_commands_keep_the_original_votes(repo):
    session = opened(repo)
    vote(repo, session, 2)
    assert create(repo, command=11, initiator=3)["votes_for"] == [1, 2]
    assert create(repo)["generation"] == session["generation"]


def test_creation_race_does_not_overwrite_winner(repo, monkeypatch):
    real_get = repo.get_vote_session
    entered = []

    def interleaved(*args):
        if not entered:
            entered.append(True)
            winner = create(repo, command=11, initiator=3)
            entered.append(winner["generation"])
            return {}
        return real_get(*args)

    monkeypatch.setattr(repo, "get_vote_session", interleaved)
    loser = create(repo)
    assert loser["generation"] == entered[1]
    assert loser["votes_for"] == [3]


@pytest.mark.parametrize("field,value", [("chat", -100999), ("message", 999), ("generation", "f" * 16)])
def test_wrong_scope_or_button_identity_cannot_create_or_change_rows(repo, field, value):
    session = opened(repo)
    with pytest.raises(votes.VoteSessionError):
        vote(repo, session, 2, **{field: value})
    assert repo.get_vote_session(CHAT, TARGET) == session
    assert repo._table.scan()["Count"] == 1


def test_logical_expiry_rejects_votes_before_ttl_removal_and_new_generation_fences_old(repo, clock):
    session = opened(repo)
    clock[0] = int(session["expires_at"])
    with pytest.raises(votes.VoteSessionError):
        vote(repo, session, 2)
    current = create(repo, command=20, date=clock[0])
    assert current["generation"] != session["generation"]
    with pytest.raises(votes.VoteSessionError):
        vote(repo, session, 3)
    assert repo.get_vote_session(CHAT, TARGET) == current


def test_duplicate_voter_cannot_switch_sides(repo):
    session = opened(repo)
    _, verdict = vote(repo, session, 1, yes=False)
    assert verdict == "already_voted"
    assert repo.get_vote_session(CHAT, TARGET) == session


def test_first_threshold_cas_wins_even_when_opposite_vote_read_stale_state(repo, monkeypatch):
    session = opened(repo)
    real_get = repo.get_vote_session
    first = []

    def stale_read(*args):
        snapshot = real_get(*args)
        if not first:
            first.append(True)
            vote(repo, session, 2, yes=False, forgive=1)
        return snapshot

    monkeypatch.setattr(repo, "get_vote_session", stale_read)
    result, verdict = vote(repo, session, 3, ban=2)
    assert verdict == "pending"
    assert result["status"] == "FORGIVE_PENDING"
    assert result["votes_for"] == [1] and result["votes_against"] == [2]
    assert "ttl" not in result


def test_confirmation_transaction_commits_once_and_fences_old_owner(repo):
    session = pending(repo)
    owner, session = repo.claim(CHAT, TARGET, session["generation"])
    with pytest.raises(ClientError):
        repo.confirm_ban(session, "wrong-owner")
    assert counter(repo) == 0
    repo.confirm_ban(session, owner)
    with pytest.raises(ClientError):
        repo.confirm_ban(session, owner)
    assert repo.get_vote_session(CHAT, TARGET)["status"] == "BANNED"
    assert counter(repo) == 1


def test_terminal_receipt_prevents_old_command_reopening_and_stale_date_survives_physical_deletion(repo, bot, clock):
    session = pending(repo)
    handler._resume(command_ctx(repo, bot), session)
    terminal = repo.get_vote_session(CHAT, TARGET)
    assert terminal["effects_complete"] is True
    assert create(repo)["generation"] == session["generation"]
    assert create(repo, command=11)["generation"] != session["generation"]
    repo._table.delete_item(Key=repo._key(CHAT, TARGET))
    clock[0] += 8 * 86400
    with pytest.raises(votes.VoteSessionError):
        create(repo)
    assert repo.get_vote_session(CHAT, TARGET) == {}


def test_lease_blocks_overlapping_effects_and_old_owner_cannot_mutate_after_takeover(repo, clock):
    session = opened(repo)
    owner, session = repo.claim(CHAT, TARGET, session["generation"])
    with pytest.raises(votes.VoteBusyError):
        repo.claim(CHAT, TARGET, session["generation"])
    clock[0] += 361
    new_owner, _ = repo.claim(CHAT, TARGET, session["generation"])
    with pytest.raises(ClientError):
        repo.update_effects(session, owner, {"status": "FORGIVEN"})
    repo.release(session, owner)
    assert repo.get_vote_session(CHAT, TARGET)["lease_owner"] == new_owner


@pytest.mark.parametrize("ttl", [None, NOW + 100])
def test_active_legacy_rows_are_not_overwritten(repo, ttl):
    row = {**repo._key(CHAT, TARGET), "votes_for": {1}}
    if ttl is not None:
        row["ttl"] = ttl
    repo._table.put_item(Item=row)
    with pytest.raises(votes.VoteSessionError):
        create(repo)
    assert repo.get_vote_session(CHAT, TARGET) == row


def test_expired_legacy_session_can_be_replaced(repo):
    repo._table.put_item(Item={**repo._key(CHAT, TARGET), "ttl": NOW - 1})
    assert create(repo)["schema_version"] == 2


def test_publication_binds_identity_before_installing_buttons_and_failed_bind_leaves_inert_message(
    repo, bot, monkeypatch
):
    actual_bind = repo.bind_message
    monkeypatch.setattr(repo, "bind_message", MagicMock(side_effect=RuntimeError("synthetic DB failure")))
    handler.handle_voteban_command(command_ctx(repo, bot))
    creating = repo.get_vote_session(CHAT, TARGET)
    assert creating["status"] == "CREATING" and creating["sent_message_id"] == 0
    bot.edit_message_text.assert_not_called()
    assert all(not call.kwargs.get("reply_markup") for call in bot.send_message.call_args_list)
    monkeypatch.setattr(repo, "bind_message", actual_bind)

    def render(chat, mid, *args, **kwargs):
        bound = repo.get_vote_session(CHAT, TARGET)
        assert bound["status"] == "OPEN" and bound["sent_message_id"] == mid
        assert bound["generation"] in kwargs["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
        return {"message_id": mid}

    bot.edit_message_text.side_effect = render
    handler.handle_voteban_command(command_ctx(repo, bot))
    assert repo.get_vote_session(CHAT, TARGET)["generation"] == creating["generation"]
    bot.edit_message_text.assert_called_once()


@pytest.mark.parametrize("data", ["voteban_for_42", "voteban_for_x:abcdef", "voteban_for_-42:" + "a" * 16])
def test_unversioned_or_malformed_callback_is_inert(repo, bot, data):
    session = opened(repo)
    ctx = callback_ctx(repo, bot, session)
    ctx.callback_data = data
    handler.handle_vote_callback(ctx)
    assert repo.get_vote_session(CHAT, TARGET) == session
    bot.kick_chat_member.assert_not_called()
    bot.edit_message_text.assert_not_called()


def test_confirmed_ban_replay_recovers_cleanup_without_repeating_ban_or_counter(repo, bot):
    session = pending(repo)
    bot.delete_message.side_effect = [RuntimeError("synthetic delete failure"), None, None]
    ctx = callback_ctx(repo, bot, session, voter=1)
    handler.handle_vote_callback(ctx)
    assert repo.get_vote_session(CHAT, TARGET)["status"] == "BANNED"
    assert counter(repo) == 1
    handler.handle_vote_callback(ctx)
    assert repo.get_vote_session(CHAT, TARGET)["effects_complete"] is True
    assert bot.kick_chat_member.call_count == 1 and counter(repo) == 1
    assert bot.send_message.call_count == 1
    assert [c.args[1] for c in bot.delete_message.call_args_list] == [777, 777, 5]
    assert all(c.kwargs["ignore_not_found"] for c in bot.delete_message.call_args_list)


def test_lost_ban_acknowledgement_is_unconfirmed_without_false_counter(repo, bot):
    session = pending(repo)
    bot.kick_chat_member.side_effect = RuntimeError("synthetic lost acknowledgement")
    ctx = callback_ctx(repo, bot, session, voter=1)
    handler.handle_vote_callback(ctx)
    assert repo.get_vote_session(CHAT, TARGET)["status"] == "BAN_PENDING"
    bot.get_chat_member.return_value = {"status": "kicked"}
    handler.handle_vote_callback(ctx)
    outcome = repo.get_vote_session(CHAT, TARGET)
    assert outcome["status"] == "UNCONFIRMED" and outcome["effects_complete"]
    assert counter(repo) == 0 and bot.kick_chat_member.call_count == 1
    assert [c.args[1] for c in bot.delete_message.call_args_list] == [777]


def test_database_failure_after_api_success_cannot_double_count(repo, bot, monkeypatch):
    session = pending(repo)
    actual_confirm = repo.confirm_ban
    monkeypatch.setattr(repo, "confirm_ban", MagicMock(side_effect=RuntimeError("synthetic DB outage")))
    ctx = callback_ctx(repo, bot, session, voter=1)
    handler.handle_vote_callback(ctx)
    assert counter(repo) == 0
    monkeypatch.setattr(repo, "confirm_ban", actual_confirm)
    bot.get_chat_member.return_value = {"status": "kicked"}
    handler.handle_vote_callback(ctx)
    assert repo.get_vote_session(CHAT, TARGET)["status"] == "UNCONFIRMED"
    assert counter(repo) == 0 and bot.kick_chat_member.call_count == 1


@pytest.mark.parametrize(
    "elapsed,expected_calls,status", [(10, 2, "BANNED"), (20, 1, "UNCONFIRMED"), (70, 1, "UNCONFIRMED")]
)
def test_temporary_deadline_never_extends_and_guard_cannot_become_permanent(
    repo, bot, clock, elapsed, expected_calls, status
):
    session = pending(repo)
    bot.kick_chat_member.side_effect = [RuntimeError("synthetic failure"), None]
    ctx = callback_ctx(repo, bot, session, voter=1)
    handler.handle_vote_callback(ctx)
    first_deadline = repo.get_vote_session(CHAT, TARGET)["ban_until"]
    clock[0] += elapsed
    handler.handle_vote_callback(ctx)
    assert repo.get_vote_session(CHAT, TARGET)["status"] == status
    assert bot.kick_chat_member.call_count == expected_calls
    assert {c.kwargs["until_date"] for c in bot.kick_chat_member.call_args_list} == {first_deadline}


def test_decision_first_executed_after_session_expiry_does_not_start_new_temporary_ban(repo, bot, clock):
    session = pending(repo)
    clock[0] = int(session["expires_at"])
    handler._resume(command_ctx(repo, bot), session)
    assert repo.get_vote_session(CHAT, TARGET)["status"] == "UNCONFIRMED"
    bot.kick_chat_member.assert_not_called()


@pytest.mark.parametrize("status", ["administrator", "creator", "kicked"])
def test_membership_changes_after_voting_do_not_count_or_ban(repo, bot, status):
    session = pending(repo)
    bot.get_chat_member.return_value = {"status": status}
    handler._resume(command_ctx(repo, bot), session)
    assert repo.get_vote_session(CHAT, TARGET)["status"] == "UNCONFIRMED"
    assert counter(repo) == 0
    bot.kick_chat_member.assert_not_called()


def test_unknown_membership_is_retryable_failure(repo, bot):
    session = pending(repo)
    bot.get_chat_member.return_value = {}
    handler.handle_vote_callback(callback_ctx(repo, bot, session))
    assert repo.get_vote_session(CHAT, TARGET)["status"] == "BAN_PENDING"
    bot.kick_chat_member.assert_not_called()
    assert counter(repo) == 0


def test_initial_threshold_one_completes_without_live_keyboard(repo, bot, monkeypatch):
    monkeypatch.setattr(handler, "VOTEBAN_THRESHOLD", 1)
    handler.handle_voteban_command(command_ctx(repo, bot))
    assert repo.get_vote_session(CHAT, TARGET)["status"] == "BANNED"
    bot.edit_message_text.assert_not_called()
    assert counter(repo) == 1


def test_forgive_winner_replay_never_bans_or_deletes_target(repo, bot):
    session = opened(repo)
    for voter in (2, 3, 4):
        vote(repo, session, voter, yes=False)
    handler.handle_vote_callback(callback_ctx(repo, bot, session, voter=1))
    handler.handle_vote_callback(callback_ctx(repo, bot, session, voter=1))
    assert repo.get_vote_session(CHAT, TARGET)["status"] == "FORGIVEN"
    bot.kick_chat_member.assert_not_called()
    assert [c.args[1] for c in bot.delete_message.call_args_list] == [777]
    assert bot.send_message.call_count == 1 and counter(repo) == 0


def test_vote_crossing_threshold_during_render_finishes_under_same_effect_lease(repo, bot):
    session = opened(repo)
    for voter in (2, 3, 4):
        vote(repo, session, voter)

    def concurrent_vote(chat, mid, *args, **kwargs):
        vote(repo, session, 5)
        with pytest.raises(votes.VoteBusyError):
            handler._resume(command_ctx(repo, bot), session)
        return {"message_id": mid}

    bot.edit_message_text.side_effect = concurrent_vote
    handler._resume(command_ctx(repo, bot), session)
    assert repo.get_vote_session(CHAT, TARGET)["effects_complete"]
    assert bot.edit_message_text.call_count == 1 and bot.kick_chat_member.call_count == 1


def test_real_adapter_rejects_unconfirmed_ban_and_preserves_pending(repo, monkeypatch):
    session = pending(repo)
    client = TelegramClient()

    def api(method, payload, **kwargs):
        if method == "getChatMember":
            return {"ok": True, "result": {"status": "member"}}
        if method == "banChatMember":
            return {"ok": True, "result": False}
        return {"ok": True, "result": True}

    monkeypatch.setattr(client, "_post", api)
    handler.handle_vote_callback(callback_ctx(repo, client, session))
    assert repo.get_vote_session(CHAT, TARGET)["status"] == "BAN_PENDING"
    assert counter(repo) == 0


def test_identical_render_error_is_idempotent_but_other_400_errors_propagate(repo, bot):
    session = opened(repo)
    bot.edit_message_text.side_effect = TelegramAPIError(400, '{"description":"Bad Request: message is not modified"}')
    handler._resume(command_ctx(repo, bot), session)
    bot.edit_message_text.side_effect = TelegramAPIError(
        400, '{"description":"Bad Request: message to edit not found"}'
    )
    with pytest.raises(TelegramAPIError):
        handler._resume(command_ctx(repo, bot), session)


def test_command_reused_while_open_cannot_reopen_after_terminal_completion(repo, bot):
    session = pending(repo)
    reused = create(repo, command=20)
    assert reused["generation"] == session["generation"]
    handler._resume(command_ctx(repo, bot), reused)
    replay = create(repo, command=20)
    assert replay["generation"] == session["generation"] and replay["effects_complete"]
    assert create(repo, command=21)["generation"] != session["generation"]


def test_pending_command_recovery_still_closes_after_target_becomes_admin(repo, bot):
    pending(repo)
    bot.get_chat_member.return_value = {"status": "administrator"}
    handler.handle_voteban_command(command_ctx(repo, bot, message_id=20))
    assert repo.get_vote_session(CHAT, TARGET)["status"] == "UNCONFIRMED"
    assert repo.get_vote_session(CHAT, TARGET)["effects_complete"]
    bot.kick_chat_member.assert_not_called()


@pytest.mark.parametrize("status", ["creator", "administrator"])
def test_initial_admin_target_is_refused_without_creating_session(repo, bot, status):
    bot.get_chat_member.return_value = {"status": status}
    handler.handle_voteban_command(command_ctx(repo, bot))
    assert repo.get_vote_session(CHAT, TARGET) == {}
    bot.kick_chat_member.assert_not_called()


def test_terminal_callback_does_not_claim_an_unrecorded_new_vote(repo, bot):
    session = pending(repo)
    handler.handle_vote_callback(callback_ctx(repo, bot, session, voter=99))
    assert 99 not in repo.get_vote_session(CHAT, TARGET)["votes_for"]
    assert bot.answer_callback_query.call_args.kwargs["text"] == handler.get_translated_text("voteban_closed", "kk")


def test_command_cannot_replace_expired_open_session_until_current_effect_lease_drains(repo, clock):
    session = opened(repo)
    clock[0] = int(session["expires_at"]) - 1
    repo.claim(CHAT, TARGET, session["generation"])
    clock[0] += 2
    with pytest.raises(votes.VoteBusyError):
        create(repo, command=20, date=clock[0])
    clock[0] += 360
    assert create(repo, command=20, date=clock[0])["generation"] != session["generation"]


def test_inert_send_without_confirmed_identity_never_installs_buttons(repo, bot):
    bot.send_message.return_value = {}
    handler.handle_voteban_command(command_ctx(repo, bot))
    assert repo.get_vote_session(CHAT, TARGET)["status"] == "CREATING"
    assert repo.get_vote_session(CHAT, TARGET)["sent_message_id"] == 0
    bot.edit_message_text.assert_not_called()


def test_unsafe_duration_cannot_turn_a_temporary_vote_into_permanent_ban(repo, bot, monkeypatch):
    session = pending(repo)
    monkeypatch.setattr(handler, "KICK_BAN_DURATION_SECONDS", 367 * 86400)
    handler._resume(command_ctx(repo, bot), session)
    assert repo.get_vote_session(CHAT, TARGET)["status"] == "UNCONFIRMED"
    bot.kick_chat_member.assert_not_called()
    assert counter(repo) == 0


def test_expired_unpublished_generation_can_be_replaced_but_old_claim_is_fenced(repo, clock):
    original = create(repo)
    clock[0] = int(original["expires_at"])
    current = create(repo, command=20, date=clock[0])
    assert current["generation"] != original["generation"]
    with pytest.raises(votes.VoteBusyError):
        repo.claim(CHAT, TARGET, original["generation"])
    assert repo.get_vote_session(CHAT, TARGET) == current


@pytest.mark.parametrize("chat_type", ["group", ""])
def test_basic_or_unknown_chat_type_cannot_receive_a_permanent_ban(repo, bot, chat_type):
    ctx = command_ctx(repo, bot)
    ctx.message["chat"]["type"] = chat_type
    handler.handle_voteban_command(ctx)
    session = repo.get_vote_session(CHAT, TARGET)
    for voter in (2, 3, 4, 5):
        vote(repo, session, voter)
    handler.handle_vote_callback(callback_ctx(repo, bot, session))
    assert repo.get_vote_session(CHAT, TARGET)["status"] == "UNCONFIRMED"
    assert repo.get_vote_session(CHAT, TARGET)["effects_complete"]
    bot.kick_chat_member.assert_not_called()
    assert counter(repo) == 0
