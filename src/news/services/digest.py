"""DigestService: orchestrates the full news digest pipeline."""

import asyncio
import re
import time
import uuid
from typing import Any
from urllib.parse import urlsplit

from core.logger import LoggerAdapter, get_logger
from core.utils import get_intro_text
from services.ai_client import NewsAIClientBase
from services.deadline import Deadline, NewsDeadlineError
from services.delivery_state import NewsDeliveryRepository, parse_job
from services.news_fetcher import NewsFetcher, classify_source_region, extract_domain
from services.telegram import TelegramSender, prepare_step

logger = LoggerAdapter(get_logger(__name__), {})

_MAX_ENRICH_CANDIDATES = 45
_MIN_SELECTABLE_QUALITY_SCORE = 1.0

_DEVELOPER_TERMS = {
    "agent",
    "ai",
    "api",
    "architecture",
    "aws",
    "backend",
    "benchmark",
    "cloud",
    "container",
    "cursor",
    "cybersecurity",
    "database",
    "developer",
    "devops",
    "docker",
    "framework",
    "gemini",
    "github",
    "infrastructure",
    "kubernetes",
    "lambda",
    "llm",
    "mcp",
    "model",
    "open source",
    "python",
    "rag",
    "release",
    "security",
    "serverless",
    "sentry",
    "software",
    "startup",
    "tool",
    "typescript",
}
_LOW_SIGNAL_TERMS = {
    "advertorial",
    "award",
    "conference agenda",
    "discount",
    "giveaway",
    "launches campaign",
    "partnership announcement",
    "press release",
    "sponsored",
}
_CONSUMER_TERMS = {
    "smartphone",
    "tablet",
    "tv",
    "headphones",
    "gaming laptop",
    "wearable",
}


def _text_for_scoring(article: dict) -> str:
    return " ".join(str(article.get(key) or "") for key in ("title", "summary", "full_text")).lower()


def _term_hits(text: str, terms: set[str]) -> int:
    return sum(1 for term in terms if term in text)


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9а-яәғқңөұүһіё]+", " ", title.lower()).strip()


def _is_homepage_like(article: dict) -> bool:
    path = urlsplit(str(article.get("link") or "")).path.strip("/")
    return not path or path in {"news", "feed", "rss"}


def _preliminary_score(article: dict) -> float:
    text = _text_for_scoring(article)
    score = float(min(_term_hits(text, _DEVELOPER_TERMS), 8))
    if article.get("source_region") == "kz":
        score += 0.6
    if _term_hits(text, _LOW_SIGNAL_TERMS):
        score -= 2.0
    if _term_hits(text, _CONSUMER_TERMS):
        score -= 1.0
    if _is_homepage_like(article):
        score -= 1.5
    return score


def _score_article_quality(article: dict) -> tuple[float, list[str]]:
    """Score local digest quality before asking the LLM to rank candidates."""
    score = 0.0
    reasons: list[str] = []
    text = _text_for_scoring(article)
    full_text_chars = int(article.get("full_text_chars") or len(str(article.get("full_text") or "")))
    has_image = bool(article.get("image_url"))
    dev_hits = _term_hits(text, _DEVELOPER_TERMS)

    if full_text_chars >= 1200:
        score += 2.0
        reasons.append("substantial_article_text")
    elif full_text_chars >= 500:
        score += 1.2
        reasons.append("usable_article_text")
    elif full_text_chars >= 220:
        score += 0.4
        reasons.append("short_article_text")
    else:
        score -= 1.4
        reasons.append("weak_or_empty_article_text")

    if has_image:
        score += 0.8
        reasons.append("has_image")
    else:
        score -= 0.3
        reasons.append("no_image")

    if dev_hits >= 6:
        score += 2.0
        reasons.append("strong_developer_relevance")
    elif dev_hits >= 3:
        score += 1.2
        reasons.append("developer_relevance")
    elif dev_hits >= 1:
        score += 0.4
        reasons.append("weak_developer_relevance")
    else:
        score -= 1.0
        reasons.append("low_developer_relevance")

    low_signal_hits = _term_hits(text, _LOW_SIGNAL_TERMS)
    if low_signal_hits:
        score -= 1.2
        reasons.append("possible_pr_or_low_signal")

    if _term_hits(text, _CONSUMER_TERMS):
        score -= 0.8
        reasons.append("consumer_gadget_angle")

    if _is_homepage_like(article):
        score -= 1.6
        reasons.append("homepage_or_thin_link")

    if article.get("source_region") == "kz":
        if full_text_chars >= 350 and dev_hits >= 2:
            score += 0.7
            reasons.append("kz_soft_bonus")
        else:
            score -= 0.7
            reasons.append("weak_kz_candidate")

    return round(score, 2), reasons


def _selection_indices(selections: list[dict]) -> list[int]:
    return [int(selection["index"]) for selection in selections if "index" in selection]


class DigestService:
    """Full news digest pipeline: fetch → enrich/score → AI select → generate → send."""

    def __init__(
        self,
        fetcher: NewsFetcher,
        ai: NewsAIClientBase,
        sender: TelegramSender,
        repository: NewsDeliveryRepository | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._ai = ai
        self._sender = sender
        self._repository = repository or NewsDeliveryRepository()

    def _dedupe_and_limit_candidates(self, raw_news: list[dict]) -> list[dict]:
        """Remove obvious duplicates and bound deep scraping work."""
        deduped: list[dict] = []
        seen_links: set[str] = set()
        seen_titles: set[str] = set()

        for article in raw_news:
            link = str(article.get("link") or "").strip()
            title = str(article.get("title") or "").strip()
            if not link or not title:
                continue
            domain = article.get("domain") or extract_domain(link)
            candidate = {
                **article,
                "domain": domain,
                "source_region": article.get("source_region") or classify_source_region(link),
            }
            link_key = link.split("#", 1)[0].rstrip("/").lower()
            title_key = f"{domain}:{_title_key(title)}"
            if link_key in seen_links or title_key in seen_titles:
                continue
            seen_links.add(link_key)
            seen_titles.add(title_key)
            deduped.append(candidate)

        deduped.sort(key=_preliminary_score, reverse=True)
        limited = deduped[:_MAX_ENRICH_CANDIDATES]
        for index, article in enumerate(limited):
            article["index"] = index
        logger.info(
            "News candidates deduped and prefiltered",
            extra={"raw_count": len(raw_news), "deduped_count": len(deduped), "limited_count": len(limited)},
        )
        return limited

    async def _enrich_news_candidates(self, raw_news, deadline):
        """At most 45 candidates, five concurrent requests, and 45 seconds for the whole stage."""
        candidates = self._dedupe_and_limit_candidates(raw_news)
        semaphore = asyncio.Semaphore(5)

        async def enrich(article):
            async with semaphore:
                article.update(await self._fetcher.fetch_deep_article_data(article["link"], deadline))

        tasks = [asyncio.create_task(enrich(article)) for article in candidates]
        try:
            async with deadline.timeout(45):
                await asyncio.gather(*tasks)
        except TimeoutError:
            logger.warning("News enrichment deadline reached; retaining source summaries")
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        for article in candidates:
            article["full_text_chars"] = int(article.get("full_text_chars") or len(article.get("full_text") or ""))
            article["has_image"] = bool(article.get("image_url"))
            article["quality_score"], article["quality_reasons"] = _score_article_quality(article)
        candidates.sort(key=lambda item: float(item.get("quality_score", 0)), reverse=True)
        for index, article in enumerate(candidates):
            article["index"] = index
        return candidates

    def run(self, event: dict[str, Any], context=None, *, budget_seconds=240) -> dict[str, Any]:
        """Raise on incomplete work: a statusCode 500 return is not a Lambda failure."""
        seconds = min(240, budget_seconds)
        if context is not None:
            seconds = min(seconds, context.get_remaining_time_in_millis() / 1000 - 15)
        deadline = Deadline(seconds)
        try:
            return asyncio.run(self._run(event, deadline))
        except TimeoutError:
            raise NewsDeadlineError("News invocation reached its end-to-end deadline") from None

    async def _run(self, event, deadline):
        async with deadline.timeout(deadline.remaining()):
            job = parse_job(event)
            deadline.remaining(reserve=10)
            owner, manifest = self._repository.claim_manifest(job)
            if owner:
                try:
                    raw_news = await self._fetcher.fetch_raw_news(deadline)
                    if raw_news:
                        enriched = await self._enrich_news_candidates(raw_news, deadline)
                        selections = await self._ai.select_top_news(enriched, deadline)
                        articles = [enriched[index] for index in _selection_indices(selections)]
                        if not articles:
                            raise RuntimeError("No news articles could be selected")
                        digests = await self._ai.generate_digests_per_article(articles, job["lang"], deadline)
                        if len(digests) != len(articles) or any(
                            not isinstance(x, str) or not x.strip() for x in digests
                        ):
                            raise RuntimeError("News generation returned incomplete content")
                        steps = [prepare_step(get_intro_text(job["lang"]))]
                        steps.extend(
                            prepare_step(text, article.get("image_url") or "")
                            for text, article in zip(digests, articles, strict=True)
                        )
                    else:
                        # Successful RSS reads with no fresh items are a real no-news result, not a timeout fallback.
                        steps = []
                    deadline.remaining(reserve=20)
                    manifest = self._repository.freeze_manifest(job, owner, steps)
                finally:
                    self._repository.release_manifest(job, owner)
            failed = 0
            sent = []
            for chat_id in manifest["chat_ids"]:
                deadline.remaining(reserve=10)
                try:
                    complete = await self._send_chat(manifest, chat_id, deadline)
                except NewsDeadlineError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "News chat delivery incomplete", extra={"chat_id": chat_id, "error_type": type(exc).__name__}
                    )
                    complete = False
                if complete:
                    sent.append(chat_id)
                else:
                    failed += 1
            if failed:
                raise RuntimeError(f"News delivery incomplete for {failed} chat(s); inspect delivery receipts")
            return {
                "statusCode": 200,
                "body": "Digest delivered" if manifest["steps"] else "No fresh news",
                "sent_chat_ids": sent,
                "content_hash": manifest["content_hash"],
            }

    async def _send_chat(self, manifest, chat_id, deadline):
        owner, row = self._repository.claim_delivery(manifest, chat_id)
        try:
            for index, content in enumerate(manifest["steps"]):
                step = dict(row["steps"][index])
                if step["state"] == "SENT":
                    continue
                if step["state"] == "UNKNOWN" or int(step.get("not_before", 0)) > int(time.time()):
                    return False
                # At most a photo attempt and its explicitly rejected text fallback; never retry an unknown send.
                for _ in range(2):
                    deadline.remaining(reserve=15)
                    step = {
                        **row["steps"][index],
                        "state": "UNKNOWN",
                        "attempt_id": uuid.uuid4().hex,
                        "attempt": int(row["steps"][index]["attempt"]) + 1,
                        "started_at": int(time.time()),
                    }
                    self._repository.save_step(row, owner, index, step)
                    result = await self._sender.send_step(chat_id, content, step["mode"], deadline)
                    if result.state == "SENT":
                        self._repository.save_step(
                            row, owner, index, {**step, "state": "SENT", "message_id": result.message_id}
                        )
                        break
                    if result.state == "UNKNOWN":
                        return False  # Durable before HTTP, including cancellation or crash before a response.
                    photo_fallback = result.state == "REJECTED" and step["mode"] == "photo"
                    step.update(
                        state="PENDING",
                        last_result=result.state,
                        last_status=result.status or 0,
                        not_before=0 if photo_fallback else int(time.time()) + max(1, result.retry_after),
                    )
                    if photo_fallback:
                        step["mode"] = "text"
                    self._repository.save_step(row, owner, index, step)
                    if not photo_fallback:
                        return False
            return True
        finally:
            self._repository.release_delivery(row, owner)
