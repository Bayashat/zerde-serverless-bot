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
    AGENT_PROACTIVE_DELAY_SECONDS,
    AGENT_PROACTIVE_FINAL_THRESHOLD,
    AGENT_PROACTIVE_SCORE_THRESHOLD,
    AGENT_RECENT_CONTEXT_LIMIT,
    get_chat_lang,
    get_gemini_api_key,
)
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.ai.gemini_client import (
    GeminiClient,
    GeminiEmptyResponseError,
    GeminiRPDExhaustedError,
    GeminiUnavailableError,
)
from services.ai.telegram_html import fit_llm_output, normalize_llm_output_for_telegram_html
from services.group_memory import (
    display_name,
    extract_message_text,
    format_long_term_memory_context,
    format_message_reference,
    format_recent_context,
    format_requester_profile_context,
    format_user_profile_context,
)
from services.memory_retrieval import build_agent_memory_context
from services.memory_safety import (
    looks_like_future_answer_directive,
    looks_like_subjective_person_ranking_question,
)
from services.repositories.group_memory import GroupMemoryRepository
from services.repositories.sqs import SQSClient
from services.telegram import TelegramClient
from services.vector_memory import format_semantic_memory_context, retrieve_relevant_memories

logger = LoggerAdapter(get_logger(__name__), {})

_agent_gemini: GeminiClient | None = None


@dataclass(frozen=True)
class ProactiveReplyScore:
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ReplyPolicy:
    instructions: str
    max_output_tokens: int
    max_chars: int


@dataclass(frozen=True)
class ExplicitQuestionContext:
    user_text: str
    current_user_message: str
    retrieval_query: str
    source_message_context: str = ""
    parent_bot_message_id: int | None = None


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


def _load_agent_reply_context(
    repo: GroupMemoryRepository,
    chat_id: int | str,
    *,
    bot_message_id: int | str,
) -> dict[str, Any]:
    try:
        item = repo.get_agent_reply_explanation(chat_id, bot_message_id=bot_message_id)
    except Exception:
        logger.exception("Failed to load previous agent reply context", extra={"chat_id": chat_id})
        return {}
    return item if isinstance(item, dict) else {}


def _agent_reply_thread_context(
    item: dict[str, Any],
    *,
    telegram_reply_text: str,
) -> str:
    source_context = str(item.get("source_message_context") or "").strip()
    previous_user = str(item.get("current_user_message") or item.get("user_message") or "").strip()
    previous_answer = str(item.get("answer_text") or telegram_reply_text or "").strip()
    parts = ["The user is continuing a thread with this previous bot answer:"]
    if source_context:
        parts.append(f"Original source message for the previous answer:\n{source_context[:1800]}")
    if previous_user:
        parts.append(f"Previous user request:\n{previous_user[:1200]}")
    if previous_answer:
        parts.append(f"Previous bot answer:\n{previous_answer[:1800]}")
    elif telegram_reply_text:
        parts.append(f"Previous bot answer from Telegram reply:\n{telegram_reply_text[:1800]}")
    return "\n\n".join(parts)


def _compact_query_text(text: str, *, limit: int) -> str:
    return " ".join((text or "").split())[:limit]


def _reply_source_retrieval_query(*, current_question: str, source_context: str) -> str:
    question = _compact_query_text(current_question, limit=600)
    source = _compact_query_text(source_context, limit=700)
    if question and source:
        return f"{question}\n\nReplied source message: {source}"
    if question:
        return question
    if source:
        return f"Explain replied source message: {source}"
    return ""


def _agent_reply_thread_retrieval_query(
    item: dict[str, Any],
    *,
    followup: str,
    telegram_reply_text: str,
) -> str:
    source_context = _compact_query_text(str(item.get("source_message_context") or ""), limit=700)
    previous_user = _compact_query_text(
        str(item.get("current_user_message") or item.get("user_message") or ""),
        limit=600,
    )
    followup_text = _compact_query_text(followup, limit=300)
    parts: list[str] = []
    if followup_text:
        parts.append(f"Current follow-up: {followup_text}")
    if previous_user:
        parts.append(f"Previous user request: {previous_user}")
    if source_context:
        parts.append(f"Original source message: {source_context}")
    if len(parts) <= 1:
        fallback_answer = _compact_query_text(str(item.get("answer_text") or telegram_reply_text or ""), limit=400)
        if fallback_answer:
            parts.append(f"Previous bot answer: {fallback_answer}")
    return "\n\n".join(parts)


def build_explicit_question_context(
    repo: GroupMemoryRepository,
    chat_id: int | str,
    message: dict[str, Any],
    *,
    current_text: str | None = None,
) -> ExplicitQuestionContext:
    text = (current_text if current_text is not None else extract_message_text(message)).strip()
    reply = message.get("reply_to_message")
    if not isinstance(reply, dict):
        return ExplicitQuestionContext(user_text=text, current_user_message=text, retrieval_query=text)

    if _replies_to_bot(message):
        replied_text = _reply_text(message)
        parent_bot_message_id = reply.get("message_id")
        item = _load_agent_reply_context(
            repo,
            chat_id,
            bot_message_id=parent_bot_message_id or 0,
        )
        thread_context = _agent_reply_thread_context(
            item,
            telegram_reply_text=replied_text,
        )
        source_context = str(item.get("source_message_context") or "").strip()
        followup = text or "The user replied to the previous bot answer and wants an explanation or continuation."
        return ExplicitQuestionContext(
            user_text=f"{thread_context}\n\nUser follow-up:\n{followup}",
            current_user_message=text,
            retrieval_query=_agent_reply_thread_retrieval_query(
                item,
                followup=followup,
                telegram_reply_text=replied_text,
            ),
            source_message_context=source_context,
            parent_bot_message_id=int(parent_bot_message_id) if parent_bot_message_id is not None else None,
        )

    source_context = format_message_reference(reply)
    if not source_context:
        return ExplicitQuestionContext(user_text=text, current_user_message=text, retrieval_query=text)
    if text:
        user_text = (
            "The user is asking about this replied-to group message:\n"
            f"{source_context}\n\n"
            "User question:\n"
            f"{text}"
        )
    else:
        user_text = (
            "The user replied to this group message and wants you to explain it or answer based on it:\n"
            f"{source_context}"
        )
    return ExplicitQuestionContext(
        user_text=user_text,
        current_user_message=text,
        retrieval_query=_reply_source_retrieval_query(current_question=text, source_context=source_context),
        source_message_context=source_context,
    )


def _clear_reply_to_bot_request(text: str) -> bool:
    lowered = " ".join((text or "").lower().split())
    if not lowered:
        return False
    if "?" in text or "？" in text:
        return True
    if re.search(
        r"\b(why|how|what|who|where|when|explain|expand|elaborate|detail|details|more|example|examples)\b",
        lowered,
    ):
        return True
    if re.search(
        (
            r"(^|\s)(қалай|неге|не|кім|түсіндір|толық|толығырақ|мысал|как|что|кто|почему|зачем|"
            r"объясни|расскажи|подробнее|поделись)(\s|$|[?.!,])"
        ),
        lowered,
    ):
        return True
    return any(cue in lowered for cue in ("怎么", "为什么", "什么", "谁", "解释", "详细", "展开", "举例"))


def _reply_to_bot_followup_skip_reason(text: str) -> str | None:
    lowered = " ".join((text or "").lower().split())
    if not lowered:
        return "empty_followup"
    if _clear_reply_to_bot_request(text):
        return None
    reaction_cues = (
        "haha",
        "lol",
        "lmao",
        "хаха",
        "ахах",
        "哈哈",
        "thanks",
        "thank you",
        "спасибо",
        "рахмет",
        "ок",
        "okay",
        "interesting",
        "nice",
        "cool",
        "қызық",
        "круто",
    )
    if any(cue in lowered for cue in reaction_cues):
        return "reaction_or_ack"
    return "no_clear_question_or_request"


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
        "which ",
        "кто",
        "как",
        "что",
        "какой",
        "какая",
        "какие",
        "где",
        "когда",
        "зачем",
        "почему",
        "怎么",
        "为什么",
        "什么",
        "哪",
        "қалай",
        "қандай",
        "қайсы",
        "қайда",
        "қашан",
        "кім",
        "неге",
    )
    return len(text) >= 12 and (question_mark or any(word in lowered for word in cue_words))


_PROACTIVE_STOP_CUES = (
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

_PROACTIVE_BOT_META_CUES = (
    "zerde",
    "зерде",
    "оқитын болған",
    "оқып отыр",
    "тыңдап отыр",
    "читает чат",
    "читает все",
    "читает любые",
    "слушает чат",
    "reading every",
    "reads every",
    "listening to everything",
    "why is the bot replying",
    "bot keeps replying",
    "бот жауап беріп жатыр",
    "бот отвечает",
)

_PROACTIVE_TECHNICAL_CUES = (
    "aws",
    "opensearch",
    "dynamodb",
    "lambda",
    "python",
    "telegram",
    "телеграм",
    "bot",
    "бот",
    "техникалық",
    "стэк",
    "стек",
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

_PROACTIVE_SUGGESTION_CUES = (
    "idea",
    "ideas",
    "suggest",
    "recommend",
    "advice",
    "topic",
    "project idea",
    "идея",
    "идеи",
    "идею",
    "посовет",
    "предлож",
    "совет",
    "тема",
    "диплом",
    "ұсын",
    "кеңес",
    "тақырып",
    "жоба",
    "проект",
    "қоса аласың",
    "毕业",
    "论文",
    "课题",
    "建议",
    "推荐",
    "想法",
)

_PROACTIVE_GROUP_REQUEST_CUES = (
    "anyone",
    "any ideas",
    "does anyone",
    "what do you all",
    "what would you",
    "кто-нибудь",
    "что посоветуете",
    "какие идеи",
    "біреу",
    "ұсына аласыңдар",
    "қоса аласыңдар",
    "не дейсіңдер",
    "有什么建议",
    "有推荐",
    "大家",
    "有人",
)

_PROACTIVE_HUMAN_ANSWER_CUES = (
    "you can",
    "you should",
    "use ",
    "try ",
    "depends",
    "because",
    "i think",
    "i'd ",
    "i would",
    "better to",
    "лучше",
    "можно",
    "нужно",
    "надо",
    "попроб",
    "потому",
    "думаю",
    "болады",
    "керек",
    "қолдан",
    "себебі",
    "меніңше",
    "可以",
    "建议",
    "因为",
    "用",
)
_PROACTIVE_HUMAN_SOLVED_CUES = (
    "solved",
    "figured it out",
    "got it",
    "нашел",
    "нашла",
    "решил",
    "решили",
    "понял",
    "таптым",
    "шешілді",
    "түсіндім",
    "解决了",
    "懂了",
)
_PROACTIVE_TERM_RE = re.compile(r"[0-9a-zа-яәғқңөұүһіё][0-9a-zа-яәғқңөұүһіё+#._-]{2,}", re.IGNORECASE)
_PROACTIVE_TERM_STOPWORDS = {
    "any",
    "are",
    "can",
    "does",
    "for",
    "how",
    "know",
    "the",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "есть",
    "как",
    "кто",
    "что",
    "это",
    "бар",
    "бір",
    "деп",
    "кім",
    "не",
    "осы",
}


def _looks_like_bot_behavior_meta(text: str) -> bool:
    """Return True for bot-behavior meta chatter, not generic bot-building questions."""
    lowered = " ".join((text or "").lower().split())
    return any(cue in lowered for cue in _PROACTIVE_BOT_META_CUES)


def _proactive_terms(text: str) -> set[str]:
    return {
        term.lstrip("@").lower()
        for term in _PROACTIVE_TERM_RE.findall(text or "")
        if term and term.lower() not in _PROACTIVE_TERM_STOPWORDS and not term.isdigit()
    }


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _looks_like_sufficient_human_answer(text: str, *, trigger_terms: set[str]) -> bool:
    lowered = " ".join((text or "").lower().split())
    if not lowered or lowered.startswith("/"):
        return False
    if any(cue in lowered for cue in _PROACTIVE_HUMAN_SOLVED_CUES):
        return True

    answer_cue = any(cue in lowered for cue in _PROACTIVE_HUMAN_ANSWER_CUES)
    response_terms = _proactive_terms(lowered)
    overlaps_trigger = bool(trigger_terms & response_terms)
    open_question = _looks_like_open_question(text)

    if open_question and not answer_cue:
        return False
    if answer_cue and (overlaps_trigger or len(text) >= 24):
        return True
    return overlaps_trigger and len(text) >= 40 and not open_question


def _human_answer_after_trigger(
    repo: GroupMemoryRepository,
    chat_id: int,
    *,
    trigger_message_id: int,
    trigger_user_id: int | str | None,
    trigger_created_at: int | None,
    user_text: str,
) -> dict[str, Any] | None:
    start_epoch = int(trigger_created_at or 0)
    end_epoch = int(time.time()) + 1
    if start_epoch > 0:
        messages = repo.get_messages_for_day(chat_id, start_epoch=start_epoch, end_epoch=end_epoch, limit=25)
    else:
        messages = repo.get_recent_messages(chat_id, limit=25)

    trigger_terms = _proactive_terms(user_text)
    trigger_user = str(trigger_user_id) if trigger_user_id is not None else ""
    for item in messages:
        message_id = _safe_int(item.get("message_id"))
        if message_id is not None and message_id <= trigger_message_id:
            continue
        text = str(item.get("text") or "").strip()
        if not text or text == user_text:
            continue
        user_id = item.get("user_id")
        same_user = trigger_user and str(user_id) == trigger_user
        if same_user and not any(cue in text.lower() for cue in _PROACTIVE_HUMAN_SOLVED_CUES):
            continue
        if _looks_like_sufficient_human_answer(text, trigger_terms=trigger_terms):
            return {
                "message_id": message_id,
                "user_id": user_id,
                "text_chars": len(text),
            }
    return None


def _log_proactive_silent(
    silent_reason: str,
    *,
    chat_id: int | str,
    message_id: int | str | None = None,
    **extra: Any,
) -> None:
    payload = {"chat_id": chat_id, "message_id": message_id, "silent_reason": silent_reason}
    payload.update(extra)
    logger.info("Group agent proactive candidate stayed silent", extra=payload)


def _local_proactive_skip_reason(text: str) -> str | None:
    """Explain why a message is rejected before proactive score/model gating."""
    lowered = text.lower().strip()
    if not _looks_like_open_question(text):
        return "not_open_question"
    if len(text) > 500:
        return "too_long"
    if any(cue in lowered for cue in _PROACTIVE_STOP_CUES):
        return "stop_or_awkward_cue"
    if _looks_like_bot_behavior_meta(text):
        return "bot_meta"
    return None


def _local_proactive_candidate(text: str) -> bool:
    """Cheap social prefilter before spending an LLM call on timing judgment."""
    return _local_proactive_skip_reason(text) is None


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

    if any(cue in lowered for cue in _PROACTIVE_TECHNICAL_CUES):
        score += 0.22
        reasons.append("technical_relevance")

    if any(cue in lowered for cue in _PROACTIVE_SUGGESTION_CUES):
        score += 0.22
        reasons.append("asks_for_suggestions")

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

    if any(cue in lowered for cue in _PROACTIVE_GROUP_REQUEST_CUES):
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
    if _mentions_bot(text):
        return "explicit"
    if _replies_to_bot(message) and _reply_to_bot_followup_skip_reason(text) is None:
        return "explicit"
    if _local_proactive_candidate(text):
        return "proactive"
    return None


def _log_skipped_reply_to_bot_followup(update: dict[str, Any]) -> None:
    if not AGENT_ENABLED or not _is_plain_text_message(update):
        return
    message = update["message"]
    text = extract_message_text(message)
    if not _replies_to_bot(message) or _mentions_bot(text):
        return
    skip_reason = _reply_to_bot_followup_skip_reason(text)
    if not skip_reason:
        return
    logger.info(
        "Group agent reply-to-bot follow-up skipped",
        extra={
            "chat_id": (message.get("chat") or {}).get("id"),
            "message_id": message.get("message_id"),
            "skip_reason": skip_reason,
        },
    )


def _log_skipped_proactive_prefilter(update: dict[str, Any]) -> None:
    if not AGENT_ENABLED or not _is_plain_text_message(update):
        return
    message = update["message"]
    text = extract_message_text(message)
    if _mentions_bot(text) or _replies_to_bot(message):
        return
    skip_reason = _local_proactive_skip_reason(text)
    if not skip_reason or skip_reason == "not_open_question":
        return
    logger.info(
        "Group agent proactive candidate skipped by local prefilter",
        extra={
            "chat_id": (message.get("chat") or {}).get("id"),
            "message_id": message.get("message_id"),
            "skip_reason": skip_reason,
            "text_chars": len(text),
        },
    )


def should_answer(update: dict[str, Any]) -> bool:
    """Return True when the agent policy allows considering an answer."""
    return _trigger_kind(update) is not None


def handle_update(
    *,
    repo: GroupMemoryRepository | None,
    bot: TelegramClient,
    update: dict[str, Any],
    sqs_repo: SQSClient | None = None,
) -> bool:
    """Handle non-/ask group prompts when agent participation is enabled.

    ``agent_enabled`` gates proactive, @mention, and reply-to-bot
    participation. Explicit ``/ask`` requests are handled by the command path
    and remain available while group memory is enabled. Proactive candidates
    are queued for a delayed final decision; explicit triggers answer now.

    Returns True when the agent handled the update and the dispatcher should not
    continue routing it as a plain message.
    """
    trigger_kind = _trigger_kind(update)
    if trigger_kind is None:
        _log_skipped_reply_to_bot_followup(update)
        _log_skipped_proactive_prefilter(update)
        return False
    if repo is None:
        return False

    message = update["message"]
    chat_id = message["chat"]["id"]
    if not repo.is_agent_enabled(chat_id):
        return False
    message_id = message["message_id"]
    if trigger_kind == "proactive":
        if sqs_repo is None:
            logger.warning(
                "Group agent proactive candidate could not be queued",
                extra={"chat_id": chat_id, "message_id": message_id, "reason": "missing_sqs_repo"},
            )
            return False
        sqs_repo.send_proactive_candidate_task(
            update_id=update.get("update_id"),
            chat_id=chat_id,
            trigger_message_id=message_id,
            trigger_user_id=(message.get("from") or {}).get("id"),
            user_text=extract_message_text(message),
            lang=get_chat_lang(chat_id),
            created_at=message.get("date"),
            delay_seconds=AGENT_PROACTIVE_DELAY_SECONDS,
        )
        logger.info(
            "Group agent proactive candidate queued",
            extra={
                "chat_id": chat_id,
                "message_id": message_id,
                "delay_seconds": AGENT_PROACTIVE_DELAY_SECONDS,
            },
        )
        return True

    question_context = build_explicit_question_context(repo, chat_id, message)
    handled = answer_group_question(
        repo=repo,
        bot=bot,
        chat_id=chat_id,
        reply_to_message_id=message_id,
        user_text=question_context.user_text,
        retrieval_query=question_context.retrieval_query,
        lang=get_chat_lang(chat_id),
        requester_user_id=(message.get("from") or {}).get("id"),
        requester_username=(message.get("from") or {}).get("username"),
        requester_display_name=display_name(message.get("from") or {}),
        current_user_message=question_context.current_user_message,
        source_message_context=question_context.source_message_context,
        parent_bot_message_id=question_context.parent_bot_message_id,
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
        _log_proactive_silent("gemini_not_configured", chat_id=chat_id, message_id=reply_to_message_id)
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
        _log_proactive_silent(
            "low_reply_score",
            chat_id=chat_id,
            message_id=reply_to_message_id,
            reply_score=reply_score.score,
            reasons=",".join(reply_score.reasons),
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
        _log_proactive_silent("gemini_rpd_limit", chat_id=chat_id, message_id=reply_to_message_id)
        return False
    except GeminiUnavailableError as exc:
        _log_proactive_silent(
            "gemini_unavailable",
            chat_id=chat_id,
            message_id=reply_to_message_id,
            error_type=exc.__class__.__name__,
            error_message=str(exc)[:500],
        )
        return False
    except Exception:
        logger.exception("Group agent proactive decision failed", extra={"chat_id": chat_id})
        return False

    final_score = reply_score.score * 0.45 + decision.confidence * 0.55
    if not decision.should_reply or final_score < AGENT_PROACTIVE_FINAL_THRESHOLD or not decision.reply_text:
        _log_proactive_silent(
            "model_said_no",
            chat_id=chat_id,
            message_id=reply_to_message_id,
            confidence=decision.confidence,
            reply_score=reply_score.score,
            final_score=final_score,
            reason=decision.reason,
        )
        return False

    if not repo.try_reserve_proactive_reply(chat_id, daily_limit=AGENT_DAILY_PROACTIVE_LIMIT):
        _log_proactive_silent(
            "daily_limit",
            chat_id=chat_id,
            message_id=reply_to_message_id,
            reason=decision.reason,
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
            current_user_message=user_text,
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


def process_proactive_candidate_task(
    *,
    repo: GroupMemoryRepository,
    bot: TelegramClient,
    body: dict[str, Any],
) -> bool:
    """Finalize a delayed proactive candidate after humans had time to answer."""
    try:
        chat_id = int(body["chat_id"])
        trigger_message_id = int(body["trigger_message_id"])
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("PROCESS_PROACTIVE_CANDIDATE missing required field", extra={"error": str(exc)})
        return False

    user_text = str(body.get("user_text") or "").strip()
    if not user_text:
        _log_proactive_silent("missing_user_text", chat_id=chat_id, message_id=trigger_message_id)
        return False

    if not repo.is_agent_enabled(chat_id):
        _log_proactive_silent("agent_disabled", chat_id=chat_id, message_id=trigger_message_id)
        return False

    skip_reason = _local_proactive_skip_reason(user_text)
    if skip_reason is not None:
        _log_proactive_silent(
            "original_no_longer_useful",
            chat_id=chat_id,
            message_id=trigger_message_id,
            original_skip_reason=skip_reason,
        )
        return False

    try:
        human_answer = _human_answer_after_trigger(
            repo,
            chat_id,
            trigger_message_id=trigger_message_id,
            trigger_user_id=body.get("trigger_user_id"),
            trigger_created_at=_safe_int(body.get("created_at")),
            user_text=user_text,
        )
    except Exception:
        logger.exception("Failed to read post-trigger context for proactive candidate", extra={"chat_id": chat_id})
        _log_proactive_silent("post_trigger_context_unavailable", chat_id=chat_id, message_id=trigger_message_id)
        return False
    if human_answer:
        _log_proactive_silent(
            "human_answered",
            chat_id=chat_id,
            message_id=trigger_message_id,
            answer_message_id=human_answer.get("message_id"),
            answer_user_id=human_answer.get("user_id"),
            answer_text_chars=human_answer.get("text_chars"),
        )
        return False

    return maybe_answer_proactively(
        repo=repo,
        bot=bot,
        chat_id=chat_id,
        reply_to_message_id=trigger_message_id,
        user_text=user_text,
        lang=str(body.get("lang") or get_chat_lang(chat_id)),
    )


def answer_group_question(
    *,
    repo: GroupMemoryRepository,
    bot: TelegramClient,
    chat_id: int,
    reply_to_message_id: int,
    user_text: str,
    lang: str,
    retrieval_query: str | None = None,
    requester_user_id: int | str | None = None,
    requester_username: str | None = None,
    requester_display_name: str | None = None,
    current_user_message: str | None = None,
    source_message_context: str | None = None,
    parent_bot_message_id: int | str | None = None,
    raise_on_unavailable: bool = False,
) -> bool:
    """Generate and send a group-context reply for an explicit question."""
    current_user_message = user_text if current_user_message is None else current_user_message
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
                current_user_message=current_user_message,
                source_message_context=source_message_context,
                parent_bot_message_id=parent_bot_message_id,
            )
        return True

    gemini = _get_gemini()
    if not gemini:
        return False

    ignored_usernames = {AGENT_BOT_USERNAME} if AGENT_BOT_USERNAME else set()
    memory_bundle = build_agent_memory_context(
        repo=repo,
        chat_id=chat_id,
        user_text=user_text,
        retrieval_query=retrieval_query,
        requester_user_id=requester_user_id,
        requester_username=requester_username,
        requester_display_name=requester_display_name,
        ignored_usernames=ignored_usernames,
        recent_limit=AGENT_RECENT_CONTEXT_LIMIT,
        semantic_limit=8,
        recent_context_fn=format_recent_context,
        long_term_context_fn=format_long_term_memory_context,
        semantic_retrieval_fn=retrieve_relevant_memories,
        semantic_context_fn=format_semantic_memory_context,
        user_profile_context_fn=format_user_profile_context,
        requester_profile_context_fn=format_requester_profile_context,
    )
    logger.info(
        "Group agent memory retrieval context prepared",
        extra={
            "chat_id": chat_id,
            "candidate_count": len(memory_bundle.candidates),
            "retrieval_source_count": len(memory_bundle.retrieval_sources),
            "semantic_context_item_count": (
                len(memory_bundle.semantic_memory_context.splitlines()) if memory_bundle.semantic_memory_context else 0
            ),
            "semantic_context_chars": len(memory_bundle.semantic_memory_context),
            "self_reference": memory_bundle.intent.is_self_reference,
            "requester_filter_applied": bool(memory_bundle.intent.is_self_reference and requester_user_id is not None),
            "target_username_count": len(memory_bundle.intent.target_usernames),
            "retrieval_query_chars": len((retrieval_query or user_text).strip()),
        },
    )
    reply_policy = _reply_policy(user_text)

    try:
        answer, _ = gemini.group_chat_reply(
            user_message=user_text,
            recent_context=memory_bundle.recent_context,
            long_term_memory_context=memory_bundle.long_term_memory_context,
            semantic_memory_context=memory_bundle.semantic_memory_context,
            user_profile_context=memory_bundle.user_profile_context,
            requester_profile_context=memory_bundle.requester_profile_context,
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
    except GeminiUnavailableError as exc:
        retryable = getattr(exc, "retryable", True)
        logger.warning(
            "Group agent Gemini call unavailable",
            extra={
                "chat_id": chat_id,
                "reply_to_message_id": reply_to_message_id,
                "error_type": exc.__class__.__name__,
                "error_message": str(exc)[:500],
                "retryable": retryable,
            },
        )
        if raise_on_unavailable and retryable and not isinstance(exc, GeminiEmptyResponseError):
            raise
        bot.send_message(
            chat_id,
            get_translated_text("ask_agent_unavailable", lang),
            reply_to_message_id=reply_to_message_id,
        )
        return True
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
            current_user_message=current_user_message,
            source_message_context=source_message_context,
            parent_bot_message_id=parent_bot_message_id,
            requester_user_id=requester_user_id,
            requester_username=requester_username,
            requester_display_name=requester_display_name,
            retrieval_sources=memory_bundle.retrieval_sources,
        )
    return True
