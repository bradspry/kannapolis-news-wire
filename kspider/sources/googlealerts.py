from __future__ import annotations

import calendar
import html
import re
from datetime import datetime, timezone
from typing import List
from urllib.parse import parse_qs, urlparse

import feedparser

from ..models import SearchResult

_FEED_URL = "https://www.google.com/alerts/feeds/12784550432978592657/5505019587260315967"


def _unwrap_url(href: str) -> str:
    """Extract real destination from Google redirect URL."""
    real = parse_qs(urlparse(href).query).get("url", [""])[0]
    return real or href


def _strip_tags(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def search(query: str = "Kannapolis", max_results: int = 30) -> List[SearchResult]:
    feed = feedparser.parse(_FEED_URL)
    results = []
    for entry in feed.entries[:max_results]:
        title = _strip_tags(entry.get("title", ""))
        url = _unwrap_url(entry.get("link", ""))
        snippet = _strip_tags(entry.get("summary", "")) or None
        domain = urlparse(url).netloc or None

        published_at = None
        pub = entry.get("published_parsed")
        if pub:
            published_at = datetime.fromtimestamp(
                calendar.timegm(pub), tz=timezone.utc
            ).isoformat()

        results.append(SearchResult(
            query=query,
            source="Google Alerts",
            title=title,
            url=url,
            snippet=snippet,
            source_domain=domain,
            published_at=published_at,
        ))
    return results
