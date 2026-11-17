"""Bounded public-topic evidence. No memory, identities, cache or generated queries."""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote

import httpx
from services.memory_v2.models import MemoryInputError
from services.memory_v2.safety import require_public_content
from zerde_common.async_http import bounded_async_client

_MAX_BYTES = 65536
_HTTP_DEADLINE = 6
_SOURCE_HTTP = contextvars.ContextVar("public_source_http", default=False)


class _SourceRequestFilter(logging.Filter):
    def filter(self, record):
        return not _SOURCE_HTTP.get()


# HTTPX emits request URLs at INFO; suppress only this context, not other callers.
logging.getLogger("httpx").addFilter(_SourceRequestFilter())
_USER_AGENT = "ZerdeBot/1.0 (https://github.com/Bayashat/zerde-serverless-bot)"
_PERSONAL = re.compile(
    r"\b(i|me|my|mine|you|your|yours|we|our|ours|us|he|his|she|her|hers|they|their|theirs|"
    r"owns?|owned|said|member|members|private|internal|intranet|"
    r"я|мне|меня|мой|моя|моё|мои|мы|наш|наша|наши|ты|твой|вы|ваш|он|она|они|его|её|их|"
    r"моего|моему|моей|моих|нашего|нашему|нашей|наших|вашего|вашей|ваших|твоего|твоей|твоих|"
    r"мен|менің|маған|сен|сенің|сіз|сіздің|біз|біздің|ол|оның|олар|олардың)\b|"
    r"我|你|您|他|她|拥有|曾说|说过|群成员|群友|内部|内网|私有|私人|住址|职业史",
    re.IGNORECASE,
)
# Reject sensitive topic classes conservatively even without a possessive pronoun.
# This guard intentionally also excludes public definitions in these categories.
_SENSITIVE = re.compile(
    r"\b(health|medical|disease|diagnosis|diabetes|depression|cancer|hiv|pregnan\w*|"
    r"salary|income|wealth|balance|bank|debt|credit|mortgage|loan|financial|finance|tax|religio\w*|"
    r"christian\w*|muslim\w*|jewish|politic\w*|vot\w*|sexual\w*|gender|gay|lesbian|"
    r"password|secret|token|credential\w*|account|passport|address|"
    r"здоров\w*|медицин\w*|болез\w*|диагноз\w*|диабет\w*|депресс\w*|рак|вич|"
    r"зарплат\w*|доход\w*|банк\w*|баланс\w*|долг\w*|кредит\w*|финанс\w*|"
    r"религи\w*|мусульман\w*|полит\w*|сексуал\w*|парол\w*|паспорт\w*|"
    r"денсаулық\w*|ауру\w*|жалақы\w*|табыс\w*|қарыз\w*|құпия\w*|дін\w*)\b|"
    r"健康|医疗|疾病|诊断|糖尿病|抑郁|癌症|艾滋|怀孕|收入|工资|薪资|财务|银行|"
    r"余额|债务|信用|税务|宗教|信仰|政治|党派|性取向|性别|密码|口令|令牌|身份证|护照",
    re.IGNORECASE,
)
_RELATIONAL = re.compile(
    r"\b(difference|between|versus|vs|pros|cons|advantages?|disadvantages?|complexity|"
    r"meaning of|purpose of|cost of|price of|performance of|capital of|population of)\b|"
    r"区别|差别|优缺点|复杂度|多少钱|разниц\w*|между|сложност\w*|артықшыл\w*|айырмашыл\w*",
    re.IGNORECASE,
)
_SMALL_TALK = {"ok", "okay", "thanks", "thank you", "yes", "no", "hi", "hello", "hey", "bye", "goodbye"}
_NON_TOPIC = re.compile(
    r"\b(explain|translate|write|calculate|tell|help|please|print|return|ignore|"
    r"lives?|works?|said|says|address|history|user|username|account|project)\b|"
    r"^请|^帮|^翻译|^解释|^编写|项目|姓名|地址|历史|账号",
    re.IGNORECASE,
)
_DEFINITIONS = (
    re.compile(r"^\s*(?P<topic>.+?)\s*是什么(?:[?？。！!]|$)", re.IGNORECASE),
    re.compile(r"^\s*什么是\s*(?P<topic>[^?？。！!]+)(?:[?？。！!]|$)", re.IGNORECASE),
    re.compile(r"^\s*what\s+(?:is|are)\s+(?P<topic>[^?？!]+?)(?:[?？!]|$)", re.IGNORECASE),
    re.compile(r"^\s*что\s+такое\s+(?P<topic>[^?？!]+?)(?:[?？!]|$)", re.IGNORECASE),
    re.compile(r"^\s*(?P<topic>.+?)\s+деген\s+не(?:[?？!]|$)", re.IGNORECASE),
)


@dataclass(frozen=True)
class PublicSource:
    title: str
    extract: str
    url: str
    language: str
    page_id: int
    fetched_at: int


@dataclass(frozen=True)
class PublicLookup:
    applicable: bool
    source: PublicSource | None = None


def public_topic(question: str) -> tuple[str, str] | None:
    """Select a narrow verbatim topic, never a general question or a fact query.

    These exclusions are a conservative lexical boundary, not a proof that all
    possible names are public. In particular, GENERAL from V2 is not a permit.
    """
    if not isinstance(question, str):
        return None
    question = re.sub(r"^/ask(?:@[A-Za-z0-9_]+)?\s+", "", question).strip()
    try:
        require_public_content(question, max_length=4000)
    except MemoryInputError:
        return None
    folded = unicodedata.normalize("NFKC", question)
    if (
        _PERSONAL.search(folded)
        or _SENSITIVE.search(folded)
        or _RELATIONAL.search(folded)
        or folded.casefold().strip(".!?？。！ ") in _SMALL_TALK
        or re.search(r"[\n\r\t@_`{}\[\]<>\\=\"'‘’“”]|\d{7}|[A-Za-z0-9]{32}", folded)
        or any(unicodedata.category(c) in {"Cc", "Cf"} for c in question)
    ):
        return None
    topic = None
    for pattern in _DEFINITIONS:
        match = pattern.match(question)
        if match:
            topic = match.group("topic").strip().removesuffix(".").strip()
            break
    if topic is None:
        if len(question.split()) > 4 or _NON_TOPIC.search(folded):
            return None
        # Acronyms, word-internal capitals and short version numbers are useful
        # technical-name shapes; there is deliberately no vendor/product list.
        if not re.search(
            r"\b[A-Z]{2,8}\b|[A-Z]{2,8}[a-z]|[a-z][A-Z]|[A-Za-z]\d{1,3}\b|\b\d{1,2}\.\d{1,2}\b",
            question,
        ):
            return None
        topic = question
    if (
        not 2 <= len(topic) <= 120
        or len(topic.split()) > 8
        or _NON_TOPIC.search(topic)
        or not any(c.isalpha() for c in topic)
        or any(not (c.isalnum() or c in " -.+") for c in topic)
        or topic not in question
    ):
        return None
    language = "zh" if re.search(r"[\u3400-\u9fff]", topic) else "ru" if re.search(r"[\u0400-\u04ff]", topic) else "en"
    return topic, language


async def _fetch_json(host: str, path: str, params: dict | None) -> dict | None:
    # The shared transport uses cancellable asynchronous DNS, not getaddrinfo
    # threads. The outer timeout covers DNS/TLS/headers AND the streaming body.
    async with asyncio.timeout(_HTTP_DEADLINE):
        async with bounded_async_client(timeout=3, connect_timeout=2, max_connections=1) as client:
            async with client.stream(
                "POST" if params is not None else "GET",
                f"https://{host}{path}",
                data=params,
                headers={"User-Agent": _USER_AGENT, "Accept": "application/json", "Accept-Encoding": "identity"},
            ) as response:
                if (
                    response.status_code != 200
                    or response.headers.get("content-encoding", "identity") != "identity"
                    or "application/json" not in response.headers.get("content-type", "")
                ):
                    return None
                raw = bytearray()
                async for chunk in response.aiter_raw():
                    raw.extend(chunk)
                    if len(raw) > _MAX_BYTES:
                        return None
    value = json.loads(raw)
    return value if isinstance(value, dict) else None


def _json_request(host: str, path: str, *, params: dict | None = None) -> dict | None:
    """At most six seconds of cancellable network I/O, no retries or redirects.

    The 64 KiB JSON decode and synchronous fence/CPU time are outside this
    network bound. Full source text and network errors are never logged.
    """
    token = _SOURCE_HTTP.set(True)
    try:
        return asyncio.run(_fetch_json(host, path, params))
    except (httpx.HTTPError, OSError, ValueError):
        return None
    finally:
        _SOURCE_HTTP.reset(token)


def _same_title(left: str, right: str) -> bool:
    return " ".join(left.replace("_", " ").split()).casefold() == " ".join(right.split()).casefold()


def _short_extract(text: str) -> str:
    if len(text) <= 1800:
        return text
    cut = max(text.rfind(end, 0, 1800) for end in (". ", "。", "! ", "? ", "\n"))
    return text[: cut + 1].strip() if cut >= 100 else ""


def lookup_public_source(
    question: str,
    *,
    before_attempt: Callable[[], None] | None = None,
    request: Callable[..., dict | None] | None = None,
) -> PublicLookup:
    selected = public_topic(question)
    if selected is None:
        return PublicLookup(False)
    topic, language = selected
    request = request or _json_request
    host = f"{language}.wikipedia.org"

    def read(path, **kwargs):
        if before_attempt is not None:
            before_attempt()  # Control failures must never become source misses.
        result = request(host, path, **kwargs)
        if before_attempt is not None:
            before_attempt()
        return result

    search = read(
        "/w/api.php",
        params={
            "action": "query",
            "list": "search",
            "srsearch": topic,
            "srnamespace": 0,
            "srlimit": 3,
            "srprop": "redirecttitle",
            "srinfo": "",
            "format": "json",
            "formatversion": 2,
        },
    )
    if not isinstance(search, dict) or "error" in search or "warnings" in search:
        return PublicLookup(True)
    rows = search.get("query", {}).get("search") if isinstance(search.get("query"), dict) else None
    if not isinstance(rows, list) or len(rows) > 3:
        return PublicLookup(True)
    matches = []
    for row in rows:
        if not isinstance(row, dict) or type(row.get("ns")) is not int or row["ns"] != 0:
            return PublicLookup(True)
        title, alias, page_id = (
            row.get("title"),
            row.get("redirecttitle", ""),
            row.get("pageid"),
        )
        if not isinstance(title, str) or not isinstance(alias, str) or type(page_id) is not int or page_id <= 0:
            return PublicLookup(True)
        if _same_title(title, topic) or _same_title(alias, topic):
            matches.append((title, page_id))
    if len(matches) != 1:
        return PublicLookup(True)
    title, page_id = matches[0]
    if not 1 <= len(title) <= 200 or any(unicodedata.category(c)[0] == "C" for c in title):
        return PublicLookup(True)
    summary = read("/api/rest_v1/page/summary/" + quote(title.replace(" ", "_"), safe=""))
    if not isinstance(summary, dict):
        return PublicLookup(True)
    extract = summary.get("extract")
    if (
        summary.get("type") != "standard"
        or type(summary.get("pageid")) is not int
        or summary["pageid"] != page_id
        or not isinstance(summary.get("title"), str)
        or not _same_title(summary["title"], title)
        or not isinstance(extract, str)
        or not extract.strip()
        or len(extract) > 6000
    ):
        return PublicLookup(True)
    extract = _short_extract(extract.strip())
    if not extract:
        return PublicLookup(True)
    return PublicLookup(
        True,
        PublicSource(
            title,
            extract,
            f"https://{host}/wiki/" + quote(title.replace(" ", "_"), safe=""),
            language,
            page_id,
            int(time.time()),
        ),
    )


def unavailable_public_topic(lang: str) -> str:
    return {
        "zh": "我暂时无法将这个名称对应到明确的公开资料。请提供官方链接或更完整的名称，以免把它和相似名称的事物混淆。",
        "ru": (
            "Пока не удалось однозначно сопоставить это название с публичным источником. "
            "Пришлите официальную ссылку или полное название, чтобы не перепутать его с похожим."
        ),
        "kk": (
            "Бұл атауды ашық дереккөзбен нақты сәйкестендіре алмадым. "
            "Ұқсас атаулармен шатастырмас үшін ресми сілтемені немесе толық атауын жіберіңіз."
        ),
    }.get(
        lang,
        (
            "I could not reliably match this name to a public source. "
            "Please provide an official link or the full name so I do not confuse it with something similarly named."
        ),
    )
