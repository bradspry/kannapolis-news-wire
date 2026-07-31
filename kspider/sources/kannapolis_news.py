from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone
from typing import List

from bs4 import BeautifulSoup

from ..models import SearchResult

_URL = "https://www.kannapolisnc.gov/news"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.4 Safari/605.1.15"
)
_RETRIES = 3
_BACKOFF = 5


def _parse_date(text: str) -> str | None:
    text = text.strip()
    for fmt in ("%m/%d/%Y", "%m/%#d/%Y"):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            pass
    return None


def search(query: str = "Kannapolis", max_results: int = 30) -> List[SearchResult]:
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(_RETRIES):
        if attempt:
            time.sleep(_BACKOFF * attempt)
        try:
            result = subprocess.run(
                ["curl", "-s", "--max-time", "15", "-H", f"User-Agent: {_UA}", _URL],
                capture_output=True, text=True, timeout=20,
            )
            if result.returncode != 0:
                raise RuntimeError(f"curl error: {result.stderr.strip()}")

            soup = BeautifulSoup(result.stdout, "lxml")
            results = []
            for item in soup.select("div.article")[:max_results]:
                a = item.find("a", href=lambda h: h and "/news/ID/" in h)
                if not a:
                    continue
                title = a.get_text(strip=True)
                href = a.get("href", "")
                if not title or not href:
                    continue

                date_div = item.find("div", class_="articleAuthor")
                published_at = _parse_date(date_div.get_text()) if date_div else None

                entry_div = item.find("div", class_="articleEntry")
                snippet = entry_div.get_text(" ", strip=True) or None if entry_div else None

                results.append(SearchResult(
                    query=query,
                    source="KannapolisNC",
                    title=title,
                    url=href,
                    snippet=snippet,
                    source_domain="kannapolisnc.gov",
                    published_at=published_at,
                ))
            return results
        except Exception as exc:
            last_exc = exc
    raise RuntimeError(f"Kannapolis news fetch failed: {last_exc}") from last_exc
