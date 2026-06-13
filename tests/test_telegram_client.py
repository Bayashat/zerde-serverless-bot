import json

import pytest
from services import telegram
from services.telegram import TelegramAPIError, TelegramClient, TelegramFileTooLargeError


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
