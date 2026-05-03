"""RPD counter failures must fail closed before calling Gemini."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from services.ai.gemini_client import GeminiClient, GeminiUnavailableError
from services.repositories.rate_limit import RateLimitRepository, RateLimitUnavailableError


def _client_error() -> ClientError:
    return ClientError(
        {"Error": {"Code": "InternalServerError", "Message": "dynamodb unavailable"}},
        "UpdateItem",
    )


def test_bot_rate_limit_increment_failure_fails_closed() -> None:
    table = MagicMock()
    table.update_item.side_effect = _client_error()

    repo = RateLimitRepository()
    with patch("services.repositories.rate_limit.get_dynamodb") as mock_get_dynamodb:
        mock_get_dynamodb.return_value.Table.return_value = table

        with pytest.raises(RateLimitUnavailableError):
            repo.increment_and_check()


def test_gemini_text_explain_does_not_call_api_when_counter_unavailable() -> None:
    client = GeminiClient.__new__(GeminiClient)
    client._api_key = "test-key"
    client._model = "test-model"
    client._rate_repo = MagicMock()
    client._rate_repo.increment_and_check.side_effect = RateLimitUnavailableError("counter down")
    client._rate_repo.rpd_limit = 1000

    with patch("services.ai.gemini_client._http.request") as mock_request:
        with pytest.raises(GeminiUnavailableError):
            client.explain_term("kubernetes", "en")

    mock_request.assert_not_called()


def test_gemini_media_explain_does_not_call_api_when_counter_unavailable() -> None:
    client = GeminiClient.__new__(GeminiClient)
    client._api_key = "test-key"
    client._model = "test-model"
    client._rate_repo = MagicMock()
    client._rate_repo.increment_and_check.side_effect = RateLimitUnavailableError("counter down")
    client._rate_repo.rpd_limit = 1000

    with patch("services.ai.gemini_client._http_multimodal.request") as mock_request:
        with pytest.raises(GeminiUnavailableError):
            client.explain_media(
                media_kind="photo",
                file_bytes=b"image",
                mime_type="image/jpeg",
                lang="en",
            )

    mock_request.assert_not_called()


def test_quiz_rate_limit_increment_failure_fails_closed() -> None:
    os.environ.setdefault("BOT_TOKEN", "test-bot-token")
    os.environ.setdefault("TABLE_NAME", "test-quiz-table")
    os.environ.setdefault("QUIZ_LLM_RPD", "1000")

    quiz_dir = Path(__file__).resolve().parents[1] / "src" / "quiz"
    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if name in {"core", "services"} or name.startswith(("core.", "services."))
    }

    try:
        for name in list(saved_modules):
            sys.modules.pop(name, None)
        sys.path.insert(0, str(quiz_dir))
        from services.rate_limit_repository import (  # noqa: PLC0415
            QuizRateLimitRepository,
            QuizRateLimitUnavailableError,
        )

        repo = QuizRateLimitRepository.__new__(QuizRateLimitRepository)
        repo._table = MagicMock()
        repo._table.update_item.side_effect = _client_error()
        repo.rpd_limit = 1000

        with pytest.raises(QuizRateLimitUnavailableError):
            repo.increment_and_check()
    finally:
        if str(quiz_dir) in sys.path:
            sys.path.remove(str(quiz_dir))
        for name in list(sys.modules):
            if name in {"core", "services"} or name.startswith(("core.", "services.")):
                sys.modules.pop(name, None)
        sys.modules.update(saved_modules)
