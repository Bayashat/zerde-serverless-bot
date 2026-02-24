"""News Lambda: Daily IT news digest entry point."""

from typing import Any

from aws_lambda_powertools import Logger
from repositories.ai_client import create_ai_client
from services.news_fetcher import NewsFetcher
from services.telegram import broadcast_messages

logger = Logger()


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """EventBridge scheduled handler. Fetches IT news and sends to Telegram."""
    logger.info("Starting daily news job")

    try:
        # 1. Fetch raw news (24h TTL)
        fetcher = NewsFetcher()
        raw_news = fetcher.fetch_raw_news(items_per_feed=15, max_age_hours=24)

        if not raw_news:
            logger.info("No news found")
            broadcast_messages(["Бүгін жаңалық жоқ."])
            return {"statusCode": 200, "body": "No news today"}

        # 2. Score with AI
        ai_client = create_ai_client()
        scored_news = ai_client.evaluate_impact(raw_news)
        logger.info(f"Scored {len(scored_news)} news items")

        # 3. Select top 1
        scored_news.sort(key=lambda x: x.get("impact_score", 0), reverse=True)
        top_news = scored_news[:3]
        logger.info(f"Top 1 score: {[n.get('impact_score') for n in top_news]}")

        # 4. Generate one Telegram message per news item
        messages = ai_client.generate_item_summaries(top_news)

        # 5. Broadcast each message to all configured chat IDs
        success = broadcast_messages(messages)

        if success:
            logger.info(f"Sent {len(messages)} messages")
            return {"statusCode": 200, "body": "News sent successfully"}
        else:
            logger.error("Failed to send any messages")
            return {"statusCode": 500, "body": "Failed to send messages"}

    except Exception:
        logger.exception("Error in news lambda")
        return {"statusCode": 500, "body": "Internal server error"}
