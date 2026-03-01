"""News Lambda: Daily IT news digest entry point (Morning / Noon / Evening)."""

from typing import Any

from aws_lambda_powertools import Logger
from helper import get_chat_lang_by_id, get_greeting_and_max_age_hours, get_intro_text
from repositories.ai_client import create_ai_client
from services import BOT_TOKEN, NEWS_CHAT_IDS
from services.news_fetcher import NewsFetcher
from services.telegram import send_message_with_photo, send_telegram_message

logger = Logger()


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """EventBridge scheduled handler. Sends intro, then each article as image + digest to Telegram."""
    logger.info("Starting daily news digest job")

    try:
        max_age_hours, greeting = get_greeting_and_max_age_hours()
        logger.info(f"Max age hours: {max_age_hours}, Greeting: {greeting}")

        fetcher = NewsFetcher()
        ai_client = create_ai_client()

        raw_news = fetcher.fetch_raw_news(items_per_feed=5, max_age_hours=max_age_hours)
        if not raw_news:
            logger.info("No news items found within TTL; skipping digest")
            return {"statusCode": 200, "body": "No news"}

        top_indices = ai_client.select_top_news(raw_news)
        logger.info("Top indices selected", extra={"indices": top_indices, "count": len(top_indices)})

        deep_news = []
        for idx in top_indices:
            article = raw_news[idx]
            logger.debug("Fetching deep article data", extra={"index": idx, "link": article.get("link")})
            deep_data = fetcher.fetch_deep_article_data(article["link"])
            article.update(deep_data)
            deep_news.append(article)

        logger.info("Deep scrape complete", extra={"articles": len(deep_news)})

        for chat_id in NEWS_CHAT_IDS:
            chat_lang = get_chat_lang_by_id(chat_id)
            intro = get_intro_text(chat_lang)
            digests = ai_client.generate_digests_per_article(deep_news, chat_lang)
            send_telegram_message(BOT_TOKEN, chat_id, f"{greeting}\n\n{intro}")
            for i, article in enumerate(deep_news):
                image_url = article.get("image_url") or ""
                digest_text = digests[i] if i < len(digests) else f"<b>{article['title']}</b>\n{article['link']}"
                logger.info(
                    "Sending message with photo",
                    extra={"chat_id": chat_id, "digest_text": digest_text, "image_url": image_url},
                )
                send_message_with_photo(BOT_TOKEN, chat_id, digest_text, image_url)

        logger.info("Digest sent successfully", extra={"chat_count": len(NEWS_CHAT_IDS)})
        return {"statusCode": 200, "body": "Agentic Digest Sent"}

    except Exception:
        logger.exception("Error in news lambda")
        return {"statusCode": 500, "body": "Internal server error"}
