from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import List, Optional

# youtube-search-python passes proxies={} to httpx.post/get(), which httpx>=0.24
# no longer accepts. Patch RequestCore methods directly — module-level httpx.post
# replacement doesn't work because the library binds via its own `import httpx`.
from youtubesearchpython.core.requests import RequestCore as _YTRequestCore
from youtubesearchpython.core.constants import userAgent as _YT_UA
import httpx as _httpx

def _yt_sync_post(self) -> _httpx.Response:
    """Replacement for RequestCore.syncPostRequest compatible with httpx>=0.24's proxies API."""
    return _httpx.post(self.url, headers={"User-Agent": _YT_UA},
                       json=self.data, timeout=self.timeout)

def _yt_sync_get(self) -> _httpx.Response:
    """Replacement for RequestCore.syncGetRequest compatible with httpx>=0.24's proxies API."""
    return _httpx.get(self.url, headers={"User-Agent": _YT_UA},
                      timeout=self.timeout, cookies={"CONSENT": "YES+1"})

_YTRequestCore.syncPostRequest = _yt_sync_post
_YTRequestCore.syncGetRequest  = _yt_sync_get

# youtube-search-python concatenates None ids directly ("…watch?v=" + component['id'])
# when a result is a Short or other non-standard type whose videoId path is absent.
# Wrap all three component builders to catch that TypeError and return a stub with
# link=None; our parsing loop below then skips stubs via `if not url`.
from youtubesearchpython.handlers.componenthandler import ComponentHandler as _YTCH

def _wrap_component_method(fn):
    """Wrap a component-builder method so a malformed result (missing id) returns None instead of raising."""
    def _safe(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except TypeError:
            return None
    return _safe

_YTCH._getVideoComponent   = _wrap_component_method(_YTCH._getVideoComponent)
_YTCH._getChannelComponent = _wrap_component_method(_YTCH._getChannelComponent)
_YTCH._getPlaylistComponent = _wrap_component_method(_YTCH._getPlaylistComponent)

from youtubesearchpython import CustomSearch, VideoUploadDateFilter

from ..models import SearchResult

_RETRIES = 3
_BACKOFF = 5


def _parse_relative_time(s: Optional[str]) -> Optional[str]:
    """Convert YouTube's relative timestamps ('3 hours ago') to ISO datetime."""
    if not s:
        return None
    s = s.lower().strip()
    try:
        parts = s.split()
        if len(parts) >= 3 and parts[2] == "ago":
            n = int(parts[0])
            unit = parts[1]
            now = datetime.utcnow()
            if "minute" in unit:
                dt = now - timedelta(minutes=n)
            elif "hour" in unit:
                dt = now - timedelta(hours=n)
            elif "day" in unit:
                dt = now - timedelta(days=n)
            elif "week" in unit:
                dt = now - timedelta(weeks=n)
            elif "month" in unit:
                dt = now - timedelta(days=n * 30)
            elif "year" in unit:
                dt = now - timedelta(days=n * 365)
            else:
                return None
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, IndexError):
        pass
    return None


def search(query: str, max_results: int = 30) -> List[SearchResult]:
    """Fetch this week's YouTube videos matching query."""
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(_RETRIES):
        if attempt:
            time.sleep(_BACKOFF * attempt)
        try:
            vs = CustomSearch(query, VideoUploadDateFilter.thisWeek, limit=max_results)
            data = vs.result()
            results = []
            for r in data.get("result", []):
                if not r:
                    continue
                url = r.get("link") or ""
                if not url:
                    continue
                thumbnails = r.get("thumbnails") or []
                thumb = thumbnails[0].get("url") if thumbnails else None
                desc_parts = r.get("descriptionSnippet") or []
                snippet = "".join(p.get("text", "") for p in desc_parts) or None
                channel = (r.get("channel") or {}).get("name", "")
                view_count = ((r.get("viewCount") or {}).get("short") or "").replace(" views", "")
                duration = r.get("duration") or ""
                extra = " · ".join(p for p in [channel, view_count, duration] if p)
                if snippet and extra:
                    snippet = f"{extra} — {snippet}"
                elif extra:
                    snippet = extra
                results.append(SearchResult(
                    query=query,
                    source="YouTube",
                    title=r.get("title", ""),
                    url=url,
                    snippet=snippet,
                    thumbnail_url=thumb,
                    source_domain="www.youtube.com",
                    published_at=_parse_relative_time(r.get("publishedTime")),
                ))
            return results
        except Exception as exc:
            last_exc = exc
    raise RuntimeError(f"YouTube search failed for {query!r}: {last_exc}") from last_exc
