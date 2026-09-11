"""Spam enforcer: deletes the message, bans the user, and updates moderation stats."""

import time
from dataclasses import dataclass

from core.config import (
    KICK_BAN_CONFIGURED_DURATION_SECONDS,
    KICK_BAN_DURATION_SECONDS,
    TELEGRAM_CHANNEL_POST_ACTOR_USER_ID,
)
from core.logger import LoggerAdapter, get_logger
from core.translations import get_translated_text
from core.utils import format_mention
from services.repositories.spam import SpamRepository
from services.telegram import TelegramAPIError, TelegramClient

logger = LoggerAdapter(get_logger(__name__), {})


@dataclass(frozen=True)
class EnforcementResult:
    state: str
    reason: str = ""

    @property
    def banned(self) -> bool:
        return self.state == "banned"


def permanent_telegram_failure(exc: Exception) -> str | None:
    if isinstance(exc, TelegramAPIError) and exc.status in {400, 401, 403, 404}:
        return f"telegram_http_{exc.status}"
    return None


class SpamEnforcer:
    """Resume a fixed moderation action and count only confirmed Telegram bans."""

    def __init__(self, bot: TelegramClient, repo: SpamRepository | None = None) -> None:
        self.bot = bot
        self.repo = repo or SpamRepository()

    def enforce(
        self,
        chat_id: int,
        user_id: int,
        message_id: int,
        reason: str,
        *,
        permanent: bool = False,
        retry_failed: bool = False,
    ) -> EnforcementResult:
        if user_id == TELEGRAM_CHANNEL_POST_ACTOR_USER_ID:
            return EnforcementResult("skipped", "channel_actor")
        action = self.repo.ensure_action(chat_id, user_id, message_id, permanent=permanent, until_date=0)
        if action["state"] in {"banned", "skipped"} or (action["state"] == "failed" and not retry_failed):
            return EnforcementResult(action["state"], action.get("reason", ""))
        action_id = action["case_id"]
        owner, action = self.repo.claim(action_id)
        try:
            # Recheck after the lease: a concurrent worker may have finished.
            if action["state"] in {"banned", "skipped"}:
                return EnforcementResult(action["state"], action.get("reason", ""))
            member = self.bot.get_chat_member(chat_id, user_id)
            if not isinstance(member, dict) or member.get("status") not in {
                "member",
                "administrator",
                "creator",
                "restricted",
                "left",
                "kicked",
            }:
                raise RuntimeError("Cannot verify moderation target membership")
            status = member["status"]
            if status in {"administrator", "creator"}:
                result = EnforcementResult("skipped", "protected_member")
            elif status == "kicked":
                # Do not shorten/extend another moderation action or claim its counter.
                result = EnforcementResult("skipped", "already_banned")
            elif not permanent and action.get("until_date") and int(action["until_date"]) <= int(time.time()) + 40:
                result = EnforcementResult("failed", "temporary_ban_window_expired")
            else:
                if not action.get("delete_done"):
                    self.bot.delete_message(chat_id, message_id, ignore_not_found=True)
                    self.repo.update(action_id, owner, {"delete_done": True})
                if permanent:
                    self.bot.ban_chat_member(chat_id, user_id)
                else:
                    if not action.get("until_date"):
                        duration = max(60, KICK_BAN_DURATION_SECONDS)
                        action["until_date"] = int(time.time()) + duration
                        self.repo.update(
                            action_id,
                            owner,
                            {"until_date": action["until_date"], "effective_duration_seconds": duration},
                        )
                        if KICK_BAN_CONFIGURED_DURATION_SECONDS < duration:
                            logger.warning(
                                "Temporary ban duration normalized to the safe minimum",
                                extra={
                                    "configured_seconds": KICK_BAN_CONFIGURED_DURATION_SECONDS,
                                    "effective_seconds": duration,
                                },
                            )
                    # Telegram treats <30 seconds as permanent. Never retry near expiry.
                    if int(action["until_date"]) <= int(time.time()) + 40:
                        result = EnforcementResult("failed", "temporary_ban_window_expired")
                        self.repo.update(action_id, owner, {"state": result.state, "reason": result.reason})
                        return result
                    self.bot.kick_chat_member(chat_id, user_id, until_date=int(action["until_date"]))
                self.repo.confirm_ban(action_id, owner, chat_id)
                return EnforcementResult("banned")
            self.repo.update(action_id, owner, {"state": result.state, "reason": result.reason})
            return result
        except Exception as exc:
            failure = permanent_telegram_failure(exc)
            if failure is None:
                raise
            self.repo.update(action_id, owner, {"state": "failed", "reason": failure})
            logger.warning("Spam enforcement requires administrator action", extra={"error_code": failure})
            return EnforcementResult("failed", failure)
        finally:
            self.repo.release(action_id, owner)

    def _translate_reason(self, reason: str, lang: str) -> str:
        return translate_spam_reason(reason, lang)


def resolve_spam_target_mention(bot: TelegramClient, chat_id: int, user_id: int) -> str:
    """Resolve a clickable Telegram mention for spam review notices."""
    try:
        member = bot.get_chat_member(chat_id, user_id)
        user = member.get("user", {}) if isinstance(member, dict) else {}
        return format_mention(
            user_id=user_id,
            username=user.get("username"),
            first_name=user.get("first_name") or "User",
            last_name=user.get("last_name"),
        )
    except Exception as e:
        logger.debug(
            "Failed to resolve spam target mention",
            extra={"chat_id": chat_id, "user_id": user_id, "error": e},
        )
    return format_mention(user_id=user_id, username=None, first_name="User")


def translate_spam_reason(reason: str, lang: str) -> str:
    """Translate detector/rule reason codes into user-facing moderation reasons."""
    if reason.startswith("rules:"):
        reason = _primary_rule_reason(reason)

    reason_key = f"spam_reason_{reason}"
    translated = get_translated_text(reason_key, lang)

    if translated == reason_key:
        return get_translated_text("spam_reason_unknown", lang)

    return translated


def _primary_rule_reason(reason: str) -> str:
    rules = {rule.strip() for rule in reason.removeprefix("rules:").split(",") if rule.strip()}
    priority = [
        ("vpn_pattern", "vpn_ad"),
        ("money_and_dm_redirect", "dm_redirect_scam"),
        ("dm_redirect", "dm_redirect_scam"),
        ("money_and_scam_hook", "dm_redirect_scam"),
        ("scam_hook", "dm_redirect_scam"),
        ("job_offer", "job_offer"),
        ("money_pattern", "job_offer"),
        ("external_url", "suspicious_link"),
        ("cis_spam_obfuscation", "suspicious_link"),
        ("external_mention", "referral_promo"),
        ("promo_words", "referral_promo"),
        ("short_text_with_contact", "referral_promo"),
    ]
    for rule, reason_code in priority:
        if rule in rules:
            return reason_code
    return "rules"
