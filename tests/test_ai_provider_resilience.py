"""Focused tests for LLM provider routing and latency controls."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

from services.ai.gemini_client import _thinking_config_for_model


def test_bot_gemini_thinking_config_uses_model_specific_low_latency_controls() -> None:
    assert _thinking_config_for_model("gemini-3.1-flash-lite") == {"thinkingLevel": "minimal"}
    assert _thinking_config_for_model("gemini-2.5-flash") == {"thinkingBudget": 0}
    assert _thinking_config_for_model("unknown-model") is None


def test_quiz_fallback_provider_continues_after_transport_error() -> None:
    zerde = os.path.join(os.path.dirname(__file__), "..", "src", "shared", "python")
    quiz_dir = os.path.join(os.path.dirname(__file__), "..", "src", "quiz")
    saved_modules: dict[str, object] = {}

    for mod_name in list(sys.modules):
        if mod_name in ("core", "services") or mod_name.startswith(("core.", "services.")):
            saved_modules[mod_name] = sys.modules.pop(mod_name)

    sys.path.insert(0, zerde)
    sys.path.insert(0, quiz_dir)
    try:
        from services.llm_provider import FallbackProvider
        from zerde_common.ai_errors import ProviderTransportError

        primary = MagicMock()
        primary.generate_json.side_effect = ProviderTransportError("primary timeout")
        secondary = MagicMock()
        secondary.generate_json.return_value = {"question": "ok"}

        provider = FallbackProvider([primary, secondary])

        result = provider.generate_json("prompt", interactive=True)

        assert result == {"question": "ok"}
        primary.generate_json.assert_called_once_with("prompt", 0.3, interactive=True)
        secondary.generate_json.assert_called_once_with("prompt", 0.3, interactive=True)
    finally:
        if quiz_dir in sys.path:
            sys.path.remove(quiz_dir)
        if zerde in sys.path:
            sys.path.remove(zerde)
        for mod_name in list(sys.modules):
            if mod_name in ("core", "services") or mod_name.startswith(("core.", "services.")):
                sys.modules.pop(mod_name, None)
        sys.modules.update(saved_modules)
