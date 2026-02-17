"""News Lambda: Sends daily IT news to Telegram group."""

import os
import time
from typing import Any, Optional

import requests
from aws_lambda_powertools import Logger

from repositories.ai_client import create_ai_client
from services.news_fetcher import NewsFetcher


logger = Logger()


def sanitize_html(text: str) -> str:
    """
    Sanitize text for Telegram HTML parse mode.
    Escapes <, >, & but preserves <b>, </b>, <blockquote>, </blockquote> tags.
    """
    if not text:
        return ""
        
    # Escape basic HTML
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    
    # Restore allowed tags
    allowed_tags = ["b", "/b", "blockquote", "/blockquote"]
    for tag in allowed_tags:
        escaped_tag = f"&lt;{tag}&gt;"
        real_tag = f"<{tag}>"
        text = text.replace(escaped_tag, real_tag)
        
    return text


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """EventBridge scheduled handler. Fetches IT news and sends to Telegram."""
    logger.info("Starting daily news job")

    try:
        bot_token = os.environ.get("BOT_TOKEN")
        chat_id = os.environ.get("NEWS_CHAT_ID")
        groq_api_key = os.environ.get("GROQ_API_KEY")

        if not all([bot_token, chat_id, groq_api_key]):
            logger.error("Missing required environment variables")
            return {"statusCode": 500, "body": "Configuration error"}

        # 1. Fetch raw news (24h TTL)
        fetcher = NewsFetcher()
        raw_news = fetcher.fetch_raw_news(items_per_feed=15, max_age_hours=24)

        if not raw_news:
            logger.info("No news found")
            send_telegram_message(bot_token, chat_id, "📭 Бүгін жаңалық жоқ.")
            return {"statusCode": 200, "body": "No news today"}

        # 2. Evaluate impact
        ai_provider = os.environ.get("AI_PROVIDER", "groq")
        ai_client = create_ai_client(provider=ai_provider, api_key=groq_api_key)
        
        scored_news = ai_client.evaluate_impact(raw_news)
        logger.info(f"Scored {len(scored_news)} news items")
        
        # 3. Select top 3
        scored_news.sort(key=lambda x: x.get("impact_score", 0), reverse=True)
        top_news = scored_news[:3]
        logger.info(f"Top 3 news scores: {[n.get('impact_score', 0) for n in top_news]}")
        
        # 4. Generate summary
        summary = ai_client.generate_news_summary(top_news, language="kk")

        # 5. Sanitize and Send
        safe_summary = sanitize_html(summary)
        
        # Primary: Send with HTML
        success = send_telegram_message(bot_token, chat_id, safe_summary)
        
        # Fallback: Send as plain text
        if not success:
            logger.warning("HTML send failed. Attempting plain text fallback...")
            success = send_telegram_message(bot_token, chat_id, summary, parse_mode=None)

        if success:
            logger.info(f"Successfully sent news to chat {chat_id}")
            return {"statusCode": 200, "body": "News sent successfully"}
        else:
            logger.error("Failed to send message to Telegram even with fallback")
            return {"statusCode": 500, "body": "Failed to send message"}

    except Exception:
        logger.exception("Error in news lambda")
        return {"statusCode": 500, "body": "Internal server error"}


def send_telegram_message(bot_token: str, chat_id: str, text: str, parse_mode: Optional[str] = "HTML") -> bool:
    """Send message to Telegram chat."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True
    }
    
    if parse_mode:
        payload["parse_mode"] = parse_mode

    # Retry mechanism with exponential backoff
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info(f"Message sent successfully on attempt {attempt + 1}")
            return True
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt == max_retries - 1:
                logger.error(f"Failed to send Telegram message after {max_retries} attempts")
                return False
            time.sleep(2 ** (attempt + 1))
    
    return False