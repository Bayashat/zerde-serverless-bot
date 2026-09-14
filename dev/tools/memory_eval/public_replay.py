"""Real public routing and durable delivery with synthetic Telegram transport."""

import asyncio
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import patch

from .contract import EvaluationInputError, fingerprint
from .plain_requests import build_audit_request, parse_audit, plain_client, validate_plain_request


class PublicAnswerReplay:
    def __init__(self, domain, plain_provider, audit_provider):
        self.domain, self.plain_provider, self.audit_provider = domain, plain_provider, audit_provider
        self.trace = []
        self.identities = {}

    def message(self, question):
        qid = question["question_id"]
        mid = 1_000_000_000 + int(fingerprint(qid)[:12], 16) % 900_000_000
        if mid in self.identities and self.identities[mid] != qid:
            raise EvaluationInputError("Synthetic message identity collision")
        self.identities[mid] = qid
        self.domain.clock.now += 1  # Questions are new messages after their checkpoint event.
        message = {
            "message_id": mid,
            "date": self.domain.clock.now,
            "chat": {"id": int(question["chat_id"]), "type": "supergroup"},
            "from": {"id": int(question["requester_id"]), "is_bot": False, "first_name": "Synthetic requester"},
            "text": question["text"],
        }
        target = question.get("target_subject_id", question["requester_id"])
        if target not in {"group", question["requester_id"]}:
            # Identity metadata only. A historical self-statement here would leak
            # the answer into the supposedly memory-free fallback input.
            message["reply_to_message"] = {
                "message_id": mid - 1,
                "from": {"id": int(target), "is_bot": False, "first_name": "Synthetic target"},
            }
        return message

    async def answer(self, question, language):
        from services.memory_v2.answer_rendering import unknown_text
        from services.memory_v2.answer_selector import MemoryAnswerSelector
        from services.memory_v2.models import MemoryConflict, MemoryInputError, MemoryUnavailable
        from services.memory_v2.public_answers import MemoryPublicAnswers

        domain, message, delivered = self.domain, self.message(question), []

        async def authorize(*_):
            return True

        async def member(_chat, actor):
            return {"status": "member", "user": {"id": int(actor), "is_bot": False}}

        async def send(chat, text, *, reply_to_message_id):
            if str(chat) != question["chat_id"] or reply_to_message_id != message["message_id"]:
                raise EvaluationInputError("Public replay changed its destination")
            mid = message["message_id"] + len(delivered) + 100
            row = {"kind": "explicit_answer", "chat_id": str(chat), "message_id": mid, "text": text}
            delivered.append(row)
            domain.sent.append(row)
            return mid

        api = SimpleNamespace(authorize=authorize, member=member, send=send)
        service = MemoryPublicAnswers(
            domain.repo,
            api,
            selector_factory=lambda validate: MemoryAnswerSelector(
                domain.answer_provider, domain.budget, validate_snapshot=validate, rate_limit=domain.quota
            ),
            bot_username="zerde_eval_bot",
        )
        route = "memory"
        try:
            consumed = await service.try_answer(message, question=question["text"], lang=language)
            if not consumed:
                route = "plain"
                # ExplicitDelivery owns synchronous send checks/asyncio.run.
                # This lane is sequential; no parallel domain scenario mutation.
                await asyncio.to_thread(self._plain, message, language, api)
        except (MemoryConflict, MemoryInputError, MemoryUnavailable):
            pass
        except Exception as exc:
            domain.missing.append(
                {"kind": "public_answer", "question_id": question["question_id"], "error_type": type(exc).__name__}
            )
        # Production can deliver a temporary-unavailability notice after exhausting
        # its provider chain. Record that send without hiding unresolved attempts.
        domain.missing.extend(self.plain_provider.missing)
        key = (
            "ANSWER_REQUEST#" + hashlib.sha256(f"tg:{question['chat_id']}:{message['message_id']}".encode()).hexdigest()
        )
        receipt = domain.repo._read(question["chat_id"], key)
        trace = {
            "question_id": question["question_id"],
            "route": route,
            "request_id": f"tg:{question['chat_id']}:{message['message_id']}",
            "state": receipt.get("state", "NOT_SENT"),
            "message_ids": [row["message_id"] for row in delivered],
            "transport": "synthetic_telegram_sink_with_real_persistence",
        }
        self.trace.append(trace)
        if receipt.get("state") != "SENT" or not delivered:
            return None
        if [step.get("message_id") for step in receipt["steps"]] != trace["message_ids"]:
            raise EvaluationInputError("Delivered messages do not match durable receipt")
        texts = [row["text"] for row in delivered]
        result = {
            "question_id": question["question_id"],
            "assertions": [],
            "abstained": False,
            "delivery": trace,
            "response_text": texts,
        }
        if route == "memory":
            for ref in receipt["fact_refs"]:
                fact = domain.repo._read(question["chat_id"], ref["fact_id"])
                identity = fact["subject_id"].removeprefix("USER#")
                match = next(
                    (
                        row
                        for row in domain.repo.get_profile(question["chat_id"], identity)
                        if row["fact_id"] == ref["fact_id"]
                    ),
                    None,
                )
                if match is None:
                    raise EvaluationInputError("Delivered fact no longer has a current source")
                result["assertions"].append(domain._fact(question["chat_id"], match))
            result["abstained"] = not result["assertions"] and texts == [unknown_text(language)]
            return result
        reply = "\n".join(texts)
        try:
            audit = parse_audit(await self.audit_provider.generate(build_audit_request(question["text"], reply)), reply)
        except Exception:
            domain.missing.append(
                {
                    "kind": "plain_answer_audit",
                    "question_id": question["question_id"],
                    "reason": "unverified_delivered_text",
                }
            )
            result["semantic_observation"] = {"state": "UNVERIFIED"}
            return result
        result["semantic_observation"] = {"state": "MODEL_OBSERVED", **audit}
        result["abstained"] = audit["classification"] == "refusal"
        for quote in audit["claim_quotes"]:
            # No gold lookup and no invented historical evidence. Every observed
            # plain claim necessarily fails the existing source-support gate.
            result["assertions"].append(
                {
                    "chat_id": question["chat_id"],
                    "subject_id": question.get("target_subject_id", question["requester_id"]),
                    "field": "unverified_plain_claim",
                    "value": quote,
                    "evidence": {},
                }
            )
        return result

    def _plain(self, message, language, api):
        from services import group_agent
        from services.ai import gemini_client
        from services.memory_v2.explicit_delivery import ExplicitDelivery
        from services.memory_v2.explicit_request_gate import capture
        from services.repositories.explicit_context_repository import ExplicitContextRepository

        domain = self.domain
        with patch("services.repositories.group_memory.get_dynamodb", return_value=domain.db):
            legacy = ExplicitContextRepository(domain.business.name, memory_v2_repo=domain.repo)
        context = group_agent.build_explicit_question_context(legacy, message["chat"]["id"], message)
        style = group_agent._load_chat_style_profile(legacy, message["chat"]["id"])
        client = plain_client()

        def transport(*, operation, url, body, headers, before_attempt=None):
            from .live import RemoteProviderFailure

            if operation != "group_chat_reply" or client._api_key not in url:
                raise EvaluationInputError("Unexpected plain provider operation")
            if before_attempt:
                before_attempt()
            request = {
                "question": context.user_text,
                "language": language,
                "style_profile": style,
                "payload": json.loads(body),
            }
            validate_plain_request(request)
            try:
                payload = asyncio.run(self.plain_provider.generate(request))
            except RemoteProviderFailure as exc:
                if exc.reason not in {"provider_unknown", "recorded_provider_unknown"}:
                    raise
                raise gemini_client.GeminiUnavailableError("Observed provider transport did not complete") from None
            return json.dumps(payload).encode()

        client._post_generate_content = transport
        chat, actor, mid = message["chat"]["id"], message["from"]["id"], message["message_id"]
        body = {
            "chat_id": chat,
            "requester_user_id": actor,
            "reply_to_message_id": mid,
            "request_gate": capture(domain.repo, chat, actor, mid, requested_at=message["date"]),
        }
        guard = ExplicitDelivery(domain.repo, legacy, SimpleNamespace(), body, api)
        try:
            guard.start()
            with (
                patch.object(group_agent, "_get_gemini", return_value=client),
                patch.object(group_agent, "_get_group_chat_reply_fallback", return_value=None),
                patch.object(gemini_client, "_circuit_is_open", return_value=False),
            ):
                group_agent.answer_group_question(
                    repo=legacy,
                    bot=guard,
                    chat_id=chat,
                    reply_to_message_id=mid,
                    user_text=context.user_text,
                    retrieval_query=context.retrieval_query,
                    lang=language,
                    requester_user_id=actor,
                    current_user_message=context.current_user_message,
                    source_message_context=context.source_message_context,
                    parent_bot_message_id=context.parent_bot_message_id,
                )
        finally:
            guard.close()
