from __future__ import annotations

import re
import subprocess
import time
from datetime import datetime, timezone
from typing import List

from bs4 import BeautifulSoup

from ..db import Database, DEFAULT_DB_PATH
from ..models import SearchResult

_URL = "https://concordnc.gov/Departments/Water-Resources/Lake-Level-Data"
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


def search(query: str = "Concord", max_results: int = 30) -> List[SearchResult]:
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(_RETRIES):
        if attempt:
            time.sleep(_BACKOFF * attempt)
        try:
            proc = subprocess.run(
                ["curl", "-sL", "--max-time", "20", "-H", f"User-Agent: {_UA}", _URL],
                capture_output=True, text=True, timeout=25,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"curl error: {proc.stderr.strip()}")

            soup = BeautifulSoup(proc.stdout, "lxml")
            table = soup.find("table", class_="lakelevel")
            if not table:
                raise RuntimeError("lake level table not found on page")

            rows = table.find_all("tr")
            levels: list[tuple[str, str]] = []
            update_date_iso: str | None = None
            update_date_str: str | None = None

            for row in rows:
                cells = row.find_all("td")
                if not cells:
                    continue

                # Update date row: single cell spanning 2 cols
                if len(cells) == 1 and cells[0].get("colspan"):
                    text = cells[0].get_text(" ", strip=True)
                    m = re.search(r"(\d{2}/\d{2}/\d{4})", text)
                    if m:
                        update_date_str = m.group(1)
                        update_date_iso = _parse_date(update_date_str)
                    continue

                if len(cells) < 2:
                    continue

                name = cells[0].get_text(strip=True)
                level = cells[1].get_text(strip=True)
                # Skip empty spacer rows
                if not name or name == "\xa0":
                    continue
                levels.append((name, level))

            if not levels:
                raise RuntimeError("no lake level rows parsed")

            if update_date_iso:
                try:
                    with Database(DEFAULT_DB_PATH) as db:
                        db.save_lake_levels(update_date_iso[:10], levels)
                except Exception:
                    pass  # never let DB writes block the dashboard result

            snippet = " | ".join(f"{name}: {level}" for name, level in levels)
            date_label = update_date_str or ""
            title = f"Concord Lake Levels — Updated {date_label}" if date_label else "Concord Lake Levels"

            # Include the update date in the URL so a new update date → new chip
            # that won't be hidden by a prior dismiss of an older update.
            url = _URL + (f"?updated={update_date_iso[:10]}" if update_date_iso else "")

            return [SearchResult(
                query=query,
                source="ConcordLakeLevels",
                title=title,
                url=url,
                snippet=snippet,
                source_domain="concordnc.gov",
                published_at=update_date_iso,
            )]

        except Exception as exc:
            last_exc = exc

    raise RuntimeError(f"Concord lake levels fetch failed: {last_exc}") from last_exc
