from __future__ import annotations

import time
from datetime import date, timedelta
from typing import List
from urllib.parse import urlparse

from googlesearch import search as _gsearch

from ..models import SearchResult

_RETRIES = 3
_BACKOFF = 5
_HASHTAG = "#kannapolis"


def _fetch_scoped(scoped: str, query: str, max_results: int) -> List[SearchResult]:
    """Run one site-scoped Google search query and wrap the results as Instagram hits."""
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(_RETRIES):
        if attempt:
            time.sleep(_BACKOFF * attempt)
        try:
            results = []
            for r in _gsearch(scoped, num_results=max_results, advanced=True, sleep_interval=1):
                results.append(SearchResult(
                    query=query,
                    source="Instagram",
                    title=r.title or "",
                    url=r.url,
                    snippet=r.description,
                    source_domain=urlparse(r.url).netloc or None,
                ))
            return results
        except Exception as exc:
            last_exc = exc
    raise RuntimeError(f"Instagram search failed for {scoped!r}: {last_exc}") from last_exc


def search(query: str, max_results: int = 30) -> List[SearchResult]:
    """Find recent public Instagram posts matching query or the local hashtag, deduped by URL."""
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    seen: set = set()
    results: List[SearchResult] = []

    for scoped in [
        f'site:instagram.com {query} after:{yesterday}',
        f'site:instagram.com "{_HASHTAG}" after:{yesterday}',
    ]:
        for r in _fetch_scoped(scoped, query, max_results):
            if r.url not in seen:
                seen.add(r.url)
                results.append(r)

    return results
