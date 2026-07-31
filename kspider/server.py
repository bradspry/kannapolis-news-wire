from __future__ import annotations

import json
from pathlib import Path

from .db import Database, DEFAULT_DB_PATH

_TEMPLATE = Path(__file__).parent / "templates" / "dashboard.html"


def export_html(
    db_path: Path = DEFAULT_DB_PATH,
    refresh_interval: int = 0,
) -> str:
    """Return a self-contained HTML string with results baked in."""
    with Database(db_path) as db:
        runs = db.list_runs(limit=5)
        latest_run_id = runs[0]["id"] if runs else None
        rows = db.query_results(limit=5000, dedupe=True) if latest_run_id else []

    _PN_EXCLUDE = {"Estate (Probate) Filings", "Notice to Creditors"}
    results = [
        dict(r) for r in rows
        if not (r["source"] == "PublicNotices" and r["title"] in _PN_EXCLUDE)
    ]
    by_source: dict = {}
    by_query: dict = {}
    for r in results:
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1
        by_query[r["query"]] = by_query.get(r["query"], 0) + 1

    data = {
        "results": results,
        "stats": {"total": len(results), "by_source": by_source, "by_query": by_query},
        "runs": [dict(r) for r in runs],
    }

    template = _TEMPLATE.read_text()
    inline = f'<script>window.__DATA__ = {json.dumps(data, separators=(",", ":"))}</script>'
    html = template.replace("<!-- KSPIDER_DATA -->", inline)

    if refresh_interval > 0:
        meta = f'<meta http-equiv="refresh" content="{refresh_interval}">'
        html = html.replace("<!-- KSPIDER_META -->", meta)
    else:
        html = html.replace("<!-- KSPIDER_META -->", "")

    return html
