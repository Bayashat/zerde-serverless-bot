"""Private stdio broker: one fixed Gemini endpoint; no corpus/gold/AWS access."""

import asyncio
import hashlib
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from .live_session import AttemptLedger, SessionError, exclusive_lock

ROOT = Path(__file__).resolve().parents[3]
MAX_FRAME_BYTES = 2_000_000


def runtime_environment():
    return {
        "PATH": os.defpath,
        "PYTHONPATH": os.pathsep.join((str(ROOT), str(ROOT / "src/bot"), str(ROOT / "src/shared/python"))),
        "PYTHONUNBUFFERED": "1",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_DEFAULT_REGION": "eu-central-1",
        "AWS_ACCESS_KEY_ID": "local-evaluation",
        "AWS_SECRET_ACCESS_KEY": "local-evaluation",
        "AWS_SHARED_CREDENTIALS_FILE": "/dev/null",
        "AWS_CONFIG_FILE": "/dev/null",
        "STATS_TABLE_NAME": "local-replay-stats",
        "QUEUE_URL": "local-replay-queue",
        "BOT_TOKEN": "local-no-telegram-token",
        "GEMINI_API_KEY": "",
        "LOG_LEVEL": "ERROR",
        "ADMIN_USER_ID": "1",
        "GEMINI_RPD_LIMIT": "1000",
        "CHAT_LANG_MAP": "{}",
        "CAPTCHA_TIMEOUT_SECONDS": "300",
        "VOTEBAN_THRESHOLD": "5",
        "VOTEBAN_FORGIVE_THRESHOLD": "3",
        "CAPTCHA_MAX_ATTEMPTS": "3",
    }


class ObservedClient:
    def __init__(self, client, evidence, key, *, max_bytes):
        self.client, self.evidence, self.key = client, evidence, key
        self.max_bytes = max_bytes

    @asynccontextmanager
    async def stream(self, method, url, **kwargs):
        from services.memory_budget import MODEL

        if (
            method != "POST"
            or url != f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
            or kwargs.get("follow_redirects") is not False
        ):
            raise SessionError("Broker rejected a non-allowlisted destination")
        async with self.client.stream(method, url, **kwargs) as response:
            self.evidence["http_status"] = response.status_code
            observer = self

            class Body:
                status_code = response.status_code

                async def aiter_bytes(self):
                    captured, digest, size = bytearray(), hashlib.sha256(), 0
                    try:
                        async for chunk in response.aiter_bytes():
                            digest.update(chunk)
                            size += len(chunk)
                            captured.extend(chunk[: max(0, observer.max_bytes - len(captured))])
                            yield chunk
                    finally:
                        observer.evidence.update(
                            response_sha256=digest.hexdigest(),
                            received_bytes=size,
                            response_truncated=size > observer.max_bytes,
                        )
                        # Non-success bodies can echo credentials; retain status
                        # only. Successful model output is synthetic and private.
                        if response.status_code == 200:
                            observer.evidence["response_text"] = captured.decode("utf-8", errors="replace").replace(
                                observer.key, "[REDACTED]"
                            )

            yield Body()


async def gemini_attempt(kind, request, key):
    from services.memory_v2.answer_selector import GeminiAnswerProvider
    from services.memory_v2.gemini_extraction import GeminiExtractionProvider
    from zerde_common.async_http import bounded_async_client

    evidence = {"http_status": None, "response_sha256": None, "error_type": None}
    started = time.monotonic()
    payload = None
    try:
        async with (
            asyncio.timeout(20),
            bounded_async_client(timeout=20, connect_timeout=3, max_connections=1) as client,
        ):
            observed = ObservedClient(client, evidence, key, max_bytes=1_000_000 if kind == "extraction" else 100000)
            provider = (
                GeminiExtractionProvider(key, client=observed)
                if kind == "extraction"
                else GeminiAnswerProvider(key, client=observed)
            )
            payload = await provider.generate(request)
            if key in json.dumps(payload, ensure_ascii=False):
                payload = None
                evidence["error_type"] = "CredentialEchoRejected"
    except Exception as exc:
        evidence["error_type"] = type(exc).__name__  # Never serialize the exception or its chain.
    evidence["elapsed_ms"] = max(0, int((time.monotonic() - started) * 1000))
    return payload, evidence


class BrokerEngine:
    def __init__(self, ledger, attempt, *, sleep=asyncio.sleep):
        self.ledger, self.attempt, self.sleep = ledger, attempt, sleep

    async def generate(self, call):
        from services.memory_v2.answer_prompt import validate_answer_request
        from services.memory_v2.extraction_prompt import validate_request

        AttemptLedger.identity(call)
        (validate_request if call["kind"] == "extraction" else validate_answer_request)(call["request"])
        cached = self.ledger.cached(call)
        if cached is not None:
            return cached
        try:
            self.ledger.check_available()
        except SessionError as exc:
            if str(exc) in {"budget_exhausted", "max_calls_exhausted"}:
                return {"ok": False, "reason": str(exc), "cache_hit": False}
            raise
        delay = self.ledger.pacing_delay()
        if delay > 60 / self.ledger.manifest["rpm"] + 5:
            raise SessionError("Wall clock regressed beyond the pacing bound")
        if delay:
            await self.sleep(delay)
        try:
            identifier = self.ledger.reserve(call)
        except SessionError as exc:
            if str(exc) in {"budget_exhausted", "max_calls_exhausted"}:
                return {"ok": False, "reason": str(exc), "cache_hit": False}
            raise
        # Cancellation/process death leaves INFLIGHT durable; it is never sent
        # again on resume. Production owners control their distinct second attempt.
        payload, evidence = await self.attempt(call["kind"], call["request"])
        if not self.ledger.finish(identifier, payload, evidence):
            return {"ok": False, "reason": "accounting_anomaly", "cache_hit": False}
        if payload is None:
            return {"ok": False, "reason": "provider_unknown", "cache_hit": False}
        return {"ok": True, "payload": payload, "cache_hit": False}


def main():
    if len(sys.argv) != 2:
        return 2
    directory = Path(sys.argv[1]).resolve()
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return 2
    sys.path[:0] = [str(ROOT / "src/bot"), str(ROOT / "src/shared/python")]
    manifest = json.loads((directory / "session.json").read_text())
    from .__main__ import source_provenance

    if manifest["execution_source_sha256"] != source_provenance(ROOT)["execution_source_sha256"]:
        return 2
    from botocore.client import BaseClient

    with (
        exclusive_lock(directory / "provider.lock"),
        patch.object(BaseClient, "_make_api_call", side_effect=SessionError("AWS is forbidden in the provider broker")),
    ):
        ledger = AttemptLedger(directory, manifest)
        engine = BrokerEngine(ledger, lambda kind, request: gemini_attempt(kind, request, key))
        try:
            while raw := sys.stdin.buffer.readline(MAX_FRAME_BYTES + 1):
                if len(raw) > MAX_FRAME_BYTES or not raw.endswith(b"\n"):
                    return 2
                try:
                    call = json.loads(raw)
                    result = asyncio.run(engine.generate(call))
                except Exception:
                    result = {"ok": False, "reason": "broker_contract_or_storage_failure", "cache_hit": False}
                encoded = json.dumps(result, ensure_ascii=False, allow_nan=False).encode()
                if len(encoded) > MAX_FRAME_BYTES:
                    return 2
                sys.stdout.buffer.write(encoded + b"\n")
                sys.stdout.buffer.flush()
        finally:
            ledger.close()
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        code = 2
    raise SystemExit(code)
