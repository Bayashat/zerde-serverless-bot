"""Quiz domain services for managing generation, sending and leaderboards."""

import html
import random
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services._publication import QuizPublicationBusy, QuizPublicationUnknown, validate_poll_receipt
from services.llm_provider import create_provider
from services.quiz_generator import CATEGORY_POOL, DIFFICULTY_POINTS, SUBTOPIC_POOL, QuizGenerator
from services.quiz_sender import PollSendRejected, PollSendUnknown, QuizSender
from services.repository import QuizRepository

logger = LoggerAdapter(get_logger(__name__), {})

_ALMATY_TZ = timezone(timedelta(hours=5))

_WEEKDAY_DIFFICULTY: dict[int, str] = {
    0: "easy",
    1: "easy_medium",
    2: "medium",
    3: "medium_hard",
    4: "hard",
}

_MEDALS = ["🥇", "🥈", "🥉"]
_SEASON_LENGTH = 4  # weeks per season
_AI_BANK_SOURCE = "ai-generated"
_AI_BANK_TARGET_PER_COMBO = 2
_AI_BANK_DEFAULT_BUILD_LIMIT = 20
_AI_BANK_DEFAULT_DIFFICULTIES = list(dict.fromkeys(_WEEKDAY_DIFFICULTY.values()))

# Categories that draw questions from a pre-built bank instead of AI
_BANKED_CATEGORIES: dict[str, list[str]] = {
    "cloud": ["aws-clf-c02"],
}

# Difficulty coverage declared per bank source. CLF-C02 is a foundations exam, so
# it should not satisfy medium/hard daily slots even if the user asks for AWS.
_BANK_SOURCE_DIFFICULTIES: dict[str, set[str]] = {
    "aws-clf-c02": {"easy", "easy_medium"},
    _AI_BANK_SOURCE: set(DIFFICULTY_POINTS),
}

# Existing CLF-C02 imports have per-item difficulty tags. For easy_medium, allow
# easy foundation questions too; for higher difficulties, do not use CLF-C02.
_BANK_ITEM_DIFFICULTY_COMPAT: dict[str, set[str]] = {
    "easy": {"easy"},
    "easy_medium": {"easy", "easy_medium"},
}

# Human-readable labels shown in the quiz announcement for each bank source
_BANK_SOURCE_LABELS: dict[str, str] = {
    "aws-clf-c02": "AWS CLF-C02 Practice Exam",
    "aws-dva-c02": "AWS Developer Associate Practice Exam",
    _AI_BANK_SOURCE: "Zerde AI Quiz Bank",
}

# Topic aliases that /genquiz should serve from the bank instead of AI.
# Keys are lowercased topic strings; values are the banked category name.
_GENQUIZ_TOPIC_TO_BANKED: dict[str, str] = {
    "cloud": "cloud",
    "aws": "cloud",
    "aws-clf": "cloud",
    "clf": "cloud",
    "clf-c02": "cloud",
    "aws-clf-c02": "cloud",
}


def _bank_sources_for_difficulty(category: str, difficulty: str) -> list[str]:
    """Return bank sources whose declared coverage includes the requested difficulty."""
    sources = _BANKED_CATEGORIES.get(category, [])
    all_difficulties = set(DIFFICULTY_POINTS)
    return [source for source in sources if difficulty in _BANK_SOURCE_DIFFICULTIES.get(source, all_difficulties)]


def _bank_item_difficulties_for_request(difficulty: str) -> set[str]:
    """Return item-level difficulties that can satisfy a requested difficulty."""
    return _BANK_ITEM_DIFFICULTY_COMPAT.get(difficulty, {difficulty})


def _queue_scope(source: str, subtopic: str | None = None) -> str:
    value = source if not subtopic else f"{source}:{subtopic}"
    return re.sub(r"[^a-zA-Z0-9_.:-]+", "-", value).strip("-")


class QuizService:
    """Orchestrates quiz operations (daily quiz and leaderboards)."""

    def __init__(self) -> None:
        provider = create_provider()
        self._generator = QuizGenerator(provider)
        self._sender = QuizSender()
        self._repo = QuizRepository()

    def get_difficulty(self, scheduled: datetime) -> str:
        """Bind difficulty to the original scheduled day, including delayed retries."""
        weekday = scheduled.astimezone(_ALMATY_TZ).weekday()
        return _WEEKDAY_DIFFICULTY.get(weekday, "easy")

    def build_announcement(self, lang: str, difficulty: str, source_label: str | None = None) -> str:
        """Build the announcement text for the daily quiz."""
        difficulty_label = get_translated_text(f"difficulty_{difficulty}", lang)
        points = DIFFICULTY_POINTS.get(difficulty, 1)
        text = get_translated_text(
            "quiz_announcement",
            lang,
            difficulty_label=difficulty_label,
            points=points,
        )
        if source_label:
            text += "\n" + get_translated_text("quiz_source_label", lang, source=source_label)
        return text

    def build_leaderboard_text(self, lang: str, entries: list[dict]) -> str:
        """Build the formatted leaderboard text, grouping users with equal scores."""
        header = get_translated_text("leaderboard_header", lang)
        if not entries:
            return header + get_translated_text("leaderboard_empty", lang)

        lines = []
        rank = 0
        current_score: int | None = None
        mentions: list[str] = []

        def flush_group() -> None:
            if current_score is None or not mentions:
                return
            medal = _MEDALS[rank - 1] if rank - 1 < len(_MEDALS) else f"{rank}."
            lines.append(f"{medal} {', '.join(mentions)} — <b>{current_score}</b>")

        for entry in entries:
            score = int(entry.get("week_score", 0))
            if current_score is None or score != current_score:
                flush_group()
                rank += 1
                current_score = score
                mentions = []
            user_id = entry.get("SK", "").replace("USER#", "")
            first_name = html.escape(str(entry.get("first_name", "User")))
            mention = f'<a href="tg://user?id={user_id}">{first_name}</a>'
            mentions.append(mention)

        flush_group()

        return header + "\n".join(lines)

    def build_season_text(self, lang: str, entries: list[dict]) -> str:
        """Build the season champion announcement text with competition-style tie handling."""
        header = get_translated_text("season_champion_header", lang)
        if not entries:
            return header + get_translated_text("season_champion_empty", lang)

        lines = []
        rank = 1
        for i, entry in enumerate(entries):
            if i > 0 and int(entry.get("season_wins", 0)) < int(entries[i - 1].get("season_wins", 0)):
                rank = i + 1
            medal = _MEDALS[rank - 1] if rank - 1 < len(_MEDALS) else f"{rank}."
            user_id = entry.get("SK", "").replace("USER#", "")
            first_name = entry.get("first_name", "User")
            wins = int(entry.get("season_wins", 0))
            mention = f'<a href="tg://user?id={user_id}">{first_name}</a>'
            wins_label = get_translated_text("season_wins_label", lang, wins=wins)
            lines.append(f"{medal} {mention} — <b>{wins_label}</b>")

        return header + "\n".join(lines)

    def process_leaderboard(self, chat_ids: list[str], lang: str) -> dict:
        """Send weekly leaderboard; on the 4th week also send the season champion."""
        sent_count = 0
        sent_chat_ids: list[str] = []
        failed: list[dict] = []
        for chat_id in chat_ids:
            entries = self._repo.get_leaderboard(str(chat_id))
            text = self.build_leaderboard_text(lang, entries)
            result = self._sender.send_message(str(chat_id), text)
            if result:
                sent_count += 1
                sent_chat_ids.append(str(chat_id))
                logger.info("Leaderboard sent", extra={"chat_id": chat_id, "lang": lang})

                # Record all co-winners tied for 1st place (only if they actually scored).
                if entries and int(entries[0].get("week_score", 0)) > 0:
                    top_score = int(entries[0].get("week_score", 0))
                    for entry in entries:
                        if int(entry.get("week_score", 0)) < top_score:
                            break
                        winner_id = entry.get("SK", "").replace("USER#", "")
                        self._repo.increment_season_wins(str(chat_id), winner_id, entry.get("first_name", "User"))

                # Advance season counter and check if the season is over
                week_count = self._repo.increment_season_week_count(str(chat_id))
                if week_count >= _SEASON_LENGTH:
                    season_entries = self._repo.get_season_leaderboard(str(chat_id))
                    season_text = self.build_season_text(lang, season_entries)
                    season_result = self._sender.send_message(str(chat_id), season_text)
                    if season_result:
                        logger.info("Season champion announced", extra={"chat_id": chat_id, "lang": lang})
                        # Credit all-time season title to every co-champion before resetting.
                        if season_entries:
                            top_wins = int(season_entries[0].get("season_wins", 0))
                            for entry in season_entries:
                                if int(entry.get("season_wins", 0)) < top_wins:
                                    break
                                champion_id = entry.get("SK", "").replace("USER#", "")
                                self._repo.increment_season_champion_count(
                                    str(chat_id), champion_id, entry.get("first_name", "User")
                                )
                        self._repo.reset_season_wins(str(chat_id))
                        self._repo.reset_season_week_count(str(chat_id))
                    else:
                        failed.append({"chat_id": str(chat_id), "step": "send_season_message"})
                        logger.error(
                            "Failed to send season champion announcement",
                            extra={"chat_id": chat_id},
                        )

                self._repo.reset_week_scores(str(chat_id))
            else:
                failed.append({"chat_id": str(chat_id), "step": "send_message"})
                logger.error("Failed to send leaderboard", extra={"chat_id": chat_id})

        return {
            "status": "partial" if failed and sent_count else "error" if failed else "ok",
            "action": "leaderboard",
            "sent": sent_count,
            "total": len(chat_ids),
            "sent_chat_ids": sent_chat_ids,
            "failed": failed,
        }

    def _pick_category_for_chat(self, chat_id: str) -> tuple[str, list[str]]:
        """Return (chosen_category, remaining_queue) using per-chat deck-of-cards rotation.

        Seeding by chat_id on first initialisation guarantees different chats start
        at different positions in the cycle even on a fresh deployment.
        """
        category_queue = self._repo.get_category_queue(chat_id)
        if not category_queue:
            # Unique seed per round: chat_id keeps cross-chat independence;
            # uuid4 ensures each new cycle produces a different shuffled order.
            rng = random.Random(f"{chat_id}::{uuid.uuid4().hex}")
            category_queue = rng.sample(CATEGORY_POOL, len(CATEGORY_POOL))
            logger.info("New category round started", extra={"chat_id": chat_id, "queue": category_queue})
        remaining = list(category_queue)
        category = remaining.pop(0)
        return category, remaining

    def _pick_subtopic_for_chat(self, category: str, chat_id: str, difficulty: str) -> tuple[str, list[str]]:
        """Return (chosen_subtopic, remaining_queue) for AI-generated questions."""
        subtopics = SUBTOPIC_POOL.get(category) or [category]
        subtopic_queue = self._repo.get_subtopic_queue(chat_id, category, difficulty)
        if not subtopic_queue:
            rng = random.Random(f"{chat_id}::{category}::{difficulty}::{uuid.uuid4().hex}")
            subtopic_queue = rng.sample(subtopics, len(subtopics))
            logger.info(
                "New subtopic round started",
                extra={
                    "chat_id": chat_id,
                    "category": category,
                    "difficulty": difficulty,
                    "total": len(subtopic_queue),
                },
            )
        remaining = list(subtopic_queue)
        subtopic = remaining.pop(0)
        return subtopic, remaining

    def _generate_ai_question_for_chat(
        self, category: str, chat_id: str, lang: str, difficulty: str
    ) -> tuple[dict, str, list[str]] | None:
        """Generate an AI question with a rotated subtopic deck."""
        subtopic, subtopic_remaining = self._pick_subtopic_for_chat(category, chat_id, difficulty)
        question = self._generator.generate_question(category, lang, difficulty, subtopic)
        if not question:
            return None
        return question, subtopic, subtopic_remaining

    def _pick_ai_bank_question_for_chat(
        self, category: str, chat_id: str, difficulty: str, subtopic: str
    ) -> tuple[dict, list[str]] | None:
        """Pick an AI-generated bank question for a concrete category/subtopic/difficulty."""
        scope = _queue_scope(_AI_BANK_SOURCE, subtopic)
        remaining = self._repo.get_question_queue(category, chat_id, difficulty, scope)
        if not remaining:
            all_keys = self._repo.get_bank_question_ids(
                category,
                [_AI_BANK_SOURCE],
                allowed_difficulties={difficulty},
                subtopic=subtopic,
            )
            if not all_keys:
                return None
            rng = random.Random(f"ai-bank:{chat_id}::{category}::{difficulty}::{subtopic}::{uuid.uuid4().hex}")
            remaining = rng.sample(all_keys, len(all_keys))
            logger.info(
                "New AI bank question round",
                extra={
                    "chat_id": chat_id,
                    "category": category,
                    "difficulty": difficulty,
                    "subtopic": subtopic,
                    "total": len(remaining),
                },
            )

        while remaining:
            key = remaining.pop(0)
            source, q_uuid = key.split("::", 1)
            item = self._repo.get_bank_question(category, source, q_uuid)
            if item:
                return (
                    {
                        "question": item["question"],
                        "options": list(item["options"]),
                        "correct_option_index": int(item["correct_option_id"]),
                        "explanation": item.get("explanation", ""),
                        "difficulty": difficulty,
                        "points": DIFFICULTY_POINTS.get(difficulty, 1),
                        "subtopic": item.get("subtopic"),
                        "fingerprint": item.get("fingerprint"),
                        "source_label": _BANK_SOURCE_LABELS.get(source, source),
                        "bank_source": source,
                        "bank_uuid": q_uuid,
                        "bank_scope": scope,
                    },
                    remaining,
                )
            logger.warning("AI bank question missing, skipping", extra={"uuid": q_uuid})

        return None

    def _pick_banked_question_for_chat(
        self, category: str, chat_id: str, difficulty: str
    ) -> tuple[dict, list[str]] | None:
        """Pick the next question from the bank for a chat using per-chat rotation.

        Returns (question_dict, remaining_queue) so the caller can persist the queue
        only after a successful poll send — prevents silent question loss on send failure.
        Returns None when the bank is empty or all entries are corrupt.
        """
        sources = _bank_sources_for_difficulty(category, difficulty)
        if not sources:
            logger.info(
                "No bank source covers requested difficulty",
                extra={"chat_id": chat_id, "category": category, "difficulty": difficulty},
            )
            return None

        remaining = self._repo.get_question_queue(category, chat_id, difficulty)
        if not remaining:
            all_keys = self._repo.get_bank_question_ids(
                category,
                sources,
                allowed_difficulties=_bank_item_difficulties_for_request(difficulty),
            )
            if not all_keys:
                return None
            # Unique seed per round: chat_id + category for cross-chat independence;
            # uuid4 ensures consecutive cycles produce different question orders.
            rng = random.Random(f"{chat_id}::{category}::{len(all_keys)}::{uuid.uuid4().hex}")
            remaining = rng.sample(all_keys, len(all_keys))
            logger.info(
                "New question bank round",
                extra={"chat_id": chat_id, "category": category, "total": len(remaining)},
            )

        # Pop until we find a valid question (handles any corrupt/missing bank entries)
        while remaining:
            key = remaining.pop(0)
            source, q_uuid = key.split("::", 1)
            item = self._repo.get_bank_question(category, source, q_uuid)
            if item:
                # Return remaining to caller; it commits to DynamoDB only after poll succeeds.
                return (
                    {
                        "question": item["question"],
                        "options": list(item["options"]),
                        "correct_option_index": int(item["correct_option_id"]),
                        "explanation": item.get("explanation", ""),
                        "difficulty": difficulty,
                        "points": DIFFICULTY_POINTS.get(difficulty, 1),
                        "subtopic": item.get("subtopic"),
                        "fingerprint": item.get("fingerprint"),
                        "source_label": _BANK_SOURCE_LABELS.get(source, source),
                    },
                    remaining,
                )
            logger.warning("Bank question missing, skipping", extra={"uuid": q_uuid})

        # No publication occurred, so leave the shared deck untouched.
        return None

    def _pick_banked_question_for_genquiz(
        self, category: str, chat_id: str, difficulty: str
    ) -> tuple[dict, list[str]] | None:
        """Pick the next on-demand question from the bank using a genquiz-specific per-chat queue.

        Returns (question_dict, remaining_queue) so the caller can persist the queue
        only after a successful poll send — prevents silent question loss on send failure.
        Uses a different DynamoDB key and shuffle seed from the daily rotation so that
        genquiz picks are unlikely to collide with upcoming daily questions.
        Daily category queue is never read or written by this method.
        """
        sources = _bank_sources_for_difficulty(category, difficulty)
        if not sources:
            logger.info(
                "No genquiz bank source covers requested difficulty",
                extra={"chat_id": chat_id, "category": category, "difficulty": difficulty},
            )
            return None

        remaining = self._repo.get_genquiz_question_queue(category, chat_id, difficulty)
        if not remaining:
            all_keys = self._repo.get_bank_question_ids(
                category,
                sources,
                allowed_difficulties=_bank_item_difficulties_for_request(difficulty),
            )
            if not all_keys:
                return None
            # "genquiz:" prefix keeps daily/genquiz shuffles independent;
            # uuid4 ensures consecutive cycles produce different question orders.
            rng = random.Random(f"genquiz:{chat_id}::{category}::{len(all_keys)}::{uuid.uuid4().hex}")
            remaining = rng.sample(all_keys, len(all_keys))
            logger.info(
                "New genquiz bank round",
                extra={"chat_id": chat_id, "category": category, "total": len(remaining)},
            )

        while remaining:
            key = remaining.pop(0)
            source, q_uuid = key.split("::", 1)
            item = self._repo.get_bank_question(category, source, q_uuid)
            if item:
                # Return remaining to caller; it commits to DynamoDB only after poll succeeds.
                return (
                    {
                        "question": item["question"],
                        "options": list(item["options"]),
                        "correct_option_index": int(item["correct_option_id"]),
                        "explanation": item.get("explanation", ""),
                        "difficulty": difficulty,
                        "points": DIFFICULTY_POINTS.get(difficulty, 1),
                        "subtopic": item.get("subtopic"),
                        "fingerprint": item.get("fingerprint"),
                        "source_label": _BANK_SOURCE_LABELS.get(source, source),
                    },
                    remaining,
                )
            logger.warning("Genquiz bank question missing, skipping", extra={"uuid": q_uuid})

        # No publication occurred, so leave the shared deck untouched.
        return None

    def _prepare_daily_publication(self, chat_id, lang, difficulty):
        category, remaining = self._pick_category_for_chat(str(chat_id))
        generated = None
        used_category = category
        # Holds the bank queue to commit only after a successful poll send (Bug #2).
        bank_remaining: list[str] | None = None
        bank_scope: str | None = None
        bank_source: str | None = None
        bank_uuid: str | None = None
        used_subtopic: str | None = None
        subtopic_remaining: list[str] | None = None
        commit_subtopic_deck = False

        used_subtopic, subtopic_remaining = self._pick_subtopic_for_chat(category, str(chat_id), difficulty)
        ai_bank_result = self._pick_ai_bank_question_for_chat(category, str(chat_id), difficulty, used_subtopic)
        if ai_bank_result:
            generated, bank_remaining = ai_bank_result
            bank_scope = generated.get("bank_scope")
            bank_source = generated.get("bank_source")
            bank_uuid = generated.get("bank_uuid")
            commit_subtopic_deck = True
            if lang != "en":
                translated = self._generator.translate_question(generated, lang)
                if translated:
                    generated = translated
                else:
                    logger.warning(
                        "AI bank translation failed, falling back to English bank question",
                        extra={"chat_id": chat_id, "lang": lang},
                    )

        if not generated and category in _BANKED_CATEGORIES:
            # Draw from pre-built question bank
            banked_result = self._pick_banked_question_for_chat(category, str(chat_id), difficulty)
            if banked_result:
                banked, bank_remaining = banked_result
                if lang == "en":
                    generated = banked
                else:
                    translated = self._generator.translate_question(banked, lang)
                    if translated:
                        generated = translated
                    else:
                        logger.warning(
                            "Translation failed, falling back to English bank question",
                            extra={"chat_id": chat_id, "lang": lang},
                        )
                        generated = banked
            else:
                logger.warning(
                    "Bank empty, falling back to AI",
                    extra={"chat_id": chat_id, "category": category},
                )
                ai_result = self._generator.generate_question(category, lang, difficulty, used_subtopic)
                if ai_result:
                    generated = ai_result
                    commit_subtopic_deck = True

        if not generated:
            # AI path for non-banked categories (or bank + AI both failed).
            # Track categories tried-but-failed so they can be reinserted at the back
            # of the queue, preserving the "each category appears once per cycle" guarantee.
            candidates = [category] + remaining
            tried_and_failed: list[str] = []
            restarted = False
            while candidates:
                cat = candidates.pop(0)
                used_subtopic, subtopic_remaining = self._pick_subtopic_for_chat(cat, str(chat_id), difficulty)
                ai_bank_result = self._pick_ai_bank_question_for_chat(cat, str(chat_id), difficulty, used_subtopic)
                if ai_bank_result:
                    generated, bank_remaining = ai_bank_result
                    bank_scope = generated.get("bank_scope")
                    bank_source = generated.get("bank_source")
                    bank_uuid = generated.get("bank_uuid")
                    commit_subtopic_deck = True
                    if lang != "en":
                        translated = self._generator.translate_question(generated, lang)
                        if translated:
                            generated = translated
                if not generated:
                    generated = self._generator.generate_question(cat, lang, difficulty, used_subtopic)
                    if generated:
                        commit_subtopic_deck = True
                if generated:
                    used_category = cat
                    # Restore skipped categories at the back so they still appear this cycle.
                    remaining = candidates if restarted else candidates + tried_and_failed
                    logger.info(
                        "Question generated",
                        extra={"chat_id": chat_id, "category": cat, "lang": lang, "difficulty": difficulty},
                    )
                    break
                tried_and_failed.append(cat)
                if not candidates and not restarted:
                    restarted = True
                    candidates = list(CATEGORY_POOL)
                    random.shuffle(candidates)
                    tried_and_failed.clear()
                    logger.warning(
                        "Queue exhausted, starting fresh category round",
                        extra={"chat_id": chat_id},
                    )

        if not generated:
            return None
        draft = self._draft(generated, used_category, lang, difficulty)
        draft["announcement"] = self.build_announcement(lang, difficulty, source_label=generated.get("source_label"))
        rotations = self._repo.publication_rotations(
            chat_id,
            category=used_category,
            category_remaining=remaining,
            bank_remaining=bank_remaining,
            bank_scope=bank_scope,
            bank_source=bank_source,
            bank_uuid=bank_uuid,
            difficulty=difficulty,
            subtopic=used_subtopic if commit_subtopic_deck else None,
            subtopic_remaining=subtopic_remaining if commit_subtopic_deck else None,
        )
        return draft, rotations

    @staticmethod
    def _draft(question, category, lang, difficulty, *, poll_question=None):
        return {
            "question": poll_question or question["question"],
            "options": question["options"],
            "correct_option_id": question["correct_option_index"],
            "explanation": question.get("explanation"),
            "category": category,
            "lang": lang,
            "difficulty": difficulty,
            "points": question["points"],
            "subtopic": question.get("subtopic"),
            "fingerprint": question.get("fingerprint"),
        }

    def _publish_request(self, chat_id, request_key, intent=None):
        try:
            execution = self._repo.claim_publication(chat_id, request_key, intent)
        except QuizPublicationBusy:
            return {"status": "pending", "reason": "publication in progress"}
        if execution["state"] == "DONE":
            return {"status": "ok", "sent": 1, "total": 1}
        if execution["state"] == "EXPIRED":
            return {"status": "expired", "reason": "quiz request expired before publication"}
        if execution["state"] in {"UNKNOWN", "CONFLICT"}:
            return {"status": "unknown", "reason": "poll outcome needs administrator verification"}
        if execution["state"] != "SENT":
            if execution["state"] == "GENERATING":
                self._repo._deck_snapshots = {}
                stored = execution["intent"]
                prepared = (
                    self._prepare_daily_publication(chat_id, stored["lang"], stored["difficulty"])
                    if stored["kind"] == "daily"
                    else self._prepare_on_demand_publication(
                        chat_id, stored["lang"], stored["topic"], stored["difficulty"], stored["interactive"]
                    )
                )
                if not prepared:
                    self._repo.mark_publication_failed(execution, unknown=False, reason="generation_failed")
                    return {"status": "error", "reason": "no valid question"}
                execution = self._repo.prepare_publication(execution, *prepared)
            draft = execution["draft"]
            if draft.get("announcement") and not execution.get("announcement_attempted"):
                execution = self._repo.mark_announcement_attempted(execution)
                self._sender.send_message(chat_id, draft["announcement"])
            execution = self._repo.mark_publication_sending(execution)
            try:
                result = self._sender.send_quiz_poll(
                    chat_id=chat_id,
                    question=draft["question"],
                    options=draft["options"],
                    correct_option_id=int(draft["correct_option_id"]),
                    explanation=draft.get("explanation"),
                )
                execution = self._repo.persist_poll_receipt(execution, result)
            except PollSendRejected:
                self._repo.mark_publication_failed(execution, unknown=False, reason="send_rejected")
                return {"status": "error", "reason": "Telegram rejected the quiz poll"}
            except (PollSendUnknown, QuizPublicationUnknown):
                self._repo.mark_publication_failed(execution, unknown=True, reason="send_unknown")
                return {"status": "unknown", "reason": "poll outcome needs administrator verification"}
        complete = self._repo.finalize_publication(execution)
        if complete["state"] != "DONE":
            return {"status": "error", "reason": "daily record conflict; known poll remains scoreable"}
        return {"status": "ok", "sent": 1, "total": 1}

    def process_daily_quiz(self, chat_ids: list[str], lang: str, *, scheduled_at=None) -> dict:
        if not chat_ids:
            return {"status": "skipped", "reason": "no chat_ids"}
        try:
            if type(scheduled_at) is int and scheduled_at > 0:
                scheduled = datetime.fromtimestamp(scheduled_at, timezone.utc)
            elif isinstance(scheduled_at, str):
                scheduled = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
                if scheduled.tzinfo is None:
                    raise ValueError("Scheduled timestamp needs its timezone")
            else:
                raise ValueError("Missing immutable scheduler timestamp")
            if scheduled.timestamp() > time.time() + 300:
                raise ValueError("Scheduled timestamp is in the future")
        except (ValueError, TypeError, OverflowError):
            return {"status": "error", "reason": "missing or invalid stable scheduled_at", "retryable": False}
        difficulty = self.get_difficulty(scheduled)
        day = scheduled.astimezone(_ALMATY_TZ).strftime("%Y-%m-%d")
        sent_chat_ids, failed = [], []
        for chat_id in chat_ids:
            chat_id = str(chat_id)
            try:
                # A pre-cutover successful daily publication also prevents another send.
                if self._repo.get_quiz_record(chat_id, f"DATE#{day}"):
                    sent_chat_ids.append(chat_id)
                    continue
                result = self._publish_request(
                    chat_id, f"DATE#{day}", {"kind": "daily", "lang": lang, "difficulty": difficulty}
                )
                if result["status"] == "ok":
                    sent_chat_ids.append(chat_id)
                else:
                    failed.append({"chat_id": chat_id, "step": result["status"], "reason": result["reason"]})
            except Exception as exc:
                logger.error(
                    "Daily quiz remains incomplete", extra={"chat_id": chat_id, "error_type": type(exc).__name__}
                )
                failed.append({"chat_id": chat_id, "step": "dependency"})
        return {
            "status": "partial" if failed and sent_chat_ids else "error" if failed else "ok",
            "sent": len(sent_chat_ids),
            "total": len(chat_ids),
            "sent_chat_ids": sent_chat_ids,
            "failed": failed,
        }

    def _prepare_on_demand_publication(self, chat_id, lang, topic, difficulty, interactive):
        banked_category = _GENQUIZ_TOPIC_TO_BANKED.get(topic.lower().strip())
        if banked_category:
            banked_result = self._pick_banked_question_for_genquiz(banked_category, str(chat_id), difficulty)
            if banked_result:
                question, remaining = banked_result
                if lang != "en":
                    translated = (
                        self._generator.translate_question(question, lang, interactive=True)
                        if interactive
                        else self._generator.translate_question(question, lang)
                    )
                    question = translated or question
                source_label = question.get("source_label", "")
                prefix = f"📚 {source_label}\n\n" if source_label else ""
                poll_question = prefix + question["question"][: 300 - len(prefix)]
                draft = self._draft(question, banked_category, lang, difficulty, poll_question=poll_question)
                rotations = self._repo.publication_rotations(
                    chat_id, category=banked_category, difficulty=difficulty, bank_remaining=remaining, genquiz=True
                )
                return draft, rotations
        question = (
            self._generator.generate_question(topic, lang, difficulty, interactive=True)
            if interactive
            else self._generator.generate_question(topic, lang, difficulty)
        )
        if not question:
            return None
        return self._draft(question, topic, lang, difficulty), []

    def process_on_demand_quiz(
        self, chat_id: str, lang: str, topic: str, difficulty: str, *, request_id: int | None = None, interactive=False
    ) -> dict:
        if type(request_id) is not int or request_id <= 0:
            return {"status": "error", "reason": "missing stable request identity", "retryable": False}
        return self._publish_request(
            str(chat_id),
            f"REQUEST#{request_id}",
            {"kind": "on_demand", "lang": lang, "topic": topic, "difficulty": difficulty, "interactive": interactive},
        )

    def reconcile_poll_receipt(self, chat_id, request_key, generation, poll_message, bot_user_id):
        # The caller's live-admin proof comes from the restricted Bot -> Quiz invoke
        # adapter; this entry validates the exact stored execution and own-bot poll.
        execution = self._repo._publication_read(self._repo.publication_key(chat_id, request_key))
        if not execution or execution.get("generation") != generation:
            return {"status": "unknown", "reason": "execution identity does not match"}
        if execution["state"] == "DONE":
            try:
                identity = validate_poll_receipt(
                    execution["draft"], poll_message, chat_id=chat_id, bot_user_id=bot_user_id
                )
            except QuizPublicationUnknown:
                return {"status": "unknown", "reason": "poll metadata does not match"}
            if identity["poll_id"] != execution["poll_id"]:
                return {"status": "unknown", "reason": "poll identity does not match"}
            return {"status": "ok", "sent": 1, "total": 1}
        try:
            sent = self._repo.persist_poll_receipt(
                execution, poll_message, bot_user_id=bot_user_id, reconciliation=True
            )
            complete = self._repo.finalize_publication(sent)
        except QuizPublicationUnknown:
            return {"status": "unknown", "reason": "poll metadata is incomplete or does not match"}
        return {"status": "ok" if complete["state"] == "DONE" else "error", "poll_id": complete["poll_id"]}

    def recover_publications(self, limit=50):
        """Resume a bounded page; UNKNOWN always remains a manual reconciliation case."""
        previous, rows, cursor = self._repo.publication_recovery_page(limit)
        counts = {"seen": len(rows), "recovered": 0, "unknown": 0, "expired": 0, "future": 0, "errors": 0}
        started = time.monotonic()
        for index, row in enumerate(rows):
            if time.monotonic() - started >= 200:
                break
            # Advance before potentially slow generation; a crash cannot starve later
            # rows, and the durable outbox is revisited on the next traversal.
            next_cursor = {"PK": row["PK"], "SK": row["SK"]} if index < len(rows) - 1 else cursor
            self._repo.checkpoint_publication_recovery(previous, next_cursor)
            previous = self._repo._publication_read({"PK": "QUIZ_PUBLICATION_RECOVERY", "SK": "CURSOR"})
            if int(row["next_attempt_at"]) > int(time.time()):
                counts["future"] += 1
                continue
            try:
                if not self._repo._publication_read(self._repo.publication_key(row["chat_id"], row["request_key"])):
                    self._repo.expire_publication_orphan(row)
                    counts["expired"] += 1
                    continue
                result = self._publish_request(row["chat_id"], row["request_key"])
                bucket = {"ok": "recovered", "unknown": "unknown", "expired": "expired"}.get(result["status"], "errors")
                counts[bucket] += 1
            except Exception as exc:
                logger.error("Quiz publication recovery failed", extra={"error_type": type(exc).__name__})
                counts["errors"] += 1
        if not rows:
            self._repo.checkpoint_publication_recovery(previous, cursor)
        if counts["errors"]:
            raise RuntimeError("Quiz publication recovery has retryable failures")
        return counts

    def build_generated_question_bank(
        self,
        *,
        max_questions: int = _AI_BANK_DEFAULT_BUILD_LIMIT,
        target_per_combo: int = _AI_BANK_TARGET_PER_COMBO,
        categories: list[str] | None = None,
        difficulties: list[str] | None = None,
        subtopics_by_category: dict[str, list[str]] | None = None,
    ) -> dict:
        """Top up the AI-generated question bank without sending Telegram polls."""
        categories_to_build = categories or list(CATEGORY_POOL)
        difficulties_to_build = difficulties or _AI_BANK_DEFAULT_DIFFICULTIES
        created = 0
        skipped_existing = 0
        failed = 0

        for category in categories_to_build:
            subtopics = (subtopics_by_category or {}).get(category) or SUBTOPIC_POOL.get(category, [category])
            for subtopic in subtopics:
                for difficulty in difficulties_to_build:
                    existing = self._repo.get_bank_question_summaries(
                        category, _AI_BANK_SOURCE, difficulty=difficulty, subtopic=subtopic
                    )
                    fingerprints = {item.get("fingerprint") for item in existing if item.get("fingerprint")}
                    needed = max(0, target_per_combo - len(existing))
                    if needed == 0:
                        skipped_existing += 1
                        continue

                    for _ in range(needed):
                        if created >= max_questions:
                            return {
                                "status": "ok",
                                "action": "build_question_bank",
                                "created": created,
                                "failed": failed,
                                "skipped_existing": skipped_existing,
                                "limit": max_questions,
                            }
                        question = self._generator.generate_question(category, "en", difficulty, subtopic)
                        if not question:
                            failed += 1
                            continue
                        fingerprint = question.get("fingerprint")
                        if fingerprint in fingerprints:
                            skipped_existing += 1
                            continue
                        question["difficulty_band"] = "ai-generated"
                        if self._repo.save_generated_bank_question(category, _AI_BANK_SOURCE, question):
                            created += 1
                            fingerprints.add(fingerprint)
                        else:
                            skipped_existing += 1

        return {
            "status": "ok",
            "action": "build_question_bank",
            "created": created,
            "failed": failed,
            "skipped_existing": skipped_existing,
            "limit": max_questions,
        }

    def process_on_demand_quiz_with_feedback(
        self,
        chat_id: str,
        lang: str,
        topic: str,
        difficulty: str,
        *,
        reply_to_message_id: int | None = None,
    ) -> dict:
        """Run on-demand quiz and notify the user when async generation fails."""
        result = self.process_on_demand_quiz(
            chat_id, lang, topic, difficulty, request_id=reply_to_message_id, interactive=True
        )
        if result.get("status") == "ok":
            return result

        reason = str(result.get("reason") or "unknown error")
        text = get_translated_text("genquiz_failed", lang, reason=reason)
        sent = self._sender.send_message(str(chat_id), text, reply_to_message_id=reply_to_message_id)
        if not sent:
            logger.error(
                "Failed to send genquiz failure feedback",
                extra={"chat_id": chat_id, "reason": reason, "reply_to_message_id": reply_to_message_id},
            )
        return result
