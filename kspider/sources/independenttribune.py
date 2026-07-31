from __future__ import annotations

import calendar
import subprocess
import time
from datetime import datetime, timezone
from typing import List
from urllib.parse import urlencode

import feedparser

from ..models import SearchResult

_BASE = "https://independenttribune.com/search/"
_DAYS = 30
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.4 Safari/605.1.15"
)


def search(query: str = "Kannapolis", max_results: int = 30) -> List[SearchResult]:
    """Fetch Kannapolis articles from the Independent Tribune via its BLOX RSS search."""
    url = f"{_BASE}?{urlencode({'f': 'rss', 't': 'article', 'q': 'kannapolis', 'l': max_results, 's': 'start_time', 'sd': 'desc'})}"
    result = subprocess.run(
        ["curl", "-sL", "--max-time", "15", "-H", f"User-Agent: {_UA}", url],
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl error: {result.stderr.strip()}")
    feed = feedparser.parse(result.stdout)

    if feed.bozo and not feed.entries:
        raise RuntimeError(f"Independent Tribune RSS failed: {feed.bozo_exception}")

    cutoff = time.time() - (_DAYS * 86_400)
    results = []

    for entry in feed.entries:
        if len(results) >= max_results:
            break

        pub_parsed = getattr(entry, "published_parsed", None)
        if pub_parsed and calendar.timegm(pub_parsed) < cutoff:
            continue

        published_at = (
            datetime.fromtimestamp(calendar.timegm(pub_parsed), tz=timezone.utc).isoformat()
            if pub_parsed else None
        )

        # Thumbnail from enclosure tag
        thumbnail_url = None
        enclosures = getattr(entry, "enclosures", [])
        if enclosures:
            thumbnail_url = enclosures[0].get("url") or None

        results.append(SearchResult(
            query=query,
            source="IndependentTribune",
            title=entry.get("title", ""),
            url=entry.get("link", ""),
            snippet=entry.get("summary") or None,
            thumbnail_url=thumbnail_url,
            source_domain="independenttribune.com",
            published_at=published_at,
        ))

    return results
