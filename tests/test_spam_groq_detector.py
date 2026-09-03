"""Request and response contracts for the Groq spam classifier."""

import json
from unittest.mock import MagicMock, patch

import pytest
from services.spam.groq_detector import GroqSpamDetector
from zerde_common.ai_errors import ProviderRateLimitError, ProviderResponseError


def _response(status: int, body: dict) -> MagicMock:
    response = MagicMock()
    response.status = status
    response.data = json.dumps(body).encode()
    return response


@patch("services.spam.groq_detector._http")
def test_spam_detector_uses_dedicated_model_and_reasoning_safe_json_payload(mock_http: MagicMock) -> None:
    mock_http.request.return_value = _response(
        200,
        {"choices": [{"message": {"content": '{"label":"SPAM","confidence":0.99,"reason":"vpn_ad"}'}}]},
    )
    detector = GroqSpamDetector()
    detector.model = "openai/gpt-oss-safeguard-20b"

    result = detector.classify("CURRENT_MESSAGE:\nVPN бесплатно https://example.invalid")

    assert result.label == "SPAM"
    assert result.reason == "vpn_ad"
    payload = json.loads(mock_http.request.call_args.kwargs["body"])
    assert payload["model"] == "openai/gpt-oss-safeguard-20b"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_completion_tokens"] == 256
    assert payload["reasoning_effort"] == "low"
    assert payload["reasoning_format"] == "hidden"
    assert "max_tokens" not in payload


@patch("services.spam.groq_detector._http")
def test_spam_detector_rejects_empty_reasoning_only_response(mock_http: MagicMock) -> None:
    mock_http.request.return_value = _response(
        200,
        {"choices": [{"message": {"content": ""}}]},
    )

    with pytest.raises(ProviderResponseError, match="empty spam classification content"):
        GroqSpamDetector().classify("CURRENT_MESSAGE:\nVPN ad")


@patch("services.spam.groq_detector._http")
def test_spam_detector_preserves_rate_limit_error_for_queue_retry(mock_http: MagicMock) -> None:
    mock_http.request.return_value = _response(429, {"error": {"message": "rate limited"}})

    with pytest.raises(ProviderRateLimitError):
        GroqSpamDetector().classify("CURRENT_MESSAGE:\nVPN ad")
