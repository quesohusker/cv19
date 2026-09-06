"""The Volleyball 14: per-match benchmarks for grading a team.

Each benchmark is a binary test a team either clears or misses in a given match.
Counting them gives a 0-14 match grade; averaging that over a season grades the team.

THRESHOLDS ARE EMPIRICAL, NOT INVENTED. Each is the value that maximized
discrimination between winning and losing performances across the 2021-2023 NCAA
women's D1 seasons (~27,500 team-matches), constrained so that between 30% and 70%
of team-matches clear it -- a benchmark almost everyone hits teaches nothing.
Thresholds were then tested out-of-sample on 2024.

WHAT THE COUNT IS GOOD FOR, AND WHAT IT ISN'T:
  * Diagnostic: it localizes *where* a team wins or loses (serve, side-out,
    transition, block, ball control), which a single rating number cannot do.
  * Descriptive: the same-match relationship is near-deterministic (0/14 -> 0% wins,
    7/14 -> 47%, 10/14 -> 95%, 14/14 -> 100%). This is largely tautological -- it
    grades performance in the match whose result it is being compared against.
  * NOT a predictive edge. Forward-tested (first half of a season -> second half
    win%), the 14-count lands at r=+0.509, statistically indistinguishable from
    sideout% alone (r=+0.509) and barely ahead of raw win-loss record (r=+0.487).
    Opponent-adjusted net rating beats all of them (r=+0.549). Use the 14 to explain
    a team; use the adjusted rating to rank or project one.

Division/sex note: thresholds are calibrated on women's D1. Men's volleyball and
D2/D3 have materially different rate distributions -- recalibrate before reusing.
"""
from __future__ import annotations

import pandas as pd

# (key, direction, threshold, label, phase)  direction +1 = higher is better
VOLLEYBALL_14 = [
    # --- SIDE-OUT PHASE: what you do when the opponent serves ---
    ("sideout_pct",      +1, 0.5833, "Side-out % >= 58.3%",            "side-out"),
    ("fbso_pct",         +1, 0.3247, "First-ball side-out % >= 32.5%", "side-out"),
    ("trans_so_pct",     +1, 0.4416, "Transition side-out % >= 44.2%", "side-out"),
    ("hit_pct",          +1, 0.1987, "Hitting efficiency >= .199",     "attack"),
    ("kill_pct",         +1, 0.3662, "Kill % of attacks >= 36.6%",     "attack"),
    ("att_err_pct",      -1, 0.1687, "Attack error rate <= 16.9%",     "attack"),
    ("rec_err_pct",      -1, 0.0556, "Reception error rate <= 5.6%",   "ball control"),
    # --- SERVE/POINT-SCORING PHASE: what you do when you serve ---
    ("point_score_pct",  +1, 0.4189, "Point-score % >= 41.9%",         "serve phase"),
    ("opp_fbso_allowed", -1, 0.3247, "Opp first-ball side-out <= 32.5%", "serve phase"),
    ("opp_hit_pct",      -1, 0.1987, "Opp hitting efficiency <= .199",  "defense"),
    ("blocks_per_set",   +1, 1.6000, "Blocks per set >= 1.6",           "block"),
    ("digs_per_set",     +1, 12.667, "Digs per set >= 12.7",            "defense"),
    ("ace_pct",          +1, 0.0510, "Ace % of serves >= 5.1%",         "serve"),
    ("ace_to_err",       +1, 0.5333, "Ace-to-service-error >= 0.53",    "serve"),
]


def score(df: pd.DataFrame) -> pd.DataFrame:
    """Add one b_<metric> column per benchmark plus `bench_hit` (0-14) to a match table."""
    out = df.copy()
    cols = []
    for metric, direction, threshold, _label, _phase in VOLLEYBALL_14:
        s = pd.to_numeric(out[metric], errors="coerce")
        hit = (s >= threshold) if direction > 0 else (s <= threshold)
        col = f"b_{metric}"
        out[col] = hit.astype(float).where(s.notna())
        cols.append(col)
    out["bench_hit"] = out[cols].sum(axis=1, min_count=1)
    return out


def season_grade(scored: pd.DataFrame, by=("team", "season_label")) -> pd.DataFrame:
    """Average benchmarks hit per match, plus per-benchmark hit rate, by team-season."""
    cols = [f"b_{m}" for m, *_ in VOLLEYBALL_14]
    agg = {"matches": ("bench_hit", "size"), "bench_hit": ("bench_hit", "mean")}
    agg.update({c: (c, "mean") for c in cols})
    return scored.groupby(list(by)).agg(**agg).reset_index()
