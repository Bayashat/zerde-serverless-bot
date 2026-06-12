import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEWS_ROOT = ROOT / "src" / "news"


def _load_news_module(name: str, relative_path: str):
    sys.path.insert(0, str(NEWS_ROOT))
    try:
        spec = importlib.util.spec_from_file_location(name, NEWS_ROOT / relative_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


class FakeResponse:
    def __init__(self, status: int = 200, data: bytes = b'{"ok":true}') -> None:
        self.status = status
        self.data = data


class FakeHttp:
    def __init__(self) -> None:
        self.requests: list[dict] = []

    def request(self, method: str, url: str, **kwargs):
        self.requests.append({"method": method, "url": url, **kwargs})
        return FakeResponse()


def test_news_sanitize_html_converts_br_and_escapes_unknown_tags():
    telegram = _load_news_module("news_telegram_test", "services/telegram.py")

    result = telegram.sanitize_html(
        '<b>Title</b><br/>Body <script>alert(1)</script> <a href="https://example.com?a=1&b=2">Read</a>'
    )

    assert "<br" not in result
    assert "<b>Title</b>\nBody" in result
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in result
    assert '<a href="https://example.com?a=1&amp;b=2">Read</a>' in result


def test_news_sender_sanitizes_send_message_payload(monkeypatch):
    telegram = _load_news_module("news_telegram_send_test", "services/telegram.py")
    fake_http = FakeHttp()
    monkeypatch.setattr(telegram, "http", fake_http)

    ok, _ = telegram.TelegramSender("token").send_message("chat", "<b>Title</b><br>Body <foo>bad</foo>")

    payload = json.loads(fake_http.requests[0]["body"].decode("utf-8"))
    assert ok is True
    assert payload["parse_mode"] == "HTML"
    assert payload["text"] == "<b>Title</b>\nBody &lt;foo&gt;bad&lt;/foo&gt;"


def test_news_sender_sanitizes_photo_caption_payload(monkeypatch):
    telegram = _load_news_module("news_telegram_photo_test", "services/telegram.py")
    fake_http = FakeHttp()
    monkeypatch.setattr(telegram, "http", fake_http)

    ok = telegram.TelegramSender("token").send_message_with_photo(
        "chat",
        "<b>Title</b><br><i>Body</i>",
        "https://example.com/image.png",
    )

    payload = json.loads(fake_http.requests[0]["body"])
    assert ok is True
    assert payload["parse_mode"] == "HTML"
    assert payload["caption"] == "<b>Title</b>\n<i>Body</i>"


def test_news_fetcher_normalizes_rss_urls_with_whitespace():
    news_fetcher = _load_news_module("news_fetcher_test", "services/news_fetcher.py")

    assert (
        news_fetcher.normalize_url(
            "https://aws.amazon.com/about-aws/whats-new/2026/06/cloudwatch-supports infrastructure-logs/"
        )
        == "https://aws.amazon.com/about-aws/whats-new/2026/06/cloudwatch-supports-infrastructure-logs/"
    )
    assert news_fetcher.normalize_url("https://example.com/a path/?q=hello world") == (
        "https://example.com/a%20path/?q=hello%20world"
    )
