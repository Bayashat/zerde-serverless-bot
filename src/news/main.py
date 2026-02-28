"""News Lambda: Daily IT news digest entry point (Morning / Noon / Evening)."""

from typing import Any

from aws_lambda_powertools import Logger
from helper import get_greeting
from repositories.ai_client import create_ai_client
from services import BOT_TOKEN, NEWS_CHAT_IDS
from services.news_fetcher import NewsFetcher
from services.telegram import send_media_group, send_telegram_message

logger = Logger()


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """EventBridge scheduled handler. Fetches IT news, generates digest, sends media group or text to Telegram."""
    logger.info("Starting daily news digest job")

    try:
        greeting = get_greeting()
        logger.info(f"Greeting: {greeting}")

        fetcher = NewsFetcher()
        ai_client = create_ai_client()

        raw_news = fetcher.fetch_raw_news(items_per_feed=5, max_age_hours=24)
        if not raw_news:
            logger.info("No news items found within TTL; skipping digest")
            return {"statusCode": 200, "body": "No news"}

        top_indices = ai_client.select_top_news(raw_news)
        logger.info("Top indices selected", extra={"indices": top_indices, "count": len(top_indices)})

        deep_news = []
        image_urls = []
        for idx in top_indices:
            article = raw_news[idx]
            logger.debug("Fetching deep article data", extra={"index": idx, "link": article.get("link")})
            deep_data = fetcher.fetch_deep_article_data(article["link"])
            article.update(deep_data)
            deep_news.append(article)
            if "unsplash" not in deep_data["image_url"]:
                image_urls.append(deep_data["image_url"])

        logger.info("Deep scrape complete", extra={"articles": len(deep_news), "images": len(image_urls)})

        final_text = ai_client.generate_final_digest(deep_news, greeting)

        for chat_id in NEWS_CHAT_IDS:
            if image_urls:
                send_media_group(BOT_TOKEN, chat_id, image_urls)
            send_telegram_message(BOT_TOKEN, chat_id, final_text)

        logger.info("Digest sent successfully", extra={"chat_count": len(NEWS_CHAT_IDS)})
        return {"statusCode": 200, "body": "Agentic Digest Sent"}

    except Exception:
        logger.exception("Error in news lambda")
        return {"statusCode": 500, "body": "Internal server error"}
