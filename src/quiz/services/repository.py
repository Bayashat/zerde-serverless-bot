"""DynamoDB repository for Quiz Lambda — writes quiz records and category metadata."""

import time
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from core.config import TABLE_NAME
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

_ALMATY_TZ = timezone(timedelta(hours=5))
_TTL_DAYS = 90


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

    def get_bank_question_ids(self, category: str, sources: list[str]) -> list[str]:
        """Return all '{source}::{uuid}' keys from the question bank for a category."""
        all_keys: list[str] = []
        for source in sources:
            try:
                query_kwargs: dict = {
                    "KeyConditionExpression": Key("PK").eq(f"BANK#{category}#{source}"),
                    "ProjectionExpression": "SK",
                }
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

    def get_question_queue(self, category: str, chat_id: str) -> list[str]:
        """Read the per-chat per-category question queue (list of 'source::uuid' keys)."""
        try:
            resp = self._table.get_item(
                Key={"PK": f"META#q_queue#{category}#{chat_id}", "SK": "LATEST"},
                ConsistentRead=False,
            )
            item = resp.get("Item")
            if item and "remaining" in item:
                return list(item["remaining"])
            return []
        except Exception as e:
            logger.error("Failed to get question queue", extra={"error": str(e)})
            return []

    def save_question_queue(self, category: str, chat_id: str, remaining: list[str]) -> None:
        """Write the per-chat per-category question queue."""
        try:
            self._table.put_item(
                Item={
                    "PK": f"META#q_queue#{category}#{chat_id}",
                    "SK": "LATEST",
                    "remaining": remaining,
                }
            )
        except Exception as e:
            logger.error("Failed to save question queue", extra={"error": str(e)})

    # ── Genquiz (on-demand) question queue — separate from daily rotation ─────

    def get_genquiz_question_queue(self, category: str, chat_id: str) -> list[str]:
        """Read the per-chat on-demand genquiz question queue (independent of daily rotation)."""
        try:
            resp = self._table.get_item(
                Key={"PK": f"META#genquiz_q_queue#{category}#{chat_id}", "SK": "LATEST"},
                ConsistentRead=False,
            )
            item = resp.get("Item")
            if item and "remaining" in item:
                return list(item["remaining"])
            return []
        except Exception as e:
            logger.error("Failed to get genquiz question queue", extra={"error": str(e)})
            return []

    def save_genquiz_question_queue(self, category: str, chat_id: str, remaining: list[str]) -> None:
        """Write the per-chat on-demand genquiz question queue."""
        try:
            self._table.put_item(
                Item={
                    "PK": f"META#genquiz_q_queue#{category}#{chat_id}",
                    "SK": "LATEST",
                    "remaining": remaining,
                }
            )
        except Exception as e:
            logger.error("Failed to save genquiz question queue", extra={"error": str(e)})

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
    ) -> None:
        """Write a daily quiz record for a chat."""
        now = datetime.now(_ALMATY_TZ)
        today = now.strftime("%Y-%m-%d")
        ttl = int(time.time()) + (_TTL_DAYS * 86400)

        try:
            self._table.put_item(
                Item={
                    "PK": f"QUIZ#{chat_id}",
                    "SK": f"DATE#{today}",
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
                    "sent_at": now.isoformat(),
                    "ttl": ttl,
                }
            )
            logger.info("Quiz record saved", extra={"chat_id": chat_id, "date": today})
        except Exception as e:
            logger.error("Failed to save quiz record", extra={"chat_id": chat_id, "error": str(e)})
            raise
