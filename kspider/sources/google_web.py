from __future__ import annotations

import base64
import re
import subprocess
import time
from datetime import datetime, timezone
from typing import List
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from ..models import SearchResult


def _parse_snippet_date(text: str) -> str | None:
    """Extract 'Apr 25, 2026' style dates Bing embeds at the start of snippets."""
    m = re.search(
        r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}',
        text or "",
    )
    if m:
        try:
            dt = datetime.strptime(m.group(0), "%b %d, %Y")
            return dt.replace(tzinfo=timezone.utc).isoformat()
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


def _decode_bing_url(href: str) -> str:
    """Unwrap bing.com/ck/a?... redirect to the real destination URL."""
    if not href.startswith("https://www.bing.com/ck/"):
        return href
    try:
        u = parse_qs(urlparse(href).query).get("u", [""])[0]
        # Bing prefixes base64 payload with "a1"
        if u.startswith("a1"):
            u = u[2:]
        # Re-pad and decode
        padded = u + "=" * (-len(u) % 4)
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore") or href
    except Exception:
        return href


_TRACKING_PARAMS = frozenset({
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term',
    'fbclid', 'gclid', 'msclkid', 'ocid', 'ref', 'ceid', 'form', 'mkt', 'msockid',
})

def _strip_tracking(url: str) -> str:
    """Remove Bing/Google session tracking params that change per-crawl."""
    try:
        p = urlparse(url)
        qs = {k: v for k, v in parse_qs(p.query, keep_blank_values=True).items()
              if k not in _TRACKING_PARAMS}
        return urlunparse((p.scheme, p.netloc, p.path, p.params, urlencode(qs, doseq=True), ''))
    except Exception:
        return url


def _domain_from_cite(cite_text: str) -> str:
    raw = cite_text.split("›")[0].strip()  # strip breadcrumb › parts
    if raw.startswith("http"):
        return urlparse(raw).netloc or raw
    return raw


def search(query: str, max_results: int = 30) -> List[SearchResult]:
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(_RETRIES):
        if attempt:
            time.sleep(_BACKOFF * attempt)
        try:
            url = (
                f"https://www.bing.com/search"
                f"?q={quote(query)}&count={max_results}"
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
            for item in soup.select("li.b_algo")[:max_results]:
                h2 = item.find("h2")
                a = h2.find("a") if h2 else None
                if not a:
                    continue
                title = a.get_text(strip=True)
                href = _strip_tracking(_decode_bing_url(a.get("href", "")))
                if not href or not title:
                    continue

                cite = item.find("cite")
                domain = _domain_from_cite(cite.get_text(strip=True)) if cite else urlparse(href).netloc

                caption = item.find("div", class_="b_caption") or item.find("p")
                snippet = caption.get_text(strip=True) if caption else None
                published_at = _parse_snippet_date(snippet)

                results.append(SearchResult(
                    query=query,
                    source="Bing",
                    title=title,
                    url=href,
                    snippet=snippet or None,
                    source_domain=domain or None,
                    published_at=published_at,
                ))
            return results
        except Exception as exc:
            last_exc = exc
    raise RuntimeError(f"Bing search failed for {query!r}: {last_exc}") from last_exc
