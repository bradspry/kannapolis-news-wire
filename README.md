# kspider

A configurable web spider and local news/events monitor, built to track
news, government meetings, and public notices for Kannapolis, NC and the
surrounding Cabarrus/Rowan county area ("KCAT").

It crawls a set of configured sources on a schedule, stores results in a
local SQLite database, and exports them to a single-file HTML dashboard
you can open in a browser.

## Features

- General-purpose site crawler (`kspider crawl`) with depth/page limits,
  CSS-selector extraction, and text/JSON/URL output.
- Scheduled search across many sources at once (`kspider search`), with
  an optional loop mode that re-runs on an interval.
- Local SQLite storage of results and run history.
- Static HTML dashboard export with chip/list views, filtering, search,
  and dismiss/block of individual stories (`kspider export`).

### Sources

Pass any of these names to `--source` (repeatable). Sources marked
"once" run a single time per search regardless of how many `--query`
values are given; the rest run once per query.

| Source | Runs | Description |
| --- | --- | --- |
| `Bing` | per query | Bing web search results. |
| `Bing News` | per query | Same-day Bing News results, sorted by date. |
| `CabarrusCommissioners` | once | Upcoming Cabarrus County Board of Commissioners meetings, with agenda/time/location detail for near-term ones. |
| `CabarrusCompass` | once | Recent posts from The Cabarrus Compass (Substack, local news), via RSS. |
| `CharlotteObserver` | once | Recent Charlotte Observer articles mentioning the query, via a Google News RSS site search. |
| `CivicClerk` | once | Upcoming City of Kannapolis government meetings and agendas, from the CivicClerk API. |
| `ConcordLakeLevels` | once | Current Howell/Coddle Creek lake level readings, scraped from concordnc.gov; also logs history to the `lake_levels` table. |
| `DuckDuckGo` | per query | Same-day DuckDuckGo news results. |
| `DuckDuckGo Images` | per query | DuckDuckGo image search results. |
| `Facebook` | per query | Recent public Facebook posts matching the query, via a Google site search. |
| `Google Alerts` | once | Entries from a pre-configured Google Alerts RSS feed. |
| `Google News` | per query | Last-24-hours Google News RSS results. |
| `IndependentTribune` | once | Recent Kannapolis articles from the Independent Tribune, via its RSS search. |
| `Instagram` | per query | Recent public Instagram posts matching the query or the local hashtag, via a Google site search. |
| `KannapolisNC` | once | Latest articles from the City of Kannapolis news page. |
| `NCDMV` | once | Traffic incidents in the Cabarrus/Rowan area from the NCDOT DriveNC API. Requires `DRIVENC_API_KEY` (see Configuration). |
| `PublicNotices` | once | Public notices mentioning Kannapolis from the Concord Independent Tribune's notice portal. |
| `SalisburyPost` | once | Recent Kannapolis articles from the Salisbury Post, via its WordPress REST API. |
| `YouTube` | per query | This week's YouTube videos matching the query. |

## Installation

Requires Python 3.9+.

```bash
git clone <this-repo-url>
cd kspider
pip install -e .
```

See `INSTALL.TXT` for platform-specific setup (PATH configuration,
system library dependencies for `lxml`, etc.) on macOS, Windows, and
Linux.

### Configuration

Some sources (currently the NCDOT/DriveNC feed) need an API key. Copy
`.env.example` to `.env` and fill in your own key:

```bash
cp .env.example .env
```

## Usage

```bash
kspider --help

kspider search                        # run a single search across all sources
kspider search --loop --interval 15   # run every 15 minutes
kspider search --source CivicClerk    # run a single source only

kspider results                       # browse stored results in the terminal
kspider runs                          # list past search runs

kspider export --open                 # export the dashboard and open it in a browser

kspider crawl https://example.com     # general-purpose site crawl
```

Data is stored in `~/.kspider/results.db`, created automatically on
first run.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

Licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE)
for the full text.
