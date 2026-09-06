"""Data access for the Streamlit app.

Everything the app needs is precomputed into app_data/ by
analytics/build_app_data.py. Nothing here touches raw play-by-play, and nothing
recomputes a benchmark -- the flags and grades are baked in at build time so the
app and the analysis can never disagree about what a grade means.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "app_data"


def _read(name: str) -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / name)


@lru_cache(maxsize=1)
def matches() -> pd.DataFrame:
    """One row per team per match, with the seven flags and the 0-7 grade."""
    return _read("matches.parquet")


@lru_cache(maxsize=1)
def team_seasons() -> pd.DataFrame:
    """One row per team-season: mean grade, per-benchmark hit rate, record, ranks."""
    return _read("team_seasons.parquet")


@lru_cache(maxsize=1)
def league_baselines() -> pd.DataFrame:
    """Per-season percentile table for every metric."""
    return _read("league_baselines.parquet")


@lru_cache(maxsize=1)
def benchmarks() -> list[dict]:
    """Benchmark definitions. Filter on `graded` for the seven that make up the grade."""
    return json.loads((DATA_DIR / "benchmarks.json").read_text())


@lru_cache(maxsize=1)
def meta() -> dict:
    return json.loads((DATA_DIR / "meta.json").read_text())


def graded_benchmarks() -> list[dict]:
    return [b for b in benchmarks() if b["graded"]]


def context_benchmarks() -> list[dict]:
    return [b for b in benchmarks() if not b["graded"]]


def seasons() -> list[str]:
    return sorted(matches().season.unique().tolist(), reverse=True)


def conferences(season: str) -> list[str]:
    ts = team_seasons()
    return sorted(ts[ts.season == season].conference.dropna().unique().tolist())


def power_rankings(season: str, conference: str | None = None,
                   min_matches: int = 15) -> pd.DataFrame:
    """Teams ordered by mean match grade. Ranks are league-wide even when filtered,
    so a conference view still shows where its teams sit nationally."""
    ts = team_seasons()
    out = ts[(ts.season == season) & (ts.graded_matches >= min_matches)].copy()
    if conference:
        out = out[out.conference == conference]
    return out.sort_values("grade", ascending=False).reset_index(drop=True)


def team_matches(season: str, team: str) -> pd.DataFrame:
    m = matches()
    return m[(m.season == season) & (m.team == team)].sort_values("match_date")


def benchmark_profile(season: str, team: str) -> pd.DataFrame:
    """Per-benchmark hit rate for one team against the league median, for a team page."""
    tm = team_matches(season, team)
    league = matches()
    league = league[league.season == season]
    rows = []
    for b in graded_benchmarks():
        col = b["flag_column"]
        if col not in tm.columns:
            continue
        rows.append({
            "benchmark": b["label"], "phase": b["phase"],
            "team_rate": tm[col].mean(), "league_rate": league[col].mean(),
        })
    out = pd.DataFrame(rows)
    out["vs_league"] = out.team_rate - out.league_rate
    return out


def grade_vs_wins(season: str, min_matches: int = 15) -> pd.DataFrame:
    ts = team_seasons()
    return ts[(ts.season == season) & (ts.graded_matches >= min_matches)][
        ["team", "conference", "grade", "win_pct", "graded_matches"]]


@lru_cache(maxsize=1)
def power_ratings() -> pd.DataFrame:
    """Opponent-adjusted ratings: overall / offense / defense, with national ranks."""
    return _read("power_ratings.parquet")


def rankings(season: str, conference: str | None = None,
             min_matches: int = 10) -> pd.DataFrame:
    """Power rankings joined to record and conference.

    Ranks stay national when a conference filter is applied, matching the CFB app.
    """
    pr = power_ratings()
    pr = pr[(pr.season == season) & (pr.n_matches >= min_matches)]
    ts = team_seasons()[["season", "team", "conference", "wins", "losses",
                         "win_pct", "grade", "grade_rank", "graded_matches"]]
    out = pr.merge(ts, on=["season", "team"], how="left")
    if conference:
        out = out[out.conference == conference]
    return out.sort_values("rank_overall").reset_index(drop=True)
