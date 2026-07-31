from __future__ import annotations

import calendar
import time
from typing import List
from urllib.parse import urlencode

import feedparser

from ..models import SearchResult

# Official Google News RSS — no scraping needed, publicly provided by Google
_BASE = "https://news.google.com/rss/search"
_24H = 86400


def search(query: str, max_results: int = 30) -> List[SearchResult]:
    url = f"{_BASE}?{urlencode({'q': query, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})}"
    feed = feedparser.parse(url)

    if feed.bozo and not feed.entries:
        raise RuntimeError(f"News RSS failed for {query!r}: {feed.bozo_exception}")

    cutoff = time.time() - _24H
    results = []

    for entry in feed.entries:
        if len(results) >= max_results:
            break

        # Drop entries older than 24 hours
        pub_parsed = getattr(entry, "published_parsed", None)
        if pub_parsed:
            if calendar.timegm(pub_parsed) < cutoff:
                continue

        source_name = None
        if hasattr(entry, "source") and hasattr(entry.source, "title"):
            source_name = entry.source.title

        published = getattr(entry, "published", None)
        url_str = entry.get("link", "")

        results.append(SearchResult(
            query=query,
            source="Google News",
            title=entry.get("title", ""),
            url=url_str,
            snippet=entry.get("summary"),
            source_domain=source_name,
            published_at=published,
        ))

    return results
