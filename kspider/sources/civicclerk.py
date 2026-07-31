from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from typing import List
from urllib.parse import urlencode

from ..models import SearchResult

_API    = "https://kannapolisnc.api.civicclerk.com/v1/Events"
_PORTAL = "https://kannapolisnc.portal.civicclerk.com"
_RETRIES = 3
_BACKOFF = 5


def _get(url: str, params: dict) -> dict:
    """Use system curl to avoid Python 3.9 TLS compatibility issues."""
    full_url = f"{url}?{urlencode(params)}"
    result = subprocess.run(
        ["curl", "-sf", "--max-time", "15", full_url],
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl error: {result.stderr.strip()}")
    return json.loads(result.stdout)


def search(query: str = "", max_results: int = 50) -> List[SearchResult]:
    """Fetch all upcoming published meetings from CivicClerk (query is ignored)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "$filter": f"startDateTime ge {now}",
        "$orderby": "startDateTime asc",
        "$top": max_results,
    }

    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(_RETRIES):
        if attempt:
            time.sleep(_BACKOFF * attempt)
        try:
            data   = _get(_API, params)
            events = data.get("value", [])

            results = []
            for ev in events:
                event_id   = ev.get("id")
                title      = ev.get("eventName", "").strip() or "(Untitled meeting)"
                start      = ev.get("startDateTime", "")
                category   = (ev.get("eventCategoryName") or ev.get("categoryName") or "").strip()
                has_agenda = bool(ev.get("hasAgenda"))
                agenda_fname = (ev.get("agendaFile") or {}).get("fileName")
                pub_files  = ev.get("publishedFiles") or []
                location   = (ev.get("eventLocation") or {})
                addr       = ", ".join(p for p in [location.get("address1"), location.get("city")] if p)

                # Build human-readable snippet
                parts = []
                if category and category.lower() not in title.lower():
                    parts.append(category)
                if start:
                    try:
                        dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                        parts.append(dt.strftime("%a %b %-d at %-I:%M %p"))
                    except Exception:
                        pass
                if addr:
                    parts.append(addr)
                agenda_published = bool(agenda_fname) or bool(pub_files)
                if has_agenda:
                    parts.append("Agenda posted" if agenda_published else "Agenda pending")
                else:
                    parts.append("No agenda yet")
                n_attach = len(pub_files)
                if n_attach:
                    parts.append(f"{n_attach} attachment{'s' if n_attach != 1 else ''}")

                results.append(SearchResult(
                    query=query or "civicclerk",
                    source="CivicClerk",
                    title=title,
                    url=f"{_PORTAL}/event/{event_id}/files",
                    snippet=" · ".join(parts) or None,
                    source_domain="kannapolisnc.portal.civicclerk.com",
                    published_at=start or None,
                ))
            return results
        except Exception as exc:
            last_exc = exc
    raise RuntimeError(f"CivicClerk fetch failed: {last_exc}") from last_exc
