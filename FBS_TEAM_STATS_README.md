# FBS team stats — cumulative-by-week rankings & z-scores

`fbs_team_stats.py` builds, for every FBS team, for every week of every season,
**cumulative-through-that-week** team stats (an offense "for" and a defense
"against" version of each), then turns them into a **1..n rank** and a
**z-score** per stat per week.

Everything is normalized so a **higher rank number and a higher z-score always
mean better** — including defensive "against" stats (allowing fewer yards/points
→ higher rank/z). Rank 1 = worst that week, rank n = best.

## Run it (Jupyter on the Mac with the drive mounted)

```python
%run fbs_team_stats.py            # process every season found + write master files
```

or step by step:

```python
from fbs_team_stats import *
inspect_season(2025)              # print schema / playType / driveResult diagnostics
validate_season(2025)             # manual spot-checks + direction-flip checks
run_all_seasons()                 # build 2005-2025 + master files
```

Seasons are auto-discovered from `BASE_DIR` (any numeric sub-folder containing a
`combined.csv`). Point it at your drive with either:

```python
import os; os.environ["CFDB_BASE_DIR"] = "/Volumes/1TB external/CFDB Stats"
```

or by editing `BASE_DIR` at the top of the file (that path is the default).

## Outputs

Per season, in `<BASE_DIR>/<year>/`:
- `team_ranks.csv` — one row per team per week, one column per stat's rank
- `team_zscores.csv` — one row per team per week, one column per stat's z-score
- `team_stats.csv` — the underlying per-game cumulative stat values (the numbers
  to eyeball against CFBstats.com); volume-only stats live here as raw counts

Master files across all seasons, in `<BASE_DIR>/`:
- `team_ranks_all_seasons.csv` — every season's ranks stacked
- `team_zscores_all_seasons.csv` — every season's z-scores stacked
- `team_stats_all_seasons.csv` — **the master stats file**: the underlying
  per-game cumulative stat values across all seasons (one row per team per week
  per season; the numbers to compare against CFBstats.com)

## Adding 2026 later (incremental append)

The master files are built **incrementally**. `run_all_seasons()` only processes
seasons that aren't already in the master, so once 2005–2025 are built, dropping
a `2026/combined.csv` on the drive and re-running appends **only** 2026 — the
prior 21 seasons aren't reprocessed:

```python
run_all_seasons()                 # sees 2026 is new -> processes just 2026, appends
```

This is exact: each season's ranks/z-scores are computed purely within that
season's weeks, so no prior season changes when a new one is added. Other modes:

```python
run_all_seasons(rebuild=True)     # reprocess everything from scratch
run_all_seasons(seasons=[2019])   # force-reprocess one season (replaces its rows)
```

## What it computes

Win/loss record (`win_pct` ranked; `wins`/`losses`/`ties` cumulative, plus a
`week_result` column = `W`/`L`/`T`/`bye` for that week's game); points; rushing
(att/yds/TDs, longest); passing (att/yds/comp/TDs, longest, completion %);
interceptions thrown/made; sacks made/allowed (+yards); fumbles lost/recovered;
punt & kickoff return yards; blocked kicks; time of possession; and the
`_approx` stats: 3rd/4th-down conversion % and red-zone scoring %.

**Fairness:** counting stats are ranked as **per-game averages** through that
week (not raw totals), so a team on a bye isn't unfairly compared with one that
just played an extra game. Rate stats (completion %, 3rd-down %, red-zone %) are
already per-attempt. A team on a bye still gets a row, carrying its stats through
the most recent week it played.

**Direction table:** an explicit `sign` per stat (see `RANKED_STATS`) drives
normalization. Turnovers and sacks flip (committing = bad on offense, forcing =
good on defense). Volume-only stats (attempts, FG/XP made&att, return counts)
get no rank/z — they carry no inherent good/bad direction.

## Verified against real 2025 data (not CFBD's docs)

The playType / driveResult / column mappings were built by inspecting a real
2025 `combined.csv`. Confirmed by the built-in validation:
- Ohio State through wk 7 — rush/pass/points per game match a hand calc exactly.
- All 136 FBS teams have the right week-rows (byes included), no gaps.
- Worst scoring defense → rank 1; best → rank n (direction flips correct).
- Sanity leaders line up with 2025 reality (Navy/Air Force/Army top rushing &
  TOP; North Texas top scoring; Ohio State top scoring defense).

## Older-season data coverage

Early seasons (roughly 2005–2013) use coarser CFBD play typing, so some stats
are genuinely unavailable then and the code warns rather than faking them:
sacks, fumbles, punt/kickoff returns, and blocked kicks are largely absent in
those years, so those columns are NaN and get **no rank/z** (a stat with no
spread in a week is left blank, not ranked "everyone tied at 1").

Older spellings that *are* mapped so their stats survive:
- `Pass Interception` → interceptions (recovers 2006–2013 INT-thrown/made).
- `Missed Field Goal Return Touchdown` → FG attempt.
- `Pass` → the coarse pass label (the whole passing game in 2005, a small
  residual 2006–2013). Counted as a pass attempt; a completion when it
  gained/lost yards, an incompletion at 0 yards; its yardage flows into passing
  yards. 2005 is very coarse regardless and best treated with low confidence.

Two more coverage notes surfaced by the warnings:
- **Passing/rushing TD *counts* are missing before ~2014** (`Passing Touchdown`/
  `Rushing Touchdown` weren't separate play types then — the TD yardage still
  counts toward pass/rush yards; only the TD-count columns go blank).
- **Extra points** never appear as their own play type in this dataset, so XP is
  skipped in every season.

## Approximations & known gaps (stated, not hidden)

- `*_approx` (3rd/4th-down %, red-zone %): PBP has no explicit "converted" flag —
  a down is scored converted when `yardsGained >= distance`; red-zone = a drive
  with any snap inside the 20 whose `driveResult` is `TD`/`FG`. Misses defensive-
  penalty first downs; can misfire on a drive's last play.
- **Kickoff-return yards** are noisy in the source (`yardsGained` mixes kick and
  return distance); return **counts** are reliable.
- **Extra points** don't appear as their own playType in 2025 → not derivable;
  the code **warns and skips** rather than emitting zeros. Any season missing an
  expected category prints a warning instead of silently zeroing it.
- **Rushing yards** count only clean `Rush`/`Rushing Touchdown` plays and exclude
  sack yardage (sacks are a separate stat). NCAA/CFBstats fold sack losses into
  rushing, so rushing yards here will differ from CFBstats by sack yardage — by
  design, since the task wants sacks as their own stat.

**Deliberately out of scope** (not reliably derivable): penalties / penalty
yards, first downs.
