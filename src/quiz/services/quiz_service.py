"""Quiz domain services for managing generation, sending and leaderboards."""

import random
import re
import uuid
from datetime import datetime, timedelta, timezone

from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.llm_provider import create_provider
from services.quiz_generator import CATEGORY_POOL, DIFFICULTY_POINTS, SUBTOPIC_POOL, QuizGenerator
from services.quiz_sender import QuizSender
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

    def get_difficulty(self) -> str:
        """Return the difficulty level for today (Almaty time)."""
        weekday = datetime.now(_ALMATY_TZ).weekday()
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
        """Build the formatted leaderboard text with competition-style tie handling.

        Users with equal scores share the same rank and medal.
        Example: two users at 7 pts both get 🥈; the next unique score is rank 4.
        """
        header = get_translated_text("leaderboard_header", lang)
        if not entries:
            return header + get_translated_text("leaderboard_empty", lang)

        lines = []
        rank = 1
        for i, entry in enumerate(entries):
            if i > 0 and int(entry.get("week_score", 0)) < int(entries[i - 1].get("week_score", 0)):
                rank = i + 1  # standard competition ranking: rank jumps to actual position
            medal = _MEDALS[rank - 1] if rank - 1 < len(_MEDALS) else f"{rank}."
            user_id = entry.get("SK", "").replace("USER#", "")
            first_name = entry.get("first_name", "User")
            score = int(entry.get("week_score", 0))
            mention = f'<a href="tg://user?id={user_id}">{first_name}</a>'
            lines.append(f"{medal} {mention} — <b>{score}</b>")

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
            "status": "ok",
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

        self._repo.save_question_queue(category, chat_id, remaining, difficulty, scope)
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

        # All entries were corrupt/missing — persist empty queue so next call refills from bank.
        self._repo.save_question_queue(category, chat_id, remaining, difficulty)
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

        # All entries were corrupt/missing — persist empty queue so next call refills from bank.
        self._repo.save_genquiz_question_queue(category, chat_id, remaining, difficulty)
        return None

    def process_daily_quiz(self, chat_ids: list[str], lang: str) -> dict:
        """Generate and send the daily quiz to each chat with independent category rotation."""
        if not chat_ids:
            logger.warning("No chat_ids in event payload")
            return {"status": "skipped", "reason": "no chat_ids"}

        difficulty = self.get_difficulty()
        logger.info("Difficulty for today", extra={"difficulty": difficulty, "lang": lang})

        sent_count = 0
        sent_chat_ids: list[str] = []
        failed: list[dict] = []

        for chat_id in chat_ids:
            existing = self._repo.get_today_quiz_record(str(chat_id))
            if existing:
                logger.info(
                    "Daily quiz already sent for this chat today, skipping",
                    extra={"chat_id": chat_id, "poll_id": existing.get("poll_id")},
                )
                sent_count += 1
                sent_chat_ids.append(str(chat_id))
                continue

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
                logger.error(
                    "Failed to generate a valid question after all categories",
                    extra={"chat_id": chat_id},
                )
                failed.append({"chat_id": str(chat_id), "step": "generate"})
                continue

            announcement = self.build_announcement(lang, difficulty, source_label=generated.get("source_label"))
            if not self._sender.send_message(str(chat_id), announcement):
                failed.append({"chat_id": str(chat_id), "step": "announcement"})
                continue

            poll_result = self._sender.send_quiz_poll(
                chat_id=chat_id,
                question=generated["question"],
                options=generated["options"],
                correct_option_id=generated["correct_option_index"],
                explanation=generated.get("explanation"),
            )
            if poll_result:
                poll_id = str(poll_result.get("poll", {}).get("id", ""))
                message_id = poll_result.get("message_id", 0)
                self._repo.save_quiz_record(
                    chat_id=chat_id,
                    question=generated["question"],
                    options=generated["options"],
                    correct_option_id=generated["correct_option_index"],
                    explanation=generated.get("explanation"),
                    category=used_category,
                    lang=lang,
                    poll_id=poll_id,
                    message_id=message_id,
                    difficulty=difficulty,
                    points=generated["points"],
                    subtopic=generated.get("subtopic"),
                    fingerprint=generated.get("fingerprint"),
                )
                # Commit bank question queue only after confirmed send (Bug #2 fix).
                if bank_remaining is not None:
                    self._repo.save_question_queue(used_category, str(chat_id), bank_remaining, difficulty, bank_scope)
                if bank_source and bank_uuid:
                    self._repo.mark_bank_question_used(used_category, bank_source, bank_uuid)
                if commit_subtopic_deck and used_subtopic is not None and subtopic_remaining is not None:
                    self._repo.save_subtopic_queue(
                        str(chat_id), used_category, difficulty, subtopic_remaining, used_subtopic
                    )
                self._repo.save_category_queue(remaining, used_category, str(chat_id))
                sent_count += 1
                sent_chat_ids.append(str(chat_id))
            else:
                failed.append({"chat_id": str(chat_id), "step": "sendPoll"})

        logger.info(
            "Quiz Lambda completed",
            extra={"sent": sent_count, "total": len(chat_ids), "failed_count": len(failed)},
        )
        return {
            "status": "ok",
            "sent": sent_count,
            "total": len(chat_ids),
            "sent_chat_ids": sent_chat_ids,
            "failed": failed,
        }

    def process_on_demand_quiz(
        self,
        chat_id: str,
        lang: str,
        topic: str,
        difficulty: str,
        *,
        interactive: bool = False,
    ) -> dict:
        """Generate and send a single on-demand quiz to one chat.

        For topics that map to a banked category (e.g. "cloud", "aws"), questions are drawn
        from the question bank using a per-chat genquiz queue that is independent from the
        daily rotation.  The RPD footer is omitted for bank-sourced questions (no AI used).
        """
        logger.info(
            "On-demand quiz requested",
            extra={"chat_id": chat_id, "topic": topic, "lang": lang, "difficulty": difficulty},
        )

        def save_sent_poll(question: dict, poll_question: str, poll_result: dict, category: str) -> bool:
            poll_id = str(poll_result.get("poll", {}).get("id", ""))
            if not poll_id:
                logger.error("On-demand poll result missing poll id", extra={"chat_id": chat_id, "topic": topic})
                return False
            return self._repo.save_quiz_record(
                chat_id=chat_id,
                question=poll_question,
                options=question["options"],
                correct_option_id=question["correct_option_index"],
                explanation=question.get("explanation"),
                category=category,
                lang=lang,
                poll_id=poll_id,
                message_id=int(poll_result.get("message_id", 0)),
                difficulty=difficulty,
                points=question["points"],
                subtopic=question.get("subtopic"),
                fingerprint=question.get("fingerprint"),
                record_key=f"ONDEMAND#{poll_id}",
            )

        # ── Bank path ────────────────────────────────────────────────────────
        banked_category = _GENQUIZ_TOPIC_TO_BANKED.get(topic.lower().strip())
        if banked_category:
            banked_result = self._pick_banked_question_for_genquiz(banked_category, str(chat_id), difficulty)
            if banked_result:
                banked, genquiz_remaining = banked_result
                question = banked
                if lang != "en":
                    if interactive:
                        translated = self._generator.translate_question(banked, lang, interactive=True)
                    else:
                        translated = self._generator.translate_question(banked, lang)
                    if translated:
                        question = translated
                    else:
                        logger.warning(
                            "Genquiz translation failed, using English original",
                            extra={"chat_id": chat_id, "lang": lang},
                        )
                # Prepend source label inline in the question text (no separate announcement)
                source_label = question.get("source_label", "")
                if source_label:
                    prefix = f"<b>📚 {source_label}</b>\n\n"
                    q_text = question["question"][: 300 - len(prefix)]
                    poll_question = prefix + q_text
                else:
                    poll_question = question["question"]
                poll_result = self._sender.send_quiz_poll(
                    chat_id=chat_id,
                    question=poll_question,
                    options=question["options"],
                    correct_option_id=question["correct_option_index"],
                    explanation=question.get("explanation"),
                    question_parse_mode="HTML",
                )
                if poll_result:
                    logger.info(
                        "Genquiz sent from bank",
                        extra={"chat_id": chat_id, "category": banked_category, "lang": lang},
                    )
                    if not save_sent_poll(question, poll_question, poll_result, banked_category):
                        logger.error("Failed to save genquiz poll lookup", extra={"chat_id": chat_id})
                        return {"status": "error", "reason": "failed to save poll record"}
                    # Commit question queue only after confirmed send (Bug #2 fix).
                    self._repo.save_genquiz_question_queue(banked_category, str(chat_id), genquiz_remaining, difficulty)
                    return {"status": "ok", "sent": 1, "total": 1}
                logger.error("Failed to send genquiz poll from bank", extra={"chat_id": chat_id})
                return {"status": "error", "reason": "failed to send poll"}
            # Bank exhausted (shouldn't happen in practice) — fall through to AI
            logger.warning(
                "Genquiz bank empty for topic, falling back to AI",
                extra={"chat_id": chat_id, "topic": topic},
            )

        # ── AI path ──────────────────────────────────────────────────────────
        if interactive:
            question = self._generator.generate_question(topic, lang, difficulty, interactive=True)
        else:
            question = self._generator.generate_question(topic, lang, difficulty)
        if not question:
            logger.error("Failed to generate on-demand question", extra={"topic": topic})
            return {"status": "error", "reason": "no valid question"}

        poll_result = self._sender.send_quiz_poll(
            chat_id=chat_id,
            question=question["question"],
            options=question["options"],
            correct_option_id=question["correct_option_index"],
            explanation=question.get("explanation"),
        )

        if poll_result:
            logger.info("On-demand quiz sent via AI", extra={"chat_id": chat_id, "topic": topic})
            if not save_sent_poll(question, question["question"], poll_result, topic):
                logger.error("Failed to save on-demand quiz poll lookup", extra={"chat_id": chat_id, "topic": topic})
                return {"status": "error", "reason": "failed to save poll record"}
            return {"status": "ok", "sent": 1, "total": 1}

        logger.error("Failed to send on-demand quiz poll", extra={"chat_id": chat_id})
        return {"status": "error", "reason": "failed to send poll"}

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
        result = self.process_on_demand_quiz(chat_id, lang, topic, difficulty, interactive=True)
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
