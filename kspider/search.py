from __future__ import annotations

import re
import time
from typing import Callable, List, Optional, Tuple
from urllib.parse import urlparse, urlencode, parse_qs

from .db import Database
from .models import SearchResult
from .sources import web, images, news, google_web, google_images, facebook, instagram, youtube, civicclerk, publicnotices, cabarruscompass, independenttribune, salisburypost, googlealerts, kannapolis_news, ncdot, charlotteobserver, cabarruscommissioners, concord_lake_levels

_INTER_FETCH_DELAY = 2   # seconds between DDG calls
_GOOGLE_SCRAPE_DELAY = 4  # seconds between Google scraping calls

DEFAULT_QUERIES = [
    "Kannapolis",
    "Kannapolis, NC",
    "Kannapolis, North Carolina",
]

ALL_SOURCES = [
    "CivicClerk",
    "KannapolisNC",
    "ConcordLakeLevels",
    "PublicNotices",
    "CabarrusCompass",
    "IndependentTribune",
    "SalisburyPost",
    "CharlotteObserver",
    "CabarrusCommissioners",
    "NCDMV",
    "DuckDuckGo", "DuckDuckGo Images",
    "Bing", "Bing News", "Google Alerts", "Google News",
    "Facebook", "Instagram", "YouTube",
]

# Run once per crawl regardless of how many queries are in the list
_ONCE_SOURCES = {"CivicClerk", "KannapolisNC", "ConcordLakeLevels", "PublicNotices", "CabarrusCompass", "IndependentTribune", "SalisburyPost", "CharlotteObserver", "CabarrusCommissioners", "Google Alerts", "NCDMV"}
# Skip keyword relevance filter (results are authoritative, not search-engine noise)
_NO_FILTER_SOURCES = {"CivicClerk", "KannapolisNC", "ConcordLakeLevels", "PublicNotices", "CabarrusCompass", "IndependentTribune", "SalisburyPost", "CharlotteObserver", "CabarrusCommissioners", "Google Alerts", "NCDMV"}

_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "fbclid", "gclid", "msclkid", "ocid", "ref", "ceid", "form", "mkt",
})


def _normalize_url(url: str) -> str:
    """Canonical URL for dedup and block matching.

    MSN serves the same article under multiple category paths; reduce to the
    article-ID only.  Also strip common tracking/session query params.
    """
    try:
        p = urlparse(url)
        host = p.netloc.lower()
        if host in ("www.msn.com", "msn.com"):
            parts = [x for x in p.path.split("/") if x]
            for part in reversed(parts):
                if re.match(r'^(ar|vi|bb)-[A-Za-z0-9]+$', part):
                    return f"https://www.msn.com/{part}"
        qs = {k: v for k, v in parse_qs(p.query, keep_blank_values=True).items()
              if k.lower() not in _TRACKING_PARAMS}
        return p._replace(query=urlencode(qs, doseq=True), fragment="").geturl()
    except Exception:
        return url


_FETCHERS = {
    "CivicClerk":           civicclerk.search,
    "KannapolisNC":         kannapolis_news.search,
    "ConcordLakeLevels":    concord_lake_levels.search,
    "PublicNotices":     publicnotices.search,
    "CabarrusCompass":     cabarruscompass.search,
    "IndependentTribune":  independenttribune.search,
    "SalisburyPost":       salisburypost.search,
    "CharlotteObserver":     charlotteobserver.search,
    "CabarrusCommissioners": cabarruscommissioners.search,
    "NCDMV":                 ncdot.search,
    "DuckDuckGo":        web.search,
    "DuckDuckGo Images": images.search,
    "Bing":              google_web.search,
    "Bing News":         google_images.search,
    "Google Alerts":     googlealerts.search,
    "Google News":       news.search,
    "Facebook":          facebook.search,
    "Instagram":         instagram.search,
    "YouTube":           youtube.search,
}

_DDG_SOURCES    = {"DuckDuckGo", "DuckDuckGo Images"}


def _primary_keyword(query: str) -> str:
    """First alphabetic word ≥4 chars from the query, lowercased."""
    words = re.findall(r'[a-zA-Z]{4,}', query)
    return words[0].lower() if words else ""


def _relevant(result, keyword: str) -> bool:
    """True if the keyword appears anywhere in the result's text fields."""
    haystack = " ".join(filter(None, [
        result.title, result.snippet, result.url, result.source_domain
    ])).lower()
    return keyword in haystack
# Google News uses RSS (feedparser) so no scraping throttle needed
_GOOGLE_SCRAPE_SOURCES = {"Bing", "Bing News", "Facebook", "Instagram"}


def run_search(
    db: Database,
    queries: List[str] = DEFAULT_QUERIES,
    sources: List[str] = ALL_SOURCES,
    max_results: int = 30,
    on_progress: Optional[Callable[[str, str, int], None]] = None,
) -> Tuple[int, int]:
    """Fetch results for each query×source and persist to db.

    Returns (run_id, total_inserted).
    """
    run_id = db.new_run(queries, sources)
    blocked = db.blocked_url_set()
    total = 0
    last_ddg_call = 0.0
    last_google_call = 0.0
    fetched_once: set = set()

    for query in queries:
        for source in sources:
            if source in _ONCE_SOURCES:
                if source in fetched_once:
                    continue
                fetched_once.add(source)
            # Throttle DDG requests to avoid rate-limit resets
            if source in _DDG_SOURCES:
                wait = _INTER_FETCH_DELAY - (time.monotonic() - last_ddg_call)
                if wait > 0:
                    time.sleep(wait)
            # Throttle Google scraping calls to reduce bot detection
            elif source in _GOOGLE_SCRAPE_SOURCES:
                wait = _GOOGLE_SCRAPE_DELAY - (time.monotonic() - last_google_call)
                if wait > 0:
                    time.sleep(wait)

            fetcher = _FETCHERS[source]
            try:
                results = fetcher(query, max_results=max_results)
            except RuntimeError as exc:
                if on_progress:
                    on_progress(query, source, -1)
                print(f"  warning: {exc}")
                continue
            finally:
                if source in _DDG_SOURCES:
                    last_ddg_call = time.monotonic()
                elif source in _GOOGLE_SCRAPE_SOURCES:
                    last_google_call = time.monotonic()

            for r in results:
                r.url = _normalize_url(r.url)
            results = [r for r in results if r.url not in blocked]
            if source not in _NO_FILTER_SOURCES:
                kw = _primary_keyword(query)
                if kw:
                    results = [r for r in results if _relevant(r, kw)]
            db.insert_results(run_id, results)
            total += len(results)
            if on_progress:
                on_progress(query, source, len(results))

    return run_id, total
