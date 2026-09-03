"""Compatibility options for Groq chat-completion models."""

from __future__ import annotations

from typing import Any, MutableMapping

_GPT_OSS_PREFIX = "openai/gpt-oss-"
_QWEN_38_MODEL = "qwen/qwen3.8-27b"
_GPT_OSS_REASONING_RESERVE = 128


def apply_groq_chat_options(
    payload: MutableMapping[str, Any],
    *,
    model: str,
    max_output_tokens: int,
) -> None:
    """Add current Groq token/reasoning controls to a request payload in place.

    Groq reasoning tokens count against ``max_completion_tokens``. GPT-OSS
    therefore needs a small reserve beyond the intended visible response; without
    it, short classifiers can finish with an empty ``content`` value. Qwen 3.8
    supports instruct mode by disabling reasoning, which is preferable for these
    latency-sensitive JSON and fallback requests.
    """
    visible_tokens = max(1, int(max_output_tokens))
    payload.pop("max_tokens", None)
    payload.pop("reasoning_effort", None)
    payload.pop("reasoning_format", None)

    if model.startswith(_GPT_OSS_PREFIX):
        payload["max_completion_tokens"] = max(
            256,
            visible_tokens + _GPT_OSS_REASONING_RESERVE,
        )
        payload["reasoning_effort"] = "low"
        payload["reasoning_format"] = "hidden"
        return

    payload["max_completion_tokens"] = visible_tokens
    if model == _QWEN_38_MODEL:
        payload["reasoning_effort"] = "none"
