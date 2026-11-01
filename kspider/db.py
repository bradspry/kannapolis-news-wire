from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional

from .models import SearchResult

DEFAULT_DB_PATH = Path.home() / ".kspider" / "results.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS search_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at      TEXT    NOT NULL,
    queries     TEXT    NOT NULL,   -- comma-joined list
    sources     TEXT    NOT NULL    -- comma-joined list
);

CREATE TABLE IF NOT EXISTS results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    search_run_id   INTEGER REFERENCES search_runs(id) ON DELETE CASCADE,
    query           TEXT    NOT NULL,
    source          TEXT    NOT NULL,
    title           TEXT    NOT NULL,
    url             TEXT    NOT NULL,
    snippet         TEXT,
    thumbnail_url   TEXT,
    source_domain   TEXT,
    published_at    TEXT,
    fetched_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_results_query   ON results(query);
CREATE INDEX IF NOT EXISTS idx_results_source  ON results(source);
CREATE INDEX IF NOT EXISTS idx_results_url     ON results(url);

CREATE TABLE IF NOT EXISTS blocked_urls (
    url        TEXT PRIMARY KEY,
    blocked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lake_levels (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at   TEXT    NOT NULL,
    updated_date TEXT    NOT NULL,  -- date from the page, YYYY-MM-DD
    lake         TEXT    NOT NULL,  -- e.g. "Howell/Coddle Creek"
    level        TEXT    NOT NULL,  -- e.g. '10.8" Below Full' or "Full"
    UNIQUE(updated_date, lake)
);

CREATE INDEX IF NOT EXISTS idx_lake_levels_date ON lake_levels(updated_date);
"""


class Database:
    def __init__(self, path: Path = DEFAULT_DB_PATH):
        """Open (creating if needed) the SQLite database at path and ensure its schema exists."""
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------ writes

    def new_run(self, queries: List[str], sources: List[str]) -> int:
        """Record the start of a search run and return its new run ID."""
        from datetime import datetime
        cur = self._conn.execute(
            "INSERT INTO search_runs (ran_at, queries, sources) VALUES (?, ?, ?)",
            (datetime.utcnow().isoformat() + "Z", ", ".join(queries), ", ".join(sources)),
        )
        self._conn.commit()
        return cur.lastrowid

    def insert_results(self, run_id: int, results: List[SearchResult]) -> None:
        """Bulk-insert search results tied to the given run ID."""
        rows = [
            (
                run_id,
                r.query, r.source, r.title, r.url,
                r.snippet, r.thumbnail_url, r.source_domain,
                r.published_at, r.fetched_at,
            )
            for r in results
        ]
        self._conn.executemany(
            """INSERT INTO results
               (search_run_id, query, source, title, url, snippet,
                thumbnail_url, source_domain, published_at, fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        self._conn.commit()

    # ------------------------------------------------------------------ reads

    def query_results(
        self,
        query: Optional[str] = None,
        source: Optional[str] = None,
        run_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
        dedupe: bool = False,
    ) -> List[sqlite3.Row]:
        """Return stored results filtered by query/source/run, newest first."""
        where, params = [], []
        if query:
            where.append("r.query = ?")
            params.append(query)
        if source:
            where.append("r.source = ?")
            params.append(source)
        if run_id is not None:
            where.append("r.search_run_id = ?")
            params.append(run_id)

        where_clause = ("WHERE " + " AND ".join(where)) if where else ""

        if dedupe:
            sql = f"""
                SELECT r.*, latest.first_seen FROM results r
                INNER JOIN (
                    SELECT url, MAX(id) AS max_id, MIN(fetched_at) AS first_seen
                    FROM results GROUP BY url
                ) latest ON r.id = latest.max_id
                {where_clause}
                ORDER BY r.id DESC
                LIMIT ? OFFSET ?
            """
        else:
            sql = f"""
                SELECT r.* FROM results r
                {where_clause}
                ORDER BY r.id DESC
                LIMIT ? OFFSET ?
            """
        params += [limit, offset]
        return self._conn.execute(sql, params).fetchall()

    def list_runs(self, limit: int = 20) -> List[sqlite3.Row]:
        """Return the most recent search runs with their result counts."""
        return self._conn.execute(
            """SELECT sr.*, COUNT(r.id) AS result_count
               FROM search_runs sr
               LEFT JOIN results r ON r.search_run_id = sr.id
               GROUP BY sr.id
               ORDER BY sr.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()

    def total_results(self) -> int:
        """Return the total number of stored results across all runs."""
        return self._conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]

    # ------------------------------------------------------------ blocked URLs

    def block_url(self, url: str) -> None:
        """Mark a URL as blocked so it can be filtered out of future exports."""
        from datetime import datetime
        self._conn.execute(
            "INSERT OR IGNORE INTO blocked_urls (url, blocked_at) VALUES (?, ?)",
            (url, datetime.utcnow().isoformat()),
        )
        self._conn.commit()

    # ---------------------------------------------------------- lake levels

    def save_lake_levels(
        self,
        updated_date: str,
        levels: list[tuple[str, str]],
    ) -> int:
        """Insert lake level rows, skipping any already recorded for this date.

        Returns the number of new rows inserted.
        """
        from datetime import datetime
        fetched_at = datetime.utcnow().isoformat() + "Z"
        rows = [(fetched_at, updated_date, lake, level) for lake, level in levels]
        cur = self._conn.executemany(
            """INSERT OR IGNORE INTO lake_levels (fetched_at, updated_date, lake, level)
               VALUES (?, ?, ?, ?)""",
            rows,
        )
        self._conn.commit()
        return cur.rowcount

    def query_lake_levels(
        self,
        updated_date: Optional[str] = None,
        lake: Optional[str] = None,
        limit: int = 200,
    ) -> List[sqlite3.Row]:
        """Return lake level history rows, newest date first."""
        where, params = [], []
        if updated_date:
            where.append("updated_date = ?")
            params.append(updated_date)
        if lake:
            where.append("lake = ?")
            params.append(lake)
        where_clause = ("WHERE " + " AND ".join(where)) if where else ""
        params.append(limit)
        return self._conn.execute(
            f"SELECT * FROM lake_levels {where_clause} ORDER BY updated_date DESC, lake LIMIT ?",
            params,
        ).fetchall()

    def blocked_url_set(self) -> set:
        """Return the set of all blocked URLs."""
        rows = self._conn.execute("SELECT url FROM blocked_urls").fetchall()
        return {r["url"] for r in rows}
