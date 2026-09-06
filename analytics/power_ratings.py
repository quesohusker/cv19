"""Opponent-adjusted power ratings, the volleyball analogue of the CFB app's
rating_overall / rating_off / rating_def.

WHY THIS EXISTS SEPARATELY FROM THE GRADE
-----------------------------------------
The benchmark grade describes a match and tracks season success (r=+0.96 with season
win%), but it is unadjusted, so a team feasting on a weak schedule grades like a team
surviving a brutal one. In the 2024 raw grade table UTEP and UT Arlington sit in the
national top ten. Ranking is a different job and needs a different number.

THE MODEL
---------
One ridge regression over every team-match. Side-out rate is the currency: every rally
is either sided out or not, and a team's point-score rate is by definition one minus
its opponent's side-out rate, so a single model covers both phases.

    sideout_pct(i receiving against j)  =  mu + off_i - def_j

  off_i   how much better than average team i sides out            (offense)
  def_j   how much team j suppresses the opponent's side-out       (defense)
  overall = off + def, the net rally margin per 100 rallies

Ratings are centered so the average D1 team is 0.0 and expressed in percentage points
of side-out rate, so "+6.1" reads as six more side-outs per hundred receive rallies
than an average team would manage against the same opponents.

Ridge (lambda default 1.0) keeps teams with short or lopsided schedules from taking
extreme values; with ~340 teams and ~9,500 matches a season the system is well
determined, and the penalty mostly shrinks the tails.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def fit_season(df: pd.DataFrame, ridge: float = 1.0) -> pd.DataFrame:
    """Fit mu + off_i - def_j to observed side-out rates for one season."""
    teams = sorted(set(df.team) | set(df.opponent_matched))
    index = {t: i for i, t in enumerate(teams)}
    n, k = len(df), len(teams)

    # design: [intercept | offense one-hot | defense one-hot (negative)]
    X = np.zeros((n, 1 + 2 * k))
    X[:, 0] = 1.0
    rows = np.arange(n)
    X[rows, 1 + df.team.map(index).to_numpy()] = 1.0
    X[rows, 1 + k + df.opponent_matched.map(index).to_numpy()] = -1.0
    y = df.sideout_pct.to_numpy()

    # ridge on the team effects only, never on the intercept
    penalty = np.eye(1 + 2 * k) * ridge
    penalty[0, 0] = 0.0
    beta = np.linalg.solve(X.T @ X + penalty, X.T @ y)

    mu = beta[0]
    off = beta[1:1 + k]
    dfn = beta[1 + k:]
    off = off - off.mean()          # center so average team is 0
    dfn = dfn - dfn.mean()

    out = pd.DataFrame({
        "team": teams,
        "rating_off": off * 100,     # percentage points of side-out
        "rating_def": dfn * 100,
        "league_sideout": mu * 100,
    })
    out["rating_overall"] = out.rating_off + out.rating_def
    counts = df.groupby("team").size().rename("n_matches")
    out = out.merge(counts, left_on="team", right_index=True, how="left")
    out["n_matches"] = out.n_matches.fillna(0).astype(int)
    return out


def build(metrics_parquet: Path, ridge: float = 1.0, min_matches: int = 5) -> pd.DataFrame:
    src = pd.read_parquet(metrics_parquet)
    src = src.dropna(subset=["sideout_pct", "opponent_matched"])
    frames = []
    for season, grp in src.groupby("season_label"):
        fit = fit_season(grp, ridge=ridge)
        fit["season"] = season
        fit = fit[fit.n_matches >= min_matches]
        fit["rank_overall"] = fit.rating_overall.rank(ascending=False, method="min").astype(int)
        fit["rank_off"] = fit.rating_off.rank(ascending=False, method="min").astype(int)
        fit["rank_def"] = fit.rating_def.rank(ascending=False, method="min").astype(int)
        frames.append(fit)
    cols = ["season", "team", "rating_overall", "rating_off", "rating_def",
            "rank_overall", "rank_off", "rank_def", "n_matches", "league_sideout"]
    return pd.concat(frames, ignore_index=True)[cols].sort_values(
        ["season", "rank_overall"]).reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--metrics", type=Path, default=Path("data/match_metrics.parquet"))
    ap.add_argument("--out", type=Path, default=Path("app_data/power_ratings.parquet"))
    ap.add_argument("--ridge", type=float, default=1.0)
    args = ap.parse_args()

    ratings = build(args.metrics, ridge=args.ridge)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    ratings.to_parquet(args.out, compression="zstd", index=False)
    print(f"wrote {args.out}  {len(ratings):,} team-seasons")
    latest = ratings.season.max()
    print(f"\n{latest} top 15 by opponent-adjusted rating:")
    print(ratings[ratings.season == latest].head(15)[
        ["rank_overall", "team", "rating_overall", "rating_off", "rating_def", "n_matches"]
    ].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
