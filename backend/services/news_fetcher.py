import logging
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"


class NewsFetcher:
    def __init__(self, timeout: float = 8.0):
        self._timeout = timeout
        self._cache: dict[str, list[str]] = {}

    async def fetch_headlines(self, query: str, limit: int = 5) -> list[str]:
        cache_key = query.lower().strip()
        if cache_key in self._cache:
            return self._cache[cache_key][:limit]

        headlines: list[str] = []
        try:
            params = {
                "q": query,
                "hl": "en-US",
                "gl": "US",
                "ceid": "US:en",
            }
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(GOOGLE_NEWS_RSS, params=params)
                resp.raise_for_status()
                root = ET.fromstring(resp.text)
                for item in root.iter("item"):
                    title_el = item.find("title")
                    if title_el is not None and title_el.text:
                        headlines.append(title_el.text.strip())
                    if len(headlines) >= limit:
                        break
        except Exception as e:
            logger.warning("News fetch failed for '%s': %s", query, e)

        self._cache[cache_key] = headlines
        if len(self._cache) > 200:
            oldest = next(iter(self._cache))
            del self._cache[oldest]

        return headlines[:limit]

    def clear_cache(self):
        self._cache.clear()


news_fetcher = NewsFetcher()
