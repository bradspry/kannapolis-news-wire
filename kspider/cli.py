from __future__ import annotations

import warnings
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

import asyncio
import json
import select
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import click

from .db import Database, DEFAULT_DB_PATH
from .page import Page
from .search import run_search, DEFAULT_QUERIES, ALL_SOURCES
from .spider import Spider, SpiderConfig


@click.group()
def main() -> None:
    """kspider — web spider and search monitor."""


# ─── crawl ───────────────────────────────────────────────────────────────────

@main.command()
@click.argument("url")
@click.option("--depth", "-d", default=2, show_default=True)
@click.option("--max-pages", "-n", default=100, show_default=True)
@click.option("--delay", default=0.5, show_default=True, help="Seconds between requests per host")
@click.option("--follow-external", is_flag=True)
@click.option("--extract", "-e", metavar="CSS", multiple=True, help="CSS selector (repeatable)")
@click.option("--output", "-o", type=click.Choice(["text", "json", "urls"]), default="text", show_default=True)
def crawl(url, depth, max_pages, delay, follow_external, extract, output):
    """Crawl a website starting from URL."""
    config = SpiderConfig(
        max_depth=depth,
        max_pages=max_pages,
        delay=delay,
        follow_external=follow_external,
    )
    collected: list = []

    def on_page(page: Page) -> None:
        if output == "urls":
            click.echo(page.url)
            return
        entry = {"url": page.url, "status": page.status_code, "title": page.title}
        if extract:
            entry["extracted"] = {sel: page.select(sel) for sel in extract}
        if output == "json":
            collected.append(entry)
        else:
            click.echo(f"[{page.status_code}] {page.url}")
            if page.title:
                click.echo(f"  title: {page.title}")
            for sel, values in (entry.get("extracted") or {}).items():
                click.echo(f"  {sel}: {values}")

    asyncio.run(Spider(config).crawl(url, on_page=on_page))
    if output == "json":
        json.dump(collected, sys.stdout, indent=2)
        click.echo()


# ─── search ──────────────────────────────────────────────────────────────────

@main.command("search")
@click.option("--query", "-q", multiple=True, metavar="TERM",
              help="Search query (repeatable). Defaults to three Kannapolis variants.")
@click.option("--source", "-s", multiple=True, metavar="SOURCE",
              type=click.Choice(ALL_SOURCES, case_sensitive=False),
              help="Source to search (repeatable, default: all).")
@click.option("--max-results", "-n", default=30, show_default=True)
@click.option("--loop", is_flag=True, help="Run repeatedly on an interval.")
@click.option("--interval", default=30, show_default=True, metavar="MINUTES",
              help="Minutes between runs when --loop is set.")
@click.option("--export", "export_path", default=None, metavar="PATH",
              help="Re-export the dashboard HTML after each run.")
@click.option("--refresh", "refresh_interval", default=900, show_default=True,
              metavar="SECONDS", help="Browser auto-refresh interval embedded in --export file.")
@click.option("--db", "db_path", default=str(DEFAULT_DB_PATH), show_default=True,
              help="Path to SQLite database file.")
def search_cmd(query, source, max_results, loop, interval, export_path, refresh_interval, db_path):
    """Fetch search results and store them in the database."""
    queries = list(query) or DEFAULT_QUERIES
    sources = list(source) or ALL_SOURCES

    def on_progress(q: str, src: str, count: int) -> None:
        if count < 0:
            click.echo(f"  {src:6s}  ERROR  {q!r}")
        else:
            click.echo(f"  {src:6s}  {count:3d} results  {q!r}")

    def run_once() -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        click.echo(f"\n[{now}] Searching {len(queries)} "
                   f"quer{'y' if len(queries)==1 else 'ies'} × {len(sources)} source(s)")
        with Database(Path(db_path)) as db:
            run_id, total = run_search(
                db,
                queries=queries,
                sources=sources,
                max_results=max_results,
                on_progress=on_progress,
            )
        click.secho(f"  Run #{run_id} complete — {total} results stored.", fg="green")

        if export_path:
            from .server import export_html
            out = Path(export_path)
            out.write_text(export_html(db_path=Path(db_path), refresh_interval=refresh_interval))
            click.echo(f"  Dashboard updated → {out.resolve()}")

    def _countdown(seconds: int) -> bool:
        """Count down second-by-second. Returns True if user pressed Enter to run now."""
        is_tty = sys.stdin.isatty()
        hint = "press Enter to run now, Ctrl-C to stop" if is_tty else "Ctrl-C to stop"
        for remaining in range(seconds, 0, -1):
            m, s = divmod(remaining, 60)
            sys.stdout.write(f"\r  Next run in {m:02d}:{s:02d} — {hint}.   ")
            sys.stdout.flush()
            if is_tty:
                ready, _, _ = select.select([sys.stdin], [], [], 1.0)
                if ready:
                    sys.stdin.readline()
                    sys.stdout.write("\n")
                    return True
            else:
                time.sleep(1)
        sys.stdout.write("\n")
        return False

    try:
        run_once()
        if loop:
            while True:
                _countdown(interval * 60)
                run_once()
    except KeyboardInterrupt:
        click.echo("\nStopped.")


# ─── results ─────────────────────────────────────────────────────────────────

@main.command("results")
@click.option("--query", "-q", default=None, help="Filter by query string.")
@click.option("--source", "-s", default=None,
              type=click.Choice(ALL_SOURCES, case_sensitive=False), help="Filter by source.")
@click.option("--run", "run_id", default=None, type=int, help="Filter by run ID.")
@click.option("--limit", "-n", default=50, show_default=True)
@click.option("--offset", default=0, show_default=True)
@click.option("--dedupe", is_flag=True, help="Show only the latest entry per URL.")
@click.option("--output", "-o", type=click.Choice(["table", "json"]), default="table", show_default=True)
@click.option("--db", "db_path", default=str(DEFAULT_DB_PATH), show_default=True)
def results_cmd(query, source, run_id, limit, offset, dedupe, output, db_path):
    """Browse stored search results."""
    with Database(Path(db_path)) as db:
        rows = db.query_results(
            query=query, source=source, run_id=run_id,
            limit=limit, offset=offset, dedupe=dedupe,
        )

    if not rows:
        click.echo("No results found.")
        return

    if output == "json":
        json.dump([dict(r) for r in rows], sys.stdout, indent=2)
        click.echo()
        return

    # table output
    click.echo(f"{'ID':>6}  {'SOURCE':6}  {'QUERY':<28}  {'TITLE'}")
    click.echo("-" * 80)
    for r in rows:
        title = (r["title"] or "")[:50]
        q = (r["query"] or "")[:26]
        click.echo(f"{r['id']:>6}  {r['source']:6}  {q:<28}  {title}")
    click.echo(f"\n{len(rows)} row(s) shown.")


# ─── runs ────────────────────────────────────────────────────────────────────

@main.command("runs")
@click.option("--db", "db_path", default=str(DEFAULT_DB_PATH), show_default=True)
def runs_cmd(db_path):
    """List past search runs."""
    with Database(Path(db_path)) as db:
        runs = db.list_runs()
        total = db.total_results()

    if not runs:
        click.echo("No runs yet. Try: kspider search")
        return

    click.echo(f"{'RUN':>5}  {'DATE/TIME (UTC)':20}  {'RESULTS':>7}  QUERIES")
    click.echo("-" * 70)
    for r in runs:
        click.echo(f"{r['id']:>5}  {r['ran_at'][:19]:20}  {r['result_count']:>7}  {r['queries']}")
    click.echo(f"\n{len(runs)} run(s), {total} total results in {db_path}")


# ─── export ───────────────────────────────────────────────────────────────────

@main.command("export")
@click.option("--out", "-o", default="kcat.html", show_default=True,
              help="Output HTML path.")
@click.option("--refresh", "refresh_interval", default=0, metavar="SECONDS",
              help="Embed a browser auto-refresh interval (0 = disabled).")
@click.option("--db", "db_path", default=str(DEFAULT_DB_PATH), show_default=True)
@click.option("--open", "do_open", is_flag=True, help="Open the file in a browser after export.")
def export_cmd(out, refresh_interval, db_path, do_open):
    """Export results to an HTML file."""
    import shutil
    from .server import export_html

    html = export_html(db_path=Path(db_path), refresh_interval=refresh_interval)

    out_path = Path(out)
    out_path.write_text(html)

    # Copy favicon.png next to the file
    favicon_src = Path(__file__).parent / "templates" / "favicon.png"
    if favicon_src.exists():
        shutil.copy2(favicon_src, out_path.parent / "favicon.png")

    click.secho(f"Exported → {out_path.resolve()}", fg="green")
    if do_open:
        import webbrowser
        webbrowser.open(out_path.resolve().as_uri())

