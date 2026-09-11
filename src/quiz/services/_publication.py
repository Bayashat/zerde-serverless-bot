"""QuizRepository's publication state machine; all methods use its one quiz table."""

import re
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

LEASE_SECONDS = 330  # Both authorized writers run in Lambdas with a 300s maximum.
RETENTION_SECONDS = 90 * 86400


class QuizPublicationConflict(RuntimeError):
    pass


class QuizPublicationBusy(RuntimeError):
    pass


class QuizPublicationUnknown(RuntimeError):
    pass


def _conditional(exc):
    code = exc.response.get("Error", {}).get("Code")
    return code == "ConditionalCheckFailedException" or (
        code == "TransactionCanceledException"
        and any(
            reason.get("Code") == "ConditionalCheckFailed" for reason in exc.response.get("CancellationReasons", [])
        )
    )


def validate_poll_receipt(draft, message, *, chat_id, bot_user_id=None):
    """Require authoritative Telegram message identity and a usable single-answer mapping."""
    if not isinstance(message, dict) or str((message.get("chat") or {}).get("id")) != str(chat_id):
        raise QuizPublicationUnknown("Poll receipt has no matching chat identity")
    if bot_user_id is not None and (
        str((message.get("from") or {}).get("id")) != str(bot_user_id)
        or (message.get("from") or {}).get("is_bot") is not True
    ):
        raise QuizPublicationUnknown("Poll receipt is not from this bot")
    if (
        any(message.get(key) for key in ("forward_origin", "forward_date", "forward_from", "forward_from_chat"))
        or type(message.get("message_id")) is not int
        or message["message_id"] <= 0
        or type(message.get("date")) is not int
        or message["date"] <= 0
    ):
        raise QuizPublicationUnknown("Poll receipt has invalid message identity")
    poll = message.get("poll") or {}
    if (
        not isinstance(poll.get("id"), str)
        or not poll["id"]
        or poll.get("type") != "quiz"
        or poll.get("is_anonymous") is not False
        or poll.get("allows_multiple_answers") is not False
        or poll.get("allows_revoting", False) is not False
        or poll.get("question") != draft["question"]
    ):
        raise QuizPublicationUnknown("Poll receipt does not match the prepared quiz")
    options = poll.get("options")
    if not isinstance(options, list) or any(
        not isinstance(option, dict) or not isinstance(option.get("text"), str) for option in options
    ):
        raise QuizPublicationUnknown("Poll receipt options are missing")
    texts = [option["text"] for option in options]
    correct = poll.get("correct_option_ids")
    if correct is None and type(poll.get("correct_option_id")) is int:
        correct = [poll["correct_option_id"]]
    if (
        not isinstance(correct, list)
        or len(correct) != 1
        or type(correct[0]) is not int
        or correct[0] not in range(len(texts))
        or Counter(texts) != Counter(draft["options"])
        or texts[correct[0]] != draft["options"][int(draft["correct_option_id"])]
    ):
        raise QuizPublicationUnknown("Poll receipt has no matching single correct answer")
    return {
        "poll_id": poll["id"],
        "message_id": message["message_id"],
        "options": texts,
        "correct_option_id": correct[0],
    }


class PublicationState:
    """Mixin for QuizRepository; no separate client, table, profile or duplicate owner."""

    def _publication_read(self, key):
        return self._table.get_item(Key=key, ConsistentRead=True).get("Item") or {}

    def _publication_transaction(self, operations):
        try:
            self._table.meta.client.transact_write_items(TransactItems=operations)
        except ClientError as exc:
            if _conditional(exc):
                raise QuizPublicationConflict("Quiz publication changed") from exc
            raise

    def _publication_put(self, item, previous):
        op = {"TableName": self._table.name, "Item": item}
        if previous:
            op.update(
                ConditionExpression="#revision = :revision AND generation = :generation",
                ExpressionAttributeNames={"#revision": "revision"},
                ExpressionAttributeValues={":revision": previous["revision"], ":generation": previous["generation"]},
            )
        else:
            op["ConditionExpression"] = "attribute_not_exists(PK)"
        return {"Put": op}

    def _publication_transition(self, item, previous):
        operations = [self._publication_put(item, previous)]
        key = {"PK": "QUIZ_PUBLICATION_OUTBOX", "SK": f"{item['chat_id']}#{item['request_key']}"}
        if item["state"] in {"DONE", "UNKNOWN", "CONFLICT", "EXPIRED"}:
            operations.append({"Delete": {"TableName": self._table.name, "Key": key}})
        else:
            operations.append(
                {
                    "Put": {
                        "TableName": self._table.name,
                        "Item": {
                            **key,
                            "chat_id": item["chat_id"],
                            "request_key": item["request_key"],
                            "generation": item["generation"],
                            "next_attempt_at": item["lease_until"],
                            "retain_until": item["ttl"],
                        },
                    }
                }
            )
        return operations

    @staticmethod
    def publication_key(chat_id, request_key):
        if not re.fullmatch(r"-?[1-9][0-9]*", str(chat_id)) or not re.fullmatch(
            r"DATE#\d{4}-\d{2}-\d{2}|REQUEST#[1-9][0-9]*", request_key
        ):
            raise ValueError("Invalid quiz request identity")
        return {"PK": f"QUIZ_EXEC#{chat_id}", "SK": request_key}

    def claim_publication(self, chat_id, request_key, intent=None):
        key = self.publication_key(chat_id, request_key)
        previous = self._publication_read(key)
        now = int(time.time())
        if previous.get("state") in {"DONE", "CONFLICT", "UNKNOWN", "EXPIRED"}:
            return previous
        if previous.get("state") in {"GENERATING", "PREPARED"} and int(previous["expires_at"]) <= now:
            expired = {
                **previous,
                "revision": int(previous["revision"]) + 1,
                "state": "EXPIRED",
                "reason": "request_expired",
                "lease_until": 0,
            }
            self._publication_transaction(self._publication_transition(expired, previous))
            return expired
        if previous and int(previous["lease_until"]) > now:
            raise QuizPublicationBusy("Another invocation owns this quiz")
        if previous.get("state") == "SENDING":
            unknown = {
                **previous,
                "revision": int(previous["revision"]) + 1,
                "state": "UNKNOWN",
                "reason": "sender_interrupted",
            }
            self._publication_transaction(self._publication_transition(unknown, previous))
            return unknown
        if not previous and (not isinstance(intent, dict) or intent.get("kind") not in {"daily", "on_demand"}):
            raise ValueError("A new quiz requires its durable request intent")
        expires_at = (
            int(
                (datetime.fromisoformat(request_key.removeprefix("DATE#")) + timedelta(days=1))
                .replace(tzinfo=timezone(timedelta(hours=5)))
                .timestamp()
            )
            if request_key.startswith("DATE#")
            else now + 86400
        )
        item = {
            **previous,
            **key,
            "generation": previous.get("generation") or uuid.uuid4().hex,
            "revision": int(previous.get("revision", 0)) + 1,
            "state": previous.get("state", "GENERATING"),
            "chat_id": str(chat_id),
            "request_key": request_key,
            "lease_token": uuid.uuid4().hex,
            "lease_until": now + LEASE_SECONDS,
            "created_at": previous.get("created_at", now),
            "ttl": now + RETENTION_SECONDS,
            "intent": previous.get("intent") or intent,
            "expires_at": previous.get("expires_at", expires_at),
        }
        if item["state"] in {"GENERATING", "PREPARED"} and int(item["expires_at"]) <= now:
            item.update(state="EXPIRED", reason="request_expired", lease_until=0)
        self._publication_transaction(self._publication_transition(item, previous))
        return item

    def _owned_publication(self, execution, *, states):
        current = self._publication_read({"PK": execution["PK"], "SK": execution["SK"]})
        if (
            not current
            or current["generation"] != execution["generation"]
            or current["lease_token"] != execution["lease_token"]
            or int(current["lease_until"]) <= int(time.time())
            or current["state"] not in states
            or (current["state"] in {"GENERATING", "PREPARED"} and int(current["expires_at"]) <= int(time.time()))
        ):
            raise QuizPublicationConflict("Publication lease or generation changed")
        return current

    def prepare_publication(self, execution, draft, rotations=None):
        current = self._owned_publication(execution, states={"GENERATING", "PREPARED"})
        if current["state"] == "PREPARED":
            return current
        if (
            not isinstance(draft.get("question"), str)
            or not 1 <= len(draft["question"]) <= 300
            or not isinstance(draft.get("options"), list)
            or not 2 <= len(draft["options"]) <= 12
            or any(not isinstance(option, str) or not option for option in draft["options"])
            or len(set(draft["options"])) != len(draft["options"])
            or type(draft.get("correct_option_id")) is not int
            or draft["correct_option_id"] not in range(len(draft["options"]))
            or type(draft.get("points")) is not int
            or draft["points"] not in range(1, 101)
        ):
            raise ValueError("Invalid single-answer quiz draft")
        item = {
            **current,
            "revision": int(current["revision"]) + 1,
            "state": "PREPARED",
            "draft": draft,
            "rotations": rotations or [],
        }
        self._publication_transaction(self._publication_transition(item, current))
        return item

    def publication_rotations(
        self,
        chat_id,
        category,
        *,
        category_remaining=None,
        bank_remaining=None,
        difficulty=None,
        bank_scope=None,
        bank_source=None,
        bank_uuid=None,
        subtopic=None,
        subtopic_remaining=None,
        genquiz=False,
    ):
        """Persist bounded deck changes in the same transaction as publication completion."""
        operations = []
        today = datetime.now(timezone(timedelta(hours=5))).strftime("%Y-%m-%d")

        def put(pk, **fields):
            key = {"PK": pk, "SK": "LATEST"}
            expected = getattr(self, "_deck_snapshots", {}).get(pk)
            if expected is None:
                expected = self._publication_read(key)
            operations.append(
                {"write": {"Put": {"TableName": self._table.name, "Item": {**key, **fields}}}, "expected": expected}
            )

        if category_remaining is not None:
            put(f"META#category#{chat_id}", remaining=category_remaining, category=category, date=today)
        if subtopic_remaining is not None:
            put(
                f"META#subtopic#{category}#{difficulty}#{chat_id}",
                remaining=subtopic_remaining,
                category=category,
                difficulty=difficulty,
                subtopic=subtopic,
                date=today,
            )
        if bank_remaining is not None:
            prefix = "genquiz_q_queue" if genquiz else "q_queue"
            suffix = (f"#{difficulty}" if difficulty else "") + (f"#{bank_scope}" if bank_scope else "")
            put(f"META#{prefix}#{category}{suffix}#{chat_id}", remaining=bank_remaining)
        if bank_source and bank_uuid:
            operations.append(
                {
                    "Update": {
                        "TableName": self._table.name,
                        "Key": {"PK": f"BANK#{category}#{bank_source}", "SK": f"Q#{bank_uuid}"},
                        "UpdateExpression": "SET last_used_at = :now ADD use_count :one",
                        "ExpressionAttributeValues": {":now": today, ":one": 1},
                    }
                }
            )
        return operations

    def mark_announcement_attempted(self, execution):
        current = self._owned_publication(execution, states={"PREPARED"})
        item = {**current, "revision": int(current["revision"]) + 1, "announcement_attempted": True}
        self._publication_transaction(self._publication_transition(item, current))
        return item

    def mark_publication_sending(self, execution):
        current = self._owned_publication(execution, states={"PREPARED"})
        item = {**current, "revision": int(current["revision"]) + 1, "state": "SENDING", "sending_at": int(time.time())}
        self._publication_transaction(self._publication_transition(item, current))
        return item

    def mark_publication_failed(self, execution, *, unknown, reason):
        current = self._owned_publication(execution, states={"GENERATING", "PREPARED", "SENDING"})
        item = {
            **current,
            "revision": int(current["revision"]) + 1,
            "state": "UNKNOWN" if unknown else ("PREPARED" if "draft" in current else "GENERATING"),
            "reason": reason,
            "lease_until": 0,
        }
        self._publication_transaction(self._publication_transition(item, current))
        return item

    def persist_poll_receipt(self, execution, message, *, bot_user_id=None, reconciliation=False):
        if reconciliation:
            current = self._publication_read({"PK": execution["PK"], "SK": execution["SK"]})
            if (
                not current
                or current["generation"] != execution["generation"]
                or current["state"] != "UNKNOWN"
                or bot_user_id is None
            ):
                raise QuizPublicationConflict("Reconciliation requires the current UNKNOWN generation")
        else:
            current = self._owned_publication(execution, states={"SENDING", "SENT"})
        identity = validate_poll_receipt(current["draft"], message, chat_id=current["chat_id"], bot_user_id=bot_user_id)
        if not int(current["sending_at"]) - 5 <= message["date"] <= int(current["sending_at"]) + LEASE_SECONDS:
            raise QuizPublicationUnknown("Poll receipt is outside this execution's send window")
        if reconciliation:
            self._assert_reconciliation_unique(current, message)
        if current.get("poll_id") and current["poll_id"] != identity["poll_id"]:
            raise QuizPublicationConflict("Execution is already bound to another poll")
        poll_key = {"PK": f"POLL#{identity['poll_id']}", "SK": "META"}
        existing = self._publication_read(poll_key)
        if existing:
            if existing.get("generation") != current["generation"] or existing.get("chat_id") != current["chat_id"]:
                raise QuizPublicationConflict("Poll identity belongs to another execution")
            return current
        lookup = {
            **current["draft"],
            **identity,
            **poll_key,
            "chat_id": current["chat_id"],
            "record_key": current["request_key"],
            "is_daily": current["request_key"].startswith("DATE#"),
            "generation": current["generation"],
            "sent_at_epoch": int(message.get("date") or time.time()),
            "ttl": int(time.time()) + RETENTION_SECONDS,
        }
        sent = {
            **current,
            **identity,
            "state": "SENT",
            "revision": int(current["revision"]) + 1,
            "lease_until": int(time.time()) + LEASE_SECONDS if reconciliation else current["lease_until"],
        }
        self._publication_transaction([*self._publication_transition(sent, current), self._publication_put(lookup, {})])
        return sent

    def _assert_reconciliation_unique(self, current, message):
        """Telegram has no request-generation echo; competing identical unknown sends are ambiguous."""
        kwargs = {"KeyConditionExpression": Key("PK").eq(current["PK"]), "ConsistentRead": True, "Limit": 100}
        for _ in range(10):
            page = self._table.query(**kwargs)
            for other in page.get("Items", []):
                if other["SK"] == current["SK"] or other.get("state") not in {"SENDING", "UNKNOWN"}:
                    continue
                if (
                    not int(other.get("sending_at", 0)) - 5
                    <= message["date"]
                    <= int(other.get("sending_at", 0)) + LEASE_SECONDS
                ):
                    continue
                try:
                    validate_poll_receipt(other["draft"], message, chat_id=current["chat_id"])
                except (QuizPublicationUnknown, KeyError):
                    continue
                raise QuizPublicationUnknown("More than one unknown send matches this poll")
            if not page.get("LastEvaluatedKey"):
                return
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
        raise QuizPublicationUnknown("Reconciliation search bound exceeded")

    def finalize_publication(self, execution):
        current = self._owned_publication(execution, states={"SENT"})
        key = {"PK": f"QUIZ#{current['chat_id']}", "SK": current["request_key"]}
        existing = self._publication_read(key)
        conflict = bool(existing and existing.get("poll_id") != current["poll_id"])
        complete = {
            **current,
            "state": "CONFLICT" if conflict else "DONE",
            "revision": int(current["revision"]) + 1,
            "completed_at": int(time.time()),
            "lease_until": 0,
        }
        operations = self._publication_transition(complete, current)
        if not existing:
            record = {
                **current["draft"],
                **key,
                "poll_id": current["poll_id"],
                "message_id": current["message_id"],
                "options": current["options"],
                "correct_option_id": current["correct_option_id"],
                "generation": current["generation"],
                "ttl": int(time.time()) + RETENTION_SECONDS,
            }
            operations.append(self._publication_put(record, {}))
        else:
            operations.append(
                {
                    "ConditionCheck": {
                        "TableName": self._table.name,
                        "Key": key,
                        "ConditionExpression": "poll_id = :poll",
                        "ExpressionAttributeValues": {":poll": existing["poll_id"]},
                    }
                }
            )
        # Rotation is part of publication completion, so a replay cannot consume a
        # second question or overwrite an independently updated score record.
        if not conflict:
            rotation_ops, skipped = self._current_rotations(current)
            operations.extend(rotation_ops)
            complete["rotation_conflicts"] = skipped
        self._publication_transaction(operations)
        return complete

    def _current_rotations(self, execution):
        operations, skipped = [], 0
        for rotation in execution.get("rotations", []):
            if "write" not in rotation:
                operations.append(rotation)  # Atomic usage increment, not a mutable deck.
                continue
            operation, expected = rotation["write"]["Put"], rotation["expected"]
            item = operation["Item"]
            key = {"PK": item["PK"], "SK": item["SK"]}
            latest = self._publication_read(key)
            if latest != expected:
                skipped += 1
                continue
            write = {**operation, "Item": {**item, "publication_generation": execution["generation"]}}
            if latest.get("publication_generation"):
                write.update(
                    ConditionExpression="publication_generation = :generation",
                    ExpressionAttributeValues={":generation": latest["publication_generation"]},
                )
            else:
                write["ConditionExpression"] = "attribute_not_exists(publication_generation)"
            operations.append({"Put": write})
        return operations, skipped

    def publication_recovery_page(self, limit=50):
        key = {"PK": "QUIZ_PUBLICATION_RECOVERY", "SK": "CURSOR"}
        previous = self._publication_read(key)
        kwargs = {
            "KeyConditionExpression": Key("PK").eq("QUIZ_PUBLICATION_OUTBOX"),
            "ConsistentRead": True,
            "Limit": max(1, min(limit, 50)),
        }
        if previous.get("cursor"):
            kwargs["ExclusiveStartKey"] = previous["cursor"]
        response = self._table.query(**kwargs)
        return previous, response.get("Items", []), response.get("LastEvaluatedKey")

    def checkpoint_publication_recovery(self, previous, cursor):
        item = {
            "PK": "QUIZ_PUBLICATION_RECOVERY",
            "SK": "CURSOR",
            "cursor": cursor or {},
            "revision": int(previous.get("revision", 0)) + 1,
            "generation": "recovery",
        }
        self._publication_transaction([self._publication_put(item, previous)])

    def expire_publication_orphan(self, row):
        if int(row["retain_until"]) > int(time.time()):
            raise QuizPublicationConflict("Unexpired publication outbox lost its execution")
        self._publication_transaction(
            [
                {
                    "ConditionCheck": {
                        "TableName": self._table.name,
                        "Key": self.publication_key(row["chat_id"], row["request_key"]),
                        "ConditionExpression": "attribute_not_exists(PK)",
                    }
                },
                {
                    "Delete": {
                        "TableName": self._table.name,
                        "Key": {"PK": row["PK"], "SK": row["SK"]},
                        "ConditionExpression": "generation = :generation",
                        "ExpressionAttributeValues": {":generation": row["generation"]},
                    }
                },
            ]
        )
