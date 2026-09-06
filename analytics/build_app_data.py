"""Build the artifacts the Streamlit app reads.

The app must never touch raw play-by-play: that is 8.8 GB of CSV, far past what a
hosted Streamlit instance can hold. This stage collapses it to a few megabytes of
parquet that can live in the repo and load instantly.

    pbp CSV  --rally_engine-->  rally parquet  --build_match_metrics-->  match metrics
                                                        |
                                                        +--build_app_data--> app_data/

Outputs, all under app_data/:
    matches.parquet       one row per team per match: the seven graded metrics, their
                          pass/fail flags, the 0-7 grade, result, and context metrics
    team_seasons.parquet  one row per team-season: mean grade, per-benchmark hit rate,
                          record, and season ranks
    league_baselines.parquet  per-season percentile table for every metric, so the app
                          can place a team in the distribution without scanning matches
    benchmarks.json       the benchmark definitions, so the app renders labels and
                          thresholds from one source of truth rather than hardcoding
    meta.json             build timestamp, coverage, and the calibration caveat
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import power_ratings
from benchmarks import CONTEXT_METRICS, VOLLEYBALL_7, score

GRADED = [m for m, *_ in VOLLEYBALL_7]
CONTEXT = [m for m, *_ in CONTEXT_METRICS]
PERCENTILE_METRICS = GRADED + CONTEXT + ["rally_win_pct"]

IDENTITY = ["season_label", "date", "team", "conference", "opponent", "location",
            "won", "sets_for", "sets_against"]


def build_matches(metrics_parquet: Path) -> pd.DataFrame:
    df = pd.read_parquet(metrics_parquet)
    df = score(df, include_context=True)

    df["location"] = ["home" if t == h else "away" for t, h in zip(df.team, df.home_team)]
    df["opponent"] = df.opponent_matched
    df["season"] = df.season_label
    df["match_date"] = pd.to_datetime(df.date, format="%m/%d/%Y", errors="coerce")
    df["grade"] = df.bench_hit

    flags = [f"b_{m}" for m in GRADED + CONTEXT]
    mirrors = [c for c in df.columns if c.startswith("opp_")]
    keep = (["season", "match_date", "team", "conference", "opponent", "location",
             "won", "sets_for", "sets_against", "grade"]
            + GRADED + CONTEXT + ["rally_win_pct"] + mirrors + flags)
    keep = list(dict.fromkeys(keep))
    out = df[[c for c in keep if c in df.columns]].copy()
    return out.sort_values(["season", "match_date", "team"]).reset_index(drop=True)


def official_records(box_dir: Path, seasons: list[str]) -> pd.DataFrame:
    """True W-L per team-season, read straight from the box scores.

    The graded match table only contains matches whose play-by-play joined to a box
    score (~94%), so counting wins there would understate real records -- a public
    app must not show a team as 30-0 when they were 33-1. Records come from the
    complete box-score file; grades come from the joined subset.
    """
    import csv as _csv
    rows = []
    for season in seasons:
        path = box_dir / f"wvb_teammatch_div1_{season}.csv"
        if not path.exists():
            continue
        with open(path, newline="") as f:
            for r in _csv.DictReader(f):
                result = (r["Result"] or "").strip()
                if not result or result[0] not in "WL":
                    continue  # cancelled / postponed
                rows.append({"season": season, "team": r["Team"],
                             "won": 1 if result[0] == "W" else 0})
    df = pd.DataFrame(rows)
    out = df.groupby(["season", "team"], as_index=False).agg(
        official_matches=("won", "size"), wins=("won", "sum"))
    out["losses"] = out.official_matches - out.wins
    out["win_pct"] = out.wins / out.official_matches
    return out


def build_team_seasons(matches: pd.DataFrame, records: pd.DataFrame) -> pd.DataFrame:
    graded_flags = [f"b_{m}" for m in GRADED]
    agg = {
        "graded_matches": ("won", "size"),
        "grade": ("grade", "mean"),
        "grade_sd": ("grade", "std"),
    }
    agg.update({m: (m, "mean") for m in GRADED + ["rally_win_pct"]})
    agg.update({f: (f, "mean") for f in graded_flags})

    ts = matches.groupby(["season", "team", "conference"], as_index=False).agg(**agg)
    ts = ts.merge(records, on=["season", "team"], how="left")
    ts["graded_share"] = ts.graded_matches / ts.official_matches

    # season ranks (1 = best) computed once here so the app never re-derives them
    ts["grade_rank"] = ts.groupby("season").grade.rank(ascending=False, method="min").astype(int)
    ts["win_pct_rank"] = ts.groupby("season").win_pct.rank(ascending=False, method="min").astype(int)
    return ts.sort_values(["season", "grade_rank"]).reset_index(drop=True)


def build_league_baselines(matches: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for season, grp in matches.groupby("season"):
        for metric in PERCENTILE_METRICS:
            if metric not in grp.columns:
                continue
            s = pd.to_numeric(grp[metric], errors="coerce").dropna()
            if s.empty:
                continue
            rows.append({
                "season": season, "metric": metric, "n": len(s), "mean": s.mean(),
                **{f"p{q}": s.quantile(q / 100) for q in (5, 10, 25, 50, 75, 90, 95)},
            })
    return pd.DataFrame(rows)


def benchmark_definitions() -> list[dict]:
    out = []
    for spec, graded in ((VOLLEYBALL_7, True), (CONTEXT_METRICS, False)):
        for metric, direction, threshold, label, phase in spec:
            out.append({
                "metric": metric, "label": label, "phase": phase, "graded": graded,
                "direction": "higher_is_better" if direction > 0 else "lower_is_better",
                "threshold": threshold, "flag_column": f"b_{metric}",
            })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--metrics", type=Path, default=Path("data/match_metrics.parquet"))
    ap.add_argument("--box-dir", type=Path,
                    default=Path("data/ncaavolleyballr/data-csv"),
                    help="team-match CSVs, used for true W-L records")
    ap.add_argument("--out-dir", type=Path, default=Path("app_data"))
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    matches = build_matches(args.metrics)
    records = official_records(args.box_dir, sorted(matches.season.unique().tolist()))
    team_seasons = build_team_seasons(matches, records)
    baselines = build_league_baselines(matches)

    ratings = power_ratings.build(args.metrics)
    ratings.to_parquet(args.out_dir / "power_ratings.parquet", compression="zstd", index=False)

    matches.to_parquet(args.out_dir / "matches.parquet", compression="zstd", index=False)
    team_seasons.to_parquet(args.out_dir / "team_seasons.parquet", compression="zstd", index=False)
    baselines.to_parquet(args.out_dir / "league_baselines.parquet", compression="zstd", index=False)
    (args.out_dir / "benchmarks.json").write_text(json.dumps(benchmark_definitions(), indent=2))

    corr = team_seasons[team_seasons.graded_matches >= 20].groupby("season").apply(
        lambda g: g.grade.corr(g.win_pct), include_groups=False)
    meta = {
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "NCAA play-by-play and box scores via JeffreyRStevens/ncaavolleyballr",
        "sport": "women's volleyball", "division": "D1",
        "seasons": sorted(matches.season.unique().tolist()),
        "team_match_rows": int(len(matches)),
        "team_seasons": int(len(team_seasons)),
        "median_graded_share": round(float(team_seasons.graded_share.median()), 4),
        "graded_benchmarks": len(VOLLEYBALL_7),
        "grade_vs_win_pct_by_season": {k: round(float(v), 4) for k, v in corr.items()},
        "caveats": [
            "Thresholds are calibrated on women's D1; men's and D2/D3 need recalibration.",
            "Matches join pbp to box scores on (date, unordered team pair) because neither "
            "source carries a contest ID; roughly 6% of team-matches drop out, mostly "
            "same-day repeat pairings in tournaments.",
            "The grade describes a match; it is not a forecast of the next one.",
        ],
    }
    (args.out_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    print(f"matches.parquet          {len(matches):>7,} rows  "
          f"{(args.out_dir/'matches.parquet').stat().st_size/1e6:>6.2f} MB")
    print(f"team_seasons.parquet     {len(team_seasons):>7,} rows  "
          f"{(args.out_dir/'team_seasons.parquet').stat().st_size/1e6:>6.2f} MB")
    print(f"league_baselines.parquet {len(baselines):>7,} rows  "
          f"{(args.out_dir/'league_baselines.parquet').stat().st_size/1e6:>6.2f} MB")
    print(f"power_ratings.parquet    {len(ratings):>7,} rows  "
          f"{(args.out_dir/'power_ratings.parquet').stat().st_size/1e6:>6.2f} MB")
    print(f"\ngrade vs win% by season: "
          + ", ".join(f"{k} {v:+.3f}" for k, v in meta['grade_vs_win_pct_by_season'].items()))


if __name__ == "__main__":
    main()
