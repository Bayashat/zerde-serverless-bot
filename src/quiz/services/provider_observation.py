"""Best-effort, content-free attempt observations; no admission or billing owner."""

import time
import uuid

from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})
_TOKEN_FIELDS = ("input_tokens", "output_tokens", "total_tokens")


def _usage_fields(usage, *, gemini=False, response_received=False):
    result = dict.fromkeys(_TOKEN_FIELDS)
    if usage is None:
        return {**result, "usage_status": "missing" if response_received else "no_response"}
    if not gemini and not isinstance(usage, dict):
        return {**result, "usage_status": "invalid"}
    names = (
        ("prompt_token_count", "candidates_token_count", "total_token_count")
        if gemini
        else ("prompt_tokens", "completion_tokens", "total_tokens")
    )
    invalid, missing = False, False
    for target, source in zip(_TOKEN_FIELDS, names, strict=True):
        value = usage.get(source) if isinstance(usage, dict) else getattr(usage, source, None)
        if value is None:
            missing = True
        elif type(value) is int and value >= 0:
            result[target] = value
        else:
            invalid = True
    return {**result, "usage_status": "invalid" if invalid else "missing" if missing else "known"}


class ProviderAttempt:
    """One actual application network attempt, independent of publication identity."""

    def __init__(self, provider, model):
        self._fields = {"provider": provider, "model": model, "attempt_id": uuid.uuid4().hex}
        self._started = time.monotonic()
        self._log({"phase": "started"})

    def _log(self, fields):
        try:
            logger.info("Quiz model attempt", extra={**self._fields, **fields})
        except Exception:
            # Observability failures must never turn a valid response into another call.
            pass

    def finish(self, outcome, *, status=None, response=None, gemini=False):
        try:
            received = response is not None
            usage = (
                getattr(response, "usage_metadata", None)
                if gemini
                else (response.get("usage") if isinstance(response, dict) else None)
            )
            fields = _usage_fields(usage, gemini=gemini, response_received=received)
        except Exception:
            fields = {**dict.fromkeys(_TOKEN_FIELDS), "usage_status": "invalid"}
        self._log(
            {
                "phase": "finished",
                "outcome": outcome,
                "elapsed_ms": max(0, int((time.monotonic() - self._started) * 1000)),
                "http_status": status if type(status) is int and 100 <= status <= 599 else None,
                **fields,
            }
        )
