"""QuizRepository's durable answer receipts, score transaction and recovery cursor."""

import re
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

_TZ = timezone(timedelta(hours=5))
_PENDING_SECONDS = 7 * 86400
_RECEIPT_SECONDS = 90 * 86400
_TERMINAL = {"SCORED", "DUPLICATE", "INVALID", "EXPIRED"}


class QuizAnswerRetryRequiredError(RuntimeError):
    """The webhook must request redelivery because no durable answer is guaranteed."""


class QuizAnswerConflict(RuntimeError):
    pass


def _identity(poll_id, user_id):
    if (
        not isinstance(poll_id, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", poll_id)
        or not re.fullmatch(r"[1-9][0-9]*", str(user_id))
    ):
        raise ValueError("Invalid quiz answer identity")
    return {"PK": f"ANSWER#{poll_id}", "SK": f"USER#{user_id}"}


def _conditional(exc):
    return exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException" or (
        exc.response.get("Error", {}).get("Code") == "TransactionCanceledException"
        and any(item.get("Code") == "ConditionalCheckFailed" for item in exc.response.get("CancellationReasons", []))
    )


class AnswerState:
    def _answer_read(self, key):
        return self._table.get_item(Key=key, ConsistentRead=True).get("Item") or {}

    def _answer_transaction(self, operations):
        try:
            self._table.meta.client.transact_write_items(TransactItems=operations)
        except ClientError as exc:
            if _conditional(exc):
                raise QuizAnswerConflict("Concurrent quiz answer update") from exc
            raise

    @staticmethod
    def _answer_outbox_key(poll_id, user_id):
        _identity(poll_id, user_id)
        return {"PK": "QUIZ_ANSWER_OUTBOX", "SK": f"{poll_id}#{user_id}"}

    def get_answer(self, poll_id, user_id):
        return self._answer_read(_identity(poll_id, user_id))

    def persist_answer(self, poll_answer, update_id):
        """Atomically accept one immutable, single-choice answer and its outbox."""
        if not isinstance(poll_answer, dict):
            return {"state": "INVALID"}
        user = poll_answer.get("user") or {}
        options = poll_answer.get("option_ids")
        if (
            type(user.get("id")) is not int
            or user["id"] <= 0
            or user.get("is_bot")
            or poll_answer.get("voter_chat")
            or type(update_id) is not int
            or update_id < 0
            or not isinstance(options, list)
            or len(options) != 1
            or type(options[0]) is not int
            or not 0 <= options[0] < 12
        ):
            return {"state": "INVALID"}
        poll_id, user_id = poll_answer.get("poll_id"), str(user["id"])
        try:
            key = _identity(poll_id, user_id)
        except ValueError:
            return {"state": "INVALID"}
        existing = self._answer_read(key)
        if existing:
            return existing  # This product disables revoting; first accepted choice owns scoring.
        now = int(time.time())
        item = {
            **key,
            "poll_id": poll_id,
            "user_id": user_id,
            "option_id": options[0],
            "first_name": str(user.get("first_name") or "User")[:128],
            "update_id": update_id,
            "received_at": now,
            "expires_at": now + _PENDING_SECONDS,
            "ttl": now + _RECEIPT_SECONDS,
            "state": "PENDING",
            "revision": 1,
            "attempts": 0,
            "next_attempt_at": now,
        }
        outbox = {
            **self._answer_outbox_key(poll_id, user_id),
            "poll_id": poll_id,
            "user_id": user_id,
            "next_attempt_at": now,
            "expires_at": item["expires_at"],
        }
        try:
            self._answer_transaction(
                [
                    {
                        "Put": {
                            "TableName": self._table.name,
                            "Item": row,
                            "ConditionExpression": "attribute_not_exists(PK)",
                        }
                    }
                    for row in (item, outbox)
                ]
            )
        except QuizAnswerConflict:
            existing = self._answer_read(key)
            if not existing:
                raise
            return existing
        return item

    def _replace_answer(self, current, item, *, extra_operations=()):
        operations = [
            {
                "Put": {
                    "TableName": self._table.name,
                    "Item": item,
                    "ConditionExpression": "#revision = :revision",
                    "ExpressionAttributeNames": {"#revision": "revision"},
                    "ExpressionAttributeValues": {":revision": current["revision"]},
                }
            }
        ]
        if item["state"] == "SCORED":
            # Re-read time after the score dependency read; a delayed worker must
            # not commit an answer whose logical retention window already ended.
            operations[0]["Put"]["ConditionExpression"] += " AND expires_at > :now"
            operations[0]["Put"]["ExpressionAttributeValues"][":now"] = int(time.time())
        key = self._answer_outbox_key(current["poll_id"], current["user_id"])
        if item["state"] in _TERMINAL:
            operations.append({"Delete": {"TableName": self._table.name, "Key": key}})
            operations.append(
                {
                    "Update": {
                        "TableName": self._table.name,
                        "Key": {"PK": "QUIZ_ANSWER_COVERAGE", "SK": "TOTAL"},
                        "UpdateExpression": "ADD #count :one",
                        "ExpressionAttributeNames": {"#count": item["state"].lower()},
                        "ExpressionAttributeValues": {":one": 1},
                    }
                }
            )
        else:
            operations.append(
                {
                    "Put": {
                        "TableName": self._table.name,
                        "Item": {
                            **key,
                            "poll_id": current["poll_id"],
                            "user_id": current["user_id"],
                            "next_attempt_at": item["next_attempt_at"],
                            "expires_at": item["expires_at"],
                        },
                    }
                }
            )
        self._answer_transaction([*operations, *extra_operations])
        return item

    def finish_answer(self, current, state):
        if state not in _TERMINAL:
            raise ValueError("Invalid answer terminal state")
        item = {**current, "state": state, "revision": int(current["revision"]) + 1, "completed_at": int(time.time())}
        return self._replace_answer(current, item)

    def defer_answer(self, current):
        now = int(time.time())
        attempts = int(current["attempts"]) + 1
        item = {
            **current,
            "state": "UNRESOLVED" if attempts >= 12 else "PENDING",
            "attempts": attempts,
            "revision": int(current["revision"]) + 1,
            "next_attempt_at": min(int(current["expires_at"]), now + (3600 if attempts >= 12 else 300)),
        }
        return self._replace_answer(current, item)

    def score_answer(self, current, poll):
        """One CAS transaction owns score, terminal receipt, coverage and outbox deletion."""
        now = int(time.time())
        if int(current["expires_at"]) <= now:
            return self.finish_answer(current, "EXPIRED")
        chat_id = str(poll.get("chat_id") or str(poll.get("PK", "")).removeprefix("QUIZ#"))
        if not re.fullmatch(r"-[1-9][0-9]*", chat_id):
            return self.finish_answer(current, "INVALID")
        options = poll.get("options")
        correct = poll.get("correct_option_id")
        # Native DynamoDB numbers deserialize as Decimal; bool remains invalid.
        if (
            not isinstance(options, list)
            or isinstance(correct, bool)
            or not isinstance(correct, (int, Decimal))
            or correct != int(correct)
            or int(correct) not in range(len(options))
            or int(current["option_id"]) not in range(len(options))
        ):
            return self.finish_answer(current, "INVALID")
        points = poll.get("points", 1)
        if (
            isinstance(points, bool)
            or not isinstance(points, (int, Decimal))
            or points != int(points)
            or int(points) not in range(1, 101)
        ):
            return self.finish_answer(current, "INVALID")
        points = int(points)
        score = self.get_user_score(chat_id, current["user_id"]) or {}
        if current["poll_id"] in score.get("answered_poll_ids", []):
            return self.finish_answer(current, "DUPLICATE")
        day = datetime.fromtimestamp(int(current["received_at"]), _TZ).date()
        today = datetime.fromtimestamp(now, _TZ).date()
        daily = str(poll.get("record_key") or poll.get("SK", "")).startswith("DATE#")
        won = int(current["option_id"]) == int(correct)
        gained = points if won else 0
        week_points = gained if daily and day.isocalendar()[:2] == today.isocalendar()[:2] else 0
        values = {
            ":zero": 0,
            ":one": 1,
            ":points": gained,
            ":week": week_points,
            ":name": current["first_name"],
            ":revision": int(score.get("answer_revision", 0)),
        }
        expression = (
            "SET total_score = if_not_exists(total_score, :zero) + :points, "
            "week_score = if_not_exists(week_score, :zero) + :week, first_name = :name, "
            "answer_revision = :revision + :one"
        )
        answer_order = (int(current["received_at"]), int(current["update_id"]))
        previous_order = (int(score.get("last_answer_at", 0)), int(score.get("last_answer_update", 0)))
        # A late, older answer can add earned total points but cannot reset a newer streak.
        if answer_order >= previous_order:
            previous_correct = score.get("last_correct_date", "")
            streak = 0
            if won:
                if previous_correct == str(day):
                    streak = max(1, int(score.get("current_streak", 0)))
                elif previous_correct == str(day - timedelta(days=1)):
                    streak = int(score.get("current_streak", 0)) + 1
                else:
                    streak = 1
            values.update(
                {
                    ":streak": streak,
                    ":best": max(streak, int(score.get("best_streak", 0))),
                    ":day": str(day),
                    ":correct_day": str(day) if won else previous_correct,
                    ":at": answer_order[0],
                    ":update": answer_order[1],
                }
            )
            expression += (
                ", current_streak = :streak, best_streak = :best, last_answered_date = :day, "
                "last_correct_date = :correct_day, last_answer_at = :at, last_answer_update = :update"
            )
        score_op = {
            "Update": {
                "TableName": self._table.name,
                "Key": {"PK": f"SCORE#{chat_id}", "SK": f"USER#{current['user_id']}"},
                "UpdateExpression": expression,
                "ConditionExpression": (
                    "attribute_not_exists(answer_revision)"
                    if "answer_revision" not in score
                    else "answer_revision = :revision"
                ),
                "ExpressionAttributeValues": values,
            }
        }
        item = {
            **current,
            "state": "SCORED",
            "revision": int(current["revision"]) + 1,
            "completed_at": now,
            "chat_id": chat_id,
            "correct": won,
            "points": gained,
            "weekly_points": week_points,
        }
        poll_check = {
            "ConditionCheck": {
                "TableName": self._table.name,
                "Key": {"PK": poll["PK"], "SK": poll["SK"]},
                "ConditionExpression": "poll_id = :poll",
                "ExpressionAttributeValues": {":poll": current["poll_id"]},
            }
        }
        if "ttl" in poll:
            poll_check["ConditionCheck"]["ConditionExpression"] += " AND #ttl > :now"
            poll_check["ConditionCheck"]["ExpressionAttributeNames"] = {"#ttl": "ttl"}
            poll_check["ConditionCheck"]["ExpressionAttributeValues"][":now"] = int(time.time())
        return self._replace_answer(current, item, extra_operations=[score_op, poll_check])

    def answer_recovery_page(self, *, limit=100):
        control = self._answer_read({"PK": "QUIZ_ANSWER_RECOVERY", "SK": "CURSOR"})
        kwargs = {
            "KeyConditionExpression": Key("PK").eq("QUIZ_ANSWER_OUTBOX"),
            "ConsistentRead": True,
            "Limit": max(1, min(limit, 100)),
        }
        if control.get("cursor"):
            kwargs["ExclusiveStartKey"] = control["cursor"]
        page = self._table.query(**kwargs)
        return control, page.get("Items", []), page.get("LastEvaluatedKey")

    def checkpoint_answer_recovery(self, previous, cursor):
        item = {
            "PK": "QUIZ_ANSWER_RECOVERY",
            "SK": "CURSOR",
            "revision": int(previous.get("revision", 0)) + 1,
            "cursor": cursor or {},
        }
        op = {"TableName": self._table.name, "Item": item, "ConditionExpression": "attribute_not_exists(PK)"}
        if previous:
            op.update(
                ConditionExpression="#revision = :revision",
                ExpressionAttributeNames={"#revision": "revision"},
                ExpressionAttributeValues={":revision": previous["revision"]},
            )
        self._answer_transaction([{"Put": op}])

    def answer_coverage(self):
        return self._answer_read({"PK": "QUIZ_ANSWER_COVERAGE", "SK": "TOTAL"})

    def expire_answer_orphan(self, row):
        if int(row["expires_at"]) > int(time.time()):
            raise RuntimeError("Unexpired answer outbox lost its receipt")
        self._answer_transaction(
            [
                {
                    "ConditionCheck": {
                        "TableName": self._table.name,
                        "Key": _identity(row["poll_id"], row["user_id"]),
                        "ConditionExpression": "attribute_not_exists(PK)",
                    }
                },
                {
                    "Delete": {
                        "TableName": self._table.name,
                        "Key": {"PK": row["PK"], "SK": row["SK"]},
                        "ConditionExpression": "attribute_exists(PK)",
                    }
                },
                {
                    "Update": {
                        "TableName": self._table.name,
                        "Key": {"PK": "QUIZ_ANSWER_COVERAGE", "SK": "TOTAL"},
                        "UpdateExpression": "ADD expired_orphan :one",
                        "ExpressionAttributeValues": {":one": 1},
                    }
                },
            ]
        )

    def answer_pending_coverage(self, limit=1000):
        """Bounded diagnostics distinguish unresolved, paused-by-backoff and expired receipts."""
        counts = {"pending": 0, "unresolved": 0, "expired_due": 0, "future": 0, "oldest_age_seconds": 0}
        kwargs = {"KeyConditionExpression": Key("PK").eq("QUIZ_ANSWER_OUTBOX"), "ConsistentRead": True, "Limit": 100}
        seen, now = 0, int(time.time())
        for _ in range(max(1, min(int(limit), 1000) // 100)):
            page = self._table.query(**kwargs)
            for row in page.get("Items", []):
                answer = self.get_answer(row["poll_id"], row["user_id"])
                if not answer or answer["state"] in _TERMINAL:
                    continue
                seen += 1
                counts["unresolved" if answer["state"] == "UNRESOLVED" else "pending"] += 1
                counts["expired_due"] += int(int(answer["expires_at"]) <= now)
                counts["future"] += int(int(answer["next_attempt_at"]) > now)
                counts["oldest_age_seconds"] = max(counts["oldest_age_seconds"], now - int(answer["received_at"]))
            if not page.get("LastEvaluatedKey"):
                return {**counts, "seen": seen, "complete": True}
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
        return {**counts, "seen": seen, "complete": False}
