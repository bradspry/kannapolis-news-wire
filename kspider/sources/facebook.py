from __future__ import annotations

import time
from datetime import date, timedelta
from typing import List
from urllib.parse import urlparse

from googlesearch import search as _gsearch

from ..models import SearchResult

_RETRIES = 3
_BACKOFF = 5


def search(query: str, max_results: int = 30) -> List[SearchResult]:
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    scoped = f"site:facebook.com {query} after:{yesterday}"

    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(_RETRIES):
        if attempt:
            time.sleep(_BACKOFF * attempt)
        try:
            results = []
            for r in _gsearch(scoped, num_results=max_results, advanced=True, sleep_interval=1):
                results.append(SearchResult(
                    query=query,
                    source="Facebook",
                    title=r.title or "",
                    url=r.url,
                    snippet=r.description,
                    source_domain=urlparse(r.url).netloc or None,
                ))
            return results
        except Exception as exc:
            last_exc = exc
    raise RuntimeError(f"Facebook search failed for {query!r}: {last_exc}") from last_exc
