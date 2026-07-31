from __future__ import annotations

import calendar
from datetime import datetime, timezone
from typing import List
from urllib.parse import urlencode

import feedparser

from ..models import SearchResult

_BASE = "https://news.google.com/rss/search"
_SITE = "site:charlotteobserver.com"
_DAYS = 30


def search(query: str = "Kannapolis", max_results: int = 30) -> List[SearchResult]:
    """Fetch Charlotte Observer articles matching query via a Google News RSS site search."""
    q = f"{query} {_SITE}"
    url = f"{_BASE}?{urlencode({'q': q, 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})}"
    feed = feedparser.parse(url)

    if feed.bozo and not feed.entries:
        raise RuntimeError(f"Charlotte Observer RSS failed: {feed.bozo_exception}")

    results = []
    for entry in feed.entries[:max_results]:
        published_at = None
        pub = getattr(entry, "published_parsed", None)
        if pub:
            published_at = datetime.fromtimestamp(
                calendar.timegm(pub), tz=timezone.utc
            ).isoformat()

        title = entry.get("title", "")
        # Strip trailing " - Charlotte Observer" attribution Google appends
        if title.endswith(" - Charlotte Observer"):
            title = title[: -len(" - Charlotte Observer")]

        results.append(SearchResult(
            query=query,
            source="CharlotteObserver",
            title=title,
            url=entry.get("link", ""),
            snippet=entry.get("summary"),
            source_domain="charlotteobserver.com",
            published_at=published_at,
        ))

    return results
