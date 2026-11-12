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

        assert db.prune_stale("NCDMV", 3) == 2

        urls = {(r["source"], r["url"]) for r in db._conn.execute("SELECT source, url FROM results")}
        assert urls == {("NCDMV", "https://x/active"), ("Bing", "https://x/other")}
        # The active incident keeps its oldest row, so first_seen is unchanged.
        assert db._conn.execute(
            "SELECT COUNT(*) FROM results WHERE url = 'https://x/active'").fetchone()[0] == 2
