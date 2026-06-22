"""NewsFetcher: Fetch IT news from RSS feeds with TTL filtering."""

import concurrent.futures
import html
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import feedparser
import urllib3
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

http = urllib3.PoolManager(timeout=urllib3.Timeout(total=10))

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

    def fetch_raw_news(self, max_age_hours: int = 24) -> list[dict]:
        """Fetch raw news pool from RSS."""
        raw_news = []
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        def fetch_single_feed(feed_url: str) -> list[dict]:
            local_news = []
            try:
                resp = http.request("GET", feed_url, timeout=10)
                feed = feedparser.parse(resp.data)
                logger.debug("Feed parsed", extra={"entries": len(feed.entries)})
                for entry in feed.entries:
                    pub_date_str = (
                        entry.get("published")
                        or entry.get("updated")
                        or entry.get("lastmod")
                        or entry.get("news_publication_date")
                    )
                    pub_date = self._parse_date(pub_date_str)
                    if pub_date is None or pub_date < cutoff_time:
                        continue
                    link = normalize_url(entry.get("link", ""))
                    local_news.append(
                        {
                            "title": entry.get("title", "No title"),
                            "link": link,
                            "summary": clean_html_text(entry.get("summary", ""))[:350],
                            "domain": extract_domain(link),
                            "source_region": classify_source_region(link),
                            "feed_url": feed_url,
                        }
                    )
                    # logger.debug(
                    #     "News item added",
                    #     extra={"title": entry.get("title", "No title"), "link": entry.get("link", "")},
                    # )
            except Exception as e:
                logger.warning("Feed fetch failed", extra={"feed_url": feed_url, "error": str(e)})
            return local_news

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.RSS_FEEDS)) as executor:
            results = executor.map(fetch_single_feed, self.RSS_FEEDS)

        for res in results:
            raw_news.extend(res)

        for i, news in enumerate(raw_news):
            news["index"] = i
        logger.info("Raw news pool fetched", extra={"count": len(raw_news), "feeds": len(self.RSS_FEEDS)})
        return raw_news

    def fetch_deep_article_data(self, url: str) -> dict:
        """Scrape the article page for og:image (or first img) and main paragraph text."""
        url = normalize_url(url)
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        try:
            resp = http.request("GET", url, headers=headers, timeout=8)
            if resp.status >= 400:
                logger.warning("Deep scrape HTTP error", extra={"url": url, "status": resp.status})
                return {"image_url": "", "full_text": "", "full_text_chars": 0}
            html_content = resp.data.decode("utf-8", errors="replace")
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
            logger.warning("Deep scrape failed", extra={"url": url, "error": str(e)})
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
