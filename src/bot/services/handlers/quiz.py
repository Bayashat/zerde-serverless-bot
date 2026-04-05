"""Quiz handlers: poll_answer processing and /quizstats command."""

from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text

logger = LoggerAdapter(get_logger(__name__), {})


def handle_poll_answer(ctx: Context) -> None:
    """Process a poll_answer update — look up poll, update score/streak."""
    poll_answer = ctx._update.get("poll_answer")
    if not poll_answer:
        return

    poll_id = str(poll_answer.get("poll_id", ""))
    user = poll_answer.get("user", {})
    user_id = str(user.get("id", ""))
    first_name = user.get("first_name", "User")
    option_ids = poll_answer.get("option_ids", [])

    if not poll_id or not user_id or not option_ids:
        logger.warning("Incomplete poll_answer data", extra={"poll_answer": poll_answer})
        return

    if not ctx.quiz_repo:
        logger.warning("QuizRepository not available, skipping poll_answer")
        return

    # Look up the quiz record by poll_id
    quiz_record = ctx.quiz_repo.lookup_poll(poll_id)
    if not quiz_record:
        logger.debug("poll_answer for unknown poll_id, ignoring", extra={"poll_id": poll_id})
        return

    chat_id = quiz_record["PK"].replace("QUIZ#", "")
    correct_option_id = int(quiz_record["correct_option_id"])
    selected_option = option_ids[0]

    if selected_option == correct_option_id:
        ctx.quiz_repo.update_score_correct(chat_id, user_id, first_name)
        logger.info("Correct answer recorded", extra={"user_id": user_id, "chat_id": chat_id})
    else:
        ctx.quiz_repo.update_score_wrong(chat_id, user_id, first_name)
        logger.info("Wrong answer recorded", extra={"user_id": user_id, "chat_id": chat_id})


def handle_quizstats(ctx: Context) -> None:
    """Handle /quizstats — show user's quiz performance in this chat."""
    if not ctx.quiz_repo:
        ctx.reply("Quiz feature is not configured.")
        return

    chat_id = str(ctx.chat_id)
    user_id = str(ctx.user_id)
    lang = ctx.lang_code

    user_score = ctx.quiz_repo.get_user_score(chat_id, user_id)
    if not user_score:
        ctx.reply(get_translated_text("quizstats_no_data", lang))
        return

    # Calculate rank
    leaderboard = ctx.quiz_repo.get_leaderboard(chat_id)
    rank = 1
    for i, entry in enumerate(leaderboard):
        if entry.get("SK") == f"USER#{user_id}":
            rank = i + 1
            break

    ctx.reply(
        get_translated_text(
            "quizstats_response",
            lang,
            score=user_score.get("total_score", 0),
            streak=user_score.get("current_streak", 0),
            best_streak=user_score.get("best_streak", 0),
            rank=rank,
            total_players=len(leaderboard),
        )
    )
