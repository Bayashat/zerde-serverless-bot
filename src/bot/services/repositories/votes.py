"""Single owner for generation-bound voteban sessions and confirmed-ban counters."""

import time
import uuid
from typing import Any

from botocore.exceptions import ClientError
from core.config import STATS_TABLE_NAME
from services.repositories._common import get_dynamodb
from services.repositories.stats import _almaty_now_str

VOTEBAN_TTL_SECONDS = 3 * 60 * 60
COMMAND_MAX_AGE_SECONDS = 24 * 60 * 60
_RECEIPT_SECONDS = 7 * 86400
_LEASE_SECONDS = 360  # Exceeds the bot's 300-second configured invocation timeout.
_FINAL = {"BANNED", "FORGIVEN", "UNCONFIRMED"}


class VoteBusyError(RuntimeError):
    pass


class VoteSessionError(RuntimeError):
    pass


def _conditional(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


class VoteRepository:
    @property
    def _table(self):
        return get_dynamodb().Table(STATS_TABLE_NAME)

    @staticmethod
    def _key(chat_id, target_user_id):
        return {"stat_key": f"voteban_{chat_id}_{target_user_id}"}

    def get_vote_session(self, chat_id: int | str, target_user_id: int) -> dict[str, Any]:
        return self._table.get_item(Key=self._key(chat_id, target_user_id), ConsistentRead=True).get("Item") or {}

    def create_vote_session(
        self,
        *,
        chat_id: int | str,
        chat_type: str,
        target_user_id: int,
        command_message_id: int,
        command_date: int,
        reply_message_id: int,
        initiator_user_id: int,
        initiator_username: str | None = None,
        initiator_first_name: str = "User",
        target_username: str | None = None,
        target_first_name: str = "User",
    ) -> dict[str, Any]:
        now = int(time.time())
        if not now - COMMAND_MAX_AGE_SECONDS <= command_date <= now + 300:
            raise VoteSessionError("Vote command is outside its replay window")
        for _ in range(8):
            old = self.get_vote_session(chat_id, target_user_id)
            if old:
                # An active legacy session is left intact, but its unversioned buttons cannot vote.
                if old.get("schema_version") != 2:
                    if not old.get("ttl") or int(old["ttl"]) > now:
                        raise VoteSessionError("Legacy vote session must expire before replacement")
                else:
                    if command_message_id <= int(old["last_command_message_id"]):
                        return old
                    unfinished = old["status"] in {"BAN_PENDING", "FORGIVE_PENDING"} or (
                        old["status"] in _FINAL and not old.get("effects_complete")
                    )
                    if unfinished or (old["status"] in {"CREATING", "OPEN"} and int(old["expires_at"]) > now):
                        # Also receipt commands that reused this session. Their later retries must not reopen it.
                        try:
                            response = self._table.update_item(
                                Key=self._key(chat_id, target_user_id),
                                UpdateExpression="SET last_command_message_id = :command, revision = :next",
                                ConditionExpression="generation = :generation AND revision = :revision",
                                ExpressionAttributeValues={
                                    ":command": command_message_id,
                                    ":next": int(old["revision"]) + 1,
                                    ":generation": old["generation"],
                                    ":revision": old["revision"],
                                },
                                ReturnValues="ALL_NEW",
                            )
                            return response["Attributes"]
                        except ClientError as exc:
                            if not _conditional(exc):
                                raise
                            continue
                    if int(old.get("lease_until", 0)) >= now and old.get("lease_owner"):
                        raise VoteBusyError("Previous vote invocation is still running")
            generation = uuid.uuid4().hex[:16]
            item = {
                **self._key(chat_id, target_user_id),
                "schema_version": 2,
                "chat_id": str(chat_id),
                "chat_type": chat_type,
                "target_user_id": target_user_id,
                "generation": generation,
                "revision": 0,
                "status": "CREATING",
                "command_message_id": command_message_id,
                "last_command_message_id": command_message_id,
                "command_date": command_date,
                "created_at": now,
                "expires_at": now + VOTEBAN_TTL_SECONDS,
                "ttl": now + _RECEIPT_SECONDS,
                "reply_message_id": reply_message_id,
                "sent_message_id": 0,
                "initiator_user_id": initiator_user_id,
                "initiator_username": initiator_username or "",
                "initiator_first_name": initiator_first_name,
                "target_username": target_username or "",
                "target_first_name": target_first_name,
                "votes_for": [initiator_user_id],
                "votes_against": [],
                "votes_for_info": [
                    {"id": initiator_user_id, "username": initiator_username or "", "first_name": initiator_first_name}
                ],
                "votes_against_info": [],
            }
            request = {"Item": item}
            if not old:
                request["ConditionExpression"] = "attribute_not_exists(stat_key)"
            elif old.get("schema_version") == 2:
                request.update(
                    ConditionExpression=(
                        "generation = :old AND revision = :revision AND "
                        "(attribute_not_exists(lease_owner) OR lease_until < :now)"
                    ),
                    ExpressionAttributeValues={":old": old["generation"], ":revision": old["revision"], ":now": now},
                )
            else:
                request.update(
                    ConditionExpression="attribute_not_exists(generation) AND #ttl = :ttl",
                    ExpressionAttributeNames={"#ttl": "ttl"},
                    ExpressionAttributeValues={":ttl": old["ttl"]},
                )
            try:
                self._table.put_item(**request)
                return item
            except ClientError as exc:
                if not _conditional(exc):
                    raise
        raise VoteBusyError("Vote creation changed concurrently")

    def claim(self, chat_id, target_user_id, generation) -> tuple[str, dict]:
        owner = uuid.uuid4().hex
        now = int(time.time())
        try:
            result = self._table.update_item(
                Key=self._key(chat_id, target_user_id),
                UpdateExpression="SET lease_owner = :owner, lease_until = :until",
                ConditionExpression=(
                    "generation = :generation AND " "(attribute_not_exists(lease_owner) OR lease_until < :now)"
                ),
                ExpressionAttributeValues={
                    ":generation": generation,
                    ":owner": owner,
                    ":until": now + _LEASE_SECONDS,
                    ":now": now,
                },
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if _conditional(exc):
                raise VoteBusyError("Vote effects are already running or session changed") from None
            raise
        return owner, result["Attributes"]

    def update_effects(self, session, owner, fields, *, durable=False):
        names = {f"#f{i}": name for i, name in enumerate(fields)}
        values = {f":v{i}": value for i, value in enumerate(fields.values())}
        expression = "SET " + ", ".join(f"#f{i} = :v{i}" for i in range(len(fields)))
        if durable:
            names["#ttl"] = "ttl"
            expression += " REMOVE #ttl"
        self._table.update_item(
            Key=self._key(session["chat_id"], session["target_user_id"]),
            UpdateExpression=expression,
            ConditionExpression="generation = :generation AND lease_owner = :owner",
            ExpressionAttributeNames=names,
            ExpressionAttributeValues={**values, ":generation": session["generation"], ":owner": owner},
        )

    def release(self, session, owner):
        try:
            self._table.update_item(
                Key=self._key(session["chat_id"], session["target_user_id"]),
                UpdateExpression="REMOVE lease_owner, lease_until",
                ConditionExpression="generation = :generation AND lease_owner = :owner",
                ExpressionAttributeValues={":generation": session["generation"], ":owner": owner},
            )
        except ClientError as exc:
            if not _conditional(exc):
                raise

    def bind_message(self, session, owner, message_id, *, for_threshold):
        status = "BAN_PENDING" if len(session["votes_for"]) >= for_threshold else "OPEN"
        self.update_effects(
            session, owner, {"sent_message_id": message_id, "status": status}, durable=status == "BAN_PENDING"
        )

    def add_vote(
        self,
        chat_id,
        target_user_id,
        voter_id,
        vote_for,
        *,
        generation,
        sent_message_id,
        for_threshold,
        against_threshold,
        voter_username=None,
        voter_first_name="User",
    ) -> tuple[dict, str]:
        for _ in range(8):
            now = int(time.time())
            session = self.get_vote_session(chat_id, target_user_id)
            if (
                not session
                or session.get("schema_version") != 2
                or session.get("generation") != generation
                or session.get("sent_message_id") != sent_message_id
            ):
                raise VoteSessionError("Vote button does not belong to this session")
            if session["status"] in {"BAN_PENDING", "FORGIVE_PENDING"} or session["status"] in _FINAL:
                return session, "pending"  # Replays resume effects even for an already-recorded voter.
            if session["status"] != "OPEN" or int(session["expires_at"]) <= now:
                raise VoteSessionError("Vote session is not open")
            if voter_id in session["votes_for"] or voter_id in session["votes_against"]:
                return session, "already_voted"
            field = "votes_for" if vote_for else "votes_against"
            info_field = field + "_info"
            voters = [*session[field], voter_id]
            infos = [
                *session[info_field],
                {"id": voter_id, "username": voter_username or "", "first_name": voter_first_name},
            ]
            status = "OPEN"
            if vote_for and len(voters) >= for_threshold:
                status = "BAN_PENDING"
            elif not vote_for and len(voters) >= against_threshold:
                status = "FORGIVE_PENDING"
            expression = "SET #votes = :votes, #infos = :infos, #status = :status, revision = :next"
            names = {"#votes": field, "#infos": info_field, "#status": "status"}
            if status != "OPEN":
                expression += " REMOVE #ttl"
                names["#ttl"] = "ttl"
            try:
                response = self._table.update_item(
                    Key=self._key(chat_id, target_user_id),
                    UpdateExpression=expression,
                    ConditionExpression=(
                        "generation = :generation AND sent_message_id = :message AND "
                        "#status = :open AND expires_at > :now AND revision = :revision"
                    ),
                    ExpressionAttributeNames=names,
                    ExpressionAttributeValues={
                        ":votes": voters,
                        ":infos": infos,
                        ":status": status,
                        ":next": int(session["revision"]) + 1,
                        ":generation": generation,
                        ":message": sent_message_id,
                        ":open": "OPEN",
                        ":now": now,
                        ":revision": session["revision"],
                    },
                    ReturnValues="ALL_NEW",
                )
                return response["Attributes"], "recorded"
            except ClientError as exc:
                if not _conditional(exc):
                    raise
        raise VoteBusyError("Votes changed concurrently; retry the same button")

    def confirm_ban(self, session, owner):
        table = self._table
        table.meta.client.transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": table.name,
                        "Key": self._key(session["chat_id"], session["target_user_id"]),
                        "UpdateExpression": "SET #status = :banned, ban_confirmed = :true",
                        "ConditionExpression": (
                            "generation = :generation AND lease_owner = :owner AND #status = :pending"
                        ),
                        "ExpressionAttributeNames": {"#status": "status"},
                        "ExpressionAttributeValues": {
                            ":banned": "BANNED",
                            ":true": True,
                            ":generation": session["generation"],
                            ":owner": owner,
                            ":pending": "BAN_PENDING",
                        },
                    }
                },
                {
                    "Update": {
                        "TableName": table.name,
                        "Key": {"stat_key": str(session["chat_id"])},
                        "UpdateExpression": (
                            "SET total_bans = if_not_exists(total_bans, :zero) + :one, "
                            "started_at = if_not_exists(started_at, :started)"
                        ),
                        "ExpressionAttributeValues": {":zero": 0, ":one": 1, ":started": _almaty_now_str()},
                    }
                },
            ]
        )

    def complete_effects(self, session, owner):
        self.update_effects(session, owner, {"effects_complete": True, "ttl": int(time.time()) + _RECEIPT_SECONDS})
