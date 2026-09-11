"""Verify actual JSON log output never contains credentials or Telegram bodies."""

import io
import json
import logging
from urllib.parse import quote

import pytest
from zerde_common.logger import JSONFormatter, ZerdeLoggerAdapter, get_json_logger
from zerde_common.logging_utils import (
    api_gateway_event_summary,
    llm_text_log_fields,
    redact_log_text,
    telegram_update_log_extra,
)


@pytest.fixture
def captured_logger():
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JSONFormatter())
    logger = logging.Logger("safe-log-test", logging.DEBUG)
    logger.addHandler(handler)
    return ZerdeLoggerAdapter(logger, {}), output


def test_formatter_redacts_message_nested_extra_and_lazily_loaded_secrets(monkeypatch, captured_logger):
    logger, output = captured_logger
    secret = "test-only-secret/with+encoding"
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    monkeypatch.setenv("MAX_OUTPUT_TOKENS", "1234")
    details = {"nested": [{"api_key": "unconfigured-key", "error": secret}], "response_chars": 1234}
    logger.error("Provider failed: %s / %s", secret, quote(secret, safe=""), extra=details)
    emitted = output.getvalue()
    assert secret not in emitted
    assert quote(secret, safe="") not in emitted
    assert "unconfigured-key" not in emitted
    assert json.loads(emitted)["response_chars"] == 1234
    assert details["nested"][0]["error"] == secret


@pytest.mark.parametrize(
    ("diagnostic", "secret"),
    [
        (
            "https://api.telegram.org/bot123456789:abcdefghijklmnopqrstuvwxyz_123456/sendMessage",
            "abcdefghijklmnopqrstuvwxyz",
        ),
        ("/botcustom-fake-token/getMe", "custom-fake-token"),
        ("token 123456789:abcdefghijklmnopqrstuvwxyz_123456", "abcdefghijklmnopqrstuvwxyz"),
        ("https://example.test/request?key=fake-google-key&mode=plain", "fake-google-key"),
        ("Authorization: Bearer fake-bearer-token", "fake-bearer-token"),
        ("Authorization: Basic fake-base64-credentials", "fake-base64-credentials"),
        ("password='fake secret containing spaces'", "containing spaces"),
        ("{'access_token': 'fake-oauth-token'}", "fake-oauth-token"),
        ("Cookie=session-sensitive-value", "session-sensitive-value"),
        ("api_key=AIzaabcdefghijklmnopqrstuvwxyz123456789", "AIzaabcdefghijklmnopqrstuvwxyz"),
        ("gsk_abcdefghijklmnopqrstuvwxyz123456789", "gsk_abcdefghijklmnopqrstuvwxyz"),
        ("sk-abcdefghijklmnopqrstuvwxyz123456789", "sk-abcdefghijklmnopqrstuvwxyz"),
    ],
)
def test_credential_shapes_are_redacted_without_environment_configuration(diagnostic, secret):
    redacted = redact_log_text(diagnostic)
    assert secret not in redacted
    assert "REDACTED" in redacted


def test_exception_chain_redacts_credentials_and_file_paths(captured_logger):
    logger, output = captured_logger
    try:
        try:
            raise OSError("GET https://api.telegram.org/file/bot123456:abcdefghijklmnopqrstuvwxyz/private-contact.pdf")
        except OSError as cause:
            raise RuntimeError("retry failed Authorization=Bearer second-fake-secret") from cause
    except RuntimeError:
        logger.exception("Telegram transport failure")
    emitted = output.getvalue()
    assert "abcdefghijklmnopqrstuvwxyz" not in emitted
    assert "private-contact.pdf" not in emitted
    assert "second-fake-secret" not in emitted
    assert "OSError" in emitted
    assert "RuntimeError" in emitted
    assert "direct cause" in json.loads(emitted)["exception"]


def test_formatter_omits_content_fields_and_handles_non_json_values(captured_logger, monkeypatch):
    secret = "fake-object-secret"
    monkeypatch.setenv("BOT_TOKEN", secret)

    class Diagnostic:
        def __str__(self):
            return f"Failed with {secret}"

    logger, output = captured_logger
    logger.info(
        "Operation failed",
        extra={
            "diagnostic": Diagnostic(),
            "payload": {"text": "private-conversation"},
            "file_id": "private-file-reference",
            "file_name": "private-file-name.pdf",
            "source_username": "private-username",
            "contact": {"phone_number": "private-contact"},
            "response_preview": "private-response",
            "response_chars": 123,
            "token_count": 5,
        },
    )
    emitted = output.getvalue()
    for private in (
        secret,
        "private-conversation",
        "private-file-reference",
        "private-file-name",
        "private-username",
        "private-contact",
        "private-response",
    ):
        assert private not in emitted
    assert json.loads(emitted)["response_chars"] == 123
    assert json.loads(emitted)["token_count"] == 5


def test_formatter_preserves_authoritative_log_fields(captured_logger):
    logger, output = captured_logger
    logger.info("Actual message", extra={"message": "spoofed", "level": "CRITICAL"})
    record = json.loads(output.getvalue())
    assert record["message"] == "Actual message"
    assert record["level"] == "INFO"


def test_bad_log_arguments_cannot_trigger_logging_raw_stderr_fallback(captured_logger, capsys):
    logger, output = captured_logger
    logger.error("Mismatched format %s %s", "private-unformatted-value")
    assert json.loads(output.getvalue())["message"] == "Log record omitted: formatting failed"
    assert "private-unformatted-value" not in output.getvalue() + capsys.readouterr().err


def test_extra_serialization_failure_cannot_print_original_record(captured_logger, capsys):
    class BrokenDiagnostic:
        def __str__(self):
            raise ValueError("private-formatting-error")

    logger, output = captured_logger
    logger.error("Diagnostic %s", "private-original-argument", extra={"diagnostic": BrokenDiagnostic()})
    emitted = output.getvalue() + capsys.readouterr().err
    assert "private-original-argument" not in emitted
    assert "private-formatting-error" not in emitted
    assert json.loads(output.getvalue())["message"] == "Log record omitted: formatting failed"


def test_non_secret_token_metrics_remain_observable():
    assert redact_log_text("max_output_tokens=1024 token_count=15") == "max_output_tokens=1024 token_count=15"


def test_urllib3_retry_warning_cannot_bypass_the_safe_json_sink(monkeypatch):
    output = io.StringIO()
    monkeypatch.setattr("sys.stderr", output)
    transport_logger = logging.getLogger("urllib3")
    child_logger = logging.getLogger("urllib3.connectionpool")
    application_logger = logging.getLogger("safe-transport-setup-test")
    for logger in (transport_logger, child_logger, application_logger):
        monkeypatch.setattr(logger, "handlers", [])
        monkeypatch.setattr(logger, "propagate", True)
        monkeypatch.setattr(logger, "level", logging.NOTSET)
    # This is urllib3's real import-time state, rather than an unrealistically empty logger.
    transport_logger.addHandler(logging.NullHandler())
    get_json_logger("safe-transport-setup-test", "INFO")
    child_logger.warning("Retrying request: %s", "/bot987654321:ABCDEFGHIJKLMNOPQRSTUVWXYZ_fake_token/sendMessage")
    emitted = output.getvalue()
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ_fake_token" not in emitted
    assert json.loads(emitted)["level"] == "WARNING"
    assert transport_logger.propagate is False


def test_telegram_update_summary_contains_only_allowlisted_metadata():
    update = {
        "update_id": 42,
        "message": {
            "message_id": 1,
            "text": "private message",
            "chat": {"id": -1001, "type": "supergroup", "title": "private group"},
            "from": {"id": 20, "first_name": "private person"},
            "contact": {"phone_number": "private-phone"},
            "photo": [{"file_id": "private-file"}],
            "reply_to_message": {"text": "private quote"},
        },
    }
    assert telegram_update_log_extra(update) == {
        "event_type": "message",
        "update_id": 42,
        "text_chars": 15,
        "photo_count": 1,
    }


def test_telegram_summary_does_not_copy_unknown_fields_or_untrusted_ids():
    assert telegram_update_log_extra({"update_id": "private-value", "private-key": {"text": "private"}}) == {
        "event_type": "unknown"
    }
    assert api_gateway_event_summary({"private-key": "private-value"}) == {"event_type": "unknown_dict", "key_count": 1}


def test_telegram_summary_counts_huge_text_without_serializing_it():
    extra = telegram_update_log_extra({"update_id": 99, "message": {"text": "x" * 500_000}})
    assert extra == {"event_type": "message", "update_id": 99, "text_chars": 500_000}


def test_llm_logging_contains_length_without_a_content_preview():
    assert llm_text_log_fields("private model output", max_preview=5) == {"response_chars": 20}
    assert llm_text_log_fields(None) == {"response_chars": 0}
