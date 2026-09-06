"""Join rally-derived phase metrics with box scores into one row per team per match.

This is the table every benchmark threshold is derived from. Rally metrics come from
the pbp-derived rally parquet (analytics/rally_engine.py); box-score metrics come from
the NCAA team-match CSVs. Matches are joined on (date, unordered team pair) because
neither source carries a contest ID and teams play twice on the same date in tournaments.
"""
from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

import duckdb
import pandas as pd

VENUE_SUFFIX = re.compile(r"\s*@.*$")


def clean_opponent(raw: str) -> str:
    """'@ Fairfield' -> 'Fairfield'; 'Central Conn. St. @Fairfield, CT' -> 'Central Conn. St.'"""
    name = raw.strip()
    if name.startswith("@"):
        name = name[1:].strip()
    return VENUE_SUFFIX.sub("", name).strip()


def rally_metrics(parquet: Path) -> pd.DataFrame:
    """Per team per match: sideout, point-score, first-ball rates, point-source mix."""
    con = duckdb.connect()
    return con.sql(f"""
        WITH sides AS (
            SELECT date, away_team, home_team, serve_team, recv_team, winner,
                   first_ball, end_event
            FROM read_parquet('{parquet}')
        ),
        recv AS (   -- what a team does when receiving serve
            SELECT date, away_team, home_team, recv_team AS team,
                   count(*) AS recv_rallies,
                   sum(CASE WHEN winner = recv_team THEN 1 ELSE 0 END) AS so_won,
                   sum(CASE WHEN winner = recv_team AND first_ball THEN 1 ELSE 0 END) AS fbso_won
            FROM sides GROUP BY 1,2,3,4
        ),
        serve AS (  -- what a team does when serving
            SELECT date, away_team, home_team, serve_team AS team,
                   count(*) AS serve_rallies,
                   sum(CASE WHEN winner = serve_team THEN 1 ELSE 0 END) AS ps_won,
                   sum(CASE WHEN winner <> serve_team AND first_ball THEN 1 ELSE 0 END) AS opp_fbso_allowed,
                   sum(CASE WHEN end_event = 'Ace' AND winner = serve_team THEN 1 ELSE 0 END) AS aces,
                   sum(CASE WHEN end_event = 'Service error' THEN 1 ELSE 0 END) AS serve_errs
            FROM sides GROUP BY 1,2,3,4
        ),
        pts AS (    -- how a team's points were won
            SELECT date, away_team, home_team, winner AS team,
                   sum(CASE WHEN end_event IN ('Kill','First ball kill') THEN 1 ELSE 0 END) AS kill_pts,
                   sum(CASE WHEN end_event = 'Block' THEN 1 ELSE 0 END) AS block_pts,
                   sum(CASE WHEN end_event IN ('Attack error','Service error','Set error',
                                               'Ball handling error','Block error','Dig error')
                            THEN 1 ELSE 0 END) AS opp_error_pts
            FROM sides GROUP BY 1,2,3,4
        )
        SELECT r.date, r.away_team, r.home_team, r.team,
               r.recv_rallies, r.so_won, r.fbso_won,
               s.serve_rallies, s.ps_won, s.opp_fbso_allowed, s.aces, s.serve_errs,
               p.kill_pts, p.block_pts, p.opp_error_pts
        FROM recv r
        JOIN serve s USING (date, away_team, home_team, team)
        LEFT JOIN pts p USING (date, away_team, home_team, team)
    """).df()


def box_scores(csv_path: Path) -> pd.DataFrame:
    rows = []
    with open(csv_path, newline="") as f:
        for r in csv.DictReader(f):
            result = (r["Result"] or "").strip()
            if not result or result[0] not in "WL":
                continue  # cancelled / postponed
            def num(key):
                v = r.get(key, "")
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return 0.0
            sets_for, sets_against = 0, 0
            m = re.search(r"(\d+)\s*-\s*(\d+)", result)
            if m:
                sets_for, sets_against = int(m.group(1)), int(m.group(2))
            rows.append({
                "date": r["Date"], "team": r["Team"], "opponent": clean_opponent(r["Opponent"]),
                "conference": r["Conference"], "season": r["Season"],
                "won": 1 if result[0] == "W" else 0,
                "sets": num("S"), "sets_for": sets_for, "sets_against": sets_against,
                "kills": num("Kills"), "att_errors": num("Errors"), "attacks": num("Total Attacks"),
                "assists": num("Assists"), "box_aces": num("Aces"), "box_serr": num("SErr"),
                "digs": num("Digs"), "ret_att": num("RetAtt"), "rec_errors": num("RErr"),
                "block_solos": num("Block Solos"), "block_assists": num("Block Assists"),
                "block_errors": num("BErr"),
            })
    return pd.DataFrame(rows)


def build(pbp_parquet: Path, teammatch_csv: Path, season_label: str) -> pd.DataFrame:
    rally = rally_metrics(pbp_parquet)
    box = box_scores(teammatch_csv)

    # unordered-pair join key: neither source has a contest ID
    rally["pair"] = [frozenset((a, h)) for a, h in zip(rally.away_team, rally.home_team)]
    rally["key"] = list(zip(rally.date, rally.pair, rally.team))
    box["pair"] = [frozenset((t, o)) for t, o in zip(box.team, box.opponent)]
    box["key"] = list(zip(box.date, box.pair, box.team))

    # drop same-date duplicate keys on both sides (same two teams twice in one day)
    rally = rally.drop_duplicates("key", keep=False)
    box = box.drop_duplicates("key", keep=False)

    df = box.merge(rally.drop(columns=["pair"]), on="key", how="inner", suffixes=("", "_r"))
    df = df.drop(columns=["key", "pair"])
    df["season_label"] = season_label

    # --- rate metrics (all normalized; raw counts are useless across 3-5 set matches) ---
    d = df
    d["sideout_pct"] = d.so_won / d.recv_rallies
    d["fbso_pct"] = d.fbso_won / d.recv_rallies
    d["point_score_pct"] = d.ps_won / d.serve_rallies
    d["opp_fbso_allowed"] = d.opp_fbso_allowed / d.serve_rallies
    d["ace_pct"] = d.aces / d.serve_rallies
    d["serve_err_pct"] = d.serve_errs / d.serve_rallies
    d["hit_pct"] = (d.kills - d.att_errors) / d.attacks.replace(0, pd.NA)
    d["kill_pct"] = d.kills / d.attacks.replace(0, pd.NA)
    d["att_err_pct"] = d.att_errors / d.attacks.replace(0, pd.NA)
    d["rec_err_pct"] = d.rec_errors / d.ret_att.replace(0, pd.NA)
    d["blocks_per_set"] = (d.block_solos + d.block_assists / 2) / d.sets.replace(0, pd.NA)
    d["digs_per_set"] = d.digs / d.sets.replace(0, pd.NA)
    d["kill_pt_share"] = d.kill_pts / (d.kill_pts + d.block_pts + d.opp_error_pts)
    d["rally_win_pct"] = (d.so_won + d.ps_won) / (d.recv_rallies + d.serve_rallies)
    # transition sideout: sideouts won after the first ball failed
    d["trans_so_pct"] = (d.so_won - d.fbso_won) / (d.recv_rallies - d.fbso_won).replace(0, pd.NA)
    return d


# Columns mirrored from the opponent's row of the same match. Several graded
# benchmarks are defined against the opponent (opp hitting efficiency, hitting
# margin), so the table is not self-contained without them.
MIRRORED = ["hit_pct", "kill_pct", "sideout_pct", "fbso_pct", "point_score_pct",
            "ace_pct", "blocks_per_set", "digs_per_set", "rec_err_pct"]


def add_opponent_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Attach opp_* columns and the derived metrics the benchmarks need."""
    keys = ["date", "away_team", "home_team", "season_label"]
    mirror = df[keys + ["team"] + MIRRORED].rename(
        columns={"team": "opponent_matched", **{c: f"opp_{c}" for c in MIRRORED}})
    out = df.merge(mirror, on=keys, how="inner")
    out = out[out.team != out.opponent_matched].copy()

    # aces earned per service error committed; a team with zero errors keeps its ace count
    out["ace_to_err"] = (out.aces / out.serve_errs.replace(0, pd.NA)).fillna(out.aces)
    out["hit_margin"] = out.hit_pct - out.opp_hit_pct
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rally-dir", type=Path, default=Path("data/rallies"))
    ap.add_argument("--box-dir", type=Path, default=Path("data/ncaavolleyballr/data-csv"))
    ap.add_argument("--sport", default="wvb")
    ap.add_argument("--division", default="div1")
    ap.add_argument("--years", nargs="+", type=int, default=[2021, 2022, 2023, 2024, 2025])
    ap.add_argument("--out", type=Path, default=Path("data/match_metrics.parquet"))
    args = ap.parse_args()

    frames = []
    for year in args.years:
        pq_path = args.rally_dir / f"{args.sport}_rallies_{args.division}_{year}.parquet"
        box_path = args.box_dir / f"{args.sport}_teammatch_{args.division}_{year}.csv"
        if not pq_path.exists() or not box_path.exists():
            print(f"skip {year}: missing {pq_path if not pq_path.exists() else box_path}")
            continue
        df = add_opponent_columns(build(pq_path, box_path, str(year)))
        frames.append(df)
        print(f"{year}: {len(df):,} team-match rows  (box rows {len(box_scores(box_path)):,})")

    out = pd.concat(frames, ignore_index=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, compression="zstd")
    print(f"\nwrote {args.out}  {len(out):,} rows, {args.out.stat().st_size/1e6:.1f} MB")


if __name__ == "__main__":
    main()
