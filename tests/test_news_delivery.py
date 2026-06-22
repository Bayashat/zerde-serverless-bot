import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
NEWS_ROOT = ROOT / "src" / "news"


def _load_news_module(name: str, relative_path: str):
    shadowed_prefixes = ("core", "services")
    saved_modules = {
        module_name: module
        for module_name, module in sys.modules.items()
        if module_name in shadowed_prefixes
        or module_name.startswith(tuple(f"{prefix}." for prefix in shadowed_prefixes))
    }
    for module_name in saved_modules:
        sys.modules.pop(module_name, None)

    sys.path.insert(0, str(NEWS_ROOT))
    try:
        spec = importlib.util.spec_from_file_location(name, NEWS_ROOT / relative_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)
        for module_name in list(sys.modules):
            if module_name in shadowed_prefixes or module_name.startswith(
                tuple(f"{prefix}." for prefix in shadowed_prefixes)
            ):
                sys.modules.pop(module_name, None)
        sys.modules.update(saved_modules)


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


class StubNewsAI:
    def __init__(self, response: dict | None = None) -> None:
        ai_client = _load_news_module("news_ai_client_base_test", "services/ai_client.py")

        class _Client(ai_client.NewsAIClientBase):
            def __init__(self, payload: dict | None) -> None:
                self.payload = payload or {"top_news": []}
                self.prompts: list[str] = []

            def _generate(self, prompt, temperature, max_output_tokens, response_json_schema=None):
                self.prompts.append(prompt)
                if "digest" in str(response_json_schema):
                    return {
                        "digest": '<b>Fact title</b>\n\nConcrete fact summary.\n\n<a href="https://x.test">阅读全文</a>'
                    }
                return self.payload

        self.client = _Client(response)


def _candidate(
    index: int,
    domain: str,
    *,
    score: float,
    region: str = "global",
    image: bool = True,
    chars: int = 1200,
) -> dict:
    return {
        "index": index,
        "title": f"Story {index} about AWS Lambda and AI agents",
        "summary": "Developers get a concrete API change.",
        "link": f"https://{domain}/story-{index}",
        "domain": domain,
        "source_region": region,
        "image_url": "https://images.test/a.jpg" if image else "",
        "full_text": "AWS Lambda AI API security developer architecture " * 40,
        "full_text_chars": chars,
        "quality_score": score,
        "quality_reasons": ["test"],
    }


def test_news_selection_treats_weak_kz_as_soft_bonus_not_quota():
    stub = StubNewsAI(
        {
            "top_news": [
                {"index": 1, "category": "kz_or_regional", "score_reason": "local"},
                {"index": 0, "category": "global_tech_ai", "score_reason": "global"},
                {"index": 2, "category": "hardcore_engineering", "score_reason": "engineering"},
            ]
        }
    ).client
    items = [
        _candidate(0, "aws.amazon.com", score=5.0),
        _candidate(1, "digitalbusiness.kz", score=0.2, region="kz", chars=80),
        _candidate(2, "thenewstack.io", score=4.3),
        _candidate(3, "cloudflare.com", score=3.9),
    ]

    selected = stub.select_top_news(items)

    assert [item["index"] for item in selected] == [0, 2, 3]


def test_news_selection_allows_major_no_image_article():
    stub = StubNewsAI(
        {
            "top_news": [
                {"index": 0, "category": "hardcore_engineering", "score_reason": "major but no image"},
                {"index": 1, "category": "global_tech_ai", "score_reason": "ai"},
                {"index": 2, "category": "other_high_signal", "score_reason": "security"},
            ]
        }
    ).client
    items = [
        _candidate(0, "engineering.example", score=5.8, image=False, chars=2200),
        _candidate(1, "ai.example", score=4.0),
        _candidate(2, "security.example", score=3.5),
    ]

    assert [item["index"] for item in stub.select_top_news(items)] == [0, 1, 2]


def test_news_selection_repairs_duplicate_domains_invalid_indices_and_short_lists():
    stub = StubNewsAI(
        {
            "top_news": [
                {"index": 0, "category": "global_tech_ai", "score_reason": "first"},
                {"index": 1, "category": "hardcore_engineering", "score_reason": "same domain"},
                {"index": 99, "category": "other_high_signal", "score_reason": "invalid"},
            ]
        }
    ).client
    items = [
        _candidate(0, "example.com", score=5.0),
        _candidate(1, "example.com", score=4.8),
        _candidate(2, "unique.dev", score=4.4),
        _candidate(3, "another.dev", score=4.0),
    ]

    selected = stub.select_top_news(items)

    assert [item["index"] for item in selected] == [0, 2, 3]


def test_news_digest_prompt_requires_fact_first_grounded_summary():
    stub = StubNewsAI().client
    article = _candidate(0, "thenewstack.io", score=4.0, chars=1400)
    article["full_text"] = "Sentry MCP attack affects Claude Code and Cursor through exposed DSN configuration."

    result = stub.generate_digests_per_article([article], "zh")

    assert result[0].startswith("<b>Fact title</b>")
    prompt = stub.prompts[0]
    assert "based ONLY on the provided title, source summary, and full_text" in prompt
    assert "Do NOT invent details or write generic hype" in prompt
    assert "new cornerstone" in prompt


def test_news_digest_uses_conservative_fallback_for_thin_article_text():
    stub = StubNewsAI().client
    stub._generate = MagicMock(side_effect=AssertionError("thin articles should not call the LLM"))
    article = _candidate(0, "apertvs.ai", score=1.8, chars=120)
    article["full_text"] = "Short page."
    article["summary"] = "A project page describes an open AI model."

    result = stub.generate_digests_per_article([article], "zh")

    assert "A project page describes an open AI model." in result[0]
    assert '<a href="https://apertvs.ai/story-0">阅读全文</a>' in result[0]
    stub._generate.assert_not_called()


def test_digest_service_enriches_candidates_before_ai_selection():
    digest = _load_news_module("news_digest_service_test", "services/digest.py")
    events: list[str] = []

    class Fetcher:
        def fetch_raw_news(self):
            return [
                {
                    "title": "AWS Lambda adds AI agent tracing",
                    "link": "https://aws.amazon.com/story",
                    "summary": "Developers get tracing for agents.",
                },
                {
                    "title": "Kazakhstan startup builds cloud security tool",
                    "link": "https://digitalbusiness.kz/story",
                    "summary": "A local startup ships a developer security tool.",
                },
                {
                    "title": "Sentry MCP issue affects Cursor",
                    "link": "https://thenewstack.io/story",
                    "summary": "Security issue for AI coding tools.",
                },
            ]

        def fetch_deep_article_data(self, link):
            events.append(f"deep:{link}")
            return {
                "image_url": f"{link}/image.jpg",
                "full_text": "AWS Lambda AI API security developer architecture " * 35,
                "full_text_chars": 1800,
            }

    class AI:
        def select_top_news(self, articles):
            events.append("select")
            assert all("full_text_chars" in article for article in articles)
            assert all("quality_score" in article for article in articles)
            return [{"index": 0, "category": "global_tech_ai", "score_reason": "best"}]

        def generate_digests_per_article(self, articles, lang):
            events.append("digest")
            return ["<b>Digest</b>"]

    class Sender:
        def send_message(self, chat_id, text):
            return True, 200

        def send_message_with_photo(self, chat_id, message, image_url):
            events.append(f"send:{bool(image_url)}")
            return True

    result = digest.DigestService(Fetcher(), AI(), Sender()).run({"chat_ids": ["chat"], "lang": "zh"})

    assert result["statusCode"] == 200
    assert events.index("select") > max(i for i, event in enumerate(events) if event.startswith("deep:"))
    assert "digest" in events
    assert "send:True" in events
