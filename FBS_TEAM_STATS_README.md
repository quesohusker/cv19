# FBS team stats — cumulative-by-week rankings & z-scores

`fbs_team_stats.py` builds, for every FBS team, for every week of every season,
**cumulative-through-that-week** team stats (an offense "for" and a defense
"against" version of each), then turns them into a **1..n rank** and a
**z-score** per stat per week.

Everything is normalized so a **higher rank number and a higher z-score always
mean better** — including defensive "against" stats (allowing fewer yards/points
→ higher rank/z). Rank 1 = worst that week, rank n = best.

## Run it (Claude Code / terminal — no Jupyter)

From the project folder, one command does everything — update the current
season's data/stats, then rerun the grading models:

```bash
./run.sh                    # update the current season + rerun the grades
./run.sh --season 2026      # a specific season instead of "current"
./run.sh --rebuild          # rebuild every season from scratch, then regrade
./run.sh --validate         # also spot-check the season after building it
```

`run.sh` just calls `python refresh.py`; run that directly if you prefer.
Drive the two stages yourself instead:

```bash
python fbs_team_stats.py                 # update just the CURRENT season
python fbs_team_stats.py --seasons 2026  # a specific season (replaces its rows)
python fbs_team_stats.py --all-new       # append every not-yet-built season
python fbs_team_stats.py --rebuild       # rebuild ALL master files from scratch
python fbs_team_stats.py --inspect 2026  # schema/playType diagnostics, then exit
python fbs_team_stats.py --validate 2026 # spot-check validation, then exit

python position_grades.py                # season-long grades, all teams/years -> CSV
python position_grades.py --scope weekly # one row per team per week -> CSV
```

Seasons are auto-discovered from the base dir (any numeric sub-folder containing
a `combined.csv`). The base dir **defaults to the folder the scripts live in**
(this project), so `<project>/<year>/combined.csv` is found automatically. Point
it elsewhere with `--base-dir "..."` or the `CFDB_BASE_DIR` env var.

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

## Position-group grades (`position_grades.py`)

`position_grades.py` consumes `team_zscores_all_seasons.csv` and grades six
position groups (QB, OL, RB, WR/TE, DL/EDGE, Secondary) A+..F with 0-100
composite scores, per team, per week or season-long:

```bash
python position_grades.py                          # season-long, all teams/years -> CSV
python position_grades.py --scope weekly           # every team, every week -> CSV
python position_grades.py --season 2026 --wide     # quick view: team x group letters
python position_grades.py --season 2026 --team "Ohio State"
```

Or import `PositionGroupEvaluator` for `grade`, `grade_wide`, `grade_all`,
`plot_radar`, and `plot_compare` (see its module docstring).

Two things to know: (1) the z-score file is **pre-directional** (higher = better
on every column, defense included), so the grader uses columns as-is and does
**not** re-apply the rubric's `×-1` flips — doing so would double-invert and
grade elite defenses as awful (`--raw` / `pre_directional=False` handles a
non-pre-directional z file). (2) The score formula is `clip(65 + 15·z, 0, 100)`,
so an **average** unit (z=0) lands at 65 — the middle of the C band — i.e. the
average team grades a **C**. Tune the curve with `--base` / `--spread`.

## Updating the current season (e.g. 2026 as it plays out)

The master files are built **incrementally**, and each season's rows are
independent (ranks/z-scores are computed only within that season's weeks), so
updating one season never touches the others. The **default** command
reprocesses just the current season and *replaces* its rows — the right thing
for an in-progress season that gains games week to week:

```bash
./run.sh                          # update current season's data + regrade
# equivalently, the two stages:
python fbs_team_stats.py          # current season only -> stats/ranks/z masters
python position_grades.py         # regrade off the refreshed z-scores
python position_grades.py --scope weekly
```

Other modes:

```bash
python fbs_team_stats.py --seasons 2026   # force one specific season (replace its rows)
python fbs_team_stats.py --all-new        # first time a brand-new season appears: append it
python fbs_team_stats.py --rebuild        # reprocess everything from scratch
```

`--all-new` appends any on-disk season not yet in the master (no reprocessing of
prior seasons); the default current-season mode instead *replaces* the current
season's rows so an in-progress season refreshes cleanly. Which season is
"current" is date-derived (`current_season_year()`): August onward = this
calendar year, otherwise last year.

## What it computes

Win/loss record (`win_pct` ranked; `wins`/`losses`/`ties` cumulative, plus a
`week_result` column = `W`/`L`/`T`/`bye` for that week's game); points; rushing
(att/yds/TDs, longest); passing (att/yds/comp/TDs, longest, completion %);
interceptions thrown/made; sacks made/allowed (+yards); fumbles lost/recovered;
punt & kickoff return yards; blocked kicks; time of possession; the `_approx`
stats (3rd/4th-down conversion % and red-zone scoring %); plus efficiency /
position-group support: yards per pass attempt, yards per rush, sack rate
(for/against), 3rd-down passing volume (`pass_att_3rd_down`, `pass_yds_3rd_down`)
and YPA, and tackles-for-loss (`tfl_made_approx` / `tfl_allowed_approx`).

**Tackles for loss are approximate**: computed as a run stopped for a loss
(`yardsGained < 0`). Sacks stay a separate stat, and official TFLs are charted
and include some pass plays, so this run-only figure is lower than a full TFL
count -- hence `_approx`.

**Not derivable from this data (deliberately absent):** per-position fumbles
(e.g. fumbles lost *by the RB* -- the data has no player/position attribution;
`fumbles_lost` is team-level), yards after contact (needs charting/tracking
data), and passes defended (no pass-breakup flag exists; only the interception
component, `int_made`, is available).

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
