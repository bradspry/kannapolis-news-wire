from __future__ import annotations

import html
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from typing import List
from urllib.parse import urlencode

from ..models import SearchResult

_BASE = "https://www.salisburypost.com/wp-json/wp/v2/posts"
_DAYS = 30
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.4 Safari/605.1.15"
)
_RETRIES = 3
_BACKOFF = 5


def _strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities, leaving plain text."""
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def search(query: str = "Kannapolis", max_results: int = 30) -> List[SearchResult]:
    """Fetch Kannapolis articles from the Salisbury Post via WordPress REST API."""
    cutoff = time.time() - (_DAYS * 86_400)
    params = urlencode({
        "search": "kannapolis",
        "per_page": max_results,
        "orderby": "date",
        "order": "desc",
        "_fields": "id,title,link,excerpt,date,jetpack_featured_media_url",
    })
    url = f"{_BASE}?{params}"

    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(_RETRIES):
        if attempt:
            time.sleep(_BACKOFF * attempt)
        try:
            result = subprocess.run(
                ["curl", "-sL", "--max-time", "15", "-H", f"User-Agent: {_UA}", url],
                capture_output=True, text=True, timeout=20,
            )
            if result.returncode != 0:
                raise RuntimeError(f"curl error: {result.stderr.strip()}")

            posts = json.loads(result.stdout)
            if not isinstance(posts, list):
                raise RuntimeError(f"unexpected response: {result.stdout[:200]}")

            results = []
            for post in posts:
                date_str = post.get("date", "")
                try:
                    # date is local ET — store as-is with UTC marker (close enough for display)
                    dt = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
                    if dt.timestamp() < cutoff:
                        continue
                    published_at = dt.isoformat()
                except (ValueError, TypeError):
                    published_at = None

                title = _strip_html(post.get("title", {}).get("rendered", ""))
                snippet = _strip_html(post.get("excerpt", {}).get("rendered", "")) or None
                thumb = post.get("jetpack_featured_media_url") or None

                results.append(SearchResult(
                    query=query,
                    source="SalisburyPost",
                    title=title,
                    url=post.get("link", ""),
                    snippet=snippet,
                    thumbnail_url=thumb,
                    source_domain="salisburypost.com",
                    published_at=published_at,
                ))
            return results
        except Exception as exc:
            last_exc = exc
    raise RuntimeError(f"Salisbury Post fetch failed: {last_exc}") from last_exc
