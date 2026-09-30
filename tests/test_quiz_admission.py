"""Local simulated AWS/HTTP faults; no real model, AWS or Telegram actions."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from botocore.exceptions import ClientError
from google import genai
from google.genai import types

from tests import quiz_support as qs

quiz_env = qs.quiz_env
QuotaUnavailable = qs.rate_module.QuizQuotaUnavailable
CHAT = "-100123"
KEY = {"PK": "QUIZ_GEMINI_RPD#2026-09-29", "SK": "LATEST"}


def counter(env):
    repo = qs.rate_module.QuizRateLimitRepository.__new__(qs.rate_module.QuizRateLimitRepository)
    repo._table = env.table
    repo.rpd_limit = 5
    repo._today_pt = lambda: "2026-09-29"
    return repo


def conditional_error():
    return ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem")


def test_missing_counter_initializes_once_and_keeps_original_day_and_ttl(quiz_env):
    repo = counter(quiz_env)
    assert repo.get_today_count() == 0
    assert repo.increment_and_check() == (1, True)
    old = quiz_env.table.get_item(Key=KEY)["Item"]
    repo._today_pt = lambda: "2026-09-30"
    assert repo.increment_and_check() == (1, True)
    assert quiz_env.table.get_item(Key=KEY)["Item"] == old
    assert old["ttl"] == 1790838000  # Pacific midnight + 48h; unchanged counter contract.


@pytest.mark.parametrize(
    "attrs",
    [{}, {"request_count": True}, {"request_count": "1"}, {"request_count": -1}, {"request_count": Decimal("1.5")}],
)
def test_invalid_existing_counter_is_never_repaired_into_a_permit(quiz_env, attrs):
    repo = counter(quiz_env)
    quiz_env.table.put_item(Item={**KEY, **attrs})
    before = quiz_env.table.get_item(Key=KEY)["Item"]
    with pytest.raises(QuotaUnavailable):
        repo.increment_and_check()
    with pytest.raises(QuotaUnavailable):
        repo.get_today_count()
    assert quiz_env.table.get_item(Key=KEY)["Item"] == before


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), 1.5, None])
def test_unstorable_or_corrupt_numbers_do_not_reach_writer(quiz_env, value):
    repo = counter(quiz_env)
    repo._table = Mock()
    repo._table.get_item.return_value = {"Item": {**KEY, "request_count": value}}
    with pytest.raises(QuotaUnavailable):
        repo.increment_and_check()
    repo._table.update_item.assert_not_called()


def test_valid_decimal_and_concurrent_cas_cannot_duplicate_last_permit(quiz_env):
    repo = counter(quiz_env)
    quiz_env.table.put_item(Item={**KEY, "request_count": Decimal(4)})

    def attempt(_):
        try:
            return repo.increment_and_check()[1]
        except QuotaUnavailable:
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(attempt, range(4))) == 1
    assert repo.get_today_count() >= 5


def test_contention_is_bounded_and_never_fabricates_permission(quiz_env):
    repo = counter(quiz_env)
    repo._table = Mock()
    repo._table.get_item.return_value = {}
    repo._table.update_item.side_effect = conditional_error()
    with pytest.raises(QuotaUnavailable, match="contention"):
        repo.increment_and_check()
    assert repo._table.update_item.call_count == repo._table.get_item.call_count == 3


@pytest.mark.parametrize("operation", ["get_item", "update_item"])
@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("secret source"),
        ClientError({"Error": {"Code": "AccessDeniedException"}}, "Read"),
        ClientError({"Error": {"Code": "ProvisionedThroughputExceededException"}}, "Write"),
    ],
)
def test_dependency_failures_never_report_zero_or_permission(quiz_env, operation, error):
    repo = counter(quiz_env)
    repo._table = Mock()
    repo._table.get_item.return_value = {}
    getattr(repo._table, operation).side_effect = error
    with pytest.raises(QuotaUnavailable) as exc:
        repo.increment_and_check()
    assert "secret" not in str(exc.value)
    assert getattr(repo._table, operation).call_count == 1


@pytest.mark.parametrize(
    "response",
    [None, {}, {"Attributes": {}}, {"Attributes": {"request_count": 0}}, {"Attributes": {"request_count": 2}}],
)
def test_uncertain_write_response_never_grants_or_refunds(quiz_env, response):
    repo = counter(quiz_env)
    original = repo._table.update_item

    def lose_response(**kwargs):
        original(**kwargs)
        return response

    repo._table.update_item = lose_response
    with pytest.raises(QuotaUnavailable):
        repo.increment_and_check()
    assert repo.get_today_count() == 1


def gemini(monkeypatch, replies, admissions):
    module = qs.provider_module
    provider = module.GeminiQuizProvider.__new__(module.GeminiQuizProvider)
    provider._model = "gemini-3.1-flash-lite"
    provider._rate_repo = Mock(rpd_limit=5)
    order = []

    def admit():
        order.append("admit")
        result = admissions.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def generate(**kwargs):
        order.append("network")
        assert kwargs["config"].http_options.retry_options.attempts == 1
        result = replies.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    provider._rate_repo.increment_and_check.side_effect = admit
    provider._client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    return provider, order


def busy():
    return qs.provider_module.genai_errors.ServerError(503, {"error": {"message": "PRIVATE MODEL TEXT"}})


def response():
    return SimpleNamespace(
        text='{"question":"ok"}',
        usage_metadata=SimpleNamespace(prompt_token_count=12, candidates_token_count=7, total_token_count=25),
    )


def test_every_application_retry_is_admitted_before_network(monkeypatch):
    provider, order = gemini(monkeypatch, [busy(), response()], [(1, True), (2, True)])
    assert provider.generate_json("PRIVATE PROMPT", interactive=True) == {"question": "ok"}
    assert order == ["admit", "network", "admit", "network"]


@pytest.mark.parametrize("second", [QuotaUnavailable("admission unavailable"), (6, False)])
def test_second_admission_failure_stops_network_and_only_true_limit_can_fallback(monkeypatch, second):
    provider, order = gemini(monkeypatch, [busy()], [(5, True), second])
    fallback = Mock()
    fallback.generate_json.return_value = {"question": "fallback"}
    chain = qs.provider_module.FallbackProvider([provider, fallback])
    if isinstance(second, Exception):
        with pytest.raises(QuotaUnavailable):
            chain.generate_json("prompt", interactive=True)
        fallback.generate_json.assert_not_called()
    else:
        assert chain.generate_json("prompt", interactive=True) == {"question": "fallback"}
    assert order == ["admit", "network", "admit"]


def test_unknown_read_only_status_is_not_full_allowance(monkeypatch):
    provider, _ = gemini(monkeypatch, [], [])
    provider._rate_repo.get_today_count.side_effect = QuotaUnavailable()
    assert provider.get_rpd_status() == (None, 5)


def test_locked_real_sdk_makes_one_http_attempt_per_explicit_call(monkeypatch):
    calls = []

    def route(request):
        calls.append(request)
        return httpx.Response(503, json={"error": {"code": 503, "message": "synthetic busy"}})

    http_client = httpx.Client(transport=httpx.MockTransport(route))
    client = genai.Client(api_key="synthetic-key", http_options=types.HttpOptions(httpx_client=http_client))
    provider, order = gemini(monkeypatch, [], [(1, True), (2, True)])
    provider._client = client
    try:
        with pytest.raises(qs.provider_module.ProviderTransportError):
            provider.generate_json("synthetic", interactive=True)
        assert len(calls) == 2
        assert order == ["admit", "admit"]
    finally:
        client.close()
        http_client.close()


def actual_generator(provider):
    return qs.generator_module.QuizGenerator(provider)


@pytest.mark.parametrize("translate", [False, True])
def test_real_generator_propagates_local_admission_without_provider_fallback(translate):
    primary, secondary = Mock(), Mock()
    primary.generate_json.side_effect = QuotaUnavailable()
    generator = actual_generator(qs.provider_module.FallbackProvider([primary, secondary]))
    with pytest.raises(QuotaUnavailable):
        if translate:
            generator.translate_question(qs.question(), "ru")
        else:
            generator.generate_question("python", "ru")
    secondary.generate_json.assert_not_called()


def test_original_publication_recovers_same_generation_after_quota_failure(quiz_env):
    env = quiz_env
    provider = Mock()
    provider.generate_json.side_effect = QuotaUnavailable()
    env.svc._generator = actual_generator(provider)
    result = env.svc.process_on_demand_quiz(CHAT, "ru", "python", "easy", request_id=99)
    assert result == {
        "status": "error",
        "reason": "quiz admission unavailable",
        "retryable": True,
        "feedback_code": "queued",
    }
    key = env.repo.publication_key(CHAT, "REQUEST#99")
    row = env.repo._publication_read(key)
    assert row["state"] == "GENERATING" and row["lease_until"] == 0
    assert row["reason"] == "quota_unavailable"
    outbox = {"PK": "QUIZ_PUBLICATION_OUTBOX", "SK": f"{CHAT}#REQUEST#99"}
    assert env.repo._publication_read(outbox)["next_attempt_at"] == 0
    assert not env.sent
    # Recovery uses the same owner; fake model only supplies a valid question on retry.
    env.svc._generator = Mock()
    env.svc._generator.generate_question.return_value = qs.question()
    assert env.svc.recover_publications()["recovered"] == 1
    done = env.repo._publication_read(key)
    assert done["generation"] == row["generation"] and done["intent"] == row["intent"]
    assert done["state"] == "DONE" and len(env.sent) == 1
    assert env.repo._publication_read(outbox) == {}
    assert env.svc.recover_publications()["recovered"] == 0
    assert len(env.sent) == 1


@pytest.mark.parametrize("submitted", [False, True])
def test_failure_transition_database_error_keeps_existing_recovery(quiz_env, monkeypatch, submitted):
    env = quiz_env
    env.svc._generator.generate_question.side_effect = QuotaUnavailable()
    original = env.repo._publication_transaction
    calls = 0

    def fail(operations):
        nonlocal calls
        calls += 1
        if calls == 2:
            if submitted:
                original(operations)
            raise TimeoutError("synthetic uncertain database result")
        return original(operations)

    monkeypatch.setattr(env.repo, "_publication_transaction", fail)
    with pytest.raises(TimeoutError):
        env.svc.process_on_demand_quiz_with_feedback(CHAT, "en", "python", "medium", reply_to_message_id=90)
    env.svc._sender.send_message.assert_not_called()
    key = env.repo.publication_key(CHAT, "REQUEST#90")
    row = env.repo._publication_read(key)
    assert row["state"] == "GENERATING" and not env.sent
    assert bool(row["lease_until"]) is not submitted
    monkeypatch.setattr(env.repo, "_publication_transaction", original)
    env.svc._generator.generate_question.side_effect = None
    env.clock.now += 331
    assert env.svc.recover_publications()["recovered"] == 1
    assert env.repo._publication_read(key)["generation"] == row["generation"] and len(env.sent) == 1


def test_daily_quota_failure_does_not_try_second_category(quiz_env, monkeypatch):
    env = quiz_env
    provider = Mock()
    provider.generate_json.side_effect = QuotaUnavailable()
    env.svc._generator = actual_generator(provider)
    monkeypatch.setattr(env.svc, "_pick_category_for_chat", lambda *args: ("programming", ["database"]))
    monkeypatch.setattr(env.svc, "_pick_ai_bank_question_for_chat", lambda *args: None)
    result = env.svc.process_daily_quiz([CHAT], "ru", scheduled_at=env.clock.now)
    assert result["status"] == "error"
    assert provider.generate_json.call_count == 1 and not env.sent


@pytest.mark.parametrize("quota_error", [True, False])
def test_bank_translation_only_stops_on_local_quota_failure(quiz_env, monkeypatch, quota_error):
    env = quiz_env
    provider = Mock()
    provider.generate_json.side_effect = (
        QuotaUnavailable() if quota_error else qs.provider_module.ProviderResponseError("synthetic")
    )
    env.svc._generator = actual_generator(provider)
    monkeypatch.setattr(env.svc, "_pick_banked_question_for_genquiz", lambda *args: (qs.question(), []))
    result = env.svc.process_on_demand_quiz(CHAT, "ru", "aws", "easy", request_id=91)
    assert result["status"] == ("error" if quota_error else "ok")
    assert len(env.sent) == (0 if quota_error else 1)


@pytest.fixture
def observations(monkeypatch):
    from zerde_common.logger import JSONFormatter

    records, formatted = [], []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)
            formatted.append(JSONFormatter().format(record))

    for module in [qs.observation_module, qs.provider_module, qs.generator_module]:
        monkeypatch.setattr(module.logger.logger, "handlers", [Capture()])
        monkeypatch.setattr(module.logger.logger, "level", logging.DEBUG)
    return records, formatted


def compatible(response=None, error=None):
    provider = qs.provider_module.OpenAICompatibleQuizProvider(
        "Groq", "synthetic-secret", "https://synthetic.invalid", "synthetic-model"
    )
    provider._interactive_http = Mock()
    provider._interactive_http.request.return_value = response
    provider._interactive_http.request.side_effect = error
    return provider


def wire(usage, status=200):
    return SimpleNamespace(
        status=status,
        data=json.dumps(
            {
                "choices": [{"message": {"content": '{"question":"ok"}'}}],
                "usage": usage,
            }
        ).encode(),
    )


@pytest.mark.parametrize(
    "usage,expected",
    [
        ({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 18}, "known"),
        (None, "missing"),
        ({"prompt_tokens": 10}, "missing"),
        ([], "invalid"),
        ({"prompt_tokens": True, "completion_tokens": -1, "total_tokens": 1.5}, "invalid"),
    ],
)
def test_fallback_usage_retains_unknowns_without_repeating_response(observations, usage, expected):
    provider = compatible(wire(usage))
    assert provider.generate_json("PRIVATE PROMPT", interactive=True) == {"question": "ok"}
    provider._interactive_http.request.assert_called_once()
    events = [r._extra for r in observations[0] if r.getMessage() == "Quiz model attempt"]
    assert len(events) == 2 and events[0]["attempt_id"] == events[1]["attempt_id"]
    last = events[1]
    assert last["outcome"] == "success" and last["usage_status"] == expected
    if expected == "known":
        assert last["total_tokens"] == 18  # Never infer 10+5.
    else:
        assert last["total_tokens"] is None
    assert "PRIVATE PROMPT" not in "\n".join(observations[1])


def test_usage_property_or_logging_failure_does_not_retry_valid_gemini(monkeypatch):
    class Response:
        text = '{"question":"ok"}'

        @property
        def usage_metadata(self):
            raise ValueError("PRIVATE USAGE")

    provider, order = gemini(monkeypatch, [Response()], [(1, True)])
    monkeypatch.setattr(qs.observation_module.logger, "info", Mock(side_effect=ValueError("log sink down")))
    assert provider.generate_json("PRIVATE PROMPT", interactive=True) == {"question": "ok"}
    assert order == ["admit", "network"]


@pytest.mark.parametrize("failure", ["http", "transport", "json", "schema"])
def test_provider_errors_and_final_formatter_never_emit_raw_content(observations, failure):
    marker = "PRIVATE PROMPT TEXT synthetic-password 123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
    error = qs.provider_module.HTTPError(marker) if failure == "transport" else None
    data = marker.encode() if failure in {"http", "json"} else json.dumps({"choices": marker}).encode()
    provider = compatible(SimpleNamespace(status=503 if failure == "http" else 200, data=data), error)
    generator = actual_generator(qs.provider_module.FallbackProvider([provider]))
    assert generator.generate_question(marker, "ru", interactive=True) is None
    rendered = "\n".join(observations[1])
    assert marker not in rendered and "PRIVATE PROMPT" not in rendered and "synthetic-password" not in rendered
    events = [r._extra for r in observations[0] if r.getMessage() == "Quiz model attempt"]
    assert len(events) == 2
    assert events[1]["outcome"] in {"http_error", "transport_unknown", "response_invalid"}
    assert events[1]["total_tokens"] is None


def test_gemini_api_error_and_usage_are_content_free(monkeypatch, observations):
    provider, _ = gemini(monkeypatch, [busy(), response()], [(1, True), (2, True)])
    assert provider.generate_json("PRIVATE PROMPT", interactive=True) == {"question": "ok"}
    events = [r._extra for r in observations[0] if r.getMessage() == "Quiz model attempt"]
    assert len(events) == 4 and events[0]["attempt_id"] != events[2]["attempt_id"]
    assert events[1]["outcome"] == "http_error" and events[1]["usage_status"] == "no_response"
    assert events[3]["usage_status"] == "known" and events[3]["total_tokens"] == 25
    assert "PRIVATE" not in "\n".join(observations[1])


def test_help_matches_existing_permissions_and_done_text_is_neutral():
    from core.translations import TRANSLATIONS

    for lang in ["en", "kk", "ru", "zh"]:
        genquiz_line = next(line for line in TRANSLATIONS[lang]["help_message"].splitlines() if "/genquiz" in line)
        assert "ADMIN_USER_ID" not in genquiz_line
    assert "恢复" not in TRANSLATIONS["zh"]["quiz_reconcile_ok"]
    assert "restored" not in TRANSLATIONS["en"]["quiz_reconcile_ok"]


@pytest.mark.parametrize("provider_kind", ["gemini", "compat_content", "compat_encoding"])
def test_unmapped_non_api_failure_does_not_expand_paid_fallback(monkeypatch, provider_kind):
    if provider_kind == "gemini":
        primary, _ = gemini(monkeypatch, [SimpleNamespace(text=None)], [(1, True)])
    elif provider_kind == "compat_content":
        primary = compatible(SimpleNamespace(status=200, data=b'{"choices":[{"message":{"content":null}}]}'))
    else:
        primary = compatible(SimpleNamespace(status=200, data=b"\xff"))
    secondary = Mock()
    chain = qs.provider_module.FallbackProvider([primary, secondary])
    with pytest.raises((TypeError, AttributeError, UnicodeDecodeError)):
        chain.generate_json("synthetic", interactive=True)
    secondary.generate_json.assert_not_called()


@pytest.mark.parametrize("invalid", ["question", "index", "leaked_terms"])
def test_generator_validation_logs_lengths_and_types_not_content(observations, invalid):
    marker = "privatequokka privatebadger"
    data = {
        "question": "Which choice?",
        "options": ["alpha beta", "gamma delta", "epsilon zeta", "eta theta"],
        "correct_option_index": 0,
        "explanation": "synthetic",
    }
    if invalid == "question":
        data["question"] = ""
    elif invalid == "index":
        data["correct_option_index"] = marker
    else:
        data["question"] = f"Which {marker} belongs?"
        data["options"] = [marker, "differentsecond longwords", "differentthird longwords", "differentfourth longwords"]
    provider = Mock()
    provider.generate_json.return_value = data
    assert actual_generator(provider).generate_question(marker, "ru", interactive=True) is None
    rendered = "\n".join(observations[1])
    assert "privatequokka" not in rendered and "privatebadger" not in rendered


def test_fallback_diagnostics_cannot_discard_valid_result_or_change_routing(monkeypatch):
    primary, secondary = Mock(), Mock()
    primary.generate_json.side_effect = qs.provider_module.ProviderTransportError("synthetic")
    secondary.generate_json.return_value = qs.question()
    monkeypatch.setattr(qs.provider_module.logger, "warning", Mock(side_effect=OSError("log unavailable")))
    monkeypatch.setattr(qs.provider_module.logger, "info", Mock(side_effect=OSError("log unavailable")))
    generator = actual_generator(qs.provider_module.FallbackProvider([primary, secondary]))
    assert generator.generate_question("python", "ru", interactive=True) is not None
    assert primary.generate_json.call_count == secondary.generate_json.call_count == 1
