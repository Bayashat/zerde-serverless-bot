"""Telegram identities only: observed aliases help lookup but never merge people."""

import re
from dataclasses import dataclass

from .models import MemoryConflict, MemoryInputError, MemoryUnavailable, chat_key, positive_id

_USERNAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{4,31}")


def username(value):
    if not isinstance(value, str) or not _USERNAME.fullmatch(value):
        raise MemoryInputError("Expected a Telegram username")
    return value.casefold()


class IdentityDirectory:
    def __init__(self, repo, *, get_chat_member):
        self.repo, self.get_chat_member = repo, get_chat_member

    def observe(self, event, telegram_user):
        """Caller passes the authenticated update's own `from`, not model text."""
        actor = positive_id(telegram_user.get("id"))
        if actor != event.actor_user_id or telegram_user.get("is_bot"):
            raise MemoryInputError("Alias observation does not belong to source author")
        alias = username(telegram_user.get("username"))
        control = self.repo._active_control(event.chat_id)
        subject = self.repo._active_subject(event.chat_id, actor, control)
        observation = self.repo.get_observation(event.chat_id, event.message_id)
        if (
            not observation
            or observation.get("deleted")
            or observation.get("ambiguous")
            or observation.get("epoch") != control["epoch"]
            or observation.get("actor_user_id") != actor
        ):
            raise MemoryUnavailable("Alias needs a current authenticated observation")
        key = f"ALIAS#{alias}#USER#{actor}"
        old = self.repo._read(event.chat_id, key)
        row = {
            "pk": chat_key(event.chat_id),
            "sk": key,
            "kind": "ALIAS",
            "revision": int(old.get("revision", 0)) + 1,
            "alias": alias,
            "actor_user_id": actor,
            "subject_generation": subject["generation"],
            "source_ref": {
                "source_id": event.message_id,
                "source_version": int(observation["revision"]),
                "epoch": control["epoch"],
            },
            "epoch": control["epoch"],
            "last_seen_at": self.repo.now(),
            "ttl": self.repo.now() + 30 * 86400,
        }
        self.repo._transaction(
            [
                self.repo._check_snapshot(control),
                self.repo._check_snapshot(subject),
                self.repo._check_snapshot(observation),
                self.repo._put_cas(row, old),
            ]
        )

    def resolve(self, chat_id, alias):
        alias = username(alias)
        control = self.repo._active_control(chat_id)
        candidates = []
        for count, row in enumerate(self.repo._list(chat_id, f"ALIAS#{alias}#USER#")):
            if count >= 64:
                raise MemoryUnavailable("Alias inventory exceeds its bounded lookup")
            if row.get("epoch") != control["epoch"] or int(row.get("ttl", 0)) <= self.repo.now():
                continue
            ref = row.get("source_ref") or {}
            observation = self.repo.get_observation(chat_id, ref.get("source_id", "0"))
            if (
                not observation
                or observation.get("deleted")
                or observation.get("ambiguous")
                or observation.get("revision") != ref.get("source_version")
                or observation.get("epoch") != control["epoch"]
            ):
                continue
            try:
                subject = self.repo._active_subject(chat_id, row["actor_user_id"], control)
            except MemoryUnavailable:
                continue
            if subject["generation"] == row["subject_generation"]:
                candidates.append(row)
            if len(candidates) > 8:
                raise MemoryUnavailable("Alias lookup is ambiguous")
        matches = []
        for row in candidates:
            # A renamed/transferred username must not silently select its old owner.
            member = self.get_chat_member(chat_id, int(row["actor_user_id"]))
            user = member.get("user") or {}
            if (
                str(user.get("id")) == row["actor_user_id"]
                and not user.get("is_bot")
                and str(user.get("username", "")).casefold() == alias
                and member.get("status") in {"member", "administrator", "creator", "restricted"}
                and (member.get("status") != "restricted" or member.get("is_member") is True)
            ):
                matches.append(row["actor_user_id"])
        if len(matches) != 1:
            raise MemoryUnavailable("No unique current Telegram identity for this alias")
        return matches[0]


@dataclass(frozen=True)
class SubjectSelection:
    subject_ids: tuple[str, ...]
    unresolved_aliases: tuple[str, ...] = ()


def select_subjects(message, *, bot_username, resolve_alias, reply_subjects):
    """Only entity user IDs, current verified aliases, and same-chat reply metadata."""
    actor = positive_id((message.get("from") or {}).get("id"))
    text = message.get("text") or message.get("caption") or ""
    wire = text.encode("utf-16-le")
    ids, unresolved = [], []
    for entity in message.get("entities", message.get("caption_entities", [])) or []:
        if entity.get("type") == "text_mention" and not (entity.get("user") or {}).get("is_bot"):
            ids.append(positive_id((entity.get("user") or {}).get("id")))
        elif entity.get("type") == "mention":
            start, length = entity.get("offset"), entity.get("length")
            if (
                type(start) is not int
                or type(length) is not int
                or start < 0
                or length < 1
                or (start + length) * 2 > len(wire)
            ):
                raise MemoryInputError("Invalid Telegram mention range")
            try:
                alias = username(wire[start * 2 : (start + length) * 2].decode("utf-16-le").removeprefix("@"))
            except (UnicodeError, MemoryInputError):
                raise MemoryInputError("Invalid Telegram mention") from None
            if alias == str(bot_username).lstrip("@").casefold():
                continue
            try:
                ids.append(resolve_alias(alias))
            except MemoryUnavailable:
                unresolved.append(alias)
    reply = message.get("reply_to_message") or {}
    replied_user = reply.get("from") or {}
    if replied_user.get("is_bot"):
        # The caller only exposes this bot's receipts. Raw Telegram bot text is ignored.
        ids.extend(reply_subjects(reply.get("message_id")))
    elif replied_user.get("id"):
        ids.append(positive_id(replied_user["id"]))
    unique = tuple(dict.fromkeys([*ids, actor]))
    if len(unique) > 8:
        raise MemoryInputError("Too many answer subjects")
    return SubjectSelection(unique or (actor,), tuple(unresolved))


def observe_accepted_alias(admission, telegram_user):
    """Safe immediate admission only; delayed CLEAN messages can learn on a later observation."""
    if not admission.eligible or not admission.event or not telegram_user.get("username"):
        return
    repo, event = admission.ingestion.repo, admission.event
    control = repo.get_control(event.chat_id)
    if not control.get("learning_enabled"):
        return
    head = repo.get_source_head(event.chat_id, event.message_id)
    observation = repo.get_observation(event.chat_id, event.message_id)
    if not head or head.get("revision") != observation.get("revision"):
        return
    try:
        IdentityDirectory(repo, get_chat_member=lambda *_: {}).observe(event, telegram_user)
    except (MemoryInputError, MemoryUnavailable, MemoryConflict):
        return
