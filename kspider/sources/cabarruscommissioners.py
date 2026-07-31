from __future__ import annotations

import re
import subprocess
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from bs4 import BeautifulSoup

from ..models import SearchResult

_URL = "https://www.cabarruscounty.us/Government/Boards-and-Committees/Board-Meetings"
_BASE = "https://www.cabarruscounty.us"
_DETAIL_WINDOW_DAYS = 90   # fetch detail pages only for meetings within this window
_DETAIL_DELAY = 1.0        # seconds between detail page fetches
_RETRIES = 3
_BACKOFF = 5
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
_CURL_HEADERS = [
    "-H", f"User-Agent: {_UA}",
    "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "-H", "Accept-Language: en-US,en;q=0.9",
    "-H", "Sec-Fetch-Dest: document",
    "-H", "Sec-Fetch-Mode: navigate",
    "-H", "Sec-Fetch-Site: none",
    "-H", 'Sec-CH-UA: "Chromium";v="124", "Google Chrome";v="124"',
    "-H", "Sec-CH-UA-Mobile: ?0",
    "-H", 'Sec-CH-UA-Platform: "macOS"',
    "-H", "Upgrade-Insecure-Requests: 1",
]


def _fetch(url: str, timeout: int = 20) -> str:
    """Fetch a URL via curl with browser-like headers to avoid being blocked."""
    proc = subprocess.run(
        ["curl", "-sL", "--max-time", str(timeout), "--http2", "--compressed"] + _CURL_HEADERS + [url],
        capture_output=True, text=True, timeout=timeout + 5,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"curl error: {proc.stderr.strip()}")
    if "Access Denied" in proc.stdout[:500] or len(proc.stdout) < 500:
        raise RuntimeError("Access denied or empty response")
    return proc.stdout


def _parse_date(text: str) -> Optional[datetime]:
    """Parse a "Month D, YYYY" meeting date string into a UTC datetime."""
    for fmt in ("%B %d, %Y", "%B %#d, %Y"):
        try:
            return datetime.strptime(text.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _parse_detail(html: str, meeting_date: datetime) -> dict:
    """Extract time, location, and agenda status from a detail page."""
    soup = BeautifulSoup(html, "lxml")
    result = {"time": None, "location": None, "has_agenda": False}

    # Time — look for HH:MM AM/PM pattern
    m = re.search(r'(\d{1,2}:\d{2}\s*[AP]M)', html)
    if m:
        result["time"] = m.group(1).strip()

    # Agenda — look for an <a> with text "Agenda"
    for a in soup.find_all("a", href=True):
        if a.get_text(strip=True).lower() == "agenda":
            result["has_agenda"] = True
            break

    # Location — look for Governmental Center text
    m2 = re.search(r'Governmental Center[^<]{0,200}', html)
    if m2:
        result["location"] = re.sub(r'&nbsp;|  +', ' ', m2.group()).strip()[:120]

    return result


def _build_published_at(date: datetime, time_str: Optional[str]) -> str:
    """Combine a meeting date with an optional time string into an ISO timestamp."""
    if time_str:
        try:
            t = datetime.strptime(time_str, "%I:%M %p")
            return date.replace(hour=t.hour, minute=t.minute).isoformat()
        except ValueError:
            pass
    return date.isoformat()


def search(query: str = "", max_results: int = 30) -> List[SearchResult]:
    """Fetch upcoming Cabarrus County Commissioners meetings, with agenda/detail info for near-term ones."""
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(_RETRIES):
        if attempt:
            time.sleep(_BACKOFF * attempt)
        try:
            html = _fetch(_URL)
            soup = BeautifulSoup(html, "lxml")
            now = datetime.now(timezone.utc)
            cutoff = now + timedelta(days=_DETAIL_WINDOW_DAYS)
            results = []

            items = soup.select("div.accordion-list-item-container article")[:max_results]
            for item in items:
                a = item.find("a", class_="accordion-trigger")
                if not a:
                    continue
                href = a.get("href", "")
                if not href:
                    continue
                url = href if href.startswith("http") else _BASE + href

                date_span = item.find("span", class_="minutes-date")
                type_span = item.find("span", class_="meeting-type")
                date_str = date_span.get_text(strip=True) if date_span else ""
                meeting_type = type_span.get_text(strip=True) if type_span else "Meeting"

                meeting_date = _parse_date(date_str)

                # Fetch detail page for near-term meetings
                detail = {"time": None, "location": None, "has_agenda": False}
                if meeting_date and meeting_date <= cutoff:
                    try:
                        time.sleep(_DETAIL_DELAY)
                        detail_html = _fetch(url, timeout=15)
                        detail = _parse_detail(detail_html, meeting_date)
                    except Exception:
                        pass

                title = f"Cabarrus County Commissioners — {meeting_type}"
                parts = [meeting_type]
                if date_str:
                    parts.append(date_str)
                if detail["time"]:
                    parts.append(detail["time"])
                if detail["location"]:
                    parts.append(detail["location"])
                parts.append("Agenda posted" if detail["has_agenda"] else "No agenda yet")

                published_at = _build_published_at(meeting_date, detail["time"]) if meeting_date else None

                results.append(SearchResult(
                    query=query or "cabarrus commissioners",
                    source="CabarrusCommissioners",
                    title=title,
                    url=url,
                    snippet=" · ".join(parts),
                    source_domain="cabarruscounty.us",
                    published_at=published_at,
                ))

            return results

        except Exception as exc:
            last_exc = exc

    raise RuntimeError(f"Cabarrus Commissioners fetch failed: {last_exc}") from last_exc
