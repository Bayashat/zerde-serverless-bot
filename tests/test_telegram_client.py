import io
import json
import logging

import pytest
from services import telegram
from services.telegram import TelegramAPIError, TelegramClient, TelegramFileTooLargeError
from zerde_common.logger import JSONFormatter, ZerdeLoggerAdapter


def test_get_file_parses_telegram_result(monkeypatch):
    fake_http = _FakeHttp(
        [
            _Response(
                status=200,
                data=json.dumps({"ok": True, "result": {"file_id": "abc", "file_path": "photos/file.jpg"}}).encode(),
            )
        ]
    )
    monkeypatch.setattr(telegram, "http", fake_http)
    client = TelegramClient()

    result = client.get_file("abc")

    assert result["file_path"] == "photos/file.jpg"
    assert fake_http.requests[0]["method"] == "POST"
    assert fake_http.requests[0]["url"].endswith("/getFile")


def test_download_file_enforces_content_length(monkeypatch):
    fake_http = _FakeHttp([_Response(status=200, data=b"", headers={"Content-Length": "5"})])
    monkeypatch.setattr(telegram, "http", fake_http)
    client = TelegramClient()

    with pytest.raises(TelegramFileTooLargeError):
        client.download_file("photos/file.jpg", max_bytes=4)


def test_download_file_enforces_streamed_size(monkeypatch):
    fake_http = _FakeHttp([_Response(status=200, chunks=[b"12", b"345"])])
    monkeypatch.setattr(telegram, "http", fake_http)
    client = TelegramClient()

    with pytest.raises(TelegramFileTooLargeError):
        client.download_file("photos/file.jpg", max_bytes=4)


def test_download_file_raises_api_error_safely(monkeypatch):
    fake_http = _FakeHttp([_Response(status=404, data=b'{"ok":false,"description":"missing"}')])
    monkeypatch.setattr(telegram, "http", fake_http)
    client = TelegramClient()

    with pytest.raises(TelegramAPIError) as exc_info:
        client.download_file("photos/missing.jpg", max_bytes=1024)

    assert exc_info.value.status == 404


def test_telegram_api_error_preserves_body_for_classification_but_not_exception_output():
    body = '{"description":"private echoed text", "file_id":"private-file-id"}'
    error = TelegramAPIError(400, body)
    assert error.body == body
    assert error.status == 400
    for rendered in (str(error), repr(error)):
        assert "private echoed text" not in rendered
        assert "private-file-id" not in rendered
        assert "400" in rendered


def test_send_message_logs_status_and_response_size_only(monkeypatch):
    from unittest.mock import MagicMock

    body = b'{"description":"private-response-text"}'
    fake_http = _FakeHttp([_Response(status=400, data=body)])
    monkeypatch.setattr(telegram, "http", fake_http)
    logger = MagicMock()
    monkeypatch.setattr(telegram, "logger", logger)
    client = TelegramClient()

    with pytest.raises(TelegramAPIError):
        client.send_message(-100123, "private-outbound-text")

    extra = logger.error.call_args.kwargs["extra"]
    assert extra == {"chat_id": -100123, "status": 400, "response_chars": len(body)}
    assert "private-response-text" not in str(logger.mock_calls)
    assert "private-outbound-text" not in str(logger.mock_calls)


@pytest.mark.parametrize("download", [False, True])
def test_telegram_network_failures_are_redacted_at_actual_log_output(monkeypatch, download):
    from unittest.mock import MagicMock

    import urllib3

    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JSONFormatter())
    raw_logger = logging.Logger("telegram-network-test")
    raw_logger.addHandler(handler)
    logger = ZerdeLoggerAdapter(raw_logger, {})
    monkeypatch.setattr(telegram, "logger", logger)
    token = "987654321:ABCDEFGHIJKLMNOPQRSTUVWXYZ_fake_token"
    monkeypatch.setattr(telegram, "get_bot_token", lambda: token)

    def fail_request(method, url, **kwargs):
        raise urllib3.exceptions.MaxRetryError(None, url, reason=OSError("connection failed"))

    monkeypatch.setattr(telegram, "http", MagicMock(request=fail_request))
    client = TelegramClient()
    file_path = "documents/private-file-reference.pdf"
    message_text = "private-message-text"
    with pytest.raises(urllib3.exceptions.MaxRetryError):
        try:
            if download:
                client.download_file(file_path, max_bytes=1024)
            else:
                client.send_message(-100123, message_text)
        except urllib3.exceptions.MaxRetryError:
            logger.exception("Worker request failed")
            raise
    emitted = output.getvalue()
    assert token not in emitted
    assert "private-file-reference" not in emitted
    assert "private-message-text" not in emitted
    assert "MaxRetryError" in emitted
    assert "connection failed" in emitted


def test_set_message_reaction_posts_single_emoji(monkeypatch):
    fake_http = _FakeHttp([_Response(status=200, data=b'{"ok":true,"result":true}')])
    monkeypatch.setattr(telegram, "http", fake_http)
    client = TelegramClient()

    client.set_message_reaction(-100123, 11, "👍")

    request = fake_http.requests[0]
    payload = json.loads(request["body"])
    assert request["method"] == "POST"
    assert request["url"].endswith("/setMessageReaction")
    assert payload == {
        "chat_id": -100123,
        "message_id": 11,
        "reaction": [{"type": "emoji", "emoji": "👍"}],
    }


def test_get_me_caches_bot_identity(monkeypatch):
    fake_http = _FakeHttp(
        [_Response(status=200, data=b'{"ok":true,"result":{"id":123,"is_bot":true,"username":"zerde"}}')]
    )
    monkeypatch.setattr(telegram, "http", fake_http)
    client = TelegramClient()

    assert client.get_me()["id"] == 123
    assert client.get_me()["username"] == "zerde"
    assert len(fake_http.requests) == 1
    assert fake_http.requests[0]["url"].endswith("/getMe")


def test_ban_chat_member_posts_permanent_ban_without_until_date(monkeypatch):
    fake_http = _FakeHttp([_Response(status=200, data=b'{"ok":true,"result":true}')])
    monkeypatch.setattr(telegram, "http", fake_http)
    client = TelegramClient()

    client.ban_chat_member(-100123, 42)

    request = fake_http.requests[0]
    payload = json.loads(request["body"])
    assert request["method"] == "POST"
    assert request["url"].endswith("/banChatMember")
    assert payload == {"chat_id": -100123, "user_id": 42}


def test_delete_message_can_ignore_already_missing_message(monkeypatch):
    fake_http = _FakeHttp(
        [
            _Response(
                status=400,
                data=b'{"ok":false,"error_code":400,"description":"Bad Request: message to delete not found"}',
            )
        ]
    )
    monkeypatch.setattr(telegram, "http", fake_http)
    client = TelegramClient()

    client.delete_message(-100123, 42, ignore_not_found=True)

    assert fake_http.requests[0]["url"].endswith("/deleteMessage")


def test_delete_message_does_not_ignore_other_api_errors(monkeypatch):
    fake_http = _FakeHttp(
        [
            _Response(
                status=400,
                data=b'{"ok":false,"error_code":400,"description":"Bad Request: message cannot be deleted"}',
            )
        ]
    )
    monkeypatch.setattr(telegram, "http", fake_http)
    client = TelegramClient()

    with pytest.raises(TelegramAPIError):
        client.delete_message(-100123, 42, ignore_not_found=True)


class _Response:
    def __init__(self, *, status, data=b"", headers=None, chunks=None):
        self.status = status
        self.data = data
        self.headers = headers or {}
        self._chunks = chunks
        self.released = False

    def read(self, amount=None):
        return self.data if amount is None else self.data[:amount]

    def stream(self, chunk_size):
        yield from (self._chunks if self._chunks is not None else [self.data])

    def release_conn(self):
        self.released = True


class _FakeHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0)
