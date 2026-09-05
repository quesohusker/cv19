#!/usr/bin/env python3
"""
cv19 automatic pipeline
=======================

One orchestrator that runs the whole chain on the machine where the data lives:

    collect  -> build source files -> run models/forecasts -> commit -> report

It is designed to run unattended (launchd at 03:00) but is equally a one-command
manual tool. Every stage is a `python -m <module>` invocation of YOUR existing
code; this file only sequences them, gates on game days, captures logs, commits
an allowlist of small outputs, and writes a run report.

Design decisions baked in
-------------------------
* GAME-DAY GATE: at 03:00 it runs only if an FBS game was played *yesterday*
  (read from the local schedule). Otherwise it exits 0 as a logged no-op, so a
  plain daily launchd trigger effectively fires only the morning after games.
* CURRENT SEASON, full rebuild each run (prior seasons are static).
* COMMIT = EXPLICIT ALLOWLIST of small output files only (never `git add -A`,
  never the 2 GB combined file or the 28/33 MB weekly masters, never scripts/).
  This also guarantees the hardcoded CFBD key in scripts/ is never committed.
* STOP ON ERROR: a failed stage aborts the run; nothing is committed from a
  half-built run unless you pass --commit-anyway.

Usage
-----
    python3 pipeline.py --dry-run           # print the plan, touch nothing
    python3 pipeline.py                      # gated full run (skips if no game yesterday)
    python3 pipeline.py --ignore-gate        # run regardless of the schedule
    python3 pipeline.py --only model         # run just one group
    python3 pipeline.py --from compute_stats # resume from a stage
    python3 pipeline.py --no-commit          # build + report, don't touch git
    python3 pipeline.py --gate-only          # just print the game-day decision

Prefer the wrapper `./pipeline.sh` so the right pandas Python is chosen.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------- #
# season / schedule helpers
# --------------------------------------------------------------------------- #
def current_season(today=None):
    """CFB season year: Aug-Dec = this year; Jan-Jul = last year."""
    today = today or dt.date.today()
    return today.year if today.month >= 8 else today.year - 1


def _games_csv(season):
    return os.path.join(HERE, "data", "cfbd", "raw", str(season), "games.csv")


def _find_date_col(fieldnames):
    for cand in ("startDate", "start_date", "start_time", "startTime", "date", "gameDate"):
        if cand in fieldnames:
            return cand
    # last resort: any field that looks date-ish
    for f in fieldnames or []:
        if "date" in f.lower():
            return f
    return None


def game_played_yesterday(season, ref=None):
    """(ran, reason). True if an FBS game's date == yesterday in the local schedule.

    Fail-open: if the schedule file is missing or unparseable, return True so the
    first run (or a schedule hiccup) never silently skips.
    """
    ref = ref or dt.date.today()
    yesterday = ref - dt.timedelta(days=1)
    path = _games_csv(season)
    if not os.path.isfile(path):
        return True, f"no schedule at {path} yet -> fail-open (run)"
    try:
        with open(path, newline="") as fh:
            r = csv.DictReader(fh)
            date_col = _find_date_col(r.fieldnames)
            if not date_col:
                return True, "no date column in games.csv -> fail-open (run)"
            hits = 0
            for row in r:
                raw = (row.get(date_col) or "").strip()
                if not raw:
                    continue
                d = _parse_date(raw)
                if d == yesterday:
                    hits += 1
            if hits:
                return True, f"{hits} FBS game(s) dated {yesterday} in the schedule"
            return False, f"no games dated {yesterday} (yesterday) in the schedule"
    except Exception as e:  # never let the gate crash the job
        return True, f"schedule read error ({e}) -> fail-open (run)"


def _parse_date(raw):
    """Parse a CFBD date/datetime string to a local calendar date, best-effort."""
    s = raw.strip().replace("Z", "+00:00")
    # try full ISO datetime first, then a bare date
    for fmt in (None, "%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            if fmt is None:
                d = dt.datetime.fromisoformat(s)
                return d.astimezone().date() if d.tzinfo else d.date()
            return dt.datetime.strptime(s[:10], fmt).date()
        except Exception:
            continue
    return None


# --------------------------------------------------------------------------- #
# stage definitions  (wired to YOUR existing entry points)
# --------------------------------------------------------------------------- #
class Stage:
    def __init__(self, name, group, argv, optional=False, enabled=True, note=""):
        self.name = name
        self.group = group          # collect | build | model | forecast
        self.argv = argv            # list after the interpreter, e.g. ["-m","scripts.cfbd.download"]
        self.optional = optional    # a failure warns but does not abort the run
        self.enabled = enabled      # disabled stages are shown but skipped (Phase-2 placeholders)
        self.note = note


def build_stages(season):
    S = str(season)
    return [
        # ---- collect (pull fresh data; scripts default to the current season) ----
        Stage("download",        "collect", ["-m", "scripts.cfbd.download"]),
        Stage("download_lines",  "collect", ["-m", "scripts.cfbd.download_lines"], optional=True),
        Stage("download_wp",     "collect", ["-m", "scripts.cfbd.download_win_probability"], optional=True),
        Stage("scrape_win_totals", "collect", ["-m", "scripts.cfbd.scrape_win_totals"], optional=True,
              note="preseason lines; usually a no-op in-season"),
        # ---- build source files ----
        Stage("combine",         "build", ["-m", "scripts.cfbd.combine"]),
        Stage("verify",          "build", ["-m", "scripts.cfbd.verify"]),
        Stage("compute_stats",   "build", ["-m", "scripts.cfbd.compute_stats"]),
        Stage("position_grades", "build", ["-m", "scripts.cfbd.position_grades"]),
        # ---- models / evaluation artifacts (refit + score) ----
        Stage("power_ratings",     "model", ["-m", "models.power_ratings.ratings"]),
        Stage("power_ratings_epa", "model", ["-m", "models.power_ratings_epa.ratings"]),
        Stage("margin_predictor",        "model", ["-m", "models.margin_predictor.predict"]),
        Stage("margin_predictor_market", "model", ["-m", "models.margin_predictor_market.predict"], optional=True),
        Stage("in_game_wp",              "model", ["-m", "models.in_game_wp.predict"]),
        Stage("aggregate",  "model", ["-m", "scripts.cfbd.aggregate_predictions"]),
        Stage("benchmark",  "model", [os.path.join("scratchpad", "benchmark_winpct.py")], optional=True,
              note="Corn Nation 14-benchmark model (explosive 9+)"),
        # ---- live 2026 forecasts ----
        # This one already exists and produces a live current-season projection:
        Stage("forecast_season_wins", "forecast",
              ["-m", "scripts.cfbd.project_season_wins", "--seasons", S, "--update"],
              note=f"live {S} season win-total forecast"),
        # Per-game season forecasts. margin (v1) is live; the others are Phase-2
        # placeholders, disabled until their forecast entry points exist.
        Stage("forecast_margin", "forecast",
              ["-m", "models.margin_predictor.forecast", "--season", S],
              optional=True, note="per-game v1 margin + win-prob forecast for the season"),
        Stage("forecast_in_game_wp", "forecast",
              ["-m", "models.in_game_wp.forecast", "--season", S],
              optional=True, note="pregame win-probability forecast for the season"),
    ]


# Explicit allowlist of SMALL outputs to commit. Never scripts/, never the
# 2 GB combined file or the 28/33 MB weekly masters. Globs are repo-relative.
COMMIT_GLOBS = [
    "data/cfbd/master/team_ranks_all_seasons.csv",
    "data/cfbd/master/position_grades_*.csv",
    "data/cfbd/master/power_ratings_weekly.csv",
    "data/cfbd/master/power_ratings_epa_weekly.csv",
    "data/cfbd/master/lines_all_seasons.csv",
    "data/cfbd/master/lines_consensus_all_seasons.csv",
    "data/cfbd/master/pregame_win_probability_all_seasons.csv",
    "data/cfbd/master/season_win_totals.csv",
    "data/cfbd/predictions/*.csv",
    "data/cfbd/projections/*.csv",
    "scratchpad/benchmark_winpct_seasons.csv",
    "scratchpad/benchmark_winpct_games.csv",
]
# Never commit these even if a glob above would catch them (safety net). Kept
# out on purpose: the 2 GB combined file, the 28/33 MB weekly z/stat masters,
# the 124 MB CFBD per-play WP benchmark, and 20 MB per-play in-game-WP output --
# all either over GitHub's 100 MB limit or pure history bloat. The leading-slash
# forms below are surgical: "/win_probability_all_seasons.csv" excludes the big
# master WITHOUT touching "pregame_win_probability_all_seasons.csv" (460 KB).
COMMIT_DENY_SUBSTR = ["combined_all_seasons", "team_stats_all_seasons",
                      "team_zscores_all_seasons", "/win_probability_all_seasons.csv",
                      "in_game_wp_perplay", "/raw/", "/processed/", "scripts/"]
COMMIT_BRANCH = "data-latest"


# --------------------------------------------------------------------------- #
# stage runner
# --------------------------------------------------------------------------- #
def run_stage(stage, python, log_dir, dry_run):
    argv = [python] + stage.argv
    printable = " ".join(argv)
    if dry_run:
        return {"name": stage.name, "status": "PLAN", "seconds": 0.0, "cmd": printable}
    log_path = os.path.join(log_dir, f"{stage.name}.log")
    t0 = time.time()
    with open(log_path, "w") as log:
        log.write(f"$ {printable}\n\n")
        log.flush()
        proc = subprocess.run(argv, cwd=HERE, stdout=log,
                              stderr=subprocess.STDOUT)
    secs = time.time() - t0
    status = "OK" if proc.returncode == 0 else f"FAIL(rc={proc.returncode})"
    return {"name": stage.name, "status": status, "seconds": secs,
            "cmd": printable, "log": log_path, "rc": proc.returncode}


# --------------------------------------------------------------------------- #
# commit
# --------------------------------------------------------------------------- #
def _git(*args, check=True):
    return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True,
                          check=check)


def resolve_commit_files():
    files = []
    for pattern in COMMIT_GLOBS:
        for p in glob.glob(os.path.join(HERE, pattern)):
            rel = os.path.relpath(p, HERE)
            if any(bad in "/" + rel for bad in COMMIT_DENY_SUBSTR):
                continue
            if os.path.isfile(p):
                files.append(rel)
    return sorted(set(files))


def commit_and_push(files, branch, season, push, dry_run):
    """Publish `files` to `branch` WITHOUT touching the working tree or HEAD.

    Uses git plumbing: seed a temp index from the branch's current tree (if any),
    overwrite the allowlisted paths with the working-tree blobs, write a tree,
    commit-tree onto the branch tip, and move the ref. The user's checked-out
    branch and working directory are never modified.
    """
    if not files:
        return {"status": "nothing to commit (no allowlisted files found)"}
    if dry_run:
        return {"status": "PLAN", "branch": branch, "files": files}

    env = dict(os.environ)
    idx = tempfile.NamedTemporaryFile(delete=False)
    idx.close()
    env["GIT_INDEX_FILE"] = idx.name
    try:
        parent = _git("rev-parse", "--verify", f"refs/heads/{branch}", check=False).stdout.strip()
        if parent:
            subprocess.run(["git", "read-tree", branch], cwd=HERE, env=env,
                           capture_output=True, text=True, check=True)
        else:
            subprocess.run(["git", "read-tree", "--empty"], cwd=HERE, env=env,
                           capture_output=True, text=True, check=True)
        for rel in files:
            blob = subprocess.run(["git", "hash-object", "-w", "--", rel], cwd=HERE,
                                  capture_output=True, text=True, check=True).stdout.strip()
            subprocess.run(["git", "update-index", "--add", "--cacheinfo",
                            f"100644,{blob},{rel}"], cwd=HERE, env=env,
                           capture_output=True, text=True, check=True)
        tree = subprocess.run(["git", "write-tree"], cwd=HERE, env=env,
                              capture_output=True, text=True, check=True).stdout.strip()
        if parent:
            parent_tree = _git("rev-parse", f"{branch}^{{tree}}", check=False).stdout.strip()
            if parent_tree == tree:
                return {"status": "no changes to commit", "branch": branch, "files": files}
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        msg = f"data refresh {season} — {stamp}\n\nAutomated pipeline run. Allowlisted outputs only."
        ct = ["commit-tree", tree, "-m", msg] + (["-p", parent] if parent else [])
        commit = _git(*ct).stdout.strip()
        _git("update-ref", f"refs/heads/{branch}", commit)
    finally:
        try:
            os.unlink(idx.name)
        except OSError:
            pass

    out = {"status": "committed", "branch": branch, "commit": commit[:9], "files": files}
    if push:
        pr = _git("push", "origin", f"{branch}:{branch}", check=False)
        out["push"] = "ok" if pr.returncode == 0 else f"FAILED: {pr.stderr.strip()[:300]}"
    return out


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def _rowcount(path, cap_bytes=250_000_000):
    try:
        if os.path.getsize(path) > cap_bytes:
            return None
        with open(path, "rb") as fh:
            return max(sum(1 for _ in fh) - 1, 0)
    except Exception:
        return None


def _sizeof(path):
    try:
        n = float(os.path.getsize(path))
    except OSError:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}TB"


def write_report(log_dir, season, gate, results, commit, started, ended):
    lines = []
    lines.append(f"# cv19 pipeline run — {started:%Y-%m-%d %H:%M}")
    lines.append("")
    lines.append(f"- season: **{season}**")
    lines.append(f"- game-day gate: **{'RAN' if gate[0] else 'SKIPPED'}** — {gate[1]}")
    dur = (ended - started).total_seconds()
    lines.append(f"- total wall time: **{dur/60:.1f} min**")
    ok = sum(1 for r in results if r["status"] == "OK")
    fail = [r for r in results if r["status"].startswith("FAIL")]
    lines.append(f"- stages: **{ok}/{len(results)} OK**"
                 + (f", **{len(fail)} FAILED**" if fail else ""))
    lines.append("")
    lines.append("## Stages")
    lines.append("")
    lines.append("| stage | status | time |")
    lines.append("|---|---|---|")
    for r in results:
        lines.append(f"| {r['name']} | {r['status']} | {r['seconds']:.0f}s |")
    lines.append("")
    lines.append("## Committed outputs")
    lines.append("")
    if isinstance(commit, dict) and commit.get("files"):
        lines.append(f"branch `{commit.get('branch')}`"
                     + (f", commit `{commit.get('commit')}`" if commit.get("commit") else "")
                     + (f", push {commit.get('push')}" if commit.get("push") else ""))
        lines.append("")
        lines.append("| file | rows | size |")
        lines.append("|---|---|---|")
        for rel in commit["files"]:
            p = os.path.join(HERE, rel)
            rc = _rowcount(p)
            lines.append(f"| {rel} | {rc if rc is not None else '—'} | {_sizeof(p)} |")
    else:
        lines.append(str(commit.get("status") if isinstance(commit, dict) else commit))
    lines.append("")
    if fail:
        lines.append("## Failures")
        lines.append("")
        for r in fail:
            lines.append(f"- **{r['name']}** ({r['status']}) — see `{r.get('log','')}`")
        lines.append("")
    report = "\n".join(lines)
    with open(os.path.join(log_dir, "REPORT.md"), "w") as fh:
        fh.write(report)
    latest = os.path.join(HERE, "logs", "latest_report.md")
    os.makedirs(os.path.dirname(latest), exist_ok=True)
    with open(latest, "w") as fh:
        fh.write(report)
    return report


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv=None):
    p = argparse.ArgumentParser(description="cv19 automatic data + model pipeline")
    p.add_argument("--season", type=int, default=None, help="override the current season")
    p.add_argument("--python", default=sys.executable, help="interpreter for the -m stages")
    p.add_argument("--dry-run", action="store_true", help="print the plan; touch nothing")
    p.add_argument("--ignore-gate", action="store_true", help="run even if no game yesterday")
    p.add_argument("--gate-only", action="store_true", help="print the game-day decision and exit")
    p.add_argument("--only", choices=["collect", "build", "model", "forecast"],
                   help="run only this stage group")
    p.add_argument("--from", dest="from_stage", help="resume from this stage name")
    p.add_argument("--skip", action="append", default=[], help="stage name to skip (repeatable)")
    p.add_argument("--no-commit", action="store_true", help="don't touch git")
    p.add_argument("--no-push", action="store_true", help="commit locally but don't push")
    p.add_argument("--commit-anyway", action="store_true", help="commit even if a stage failed")
    p.add_argument("--branch", default=COMMIT_BRANCH, help="branch for committed outputs")
    args = p.parse_args(argv)

    season = args.season or current_season()
    gate = (True, "gate ignored (--ignore-gate)") if args.ignore_gate \
        else game_played_yesterday(season)

    if args.gate_only:
        print(f"season {season}: {'RUN' if gate[0] else 'SKIP'} — {gate[1]}")
        return 0
    if not gate[0] and not args.dry_run:
        print(f"[gate] season {season}: no run — {gate[1]}")
        return 0

    stages = [s for s in build_stages(season) if s.enabled and s.name not in args.skip]
    if args.only:
        stages = [s for s in stages if s.group == args.only]
    if args.from_stage:
        names = [s.name for s in stages]
        if args.from_stage in names:
            stages = stages[names.index(args.from_stage):]

    started = dt.datetime.now()
    log_dir = os.path.join(HERE, "logs", f"pipeline_{started:%Y%m%d_%H%M%S}")
    os.makedirs(log_dir, exist_ok=True)

    banner_when = "DRY RUN" if args.dry_run else started.strftime("%Y-%m-%d %H:%M")
    print(f"cv19 pipeline — season {season} — {banner_when}")
    print(f"gate: {'RUN' if gate[0] else 'SKIP'} — {gate[1]}")
    print(f"stages: {', '.join(s.name for s in stages)}\n")

    results, aborted = [], False
    for s in stages:
        print(f"  -> {s.name} ...", flush=True)
        res = run_stage(s, args.python, log_dir, args.dry_run)
        results.append(res)
        print(f"     {res['status']} ({res['seconds']:.0f}s)")
        if res["status"].startswith("FAIL") and not s.optional and not args.dry_run:
            print(f"  !! required stage '{s.name}' failed — aborting (see {res.get('log')})")
            aborted = True
            break

    # commit
    do_commit = (not args.no_commit and not args.dry_run and (not aborted or args.commit_anyway))
    if args.dry_run:
        commit = {"status": "PLAN", "branch": args.branch, "files": resolve_commit_files()}
    elif do_commit:
        commit = commit_and_push(resolve_commit_files(), args.branch, season,
                                 push=not args.no_push, dry_run=False)
    else:
        commit = {"status": "skipped (aborted run)" if aborted else "skipped (--no-commit)"}

    ended = dt.datetime.now()
    report = write_report(log_dir, season, gate, results, commit, started, ended)
    print("\n" + "=" * 60 + "\n" + report + "\n" + "=" * 60)
    print(f"\nreport: {os.path.join(log_dir, 'REPORT.md')}")
    return 1 if aborted else 0


if __name__ == "__main__":
    sys.exit(main())
