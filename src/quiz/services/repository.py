"""DynamoDB repository for Quiz Lambda — writes quiz records and category metadata."""

import hashlib
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
from core.config import TABLE_NAME
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

_ALMATY_TZ = timezone(timedelta(hours=5))
_TTL_DAYS = 90


def _question_fingerprint(question: str) -> str:
    normalized = re.sub(r"[^a-z0-9\s]+", " ", question.lower())
    normalized = re.sub(r"\b\d+\b", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


class QuizRepository:
    """Writes daily quiz records and category metadata to DynamoDB."""

    def __init__(self) -> None:
        self._table = boto3.resource("dynamodb").Table(TABLE_NAME)
        logger.info("QuizRepository initialized", extra={"table": TABLE_NAME})

    def get_category_queue(self, chat_id: str) -> list[str]:
        """Read the per-chat remaining category queue from metadata."""
        try:
            resp = self._table.get_item(
                Key={"PK": f"META#category#{chat_id}", "SK": "LATEST"},
                ConsistentRead=False,
            )
            item = resp.get("Item")
            if item and "remaining" in item:
                return list(item["remaining"])
            return []
        except Exception as e:
            logger.error("Failed to get category queue", extra={"error": str(e)})
            return []

    def save_category_queue(self, remaining: list[str], used_category: str, chat_id: str) -> None:
        """Write the per-chat updated category queue and last-used category."""
        today = datetime.now(_ALMATY_TZ).strftime("%Y-%m-%d")
        try:
            self._table.put_item(
                Item={
                    "PK": f"META#category#{chat_id}",
                    "SK": "LATEST",
                    "remaining": remaining,
                    "category": used_category,
                    "date": today,
                }
            )
        except Exception as e:
            logger.error("Failed to save category queue", extra={"error": str(e)})

    def get_subtopic_queue(self, chat_id: str, category: str, difficulty: str) -> list[str]:
        """Read the per-chat subtopic deck for a category/difficulty pair."""
        try:
            resp = self._table.get_item(
                Key={"PK": f"META#subtopic#{category}#{difficulty}#{chat_id}", "SK": "LATEST"},
                ConsistentRead=False,
            )
            item = resp.get("Item")
            if item and "remaining" in item:
                return list(item["remaining"])
            return []
        except Exception as e:
            logger.error("Failed to get subtopic queue", extra={"error": str(e)})
            return []

    def save_subtopic_queue(
        self,
        chat_id: str,
        category: str,
        difficulty: str,
        remaining: list[str],
        used_subtopic: str,
    ) -> None:
        """Write the updated per-chat subtopic deck."""
        today = datetime.now(_ALMATY_TZ).strftime("%Y-%m-%d")
        try:
            self._table.put_item(
                Item={
                    "PK": f"META#subtopic#{category}#{difficulty}#{chat_id}",
                    "SK": "LATEST",
                    "remaining": remaining,
                    "category": category,
                    "difficulty": difficulty,
                    "subtopic": used_subtopic,
                    "date": today,
                }
            )
        except Exception as e:
            logger.error("Failed to save subtopic queue", extra={"error": str(e)})

    def _query_all_pages(self, chat_id: str) -> list[dict[str, Any]]:
        """Paginate through all DynamoDB items for a SCORE#{chat_id} partition."""
        query_kwargs: dict = {"KeyConditionExpression": Key("PK").eq(f"SCORE#{chat_id}")}
        items: list[dict[str, Any]] = []
        while True:
            resp = self._table.query(**query_kwargs)
            items.extend(resp.get("Items", []))
            last_key = resp.get("LastEvaluatedKey")
            if not last_key:
                break
            query_kwargs["ExclusiveStartKey"] = last_key
        return items

    def get_leaderboard(self, chat_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return top N users for a chat sorted by week_score descending."""
        try:
            items = self._query_all_pages(chat_id)
            sorted_items = sorted(items, key=lambda x: x.get("week_score", 0), reverse=True)
            return sorted_items[:limit]
        except Exception as e:
            logger.error("Failed to get leaderboard", extra={"chat_id": chat_id, "error": str(e)})
            return []

    def reset_week_scores(self, chat_id: str) -> None:
        """Reset week_score to 0 for all users in a chat after the leaderboard is sent."""
        try:
            items = self._query_all_pages(chat_id)
            for item in items:
                for attempt in range(3):
                    try:
                        self._table.update_item(
                            Key={"PK": item["PK"], "SK": item["SK"]},
                            UpdateExpression="SET week_score = :zero",
                            ExpressionAttributeValues={":zero": 0},
                        )
                        break
                    except Exception:
                        if attempt == 2:
                            raise
                        time.sleep(0.1 * (2**attempt))
            logger.info("Week scores reset", extra={"chat_id": chat_id, "users": len(items)})
        except Exception as e:
            logger.error("Failed to reset week scores", extra={"chat_id": chat_id, "error": str(e)})

    # ── Season helpers ────────────────────────────────────────────────────

    def increment_season_week_count(self, chat_id: str) -> int:
        """Atomically increment the season week counter and return the new value."""
        try:
            resp = self._table.update_item(
                Key={"PK": f"META#season#{chat_id}", "SK": "LATEST"},
                UpdateExpression="ADD week_count :one",
                ExpressionAttributeValues={":one": 1},
                ReturnValues="UPDATED_NEW",
            )
            return int(resp["Attributes"]["week_count"])
        except Exception as e:
            logger.error("Failed to increment season week count", extra={"chat_id": chat_id, "error": str(e)})
            return 0

    def reset_season_week_count(self, chat_id: str) -> None:
        """Reset the season week counter to 0."""
        try:
            self._table.update_item(
                Key={"PK": f"META#season#{chat_id}", "SK": "LATEST"},
                UpdateExpression="SET week_count = :zero",
                ExpressionAttributeValues={":zero": 0},
            )
        except Exception as e:
            logger.error("Failed to reset season week count", extra={"chat_id": chat_id, "error": str(e)})

    def increment_season_wins(self, chat_id: str, user_id: str, first_name: str) -> None:
        """Add 1 to the weekly winner's season_wins counter."""
        try:
            self._table.update_item(
                Key={"PK": f"SCORE#{chat_id}", "SK": f"USER#{user_id}"},
                UpdateExpression=(
                    "SET season_wins = if_not_exists(season_wins, :zero) + :one," "    first_name = :name"
                ),
                ExpressionAttributeValues={":zero": 0, ":one": 1, ":name": first_name},
            )
            logger.info("Season win recorded", extra={"chat_id": chat_id, "user_id": user_id})
        except Exception as e:
            logger.error("Failed to increment season wins", extra={"chat_id": chat_id, "error": str(e)})

    def get_season_leaderboard(self, chat_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return top N users sorted by season_wins descending (only users with ≥1 win)."""
        try:
            items = self._query_all_pages(chat_id)
            active = [i for i in items if int(i.get("season_wins", 0)) > 0]
            return sorted(active, key=lambda x: int(x.get("season_wins", 0)), reverse=True)[:limit]
        except Exception as e:
            logger.error("Failed to get season leaderboard", extra={"chat_id": chat_id, "error": str(e)})
            return []

    def increment_season_champion_count(self, chat_id: str, user_id: str, first_name: str) -> None:
        """Increment the all-time season champion counter for the overall season winner.

        Unlike season_wins (which resets every 4 weeks), this counter is never cleared —
        it tracks how many seasons a user has finished in 1st place across all time.
        """
        try:
            self._table.update_item(
                Key={"PK": f"SCORE#{chat_id}", "SK": f"USER#{user_id}"},
                UpdateExpression=(
                    "SET season_champion_count = if_not_exists(season_champion_count, :zero) + :one,"
                    "    first_name = :name"
                ),
                ExpressionAttributeValues={":zero": 0, ":one": 1, ":name": first_name},
            )
            logger.info(
                "Season champion count incremented",
                extra={"chat_id": chat_id, "user_id": user_id},
            )
        except Exception as e:
            logger.error(
                "Failed to increment season champion count",
                extra={"chat_id": chat_id, "user_id": user_id, "error": str(e)},
            )

    def reset_season_wins(self, chat_id: str) -> None:
        """Reset season_wins to 0 for all users in a chat after the season announcement."""
        try:
            items = self._query_all_pages(chat_id)
            for item in items:
                for attempt in range(3):
                    try:
                        self._table.update_item(
                            Key={"PK": item["PK"], "SK": item["SK"]},
                            UpdateExpression="SET season_wins = :zero",
                            ExpressionAttributeValues={":zero": 0},
                        )
                        break
                    except Exception:
                        if attempt == 2:
                            raise
                        time.sleep(0.1 * (2**attempt))
            logger.info("Season wins reset", extra={"chat_id": chat_id, "users": len(items)})
        except Exception as e:
            logger.error("Failed to reset season wins", extra={"chat_id": chat_id, "error": str(e)})

    # ── Question bank helpers ─────────────────────────────────────────────

    def get_bank_question_ids(
        self,
        category: str,
        sources: list[str],
        allowed_difficulties: set[str] | None = None,
        subtopic: str | None = None,
    ) -> list[str]:
        """Return all '{source}::{uuid}' bank keys for a category, optionally by difficulty."""
        all_keys: list[str] = []
        for source in sources:
            try:
                query_kwargs: dict = {
                    "KeyConditionExpression": Key("PK").eq(f"BANK#{category}#{source}"),
                    "ProjectionExpression": "SK",
                }
                filter_expression = None
                if allowed_difficulties:
                    filter_expression = Attr("difficulty").is_in(list(allowed_difficulties))
                if subtopic:
                    subtopic_filter = Attr("subtopic").eq(subtopic)
                    filter_expression = (
                        subtopic_filter if filter_expression is None else filter_expression & subtopic_filter
                    )
                if filter_expression is not None:
                    query_kwargs["FilterExpression"] = filter_expression
                resp = self._table.query(**query_kwargs)
                items = list(resp.get("Items", []))
                while "LastEvaluatedKey" in resp:
                    resp = self._table.query(**query_kwargs, ExclusiveStartKey=resp["LastEvaluatedKey"])
                    items.extend(resp.get("Items", []))
                all_keys.extend(f"{source}::{item['SK'].replace('Q#', '')}" for item in items)
            except Exception as e:
                logger.error(
                    "Failed to get bank question IDs",
                    extra={"category": category, "source": source, "error": str(e)},
                )
        return all_keys

    def get_bank_question_summaries(
        self,
        category: str,
        source: str,
        difficulty: str | None = None,
        subtopic: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return lightweight bank metadata for counting and dedupe."""
        try:
            query_kwargs: dict = {
                "KeyConditionExpression": Key("PK").eq(f"BANK#{category}#{source}"),
                "ProjectionExpression": "SK, difficulty, subtopic, fingerprint, created_at, last_used_at",
            }
            filter_expression = None
            if difficulty:
                filter_expression = Attr("difficulty").eq(difficulty)
            if subtopic:
                subtopic_filter = Attr("subtopic").eq(subtopic)
                filter_expression = (
                    subtopic_filter if filter_expression is None else filter_expression & subtopic_filter
                )
            if filter_expression is not None:
                query_kwargs["FilterExpression"] = filter_expression

            items: list[dict[str, Any]] = []
            resp = self._table.query(**query_kwargs)
            items.extend(resp.get("Items", []))
            while "LastEvaluatedKey" in resp:
                resp = self._table.query(**query_kwargs, ExclusiveStartKey=resp["LastEvaluatedKey"])
                items.extend(resp.get("Items", []))
            return items
        except Exception as e:
            logger.error(
                "Failed to get bank question summaries",
                extra={
                    "category": category,
                    "source": source,
                    "difficulty": difficulty,
                    "subtopic": subtopic,
                    "error": str(e),
                },
            )
            return []

    def save_generated_bank_question(self, category: str, source: str, question: dict) -> bool:
        """Write an AI-generated bank question. Returns False on duplicate UUID collision."""
        q_uuid = question.get("uuid") or str(uuid.uuid4())
        now = datetime.now(_ALMATY_TZ).isoformat()
        try:
            self._table.put_item(
                Item={
                    "PK": f"BANK#{category}#{source}",
                    "SK": f"Q#{q_uuid}",
                    "uuid": q_uuid,
                    "source": source,
                    "category": category,
                    "subtopic": question.get("subtopic"),
                    "difficulty": question.get("difficulty"),
                    "difficulty_band": question.get("difficulty_band", "ai-generated"),
                    "fingerprint": question.get("fingerprint") or _question_fingerprint(question["question"]),
                    "question": question["question"],
                    "options": list(question["options"]),
                    "correct_option_id": int(question["correct_option_index"]),
                    "explanation": question.get("explanation", ""),
                    "created_at": now,
                    "last_used_at": None,
                },
                ConditionExpression=Attr("PK").not_exists(),
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.warning("Generated bank UUID already exists", extra={"category": category, "uuid": q_uuid})
                return False
            logger.error("Failed to save generated bank question", extra={"category": category, "error": str(e)})
            raise

    def get_bank_question(self, category: str, source: str, uuid: str) -> dict | None:
        """Read a single question from the bank by its UUID."""
        try:
            resp = self._table.get_item(
                Key={"PK": f"BANK#{category}#{source}", "SK": f"Q#{uuid}"},
            )
            return resp.get("Item")
        except Exception as e:
            logger.error(
                "Failed to get bank question",
                extra={"category": category, "source": source, "uuid": uuid, "error": str(e)},
            )
            return None

    def mark_bank_question_used(self, category: str, source: str, uuid: str) -> None:
        """Record best-effort usage timestamp on a bank question."""
        try:
            self._table.update_item(
                Key={"PK": f"BANK#{category}#{source}", "SK": f"Q#{uuid}"},
                UpdateExpression="SET last_used_at = :now ADD use_count :one",
                ExpressionAttributeValues={":now": datetime.now(_ALMATY_TZ).isoformat(), ":one": 1},
            )
        except Exception as e:
            logger.warning(
                "Failed to mark bank question used",
                extra={"category": category, "source": source, "uuid": uuid, "error": str(e)},
            )

    def get_question_queue(
        self, category: str, chat_id: str, difficulty: str | None = None, scope: str | None = None
    ) -> list[str]:
        """Read the per-chat per-category question queue (list of 'source::uuid' keys)."""
        difficulty_suffix = f"#{difficulty}" if difficulty else ""
        scope_suffix = f"#{scope}" if scope else ""
        try:
            resp = self._table.get_item(
                Key={"PK": f"META#q_queue#{category}{difficulty_suffix}{scope_suffix}#{chat_id}", "SK": "LATEST"},
                ConsistentRead=False,
            )
            item = resp.get("Item")
            if item and "remaining" in item:
                return list(item["remaining"])
            return []
        except Exception as e:
            logger.error("Failed to get question queue", extra={"error": str(e)})
            return []

    def save_question_queue(
        self,
        category: str,
        chat_id: str,
        remaining: list[str],
        difficulty: str | None = None,
        scope: str | None = None,
    ) -> None:
        """Write the per-chat per-category question queue."""
        difficulty_suffix = f"#{difficulty}" if difficulty else ""
        scope_suffix = f"#{scope}" if scope else ""
        try:
            self._table.put_item(
                Item={
                    "PK": f"META#q_queue#{category}{difficulty_suffix}{scope_suffix}#{chat_id}",
                    "SK": "LATEST",
                    "remaining": remaining,
                }
            )
        except Exception as e:
            logger.error("Failed to save question queue", extra={"error": str(e)})

    # ── Genquiz (on-demand) question queue — separate from daily rotation ─────

    def get_genquiz_question_queue(self, category: str, chat_id: str, difficulty: str | None = None) -> list[str]:
        """Read the per-chat on-demand genquiz question queue (independent of daily rotation)."""
        difficulty_suffix = f"#{difficulty}" if difficulty else ""
        try:
            resp = self._table.get_item(
                Key={"PK": f"META#genquiz_q_queue#{category}{difficulty_suffix}#{chat_id}", "SK": "LATEST"},
                ConsistentRead=False,
            )
            item = resp.get("Item")
            if item and "remaining" in item:
                return list(item["remaining"])
            return []
        except Exception as e:
            logger.error("Failed to get genquiz question queue", extra={"error": str(e)})
            return []

    def save_genquiz_question_queue(
        self, category: str, chat_id: str, remaining: list[str], difficulty: str | None = None
    ) -> None:
        """Write the per-chat on-demand genquiz question queue."""
        difficulty_suffix = f"#{difficulty}" if difficulty else ""
        try:
            self._table.put_item(
                Item={
                    "PK": f"META#genquiz_q_queue#{category}{difficulty_suffix}#{chat_id}",
                    "SK": "LATEST",
                    "remaining": remaining,
                }
            )
        except Exception as e:
            logger.error("Failed to save genquiz question queue", extra={"error": str(e)})

    def get_today_quiz_record(self, chat_id: str) -> dict[str, Any] | None:
        """Return today's quiz record for a chat, or None if not yet sent."""
        today = datetime.now(_ALMATY_TZ).strftime("%Y-%m-%d")
        try:
            resp = self._table.get_item(
                Key={"PK": f"QUIZ#{chat_id}", "SK": f"DATE#{today}"},
                ConsistentRead=True,
            )
            return resp.get("Item")
        except ClientError as e:
            logger.error("Failed to read today quiz record", extra={"chat_id": chat_id, "error": str(e)})
            return None

    def save_quiz_record(
        self,
        chat_id: str,
        question: str,
        options: list[str],
        correct_option_id: int,
        explanation: str | None,
        category: str,
        lang: str,
        poll_id: str,
        message_id: int,
        difficulty: str = "easy",
        points: int = 1,
        subtopic: str | None = None,
        fingerprint: str | None = None,
        record_key: str | None = None,
    ) -> bool:
        """Write a quiz poll lookup record for a chat.

        Daily quizzes use ``DATE#YYYY-MM-DD``. On-demand quizzes pass a unique
        ``record_key`` (normally ``ONDEMAND#<poll_id>``) so their poll answers can
        be scored without colliding with the daily idempotency record.
        """
        now = datetime.now(_ALMATY_TZ)
        today = now.strftime("%Y-%m-%d")
        sk = record_key or f"DATE#{today}"
        ttl = int(time.time()) + (_TTL_DAYS * 86400)

        try:
            self._table.put_item(
                Item={
                    "PK": f"QUIZ#{chat_id}",
                    "SK": sk,
                    "question": question,
                    "options": options,
                    "correct_option_id": correct_option_id,
                    "explanation": explanation,
                    "category": category,
                    "lang": lang,
                    "poll_id": str(poll_id),
                    "message_id": message_id,
                    "difficulty": difficulty,
                    "points": points,
                    "subtopic": subtopic,
                    "fingerprint": fingerprint or _question_fingerprint(question),
                    "sent_at": now.isoformat(),
                    "ttl": ttl,
                },
                ConditionExpression=Attr("PK").not_exists(),
            )
            logger.info("Quiz record saved", extra={"chat_id": chat_id, "sk": sk, "poll_id": poll_id})
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.warning(
                    "Quiz record already exists, skipping save",
                    extra={"chat_id": chat_id, "sk": sk, "poll_id": poll_id},
                )
                return False
            logger.error("Failed to save quiz record", extra={"chat_id": chat_id, "error": str(e)})
            raise
