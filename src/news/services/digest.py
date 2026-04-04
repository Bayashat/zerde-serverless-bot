"""DigestService: orchestrates the full news digest pipeline."""

from typing import Any

from core.logger import LoggerAdapter, get_logger
from core.utils import extract_event, get_greeting_and_max_age_hours, get_intro_text
from services.ai_client import AIClient
from services.news_fetcher import NewsFetcher
from services.telegram import TelegramSender

logger = LoggerAdapter(get_logger(__name__), {})


class DigestService:
    """Full news digest pipeline: fetch → AI select → deep scrape → generate → send."""

    def __init__(
        self,
        fetcher: NewsFetcher,
        ai: AIClient,
        sender: TelegramSender,
    ) -> None:
        self._fetcher = fetcher
        self._ai = ai
        self._sender = sender

    def run(self, event: dict[str, Any]) -> dict[str, Any]:
        """Execute the digest pipeline for a language group.

        Expects event keys: chat_ids (list[str]), lang (str).
        Generates the digest once and sends it to all chat_ids.
        Returns an API-Gateway-style response dict.
        """
        logger.info("Starting daily news digest job")
        chat_ids, lang = extract_event(event)
        max_age_hours, hour = get_greeting_and_max_age_hours(lang)
        logger.info(f"Max age hours: {max_age_hours}, Hour: {hour}")
        try:
            raw_news = self._fetcher.fetch_raw_news(max_age_hours=max_age_hours)
            if not raw_news:
                logger.info("No news items found within TTL; skipping digest")
                return {"statusCode": 200, "body": "No news"}

            top_indices = self._ai.select_top_news(raw_news)
            logger.info(
                "Top indices selected",
                extra={"indices": top_indices, "count": len(top_indices)},
            )

            deep_news: list[dict] = []
            for idx in top_indices:
                article = raw_news[idx]
                logger.debug(
                    "Fetching deep article data",
                    extra={"index": idx, "link": article.get("link")},
                )
                deep_data = self._fetcher.fetch_deep_article_data(article["link"])
                article.update(deep_data)
                deep_news.append(article)

            logger.info("Deep scrape complete", extra={"articles": len(deep_news)})

            intro = get_intro_text(lang, hour)
            digests = self._ai.generate_digests_per_article(deep_news, lang)

            for chat_id in chat_ids:
                logger.info("Sending digest to chat", extra={"chat_id": chat_id})
                self._sender.send_message(chat_id, intro)
                for i, article in enumerate(deep_news):
                    image_url = article.get("image_url") or ""
                    digest_text = digests[i] if i < len(digests) else f"<b>{article['title']}</b>\n{article['link']}"
                    logger.info(
                        "Sending message with photo",
                        extra={"chat_id": chat_id, "image_url": image_url},
                    )
                    self._sender.send_message_with_photo(chat_id, digest_text, image_url)
                logger.info("Digest sent successfully", extra={"chat_id": chat_id})

            return {"statusCode": 200, "body": "Agentic Digest Sent"}

        except Exception:
            logger.exception("Error in news digest pipeline")
            return {"statusCode": 500, "body": "Internal server error"}
