"""AI client for generating daily news digest with provider abstraction."""

import json
import random
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import urllib3
from core.config import DEEPSEEK_API_BASE, DEEPSEEK_MODEL, LLM_MODEL, get_deepseek_api_key, get_gemini_api_key
from core.logger import LoggerAdapter, get_logger
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from zerde_common.ai_errors import (
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTransportError,
    ZerdeProviderError,
    map_http_status_to_provider_error,
)
from zerde_common.logging_utils import llm_text_log_fields

logger = LoggerAdapter(get_logger(__name__), {})


def _map_gemini_api_error(exc: genai_errors.APIError) -> ZerdeProviderError:
    if exc.code == 429:
        return ProviderRateLimitError(str(exc))
    if exc.code in (500, 503, 504):
        return ProviderTransportError(str(exc))
    if exc.code and 400 <= int(exc.code) < 500:
        return ProviderResponseError(str(exc))
    return ProviderResponseError(str(exc))


_TOP_NEWS_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "top_news": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "category": {
                        "type": "string",
                        "enum": ["global_tech_ai", "hardcore_engineering", "kz_or_regional", "other_high_signal"],
                    },
                    "score_reason": {"type": "string"},
                },
                "required": ["index", "category", "score_reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["top_news"],
    "additionalProperties": False,
}

_ARTICLE_DIGEST_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "digest": {"type": "string"},
    },
    "required": ["digest"],
    "additionalProperties": False,
}

_MIN_SELECTION_QUALITY_SCORE = 1.0
_MIN_GENERATIVE_TEXT_CHARS = 420


class NewsAIClientBase(ABC):
    """Base class: shared prompt logic; subclasses implement ``_generate``."""

    @abstractmethod
    def _generate(
        self,
        prompt: str,
        temperature: float,
        max_output_tokens: int,
        response_json_schema: dict[str, Any] | None = None,
    ) -> dict:
        """Call the LLM and return the parsed JSON dict. Raises on failure."""

    def _fallback_top_news(
        self,
        news_items: list[dict],
        used_indices: set[int] | None = None,
        used_domains: set[str] | None = None,
    ) -> list[dict]:
        """Deterministically pick high-quality, domain-unique fallback selections."""
        used_indices = used_indices or set()
        used_domains = used_domains or set()
        selections: list[dict] = []
        sorted_items = sorted(
            news_items,
            key=lambda item: (
                float(item.get("quality_score", 0)),
                bool(item.get("image_url")),
                int(item.get("full_text_chars") or 0),
            ),
            reverse=True,
        )
        for article in sorted_items:
            index = int(article.get("index", -1))
            domain = str(article.get("domain") or "")
            if index in used_indices or (domain and domain in used_domains):
                continue
            if len(selections) < 3 and float(article.get("quality_score", 0)) < _MIN_SELECTION_QUALITY_SCORE:
                continue
            selections.append(
                {
                    "index": index,
                    "category": (
                        "kz_or_regional" if article.get("source_region") in {"kz", "regional"} else "other_high_signal"
                    ),
                    "score_reason": "local quality-score fallback",
                }
            )
            used_indices.add(index)
            if domain:
                used_domains.add(domain)
            if len(selections) == 3:
                break

        if len(selections) < min(3, len(news_items)):
            for article in sorted_items:
                index = int(article.get("index", -1))
                domain = str(article.get("domain") or "")
                if index in used_indices or (domain and domain in used_domains):
                    continue
                selections.append(
                    {
                        "index": index,
                        "category": "other_high_signal",
                        "score_reason": "low-supply local fallback",
                    }
                )
                used_indices.add(index)
                if domain:
                    used_domains.add(domain)
                if len(selections) == min(3, len(news_items)):
                    break
        return selections

    def _validate_top_news_response(self, data: dict, news_items: list[dict]) -> list[dict]:
        """Normalize LLM choices and enforce local uniqueness/quality constraints."""
        raw_items = data.get("top_news")
        if raw_items is None:
            raw_items = [
                {"index": index, "category": "other_high_signal", "score_reason": "legacy response"}
                for index in data.get("top_indices", [])
            ]

        by_index = {int(item["index"]): item for item in news_items if "index" in item}
        selections: list[dict] = []
        used_indices: set[int] = set()
        used_domains: set[str] = set()

        for raw in raw_items or []:
            try:
                index = int(raw.get("index"))
            except (AttributeError, TypeError, ValueError):
                continue
            article = by_index.get(index)
            if not article or index in used_indices:
                continue
            domain = str(article.get("domain") or "")
            if domain and domain in used_domains:
                continue
            if float(article.get("quality_score", 0)) < _MIN_SELECTION_QUALITY_SCORE:
                continue
            selections.append(
                {
                    "index": index,
                    "category": str(raw.get("category") or "other_high_signal"),
                    "score_reason": str(raw.get("score_reason") or "selected by AI"),
                }
            )
            used_indices.add(index)
            if domain:
                used_domains.add(domain)
            if len(selections) == min(3, len(news_items)):
                break

        if len(selections) < min(3, len(news_items)):
            filler = self._fallback_top_news(
                news_items,
                used_indices=set(used_indices),
                used_domains=set(used_domains),
            )
            for item in filler:
                if item["index"] not in used_indices:
                    selections.append(item)
                    used_indices.add(item["index"])
                if len(selections) == min(3, len(news_items)):
                    break

        return selections

    def select_top_news(self, news_items: list[dict]) -> list[dict]:
        """Ask the model to pick the top 3 unique enriched news candidates."""
        if not news_items:
            return []

        payload = [
            {
                "index": n["index"],
                "title": n["title"],
                "summary": n.get("summary", ""),
                "domain": n.get("domain", ""),
                "source_region": n.get("source_region", "global"),
                "has_image": bool(n.get("image_url")),
                "full_text_chars": int(n.get("full_text_chars") or 0),
                "quality_score": float(n.get("quality_score", 0)),
                "quality_reasons": n.get("quality_reasons", []),
                "text_preview": (n.get("full_text") or n.get("summary") or "")[:700],
            }
            for n in news_items
        ]
        prompt = (
            "You are an expert IT Editor curating a daily news digest for a hardcore community of Software Engineers (primarily backend, cloud, and AI developers).\n"  # noqa: E501
            "Analyze the provided enriched JSON list of news items and cluster duplicate or similar stories.\n"
            "Your task is to select EXACTLY 3 of the most IMPACTFUL, HIGH-SIGNAL, and UNIQUE news items.\n"
            "Prefer candidates with strong quality_score, concrete article text, "
            "clear developer relevance, and images.\n\n"
            "**DEFINITION OF 'IMPACTFUL' FOR THIS AUDIENCE:**\n"
            "✅ YES (High Priority): Major framework/tool updates (e.g., AWS, Python, AI models), deep architectural insights, high-profile open-source releases, tech startup funding, or paradigm shifts in software engineering.\n"  # noqa: E501
            "❌ NO (DO NOT SELECT): Empty/thin article pages, generic e-government/municipal updates, pure consumer gadget reviews, homepage/project pages with no news angle, or corporate PR fluff.\n\n"  # noqa: E501
            "Aim for content diversity across these categories when quality supports it:\n"
            "1. Global Tech & AI: Game-changing tech news, major AI model releases, or massive industry shifts that affect how developers build software.\n"  # noqa: E501
            "2. Hardcore Engineering: Practical cloud infrastructure (Serverless, AWS), backend architecture, or DevOps tools.\n"  # noqa: E501
            "3. Kazakhstan IT & Community: Local tech startups, IT business in KZ, Almaty/Astana developer community events, or Kazakhstani tech industry news.\n\n"  # noqa: E501
            "🛡️ LOCAL CONSTRAINTS:\n"
            "- Kazakhstan/regional content is a SOFT BONUS, not a quota. Include one only when it is genuinely strong for software/AI/cloud/startup developers.\n"  # noqa: E501
            "- If KZ/local candidates are weak, choose three stronger global engineering/AI stories instead.\n"
            "- DOMAIN UNIQUENESS: Do not select multiple articles from the same website domain.\n\n"
            "Respond ONLY with a JSON object in this exact format:\n"
            '{"top_news": [{"index": 0, "category": "global_tech_ai", "score_reason": "concrete reason"}]}\n\n'
            f"DATA:\n{json.dumps(payload, ensure_ascii=False)}"
        )

        try:
            logger.info("Selecting top news with AI", extra={"pool_size": len(news_items)})
            data = self._generate(
                prompt,
                temperature=0.1,
                max_output_tokens=1024,
                response_json_schema=_TOP_NEWS_RESPONSE_SCHEMA,
            )
            result = self._validate_top_news_response(data, news_items)
            logger.info(
                "Top news selected",
                extra={"indices": [item["index"] for item in result], "pool_size": len(news_items)},
            )
            return result
        except ZerdeProviderError:
            logger.exception("AI failed to select top news; falling back to local quality score")
            return self._fallback_top_news(news_items)

    def generate_digests_per_article(self, deep_news_items: list[dict], chat_lang: str) -> list[str]:
        """Generate one HTML digest block per article for pairing with images."""
        if not deep_news_items:
            return []

        if chat_lang == "zh":
            community_name = "Chinese developer community"
            language = "Chinese (Simplified)"
            read_full_text = "阅读全文"
        elif chat_lang == "kk":
            community_name = "Kazakh developer community"
            language = "Kazakh (Cyrillic)"
            read_full_text = "Толығырақ оқу"
        elif chat_lang == "ru":
            community_name = "Russian developer community"
            language = "Russian"
            read_full_text = "Читать полностью"
        else:
            raise ValueError(f"Unsupported chat language: {chat_lang}")

        logger.info(
            "Generating per-article news digests with AI",
            extra={"article_count": len(deep_news_items), "chat_lang": chat_lang},
        )

        def fallback(article: dict) -> str:
            summary = (article.get("summary") or article.get("full_text") or "").strip()
            summary_line = f"\n\n{summary[:420]}" if summary else ""
            return f'<b>{article["title"]}</b>{summary_line}\n\n<a href="{article["link"]}">{read_full_text}</a>'

        def build_prompt(article: dict) -> str:
            payload = {
                "title": article["title"],
                "link": article["link"],
                "source_summary": article.get("summary", ""),
                "full_text": article.get("full_text", article["summary"]),
                "full_text_chars": int(article.get("full_text_chars") or 0),
            }
            return (
                f"You are an expert IT journalist for a {community_name}.\n"
                "I will give you the title, source summary, and extracted article text for one IT news article.\n"
                f"Write ONE fact-first digest block in modern {language}. "
                f"CRITICAL: The ENTIRE block, INCLUDING the TITLE, MUST be completely translated and written in {language}.\n\n"  # noqa: E501
                "FORMAT RULES:\n"
                f"1. One relevant Emoji, then a <b>specific factual title TRANSLATED INTO {language}</b>.\n"
                "2. Add two new lines (\\n\\n) after the title, then write 3-4 concise sentences based ONLY on the provided title, source summary, and full_text.\n"  # noqa: E501
                f'3. End with the HTML link: <a href="URL">{read_full_text}</a>.\n'
                "4. NO raw URLs except inside the href attribute.\n"
                "5. Keep the block under ~800 characters.\n\n"
                "CONTENT RULES:\n"
                "- Say what concretely happened: who did what, which product/model/tool/company is involved, and what changes for developers.\n"  # noqa: E501
                "- Include at least one concrete detail from the article: a version, number, named feature, affected tool, company, model, API, vulnerability, funding amount, or deployment impact.\n"  # noqa: E501
                "- Do NOT invent details or write generic hype. Avoid phrases like 'industry benchmark', 'new cornerstone', 'new chapter', 'core driver', or 'urgent challenge' unless the text explicitly supports them.\n"  # noqa: E501
                "- If evidence is limited, be modest and specific instead of analytical.\n\n"
                "Respond ONLY with a JSON object:\n"
                '{"digest": "single html digest block"}\n\n'
                f"DATA:\n{json.dumps(payload, ensure_ascii=False)}"
            )

        def generate_one(index: int, article: dict) -> str:
            if int(article.get("full_text_chars") or 0) < _MIN_GENERATIVE_TEXT_CHARS:
                logger.info(
                    "Skipping AI digest generation for thin article text",
                    extra={"index": index, "full_text_chars": int(article.get("full_text_chars") or 0)},
                )
                return fallback(article)
            logger.info("Generating single article digest", extra={"index": index})
            data = self._generate(
                build_prompt(article),
                temperature=0.4,
                max_output_tokens=1800,
                response_json_schema=_ARTICLE_DIGEST_RESPONSE_SCHEMA,
            )
            digest = (data.get("digest") or "").strip()
            if not digest:
                raise ValueError("AI returned empty digest")
            logger.info("Single article digest generated", extra={"index": index, "digest_chars": len(digest)})
            return digest

        result = [fallback(article) for article in deep_news_items]
        with ThreadPoolExecutor(max_workers=min(3, len(deep_news_items))) as executor:
            futures = {executor.submit(generate_one, i, article): i for i, article in enumerate(deep_news_items)}
            for future in as_completed(futures):
                index = futures[future]
                try:
                    result[index] = future.result()
                except ZerdeProviderError:
                    logger.exception("Failed to generate single article digest", extra={"index": index})

        logger.info("Per-article digests generated", extra={"count": len(result)})
        return result


class GeminiNewsClient(NewsAIClientBase):
    """Google Gemini provider via google-genai SDK. Raises on exhausted retries."""

    _RETRY_DELAYS = (5, 15, 30)  # seconds between attempts

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        logger.info("GeminiNewsClient initialized", extra={"model": model})

    def _generate(
        self,
        prompt: str,
        temperature: float,
        max_output_tokens: int,
        response_json_schema: dict[str, Any] | None = None,
    ) -> dict:
        has_schema = response_json_schema is not None
        for attempt, delay in enumerate(self._RETRY_DELAYS):
            try:
                thinking_config = self._thinking_config()
                config_kwargs: dict[str, Any] = {
                    "temperature": temperature,
                    "response_mime_type": "application/json",
                    "max_output_tokens": max_output_tokens,
                }
                if response_json_schema is not None:
                    config_kwargs["response_json_schema"] = response_json_schema
                if thinking_config is not None:
                    config_kwargs["thinking_config"] = thinking_config

                logger.info(
                    "Gemini news request started",
                    extra={
                        "model": self._model,
                        "attempt": attempt + 1,
                        "temperature": temperature,
                        "max_output_tokens": max_output_tokens,
                        "response_json_schema": has_schema,
                        "thinking_config": self._thinking_config_name(thinking_config),
                    },
                )
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
                finish_reason = self._finish_reason(response)
                logger.info(
                    "Gemini call succeeded",
                    extra={"model": self._model, "attempt": attempt + 1, "finish_reason": finish_reason},
                )
                text = response.text.strip()
                logger.debug("Gemini response (preview)", extra=llm_text_log_fields(text))
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as je:
                    raise ProviderResponseError(f"Gemini returned invalid JSON: {je}") from je
                logger.info(
                    "Gemini news response parsed",
                    extra={
                        "model": self._model,
                        "attempt": attempt + 1,
                        "response_chars": len(text),
                        "response_json_schema": has_schema,
                        "finish_reason": finish_reason,
                    },
                )
                return data
            except genai_errors.APIError as exc:
                retryable = exc.code in (429, 500, 503, 504)
                is_last_attempt = attempt == len(self._RETRY_DELAYS) - 1
                if not retryable or is_last_attempt:
                    logger.warning(
                        "Gemini exhausted retries or non-retryable error",
                        extra={"model": self._model, "code": exc.code},
                    )
                    raise _map_gemini_api_error(exc) from exc
                if exc.code in (429, 503):
                    # Rate limited or globally overloaded — no point retrying, fall through to DeepSeek
                    logger.warning(
                        "Gemini overloaded/rate-limited, skipping retries",
                        extra={"model": self._model, "code": exc.code},
                    )
                    if exc.code == 429:
                        raise ProviderRateLimitError(str(exc)) from exc
                    raise _map_gemini_api_error(exc) from exc
                wait = delay + random.uniform(0, 3)
                logger.warning(
                    "Gemini request failed, retrying with backoff",
                    extra={"model": self._model, "attempt": attempt + 1, "wait_s": round(wait, 1), "code": exc.code},
                )
                time.sleep(wait)
            except ZerdeProviderError:
                raise

    @staticmethod
    def _finish_reason(response: Any) -> str | None:
        """Extract Gemini finish reason without depending on SDK internals."""
        try:
            return str(response.candidates[0].finish_reason)
        except (AttributeError, IndexError, TypeError):
            return None

    def _thinking_config(self) -> types.ThinkingConfig | None:
        """Use the lowest supported thinking budget for deterministic JSON tasks."""
        if self._model.startswith("gemini-3"):
            return types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)
        if self._model.startswith("gemini-2.5"):
            return types.ThinkingConfig(thinking_budget=0)
        return None

    @staticmethod
    def _thinking_config_name(config: types.ThinkingConfig | None) -> str | None:
        if config is None:
            return None
        if config.thinking_level is not None:
            return f"level:{config.thinking_level.value}"
        if config.thinking_budget is not None:
            return f"budget:{config.thinking_budget}"
        return "default"


class DeepSeekNewsClient(NewsAIClientBase):
    """DeepSeek provider via OpenAI-compatible API (urllib3, no extra SDK)."""

    _http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(connect=5, read=60))

    def __init__(self, api_key: str, api_base: str, model: str) -> None:
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._model = model
        logger.info("DeepSeekNewsClient initialized", extra={"model": model})

    def _generate(
        self,
        prompt: str,
        temperature: float,
        max_output_tokens: int,
        response_json_schema: dict[str, Any] | None = None,
    ) -> dict:
        has_schema = response_json_schema is not None
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_output_tokens,
            "response_format": {"type": "json_object"},
        }

        logger.info(
            "DeepSeek news request started",
            extra={
                "model": self._model,
                "temperature": temperature,
                "max_tokens": max_output_tokens,
                "response_json_schema": has_schema,
                "response_format": "json_object",
            },
        )
        resp = self._http.request(
            "POST",
            f"{self._api_base}/chat/completions",
            body=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )

        if resp.status == 429:
            raise ProviderRateLimitError(f"DeepSeek rate limited: {resp.status}")

        if resp.status >= 400:
            body = resp.data.decode("utf-8")
            logger.error("DeepSeek API error", extra={"status": resp.status, "body": body[:500]})
            raise map_http_status_to_provider_error(
                resp.status,
                f"DeepSeek API {resp.status}: {body[:200]}",
            )

        try:
            data = json.loads(resp.data.decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
        except json.JSONDecodeError as e:
            raise ProviderResponseError(f"DeepSeek response was not valid JSON: {e}") from e
        except (KeyError, IndexError, TypeError):
            raise
        logger.info("DeepSeek call succeeded", extra={"model": self._model})
        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            raise ProviderResponseError(f"DeepSeek content was not valid JSON: {e}") from e
        logger.info(
            "DeepSeek news response parsed",
            extra={"model": self._model, "response_chars": len(content), "response_json_schema": has_schema},
        )
        return result


class FallbackNewsClient(NewsAIClientBase):
    """Tries primary (Gemini); on any failure falls back to secondary (DeepSeek)."""

    def __init__(self, primary: NewsAIClientBase, fallback: NewsAIClientBase) -> None:
        self._primary = primary
        self._fallback = fallback

    def _generate(
        self,
        prompt: str,
        temperature: float,
        max_output_tokens: int,
        response_json_schema: dict[str, Any] | None = None,
    ) -> dict:
        try:
            return self._primary._generate(prompt, temperature, max_output_tokens, response_json_schema)
        except ZerdeProviderError as e:
            logger.warning(
                "Primary news provider failed, falling back to DeepSeek",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            return self._fallback._generate(prompt, temperature, max_output_tokens, response_json_schema)


def create_ai_client() -> NewsAIClientBase:
    """Factory: returns Gemini primary → DeepSeek fallback client."""
    gemini = GeminiNewsClient(api_key=get_gemini_api_key(), model=LLM_MODEL)
    deepseek = DeepSeekNewsClient(api_key=get_deepseek_api_key(), api_base=DEEPSEEK_API_BASE, model=DEEPSEEK_MODEL)
    return FallbackNewsClient(primary=gemini, fallback=deepseek)
