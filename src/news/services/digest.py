"""DigestService: orchestrates the full news digest pipeline."""

import re
from typing import Any
from urllib.parse import urlsplit

from core.logger import LoggerAdapter, get_logger
from core.utils import extract_event, get_intro_text
from services.ai_client import NewsAIClientBase
from services.news_fetcher import NewsFetcher, classify_source_region, extract_domain
from services.telegram import TelegramSender

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
    ) -> None:
        self._fetcher = fetcher
        self._ai = ai
        self._sender = sender

    def _notify_chats_digest_failure(self, chat_ids: list[str], message: str) -> None:
        """Best-effort alert to every configured chat (errors are logged, not raised)."""
        for chat_id in chat_ids:
            try:
                self._sender.send_message(chat_id, message)
            except Exception:
                logger.exception(
                    "Failed to send digest failure notification",
                    extra={"chat_id": chat_id},
                )

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

    def _enrich_news_candidates(self, raw_news: list[dict]) -> list[dict]:
        """Fetch article metadata/text before selection so ranking has evidence."""
        candidates = self._dedupe_and_limit_candidates(raw_news)
        enriched: list[dict] = []
        for article in candidates:
            deep_data = self._fetcher.fetch_deep_article_data(article["link"])
            article.update(deep_data)
            article["full_text_chars"] = int(article.get("full_text_chars") or len(article.get("full_text") or ""))
            article["has_image"] = bool(article.get("image_url"))
            article["quality_score"], article["quality_reasons"] = _score_article_quality(article)
            enriched.append(article)

        enriched.sort(key=lambda item: float(item.get("quality_score", 0)), reverse=True)
        for index, article in enumerate(enriched):
            article["index"] = index
        logger.info(
            "News candidates enriched",
            extra={
                "candidate_count": len(enriched),
                "selectable_count": sum(
                    1 for item in enriched if float(item.get("quality_score", 0)) >= _MIN_SELECTABLE_QUALITY_SCORE
                ),
            },
        )
        return enriched

    def run(self, event: dict[str, Any]) -> dict[str, Any]:
        """Execute the digest pipeline for a language group.

        Expects event keys: chat_ids (list[str]), lang (str).
        Generates the digest once and sends it to all chat_ids.
        Returns an API-Gateway-style response dict.
        """
        logger.info("Starting daily news digest job")
        chat_ids, lang = extract_event(event)
        try:
            raw_news = self._fetcher.fetch_raw_news()
            if not raw_news:
                logger.info("No news items found within TTL; skipping digest")
                return {"statusCode": 200, "body": "No news"}

            enriched_news = self._enrich_news_candidates(raw_news)
            if not enriched_news:
                logger.info("No usable news candidates after enrichment; skipping digest")
                return {"statusCode": 200, "body": "No usable news"}

            selections = self._ai.select_top_news(enriched_news)
            top_indices = _selection_indices(selections)
            logger.info(
                "Top news selected",
                extra={
                    "indices": top_indices,
                    "count": len(top_indices),
                    "selection_reasons": [selection.get("score_reason", "")[:120] for selection in selections],
                },
            )

            deep_news = [enriched_news[idx] for idx in top_indices]
            logger.info("Selected enriched articles", extra={"articles": len(deep_news)})

            intro = get_intro_text(lang)
            digests = self._ai.generate_digests_per_article(deep_news, lang)

            sent_chats: list[str] = []
            failed: list[dict] = []
            for chat_id in chat_ids:
                logger.info("Sending digest to chat", extra={"chat_id": chat_id})
                ok = True
                if not self._sender.send_message(chat_id, intro)[0]:
                    failed.append({"chat_id": str(chat_id), "step": "intro"})
                    continue
                for i, article in enumerate(deep_news):
                    image_url = article.get("image_url") or ""
                    digest_text = digests[i] if i < len(digests) else f"<b>{article['title']}</b>\n{article['link']}"
                    logger.info(
                        "Sending message with photo",
                        extra={"chat_id": chat_id, "has_image": bool(image_url), "index": i},
                    )
                    if not self._sender.send_message_with_photo(chat_id, digest_text, image_url):
                        ok = False
                        failed.append(
                            {
                                "chat_id": str(chat_id),
                                "step": f"article_{i}",
                                "article_index": i,
                            },
                        )
                if ok:
                    sent_chats.append(str(chat_id))
                    logger.info("Digest sent successfully", extra={"chat_id": chat_id})

            return {
                "statusCode": 200,
                "body": "Agentic Digest Sent",
                "sent_chat_ids": sent_chats,
                "failed": failed,
            }

        except Exception as e:
            logger.exception("Error in news digest pipeline")
            # Avoid putting raw exception text in Telegram (may contain URLs or internal detail).
            self._notify_chats_digest_failure(
                chat_ids,
                f"⚠️ News digest failed ({type(e).__name__}). Check CloudWatch logs for details.",
            )
            return {"statusCode": 500, "body": "Internal server error"}
