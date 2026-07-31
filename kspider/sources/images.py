from __future__ import annotations

import time
from typing import List
from urllib.parse import urlparse

from ddgs import DDGS

from ..models import SearchResult

_RETRIES = 3
_BACKOFF = 10  # seconds between retries (DDG rate-limits aggressively)


def search(query: str, max_results: int = 30) -> List[SearchResult]:
    """Fetch DuckDuckGo image search results for query."""
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(_RETRIES):
        if attempt:
            time.sleep(_BACKOFF * attempt)
        try:
            results = []
            with DDGS(timeout=20) as ddgs:
                for r in ddgs.images(query, max_results=max_results):
                    results.append(SearchResult(
                        query=query,
                        source="DuckDuckGo Images",
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        thumbnail_url=r.get("thumbnail"),
                        source_domain=urlparse(r.get("url", "")).netloc or None,
                    ))
            return results
        except Exception as exc:
            if "No results found" in str(exc):
                return []
            last_exc = exc
    raise RuntimeError(f"Image search failed for {query!r}: {type(last_exc).__name__}: {last_exc}") from last_exc
