"""Simple bot commands: /start, /help, /support, /ping, /stats, /genquiz."""

from core.config import (
    ADMIN_USER_ID,
    QUIZ_LAMBDA_NAME,
    VALID_DIFFICULTIES,
    VALID_LANGS,
    get_chat_lang,
)
from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.group_agent import answer_group_question, build_explicit_question_context
from services.handlers.quiz import react_genquiz_processing
from services.memory_cutover import is_current_explicit_task
from services.telegram_actor import actor_display_name
from services.telegram_media import (
    MediaDisabledError,
    MediaTooLargeError,
    MediaUnavailableError,
    MediaUnsupportedError,
    default_question_for_media_refs,
    detect_media_references,
    has_any_media,
    media_reference_log_extra,
    media_references_log_extra,
    media_references_retrieval_query,
    prepare_media_collection_for_gemini,
)

logger = LoggerAdapter(get_logger(__name__), {})


def _is_admin_user(ctx: Context) -> bool:
    return ctx.user_id == ADMIN_USER_ID


def _chat_member_status(ctx: Context) -> str:
    try:
        member = ctx.bot.get_chat_member(ctx.chat_id, ctx.user_id)
        return (member.get("status") or "").lower()
    except Exception:
        logger.exception("Failed to verify chat member status", extra={"chat_id": ctx.chat_id, "user_id": ctx.user_id})
        return ""


def _is_chat_admin(ctx: Context) -> bool:
    return _is_admin_user(ctx) or _chat_member_status(ctx) in ("creator", "administrator")


def _require_chat_admin(ctx: Context) -> bool:
    if _is_chat_admin(ctx):
        return True
    ctx.reply(get_translated_text("stats_admin_only", ctx.lang_code), ctx.message_id)
    return False


def _require_memory_repo(ctx: Context) -> bool:
    if ctx.memory_repo:
        return True
    ctx.reply(get_translated_text("memory_storage_not_configured", ctx.lang_code), ctx.message_id)
    return False


def _command_args(text: str) -> str:
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def _normalized_subcommand(args: str) -> str:
    return " ".join(args.replace("_", " ").lower().split())


def _message_for_ask_context(ctx: Context, question: str) -> dict:
    message = dict(ctx.message) if isinstance(ctx.message, dict) else {"text": question}
    if isinstance(ctx.reply_to_message, dict):
        message["reply_to_message"] = ctx.reply_to_message
    return message


def _parse_genquiz_args(text: str, chat_id: int | str) -> tuple[str, str, str] | None:
    """Parse ``/genquiz`` args: ``topic`` [, ``difficulty`` [, ``lang``]].

    Order is fixed: topic (words), then optional difficulty, then optional lang.
    Defaults: difficulty ``medium``, lang from ``CHAT_LANG_MAP`` / ``DEFAULT_LANG``.
    """
    parts = text.split()
    if len(parts) < 2:
        return None
    tokens = parts[1:]
    if len(tokens) == 1:
        return (tokens[0], "medium", get_chat_lang(chat_id))

    lang: str | None = None
    difficulty: str | None = None

    if tokens[-1] in VALID_LANGS:
        lang = tokens.pop()

    if len(tokens) >= 2 and tokens[-1] in VALID_DIFFICULTIES:
        difficulty = tokens.pop()

    topic = " ".join(tokens).strip()
    if not topic:
        return None

    return (
        topic,
        difficulty or "medium",
        lang or get_chat_lang(chat_id),
    )


def handle_start(ctx: Context) -> None:
    ctx.reply(get_translated_text("start_message", ctx.lang_code), ctx.message_id)


def handle_help(ctx: Context) -> None:
    ctx.reply(get_translated_text("help_message", ctx.lang_code), ctx.message_id)


def handle_support(ctx: Context) -> None:
    ctx.reply(
        get_translated_text("support_message", ctx.lang_code),
        ctx.message_id,
    )


def handle_ping(ctx: Context) -> None:
    ctx.reply("🏓 Pong! Serverless is fast.", ctx.message_id)


def handle_stats(ctx: Context) -> None:
    """Admin-only: reply with group statistics."""
    try:
        if not _require_chat_admin(ctx):
            return

        stats: dict = ctx.stats_repo.get_stats(ctx.chat_id)
        total = stats["total_joins"]
        verified = stats["verified_users"]
        banned = stats["total_bans"]
        spam_banned = stats["spam_bans"]
        start_date = stats["started_at"]

        activity_level_percentage = int(min(100, 100 * verified / max(1, total)))
        if activity_level_percentage < 30:
            level_key = "activity_low"
        elif activity_level_percentage < 70:
            level_key = "activity_medium"
        else:
            level_key = "activity_high"

        activity_level = get_translated_text(level_key, ctx.lang_code)
        msg = get_translated_text(
            "stats_message",
            ctx.lang_code,
            start_date=start_date,
            total=total,
            verified=verified,
            banned=banned,
            spam_banned=spam_banned,
            activity_level=activity_level,
        )
        ctx.reply(msg, ctx.message_id)
    except Exception as e:
        logger.exception(f"handle_stats error: {e}")
        ctx.reply(
            get_translated_text("stats_error", ctx.lang_code),
            ctx.message_id,
        )


def handle_agent_on(ctx: Context) -> None:
    """Legacy controls cannot turn retired learning or social behavior back on."""
    ctx.reply(get_translated_text("legacy_agent_retired", ctx.lang_code), ctx.message_id)


def handle_agent_off(ctx: Context) -> None:
    """Legacy controls cannot turn retired learning or social behavior back on."""
    ctx.reply(get_translated_text("legacy_agent_retired", ctx.lang_code), ctx.message_id)


def handle_memory_status(ctx: Context) -> None:
    """Legacy controls cannot turn retired learning or social behavior back on."""
    ctx.reply(get_translated_text("legacy_agent_retired", ctx.lang_code), ctx.message_id)


def handle_memory(ctx: Context) -> None:
    from services.memory_v2.public_commands import handle_memory_v2

    handle_memory_v2(ctx)


def handle_agent_status(ctx: Context) -> None:
    handle_memory_status(ctx)


def handle_agent(ctx: Context) -> None:
    action = _normalized_subcommand(_command_args(ctx.text))
    if action == "on":
        handle_agent_on(ctx)
    elif action == "off":
        handle_agent_off(ctx)
    elif action == "status":
        handle_agent_status(ctx)
    elif action == "why":
        handle_why_reply(ctx)
    elif action == "wrong":
        handle_wrong_memory_feedback(ctx)
    else:
        ctx.reply(get_translated_text("agent_usage", ctx.lang_code), ctx.message_id)


def handle_ask(ctx: Context) -> None:
    if not _require_memory_repo(ctx):
        return
    if not ctx.sqs_repo:
        ctx.reply(get_translated_text("ask_agent_unavailable", ctx.lang_code), ctx.message_id)
        return
    question = _command_args(ctx.text)
    ask_message = _message_for_ask_context(ctx, question)
    media_refs = detect_media_references(
        ask_message,
        media_group_loader=lambda media_group_id: ctx.memory_repo.get_media_group_refs(ctx.chat_id, media_group_id),
    )
    if media_refs:
        media_log = media_references_log_extra(media_refs)
        if len(media_refs) == 1:
            media_log.update(media_reference_log_extra(media_refs[0]))
        logger.info(
            "Explicit ask media detected",
            extra={
                "chat_id": ctx.chat_id,
                "message_id": ctx.message_id,
                "update_id": ctx.update_id,
                "media_source": (
                    "media_group"
                    if len(media_refs) > 1
                    else "current_message" if media_refs[0].source_message_id == ctx.message_id else "reply_to_message"
                ),
                **media_log,
            },
        )
    if not media_refs and has_any_media(ask_message):
        logger.info(
            "Explicit ask media unsupported",
            extra={"chat_id": ctx.chat_id, "message_id": ctx.message_id, "update_id": ctx.update_id},
        )
        ctx.reply(get_translated_text("ask_media_unsupported", ctx.lang_code), ctx.message_id)
        return
    effective_question = question or (default_question_for_media_refs(media_refs) if media_refs else "")
    if not media_refs and effective_question:
        from services.memory_v2.public_answers import try_memory_answer

        if try_memory_answer(ctx.message, question=effective_question, lang=ctx.lang_code):
            return

    ask_message = _message_for_ask_context(ctx, effective_question)
    question_context = build_explicit_question_context(
        ctx.memory_repo,
        ctx.chat_id,
        ask_message,
        current_text=effective_question,
    )
    if not question_context.user_text:
        ctx.reply(get_translated_text("ask_usage", ctx.lang_code), ctx.message_id)
        return
    retrieval_query = question_context.retrieval_query
    if media_refs:
        retrieval_query = media_references_retrieval_query(retrieval_query, media_refs)
    try:
        ctx.react("👀")
    except Exception:
        logger.debug(
            "Failed to react to /ask before enqueue",
            extra={"chat_id": ctx.chat_id, "message_id": ctx.message_id},
        )
    try:
        ctx.sqs_repo.send_group_ask_task(
            update_id=ctx.update_id or ctx.message_id or 0,
            chat_id=ctx.chat_id,
            reply_to_message_id=ctx.message_id,
            user_text=question_context.user_text,
            retrieval_query=retrieval_query,
            lang=ctx.lang_code,
            requester_user_id=ctx.user_id,
            request_sent_at=ctx.message.get("date"),
            requester_username=ctx.username,
            requester_display_name=actor_display_name(ctx.user_data),
            current_user_message=question_context.current_user_message,
            source_message_context=question_context.source_message_context,
            parent_bot_message_id=question_context.parent_bot_message_id,
            media_refs=[media_ref.to_dict() for media_ref in media_refs] or None,
        )
    except Exception:
        logger.exception("Failed to enqueue /ask task", extra={"chat_id": ctx.chat_id, "message_id": ctx.message_id})
        ctx.reply(get_translated_text("ask_agent_unavailable", ctx.lang_code), ctx.message_id)
        return


def process_group_ask_task(*, repo, bot, body):
    from services.memory_v2.explicit_delivery import configured_delivery
    from services.memory_v2.models import MemoryConflict, MemoryInputError, MemoryUnavailable

    if not is_current_explicit_task(body):
        return
    try:
        with configured_delivery(repo, bot, body) as (guarded_bot, current):
            _process_group_ask_task(repo=repo, bot=guarded_bot, body=current)
    except (MemoryConflict, MemoryInputError, MemoryUnavailable):
        return  # Duplicate/invalidated/uncertain external delivery cannot be replayed.


def _process_group_ask_task(
    *,
    repo,
    bot,
    body: dict[str, object],
) -> None:
    """Process only new explicit requests; legacy payloads may contain old memory."""
    if not is_current_explicit_task(body):
        return
    from services.memory_v2.explicit_request_gate import validate_configured
    from services.memory_v2.models import MemoryInputError, MemoryUnavailable

    try:
        validate_configured(body)
    except (MemoryInputError, MemoryUnavailable):
        return
    chat_id = int(body["chat_id"])
    reply_to_message_id = int(body["reply_to_message_id"])
    user_text = str(body["user_text"]).strip()
    retrieval_query = str(body.get("retrieval_query") or "").strip() or None
    lang = str(body.get("lang") or "kk")
    requester_user_id = body.get("requester_user_id")
    if not user_text:
        logger.warning("PROCESS_GROUP_ASK received empty user_text", extra={"chat_id": chat_id})
        return
    media_parts = None
    media_context = ""
    media_metadata = None
    raw_media_refs = body.get("media_refs")
    media_refs = (
        [value for value in raw_media_refs if isinstance(value, dict)] if isinstance(raw_media_refs, list) else []
    )
    legacy_media_ref = body.get("media_ref")
    if not media_refs and isinstance(legacy_media_ref, dict):
        media_refs = [legacy_media_ref]
    if media_refs:
        try:
            prepared_media = prepare_media_collection_for_gemini(bot, media_refs)
            media_parts = prepared_media.media_parts
            media_context = prepared_media.media_context
            media_metadata = prepared_media.agent_reply_metadata
            media_log = media_references_log_extra(media_refs)
            if len(media_refs) == 1:
                media_log.update(media_reference_log_extra(media_refs[0]))
            logger.info(
                "Explicit ask media prepared",
                extra={
                    "chat_id": chat_id,
                    "reply_to_message_id": reply_to_message_id,
                    **media_log,
                    "downloaded_bytes": prepared_media.downloaded_bytes,
                    "content_modes": prepared_media.content_modes,
                    "media_part_count": len(media_parts or []),
                    "media_prepared_count": prepared_media.prepared_count,
                    "media_skipped_count": prepared_media.skipped_count,
                    "media_skipped_reasons": prepared_media.skipped_reasons,
                    "media_context_chars": len(media_context),
                },
            )
        except MediaDisabledError:
            bot.send_message(
                chat_id,
                get_translated_text("ask_multimodal_unavailable", lang),
                reply_to_message_id=reply_to_message_id,
            )
            return
        except MediaUnsupportedError:
            bot.send_message(
                chat_id,
                get_translated_text("ask_media_unsupported", lang),
                reply_to_message_id=reply_to_message_id,
            )
            return
        except MediaTooLargeError:
            bot.send_message(
                chat_id,
                get_translated_text("ask_media_too_large", lang),
                reply_to_message_id=reply_to_message_id,
            )
            return
        except MediaUnavailableError as exc:
            if exc.retryable:
                raise
            bot.send_message(
                chat_id,
                get_translated_text("ask_media_unavailable", lang),
                reply_to_message_id=reply_to_message_id,
            )
            return
    from services.memory_v2.explicit_delivery import ExplicitDelivery

    if isinstance(bot, ExplicitDelivery):
        bot.check()  # Validate again after downloads and immediately before provider use.
    handled = answer_group_question(
        repo=repo,
        bot=bot,
        chat_id=chat_id,
        reply_to_message_id=reply_to_message_id,
        user_text=user_text,
        retrieval_query=retrieval_query,
        lang=lang,
        requester_user_id=requester_user_id,
        requester_username=str(body.get("requester_username") or "") or None,
        requester_display_name=str(body.get("requester_display_name") or "") or None,
        current_user_message=str(body.get("current_user_message") or "") or None,
        source_message_context=str(body.get("source_message_context") or "") or None,
        parent_bot_message_id=body.get("parent_bot_message_id"),
        media_parts=media_parts,
        media_context=media_context,
        media_metadata=media_metadata,
        raise_on_unavailable=True,
    )
    if not handled:
        bot.send_message(
            chat_id, get_translated_text("ask_agent_unavailable", lang), reply_to_message_id=reply_to_message_id
        )


def handle_wrong_memory_feedback(ctx: Context) -> None:
    """All legacy facts are already excluded; V2 corrections have a new owner."""
    ctx.reply(get_translated_text("legacy_agent_retired", ctx.lang_code), ctx.message_id)


def handle_why_reply(ctx: Context) -> None:
    """Legacy answer bodies are unavailable; do not read retired explanations."""
    ctx.reply(get_translated_text("why_reply_missing", ctx.lang_code), ctx.message_id)


def handle_quiz_generate(ctx: Context) -> None:
    """Generate and send an on-demand quiz poll to the current chat (open to all users).

    Usage: ``/genquiz <topic>`` [, ``<difficulty>`` [, ``<lang>``]] — fixed order;
    omitted difficulty defaults to ``medium``, omitted lang to this chat's default.
    """
    if not QUIZ_LAMBDA_NAME or not ctx.lambda_invoker:
        react_genquiz_processing(ctx, "🤡")
        ctx.reply(get_translated_text("genquiz_lambda_not_configured", ctx.lang_code), ctx.message_id)
        return

    parsed = _parse_genquiz_args(ctx.text, ctx.chat_id)
    if parsed is None:
        react_genquiz_processing(ctx, "🤡")
        ctx.reply(get_translated_text("genquiz_usage", ctx.lang_code), ctx.message_id)
        return

    topic, difficulty, lang = parsed

    if lang not in VALID_LANGS:
        react_genquiz_processing(ctx, "🤡")
        langs_str = ", ".join(sorted(VALID_LANGS))
        ctx.reply(get_translated_text("genquiz_invalid_lang", ctx.lang_code, langs=langs_str), ctx.message_id)
        return

    if difficulty not in VALID_DIFFICULTIES:
        diffs_str = ", ".join(sorted(VALID_DIFFICULTIES))
        ctx.reply(
            get_translated_text("genquiz_invalid_difficulty", ctx.lang_code, difficulties=diffs_str), ctx.message_id
        )
        return

    react_genquiz_processing(ctx)

    logger.info(
        "Invoking quiz lambda on-demand",
        extra={"topic": topic, "lang": lang, "difficulty": difficulty, "chat_id": ctx.chat_id},
    )

    accepted = ctx.lambda_invoker.invoke_async(
        QUIZ_LAMBDA_NAME,
        {
            "action": "on_demand",
            "chat_id": str(ctx.chat_id),
            "topic": topic,
            "lang": lang,
            "difficulty": difficulty,
            "reply_to_message_id": ctx.message_id,
        },
    )
    if not accepted:
        msg = get_translated_text("genquiz_failed", ctx.lang_code, reason="failed to start generation")
        ctx.reply(msg, ctx.message_id)
        return
