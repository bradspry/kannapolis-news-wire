from __future__ import annotations

import time
from typing import List
from urllib.parse import urlparse

from ddgs import DDGS

from ..models import SearchResult

_RETRIES = 3
_BACKOFF = 10  # seconds between retries (DDG rate-limits aggressively)


def search(query: str, max_results: int = 30) -> List[SearchResult]:
    """Fetch same-day DuckDuckGo news results for query."""
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(_RETRIES):
        if attempt:
            time.sleep(_BACKOFF * attempt)
        try:
            results = []
            with DDGS(timeout=20) as ddgs:
                for r in ddgs.news(query, max_results=max_results, timelimit="d"):
                    results.append(SearchResult(
                        query=query,
                        source="DuckDuckGo",
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        snippet=r.get("body"),
                        source_domain=r.get("source") or urlparse(r.get("url", "")).netloc or None,
                        published_at=r.get("date") or None,
                    ))
            return results
        except Exception as exc:
            if "No results found" in str(exc):
                return []
            last_exc = exc
    raise RuntimeError(f"Web search failed for {query!r}: {type(last_exc).__name__}: {last_exc}") from last_exc
