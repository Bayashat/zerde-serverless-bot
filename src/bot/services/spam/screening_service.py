"""Layer-1 rule-based spam screening and SQS hand-off for ambiguous scores."""

from __future__ import annotations

from core.logger import LoggerAdapter, get_logger
from services.repositories.sqs import SQSClient
from services.repositories.stats import StatsRepository
from services.spam.channel_post import should_skip_spam_for_channel_discussion_mirror
from services.spam.chat_member import is_chat_admin_or_creator
from services.spam.enforcer import SpamEnforcer
from services.spam.message_text import collect_spam_screen_text
from services.spam.rule_filter import RuleBasedSpamFilter
from services.telegram import TelegramClient

logger = LoggerAdapter(get_logger(__name__), {})


class SpamScreeningService:
    """Scores incoming messages, enforces high-confidence rule hits, else may enqueue AI check."""

    def __init__(self, bot: TelegramClient, sqs_repo: SQSClient) -> None:
        self._bot = bot
        self._sqs = sqs_repo

    @staticmethod
    def should_screen(body: dict) -> bool:
        """True for non-command, non-bot regular messages that may need spam handling."""
        if "message" not in body:
            return False
        msg = body["message"]
        if should_skip_spam_for_channel_discussion_mirror(msg):
            return False
        if "new_chat_members" in msg:
            return False
        if msg.get("from", {}).get("is_bot", False):
            return False
        primary = msg.get("text") or msg.get("caption") or ""
        if primary.strip().startswith("/"):
            return False
        combined = collect_spam_screen_text(msg)
        if not combined.strip():
            return False
        return True

    def run(self, body: dict) -> None:
        """Score message, enforce or queue Groq. Never raises."""
        try:
            msg = body["message"]
            combined = collect_spam_screen_text(msg)
            if not combined.strip():
                return
            user_id: int = msg["from"]["id"]
            message_id: int = msg["message_id"]
            chat_id: int = msg["chat"]["id"]

            if is_chat_admin_or_creator(self._bot, chat_id, user_id):
                logger.info(
                    "Spam screening skipped (sender is administrator or creator)",
                    extra={"chat_id": chat_id, "user_id": user_id, "message_id": message_id},
                )
                return

            score, triggered_rules = RuleBasedSpamFilter().check(combined, user_id, chat_id)
            if score > 0.8:
                logger.info(
                    "Rule-based spam detected, enforcing",
                    extra={"chat_id": chat_id, "user_id": user_id, "score": score, "rules": triggered_rules},
                )
                SpamEnforcer(self._bot, StatsRepository()).enforce(
                    chat_id=chat_id,
                    user_id=user_id,
                    message_id=message_id,
                    reason=f"rules:{','.join(triggered_rules)}",
                )
                return
            if score > 0.15:
                logger.info(
                    "Ambiguous spam score, queuing for AI check",
                    extra={"chat_id": chat_id, "user_id": user_id, "score": score, "rules": triggered_rules},
                )
                self._sqs.send_spam_check_task(
                    chat_id=chat_id,
                    user_id=user_id,
                    message_id=message_id,
                    text=combined,
                    triggered_rules=triggered_rules,
                )
                return
            if triggered_rules:
                logger.info(
                    "Spam screening below AI threshold (no automatic action)",
                    extra={"chat_id": chat_id, "user_id": user_id, "score": score, "rules": triggered_rules},
                )
        except Exception as e:
            logger.error("Spam screening error, continuing normal flow", extra={"error": e})
