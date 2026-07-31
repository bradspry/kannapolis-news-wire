from __future__ import annotations

import calendar
import re
import time
from datetime import datetime, timezone
from typing import List

import feedparser

from ..models import SearchResult

_FEED = "https://cabarruscompass.com/feed"
_DAYS = 90


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def search(query: str = "", max_results: int = 50) -> List[SearchResult]:
    """Fetch recent posts from The Cabarrus Compass (Substack RSS)."""
    feed = feedparser.parse(_FEED)

    if feed.bozo and not feed.entries:
        raise RuntimeError(f"Cabarrus Compass RSS failed: {feed.bozo_exception}")

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
        snippet = _strip_html(entry.get("summary", ""))[:300] or None

        results.append(SearchResult(
            query=query,
            source="CabarrusCompass",
            title=entry.get("title", ""),
            url=entry.get("link", ""),
            snippet=snippet,
            source_domain="cabarruscompass.com",
            published_at=published_at,
        ))

    return results
