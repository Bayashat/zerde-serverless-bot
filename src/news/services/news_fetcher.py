"""NewsFetcher: Fetch IT news from RSS feeds with TTL filtering."""

import concurrent.futures
from datetime import datetime, timedelta, timezone
from typing import Optional

import feedparser
from aws_lambda_powertools import Logger

logger = Logger()


class NewsFetcher:
    """
    RSS news aggregator with parallel fetching and TTL filtering.

    Fetches news items from multiple RSS feeds concurrently and filters
    by publish date (max_age_hours) to ensure only fresh content.
    """

    RSS_FEEDS = [
        # --- TIER 1: Macro-economy, Big Tech, Investments ---
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910",
        "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
        "https://techcrunch.com/feed/",
        "https://venturebeat.com/feed/",
        # --- TIER 2: Global trends and hardware ---
        "https://www.theverge.com/rss/index.xml",
        "https://feeds.arstechnica.com/arstechnica/index",
        "https://www.wired.com/feed/rss",
        "https://www.theregister.com/headlines.atom",
        # --- TIER 3: Specialized (AI and Cybersecurity) ---
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.bleepingcomputer.com/feed/",
    ]

    def fetch_raw_news(self, items_per_feed: int = 15, max_age_hours: int = 24) -> list[dict]:
        """Fetch raw news pool within TTL using ThreadPoolExecutor."""
        raw_news = []
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        def fetch_single_feed(feed_url: str) -> list[dict]:
            local_news = []
            try:
                feed = feedparser.parse(feed_url)

                for entry in feed.entries[:items_per_feed]:
                    pub_date = self._parse_date(entry.get("published"))

                    if pub_date is None or pub_date < cutoff_time:
                        continue

                    local_news.append(
                        {
                            "title": entry.get("title", "No title"),
                            "summary": entry.get("summary", "")[:250],
                            "link": entry.get("link", ""),
                            "published": pub_date,
                            "source": feed.feed.get("title", "Unknown") if hasattr(feed, "feed") else "Unknown",
                        }
                    )
            except Exception:
                logger.warning(f"Failed to fetch {feed_url}", exc_info=True)

            return local_news

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(fetch_single_feed, self.RSS_FEEDS)

        for res in results:
            raw_news.extend(res)

        for i, news in enumerate(raw_news):
            news["id"] = i

        return raw_news

    def _parse_date(self, date_string: Optional[str]) -> Optional[datetime]:
        """Parse RSS date string to timezone-aware datetime."""
        if not date_string:
            return None

        try:
            from email.utils import parsedate_to_datetime

            dt = parsedate_to_datetime(date_string)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            # On parse failure, return None so malformed/unknown dates are filtered out by TTL logic
            return None
