"""Selector attempts use real budget CAS; all network outcomes are synthetic."""

import asyncio
import json
from unittest.mock import Mock

import httpx
import pytest
from services.memory_budget import RESERVATION_MICRO_USD, cost_micro_usd
from services.memory_v2.answer_prompt import build_answer_request
from services.memory_v2.answer_selector import AnswerSelectionUnavailable, GeminiAnswerProvider, MemoryAnswerSelector
from services.memory_v2.models import MemoryUnavailable

from tests import test_memory_budget as budget_contract

budget = budget_contract.budget
FACTS = [
    {
        "subject_id": "USER#42",
        "field": "tech_stack",
        "facet": "",
        "value": "Python",
        "last_confirmed_at": 1788998400,
        "freshness": "current",
    }
]


def payload():
    return {
        "candidates": [
            {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps({"mode": "facts", "indices": [0]})}]}}
        ],
        "usageMetadata": budget_contract.usage(),
    }


class Provider:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = 0

    async def generate(self, request):
        self.calls += 1
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


async def valid():
    return True


def selector(repo, provider, *, validator=valid):
    quota = Mock()
    quota.increment_and_check.return_value = (1, True)
    return MemoryAnswerSelector(provider, repo, validate_snapshot=validator, rate_limit=quota), quota


def run(select):
    return asyncio.run(select.select("What do I use?", FACTS, ["42"]))


def test_answer_retry_preserves_unknown_charge_and_settles_full_second_call(budget):
    repo, _ = budget
    provider = Provider([TimeoutError(), payload()])
    select, quota = selector(repo, provider)
    assert run(select) == ("facts", (0,))
    assert provider.calls == 2 and quota.increment_and_check.call_count == 2
    assert repo.snapshot()["charged_micro_usd"] == RESERVATION_MICRO_USD + cost_micro_usd(100, 70)
    attempts = repo.table.scan()["Items"]
    assert {row["purpose"] for row in attempts if "purpose" in row} == {"answer"}


def test_paused_budget_cannot_consume_quota_or_make_provider_call(budget):
    repo, _ = budget
    repo.table.put_item(Item={"pk": "MEMORY_BUDGET#CONTROL", "sk": "MODEL", "paused": True})
    provider = Provider([])
    select, quota = selector(repo, provider)
    with pytest.raises(AnswerSelectionUnavailable):
        run(select)
    assert provider.calls == 0
    quota.increment_and_check.assert_not_called()


def test_unknown_usage_keeps_entire_answer_reservation(budget):
    repo, _ = budget
    response = payload()
    response.pop("usageMetadata")
    select, _ = selector(repo, Provider([response]))
    assert run(select) == ("facts", (0,))
    assert repo.snapshot()["charged_micro_usd"] == RESERVATION_MICRO_USD


def test_source_change_after_reservation_blocks_http_and_conservatively_holds_cost(budget):
    repo, _ = budget
    calls = []

    async def changed():
        calls.append(1)
        if len(calls) > 1:
            raise MemoryUnavailable("source changed")

    provider = Provider([])
    select, _ = selector(repo, provider, validator=changed)
    with pytest.raises(MemoryUnavailable):
        run(select)
    assert provider.calls == 0 and repo.snapshot()["charged_micro_usd"] == RESERVATION_MICRO_USD


def test_rate_limit_error_sentinel_is_not_authorization(budget):
    repo, _ = budget
    provider = Provider([])
    select, quota = selector(repo, provider)
    quota.increment_and_check.return_value = (0, True)
    with pytest.raises(AnswerSelectionUnavailable):
        run(select)
    assert provider.calls == 0 and not repo.snapshot()


@pytest.mark.parametrize("mode", ["unknown", "general"])
def test_empty_profile_still_classifies_personal_unknown_separately_from_general(budget, mode):
    repo, _ = budget
    result = payload()
    result["candidates"][0]["content"]["parts"][0]["text"] = json.dumps({"mode": mode, "indices": []})
    provider = Provider([result])
    select, quota = selector(repo, provider)
    assert asyncio.run(select.select("What do I use?", [], ["42"])) == (mode, ())
    assert provider.calls == 1 and repo.snapshot()["charged_micro_usd"] > 0
    quota.increment_and_check.assert_called_once()


def test_http_provider_has_fixed_model_header_and_no_redirect():
    seen = []

    def response(request):
        seen.append(request)
        assert "synthetic-key" not in str(request.url)
        assert request.headers["x-goog-api-key"] == "synthetic-key"
        assert request.url.path.endswith("gemini-3.1-flash-lite:generateContent")
        return httpx.Response(200, json=payload())

    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
            return await GeminiAnswerProvider("synthetic-key", client=client).generate(
                build_answer_request("What do I use?", FACTS, ["42"])
            )

    assert asyncio.run(call())["usageMetadata"] and len(seen) == 1


def test_http_error_never_exposes_body_or_secret():
    async def call():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(500, text="synthetic-secret-body"))
        ) as client:
            await GeminiAnswerProvider("synthetic-key", client=client).generate(
                build_answer_request("What do I use?", FACTS, ["42"])
            )

    with pytest.raises(AnswerSelectionUnavailable) as error:
        asyncio.run(call())
    assert "synthetic" not in str(error.value) and error.value.__cause__ is None
