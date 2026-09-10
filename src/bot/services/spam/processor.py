"""SQS processor for SPAM_CHECK tasks: Layer-2 Groq classification and enforcement."""

import re
from html import escape
from typing import Any

from core.config import (
    SPAM_AI_CONFIDENCE_THRESHOLD,
    SPAM_REVIEW_BAN_PREFIX,
    SPAM_REVIEW_IGNORE_PREFIX,
    TELEGRAM_CHANNEL_POST_ACTOR_USER_ID,
    get_chat_lang,
    get_spam_review_admin_mentions,
)
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from services.repositories.captcha import CaptchaRepository
from services.repositories.group_memory import GroupMemoryRepository
from services.repositories.spam import SpamRepository
from services.spam.chat_member import is_chat_admin_or_creator
from services.spam.enforcer import (
    SpamEnforcer,
    permanent_telegram_failure,
    resolve_spam_target_mention,
    translate_spam_reason,
)
from services.spam.groq_detector import GroqSpamDetector, SpamCheckResult
from services.spam.message_text import format_spam_ai_context
from services.spam.rule_filter import RuleBasedSpamFilter
from services.telegram import TelegramClient
from zerde_common.ai_errors import ProviderResponseError

logger = LoggerAdapter(get_logger(__name__), {})

_detector: GroqSpamDetector | None = None
_RECENT_CONTEXT_QUERY_LIMIT = 12
_RECENT_CONTEXT_RENDER_LIMIT = 8
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")
_STRONG_AUTO_ENFORCE_RULES = frozenset(
    {
        "external_url",
        "external_mention",
        "vpn_pattern",
        "dm_redirect",
        "money_and_dm_redirect",
        "scam_hook",
        "money_and_scam_hook",
        "finance_soft_lead_bait",
        "short_text_with_contact",
    }
)


def _get_detector() -> GroqSpamDetector:
    global _detector
    if _detector is None:
        _detector = GroqSpamDetector()
    return _detector


def process_spam_check_task(
    bot: TelegramClient,
    body: dict,
    captcha_repo: CaptchaRepository | None = None,
    memory_repo: GroupMemoryRepository | None = None,
    moderation_repo: SpamRepository | None = None,
) -> str | None:
    """Process a SPAM_CHECK SQS task: classify with Groq and enforce if confident."""
    try:
        chat_id: int = body["chat_id"]
        user_id: int = body["user_id"]
        message_id: int = body["message_id"]
        text: str = str(body["text"])
    except (KeyError, TypeError) as e:
        logger.error("Malformed SPAM_CHECK body, skipping", extra={"error": e, "body": body})
        return

    triggered_rules = _normalise_triggered_rules(body.get("triggered_rules"))
    rule_score = _coerce_float(body.get("rule_score"))
    message_context = body.get("message_context") if isinstance(body.get("message_context"), dict) else {}

    if user_id == TELEGRAM_CHANNEL_POST_ACTOR_USER_ID:
        logger.info(
            "Skipping SPAM_CHECK for channel discussion mirror actor",
            extra={"chat_id": chat_id, "message_id": message_id},
        )
        return

    if _has_pending_captcha(captcha_repo, chat_id, user_id):
        logger.info(
            "Skipping SPAM_CHECK for pending captcha user",
            extra={"chat_id": chat_id, "user_id": user_id, "message_id": message_id},
        )
        return

    administrator_exempt = is_chat_admin_or_creator(bot, chat_id, user_id, raise_on_error=True)
    if administrator_exempt:
        logger.info(
            "Skipping SPAM_CHECK for administrator/creator",
            extra={"chat_id": chat_id, "user_id": user_id},
        )

    moderation_repo = moderation_repo or SpamRepository()
    case = moderation_repo.ensure_case(body)
    if case["state"] in {"clean", "blocked", "ignored"} or case.get("alert_sent") or case.get("selected_action"):
        return case["state"]
    owner, case = moderation_repo.claim(case["case_id"])
    try:
        if case["state"] in {"clean", "blocked", "ignored"} or case.get("alert_sent") or case.get("selected_action"):
            return case["state"]
        if administrator_exempt:
            moderation_repo.update(case["case_id"], owner, {"reason": "administrator_exempt"})
            moderation_repo.finish_clean(case, owner)
            return "clean"
        recent_context = _load_recent_context(memory_repo, chat_id, message_id)
        classifier_input = format_spam_ai_context(
            text=text,
            message_context=message_context,
            recent_context=recent_context,
            rule_score=rule_score,
            triggered_rules=triggered_rules,
        )
        guest = message_context.get("guest_bot") is True
        # Recompute on CURRENT_MESSAGE only: quoted/replied advertising is not
        # evidence for deterministic deletion of a guest's current response.
        _, current_rules = RuleBasedSpamFilter().check(
            str(message_context.get("current_message") or ""), user_id, chat_id
        )
        if case.get("decision_label"):
            result = SpamCheckResult(case["decision_label"], int(case["confidence_ppm"]) / 1_000_000, case["reason"])
        elif guest and "repeated_obfuscated_url" in current_rules:
            result = SpamCheckResult("SPAM", 1.0, "referral_promo")
        else:
            result = _get_detector().classify(classifier_input)
        strong_signal = _has_strong_auto_enforce_signal(triggered_rules)
        auto_enforce = result.label == "SPAM" and result.confidence >= SPAM_AI_CONFIDENCE_THRESHOLD and strong_signal

        logger.info(
            "Groq spam check result",
            extra={
                "chat_id": chat_id,
                "user_id": user_id,
                "message_id": message_id,
                "label": result.label,
                "confidence": result.confidence,
                "reason": result.reason,
                "error": result.error,
                "rules": triggered_rules,
                "rule_score": rule_score,
                "strong_auto_enforce_signal": strong_signal,
                "auto_enforce": auto_enforce,
                "recent_context_count": len(recent_context),
                "decision_source": (
                    "guest_structure" if guest and "repeated_obfuscated_url" in current_rules else "groq"
                ),
                "guest_bot": guest,
                "guest_caller_user_id": message_context.get("guest_caller_user_id") if guest else None,
            },
        )

        if result.error:
            raise ProviderResponseError("spam classifier failed")
        if result.label not in {"SPAM", "NOT_SPAM"}:
            raise ProviderResponseError("spam classifier returned an unknown label")
        moderation_repo.update(
            case["case_id"],
            owner,
            {
                "decision_label": result.label,
                "confidence_ppm": int(result.confidence * 1_000_000),
                "reason": result.reason,
            },
        )

        if result.label == "NOT_SPAM":
            moderation_repo.finish_clean(case, owner)
            return "clean"

        if guest and result.label == "SPAM":
            if auto_enforce:
                try:
                    bot.delete_message(chat_id, message_id, ignore_not_found=True)
                except Exception as exc:
                    failure = permanent_telegram_failure(exc)
                    if failure is None:
                        raise
                    moderation_repo.update(case["case_id"], owner, {"enforcement_error": failure})
                logger.info(
                    "Guest bot spam deletion processed",
                    extra={"chat_id": chat_id, "message_id": message_id, "bot_user_id": user_id},
                )
            caller_id = message_context.get("guest_caller_user_id")
            if type(caller_id) is int and caller_id > 0:
                _request_review(
                    moderation_repo, case, owner, bot, caller_id, result.reason, result.confidence, guest_bot_id=user_id
                )
                return "review"
            else:
                logger.warning(
                    "Guest spam has no personal caller; no user ban proposed",
                    extra={"chat_id": chat_id, "message_id": message_id, "bot_user_id": user_id},
                )
                moderation_repo.update(case["case_id"], owner, {"state": "blocked"})
                return "blocked"
        elif auto_enforce:
            enforcement = SpamEnforcer(bot, moderation_repo).enforce(
                chat_id=chat_id,
                user_id=user_id,
                message_id=message_id,
                reason=result.reason,
            )
            if enforcement.state == "failed":
                moderation_repo.update(case["case_id"], owner, {"enforcement_error": enforcement.reason})
                _request_review(moderation_repo, case, owner, bot, user_id, result.reason, result.confidence)
                return "review"
            moderation_repo.update(case["case_id"], owner, {"state": "blocked"})
            return "blocked"
        elif result.label == "SPAM":
            # Low-confidence or weak-signal SPAM: alert admins without taking automated action.
            _request_review(moderation_repo, case, owner, bot, user_id, result.reason, result.confidence)
            return "review"

    except Exception as e:
        logger.error(
            "Unexpected error in process_spam_check_task",
            extra={"chat_id": chat_id, "user_id": user_id, "error": e},
            exc_info=True,
        )
        raise
    finally:
        moderation_repo.release(case["case_id"], owner)


def _has_pending_captcha(captcha_repo: CaptchaRepository | None, chat_id: int, user_id: int) -> bool:
    if not captcha_repo:
        return False
    # Unknown verification state must not become permission to classify or learn.
    return captcha_repo.get_pending(chat_id, user_id) is not None


def _request_review(repo, case, owner, bot, target_user_id, reason, confidence, *, guest_bot_id=None):
    repo.update(case["case_id"], owner, {"state": "review", "review_target_user_id": target_user_id})
    _send_spam_review_alert(
        bot,
        int(case["chat_id"]),
        target_user_id,
        int(case["message_id"]),
        reason,
        confidence,
        guest_bot_id=guest_bot_id,
        case_id=case["case_id"],
    )
    repo.update(case["case_id"], owner, {"alert_sent": True})


def report_rule_enforcement_failure(bot, body: dict, *, reason: str) -> None:
    """Keep a permanent rule-action failure reviewable without treating it as clean."""
    repo = SpamRepository()
    case = repo.ensure_case(body)
    if case.get("alert_sent") or case.get("selected_action") or case["state"] in {"clean", "blocked", "ignored"}:
        return
    owner, case = repo.claim(case["case_id"])
    try:
        if not case.get("alert_sent") and not case.get("selected_action"):
            _request_review(repo, case, owner, bot, int(body["user_id"]), reason, 1.0)
    finally:
        repo.release(case["case_id"], owner)


def _send_spam_review_alert(
    bot: TelegramClient,
    chat_id: int,
    user_id: int,
    message_id: int,
    result_reason: str,
    confidence: float,
    *,
    guest_bot_id: int | None = None,
    case_id: str | None = None,
) -> None:
    try:
        target = resolve_spam_target_mention(bot, chat_id, user_id)
        lang = get_chat_lang(chat_id)
        reason = translate_spam_reason(result_reason, lang)
        confidence_pct = int(confidence * 100)
        notice = get_translated_text(
            "spam_guest_review_notice" if guest_bot_id else "spam_uncertain_notice",
            lang,
            TARGET=target,
            REASON=reason,
            CONFIDENCE=confidence_pct,
            BOT=resolve_spam_target_mention(bot, chat_id, guest_bot_id) if guest_bot_id else "",
        )
        admin_mentions = _format_admin_mentions(chat_id)
        if admin_mentions:
            notice = f"{admin_mentions}\n{notice}"
        bot.send_message(
            chat_id,
            notice,
            reply_markup=_spam_review_keyboard(user_id, message_id, lang, case_id=case_id),
        )
    except Exception as e:
        logger.warning("Failed to send uncertain spam alert", extra={"error": e})
        raise


def _load_recent_context(
    memory_repo: GroupMemoryRepository | None,
    chat_id: int,
    current_message_id: int,
) -> list[dict[str, Any]]:
    if memory_repo is None:
        return []
    try:
        items = memory_repo.get_recent_messages(chat_id, limit=_RECENT_CONTEXT_QUERY_LIMIT)
    except Exception as e:
        logger.warning(
            "Failed to load recent context for SPAM_CHECK",
            extra={"chat_id": chat_id, "message_id": current_message_id, "error": e},
        )
        return []

    recent: list[dict[str, Any]] = []
    for item in items:
        if str(item.get("message_id")) == str(current_message_id):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        recent.append(
            {
                "message_id": item.get("message_id"),
                "user_id": item.get("user_id"),
                "username": item.get("username"),
                "display_name": item.get("display_name"),
                "text": text,
            }
        )
    return recent[-_RECENT_CONTEXT_RENDER_LIMIT:]


def _normalise_triggered_rules(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rules: list[str] = []
    seen: set[str] = set()
    for item in value:
        rule = str(item or "").strip()
        if rule and rule not in seen:
            seen.add(rule)
            rules.append(rule)
    return rules


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_strong_auto_enforce_signal(triggered_rules: list[str]) -> bool:
    rules = set(triggered_rules)
    if rules & _STRONG_AUTO_ENFORCE_RULES:
        return True
    return "job_offer" in rules and bool(
        rules & {"money_pattern", "external_mention", "external_url", "dm_redirect", "scam_hook"}
    )


def _format_admin_mentions(chat_id: int) -> str:
    mentions: list[str] = []
    for raw_username in get_spam_review_admin_mentions(chat_id):
        username = str(raw_username or "").strip().lstrip("@")
        if not username or not _USERNAME_RE.fullmatch(username):
            continue
        mentions.append(f"@{escape(username)}")
    return " ".join(mentions)


def _spam_review_keyboard(user_id: int, message_id: int, lang: str, *, case_id: str | None = None) -> dict:
    target = case_id.removeprefix("decision#") if case_id else f"{user_id}:{message_id}"
    return {
        "inline_keyboard": [
            [
                {
                    "text": get_translated_text("spam_review_ban_button", lang),
                    "callback_data": f"{SPAM_REVIEW_BAN_PREFIX}{target}",
                },
                {
                    "text": get_translated_text("spam_review_ignore_button", lang),
                    "callback_data": f"{SPAM_REVIEW_IGNORE_PREFIX}{target}",
                },
            ]
        ]
    }
