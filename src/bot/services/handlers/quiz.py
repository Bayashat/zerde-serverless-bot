"""Quiz handlers: poll_answer, /quizstats, and /genquiz processing UX."""

import html

from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.telegram import TelegramAPIError, TelegramClient

logger = LoggerAdapter(get_logger(__name__), {})

_GENQUIZ_PROCESSING_REACTION = "👌"


def react_genquiz_processing(ctx: Context, reaction: str = _GENQUIZ_PROCESSING_REACTION) -> None:
    """React to the /genquiz message before slow work so the webhook is visibly active."""
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
    """Persist before enqueue; lost delivery is recovered from the durable outbox."""
    from services.repositories._quiz_answers import QuizAnswerRetryRequiredError

    if not ctx.poll_answer:
        return
    if not ctx.quiz_repo:
        raise QuizAnswerRetryRequiredError("Quiz repository is unavailable")
    try:
        answer = ctx.quiz_repo.persist_answer(ctx.poll_answer, ctx.update_id)
    except Exception as exc:
        raise QuizAnswerRetryRequiredError("Quiz answer persistence requires redelivery") from exc
    if answer["state"] not in {"PENDING", "UNRESOLVED"}:
        return
    try:
        ctx.sqs_repo.send_quiz_answer_task(answer["poll_id"], answer["user_id"])
    except Exception as exc:
        logger.warning("Quiz answer retained for recovery", extra={"error_type": type(exc).__name__})


def handle_quizstats(ctx: Context) -> None:
    """Handle /quizstats — show user's quiz performance in this chat."""
    if not ctx.quiz_repo:
        ctx.reply(get_translated_text("quiz_not_configured", ctx.lang_code))
        return

    chat_id = str(ctx.chat_id)
    user_id = str(ctx.user_id)
    lang = ctx.lang_code

    user_score_raw = ctx.quiz_repo.get_user_score(chat_id, user_id)
    if user_score_raw is None:
        try:
            ctx.send_private_message(get_translated_text("quizstats_no_data", lang))
            ctx.react("👌")
        except TelegramAPIError as error:
            if error.status == 403:
                ctx.reply(get_translated_text("quizstats_open_private_chat", lang), ctx.message_id)
                return
            raise
        return

    user_score = user_score_raw

    leaderboard = ctx.quiz_repo.get_leaderboard(chat_id)
    # Unranked users (on the board but not in this week's list) go after the last row
    rank = len(leaderboard) + 1
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
                week_score=int(user_score.get("week_score", 0)),
                season_wins=int(user_score.get("season_wins", 0)),
                season_champion_count=int(user_score.get("season_champion_count", 0)),
                total_score=int(user_score.get("total_score", 0)),
                streak=int(user_score.get("current_streak", 0)),
                best_streak=int(user_score.get("best_streak", 0)),
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
