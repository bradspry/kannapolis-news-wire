from datetime import datetime, timedelta

from kspider.db import Database
from kspider.models import SearchResult


def _result(url, source="NCDMV", days_ago=0):
    fetched = (datetime.utcnow() - timedelta(days=days_ago)).isoformat() + "Z"
    return SearchResult(query="q", source=source, title="t", url=url, fetched_at=fetched)


def test_prune_stale_removes_only_urls_not_seen_recently(tmp_path):
    with Database(tmp_path / "t.db") as db:
        run = db.new_run(["q"], ["NCDMV"])
        db.insert_results(run, [
            _result("https://x/old", days_ago=10),
            _result("https://x/old", days_ago=5),
            _result("https://x/active", days_ago=10),   # first seen long ago...
            _result("https://x/active", days_ago=0),    # ...but still in the feed
            _result("https://x/other", source="Bing", days_ago=10),
        ])

        assert db.prune_stale("NCDMV", 3) == 1

        urls = {(r["source"], r["url"]) for r in db._conn.execute("SELECT source, url FROM results")}
        assert urls == {("NCDMV", "https://x/active"), ("Bing", "https://x/other")}
        # The active incident keeps its original first_seen.
        (row,) = db.query_results(source="NCDMV", dedupe=True)
        assert row["first_seen"] < row["fetched_at"]


def test_insert_updates_existing_item_instead_of_resaving(tmp_path):
    with Database(tmp_path / "t.db") as db:
        run1 = db.new_run(["q"], ["CivicClerk"])
        first = _result("https://x/mtg", source="CivicClerk", days_ago=5)
        first.snippet = "No agenda yet"
        db.insert_results(run1, [first])

        run2 = db.new_run(["q"], ["CivicClerk"])
        again = _result("https://x/mtg", source="CivicClerk")
        again.snippet = "Agenda posted · 2 attachments"
        db.insert_results(run2, [again, _result("https://x/new", source="CivicClerk")])

        assert db.total_results() == 2
        rows = {r["url"]: r for r in db.query_results(dedupe=True)}
        mtg = rows["https://x/mtg"]
        assert mtg["snippet"] == "Agenda posted · 2 attachments"
        assert mtg["search_run_id"] == run2
        assert mtg["first_seen"] == first.fetched_at
        assert mtg["fetched_at"] == again.fetched_at


def test_migration_backfills_first_seen(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE results (id INTEGER PRIMARY KEY AUTOINCREMENT, search_run_id INTEGER,
            query TEXT NOT NULL, source TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL,
            snippet TEXT, thumbnail_url TEXT, source_domain TEXT, published_at TEXT,
            fetched_at TEXT NOT NULL);
        INSERT INTO results (query, source, title, url, fetched_at) VALUES
            ('q','Bing','t','https://x/a','2026-01-01T00:00:00Z'),
            ('q','Bing','t','https://x/a','2026-02-01T00:00:00Z');
    """)
    con.commit(); con.close()
    with Database(path) as db:
        firsts = {r[0] for r in db._conn.execute("SELECT first_seen FROM results")}
        assert firsts == {"2026-01-01T00:00:00Z"}
        (row,) = db.query_results(dedupe=True)
        assert row["first_seen"] == "2026-01-01T00:00:00Z"
        assert row["fetched_at"] == "2026-02-01T00:00:00Z"
