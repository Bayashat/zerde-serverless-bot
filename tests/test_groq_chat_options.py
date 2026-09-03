"""Groq request compatibility controls for reasoning-capable models."""

from zerde_common.groq_chat import apply_groq_chat_options


def test_gpt_oss_uses_low_hidden_reasoning_with_output_reserve() -> None:
    payload = {"max_tokens": 64}

    apply_groq_chat_options(
        payload,
        model="openai/gpt-oss-safeguard-20b",
        max_output_tokens=128,
    )

    assert "max_tokens" not in payload
    assert payload["max_completion_tokens"] == 256
    assert payload["reasoning_effort"] == "low"
    assert payload["reasoning_format"] == "hidden"


def test_qwen_38_disables_reasoning_for_short_structured_decisions() -> None:
    payload: dict[str, object] = {}

    apply_groq_chat_options(
        payload,
        model="qwen/qwen3.8-27b",
        max_output_tokens=220,
    )

    assert payload["max_completion_tokens"] == 220
    assert payload["reasoning_effort"] == "none"
    assert "reasoning_format" not in payload


def test_non_reasoning_model_uses_modern_completion_limit_only() -> None:
    payload: dict[str, object] = {"max_tokens": 80}

    apply_groq_chat_options(
        payload,
        model="some-future-model",
        max_output_tokens=80,
    )

    assert payload == {"max_completion_tokens": 80}
