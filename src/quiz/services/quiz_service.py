"""Quiz domain services for managing generation, sending and leaderboards."""

import random
from datetime import datetime, timedelta, timezone

from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.quiz_generator import CATEGORY_POOL, DIFFICULTY_POINTS, QuizGenerator
from services.quiz_sender import QuizSender
from services.repository import QuizRepository

logger = LoggerAdapter(get_logger(__name__), {})

_ALMATY_TZ = timezone(timedelta(hours=5))

_WEEKDAY_DIFFICULTY: dict[int, str] = {
    0: "easy",
    1: "easy",
    2: "medium",
    3: "medium",
    4: "hard",
    5: "hard",
    6: "expert",
}

_MEDALS = ["🥇", "🥈", "🥉"]


class QuizService:
    """Orchestrates quiz operations (daily quiz and leaderboards)."""

    def __init__(self) -> None:
        self._generator = QuizGenerator()
        self._sender = QuizSender()
        self._repo = QuizRepository()

    def get_difficulty(self) -> str:
        """Return the difficulty level for today (Almaty time)."""
        weekday = datetime.now(_ALMATY_TZ).weekday()
        return _WEEKDAY_DIFFICULTY.get(weekday, "easy")

    def build_announcement(self, lang: str, difficulty: str) -> str:
        """Build the announcement text for the daily quiz."""
        difficulty_label = get_translated_text(f"difficulty_{difficulty}", lang)
        points = DIFFICULTY_POINTS.get(difficulty, 1)
        return get_translated_text(
            "quiz_announcement",
            lang,
            difficulty_label=difficulty_label,
            points=points,
        )

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
            score = int(entry.get("total_score", 0))
            mention = f'<a href="tg://user?id={user_id}">{first_name}</a>'
            lines.append(f"{medal} {mention} — <b>{score}</b>")

        return header + "\n".join(lines)

    def process_leaderboard(self, chat_ids: list[str], lang: str) -> dict:
        """Send leaderboard to all chats for a given language."""
        sent_count = 0
        for chat_id in chat_ids:
            entries = self._repo.get_leaderboard(str(chat_id))
            text = self.build_leaderboard_text(lang, entries)
            result = self._sender.send_message(str(chat_id), text)
            if result:
                sent_count += 1
                logger.info("Leaderboard sent", extra={"chat_id": chat_id, "lang": lang})
            else:
                logger.error("Failed to send leaderboard", extra={"chat_id": chat_id})

        return {"status": "ok", "action": "leaderboard", "sent": sent_count, "total": len(chat_ids)}

    def process_daily_quiz(self, chat_ids: list[str], lang: str) -> dict:
        """Generate and send the daily quiz to all chats."""
        if not chat_ids:
            logger.warning("No chat_ids in event payload")
            return {"status": "skipped", "reason": "no chat_ids"}

        difficulty = self.get_difficulty()
        logger.info("Difficulty for today", extra={"difficulty": difficulty, "lang": lang})

        # Deck-of-cards category rotation
        category_queue = self._repo.get_category_queue()
        if not category_queue:
            category_queue = list(CATEGORY_POOL)
            random.shuffle(category_queue)
            logger.info("New category round started", extra={"queue": category_queue})

        remaining = list(category_queue)
        generated = None
        used_category = None
        restarted = False

        while remaining:
            category = remaining.pop(0)
            question = self._generator.generate_question(category, lang, difficulty)
            if question:
                generated = question
                used_category = category
                logger.info(
                    "Question generated",
                    extra={"category": category, "lang": lang, "difficulty": difficulty},
                )
                break
            if not remaining and not restarted:
                restarted = True
                remaining = list(CATEGORY_POOL)
                random.shuffle(remaining)
                logger.warning("Queue exhausted, starting fresh category round")

        if not generated:
            logger.error("Failed to generate a valid question after all categories")
            return {"status": "error", "reason": "no valid question"}

        # Send announcement + quiz poll to each chat
        sent_count = 0
        announcement = self.build_announcement(lang, difficulty)

        for chat_id in chat_ids:
            self._sender.send_message(str(chat_id), announcement)

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
                sent_count += 1

        if sent_count > 0:
            self._repo.save_category_queue(remaining, used_category)

        logger.info("Quiz Lambda completed", extra={"sent": sent_count, "total": len(chat_ids)})
        return {"status": "ok", "sent": sent_count, "total": len(chat_ids)}
