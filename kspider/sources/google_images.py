from __future__ import annotations

import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from typing import List
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup

from ..models import SearchResult


def _parse_age_label(aria_label: str) -> str | None:
    """Convert Bing's aria-label to ISO timestamp.

    Handles two formats:
      '1 hour ago' / '17 days ago'  →  relative offset
      '4/25/2026'                   →  absolute M/D/YYYY date
    """
    s = (aria_label or "").strip()
    # Relative: "1 hour ago", "17 days ago", "30 minutes ago"
    m = re.match(r'(\d+)\s+(minute|hour|day)s?\s+ago', s.lower())
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {"minute": timedelta(minutes=n), "hour": timedelta(hours=n), "day": timedelta(days=n)}[unit]
        return (datetime.now(timezone.utc) - delta).isoformat()
    # Absolute: "4/25/2026"
    m2 = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', s)
    if m2:
        try:
            dt = datetime(int(m2.group(3)), int(m2.group(1)), int(m2.group(2)), tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            pass
    return None

_RETRIES = 3
_BACKOFF = 5
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.4 Safari/605.1.15"
)


def search(query: str, max_results: int = 30) -> List[SearchResult]:
    """Fetch same-day Bing News results for query, sorted by date."""
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(_RETRIES):
        if attempt:
            time.sleep(_BACKOFF * attempt)
        try:
            url = (
                f"https://www.bing.com/news/search"
                f"?q={quote(query)}&freshness=Day&sortby=Date&count={max_results}"
            )
            result = subprocess.run(
                ["curl", "-sf", "--max-time", "15",
                 "-H", f"User-Agent: {_UA}",
                 "-H", "Accept-Language: en-US,en;q=0.9",
                 url],
                capture_output=True, text=True, timeout=20,
            )
            if result.returncode != 0:
                raise RuntimeError(f"curl error: {result.stderr.strip()}")

            soup = BeautifulSoup(result.stdout, "lxml")
            results = []
            for card in soup.select("div.news-card")[:max_results]:
                a = card.select_one("a.title")
                if not a:
                    continue
                title = a.get_text(strip=True)
                href = a.get("href", "")
                if not href or not title:
                    continue

                snippet_el = card.select_one(".snippet")
                snippet = snippet_el.get_text(strip=True) if snippet_el else None

                source_el = card.select_one(".source")
                source_text = source_el.get_text(strip=True) if source_el else ""
                source_name = re.sub(r'\s*\d+[mhd]$', '', source_text).strip() or None

                # Extract published time from aria-label on the age span
                age_span = card.select_one("span[aria-label]")
                published_at = _parse_age_label(age_span.get("aria-label", "") if age_span else "")

                results.append(SearchResult(
                    query=query,
                    source="Bing News",
                    title=title,
                    url=href,
                    snippet=snippet or None,
                    source_domain=source_name or urlparse(href).netloc or None,
                    published_at=published_at,
                ))
            if not results:
                raise RuntimeError("no news cards found — Bing may have blocked the request")
            return results
        except Exception as exc:
            last_exc = exc
    raise RuntimeError(f"Bing News search failed for {query!r}: {last_exc}") from last_exc
