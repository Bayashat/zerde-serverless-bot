"""Fair linked-channel contest orchestration.

This module owns deterministic Telegram-shape recognition and the lifecycle
between :class:`ContestRepository` and Telegram.  AI and group-memory services
do not participate in eligibility or winner selection.
"""

from __future__ import annotations

import re
import secrets
import time
from html import escape
from typing import Any

from core.logger import LoggerAdapter, get_logger
from core.utils import format_mention
from services.repositories.contest import ContestRepository, RegistrationResult
from services.repositories.sqs import SQSClient
from services.telegram import TelegramAPIError, TelegramClient
from services.telegram_actor import is_linked_channel_discussion_post

logger = LoggerAdapter(get_logger(__name__), {})

CONTEST_MARKER = "#конкурс"
ENTRY_PHRASE = "қатысамын"
MAX_DRAWS = 3
TTL_SWEEP_PAGE_SIZE = 50
TTL_OUTBOX_PAGE_SIZE = 100
CREATION_ATTEMPT_LEASE_SECONDS = 30
EMBEDDED_ROOT_OVERLAP_SECONDS = 5 * 60
TELEGRAM_UPDATE_RETENTION_SECONDS = 24 * 60 * 60
TELEGRAM_SAFE_HTML_CHARS = 4000

_CONTEST_MARKER_RE = re.compile(r"(?<![\w#])#конкурс(?!\w)", re.IGNORECASE)
_MISSING_REPLY_DESCRIPTIONS = (
    "message to be replied not found",
    "reply message not found",
)

RULES_MESSAGE_KK = (
    "🎉 <b>Конкурс басталды!</b>\n\n"
    "Қатысу үшін осы бастапқы жазбаға тікелей жауап беріп, мәтінде "
    "«қатысамын» сөзін жазыңыз.\n"
    "Әр адам бір рет қана қатысады. Тек жеке аккаунттар есепке алынады.\n"
    "Басқа пікірге немесе осы хабарламаға берілген жауап есептелмейді.\n"
    "Пікіріңізге 🎉 қойылса, қатысуыңыз тіркелді.\n"
    "Жеңімпаз қауіпсіз кездейсоқ таңдау арқылы анықталады."
)
BOT_ADMIN_REQUIRED_KK = "⚠️ Конкурсты бастау мүмкін болмады: Zerde осы талқылау тобында әкімші болуы керек."
OWNER_ONLY_KK = "⛔ Бұл әрекетті тек топ иесі орындай алады."
ADMIN_ONLY_KK = "⛔ Конкурс күйін тек топ иесі немесе әкімші көре алады."
PERSONAL_ACCOUNT_REQUIRED_KK = "⛔ Команданы жеке аккаунттан жіберіңіз."
REPLY_ANCHOR_REQUIRED_KK = "ℹ️ Команданы конкурс жазбасына немесе Zerde жариялаған ережелерге жауап ретінде жіберіңіз."
UNKNOWN_SUBCOMMAND_KK = "ℹ️ Қолдану: /contest draw | redraw | status | cancel"
NO_PARTICIPANTS_KK = "ℹ️ Әзірге жарамды қатысушы жоқ. Конкурс ашық күйінде қалды."
USE_DRAW_FIRST_KK = "ℹ️ Алдымен /contest draw командасын қолданыңыз."
CONTEST_CANCELLED_KK = "🚫 Конкурс тоқтатылды. Жаңа қатысушылар қабылданбайды."
CONTEST_ALREADY_CANCELLED_KK = "ℹ️ Бұл конкурс бұрын тоқтатылған."
CONTEST_CLOSED_KK = "ℹ️ Бұл конкурс жабық."
CONTEST_EXPIRED_KK = "⌛ Конкурстың 30 күндік сақтау мерзімі аяқталды."
REDRAW_LIMIT_KK = "ℹ️ Қайта ұтыс шегіне жетті: барлығы 3 ұтысқа дейін рұқсат."
NO_REMAINING_CANDIDATES_KK = "ℹ️ Қайта ұтысқа бұрын жеңбеген қатысушы қалмады."
ANNOUNCEMENT_RETRIED_KK = "ℹ️ Сақталған нәтиже қайта жарияланды. Қайта ұтыс үшін команданы тағы жіберіңіз."
ORPHANED_KK = "⚠️ Конкурс дәлел хабарламалары жойылғандықтан жабылды; тек күйін көруге болады."
CONTEST_NOT_READY_KK = "ℹ️ Конкурс әлі дайын емес. Кейінірек қайталап көріңіз."
CONTEST_ERROR_KK = "⚠️ Конкурс әрекетін орындау мүмкін болмады. Кейінірек қайталап көріңіз."


class AnnouncementOrphanedError(RuntimeError):
    """Winner and root reply anchors are both unavailable."""


class ContestRetryRequiredError(RuntimeError):
    """A concurrent fail-closed transition requires Telegram redelivery."""


def has_contest_marker(message: dict[str, Any]) -> bool:
    """Return whether the initial text/caption contains standalone ``#конкурс``."""
    content = message.get("text") or message.get("caption") or ""
    return isinstance(content, str) and bool(_CONTEST_MARKER_RE.search(content))


def is_entry_message(message: dict[str, Any]) -> bool:
    """Return whether a raw message has the non-repository entry shape."""
    text = message.get("text")
    if not isinstance(text, str) or ENTRY_PHRASE.casefold() not in text.casefold():
        return False

    sender = message.get("from")
    if not isinstance(sender, dict) or sender.get("id") is None:
        return False
    if sender.get("is_bot") is True or message.get("sender_chat"):
        return False

    root_message_id = message.get("message_thread_id")
    reply = message.get("reply_to_message")
    chat = message.get("chat")
    if (
        not isinstance(message.get("message_id"), int)
        or not isinstance(chat, dict)
        or chat.get("id") is None
        or not isinstance(root_message_id, int)
        or not isinstance(reply, dict)
    ):
        return False
    return reply.get("message_id") == root_message_id


def is_contest_root_shape(message: dict[str, Any]) -> bool:
    """Return whether a message has the strict official discussion-root shape."""
    chat = message.get("chat")
    sender_chat = message.get("sender_chat")
    return bool(
        isinstance(chat, dict)
        and chat.get("type") == "supergroup"
        and isinstance(message.get("message_id"), int)
        and is_linked_channel_discussion_post(message)
        and isinstance(sender_chat, dict)
        and sender_chat.get("type") == "channel"
        and sender_chat.get("id") is not None
    )


def _is_fresh_embedded_root(entry: dict[str, Any], root: dict[str, Any]) -> bool:
    """Limit missing-META retries to an unedited, currently overlapping root update."""
    if root.get("edit_date") is not None:
        return False
    root_date = root.get("date")
    entry_date = entry.get("date")
    if not isinstance(root_date, int) or not isinstance(entry_date, int):
        return False
    now = int(time.time())
    return (
        0 <= entry_date - root_date <= EMBEDDED_ROOT_OVERLAP_SECONDS
        and -EMBEDDED_ROOT_OVERLAP_SECONDS <= now - entry_date <= TELEGRAM_UPDATE_RETENTION_SECONDS
    )


def _is_missing_reply_error(exc: TelegramAPIError) -> bool:
    if exc.status != 400:
        return False
    description = str(exc.body or "").casefold()
    return any(fragment in description for fragment in _MISSING_REPLY_DESCRIPTIONS)


def _source_channel_post_id(message: dict[str, Any]) -> int | None:
    direct = message.get("forward_from_message_id")
    if isinstance(direct, int):
        return direct
    origin = message.get("forward_origin")
    if isinstance(origin, dict) and isinstance(origin.get("message_id"), int):
        return origin["message_id"]
    return None


def _winner_at(contest: dict[str, Any], draw_number: int) -> dict[str, Any] | None:
    winners = contest.get("winners")
    if not isinstance(winners, list) or draw_number < 1 or len(winners) < draw_number:
        return None
    winner = winners[draw_number - 1]
    return winner if isinstance(winner, dict) else None


def _winner_mention(winner: dict[str, Any]) -> str:
    return format_mention(
        int(winner["user_id"]),
        str(winner.get("username") or "") or None,
        str(winner.get("first_name") or "Қатысушы")[:120],
        str(winner.get("last_name") or "")[:120] or None,
    )


def _escaped_to_budget(raw_text: str, budget: int) -> tuple[str, bool]:
    """Escape whole characters without cutting an HTML entity at ``budget``."""
    rendered: list[str] = []
    used = 0
    for index, char in enumerate(raw_text):
        token = escape(char)
        if used + len(token) > budget:
            return "".join(rendered), True
        rendered.append(token)
        used += len(token)
        if index == len(raw_text) - 1:
            return "".join(rendered), False
    return "", False


def _evidence_excerpt(raw_text: str) -> str:
    """Keep the qualifying phrase visible when a deleted entry needs fallback evidence."""
    match = re.search(re.escape(ENTRY_PHRASE), raw_text, re.IGNORECASE)
    if not match:
        return raw_text
    context_chars = 120
    start = max(0, match.start() - context_chars)
    end = min(len(raw_text), match.end() + context_chars)
    if start == 0 and end == len(raw_text):
        return raw_text
    return ("…" if start else "") + raw_text[start:end] + ("…" if end < len(raw_text) else "")


def _winner_message(contest: dict[str, Any], winner: dict[str, Any], *, include_snapshot: bool) -> str:
    draw_number = int(winner["draw_number"])
    participant_count = int(contest.get("frozen_participant_count") or 0)
    lines = [
        "🎉 <b>Жеңімпаз анықталды!</b>",
        f"🏆 {_winner_mention(winner)}",
        f"👥 Қатысушылар саны: <b>{participant_count}</b>",
        f"🎲 Ұтыс: <b>{draw_number}/{MAX_DRAWS}</b>",
    ]
    if not include_snapshot:
        return "\n".join(lines)

    lines.append(f"🧾 Алғашқы жарамды пікір: <code>#{int(winner['entry_message_id'])}</code>")
    prefix = "\n".join([*lines, "<blockquote>"])
    suffix = "</blockquote>"
    budget = max(0, TELEGRAM_SAFE_HTML_CHARS - len(prefix) - len(suffix))
    raw_text = _evidence_excerpt(str(winner.get("text") or ""))
    snapshot, was_truncated = _escaped_to_budget(raw_text, budget)
    if was_truncated and budget > 0:
        snapshot, _ = _escaped_to_budget(raw_text, max(0, budget - 1))
        snapshot += "…"
    return f"{prefix}{snapshot}{suffix}"


class ContestService:
    """Coordinate contest recognition, draws, evidence, and retention."""

    def __init__(
        self,
        repo: ContestRepository,
        bot: TelegramClient,
        sqs_repo: SQSClient | None = None,
    ) -> None:
        self.repo = repo
        self.bot = bot
        self.sqs_repo = sqs_repo

    def observe_update(self, update: dict[str, Any]) -> None:
        """Observe one initial Telegram message without consuming normal bot flows."""
        message = update.get("message")
        if not isinstance(message, dict):
            return
        if has_contest_marker(message):
            self._observe_root(message)
        if is_entry_message(message):
            self._observe_entry(message)

    def _bot_is_administrator(self, chat_id: int | str) -> bool:
        bot_id = int(self.bot.get_me()["id"])
        member = self.bot.get_chat_member(chat_id, bot_id)
        return str(member.get("status") or "").casefold() == "administrator"

    def _send_admin_error(self, chat_id: int | str, root_message_id: int) -> None:
        try:
            self.bot.send_message(chat_id, BOT_ADMIN_REQUIRED_KK, reply_to_message_id=root_message_id)
        except Exception:
            logger.exception(
                "Failed to send contest bot-admin prerequisite message",
                extra={"chat_id": chat_id, "root_message_id": root_message_id},
            )

    def _observe_root(self, message: dict[str, Any]) -> None:
        chat = message.get("chat")
        sender_chat = message.get("sender_chat")
        root_message_id = message.get("message_id")
        if not is_contest_root_shape(message):
            return

        chat_id = chat.get("id")
        if chat_id is None:
            return
        linked_chat = self.bot.get_chat(chat_id)
        if str(linked_chat.get("linked_chat_id")) != str(sender_chat["id"]):
            return

        existing = self.repo.get_contest(chat_id, root_message_id, consistent=True)
        if existing:
            if existing.get("status") == "CREATING":
                self._activate_creating(existing)
            return

        if not self._bot_is_administrator(chat_id):
            self._send_admin_error(chat_id, root_message_id)
            return

        created = self.repo.create_contest(
            chat_id=chat_id,
            root_message_id=root_message_id,
            source_channel_id=sender_chat["id"],
            source_channel_title=str(sender_chat.get("title") or "") or None,
            source_channel_username=str(sender_chat.get("username") or "") or None,
            source_channel_post_id=_source_channel_post_id(message),
            created_at=message.get("date") if isinstance(message.get("date"), int) else None,
        )
        contest = self.repo.get_contest(chat_id, root_message_id, consistent=True)
        if created or (contest and contest.get("status") == "CREATING"):
            self._activate_creating(contest or {"chat_id": str(chat_id), "root_message_id": root_message_id})

    def _activate_creating(self, contest: dict[str, Any]) -> bool:
        chat_id = contest["chat_id"]
        root_message_id = int(contest["root_message_id"])
        now = int(time.time())
        attempt_id = secrets.token_hex(16)
        claimed = self.repo.begin_creation_attempt(
            chat_id,
            root_message_id,
            attempt_id=attempt_id,
            stale_before=now - CREATION_ATTEMPT_LEASE_SECONDS,
            now=now,
        )
        if not claimed:
            raise ContestRetryRequiredError("Contest rules publication is already in progress")
        try:
            bot_is_administrator = self._bot_is_administrator(chat_id)
        except Exception:
            self.repo.release_creation_attempt(chat_id, root_message_id, attempt_id=attempt_id)
            raise
        if not bot_is_administrator:
            self.repo.fail_creation(chat_id, root_message_id, attempt_id=attempt_id)
            self._send_admin_error(chat_id, root_message_id)
            return False
        try:
            rules = self.bot.send_message(
                chat_id,
                RULES_MESSAGE_KK,
                reply_to_message_id=root_message_id,
                link_preview_disable=True,
            )
        except TelegramAPIError as exc:
            if exc.status in {400, 403}:
                self.repo.fail_creation(chat_id, root_message_id, attempt_id=attempt_id)
                logger.exception(
                    "Definite Telegram failure while creating contest",
                    extra={"chat_id": chat_id, "root_message_id": root_message_id},
                )
                return False
            self.repo.release_creation_attempt(chat_id, root_message_id, attempt_id=attempt_id)
            raise
        except Exception:
            # Telegram may have accepted the request before the transport failed.
            # Release the lease so webhook retry can safely publish again. A
            # duplicate rules message is preferable to a hidden open contest.
            self.repo.release_creation_attempt(chat_id, root_message_id, attempt_id=attempt_id)
            logger.exception(
                "Ambiguous Telegram failure while creating contest",
                extra={"chat_id": chat_id, "root_message_id": root_message_id},
            )
            raise

        rules_message_id = rules.get("message_id") if isinstance(rules, dict) else None
        if not isinstance(rules_message_id, int):
            self.repo.release_creation_attempt(chat_id, root_message_id, attempt_id=attempt_id)
            logger.error(
                "Telegram rules response lacked message_id; contest remains CREATING",
                extra={"chat_id": chat_id, "root_message_id": root_message_id},
            )
            raise RuntimeError("Telegram rules response lacked message_id")
        try:
            activated = self.repo.activate_contest(
                chat_id,
                root_message_id,
                rules_message_id,
                attempt_id=attempt_id,
            )
        except Exception:
            self.repo.release_creation_attempt(chat_id, root_message_id, attempt_id=attempt_id)
            raise
        if not activated:
            self.repo.release_creation_attempt(chat_id, root_message_id, attempt_id=attempt_id)
        return activated

    def _observe_entry(self, message: dict[str, Any]) -> None:
        chat_id = message.get("chat", {}).get("id")
        root_message_id = message["message_thread_id"]
        if chat_id is None:
            return
        contest = self.repo.get_contest(chat_id, root_message_id, consistent=True)
        if not contest:
            replied_root = message.get("reply_to_message")
            replied_chat = replied_root.get("chat") if isinstance(replied_root, dict) else None
            if (
                isinstance(replied_root, dict)
                and isinstance(replied_chat, dict)
                and str(replied_chat.get("id")) == str(chat_id)
                and replied_root.get("message_id") == root_message_id
                and has_contest_marker(replied_root)
                and is_contest_root_shape(replied_root)
                and _is_fresh_embedded_root(message, replied_root)
            ):
                # Never create from a nested snapshot: it may be edited or
                # pre-cutover history. Ask Telegram to redeliver briefly while
                # the original root invocation owns activation.
                raise ContestRetryRequiredError("Contest root activation is still in progress")
        if not contest:
            return
        if contest.get("status") == "CREATING":
            self._activate_creating(contest)
            contest = self.repo.get_contest(chat_id, root_message_id, consistent=True)
        if not contest or contest.get("status") != "OPEN":
            return

        sender = message["from"]
        result = self.repo.register_participant(
            chat_id=chat_id,
            root_message_id=root_message_id,
            user_id=int(sender["id"]),
            entry_message_id=int(message["message_id"]),
            username=str(sender.get("username") or "") or None,
            first_name=str(sender.get("first_name") or "") or None,
            last_name=str(sender.get("last_name") or "") or None,
            text=str(message["text"]),
            accepted_at=message.get("date") if isinstance(message.get("date"), int) else None,
        )
        if result in {RegistrationResult.REGISTERED, RegistrationResult.REPLAY}:
            try:
                self.bot.set_message_reaction(chat_id, int(message["message_id"]), "🎉")
            except TelegramAPIError as exc:
                logger.exception(
                    "Contest entry stored but acknowledgement reaction failed",
                    extra={"chat_id": chat_id, "root_message_id": root_message_id, "user_id": sender["id"]},
                )
                if exc.status != 400:
                    raise
            except Exception:
                logger.exception(
                    "Contest entry reaction delivery was ambiguous",
                    extra={"chat_id": chat_id, "root_message_id": root_message_id, "user_id": sender["id"]},
                )
                raise

    def _send_command_reply(self, chat_id: int | str, command_message_id: int, text: str) -> None:
        self.bot.send_message(chat_id, text, reply_to_message_id=command_message_id)

    def _enqueue_ttl_sweep(self, contest: dict[str, Any]) -> None:
        if contest.get("ttl_sweep_status") != "PENDING":
            return
        if not self.sqs_repo:
            logger.error(
                "Contest TTL sweep has no SQS client; durable outbox remains pending",
                extra={"chat_id": contest.get("chat_id"), "root_message_id": contest.get("root_message_id")},
            )
            return
        try:
            self.sqs_repo.send_contest_ttl_sweep_task(
                chat_id=int(contest["chat_id"]),
                root_message_id=int(contest["root_message_id"]),
            )
        except Exception:
            logger.exception(
                "Failed to enqueue contest TTL sweep; durable outbox will recover it",
                extra={"chat_id": contest.get("chat_id"), "root_message_id": contest.get("root_message_id")},
            )

    def _sample_candidate(
        self,
        chat_id: int | str,
        root_message_id: int,
        *,
        excluded_user_ids: set[str],
    ) -> tuple[dict[str, Any] | None, int]:
        """Uniformly sample across every strong page without materializing the set."""
        selected: dict[str, Any] | None = None
        participant_count = 0
        candidate_count = 0
        for participant in self.repo.iter_participants(chat_id, root_message_id):
            participant_count += 1
            if str(participant.get("user_id")) in excluded_user_ids:
                continue
            candidate_count += 1
            if secrets.randbelow(candidate_count) == 0:
                selected = participant
        return selected, participant_count

    def _announce_winner(self, contest: dict[str, Any], winner: dict[str, Any]) -> None:
        chat_id = contest["chat_id"]
        root_message_id = int(contest["root_message_id"])
        draw_number = int(winner["draw_number"])
        try:
            sent = self.bot.send_message(
                chat_id,
                _winner_message(contest, winner, include_snapshot=False),
                reply_to_message_id=int(winner["entry_message_id"]),
                link_preview_disable=True,
            )
        except TelegramAPIError as entry_error:
            if not _is_missing_reply_error(entry_error):
                raise
            try:
                sent = self.bot.send_message(
                    chat_id,
                    _winner_message(contest, winner, include_snapshot=True),
                    reply_to_message_id=root_message_id,
                    link_preview_disable=True,
                )
            except TelegramAPIError as root_error:
                if not _is_missing_reply_error(root_error):
                    raise
                self.repo.mark_orphaned(chat_id, root_message_id, draw_number=draw_number)
                raise AnnouncementOrphanedError("winner entry and contest root are unavailable") from root_error

        announcement_message_id = sent.get("message_id") if isinstance(sent, dict) else None
        if not isinstance(announcement_message_id, int):
            raise RuntimeError("Telegram winner announcement response lacked message_id")
        self.repo.mark_announcement_sent(
            chat_id,
            root_message_id,
            draw_number=draw_number,
            announcement_message_id=announcement_message_id,
        )

    def _replay_pending_announcement(
        self,
        contest: dict[str, Any],
        *,
        command_message_id: int,
        redraw_requested: bool,
    ) -> bool:
        if contest.get("status") != "DRAWN" or contest.get("announcement_state") != "PENDING":
            return False
        draw_number = int(contest.get("draw_count") or 0)
        winner = _winner_at(contest, draw_number)
        if not winner:
            raise RuntimeError("Persisted contest winner is missing")
        self._announce_winner(contest, winner)
        if redraw_requested:
            self._send_command_reply(
                contest["chat_id"],
                command_message_id,
                ANNOUNCEMENT_RETRIED_KK,
            )
        return True

    def draw(
        self,
        *,
        chat_id: int | str,
        root_message_id: int,
        command_message_id: int,
        redraw: bool = False,
    ) -> None:
        """Run or resume one secure draw, persisting the winner before delivery."""
        self._draw(
            chat_id=chat_id,
            root_message_id=root_message_id,
            command_message_id=command_message_id,
            redraw=redraw,
            transition_retries=1,
        )

    def _draw(
        self,
        *,
        chat_id: int | str,
        root_message_id: int,
        command_message_id: int,
        redraw: bool,
        transition_retries: int,
    ) -> None:
        contest = self.repo.get_contest(chat_id, root_message_id, consistent=True)
        if not contest:
            self._send_command_reply(chat_id, command_message_id, REPLY_ANCHOR_REQUIRED_KK)
            return
        if self.repo.is_logically_expired(contest):
            self._send_command_reply(chat_id, command_message_id, CONTEST_EXPIRED_KK)
            return
        if contest.get("status") == "ORPHANED":
            self._send_command_reply(chat_id, command_message_id, ORPHANED_KK)
            return
        if self._replay_pending_announcement(
            contest,
            command_message_id=command_message_id,
            redraw_requested=redraw,
        ):
            self._enqueue_ttl_sweep(contest)
            return

        status = contest.get("status")
        draw_number: int
        attempt_id: str
        if status == "DRAWING":
            draw_number = int(contest.get("pending_draw_number") or 0)
            attempt_id = str(contest.get("draw_attempt_id") or "")
            if draw_number < 1 or not attempt_id or (draw_number == 1) == redraw:
                self._send_command_reply(chat_id, command_message_id, CONTEST_NOT_READY_KK)
                return
        elif status == "OPEN":
            if redraw:
                self._send_command_reply(chat_id, command_message_id, USE_DRAW_FIRST_KK)
                return
            attempt_id = secrets.token_hex(16)
            if not self.repo.begin_first_draw(
                chat_id,
                root_message_id,
                attempt_id=attempt_id,
            ):
                if transition_retries > 0:
                    return self._draw(
                        chat_id=chat_id,
                        root_message_id=root_message_id,
                        command_message_id=command_message_id,
                        redraw=redraw,
                        transition_retries=transition_retries - 1,
                    )
                self._send_command_reply(chat_id, command_message_id, CONTEST_NOT_READY_KK)
                return
            draw_number = 1
        elif status == "DRAWN":
            if not redraw:
                first_winner = _winner_at(contest, 1)
                if not first_winner:
                    raise RuntimeError("Persisted first contest winner is missing")
                self._send_command_reply(
                    chat_id,
                    command_message_id,
                    "ℹ️ Алғашқы сақталған нәтиже:\n" + _winner_message(contest, first_winner, include_snapshot=False),
                )
                self._enqueue_ttl_sweep(contest)
                return
            draw_count = int(contest.get("draw_count") or 0)
            if draw_count >= MAX_DRAWS:
                self._send_command_reply(chat_id, command_message_id, REDRAW_LIMIT_KK)
                return
            attempt_id = secrets.token_hex(16)
            if not self.repo.begin_redraw(
                chat_id,
                root_message_id,
                expected_draw_count=draw_count,
                attempt_id=attempt_id,
            ):
                if transition_retries > 0:
                    return self._draw(
                        chat_id=chat_id,
                        root_message_id=root_message_id,
                        command_message_id=command_message_id,
                        redraw=redraw,
                        transition_retries=transition_retries - 1,
                    )
                self._send_command_reply(chat_id, command_message_id, CONTEST_NOT_READY_KK)
                return
            draw_number = draw_count + 1
        elif status == "CANCELLED":
            self._send_command_reply(chat_id, command_message_id, CONTEST_ALREADY_CANCELLED_KK)
            self._enqueue_ttl_sweep(contest)
            return
        else:
            self._send_command_reply(chat_id, command_message_id, CONTEST_NOT_READY_KK)
            return

        try:
            prior_ids = {str(value) for value in contest.get("winner_user_ids") or []}
            winner, participant_count = self._sample_candidate(
                chat_id,
                root_message_id,
                excluded_user_ids=prior_ids,
            )
            if draw_number > 1 and self.repo.is_logically_expired(contest):
                self.repo.abort_draw(
                    chat_id,
                    root_message_id,
                    draw_number=draw_number,
                    attempt_id=attempt_id,
                )
                self._send_command_reply(chat_id, command_message_id, CONTEST_EXPIRED_KK)
                return
            if winner is None:
                self.repo.abort_draw(
                    chat_id,
                    root_message_id,
                    draw_number=draw_number,
                    attempt_id=attempt_id,
                )
                message = NO_PARTICIPANTS_KK if draw_number == 1 else NO_REMAINING_CANDIDATES_KK
                self._send_command_reply(chat_id, command_message_id, message)
                return
            completed = self.repo.complete_draw(
                chat_id,
                root_message_id,
                draw_number=draw_number,
                attempt_id=attempt_id,
                participant=winner,
                frozen_participant_count=participant_count,
            )
        except Exception:
            self.repo.abort_draw(
                chat_id,
                root_message_id,
                draw_number=draw_number,
                attempt_id=attempt_id,
            )
            raise

        if not completed:
            persisted = self.repo.get_contest(chat_id, root_message_id, consistent=True)
            if draw_number > 1 and (self.repo.is_logically_expired(persisted or contest)):
                self.repo.abort_draw(
                    chat_id,
                    root_message_id,
                    draw_number=draw_number,
                    attempt_id=attempt_id,
                )
                self._send_command_reply(chat_id, command_message_id, CONTEST_EXPIRED_KK)
                return
            if persisted and persisted.get("status") == "DRAWN":
                self._replay_pending_announcement(
                    persisted,
                    command_message_id=command_message_id,
                    redraw_requested=False,
                )
                self._enqueue_ttl_sweep(persisted)
                return
            if (
                persisted
                and persisted.get("status") == "DRAWING"
                and str(persisted.get("draw_attempt_id") or "") == attempt_id
            ):
                self.repo.abort_draw(
                    chat_id,
                    root_message_id,
                    draw_number=draw_number,
                    attempt_id=attempt_id,
                )
                raise RuntimeError("Contest draw completion condition failed")
            return

        contest = self.repo.get_contest(chat_id, root_message_id, consistent=True)
        if not contest:
            raise RuntimeError("Contest disappeared after winner persistence")
        persisted_winner = _winner_at(contest, draw_number)
        if not persisted_winner:
            raise RuntimeError("Winner disappeared after persistence")
        self._announce_winner(contest, persisted_winner)
        self._enqueue_ttl_sweep(contest)

    def cancel(
        self,
        *,
        chat_id: int | str,
        root_message_id: int,
        command_message_id: int,
    ) -> None:
        contest = self.repo.get_contest(chat_id, root_message_id, consistent=True)
        if not contest:
            self._send_command_reply(chat_id, command_message_id, REPLY_ANCHOR_REQUIRED_KK)
            return
        if self.repo.is_logically_expired(contest):
            self._send_command_reply(chat_id, command_message_id, CONTEST_EXPIRED_KK)
            return
        if contest.get("status") == "ORPHANED":
            self._send_command_reply(chat_id, command_message_id, ORPHANED_KK)
            return
        cancelled = self.repo.cancel_contest(chat_id, root_message_id)
        if not cancelled:
            message = CONTEST_ALREADY_CANCELLED_KK if contest.get("status") == "CANCELLED" else CONTEST_CLOSED_KK
            self._send_command_reply(chat_id, command_message_id, message)
            self._enqueue_ttl_sweep(contest)
            return
        self._send_command_reply(chat_id, command_message_id, CONTEST_CANCELLED_KK)
        self._enqueue_ttl_sweep(cancelled)

    def status(
        self,
        *,
        chat_id: int | str,
        root_message_id: int,
        command_message_id: int,
    ) -> None:
        contest = self.repo.get_contest(chat_id, root_message_id, consistent=True)
        if not contest:
            self._send_command_reply(chat_id, command_message_id, REPLY_ANCHOR_REQUIRED_KK)
            return
        status = str(contest.get("status") or "UNKNOWN")
        if self.repo.is_logically_expired(contest):
            state_text = "мерзімі аяқталған"
        else:
            state_text = {
                "CREATING": "дайындалып жатыр",
                "CREATION_FAILED": "құру сәтсіз аяқталды",
                "OPEN": "ашық",
                "DRAWING": "ұтыс орындалып жатыр",
                "DRAWN": "жабық, жеңімпаз анықталған",
                "CANCELLED": "тоқтатылған",
                "ORPHANED": "дәлел хабарламалары жойылған",
            }.get(status, "белгісіз")
        participant_count = (
            int(contest.get("frozen_participant_count") or 0)
            if status in {"DRAWN", "ORPHANED"}
            else int(contest.get("participant_count") or 0)
        )
        draw_count = int(contest.get("draw_count") or 0)
        text = (
            "📊 <b>Конкурс күйі</b>\n"
            f"Күйі: <b>{escape(state_text)}</b>\n"
            f"Бірегей қатысушылар: <b>{participant_count}</b>\n"
            f"Ұтыс саны: <b>{draw_count}/{MAX_DRAWS}</b>"
        )
        self._send_command_reply(chat_id, command_message_id, text)


class ContestTTLWorker:
    """Advance retention work without exposing a Telegram-less service state."""

    def __init__(self, repo: ContestRepository, sqs_repo: SQSClient) -> None:
        self.repo = repo
        self.sqs_repo = sqs_repo

    def process(self, body: dict[str, Any]) -> None:
        """Stamp one bounded participant page and durably continue the sweep."""
        chat_id = body["chat_id"]
        root_message_id = int(body["root_message_id"])
        contest = self.repo.get_contest(chat_id, root_message_id, consistent=True)
        if not contest or contest.get("ttl_sweep_status") == "COMPLETE":
            return
        expires_at = contest.get("expires_at")
        if expires_at is None:
            return

        durable_cursor = contest.get("ttl_sweep_cursor")
        start_key = durable_cursor if isinstance(durable_cursor, dict) else None
        sweep_version = int(contest.get("ttl_sweep_version") or 0)
        page, next_start_key = self.repo.participant_page(
            chat_id,
            root_message_id,
            limit=TTL_SWEEP_PAGE_SIZE,
            start_key=start_key if isinstance(start_key, dict) else None,
        )
        self.repo.stamp_participant_ttl(page, int(expires_at))
        if next_start_key:
            advanced = self.repo.record_ttl_sweep_progress(
                chat_id,
                root_message_id,
                expected_start_key=start_key,
                expected_version=sweep_version,
                next_start_key=next_start_key,
            )
            if not advanced:
                return
            self.sqs_repo.send_contest_ttl_sweep_task(
                chat_id=int(chat_id),
                root_message_id=root_message_id,
            )
            return

        self.repo.complete_ttl_sweep(
            chat_id,
            root_message_id,
            rules_message_id=(
                int(contest["rules_message_id"]) if contest.get("rules_message_id") is not None else None
            ),
            expires_at=int(expires_at),
            expected_start_key=start_key,
            expected_version=sweep_version,
        )


def process_contest_ttl_recovery_task(
    body: dict[str, Any],
    *,
    repo: ContestRepository,
    sqs_repo: SQSClient,
) -> None:
    """Replay one bounded outbox page; sweep completion consumes each marker."""
    supplied_start_key = body.get("start_key")
    start_key = supplied_start_key if isinstance(supplied_start_key, dict) else None
    markers, next_start_key = repo.ttl_outbox_page(
        limit=TTL_OUTBOX_PAGE_SIZE,
        start_key=start_key,
    )
    for marker in markers:
        sqs_repo.send_contest_ttl_sweep_task(
            chat_id=int(marker["chat_id"]),
            root_message_id=int(marker["root_message_id"]),
        )
    if next_start_key:
        sqs_repo.send_contest_ttl_recovery_task(start_key=next_start_key)


def observe_contest_update(
    repo: ContestRepository | None,
    bot: TelegramClient,
    update: dict[str, Any],
    *,
    sqs_repo: SQSClient | None = None,
) -> None:
    """Convenience boundary used by the webhook."""
    if repo is not None:
        ContestService(repo, bot, sqs_repo).observe_update(update)


def process_contest_ttl_sweep_task(
    body: dict[str, Any],
    *,
    repo: ContestRepository,
    sqs_repo: SQSClient,
) -> None:
    """Convenience boundary used by the main SQS router."""
    ContestTTLWorker(repo, sqs_repo).process(body)
