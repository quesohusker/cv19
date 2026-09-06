# cv19 automatic pipeline

`pipeline.py` runs the whole chain on the machine where the data lives:

```
game-day gate → collect → build source files → run models/forecasts → commit → report
```

It is one command by hand and an unattended launchd job on a schedule. It only
*sequences* your existing code (`python -m scripts.cfbd.*` and `python -m
models.*`); it does not reimplement any of it.

## Run it

```bash
./pipeline.sh                 # gated full run (skips if no FBS game yesterday) + commit + push
./pipeline.sh --dry-run       # print the plan; touch nothing
./pipeline.sh --ignore-gate   # run regardless of the schedule
./pipeline.sh --gate-only     # just print today's game-day decision
./pipeline.sh --no-commit     # build + report only, don't touch git
./pipeline.sh --only model    # run one group: collect | build | model | forecast
./pipeline.sh --from compute_stats   # resume from a stage
```

`pipeline.sh` finds a Python that has pandas+numpy and passes it down, so the
launchd environment works without extra setup.

## Schedule (macOS launchd)

Runs daily at 03:00; the **game-day gate** turns it into a no-op on mornings
after a day with no FBS game, so it effectively fires only after game days.

```bash
cp com.cornnation.cv19pipeline.plist ~/Library/LaunchAgents/
launchctl load  ~/Library/LaunchAgents/com.cornnation.cv19pipeline.plist
launchctl start com.cornnation.cv19pipeline      # test-fire once now
launchctl unload ~/Library/LaunchAgents/com.cornnation.cv19pipeline.plist   # stop
```

The gate reads `data/cfbd/raw/<season>/games.csv` and runs only if a game is
dated *yesterday*. It fails **open** (runs) if the schedule file is missing, so
the first run is never skipped.

## Stages (wired to your entry points)

| group | stage | module |
|---|---|---|
| collect | download | `scripts.cfbd.download` |
| collect | download_lines | `scripts.cfbd.download_lines` |
| collect | download_wp | `scripts.cfbd.download_win_probability` |
| collect | scrape_win_totals | `scripts.cfbd.scrape_win_totals` |
| build | combine | `scripts.cfbd.combine` |
| build | verify | `scripts.cfbd.verify` |
| build | compute_stats | `scripts.cfbd.compute_stats` |
| build | position_grades | `scripts.cfbd.position_grades` |
| model | power_ratings | `models.power_ratings.ratings` |
| model | power_ratings_epa | `models.power_ratings_epa.ratings` |
| model | margin_predictor | `models.margin_predictor.predict` |
| model | margin_predictor_market | `models.margin_predictor_market.predict` |
| model | in_game_wp | `models.in_game_wp.predict` |
| model | aggregate | `scripts.cfbd.aggregate_predictions` |
| model | benchmark | `scratchpad/benchmark_winpct.py` |
| forecast | forecast_season_wins | `scripts.cfbd.project_season_wins --seasons <yr> --update` |

A required stage that fails **aborts the run and commits nothing**. Optional
stages (lines, WP, win-totals scrape, market model, benchmark) warn and
continue.

## What gets committed

An **explicit allowlist** of small outputs (see `COMMIT_GLOBS` in
`pipeline.py`) is published to the **`data-latest`** branch — predictions,
projections, power ratings, position grades, lines, win-probability, season win
totals, benchmark CSVs. Never committed: `combined_all_seasons.csv` (2 GB) and
the 28/33 MB weekly masters (`team_stats`/`team_zscores`), raw/processed, or
anything under `scripts/`.

The commit is done with **git plumbing** — it builds the commit and moves the
`data-latest` ref directly, so it **never checks out a branch or touches your
working tree**. Whatever branch you're on stays put. History is kept, so
week-over-week forecasts are preserved for backtesting.

## Report

Every run writes `logs/pipeline_<timestamp>/REPORT.md` (and copies it to
`logs/latest_report.md`): per-stage status + timing, the committed file
manifest with row counts, the commit hash / push result, and any failures.
Per-stage stdout/stderr is in `logs/pipeline_<timestamp>/<stage>.log`.

## Status: what's live vs. pending

**Live now:** the full collect → build → models → commit → report chain, the
game-day gate, and the current-season **season-win-total** forecast
(`project_season_wins --seasons <yr> --update`).

**Pending (Phase 2) — per-game 2026 forecasts.** `margin_predictor`,
`margin_predictor_market`, and `in_game_wp` currently produce *evaluation*
artifacts (test = 2024–25, 2026 excluded). To forecast every 2026 game each
week they each need a `forecast` entry point that refits on all completed data
and scores the upcoming slate. Those stages exist in `pipeline.py` but are
`enabled=False` until the entry points are written. Enable them there once done.

## ⚠️ API key

The CFBD API key is hardcoded in `scripts/cfbd/*`. The pipeline's commit
allowlist never includes `scripts/`, so the automation won't leak it — but do
**not** push `scripts/` to a public repo (e.g. the Streamlit app repo). Move the
key to a gitignored `scripts/cfbd/secret.py` or an env var when convenient.
