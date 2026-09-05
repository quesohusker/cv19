#!/usr/bin/env python
"""Refresh the whole FBS pipeline end to end, from the command line.

One command does the three steps you'd otherwise run by hand:

  1. update the data/stat files for a season  (fbs_team_stats: stats, ranks, z)
  2. those per-season + master files are (re)written as part of step 1
  3. rerun the grading models on the updated z-scores  (position_grades)

By DEFAULT it touches ONLY THE CURRENT SEASON -- prior seasons' rows in the
master files are left exactly as they are -- then regrades every team/year off
the refreshed z-score master file.

Run from a terminal / Claude Code on the machine where the drive is mounted:

    python refresh.py                       # update current season + regrade
    python refresh.py --season 2026         # a specific season instead
    python refresh.py --rebuild             # full rebuild of every season, then regrade
    python refresh.py --base-dir "/Volumes/1TB external/CFDB Stats"
    python refresh.py --skip-grades         # just the stats step
    python refresh.py --validate            # spot-check the season after building it

Point it at the drive with --base-dir or the CFDB_BASE_DIR env var.
"""
from __future__ import annotations

import argparse
import os

import pandas as pd

import fbs_team_stats as fts
import position_grades as pg


def _regrade(base_dir, verbose=True):
    """Rerun the grading models over the refreshed z-score master file.

    Writes both the season-long and the weekly grade tables next to the master
    z-score file, and grades every season present (max_season follows the file,
    so a freshly-added current season is included automatically).
    """
    zpath = os.path.join(base_dir, fts.MASTER_FILES["zscores"])
    if not os.path.isfile(zpath):
        print(f"[grades] no z-score master file at {zpath}; skipping grading.")
        return
    df = pd.read_csv(zpath)
    max_season = int(df["season"].max())
    ev = pg.PositionGroupEvaluator(df, max_season=max_season)
    out_dir = os.path.dirname(os.path.abspath(zpath))
    for scope in ("season", "weekly"):
        out = os.path.join(out_dir, f"position_grades_{scope}.csv")
        tbl = ev.grade_all(scope=scope, out_path=out)
        if verbose:
            print(f"[grades] {scope:6s}: {len(tbl):,} rows -> {out}")
    if verbose:
        seasons = sorted(int(s) for s in ev.df["season"].unique())
        print(f"[grades] graded seasons {ev.df['season'].min():.0f}-{max_season} "
              f"(seasons in file: {seasons})")


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="refresh.py",
        description="Update current-season stats and rerun the grading models.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--base-dir", default=fts.BASE_DIR,
                   help="root holding <year>/combined.csv folders (or $CFDB_BASE_DIR)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--season", type=int, metavar="YEAR",
                      help="update this season instead of the current one")
    mode.add_argument("--rebuild", action="store_true",
                      help="rebuild every season's stats from scratch before regrading")
    p.add_argument("--skip-grades", action="store_true",
                   help="only update the stat files; don't rerun the grading models")
    p.add_argument("--validate", action="store_true",
                   help="run the spot-check validation on the season after building it")
    p.add_argument("-q", "--quiet", action="store_true", help="less output")
    args = p.parse_args(argv)
    verbose = not args.quiet

    # ---- step 1+2: stats / ranks / z-scores (per-season + master files) ----
    if args.rebuild:
        print("=== step 1: rebuilding ALL seasons ===")
        processed = fts.run_all_seasons(base_dir=args.base_dir, rebuild=True, verbose=verbose)
    else:
        year = args.season or fts.current_season_year()
        if year not in fts._discover_seasons(args.base_dir):
            print(f"=== step 1: {year} has no "
                  f"{os.path.join(args.base_dir, str(year), 'combined.csv')} yet ===")
            print(f"    seasons on disk: {fts._discover_seasons(args.base_dir) or '(none)'}")
            processed = []
        else:
            print(f"=== step 1: updating {year} only (prior seasons untouched) ===")
            processed = fts.run_all_seasons(base_dir=args.base_dir, seasons=[year],
                                            verbose=verbose)

    if args.validate and processed:
        for s in processed:
            fts.validate_season(s, base_dir=args.base_dir)

    if not processed and not args.rebuild:
        print("\nNothing was processed, so the grading step is skipped.")
        return

    # ---- step 3: rerun the grading models ----
    if args.skip_grades:
        print("\n(--skip-grades) grading models not rerun.")
        return
    print("\n=== step 3: rerunning grading models on refreshed z-scores ===")
    _regrade(args.base_dir, verbose=verbose)
    print("\nDone.")


if __name__ == "__main__":
    main()
