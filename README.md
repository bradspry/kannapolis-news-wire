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

- Local government/civic: CivicClerk, City of Kannapolis news, Cabarrus
  County Commissioners, Concord lake levels, NCDMV, public notices
- Local news: Cabarrus Compass, Independent Tribune, Salisbury Post,
  Charlotte Observer
- General web/search: Bing, Bing News, DuckDuckGo, DuckDuckGo Images,
  Google News, Google Alerts
- Social/media: Facebook, Instagram, YouTube

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
