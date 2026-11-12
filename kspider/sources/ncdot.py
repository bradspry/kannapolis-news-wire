from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

from ..models import SearchResult

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_URL = "https://www.drivenc.gov/api/v2/get/event"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.4 Safari/605.1.15"
)
_RETRIES = 2
_BACKOFF = 5

# Bounding box around Kannapolis city limits (lat_min, lat_max, lon_min, lon_max).
# Covers I-85 from Kannapolis Pkwy (exit 54) to Old Beatty Ford Rd (exit 65,
# annexed by Kannapolis) and the Rowan County part of the city; excludes
# Concord Mills, Salisbury and Charlotte.
_BBOX = (35.415, 35.570, -80.720, -80.540)


def _in_area(lat: float, lon: float) -> bool:
    """Check whether a coordinate falls within the Kannapolis bounding box."""
    lat_min, lat_max, lon_min, lon_max = _BBOX
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def _unix_to_iso(val) -> Optional[str]:
    """Convert a Unix timestamp to an ISO datetime string, or None if invalid."""
    if val is None:
        return None
    try:
        return datetime.fromtimestamp(int(val), tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return None


def search(query: str = "Kannapolis", max_results: int = 50) -> List[SearchResult]:
    """Fetch NCDOT DriveNC traffic incidents in or mentioning Kannapolis."""
    api_key = os.environ.get("DRIVENC_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "DRIVENC_API_KEY environment variable not set — "
            "register at https://drivenc.gov/developers/doc"
        )

    url = f"{_URL}?key={api_key}&format=json"
    last_exc: Exception = RuntimeError("no attempts made")

    for attempt in range(_RETRIES):
        if attempt:
            time.sleep(_BACKOFF * attempt)
        try:
            proc = subprocess.run(
                ["curl", "-s", "--max-time", "25", "-H", f"User-Agent: {_UA}",
                 "-H", "Accept: application/json", url],
                capture_output=True, timeout=30,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"curl error: {proc.stderr.decode().strip()}")

            text = proc.stdout.decode("utf-8", errors="replace")
            try:
                events = json.loads(text)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"unexpected response (not JSON): {text[:120]!r}") from e

            if isinstance(events, dict) and "Message" in events:
                raise RuntimeError(f"API error: {events['Message']}")

            if not isinstance(events, list):
                raise RuntimeError(f"unexpected JSON shape: {text[:120]!r}")

            # Keep events located in Kannapolis or that name it, newest first so
            # the max_results cap never drops the most recent ones.
            events = [
                ev for ev in events
                if _in_area(ev.get("Latitude") or 0.0, ev.get("Longitude") or 0.0)
                or "kannapolis" in (ev.get("Description") or "").lower()
            ]
            events.sort(key=lambda ev: int(ev.get("StartDate") or 0), reverse=True)

            results = []
            for ev in events:

                incident_id = str(ev.get("ID", ""))
                road = (ev.get("RoadwayName") or "").strip()
                direction = (ev.get("DirectionOfTravel") or "").strip()
                event_type = (ev.get("EventType") or "").strip()
                event_subtype = (ev.get("EventSubType") or "").strip()
                description = (ev.get("Description") or "").strip()
                lanes = (ev.get("LanesAffected") or "").strip()
                organization = (ev.get("Organization") or "").strip()

                label = event_subtype or event_type or "Incident"
                title = label + (" — " + road if road else "")
                if direction and direction.lower() not in ("none", "all directions"):
                    title += f" ({direction})"

                parts = []
                if description:
                    parts.append(description)
                if lanes:
                    parts.append(f"Lanes: {lanes}")
                if organization:
                    parts.append(f"Source: {organization}")
                snippet = " | ".join(parts) or None

                url_result = (
                    f"https://www.drivenc.gov/Event/Incidents/{incident_id}?lang=en"
                    if incident_id else "https://www.drivenc.gov"
                )

                results.append(SearchResult(
                    query=query,
                    source="NCDMV",
                    title=title,
                    url=url_result,
                    snippet=snippet,
                    source_domain="drivenc.gov",
                    published_at=_unix_to_iso(ev.get("StartDate")),
                ))
                if len(results) >= max_results:
                    break

            return results

        except Exception as exc:
            last_exc = exc

    raise RuntimeError(f"NCDOT fetch failed: {last_exc}") from last_exc
