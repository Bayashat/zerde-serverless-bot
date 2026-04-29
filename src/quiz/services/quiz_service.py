"""Quiz domain services for managing generation, sending and leaderboards."""

import random
from datetime import datetime, timedelta, timezone

from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.llm_provider import create_provider
from services.quiz_generator import CATEGORY_POOL, DIFFICULTY_POINTS, QuizGenerator
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

# Categories that draw questions from a pre-built bank instead of AI
_BANKED_CATEGORIES: dict[str, list[str]] = {
    "cloud": ["aws-clf-c02"],
}

# Human-readable labels shown in the quiz announcement for each bank source
_BANK_SOURCE_LABELS: dict[str, str] = {
    "aws-clf-c02": "AWS CLF-C02 Practice Exam",
    "aws-dva-c02": "AWS Developer Associate Practice Exam",
}


class QuizService:
    """Orchestrates quiz operations (daily quiz and leaderboards)."""

    def __init__(self) -> None:
        provider = create_provider()
        self._generator = QuizGenerator(provider)
        self._sender = QuizSender()
        self._repo = QuizRepository()

    def _rpd_payload(self) -> dict[str, int]:
        """Build a response fragment with quiz Gemini RPD counters."""
        remaining, total = self._generator.get_rpd_status()
        if remaining is None or total is None:
            return {}
        return {"rpd_remaining": remaining, "rpd_total": total}

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
        """Build the formatted leaderboard text."""
        header = get_translated_text("leaderboard_header", lang)
        if not entries:
            return header + get_translated_text("leaderboard_empty", lang)

        lines = []
        for i, entry in enumerate(entries):
            medal = _MEDALS[i] if i < len(_MEDALS) else f"{i + 1}."
            user_id = entry.get("SK", "").replace("USER#", "")
            first_name = entry.get("first_name", "User")
            score = int(entry.get("week_score", 0))
            mention = f'<a href="tg://user?id={user_id}">{first_name}</a>'
            lines.append(f"{medal} {mention} — <b>{score}</b>")

        return header + "\n".join(lines)

    def build_season_text(self, lang: str, entries: list[dict]) -> str:
        """Build the season champion announcement text."""
        header = get_translated_text("season_champion_header", lang)
        if not entries:
            return header + get_translated_text("season_champion_empty", lang)

        lines = []
        for i, entry in enumerate(entries):
            medal = _MEDALS[i] if i < len(_MEDALS) else f"{i + 1}."
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

                # Record the week's winner (only if they actually scored)
                if entries and int(entries[0].get("week_score", 0)) > 0:
                    winner = entries[0]
                    winner_id = winner.get("SK", "").replace("USER#", "")
                    self._repo.increment_season_wins(str(chat_id), winner_id, winner.get("first_name", "User"))

                # Advance season counter and check if the season is over
                week_count = self._repo.increment_season_week_count(str(chat_id))
                if week_count >= _SEASON_LENGTH:
                    season_entries = self._repo.get_season_leaderboard(str(chat_id))
                    season_text = self.build_season_text(lang, season_entries)
                    season_result = self._sender.send_message(str(chat_id), season_text)
                    if season_result:
                        logger.info("Season champion announced", extra={"chat_id": chat_id, "lang": lang})
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
            rng = random.Random(chat_id)
            category_queue = rng.sample(CATEGORY_POOL, len(CATEGORY_POOL))
            logger.info("New category round started", extra={"chat_id": chat_id, "queue": category_queue})
        remaining = list(category_queue)
        category = remaining.pop(0)
        return category, remaining

    def _pick_banked_question_for_chat(self, category: str, chat_id: str, difficulty: str) -> dict | None:
        """Pick the next question from the bank for a chat using per-chat rotation."""
        sources = _BANKED_CATEGORIES[category]
        remaining = self._repo.get_question_queue(category, chat_id)
        if not remaining:
            all_keys = self._repo.get_bank_question_ids(category, sources)
            if not all_keys:
                return None
            # Seed by chat_id + pool size so different chats start at different positions
            rng = random.Random(f"{chat_id}::{len(all_keys)}")
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
                self._repo.save_question_queue(category, chat_id, remaining)
                return {
                    "question": item["question"],
                    "options": list(item["options"]),
                    "correct_option_index": int(item["correct_option_id"]),
                    "explanation": item.get("explanation", ""),
                    "difficulty": difficulty,
                    "points": DIFFICULTY_POINTS.get(difficulty, 1),
                    "source_label": _BANK_SOURCE_LABELS.get(source, source),
                }
            logger.warning("Bank question missing, skipping", extra={"uuid": q_uuid})

        self._repo.save_question_queue(category, chat_id, remaining)
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
            category, remaining = self._pick_category_for_chat(str(chat_id))
            generated = None
            used_category = category

            if category in _BANKED_CATEGORIES:
                # Draw from pre-built question bank
                banked = self._pick_banked_question_for_chat(category, str(chat_id), difficulty)
                if banked:
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
                    q = self._generator.generate_question(category, lang, difficulty)
                    if q:
                        generated = q

            if not generated:
                # AI path for non-banked categories (or bank + AI both failed)
                candidates = [category] + remaining
                restarted = False
                while candidates:
                    cat = candidates.pop(0)
                    question = self._generator.generate_question(cat, lang, difficulty)
                    if question:
                        generated = question
                        used_category = cat
                        remaining = candidates
                        logger.info(
                            "Question generated",
                            extra={"chat_id": chat_id, "category": cat, "lang": lang, "difficulty": difficulty},
                        )
                        break
                    if not candidates and not restarted:
                        restarted = True
                        candidates = list(CATEGORY_POOL)
                        random.shuffle(candidates)
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

    def process_on_demand_quiz(self, chat_id: str, lang: str, topic: str, difficulty: str) -> dict:
        """Generate and send a single on-demand quiz to one chat."""
        logger.info(
            "On-demand quiz requested",
            extra={"chat_id": chat_id, "topic": topic, "lang": lang, "difficulty": difficulty},
        )

        question = self._generator.generate_question(topic, lang, difficulty)
        if not question:
            logger.error("Failed to generate on-demand question", extra={"topic": topic})
            return {"status": "error", "reason": "no valid question", **self._rpd_payload()}

        poll_result = self._sender.send_quiz_poll(
            chat_id=chat_id,
            question=question["question"],
            options=question["options"],
            correct_option_id=question["correct_option_index"],
            explanation=question.get("explanation"),
        )

        if poll_result:
            logger.info("On-demand quiz sent", extra={"chat_id": chat_id, "topic": topic})
            return {"status": "ok", "sent": 1, "total": 1, **self._rpd_payload()}

        logger.error("Failed to send on-demand quiz poll", extra={"chat_id": chat_id})
        return {"status": "error", "reason": "failed to send poll", **self._rpd_payload()}

    def process_on_demand_quiz_with_feedback(
        self,
        chat_id: str,
        lang: str,
        topic: str,
        difficulty: str,
        *,
        include_rpd_footer: bool,
        reply_to_message_id: int | None = None,
    ) -> dict:
        """Run on-demand quiz and optionally send RPD footer to chat."""
        result = self.process_on_demand_quiz(chat_id, lang, topic, difficulty)
        if include_rpd_footer:
            remaining = result.get("rpd_remaining")
            total = result.get("rpd_total")
            if isinstance(remaining, int) and isinstance(total, int):
                footer = get_translated_text("genquiz_rpd_footer", lang, remaining=remaining, total=total)
                self._sender.send_message(chat_id, footer, reply_to_message_id=reply_to_message_id)
        return result
