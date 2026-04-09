"""Quiz handlers: poll_answer, /quizstats, and /genquiz processing UX."""

import html

from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.telegram import TelegramAPIError, TelegramClient

logger = LoggerAdapter(get_logger(__name__), {})

_GENQUIZ_PROCESSING_REACTION = "👌"


def react_genquiz_processing(ctx: Context, reaction: str = _GENQUIZ_PROCESSING_REACTION) -> None:
    """React to the /genquiz message before slow work so the webhook is visibly active (same idea as /wtf)."""
    try:
        ctx.react(reaction)
    except TelegramAPIError as e:
        logger.warning(
            "setMessageReaction failed for /genquiz",
            extra={"status": e.status, "body": e.body[:200]},
        )


def _html_chat_title_for_pm(bot: TelegramClient, chat_id: int | str) -> str:
    """HTML-escaped chat label for private quizstats (group title, @username, or id)."""
    try:
        chat = bot.get_chat(chat_id)
    except Exception as exc:
        logger.warning("getChat failed for quizstats", extra={"chat_id": chat_id, "error": str(exc)})
        return html.escape(str(chat_id))

    ctype = (chat.get("type") or "").lower()
    if ctype in ("group", "supergroup", "channel"):
        title = (chat.get("title") or "").strip()
        if chat.get("username"):
            handle = f"@{chat['username']}"
            label = f"{title} ({handle})" if title else handle
        else:
            label = title or str(chat_id)
        return html.escape(label)
    if ctype == "private":
        name = " ".join(p for p in (chat.get("first_name"), chat.get("last_name")) if p).strip()
        return html.escape(name or "Private")

    return html.escape(str(chat.get("title") or chat_id))


def handle_poll_answer(ctx: Context) -> None:
    """Process a poll_answer update — look up poll, update score/streak."""
    if not ctx.poll_answer:
        return

    poll_id = str(ctx.poll_answer.get("poll_id", ""))
    user = ctx.poll_answer.get("user", {})
    user_id = str(user.get("id", ""))
    first_name = user.get("first_name", "User")
    option_ids = ctx.poll_answer.get("option_ids", [])

    if not poll_id or not user_id or not option_ids:
        logger.warning("Incomplete poll_answer data", extra={"poll_answer": ctx.poll_answer})
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

    points = int(quiz_record.get("points", 1))

    if selected_option == correct_option_id:
        ctx.quiz_repo.update_score_correct(chat_id, user_id, first_name, points=points)
        logger.info("Correct answer recorded", extra={"user_id": user_id, "chat_id": chat_id, "points": points})
    else:
        ctx.quiz_repo.update_score_wrong(chat_id, user_id, first_name)
        logger.info("Wrong answer recorded", extra={"user_id": user_id, "chat_id": chat_id})


def handle_quizstats(ctx: Context) -> None:
    """Handle /quizstats — show user's quiz performance in this chat."""
    if not ctx.quiz_repo:
        ctx.reply(get_translated_text("quiz_not_configured", ctx.lang_code))
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

    chat_title = _html_chat_title_for_pm(ctx.bot, ctx.chat_id)

    try:
        ctx.send_private_message(
            get_translated_text(
                "quizstats_response",
                lang,
                chat_title=chat_title,
                score=user_score.get("total_score", 0),
                streak=user_score.get("current_streak", 0),
                best_streak=user_score.get("best_streak", 0),
                rank=rank,
                total_players=len(leaderboard),
            )
        )
        ctx.react("👌")
    except TelegramAPIError as error:
        if error.status == 403:
            ctx.reply(get_translated_text("quizstats_open_private_chat", lang), ctx.message_id)
            return
        raise
