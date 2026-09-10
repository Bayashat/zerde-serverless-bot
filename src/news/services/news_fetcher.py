"""NewsFetcher: Fetch IT news from RSS feeds with TTL filtering."""

import asyncio
import html
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import feedparser
from core.logger import LoggerAdapter, get_logger
from services.deadline import request_bytes

logger = LoggerAdapter(get_logger(__name__), {})


_KZ_DOMAINS = ("digitalbusiness.kz", "profit.kz")
_REGIONAL_DOMAINS = ("tproger.ru",)


def normalize_url(url: str) -> str:
    """Return a request-safe URL, repairing common RSS whitespace glitches."""
    cleaned = " ".join((url or "").strip().split())
    if not cleaned:
        return ""
    parts = urlsplit(cleaned)
    path = re.sub(r"\s+", "-", parts.path) if parts.netloc.endswith("aws.amazon.com") else parts.path
    path = quote(path, safe="/:%")
    query = quote(parts.query, safe="=&?/:,+%")
    fragment = quote(parts.fragment, safe="=&?/:,+%")
    return urlunsplit((parts.scheme, parts.netloc, path, query, fragment))


def extract_domain(url: str) -> str:
    """Return a normalized hostname without a leading www."""
    netloc = urlsplit(normalize_url(url)).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def classify_source_region(url: str) -> str:
    """Classify source geography for digest ranking."""
    domain = extract_domain(url)
    if domain.endswith(_KZ_DOMAINS):
        return "kz"
    if domain.endswith(_REGIONAL_DOMAINS):
        return "regional"
    return "global"


def clean_html_text(value: str) -> str:
    """Strip simple RSS/HTML markup into compact text."""
    if not value:
        return ""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


class NewsFetcher:
    """
    RSS news aggregator with parallel fetching and TTL filtering.

    Fetches news items from multiple RSS feeds concurrently and filters
    by publish date (max_age_hours) to ensure only fresh content.
    """

    RSS_FEEDS = [
        # --- TIER 1: Macro-economy, Big Tech, Investments ---
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910",
        "https://techcrunch.com/feed/",
        "https://venturebeat.com/feed/",
        # --- TIER 2: Global trends and hardware ---
        "https://www.theverge.com/rss/index.xml",
        "https://feeds.arstechnica.com/arstechnica/index",
        "https://www.wired.com/feed/rss",
        "https://www.theregister.com/headlines.atom",
        # --- TIER 3: Specialized (AI and Cybersecurity) ---
        "https://www.bleepingcomputer.com/feed/",
        # --- TIER 4: Hardcore Engineering & Cloud Infrastructure ---
        "https://hnrss.org/frontpage",
        "https://thenewstack.io/feed/",
        "https://feed.infoq.com/",
        "https://aws.amazon.com/about-aws/whats-new/recent/feed/",
        "https://blog.cloudflare.com/rss/",
        # --- TIER 5: Regional & Developer Communities ---
        "https://profit.kz/rss/news/",
        "https://digitalbusiness.kz/feed/",
        "https://tproger.ru/feed/",
    ]

    async def fetch_raw_news(self, deadline, max_age_hours: int = 24) -> list[dict]:
        """Bound all RSS work to 15 seconds, retaining completed sources on timeout."""
        raw_news = []
        completed = []
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        semaphore = asyncio.Semaphore(5)

        async def fetch_single_feed(feed_url):
            async with semaphore:
                try:
                    status, body = await request_bytes(
                        "GET", feed_url, deadline=deadline, cap=10, max_bytes=512000, follow_redirects=True
                    )
                    if status >= 400:
                        raise ValueError("RSS HTTP failure")
                    feed = feedparser.parse(body)
                    if feed.bozo and not feed.entries:
                        raise ValueError("RSS did not contain a readable feed")
                    local = []
                    for entry in feed.entries[:200]:
                        stamp = (
                            entry.get("published")
                            or entry.get("updated")
                            or entry.get("lastmod")
                            or entry.get("news_publication_date")
                        )
                        published = self._parse_date(stamp)
                        if published is None or published < cutoff_time:
                            continue
                        link = normalize_url(entry.get("link", ""))
                        local.append(
                            {
                                "title": entry.get("title", "No title"),
                                "link": link,
                                "summary": clean_html_text(entry.get("summary", ""))[:350],
                                "domain": extract_domain(link),
                                "source_region": classify_source_region(link),
                                "feed_url": feed_url,
                            }
                        )
                    raw_news.extend(local)
                    completed.append(feed_url)
                except Exception as exc:
                    logger.warning("News feed failed", extra={"error_type": type(exc).__name__})

        tasks = [asyncio.create_task(fetch_single_feed(url)) for url in self.RSS_FEEDS]
        try:
            async with deadline.timeout(15):
                await asyncio.gather(*tasks)
        except TimeoutError:
            logger.warning("RSS stage deadline reached", extra={"completed_feeds": len(completed)})
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        if not completed:
            raise RuntimeError("No news feed completed successfully")
        for index, article in enumerate(raw_news):
            article["index"] = index
        logger.info("Raw news pool fetched", extra={"count": len(raw_news), "completed_feeds": len(completed)})
        return raw_news

    async def fetch_deep_article_data(self, url: str, deadline) -> dict:
        """Scrape the article page for og:image (or first img) and main paragraph text."""
        url = normalize_url(url)
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        try:
            status, body = await request_bytes(
                "GET", url, deadline=deadline, cap=8, max_bytes=1000000, headers=headers, follow_redirects=True
            )
            if status >= 400:
                logger.warning("Deep scrape HTTP error", extra={"url": url, "status": status})
                return {"image_url": "", "full_text": "", "full_text_chars": 0}
            html_content = body.decode("utf-8", errors="replace")
            image_url = ""

            # Prefer og:image / twitter:image, then first content img
            patterns = [
                r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
                r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:image["\']',
                r'<meta\s+name=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']',
                r'<meta\s+property=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']',
                r'<img[^>]+src=["\']([^"\']+(?:jpg|jpeg|png|webp)(?:\?[^"\']*)?)["\']',
            ]
            for pattern in patterns:
                match = re.search(pattern, html_content, re.IGNORECASE)
                if match:
                    extracted_url = match.group(1).strip()
                    extracted_url = html.unescape(extracted_url)
                    image_url = urljoin(url, extracted_url)
                    if image_url.startswith("http"):
                        break

            p_tags = re.findall(r"<p[^>]*>(.*?)</p>", html_content, re.IGNORECASE | re.DOTALL)
            paragraphs = [clean_html_text(p) for p in p_tags]
            clean_text = " ".join([p for p in paragraphs if len(p) > 50])
            full_text = clean_text[:3000]
            logger.debug("Deep scrape success", extra={"url": url, "image_found": image_url})
            return {"image_url": image_url, "full_text": full_text, "full_text_chars": len(full_text)}
        except Exception as e:
            logger.warning("Deep scrape failed", extra={"error_type": type(e).__name__})
            return {"image_url": "", "full_text": "", "full_text_chars": 0}

    def _parse_date(self, date_string: Optional[str]) -> Optional[datetime]:
        """Parse RSS date string to timezone-aware UTC datetime."""
        if not date_string:
            return None
        try:
            dt = parsedate_to_datetime(date_string)
        except Exception:
            try:
                dt = datetime.fromisoformat(date_string)
            except Exception:
                return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
