"""Real async HTTP adapter with synthetic transports; never contacts Gemini."""

import asyncio
import copy
import json
import time
import traceback

import httpx
import pytest
from services.memory_v2 import gemini_extraction
from services.memory_v2.extraction_prompt import build_request
from services.memory_v2.gemini_extraction import ExtractionProviderError, GeminiExtractionProvider

from tests.test_memory_v2_extraction import source


def run_provider(handler, *, request=None, follow_redirects=False):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=follow_redirects
        ) as client:
            return await GeminiExtractionProvider("synthetic-api-key", client=client).generate(
                request if request is not None else build_request([source()])
            )

    return asyncio.run(run())


def test_actual_adapter_sends_one_text_json_request_with_key_only_in_header():
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"candidates": [], "usageMetadata": {"totalTokenCount": 10}})

    result = run_provider(handle, request=build_request([source("Сәлем")]))
    assert result["usageMetadata"]["totalTokenCount"] == 10
    assert len(seen) == 1 and seen[0].method == "POST"
    assert str(seen[0].url) == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent"
    )
    assert seen[0].headers["x-goog-api-key"] == "synthetic-api-key"
    document = json.loads(json.loads(seen[0].content)["contents"][0]["parts"][0]["text"])
    assert document["sources"][0]["text"] == "Сәлем"


@pytest.mark.parametrize("status", [302, 400, 429, 503])
def test_non_success_never_implicitly_retries_or_follows_redirects(status):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(
            status, headers={"Location": "https://example.invalid/leak"}, text="synthetic private text"
        )

    with pytest.raises(ExtractionProviderError) as error:
        run_provider(handle, follow_redirects=True)
    assert len(seen) == 1
    assert "private" not in str(error.value)
    assert error.value.__context__ is None


def test_transport_secret_and_private_body_cannot_escape_in_exception_chain():
    secret = "synthetic-secret-in-transport"

    def handle(request):
        raise httpx.ConnectError(secret + " user private message", request=request)

    with pytest.raises(ExtractionProviderError) as error:
        run_provider(handle)
    rendered = "".join(traceback.format_exception(error.value))
    assert secret not in rendered and "user private message" not in rendered
    assert error.value.__context__ is None


def test_total_deadline_cancels_and_closes_a_streaming_response(monkeypatch):
    monkeypatch.setattr(gemini_extraction, "REQUEST_TIMEOUT_SECONDS", 0.02)

    class SlowStream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b'{"candidates":'
            await asyncio.Event().wait()

        async def aclose(self):
            self.closed = True

    stream = SlowStream()
    started = time.monotonic()
    with pytest.raises(ExtractionProviderError):
        run_provider(lambda request: httpx.Response(200, stream=stream))
    assert stream.closed
    assert time.monotonic() - started < 0.5


def test_response_byte_limit_closes_stream_without_parsing_large_payload(monkeypatch):
    monkeypatch.setattr(gemini_extraction, "MAX_RESPONSE_BYTES", 32)
    with pytest.raises(ExtractionProviderError):
        run_provider(lambda request: httpx.Response(200, content=b"x" * 33))


@pytest.mark.parametrize("data", [b"not json", b"[]", b"null"])
def test_malformed_response_never_looks_like_an_empty_success(data):
    with pytest.raises(ExtractionProviderError):
        run_provider(lambda request: httpx.Response(200, content=data))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda request: request.update(tools=[{"googleSearch": {}}]),
        lambda request: request.update(cachedContent="cachedContents/synthetic"),
        lambda request: request["generationConfig"].update(candidateCount=2),
        lambda request: request["generationConfig"].update(candidateCount=True),
        lambda request: request["generationConfig"].update(maxOutputTokens=65536),
        lambda request: request["generationConfig"].update(responseModalities=["AUDIO"]),
        lambda request: request["contents"][0]["parts"].append({"inlineData": {"data": "synthetic"}}),
        lambda request: request["contents"][0].update(role="model"),
        lambda request: request["systemInstruction"]["parts"][0].update(text="different instructions"),
    ],
)
def test_provider_rejects_unpriced_or_non_extraction_request_before_http(mutation):
    seen = []
    request = copy.deepcopy(build_request([source()]))
    mutation(request)
    with pytest.raises(ExtractionProviderError):
        run_provider(lambda incoming: seen.append(incoming), request=request)
    assert seen == []


def test_request_schema_copy_cannot_mutate_the_approved_configuration():
    request = build_request([source()])
    request["generationConfig"]["responseJsonSchema"]["properties"]["sources"]["maxItems"] = 999
    seen = []
    with pytest.raises(ExtractionProviderError):
        run_provider(lambda incoming: seen.append(incoming), request=request)
    assert seen == []


def test_duplicate_input_json_keys_cannot_hide_unsafe_text_from_validation():
    request = build_request([source()])
    request["contents"][0]["parts"][0]["text"] = (
        '{"sources":[{"source_index":0,"text":"password is synthetic",' '"text":"I use Python.","quoted_spans":[]}]}'
    )
    seen = []
    with pytest.raises(ExtractionProviderError):
        run_provider(lambda incoming: seen.append(incoming), request=request)
    assert seen == []
