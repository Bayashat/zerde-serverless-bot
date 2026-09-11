import asyncio
import importlib.util
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import boto3
import httpx
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

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


def _deadline(seconds=60):
    return _load_news_module("news_deadline_test", "services/deadline.py").Deadline(seconds)


def _event(chats=None):
    return {
        "chat_ids": chats or ["-1001"],
        "lang": "zh",
        "scheduled_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


@pytest.fixture
def actual_table():
    with mock_aws():
        resource = boto3.resource(
            "dynamodb", region_name="eu-central-1", aws_access_key_id="fake", aws_secret_access_key="fake"
        )
        yield resource.create_table(
            TableName="news-test-stats",
            KeySchema=[{"AttributeName": "stat_key", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "stat_key", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )


@pytest.fixture
def actual_repo(actual_table):
    state = _load_news_module("news_delivery_state_test", "services/delivery_state.py")
    return state.NewsDeliveryRepository(actual_table)


def test_news_sanitize_html_converts_br_and_escapes_unknown_tags():
    telegram = _load_news_module("news_telegram_test", "services/telegram.py")

    result = telegram.sanitize_html(
        '<b>Title</b><br/>Body <script>alert(1)</script> <a href="https://example.com?a=1&b=2">Read</a>'
    )

    assert "<br" not in result
    assert "<b>Title</b>\nBody" in result
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in result
    assert '<a href="https://example.com?a=1&amp;b=2">Read</a>' in result


@pytest.mark.parametrize("mode", ["text", "photo"])
def test_news_sender_sanitizes_payload_and_requires_telegram_identity(monkeypatch, mode):
    telegram = _load_news_module("news_telegram_send_test", "services/telegram.py")
    requests = []

    async def fake_request(method, url, **kwargs):
        requests.append(kwargs["payload"])
        return 200, b'{"ok":true,"result":{"message_id":7,"chat":{"id":-1001}}}'

    monkeypatch.setattr(telegram, "request_bytes", fake_request)
    result = asyncio.run(
        telegram.TelegramSender("fake-token").send_step(
            "-1001",
            telegram.prepare_step("<b>Title</b><br>Body <foo>bad</foo>", "https://example.com/image.png"),
            mode,
            _deadline(),
        )
    )
    payload = requests[0]
    assert result.state == "SENT" and result.message_id == 7
    assert payload["parse_mode"] == "HTML"
    assert payload["caption" if mode == "photo" else "text"] == "<b>Title</b>\nBody &lt;foo&gt;bad&lt;/foo&gt;"


def test_news_sender_logs_http_failure_metadata_without_response_body(monkeypatch):
    telegram = _load_news_module("news_telegram_failure_test", "services/telegram.py")
    body = b'{"ok":false,"description":"private-provider-response"}'

    async def failure(*args, **kwargs):
        return 400, body

    monkeypatch.setattr(telegram, "request_bytes", failure)
    logger = MagicMock()
    monkeypatch.setattr(telegram, "logger", logger)
    result = asyncio.run(
        telegram.TelegramSender("fake-token").send_step("-1001", {"text": "private-message-text"}, "text", _deadline())
    )
    assert result.state == "REJECTED" and result.status == 400
    assert logger.warning.call_args.kwargs["extra"] == {"chat_id": "-1001", "status": 400, "response_chars": len(body)}
    assert "private-provider-response" not in str(logger.mock_calls)
    assert "private-message-text" not in str(logger.mock_calls)


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

            async def _generate(self, prompt, temperature, max_output_tokens, response_json_schema=None, *, deadline):
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

    selected = asyncio.run(stub.select_top_news(items, _deadline()))

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

    assert [item["index"] for item in asyncio.run(stub.select_top_news(items, _deadline()))] == [0, 1, 2]


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

    selected = asyncio.run(stub.select_top_news(items, _deadline()))

    assert [item["index"] for item in selected] == [0, 2, 3]


def test_news_digest_prompt_requires_fact_first_grounded_summary():
    stub = StubNewsAI().client
    article = _candidate(0, "thenewstack.io", score=4.0, chars=1400)
    article["full_text"] = "Sentry MCP attack affects Claude Code and Cursor through exposed DSN configuration."

    result = asyncio.run(stub.generate_digests_per_article([article], "zh", _deadline()))

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

    result = asyncio.run(stub.generate_digests_per_article([article], "zh", _deadline()))

    assert "A project page describes an open AI model." in result[0]
    assert '<a href="https://apertvs.ai/story-0">阅读全文</a>' in result[0]
    stub._generate.assert_not_called()


def test_digest_service_enriches_candidates_before_ai_selection(actual_repo):
    digest = _load_news_module("news_digest_service_test", "services/digest.py")
    events: list[str] = []

    class Fetcher:
        async def fetch_raw_news(self, deadline):
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

        async def fetch_deep_article_data(self, link, deadline):
            events.append(f"deep:{link}")
            return {
                "image_url": f"{link}/image.jpg",
                "full_text": "AWS Lambda AI API security developer architecture " * 35,
                "full_text_chars": 1800,
            }

    class AI:
        async def select_top_news(self, articles, deadline):
            events.append("select")
            assert all("full_text_chars" in article for article in articles)
            assert all("quality_score" in article for article in articles)
            return [{"index": 0, "category": "global_tech_ai", "score_reason": "best"}]

        async def generate_digests_per_article(self, articles, lang, deadline):
            events.append("digest")
            return ["<b>Digest</b>"]

    class Sender:
        async def send_step(self, chat_id, content, mode, deadline):
            events.append(f"send:{bool(content.get('image_url'))}")
            return SimpleNamespace(state="SENT", message_id=7)

    result = digest.DigestService(Fetcher(), AI(), Sender(), actual_repo).run(_event())

    assert result["statusCode"] == 200
    assert events.index("select") > max(i for i, event in enumerate(events) if event.startswith("deep:"))
    assert "digest" in events
    assert "send:True" in events


def _prepared(repo, event=None, steps=None):
    event = event or _event()
    state = _load_news_module("news_job_parse_test", "services/delivery_state.py")
    job = state.parse_job(event)
    owner, _ = repo.claim_manifest(job)
    telegram = _load_news_module("news_prepare_manifest_test", "services/telegram.py")
    contents = (
        steps
        if steps is not None
        else [{"text": "intro", "image_url": ""}, {"text": "article", "image_url": "https://example.com/image.png"}]
    )
    manifest = repo.freeze_manifest(
        job, owner, [telegram.prepare_step(step["text"], step.get("image_url", "")) for step in contents]
    )
    return event, job, manifest


class RecordingSender:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    async def send_step(self, chat_id, content, mode, deadline):
        self.calls.append((chat_id, content["text"], mode))
        if self.fail:
            result = self.fail(chat_id, content, mode)
            if result:
                return result
        return SimpleNamespace(state="SENT", message_id=100 + len(self.calls))


def _service(repo, sender):
    digest = _load_news_module("news_service_recovery_test", "services/digest.py")
    no_build = MagicMock(side_effect=AssertionError("Frozen news must not be generated again"))
    return digest.DigestService(no_build, no_build, sender, repo)


def test_partial_chat_retry_skips_successful_chats_and_their_already_sent_intro(actual_repo, monkeypatch):
    event, job, _ = _prepared(actual_repo, _event(["-1001", "-1002"]))
    sender = RecordingSender(
        lambda chat, content, mode: (
            SimpleNamespace(state="RETRYABLE", status=429, retry_after=1)
            if chat == "-1002" and content["text"] == "article"
            else None
        )
    )
    service = _service(actual_repo, sender)
    with pytest.raises(RuntimeError, match="1 chat"):
        service.run(event)
    assert actual_repo.get_delivery(job["job_id"], "-1001")["steps"][1]["state"] == "SENT"
    assert actual_repo.get_delivery(job["job_id"], "-1002")["steps"][0]["state"] == "SENT"
    sender.fail = None
    stamp = time.time()
    monkeypatch.setattr(time, "time", lambda: stamp + 2)
    result = service.run(event)
    assert result["statusCode"] == 200
    assert sender.calls.count(("-1001", "intro", "text")) == 1
    assert sender.calls.count(("-1001", "article", "photo")) == 1
    assert sender.calls.count(("-1002", "intro", "text")) == 1
    assert sender.calls.count(("-1002", "article", "photo")) == 2


def test_unknown_photo_never_falls_back_or_automatically_repeats(actual_repo):
    event, job, _ = _prepared(actual_repo)
    sender = RecordingSender(lambda chat, content, mode: SimpleNamespace(state="UNKNOWN") if mode == "photo" else None)
    service = _service(actual_repo, sender)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="incomplete"):
            service.run(event)
    row = actual_repo.get_delivery(job["job_id"], "-1001")
    assert row["steps"][1]["state"] == "UNKNOWN"
    assert sender.calls == [("-1001", "intro", "text"), ("-1001", "article", "photo")]


def test_definitively_rejected_photo_uses_one_durable_text_fallback(actual_repo):
    event, job, _ = _prepared(actual_repo)
    sender = RecordingSender(
        lambda chat, content, mode: (
            SimpleNamespace(state="REJECTED", status=400, retry_after=0) if mode == "photo" else None
        )
    )
    service = _service(actual_repo, sender)
    service.run(event)
    service.run(event)
    assert sender.calls == [("-1001", "intro", "text"), ("-1001", "article", "photo"), ("-1001", "article", "text")]
    assert actual_repo.get_delivery(job["job_id"], "-1001")["steps"][1]["mode"] == "text"


def test_acknowledged_send_followed_by_database_failure_becomes_unknown_and_does_not_repeat(actual_repo, monkeypatch):
    event, job, _ = _prepared(actual_repo)
    save = actual_repo.save_step

    def outage(row, owner, index, step):
        if step["state"] == "SENT":
            raise RuntimeError("synthetic DynamoDB outage after successful Telegram response")
        return save(row, owner, index, step)

    monkeypatch.setattr(actual_repo, "save_step", outage)
    sender = RecordingSender()
    service = _service(actual_repo, sender)
    with pytest.raises(RuntimeError):
        service.run(event)
    monkeypatch.setattr(actual_repo, "save_step", save)
    with pytest.raises(RuntimeError):
        service.run(event)
    assert sender.calls == [("-1001", "intro", "text")]
    assert actual_repo.get_delivery(job["job_id"], "-1001")["steps"][0]["state"] == "UNKNOWN"


def test_crash_before_response_leaves_unknown_attempt_and_no_ghost_success(actual_repo):
    event, job, _ = _prepared(actual_repo)

    class CrashingSender:
        async def send_step(self, *args):
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        _service(actual_repo, CrashingSender()).run(event)
    row = actual_repo.get_delivery(job["job_id"], "-1001")
    assert row["steps"][0]["state"] == "UNKNOWN" and "lease_owner" not in row


def test_manifest_lease_prevents_duplicate_generation_and_fences_a_late_owner(actual_repo, monkeypatch):
    state = _load_news_module("news_manifest_fence_test", "services/delivery_state.py")
    job = state.parse_job(_event())
    owner, _ = actual_repo.claim_manifest(job)
    with pytest.raises(RuntimeError, match="busy"):
        actual_repo.claim_manifest(job)
    stamp = time.time()
    monkeypatch.setattr(time, "time", lambda: stamp + 361)
    next_owner, _ = actual_repo.claim_manifest(job)
    with pytest.raises(ClientError):
        actual_repo.freeze_manifest(job, owner, [])
    manifest = actual_repo.freeze_manifest(job, next_owner, [{"text": "current", "image_url": ""}])
    assert actual_repo.claim_manifest(job) == (None, manifest)
    with pytest.raises(RuntimeError, match="identity changed"):
        actual_repo.claim_manifest({**job, "chat_ids": ["-999"]})


def test_delivery_lease_and_revision_fence_stale_writers(actual_repo, monkeypatch):
    _, job, manifest = _prepared(actual_repo)
    owner, row = actual_repo.claim_delivery(manifest, "-1001")
    stale = {**row, "steps": [dict(step) for step in row["steps"]]}
    step = {**row["steps"][0], "state": "UNKNOWN", "attempt_id": "attempt"}
    actual_repo.save_step(row, owner, 0, step)
    with pytest.raises(ClientError):
        actual_repo.save_step(stale, owner, 0, {**step, "state": "SENT"})
    stamp = time.time()
    monkeypatch.setattr(time, "time", lambda: stamp + 361)
    next_owner, current = actual_repo.claim_delivery(manifest, "-1001")
    with pytest.raises(ClientError):
        actual_repo.save_step(row, owner, 0, {**step, "state": "SENT"})
    actual_repo.release_delivery(row, owner)
    assert actual_repo.get_delivery(job["job_id"], "-1001")["lease_owner"] == next_owner
    actual_repo.release_delivery(current, next_owner)


@pytest.mark.parametrize(
    "mismatch",
    [
        {"content_hash": "wrong"},
        {"step_index": 1},
        {"attempt_id": "old"},
        {"expected_revision": 999},
        {"chat_id": "-1002"},
    ],
)
def test_unknown_repair_requires_exact_manifest_chat_step_attempt_and_revision(actual_repo, mismatch):
    event, job, manifest = _prepared(actual_repo)
    sender = RecordingSender(lambda *args: SimpleNamespace(state="UNKNOWN"))
    with pytest.raises(RuntimeError):
        _service(actual_repo, sender).run(event)
    row = actual_repo.get_delivery(job["job_id"], "-1001")
    repair = dict(
        job_id=job["job_id"],
        chat_id="-1001",
        content_hash=manifest["content_hash"],
        step_index=0,
        attempt_id=row["steps"][0]["attempt_id"],
        expected_revision=row["revision"],
        resolution="CONFIRM_SENT",
        message_id=321,
        note="Synthetic operator verification",
    )
    with pytest.raises(RuntimeError):
        actual_repo.repair_unknown(**{**repair, **mismatch})
    assert actual_repo.get_delivery(job["job_id"], "-1001") == row


@pytest.mark.parametrize("resolution", ["CONFIRM_SENT", "REOPEN"])
def test_explicit_unknown_repair_resumes_only_the_intended_step(actual_repo, resolution):
    event, job, manifest = _prepared(actual_repo)
    sender = RecordingSender(lambda *args: SimpleNamespace(state="UNKNOWN"))
    with pytest.raises(RuntimeError):
        _service(actual_repo, sender).run(event)
    row = actual_repo.get_delivery(job["job_id"], "-1001")
    repair = dict(
        job_id=job["job_id"],
        chat_id="-1001",
        content_hash=manifest["content_hash"],
        step_index=0,
        attempt_id=row["steps"][0]["attempt_id"],
        expected_revision=row["revision"],
        resolution=resolution,
        message_id=321,
        note="Synthetic operator verification",
    )
    actual_repo.repair_unknown(**repair)
    with pytest.raises(RuntimeError):
        actual_repo.repair_unknown(**repair)
    sender.fail = None
    _service(actual_repo, sender).run(event)
    assert sender.calls.count(("-1001", "intro", "text")) == (2 if resolution == "REOPEN" else 1)
    assert actual_repo.get_delivery(job["job_id"], "-1001")["steps"][1]["state"] == "SENT"


def test_original_scheduled_time_survives_midnight_and_separate_slots_do_not_collide(monkeypatch):
    state = _load_news_module("news_schedule_identity_test", "services/delivery_state.py")
    event = {"chat_ids": ["-1001"], "lang": "kk", "scheduled_at": "2026-09-10T18:59:00Z"}
    stamp = datetime.fromisoformat("2026-09-10T19:10:00+00:00").timestamp()
    monkeypatch.setattr(time, "time", lambda: stamp)
    original = state.parse_job(event)
    assert original["date"] == "2026-09-10"  # Almaty was still 23:59 at the scheduled event.
    assert original["job_id"] == state.parse_job(event)["job_id"]
    later = state.parse_job({**event, "scheduled_at": "2026-09-10T19:00:00Z"})
    assert later["date"] == "2026-09-11" and later["job_id"] != original["job_id"]
    assert state.parse_job({**event, "schedule_slot": "second"})["job_id"] != original["job_id"]


@pytest.mark.parametrize(
    "change",
    [
        {"scheduled_at": None},
        {"scheduled_at": "2026-09-10T12:00:00"},
        {"scheduled_at": "2000-01-01T00:00:00Z"},
        {"chat_ids": [123]},
        {"schedule_slot": "unexpected#delimiter"},
    ],
)
def test_invalid_or_old_scheduled_identity_fails_before_writing_or_sending(actual_repo, change):
    sender = RecordingSender()
    with pytest.raises(ValueError):
        _service(actual_repo, sender).run({**_event(), **change})
    assert actual_repo._table().scan()["Count"] == 0 and sender.calls == []


@pytest.mark.parametrize(
    "status,body",
    [
        (200, b'{"ok":true}'),
        (200, b'{"ok":true,"result":{"message_id":7,"chat":{"id":-999}}}'),
        (500, b'{"ok":false}'),
        (200, b"not-json"),
    ],
)
def test_telegram_missing_or_wrong_confirmation_is_unknown(monkeypatch, status, body):
    telegram = _load_news_module("news_bad_confirmation_test", "services/telegram.py")
    calls = []

    async def response(*args, **kwargs):
        calls.append(1)
        return status, body

    monkeypatch.setattr(telegram, "request_bytes", response)
    result = asyncio.run(
        telegram.TelegramSender("fake-token").send_step("-1001", {"text": "synthetic"}, "text", _deadline())
    )
    assert result.state == "UNKNOWN" and len(calls) == 1


def test_45_slow_articles_are_cancelled_as_a_batch_with_no_thread_or_task_left_running(actual_repo):
    digest = _load_news_module("news_slow_enrichment_test", "services/digest.py")
    active = [0]
    peak = [0]

    class SlowFetcher:
        async def fetch_deep_article_data(self, link, deadline):
            active[0] += 1
            peak[0] = max(peak[0], active[0])
            try:
                await asyncio.sleep(60)
            finally:
                active[0] -= 1

    candidates = [_candidate(i, f"source{i}.example", score=4) for i in range(45)]
    started = time.monotonic()
    output = asyncio.run(
        digest.DigestService(SlowFetcher(), None, None, actual_repo)._enrich_news_candidates(
            candidates, _deadline(0.03)
        )
    )
    assert len(output) == 45 and peak[0] == 5 and active[0] == 0
    assert time.monotonic() - started < 0.7


def test_http_deadline_cancels_slow_stream_and_closes_it():
    deadline_module = _load_news_module("news_real_http_deadline_test", "services/deadline.py")

    class SlowStream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b"begin"
            await asyncio.sleep(60)

        async def aclose(self):
            self.closed = True

    stream = SlowStream()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        asyncio.run(
            deadline_module.request_bytes(
                "GET", "https://synthetic.invalid", deadline=_deadline(1), cap=0.03, max_bytes=100, transport=transport
            )
        )
    assert stream.closed and time.monotonic() - started < 0.7


def test_http_deadline_covers_waiting_for_connection_or_headers():
    deadline_module = _load_news_module("news_connect_deadline_test", "services/deadline.py")
    cancelled = []

    async def stalled(request):
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.append(True)

    with pytest.raises(TimeoutError):
        asyncio.run(
            deadline_module.request_bytes(
                "GET",
                "https://synthetic.invalid",
                deadline=_deadline(1),
                cap=0.03,
                max_bytes=100,
                transport=httpx.MockTransport(stalled),
            )
        )
    assert cancelled == [True]


def test_actual_gemini_sdk_async_timeout_closes_slow_response_without_retry(monkeypatch):
    ai = _load_news_module("news_gemini_deadline_test", "services/ai_client.py")

    class SlowStream(httpx.AsyncByteStream):
        closed = False
        started = False

        async def __aiter__(self):
            self.started = True
            yield b'{"candidates":['
            await asyncio.sleep(60)

        async def aclose(self):
            self.closed = True

    stream = SlowStream()
    calls = []

    def route(request):
        calls.append(request)
        return httpx.Response(200, stream=stream)

    real_client = ai.genai.Client
    real_http_client = ai.bounded_async_client
    opened_clients = []

    def test_http_client(**kwargs):
        client = real_http_client(**kwargs, transport=httpx.MockTransport(route))
        opened_clients.append(client)
        return client

    monkeypatch.setattr(ai, "bounded_async_client", test_http_client)

    def test_client(**kwargs):
        assert kwargs["http_options"].retry_options.attempts == 1
        return real_client(**kwargs)

    monkeypatch.setattr(ai.genai, "Client", test_client)
    client = ai.GeminiNewsClient("synthetic-key", "gemini-2.5-flash")
    with pytest.raises(ai.ProviderTransportError):
        asyncio.run(client._generate("synthetic", 0.1, 30, deadline=_deadline(0.5)))
    assert stream.started and stream.closed and len(calls) == 1
    assert opened_clients[0].is_closed


def test_context_budget_exhaustion_is_an_exception_not_status_500_or_empty_broadcast(actual_repo):
    sender = RecordingSender()
    context = SimpleNamespace(get_remaining_time_in_millis=lambda: 10000)
    with pytest.raises(RuntimeError, match="budget"):
        _service(actual_repo, sender).run(_event(), context)
    assert actual_repo._table().scan()["Count"] == 0 and sender.calls == []


class BuildFetcher:
    def __init__(self, *, empty=False):
        self.calls = 0
        self.empty = empty

    async def fetch_raw_news(self, deadline):
        self.calls += 1
        return [] if self.empty else [_candidate(0, "synthetic.example", score=4)]

    async def fetch_deep_article_data(self, url, deadline):
        return {"full_text": "synthetic source " * 50, "full_text_chars": 850, "image_url": ""}


class BuildAI:
    def __init__(self):
        self.calls = 0

    async def select_top_news(self, articles, deadline):
        return [{"index": 0}]

    async def generate_digests_per_article(self, articles, lang, deadline):
        self.calls += 1
        return ["<b>Frozen synthetic news</b>"]


def test_successful_no_fresh_news_is_persisted_without_empty_broadcast(actual_repo):
    digest = _load_news_module("news_empty_success_test", "services/digest.py")
    fetcher = BuildFetcher(empty=True)
    ai = BuildAI()
    sender = RecordingSender()
    service = digest.DigestService(fetcher, ai, sender, actual_repo)
    event = _event()
    assert service.run(event)["body"] == "No fresh news"
    service.run(event)
    assert fetcher.calls == 1 and ai.calls == 0 and sender.calls == []


def test_failed_generation_releases_manifest_and_raises_without_empty_delivery(actual_repo):
    digest = _load_news_module("news_generation_failure_test", "services/digest.py")

    class FailedAI(BuildAI):
        async def generate_digests_per_article(self, articles, lang, deadline):
            raise RuntimeError("synthetic generation failure")

    sender = RecordingSender()
    with pytest.raises(RuntimeError, match="generation failure"):
        digest.DigestService(BuildFetcher(), FailedAI(), sender, actual_repo).run(_event())
    items = actual_repo._table().scan()["Items"]
    assert len(items) == 1 and items[0]["state"] == "BUILDING" and "lease_owner" not in items[0]
    assert "content_hash" not in items[0] and sender.calls == []


def test_lost_manifest_write_acknowledgement_reuses_frozen_content_without_more_models(actual_repo, monkeypatch):
    digest = _load_news_module("news_manifest_lost_ack_test", "services/digest.py")
    actual_freeze = actual_repo.freeze_manifest

    def lost_ack(*args):
        actual_freeze(*args)
        raise RuntimeError("synthetic lost manifest acknowledgement")

    monkeypatch.setattr(actual_repo, "freeze_manifest", lost_ack)
    fetcher, ai, sender = BuildFetcher(), BuildAI(), RecordingSender()
    service = digest.DigestService(fetcher, ai, sender, actual_repo)
    event = _event()
    with pytest.raises(RuntimeError, match="lost manifest"):
        service.run(event)
    monkeypatch.setattr(actual_repo, "freeze_manifest", actual_freeze)
    service.run(event)
    assert fetcher.calls == 1 and ai.calls == 1 and len(sender.calls) == 2


def test_deadline_after_one_confirmed_step_preserves_receipt_for_next_invocation(actual_repo):
    event, job, _ = _prepared(actual_repo)

    class BudgetExpiredSender(RecordingSender):
        async def send_step(self, chat_id, content, mode, deadline):
            result = await super().send_step(chat_id, content, mode, deadline)
            deadline.expires = time.monotonic() - 1
            return result

    first = BudgetExpiredSender()
    with pytest.raises(RuntimeError, match="deadline"):
        _service(actual_repo, first).run(event)
    row = actual_repo.get_delivery(job["job_id"], "-1001")
    assert [step["state"] for step in row["steps"]] == ["SENT", "PENDING"]
    retry = RecordingSender()
    _service(actual_repo, retry).run(event)
    assert retry.calls == [("-1001", "article", "photo")]


def test_expired_unknown_can_be_confirmed_but_cannot_be_reopened(actual_repo, monkeypatch):
    event, job, manifest = _prepared(actual_repo)
    with pytest.raises(RuntimeError):
        _service(actual_repo, RecordingSender(lambda *args: SimpleNamespace(state="UNKNOWN"))).run(event)
    row = actual_repo.get_delivery(job["job_id"], "-1001")
    repair = dict(
        job_id=job["job_id"],
        chat_id="-1001",
        content_hash=manifest["content_hash"],
        step_index=0,
        attempt_id=row["steps"][0]["attempt_id"],
        expected_revision=row["revision"],
        note="Synthetic operator verification",
        message_id=321,
    )
    stamp = time.time()
    monkeypatch.setattr(time, "time", lambda: stamp + 37 * 3600)
    with pytest.raises(RuntimeError, match="Expired"):
        actual_repo.repair_unknown(**repair, resolution="REOPEN")
    actual_repo.repair_unknown(**repair, resolution="CONFIRM_SENT")
    assert actual_repo.get_delivery(job["job_id"], "-1001")["steps"][0]["state"] == "SENT"


def test_frozen_payload_variants_are_sent_verbatim_after_formatter_changes(monkeypatch):
    telegram = _load_news_module("news_frozen_format_test", "services/telegram.py")
    step = telegram.prepare_step("<b>Synthetic</b><br>Evidence", "https://synthetic.invalid/image")
    monkeypatch.setattr(
        telegram, "sanitize_html", MagicMock(side_effect=AssertionError("Frozen content must not reformat"))
    )
    payloads = []

    async def request(*args, **kwargs):
        payloads.append(kwargs["payload"])
        return 200, b'{"ok":true,"result":{"message_id":7,"chat":{"id":-1001}}}'

    monkeypatch.setattr(telegram, "request_bytes", request)
    sender = telegram.TelegramSender("synthetic-key")
    assert asyncio.run(sender.send_step("-1001", step, "photo", _deadline())).state == "SENT"
    assert asyncio.run(sender.send_step("-1001", step, "text", _deadline())).state == "SENT"
    assert payloads[0]["caption"] == step["caption"] and payloads[1]["text"] == step["text"]
