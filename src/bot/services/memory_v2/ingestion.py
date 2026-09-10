"""Trusted admission adapter: canonical bodies never come from moderation receipts."""

from __future__ import annotations

import hashlib
import json
import logging
import re

import boto3

from .models import MemoryInputError, MemoryLearningPaused, MemoryUnavailable, SourceRef, chat_key

logger = logging.getLogger(__name__)


def moderation_input_hash(text, message_context=None):
    """Exactly Z13's moderation-input digest, distinct from canonical source_hash."""
    return hashlib.sha256(
        json.dumps(
            {"text": text, "message_context": message_context or {}}, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def task_payload(chat_id, ref):
    chat_key(chat_id)
    if not isinstance(ref, SourceRef):
        raise MemoryInputError("Expected typed source reference")
    return {"schema": 2, "task_type": "PROCESS_MEMORY_V2", "chat_id": str(chat_id), "source_ref": ref.as_dict()}


class MemoryQueue:
    def __init__(self, queue_url, *, client=None):
        if not isinstance(queue_url, str) or not queue_url:
            raise MemoryInputError("An independent Memory V2 queue is required")
        self.queue_url = queue_url
        self.client = client

    def send(self, chat_id, ref):
        if self.client is None:
            self.client = boto3.client("sqs")
        self.client.send_message(QueueUrl=self.queue_url, MessageBody=json.dumps(task_payload(chat_id, ref)))


class MemoryIngestion:
    def __init__(self, repo, moderation_repo, queue):
        self.repo = repo
        self.moderation_repo = moderation_repo
        self.queue = queue

    def observe(self, event):
        return self.repo.observe(event)

    def prepare(self, event, moderation_input_hash):
        return self.repo.prepare_candidate(event, moderation_input_hash)

    def reject(self, chat_id, ref):
        return self.repo.finish_admission(chat_id, ref, outcome="REJECTED")

    def enqueue(self, chat_id, ref, *, strict=False):
        try:
            self.queue.send(chat_id, ref)
            return True
        except Exception as exc:
            if strict:
                raise
            # WORK is already durable. No raw body or exception text enters logs.
            logger.warning("Memory enqueue deferred to recovery", extra={"error_type": type(exc).__name__})
            return False

    def accept_safe(self, event):
        """Only the webhook's deterministic CLEAN / review-exempt adapter may call."""
        old = self.repo.get_source_head(event.chat_id, event.message_id)
        ref = self.repo.register_source(event, expected_source_version=int(old.get("revision", 0)))
        self.enqueue(event.chat_id, ref)
        return ref

    def _receipt(self, case_id):
        if not isinstance(case_id, str) or not re.fullmatch(r"decision#[0-9a-f]{32}", case_id):
            raise MemoryInputError("Invalid moderation case identity")
        receipt = self.moderation_repo.get(case_id)
        if (
            not receipt
            or receipt.get("kind") != "spam_decision"
            or receipt.get("state") != "clean"
            or receipt.get("guest_bot") is not False
            or not receipt.get("source_ref")
        ):
            raise MemoryUnavailable("No eligible CLEAN receipt")
        raw_ref = receipt["source_ref"]
        ref = SourceRef(str(raw_ref["source_id"]), int(raw_ref["source_version"]), raw_ref["epoch"])
        chat_key(receipt["chat_id"])
        if str(receipt["message_id"]) != ref.source_id:
            raise MemoryInputError("Moderation receipt source identity mismatch")
        return receipt, ref

    def _condition(self, receipt, ref, admission):
        # Table is injected by trusted app wiring. No caller-provided table, predicate,
        # body, or 'safe=True' can authorize promotion.
        values = {
            ":kind": "spam_decision",
            ":clean": "clean",
            ":pending": True,
            ":guest": False,
            ":chat": str(receipt["chat_id"]),
            ":user": int(receipt["user_id"]),
            ":message": int(receipt["message_id"]),
            ":ref": ref.as_dict(),
            ":hash": admission["moderation_input_hash"],
        }
        return {
            "ConditionCheck": {
                "TableName": self.moderation_repo.table.name,
                "Key": {"stat_key": "spam_case#" + receipt["case_id"]},
                "ConditionExpression": (
                    "kind = :kind AND #state = :clean AND outbox_pending = :pending "
                    "AND guest_bot = :guest AND chat_id = :chat AND user_id = :user "
                    "AND message_id = :message AND source_ref = :ref AND input_hash = :hash"
                ),
                "ExpressionAttributeNames": {"#state": "state"},
                "ExpressionAttributeValues": values,
            }
        }

    def promote_clean(self, case_id):
        receipt, ref = self._receipt(case_id)
        chat_id = receipt["chat_id"]
        if not receipt.get("outbox_pending"):
            self.repo.complete_admission_ack(chat_id, ref)
            return receipt.get("recovery_outcome", "EXPIRED")
        admission = self.repo._read(chat_id, f"ADMISSION#{ref.source_id}#{ref.source_version}")
        if (
            admission
            and admission.get("state") in {"PENDING_REVIEW", "ACCEPTED"}
            and (
                admission.get("actor_user_id") != str(receipt["user_id"])
                or admission.get("moderation_input_hash") != receipt.get("input_hash")
            )
        ):
            raise MemoryInputError("CLEAN receipt does not match the staged canonical source")
        if admission and admission.get("state") == "ACCEPTED":
            outcome = "INGESTED"  # Commit succeeded but receipt ACK may have been lost.
        elif admission and admission.get("state") in {"EXPIRED", "REJECTED"}:
            outcome = "EXPIRED"
        else:
            try:
                if not admission:
                    raise MemoryUnavailable("Candidate admission expired")
                self.repo.promote_candidate(
                    chat_id, ref, receipt_condition=self._condition(receipt, ref, admission), receipt_case_id=case_id
                )
                outcome = "INGESTED"
            except MemoryLearningPaused:
                return "PAUSED"
            except MemoryUnavailable:
                terminal = self.repo.finish_admission(chat_id, ref, outcome="EXPIRED")
                outcome = "INGESTED" if terminal == "ACCEPTED" else "EXPIRED"
        self.moderation_repo.acknowledge_clean(
            case_id,
            ref.as_dict(),
            chat_id=int(chat_id),
            user_id=int(receipt["user_id"]),
            message_id=int(receipt["message_id"]),
            outcome=outcome,
        )
        if outcome == "INGESTED":
            self.repo.complete_admission_ack(chat_id, ref)
            self.enqueue(chat_id, ref)
        return outcome
