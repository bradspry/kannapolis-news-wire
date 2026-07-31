from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from typing import List

from ..models import SearchResult

_API     = "https://us-central1-enotice-production.cloudfunctions.net/api/search/public-notices"
_PAPER   = "Concord Independent Tribune"
_PORTAL  = "https://independenttribune.column.us/search"
_DAYS    = 90
_EXCLUDE_TYPES = {"Estate (Probate) Filings", "Notice to Creditors"}
_RETRIES = 3
_BACKOFF = 5


def search(query: str = "Kannapolis", max_results: int = 50) -> List[SearchResult]:
    """Fetch public notices containing 'Kannapolis' from the Concord Independent Tribune."""
    now_ms  = int(time.time() * 1000)
    from_ms = now_ms - (_DAYS * 86_400 * 1_000)

    payload = {
        "search": "Kannapolis",
        "allFilters": [
            {"publishedtimestamp": {"from": from_ms, "to": now_ms}},
            {"newspapername": [_PAPER]},
        ],
        "noneFilters": [],
        "sort": [{"publishedtimestamp": "desc"}],
        "pageSize": max_results,
        "current": 1,
        "isDemo": False,
    }

    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(_RETRIES):
        if attempt:
            time.sleep(_BACKOFF * attempt)
        try:
            result = subprocess.run(
                [
                    "curl", "-sf", "--max-time", "15",
                    "-X", "POST", _API,
                    "-H", "Content-Type: application/json",
                    "-d", json.dumps(payload),
                ],
                capture_output=True, text=True, timeout=20,
            )
            if result.returncode != 0:
                raise RuntimeError(f"curl error: {result.stderr.strip()}")

            data = json.loads(result.stdout)
            if not data.get("success"):
                raise RuntimeError("API returned success=false")

            results = []
            for item in data.get("results", []):
                if (item.get("noticetype") or "") in _EXCLUDE_TYPES:
                    continue
                notice_type = (item.get("noticetype") or "Public Notice").strip()
                text        = (item.get("text") or "").strip()
                notice_id   = item.get("id", "")
                pdf_url     = (item.get("pdfurl") or "").strip()

                # Build a readable snippet from the first few non-header lines
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                body_lines = [l for l in lines if l.lower() != notice_type.lower()]
                snippet = " · ".join(body_lines[:3])[:250] if body_lines else None

                # Always use the stable activeNotice deep-link as canonical URL for dedup
                url = f"{_PORTAL}?activeNotice={notice_id}"

                ts = item.get("publishedtimestamp")
                published_at = (
                    datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
                    if ts else None
                )

                results.append(SearchResult(
                    query=query or "Kannapolis",
                    source="PublicNotices",
                    title=notice_type,
                    url=url,
                    snippet=snippet or None,
                    source_domain="independenttribune.column.us",
                    published_at=published_at,
                ))
            return results
        except Exception as exc:
            last_exc = exc
    raise RuntimeError(f"PublicNotices fetch failed: {last_exc}") from last_exc
