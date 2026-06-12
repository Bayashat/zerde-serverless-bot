"""Simple bot commands: /start, /help, /support, /ping, /stats, /genquiz."""

import html
from collections import Counter
from typing import Any

from core.config import (
    ADMIN_USER_ID,
    AGENT_ENABLED,
    GROUP_MEMORY_ENABLED,
    QUIZ_LAMBDA_NAME,
    VALID_DIFFICULTIES,
    VALID_LANGS,
    get_chat_lang,
)
from core.dispatcher import Context
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.group_agent import answer_group_question, build_explicit_question_context
from services.group_memory import display_name
from services.handlers.quiz import react_genquiz_processing
from services.vector_memory import (
    delete_chat_vectors,
    delete_memory_vectors_for_items,
    delete_user_vectors,
    get_vector_index_status,
    vector_memory_configured,
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


def _is_chat_owner_or_admin_user(ctx: Context) -> bool:
    return _is_admin_user(ctx) or _chat_member_status(ctx) == "creator"


def _require_chat_admin(ctx: Context) -> bool:
    if _is_chat_admin(ctx):
        return True
    ctx.reply(get_translated_text("stats_admin_only", ctx.lang_code), ctx.message_id)
    return False


def _require_chat_owner_or_admin_user(ctx: Context) -> bool:
    if _is_chat_owner_or_admin_user(ctx):
        return True
    ctx.reply(get_translated_text("memory_owner_only", ctx.lang_code), ctx.message_id)
    return False


def _require_admin_user(ctx: Context) -> bool:
    if _is_admin_user(ctx):
        return True
    ctx.reply(get_translated_text("bot_owner_only", ctx.lang_code), ctx.message_id)
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


def handle_memory_on(ctx: Context) -> None:
    if not _require_memory_repo(ctx):
        return
    if not GROUP_MEMORY_ENABLED:
        ctx.reply(get_translated_text("memory_deployment_disabled", ctx.lang_code), ctx.message_id)
        return
    if not _require_chat_owner_or_admin_user(ctx):
        return
    ctx.memory_repo.set_chat_settings(ctx.chat_id, memory_enabled=True)
    ctx.reply(get_translated_text("memory_enabled", ctx.lang_code), ctx.message_id)


def handle_memory_off(ctx: Context) -> None:
    if not _require_memory_repo(ctx):
        return
    if not _require_chat_owner_or_admin_user(ctx):
        return
    ctx.memory_repo.set_chat_settings(ctx.chat_id, memory_enabled=False, agent_enabled=False)
    ctx.reply(get_translated_text("memory_disabled", ctx.lang_code), ctx.message_id)


def handle_agent_on(ctx: Context) -> None:
    if not _require_memory_repo(ctx):
        return
    if not AGENT_ENABLED:
        ctx.reply(get_translated_text("agent_deployment_disabled", ctx.lang_code), ctx.message_id)
        return
    if not _require_chat_owner_or_admin_user(ctx):
        return
    ctx.memory_repo.set_chat_settings(ctx.chat_id, memory_enabled=True, agent_enabled=True)
    ctx.reply(get_translated_text("agent_enabled", ctx.lang_code), ctx.message_id)


def handle_agent_off(ctx: Context) -> None:
    if not _require_memory_repo(ctx):
        return
    if not _require_chat_owner_or_admin_user(ctx):
        return
    ctx.memory_repo.set_chat_settings(ctx.chat_id, agent_enabled=False)
    ctx.reply(get_translated_text("agent_disabled", ctx.lang_code), ctx.message_id)


def handle_memory_status(ctx: Context) -> None:
    if not _require_memory_repo(ctx):
        return
    if not _require_chat_admin(ctx):
        return
    settings = ctx.memory_repo.get_chat_settings(ctx.chat_id)
    memory = (
        get_translated_text("status_on", ctx.lang_code)
        if settings["memory_enabled"]
        else get_translated_text("status_off", ctx.lang_code)
    )
    agent = (
        get_translated_text("status_on", ctx.lang_code)
        if settings["agent_enabled"]
        else get_translated_text("status_off", ctx.lang_code)
    )
    overview = ctx.memory_repo.get_memory_overview(ctx.chat_id)
    vector_status = get_vector_index_status(ctx.chat_id, repo=ctx.memory_repo, overview=overview)
    vector_configured = get_translated_text(
        "vector_configured_yes" if vector_status["configured"] else "vector_configured_no",
        ctx.lang_code,
    )
    backfill_status = str(vector_status.get("last_backfill_status") or "")
    backfill_key = f"vector_backfill_{backfill_status}"
    if backfill_key not in {
        "vector_backfill_queued",
        "vector_backfill_queued_next_page",
        "vector_backfill_queued_with_failures",
    }:
        backfill_key = "vector_backfill_none"
    vector_backfill = get_translated_text(
        backfill_key,
        ctx.lang_code,
    )
    backfill_processed_total = int(vector_status.get("last_backfill_processed_total") or 0)
    backfill_enqueued_total = int(vector_status.get("last_backfill_enqueued_total") or 0)
    backfill_failures_total = int(vector_status.get("last_backfill_failures_total") or 0)
    if backfill_processed_total or backfill_enqueued_total or backfill_failures_total:
        vector_backfill = f"{vector_backfill}; " + get_translated_text(
            "vector_backfill_progress",
            ctx.lang_code,
            processed_total=backfill_processed_total,
            enqueued_total=backfill_enqueued_total,
            failures_total=backfill_failures_total,
        )
    ctx.reply(
        get_translated_text(
            "memory_status_message",
            ctx.lang_code,
            memory=memory,
            agent=agent,
            recent_messages=overview["recent_messages"],
            user_profiles=overview["user_profiles"],
            events=overview["events"],
            user_facts=overview["user_facts"],
            group_facts=overview["group_facts"],
            jokes=overview["jokes"],
            daily_summaries=overview["daily_summaries"],
            agent_replies=overview["agent_replies"],
            vector_configured=vector_configured,
            vector_indexed=vector_status["indexed_count"],
            vector_total=vector_status["total_count"],
            vector_pending=vector_status["pending_count"],
            vector_failed=vector_status["failed_count"],
            vector_skipped=vector_status["skipped_count"],
            vector_backfill=vector_backfill,
        ),
        ctx.message_id,
    )


def _profile_values(value: Any, *, limit: int = 6) -> list[str]:
    if not isinstance(value, list):
        return []
    values: list[str] = []
    seen: set[str] = set()
    for raw in value:
        text = str(raw or "").replace("\n", " ").strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            values.append(text[:160])
        if len(values) >= limit:
            break
    return values


def _profile_topics(profile: dict[str, Any], *, limit: int = 6) -> list[str]:
    interests = _profile_values(profile.get("interests"), limit=limit)
    if interests:
        return interests
    counts = profile.get("topic_counts")
    if not isinstance(counts, dict):
        return []
    ranked: list[tuple[str, int]] = []
    for raw_term, raw_count in counts.items():
        term = str(raw_term or "").strip()
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            continue
        if term and count > 0:
            ranked.append((term, count))
    ranked.sort(key=lambda item: (-item[1], item[0]))
    return [term for term, _ in ranked[:limit]]


def _profile_line(values: list[str]) -> str:
    if not values:
        return "-"
    return ", ".join(html.escape(value) for value in values)


def handle_memory_about_me(ctx: Context) -> None:
    if not _require_memory_repo(ctx):
        return
    if not ctx.user_id:
        ctx.reply(get_translated_text("forget_me_no_user", ctx.lang_code), ctx.message_id)
        return
    profile = ctx.memory_repo.get_user_profile(ctx.chat_id, ctx.user_id)
    if not profile:
        ctx.reply(get_translated_text("memory_about_me_empty", ctx.lang_code), ctx.message_id)
        return
    language_style = _profile_values(profile.get("language_style"))
    common_topics = _profile_topics(profile)
    preferences = _profile_values(profile.get("preferences"))
    background = _profile_values(profile.get("known_facts"))
    boundaries = _profile_values(profile.get("boundaries"))
    if not any((language_style, common_topics, preferences, background, boundaries)):
        ctx.reply(get_translated_text("memory_about_me_empty", ctx.lang_code), ctx.message_id)
        return
    ctx.reply(
        get_translated_text(
            "memory_about_me_message",
            ctx.lang_code,
            language_style=_profile_line(language_style),
            common_topics=_profile_line(common_topics),
            preferences=_profile_line(preferences),
            background=_profile_line(background),
            boundaries=_profile_line(boundaries),
        ),
        ctx.message_id,
    )


def handle_memory(ctx: Context) -> None:
    action = _normalized_subcommand(_command_args(ctx.text))
    if action == "on":
        handle_memory_on(ctx)
    elif action == "off":
        handle_memory_off(ctx)
    elif action == "status":
        handle_memory_status(ctx)
    elif action == "about me":
        handle_memory_about_me(ctx)
    elif action == "forget me":
        handle_forget_me(ctx)
    elif action == "forget this":
        handle_forget_this(ctx)
    elif action == "forget group":
        handle_forget_group(ctx)
    else:
        ctx.reply(get_translated_text("memory_usage", ctx.lang_code), ctx.message_id)


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
    else:
        ctx.reply(get_translated_text("agent_usage", ctx.lang_code), ctx.message_id)


def handle_ask(ctx: Context) -> None:
    if not _require_memory_repo(ctx):
        return
    if not ctx.sqs_repo:
        ctx.reply(get_translated_text("ask_agent_unavailable", ctx.lang_code), ctx.message_id)
        return
    question = _command_args(ctx.text)
    question_context = build_explicit_question_context(
        ctx.memory_repo,
        ctx.chat_id,
        _message_for_ask_context(ctx, question),
        current_text=question,
    )
    if not question_context.user_text:
        ctx.reply(get_translated_text("ask_usage", ctx.lang_code), ctx.message_id)
        return
    if not ctx.memory_repo.is_memory_enabled(ctx.chat_id):
        ctx.reply(get_translated_text("ask_memory_off", ctx.lang_code), ctx.message_id)
        return
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
            lang=ctx.lang_code,
            requester_user_id=ctx.user_id,
            requester_username=ctx.username,
            requester_display_name=display_name(ctx.user_data),
            current_user_message=question_context.current_user_message,
            source_message_context=question_context.source_message_context,
            parent_bot_message_id=question_context.parent_bot_message_id,
        )
    except Exception:
        logger.exception("Failed to enqueue /ask task", extra={"chat_id": ctx.chat_id, "message_id": ctx.message_id})
        ctx.reply(get_translated_text("ask_agent_unavailable", ctx.lang_code), ctx.message_id)
        return


def process_group_ask_task(
    *,
    repo,
    bot,
    body: dict[str, object],
) -> None:
    """Process an async /ask request from SQS."""
    chat_id = int(body["chat_id"])
    reply_to_message_id = int(body["reply_to_message_id"])
    user_text = str(body["user_text"]).strip()
    lang = str(body.get("lang") or "kk")
    requester_user_id = body.get("requester_user_id")
    if not user_text:
        logger.warning("PROCESS_GROUP_ASK received empty user_text", extra={"chat_id": chat_id})
        return
    handled = answer_group_question(
        repo=repo,
        bot=bot,
        chat_id=chat_id,
        reply_to_message_id=reply_to_message_id,
        user_text=user_text,
        lang=lang,
        requester_user_id=requester_user_id,
        requester_username=str(body.get("requester_username") or "") or None,
        requester_display_name=str(body.get("requester_display_name") or "") or None,
        current_user_message=str(body.get("current_user_message") or "") or None,
        source_message_context=str(body.get("source_message_context") or "") or None,
        parent_bot_message_id=body.get("parent_bot_message_id"),
        raise_on_unavailable=True,
    )
    if not handled:
        bot.send_message(
            chat_id, get_translated_text("ask_agent_unavailable", lang), reply_to_message_id=reply_to_message_id
        )


def handle_forget_group(ctx: Context) -> None:
    if not _require_memory_repo(ctx):
        return
    if not _require_admin_user(ctx):
        return
    vector_note = _delete_chat_vectors_note(ctx)
    deleted = ctx.memory_repo.delete_chat_memory(ctx.chat_id)
    ctx.reply(
        get_translated_text("forget_group_done", ctx.lang_code, deleted=deleted, vector_note=vector_note),
        ctx.message_id,
    )


def handle_forget_me(ctx: Context) -> None:
    if not _require_memory_repo(ctx):
        return
    if not ctx.user_id:
        ctx.reply(get_translated_text("forget_me_no_user", ctx.lang_code), ctx.message_id)
        return
    vector_note = _delete_user_vectors_note(ctx, ctx.user_id)
    deleted = ctx.memory_repo.delete_user_memory(ctx.chat_id, ctx.user_id)
    ctx.reply(
        get_translated_text("forget_me_done", ctx.lang_code, deleted=deleted, vector_note=vector_note),
        ctx.message_id,
    )


def _is_group_owner_or_bot_owner(ctx: Context) -> bool:
    return _is_chat_owner_or_admin_user(ctx)


def _is_reply_to_bot_message(reply_to_message: dict[str, Any]) -> bool:
    sender = reply_to_message.get("from") if isinstance(reply_to_message, dict) else {}
    return bool(isinstance(sender, dict) and sender.get("is_bot"))


def _delete_items_vectors_note(ctx: Context, items: list[dict[str, Any]]) -> str:
    if not vector_memory_configured():
        return get_translated_text("vector_cleanup_skipped", ctx.lang_code)
    try:
        deleted = delete_memory_vectors_for_items(ctx.chat_id, items)
        return get_translated_text("vector_cleanup_deleted", ctx.lang_code, deleted=deleted)
    except Exception:
        logger.exception("Failed to delete selected vector memory", extra={"chat_id": ctx.chat_id})
        return get_translated_text("vector_cleanup_delayed", ctx.lang_code)


def _source_sk_values(retrieval_sources: Any) -> list[str]:
    if not isinstance(retrieval_sources, list):
        return []
    source_sks: list[str] = []
    seen: set[str] = set()
    for source in retrieval_sources:
        if not isinstance(source, dict):
            continue
        source_sk = str(source.get("source_sk") or "").strip()
        if source_sk and source_sk not in seen:
            seen.add(source_sk)
            source_sks.append(source_sk)
    return source_sks


def _deletable_source_sks_for_user(ctx: Context, source_sks: list[str], *, can_delete_group_memory: bool) -> list[str]:
    if can_delete_group_memory:
        return source_sks
    allowed: list[str] = []
    for source_sk in source_sks:
        item = ctx.memory_repo.get_memory_item(ctx.chat_id, source_sk)
        if item and ctx.user_id and ctx.memory_repo.is_memory_item_related_to_user(item, ctx.user_id):
            allowed.append(source_sk)
    return allowed


def _handle_forget_this_bot_answer(ctx: Context, bot_message_id: int | str | None) -> None:
    if bot_message_id is None:
        ctx.reply(get_translated_text("forget_this_usage", ctx.lang_code), ctx.message_id)
        return
    item = ctx.memory_repo.get_agent_reply_explanation(ctx.chat_id, bot_message_id=bot_message_id)
    if not item:
        ctx.reply(get_translated_text("why_reply_missing", ctx.lang_code), ctx.message_id)
        return
    source_sks = _source_sk_values(item.get("retrieval_sources"))
    if not source_sks:
        ctx.reply(get_translated_text("forget_this_no_sources", ctx.lang_code), ctx.message_id)
        return

    can_delete_group_memory = _is_group_owner_or_bot_owner(ctx)
    deletable_sks = _deletable_source_sks_for_user(
        ctx,
        source_sks,
        can_delete_group_memory=can_delete_group_memory,
    )
    if not deletable_sks:
        ctx.reply(get_translated_text("forget_this_not_allowed", ctx.lang_code), ctx.message_id)
        return

    deleted_items = ctx.memory_repo.delete_memory_items_by_sks(ctx.chat_id, deletable_sks)
    if not deleted_items:
        ctx.reply(get_translated_text("forget_this_nothing_deleted", ctx.lang_code), ctx.message_id)
        return
    vector_note = _delete_items_vectors_note(ctx, deleted_items)
    ctx.reply(
        get_translated_text(
            "forget_this_done",
            ctx.lang_code,
            deleted=len(deleted_items),
            vector_note=vector_note,
        ),
        ctx.message_id,
    )


def _handle_forget_this_source_message(ctx: Context, source_message: dict[str, Any]) -> None:
    message_id = source_message.get("message_id")
    if message_id is None:
        ctx.reply(get_translated_text("forget_this_usage", ctx.lang_code), ctx.message_id)
        return
    can_delete_group_memory = _is_group_owner_or_bot_owner(ctx)
    sender = source_message.get("from") if isinstance(source_message, dict) else {}
    sender_user_id = sender.get("id") if isinstance(sender, dict) else None
    if not can_delete_group_memory and (not ctx.user_id or str(sender_user_id) != str(ctx.user_id)):
        ctx.reply(get_translated_text("forget_this_not_allowed", ctx.lang_code), ctx.message_id)
        return

    deleted_items = ctx.memory_repo.delete_memory_for_message(ctx.chat_id, message_id)
    if not deleted_items:
        ctx.reply(get_translated_text("forget_this_nothing_deleted", ctx.lang_code), ctx.message_id)
        return
    vector_note = _delete_items_vectors_note(ctx, deleted_items)
    ctx.reply(
        get_translated_text(
            "forget_this_done",
            ctx.lang_code,
            deleted=len(deleted_items),
            vector_note=vector_note,
        ),
        ctx.message_id,
    )


def handle_forget_this(ctx: Context) -> None:
    if not _require_memory_repo(ctx):
        return
    if not ctx.user_id:
        ctx.reply(get_translated_text("forget_me_no_user", ctx.lang_code), ctx.message_id)
        return
    if not isinstance(ctx.reply_to_message, dict):
        ctx.reply(get_translated_text("forget_this_usage", ctx.lang_code), ctx.message_id)
        return
    if _is_reply_to_bot_message(ctx.reply_to_message):
        _handle_forget_this_bot_answer(ctx, ctx.reply_to_message.get("message_id"))
        return
    _handle_forget_this_source_message(ctx, ctx.reply_to_message)


def _delete_chat_vectors_note(ctx: Context) -> str:
    if not vector_memory_configured():
        return get_translated_text("vector_cleanup_skipped", ctx.lang_code)
    try:
        deleted = delete_chat_vectors(ctx.chat_id, repo=ctx.memory_repo)
        return get_translated_text("vector_cleanup_deleted", ctx.lang_code, deleted=deleted)
    except Exception:
        logger.exception("Failed to delete chat vector memory", extra={"chat_id": ctx.chat_id})
        return get_translated_text("vector_cleanup_delayed", ctx.lang_code)


def _delete_user_vectors_note(ctx: Context, user_id: int | str) -> str:
    if not vector_memory_configured():
        return get_translated_text("vector_cleanup_skipped", ctx.lang_code)
    try:
        deleted = delete_user_vectors(ctx.chat_id, user_id, repo=ctx.memory_repo)
        return get_translated_text("vector_cleanup_deleted", ctx.lang_code, deleted=deleted)
    except Exception:
        logger.exception("Failed to delete user vector memory", extra={"chat_id": ctx.chat_id, "user_id": user_id})
        return get_translated_text("vector_cleanup_delayed", ctx.lang_code)


_WHY_SOURCE_ORDER = (
    "requester_profile",
    "target_profile",
    "semantic",
    "lexical",
    "long_term",
    "recent",
)
_WHY_PRESENCE_SOURCES = {"requester_profile", "target_profile", "recent"}


def _agent_source_label(source: str, lang: str) -> str:
    key = {
        "requester_profile": "why_source_requester_profile",
        "target_profile": "why_source_target_profile",
        "semantic": "why_source_semantic",
        "lexical": "why_source_lexical",
        "long_term": "why_source_long_term",
        "recent": "why_source_recent",
    }.get(source)
    return get_translated_text(key, lang) if key else html.escape(source.replace("_", " "))


def _format_agent_memory_sources(retrieval_sources: Any, lang: str) -> str:
    counts: Counter[str] = Counter()
    if isinstance(retrieval_sources, list):
        for source in retrieval_sources:
            if not isinstance(source, dict):
                continue
            source_name = str(source.get("source") or "").strip()
            if source_name:
                counts[source_name] += 1
    if not counts:
        return get_translated_text("why_sources_none", lang)

    lines = [get_translated_text("why_sources_header", lang)]
    ordered_sources = [source for source in _WHY_SOURCE_ORDER if counts.get(source)]
    ordered_sources.extend(sorted(source for source in counts if source not in _WHY_SOURCE_ORDER))
    for source in ordered_sources:
        label = _agent_source_label(source, lang)
        value = get_translated_text("why_source_yes", lang) if source in _WHY_PRESENCE_SOURCES else str(counts[source])
        lines.append(get_translated_text("why_sources_item", lang, label=label, value=value))
    return "\n".join(lines)


def handle_why_reply(ctx: Context) -> None:
    if not _require_memory_repo(ctx):
        return
    bot_message_id = None
    if ctx.reply_to_message:
        sender = ctx.reply_to_message.get("from") or {}
        if sender.get("is_bot"):
            bot_message_id = ctx.reply_to_message.get("message_id")

    item = ctx.memory_repo.get_agent_reply_explanation(ctx.chat_id, bot_message_id=bot_message_id)
    if not item:
        ctx.reply(get_translated_text("why_reply_missing", ctx.lang_code), ctx.message_id)
        return

    trigger_kind = item.get("trigger_kind") or "unknown"
    reason = item.get("reason") or "No reason recorded."
    confidence = item.get("confidence")
    ctx.reply(
        get_translated_text(
            "why_reply_message",
            ctx.lang_code,
            reason=reason,
            trigger=trigger_kind,
            confidence=f"{float(confidence):.2f}" if confidence is not None else "-",
            sources=_format_agent_memory_sources(item.get("retrieval_sources"), ctx.lang_code),
        ),
        ctx.message_id,
    )


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
