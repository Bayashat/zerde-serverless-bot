"""Context-aware group chat agent helpers."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from numbers import Number
from typing import Any

from core.config import (
    AGENT_BOT_USERNAME,
    AGENT_DAILY_PROACTIVE_LIMIT,
    AGENT_ENABLED,
    AGENT_PROACTIVE_FINAL_THRESHOLD,
    AGENT_PROACTIVE_SCORE_THRESHOLD,
    AGENT_RECENT_CONTEXT_LIMIT,
    get_chat_lang,
    get_gemini_api_key,
)
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.ai.gemini_client import GeminiClient, GeminiRPDExhaustedError, GeminiUnavailableError
from services.ai.telegram_html import fit_llm_output, normalize_llm_output_for_telegram_html
from services.group_memory import (
    display_name,
    extract_message_text,
    format_long_term_memory_context,
    format_recent_context,
    format_requester_profile_context,
    format_user_profile_context,
)
from services.memory_safety import (
    looks_like_future_answer_directive,
    looks_like_subjective_person_ranking_question,
)
from services.repositories.group_memory import GroupMemoryRepository
from services.telegram import TelegramClient
from services.vector_memory import format_semantic_memory_context, retrieve_relevant_memories

logger = LoggerAdapter(get_logger(__name__), {})

_agent_gemini: GeminiClient | None = None

_SELF_REFERENCE_CUES = (
    "who am i",
    "who am i?",
    "what do you know about me",
    "what did i say",
    "did i say",
    "我是谁",
    "你知道我",
    "我说过",
    "кто я",
    "я кто",
    "что ты знаешь обо мне",
    "что я говорил",
    "что я сказал",
    "мен кім",
    "мен кіммін",
    "мен не дедім",
)


@dataclass(frozen=True)
class ProactiveReplyScore:
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ReplyPolicy:
    instructions: str
    max_output_tokens: int
    max_chars: int


def _get_gemini() -> GeminiClient | None:
    global _agent_gemini
    if get_gemini_api_key() and _agent_gemini is None:
        _agent_gemini = GeminiClient()
    return _agent_gemini


def _is_plain_text_message(update: dict[str, Any]) -> bool:
    message = update.get("message")
    if not isinstance(message, dict):
        return False
    chat = message.get("chat") or {}
    if chat.get("type") not in {"group", "supergroup"}:
        return False
    text = extract_message_text(message)
    return bool(text and not text.startswith("/"))


def _mentions_bot(text: str) -> bool:
    if not AGENT_BOT_USERNAME:
        return False
    return re.search(rf"@{re.escape(AGENT_BOT_USERNAME)}\b", text, flags=re.IGNORECASE) is not None


def _looks_like_self_reference(text: str) -> bool:
    lowered = " ".join((text or "").lower().split())
    compact = lowered.replace(" ", "")
    return any(cue in lowered or cue.replace(" ", "") in compact for cue in _SELF_REFERENCE_CUES)


def _replies_to_bot(message: dict[str, Any]) -> bool:
    reply = message.get("reply_to_message")
    if not isinstance(reply, dict):
        return False
    sender = reply.get("from") or {}
    return bool(sender.get("is_bot"))


def _reply_text(message: dict[str, Any]) -> str:
    reply = message.get("reply_to_message")
    if not isinstance(reply, dict):
        return ""
    return extract_message_text(reply)


def _agent_reply_thread_context(
    repo: GroupMemoryRepository,
    chat_id: int | str,
    *,
    bot_message_id: int | str,
    telegram_reply_text: str,
) -> str:
    try:
        item = repo.get_agent_reply_explanation(chat_id, bot_message_id=bot_message_id)
    except Exception:
        logger.exception("Failed to load previous agent reply context", extra={"chat_id": chat_id})
        item = {}
    if not isinstance(item, dict):
        item = {}
    previous_user = str(item.get("user_message") or "").strip()
    previous_answer = str(item.get("answer_text") or telegram_reply_text or "").strip()
    parts = ["The user is continuing a thread with this previous bot answer:"]
    if previous_user:
        parts.append(f"Previous user request:\n{previous_user[:1200]}")
    if previous_answer:
        parts.append(f"Previous bot answer:\n{previous_answer[:1800]}")
    elif telegram_reply_text:
        parts.append(f"Previous bot answer from Telegram reply:\n{telegram_reply_text[:1800]}")
    return "\n\n".join(parts)


def _explicit_user_text(repo: GroupMemoryRepository, chat_id: int | str, message: dict[str, Any]) -> str:
    text = extract_message_text(message)
    replied_text = _reply_text(message)
    if _replies_to_bot(message):
        reply = message.get("reply_to_message") or {}
        thread_context = _agent_reply_thread_context(
            repo,
            chat_id,
            bot_message_id=reply.get("message_id") or 0,
            telegram_reply_text=replied_text,
        )
        return f"{thread_context}\n\nUser follow-up:\n{text}"
    return text


def _reply_policy(user_text: str) -> ReplyPolicy:
    lowered = user_text.lower()
    explicit_long = any(
        cue in lowered
        for cue in (
            "подробно",
            "толық",
            "детально",
            "развернуто",
            "deep dive",
            "explain in detail",
            "详细",
            "展开",
        )
    )
    explicit_short = any(
        cue in lowered
        for cue in (
            "қысқа",
            "қысқаша",
            "короче",
            "кратко",
            "short",
            "brief",
            "tl;dr",
            "tldr",
            "总结",
            "简短",
        )
    )
    continuation = "user is continuing a thread with this previous bot answer" in lowered
    ask_without_question = "wants you to explain it or answer based on it" in lowered

    if explicit_long:
        return ReplyPolicy(
            instructions=(
                "The user asked for detail. Answer with the minimum useful detail, up to 5 short paragraphs "
                "or 6 bullets. Avoid repeating the full context."
            ),
            max_output_tokens=460,
            max_chars=2600,
        )
    if explicit_short or continuation:
        return ReplyPolicy(
            instructions=(
                "This is a short follow-up. Answer directly in 1-3 short sentences. "
                "Do not recap the whole previous answer unless the user asks."
            ),
            max_output_tokens=180,
            max_chars=900,
        )
    if ask_without_question:
        return ReplyPolicy(
            instructions=(
                "The user asked about a replied-to message without a specific question. "
                "Give the main point in 3-5 concise sentences or at most 3 bullets."
            ),
            max_output_tokens=260,
            max_chars=1400,
        )
    return ReplyPolicy(
        instructions=(
            "Answer in 2-5 concise sentences. Use bullets only when they make the answer easier to scan. "
            "Do not write an essay by default."
        ),
        max_output_tokens=300,
        max_chars=1800,
    )


def _guardrail_reply(user_text: str, lang: str) -> str:
    lowered_lang = (lang or "").lower()
    if looks_like_future_answer_directive(user_text):
        if lowered_lang == "ru":
            return (
                "Понял шутку, но я не буду запоминать такие инструкции как правило. "
                "Особенно если это субъективный рейтинг или фиксированный ответ про человека."
            )
        if lowered_lang == "zh":
            return "懂你的意思，但我不会把这种固定回答当成长期规则，尤其是关于某个人的主观排名。"
        return (
            "Түсіндім, бірақ мұндайды тұрақты ереже ретінде сақтамаймын. "
            "Әсіресе адам туралы субъективті рейтинг немесе алдын ала бекітілген жауап болса."
        )
    if looks_like_subjective_person_ranking_question(user_text):
        if lowered_lang == "ru":
            return (
                "Не буду ранжировать людей как «самого сильного» в чате. "
                "Если нужен разбор по конкретному опыту или сообщениям, спроси точнее."
            )
        if lowered_lang == "zh":
            return "我不会给群友做“最强/第一”这种主观排名。可以问某个人说过什么、做过什么或擅长哪些话题。"
        return (
            "Чаттағы адамдарды «ең мықты» деп рейтингтемеймін. "
            "Нақты тәжірибесі, айтқан сөздері немесе тақырыптары бойынша сұрасаң, соған сүйеніп жауап берем."
        )
    return ""


def _looks_like_open_question(text: str) -> bool:
    lowered = text.lower()
    question_mark = "?" in text or "？" in text
    cue_words = (
        "how ",
        "why ",
        "what ",
        "кто",
        "как",
        "почему",
        "怎么",
        "为什么",
        "қалай",
        "неге",
    )
    return len(text) >= 12 and (question_mark or any(word in lowered for word in cue_words))


def _local_proactive_candidate(text: str) -> bool:
    """Cheap social prefilter before spending an LLM call on timing judgment."""
    lowered = text.lower().strip()
    if not _looks_like_open_question(text):
        return False
    if len(text) > 500:
        return False
    awkward_cues = (
        "болды",
        "жазба",
        "жетеді",
        "stop",
        "don't reply",
        "не отвечай",
        "хватит",
        "не пиши",
        "别说",
        "不要说",
        "尴尬",
    )
    if any(cue in lowered for cue in awkward_cues):
        return False
    # Meta questions about the bot's behavior are usually better left to humans
    # unless the bot is explicitly addressed.
    bot_meta_cues = ("bot", "бот", "zerde", "оқитын болған", "читает", "тыңдап отыр")
    if any(cue in lowered for cue in bot_meta_cues):
        return False
    return True


def score_proactive_reply(
    *,
    user_text: str,
    recent_context: str,
    long_term_memory_context: str,
    recent_bot_replies: int = 0,
) -> ProactiveReplyScore:
    """Cheap, explainable gate before asking the LLM for social timing."""
    lowered = user_text.lower().strip()
    score = 0.0
    reasons: list[str] = []

    if _looks_like_open_question(user_text):
        score += 0.34
        reasons.append("open_question")

    technical_cues = (
        "aws",
        "opensearch",
        "dynamodb",
        "lambda",
        "python",
        "telegram",
        "bot",
        "infra",
        "deploy",
        "api",
        "database",
        "serverless",
        "llm",
        "gemini",
        "deepseek",
        "groq",
    )
    if any(cue in lowered for cue in technical_cues):
        score += 0.22
        reasons.append("technical_relevance")

    if long_term_memory_context:
        memory_terms = {
            term
            for term in re.findall(r"[a-zа-яәғқңөұүһіё0-9+#._-]{4,}", long_term_memory_context.lower())
            if term not in {"summary", "speaker", "reason", "daily"}
        }
        if any(term in lowered for term in list(memory_terms)[:80]):
            score += 0.16
            reasons.append("matches_group_memory")

    if recent_context:
        score += 0.08
        reasons.append("has_recent_context")
    else:
        score -= 0.08
        reasons.append("no_recent_context")

    if len(user_text) > 220:
        score += 0.05
        reasons.append("substantial_question")

    if any(cue in lowered for cue in ("anyone", "кто-нибудь", "біреу", "有人", "does anyone")):
        score += 0.08
        reasons.append("asks_group")

    if recent_bot_replies:
        penalty = min(0.32, recent_bot_replies * 0.16)
        score -= penalty
        reasons.append(f"recent_bot_activity_penalty:{recent_bot_replies}")

    if any(cue in lowered for cue in ("haha", "lol", "ахах", "хаха", "哈哈")):
        score -= 0.18
        reasons.append("joke_penalty")

    return ProactiveReplyScore(score=max(0.0, min(1.0, score)), reasons=tuple(reasons))


def _trigger_kind(update: dict[str, Any]) -> str | None:
    if not AGENT_ENABLED or not _is_plain_text_message(update):
        return None
    message = update["message"]
    text = extract_message_text(message)
    if _mentions_bot(text) or _replies_to_bot(message):
        return "explicit"
    if _local_proactive_candidate(text):
        return "proactive"
    return None


def should_answer(update: dict[str, Any]) -> bool:
    """Return True when the agent policy allows considering an answer."""
    return _trigger_kind(update) is not None


def handle_update(
    *,
    repo: GroupMemoryRepository | None,
    bot: TelegramClient,
    update: dict[str, Any],
) -> bool:
    """Answer an explicit group chat prompt with recent group context.

    Returns True when the agent handled the update and the dispatcher should not
    continue routing it as a plain message.
    """
    trigger_kind = _trigger_kind(update)
    if repo is None or trigger_kind is None:
        return False

    message = update["message"]
    chat_id = message["chat"]["id"]
    if not repo.is_agent_enabled(chat_id):
        return False
    message_id = message["message_id"]
    if trigger_kind == "proactive":
        return maybe_answer_proactively(
            repo=repo,
            bot=bot,
            chat_id=chat_id,
            reply_to_message_id=message_id,
            user_text=extract_message_text(message),
            lang=get_chat_lang(chat_id),
        )

    handled = answer_group_question(
        repo=repo,
        bot=bot,
        chat_id=chat_id,
        reply_to_message_id=message_id,
        user_text=_explicit_user_text(repo, chat_id, message),
        lang=get_chat_lang(chat_id),
        requester_user_id=(message.get("from") or {}).get("id"),
        requester_username=(message.get("from") or {}).get("username"),
        requester_display_name=display_name(message.get("from") or {}),
    )
    if handled:
        logger.info(
            "Group agent handled update",
            extra={"chat_id": chat_id, "message_id": message_id, "trigger_kind": trigger_kind},
        )
    return handled


def maybe_answer_proactively(
    *,
    repo: GroupMemoryRepository,
    bot: TelegramClient,
    chat_id: int,
    reply_to_message_id: int,
    user_text: str,
    lang: str,
) -> bool:
    """Ask the model whether speaking is socially useful; speak only on a strong yes."""
    gemini = _get_gemini()
    if not gemini:
        return False

    recent_context = format_recent_context(repo, chat_id, limit=AGENT_RECENT_CONTEXT_LIMIT)
    long_term_memory_context = format_long_term_memory_context(repo, chat_id, query_text=user_text)
    raw_recent_bot_replies = repo.count_recent_agent_replies(chat_id, since_epoch=int(time.time()) - 60 * 60)
    recent_bot_replies = int(raw_recent_bot_replies) if isinstance(raw_recent_bot_replies, Number) else 0
    reply_score = score_proactive_reply(
        user_text=user_text,
        recent_context=recent_context,
        long_term_memory_context=long_term_memory_context,
        recent_bot_replies=recent_bot_replies,
    )
    if reply_score.score < AGENT_PROACTIVE_SCORE_THRESHOLD:
        logger.info(
            "Group agent proactive candidate skipped by reply score",
            extra={
                "chat_id": chat_id,
                "message_id": reply_to_message_id,
                "reply_score": reply_score.score,
                "reasons": ",".join(reply_score.reasons),
            },
        )
        return False

    try:
        decision, _ = gemini.group_chat_proactive_decision(
            user_message=user_text,
            recent_context=recent_context,
            long_term_memory_context=long_term_memory_context,
            lang=lang,
        )
    except GeminiRPDExhaustedError:
        logger.info("Group agent proactive decision skipped by Gemini RPD limit", extra={"chat_id": chat_id})
        return False
    except GeminiUnavailableError:
        logger.warning("Group agent proactive decision unavailable", extra={"chat_id": chat_id})
        return False
    except Exception:
        logger.exception("Group agent proactive decision failed", extra={"chat_id": chat_id})
        return False

    final_score = reply_score.score * 0.45 + decision.confidence * 0.55
    if not decision.should_reply or final_score < AGENT_PROACTIVE_FINAL_THRESHOLD or not decision.reply_text:
        logger.info(
            "Group agent stayed silent",
            extra={
                "chat_id": chat_id,
                "message_id": reply_to_message_id,
                "confidence": decision.confidence,
                "reply_score": reply_score.score,
                "final_score": final_score,
                "reason": decision.reason,
            },
        )
        return False

    if not repo.try_reserve_proactive_reply(chat_id, daily_limit=AGENT_DAILY_PROACTIVE_LIMIT):
        logger.info(
            "Group agent proactive reply skipped by daily limit",
            extra={"chat_id": chat_id, "message_id": reply_to_message_id, "reason": decision.reason},
        )
        return False

    answer_text = fit_llm_output(decision.reply_text, max_chars=900)
    answer_html = normalize_llm_output_for_telegram_html(answer_text)
    sent = bot.send_message(chat_id, answer_html, reply_to_message_id=reply_to_message_id)
    bot_message_id = sent.get("message_id") if isinstance(sent, dict) else None
    if bot_message_id:
        repo.record_agent_reply(
            chat_id=chat_id,
            bot_message_id=bot_message_id,
            trigger_message_id=reply_to_message_id,
            trigger_kind="proactive",
            reason=(
                f"{decision.reason or 'I judged this as a useful moment to answer.'} "
                f"reply_score={reply_score.score:.2f}; signals={', '.join(reply_score.reasons)}"
            ),
            answer_text=answer_text,
            user_message=user_text,
            confidence=final_score,
        )
    logger.info(
        "Group agent handled update",
        extra={
            "chat_id": chat_id,
            "message_id": reply_to_message_id,
            "trigger_kind": "proactive",
            "confidence": decision.confidence,
            "reply_score": reply_score.score,
            "final_score": final_score,
            "reason": decision.reason,
        },
    )
    return True


def answer_group_question(
    *,
    repo: GroupMemoryRepository,
    bot: TelegramClient,
    chat_id: int,
    reply_to_message_id: int,
    user_text: str,
    lang: str,
    requester_user_id: int | str | None = None,
    requester_username: str | None = None,
    requester_display_name: str | None = None,
    raise_on_unavailable: bool = False,
) -> bool:
    """Generate and send a group-context reply for an explicit question."""
    guarded_answer = _guardrail_reply(user_text, lang)
    if guarded_answer:
        answer_html = normalize_llm_output_for_telegram_html(guarded_answer)
        sent = bot.send_message(chat_id, answer_html, reply_to_message_id=reply_to_message_id)
        bot_message_id = sent.get("message_id") if isinstance(sent, dict) else None
        if bot_message_id:
            repo.record_agent_reply(
                chat_id=chat_id,
                bot_message_id=bot_message_id,
                trigger_message_id=reply_to_message_id,
                trigger_kind="explicit",
                reason="Guardrail blocked a subjective ranking or persistent future-answer directive.",
                answer_text=guarded_answer,
                user_message=user_text,
            )
        return True

    gemini = _get_gemini()
    if not gemini:
        return False

    recent_context = format_recent_context(repo, chat_id, limit=AGENT_RECENT_CONTEXT_LIMIT)
    long_term_memory_context = format_long_term_memory_context(repo, chat_id, query_text=user_text)
    self_reference = _looks_like_self_reference(user_text)
    semantic_memories = retrieve_relevant_memories(
        chat_id,
        user_text,
        limit=8,
        user_id=requester_user_id if self_reference else None,
    )
    semantic_memory_context = format_semantic_memory_context(semantic_memories)
    logger.info(
        "Group agent semantic memory context prepared",
        extra={
            "chat_id": chat_id,
            "retrieved_count": len(semantic_memories),
            "context_item_count": len(semantic_memory_context.splitlines()) if semantic_memory_context else 0,
            "context_chars": len(semantic_memory_context),
            "self_reference": self_reference,
            "requester_filter_applied": bool(self_reference and requester_user_id is not None),
        },
    )
    ignored_usernames = {AGENT_BOT_USERNAME} if AGENT_BOT_USERNAME else set()
    user_profile_context = format_user_profile_context(
        repo,
        chat_id,
        user_text=user_text,
        ignored_usernames=ignored_usernames,
    )
    requester_profile_context = format_requester_profile_context(
        repo,
        chat_id,
        requester_user_id=requester_user_id,
        requester_username=requester_username,
        requester_display_name=requester_display_name,
    )
    reply_policy = _reply_policy(user_text)

    try:
        answer, _ = gemini.group_chat_reply(
            user_message=user_text,
            recent_context=recent_context,
            long_term_memory_context=long_term_memory_context,
            semantic_memory_context=semantic_memory_context,
            user_profile_context=user_profile_context,
            requester_profile_context=requester_profile_context,
            reply_instructions=reply_policy.instructions,
            max_output_tokens=reply_policy.max_output_tokens,
            lang=lang,
        )
    except GeminiRPDExhaustedError:
        bot.send_message(
            chat_id,
            get_translated_text("ask_daily_quota_exhausted", lang),
            reply_to_message_id=reply_to_message_id,
        )
        return True
    except GeminiUnavailableError:
        logger.warning("Group agent Gemini call unavailable", extra={"chat_id": chat_id})
        if raise_on_unavailable:
            raise
        return False
    except Exception:
        logger.exception("Group agent failed", extra={"chat_id": chat_id})
        if raise_on_unavailable:
            raise
        return False

    answer_text = fit_llm_output(answer, max_chars=reply_policy.max_chars)
    answer_html = normalize_llm_output_for_telegram_html(answer_text)
    sent = bot.send_message(chat_id, answer_html, reply_to_message_id=reply_to_message_id)
    bot_message_id = sent.get("message_id") if isinstance(sent, dict) else None
    if bot_message_id:
        repo.record_agent_reply(
            chat_id=chat_id,
            bot_message_id=bot_message_id,
            trigger_message_id=reply_to_message_id,
            trigger_kind="explicit",
            reason=(
                "I was mentioned, replied to, or called through /ask, "
                "so I answered with recent, semantic, and trusted memory context."
            ),
            answer_text=answer_text,
            user_message=user_text,
            requester_user_id=requester_user_id,
            requester_username=requester_username,
            requester_display_name=requester_display_name,
        )
    return True
