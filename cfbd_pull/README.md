# cfbd_pull

Pulls every available statistic from the [CollegeFootballData.com](https://collegefootballdata.com)
API (CFBD) and stores it on disk, organised by season.

All **74** endpoints the API exposes are covered. The endpoint list, paths and
required parameters were extracted from the official `cfbd` Python SDK (v5.24.2),
which is generated from CFBD's OpenAPI spec — so they are taken from the source
of truth rather than hand-written from memory.

## Setup

Only `requests` is needed, and Anaconda already ships it. No `pip install`
required.

Put your API key in `cfbd_pull/local_key.py`:

```python
API_KEY = "your-key-here"
```

That file is git-ignored, so the key stays on your machine. (`cv19` is a
**public** repo — a key committed there is scraped within minutes and stays in
the git history even after a later commit removes it.) A `CFBD_API_KEY`
environment variable or `--api-key` also work. Free keys:
<https://collegefootballdata.com/key>

## Usage

```bash
# See what a run would do — no API calls, no key needed
python -m cfbd_pull --years 2024 --dry-run

# Pull one season of season-level stats
python -m cfbd_pull --years 2024

# Everything for a season, including play-by-play
python -m cfbd_pull --years 2024 --tier full

# A range of seasons, one group of endpoints
python -m cfbd_pull --years 2015-2024 --groups betting ratings

# List the endpoint registry
python -m cfbd_pull --list-endpoints
```

Output defaults to `/Volumes/1TB external/CFDB Stats`; override with `--out`.

## Output layout

Season first, then endpoint:

```
/Volumes/1TB external/CFDB Stats/
├── _manifest.jsonl                       ← every completed call
├── static/                               ← season-less reference data
│   ├── venues/all.json.gz
│   └── plays__types/all.json.gz
├── 2023/
│   ├── games/seasonType-both.json.gz
│   ├── plays/seasonType-regular_week-3.json.gz
│   ├── stats__season/all.json.gz
│   └── ratings__sp/all.json.gz
└── 2024/
    └── ...
```

The directory carries the season, so it is not repeated in the filename.
Responses are gzipped JSON (`--no-compress` for plain `.json`).

## Tiers

`--tier` controls depth, because "all stats" spans four orders of magnitude:

| Tier | Adds | Calls/season |
|---|---|---|
| `core` (default) | reference data, season and team aggregates, ratings, recruiting | ~56 |
| `full` | play-by-play, drives, per-week box scores | ~527 |
| `exhaustive` | per-game advanced box scores, win probability, per-player detail | ~1,000s |

`exhaustive` is keyed by game and player ids, so it issues one call *per game*
and *per player*. For a single season that is thousands of calls; across all
seasons, hundreds of thousands. Start with one season and check your quota at
<https://collegefootballdata.com/key>.

## Resuming

Every completed call is appended to `_manifest.jsonl`. Re-running skips what is
already done, so an interrupted pull (Ctrl-C, dropped network, unplugged drive)
picks up where it left off without re-spending quota. `--no-resume` forces a
re-pull.

## How the sweep is planned

Endpoints differ in what they need, so each declares a strategy:

- **STATIC** — one call (venues, play types, stat categories)
- **YEAR** — one call per season (most stats)
- **YEAR_WEEK** — one call per season/week (plays, drives — `/plays/stats` is
  capped at 2000 records server-side, so week granularity is required)
- **GAME_ID / YEAR_PLAYER / COACH_ID** — keyed by ids harvested from `/games`,
  `/roster` and `/coaches`, so these run in a second phase after their sources
  are on disk
- **MANUAL** — `/player/search` and `/teams/matchup` need inputs that cannot be
  enumerated, and are skipped
- **LIVE / META** — `/scoreboard`, `/live/plays`, `/info` — opt in with
  `--include-live` / `--include-meta`

A few endpoints accept `year` alone for some queries but demand `week` or
`team` for others. Rather than guessing, the runner degrades automatically: on
an HTTP 400 it re-plans that endpoint at finer granularity, records the change
in the manifest, and reuses it on later runs.

## Reading the data back

```python
from cfbd_pull import Store

store = Store("/Volumes/1TB external/CFDB Stats")
store.seasons()                                  # [2024, 2023, ...]
games = list(store.iter_rows("games"))           # flattened across seasons
sp    = store.read("ratings__sp", {"year": 2023})

import pandas as pd
df = pd.DataFrame(store.iter_rows("stats__season", seasons=[2023]))
```

## Rate limiting

Requests are paced (`--min-interval`, default 0.6s) and retried with
exponential backoff on 429/5xx, honouring `Retry-After`. CFBD's free tier has a
monthly call budget; `--dry-run` reports the call count before you spend it.

## Caveats

The code was written and its logic tested offline — planning, season
partitioning, the manifest/resume path and the 400-fallback all have coverage —
but **it has not been run against the live API**, because the environment it was
authored in blocks outbound traffic to `collegefootballdata.com`. Paths and
parameter names come from the official SDK and are accurate; what remains
unverified is runtime behaviour — exact response shapes, which endpoints demand
`week`/`team`, and which require a paid tier. The 400-fallback and the
per-call manifest are there so a surprise degrades one endpoint rather than
sinking the run. Do a `--dry-run`, then a single season, before a long pull.
