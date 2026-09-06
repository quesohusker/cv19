"""The Volleyball 7: per-match benchmarks for grading a team.

Each benchmark is a binary test a team clears or misses in a match. Counting them
gives a 0-7 match grade; averaging over a season grades the team.

WHY SEVEN AND NOT FOURTEEN
--------------------------
This started as a 14-benchmark set modeled on football scorecards. Volleyball does
not support fourteen independent measurements, for a structural reason: every rally
is won by exactly one team and is either a side-out or a point-score, so most
"different" volleyball stats are components of the same two numbers.

Measured on 37,118 team-matches (women's D1, 2021-2024):

  * Two of the original fourteen were ALGEBRAIC IDENTITIES, not merely correlations:
        hitting efficiency == kill% - attack error%              (max diff 1.1e-16)
        side-out% == fbso% + (1 - fbso%) * transition side-out%  (max diff 2.2e-16)
    In each trio the third number carries exactly zero new information. Three
    benchmarks had infinite VIF; three more had VIF between 42 and 159.

  * PCA on the fourteen: PC1 explains 40.9% of variance, and 6 components cover 80%.
    The effective dimensionality is around six, not fourteen.

  * Cutting to six costs nothing. Same-match discrimination (AUC) 0.9535 vs 0.9590
    for all fourteen; forward prediction is actually slightly better. Equal-weight
    counting means every added benchmark is an implicit weight, so redundant or
    weakly-discriminating ones dilute the score rather than sharpen it -- an
    8-benchmark variant scored WORSE than that 6 (AUC 0.9487).

  * The seventh, hitting margin, was then added back because it is the one addition
    that carries genuinely new information. The absolute pair (own hit% >= .199,
    opp hit% <= .199) tests two fixed bars independently and loses the relationship
    between them: .190 against an opponent held to .050 scores 1/2 despite being
    dominant, while .210 against .195 scores 2/2 despite being a coin flip. Margin
    fixes both. It has the highest single-benchmark lift measured anywhere in this
    work (+81.1) and lifts set AUC 0.9535 -> 0.9635.

    That gain is information, not arithmetic: adding a DUPLICATE of an existing
    benchmark instead (a free extra scale level, zero new information) moves AUC to
    0.9523 / 0.9491 / 0.9534 -- at or below the 6-benchmark baseline.

    The threshold is ZERO -- simply out-hit the opponent -- not some large margin.
    A .250 bar is cleared in only 6% of team-matches and drops set AUC to 0.9178.
    The intuition it is meant to protect (hitting poorly yourself while smothering
    the opponent) is almost nonexistent at D1 level: in all of 2024, only 12 of 9,594
    team-matches hit under .199 while holding the opponent below .000, and only 3
    paired sub-.199 hitting with a .250+ margin.

THRESHOLDS ARE EMPIRICAL. Each is the value maximizing win/loss discrimination across
2021-2023, constrained to a 30-70% hit rate, then validated out-of-sample on 2024.

WHAT THE GRADE IS FOR, AND WHAT IT ISN'T
----------------------------------------
  * Diagnostic: it localizes *where* a team wins or loses. That is the reason to keep
    seven rather than collapse to two -- side-out% and point-score% alone reach AUC
    0.9221, close on discrimination but useless for telling a coach what broke.
  * Descriptive: the same-match grade ladder is near-deterministic and largely
    tautological -- it grades performance in the match whose result it is compared to.
  * NOT a predictive edge. Forward-tested (first half of season -> second half win%),
    the count reaches r=+0.506, no better than side-out% alone (+0.509) and barely
    ahead of raw win-loss record (+0.487). Adding the margin improved description
    (AUC) without moving prediction (+0.504 -> +0.506) -- consistent with everything
    else here: nothing in this family of stats predicts better than opponent
    adjustment does. Opponent-adjusted net rating (+0.549) is
    what should rank and project teams. Grade with this; rank with that.

Thresholds are calibrated on women's D1. Men's and D2/D3 distributions differ enough
to require recalibration before reuse.
"""
from __future__ import annotations

import pandas as pd

# (key, direction, threshold, label, phase)  direction +1 = higher is better
VOLLEYBALL_7 = [
    # --- side-out phase: what you do when they serve ---
    ("sideout_pct",     +1, 0.5833, "Side-out % >= 58.3%",            "side-out"),
    ("fbso_pct",        +1, 0.3247, "First-ball side-out % >= 32.5%", "in-system offense"),
    ("hit_pct",         +1, 0.1987, "Hitting efficiency >= .199",     "attack"),
    # --- serve phase: what you do when you serve ---
    ("point_score_pct", +1, 0.4189, "Point-score % >= 41.9%",         "serve phase"),
    ("opp_hit_pct",     -1, 0.1987, "Opp hitting efficiency <= .199", "defense"),
    ("ace_to_err",      +1, 0.5333, "Ace-to-service-error >= 0.53",   "serve"),
    # --- the two hitting numbers against each other, which neither absolute captures ---
    ("hit_margin",      +1, 0.0000, "Out-hit the opponent",           "attack vs defense"),
]

# Kept for reference; VOLLEYBALL_7 is the graded set.
VOLLEYBALL_6 = VOLLEYBALL_7[:6]

# Shown on a team page for context; deliberately NOT part of the grade. Each is either
# redundant with a graded benchmark (the identities above), or too weak a discriminator
# to earn equal weight with one. Displaying them costs nothing; scoring them dilutes.
CONTEXT_METRICS = [
    ("trans_so_pct",     +1, 0.4416, "Transition side-out % >= 44.2%",  "scramble offense"),
    ("kill_pct",         +1, 0.3662, "Kill % of attacks >= 36.6%",      "attack"),
    ("att_err_pct",      -1, 0.1687, "Attack error rate <= 16.9%",      "attack"),
    ("rec_err_pct",      -1, 0.0556, "Reception error rate <= 5.6%",    "ball control"),
    ("opp_fbso_allowed", -1, 0.3247, "Opp first-ball side-out <= 32.5%", "serve phase"),
    ("blocks_per_set",   +1, 1.6000, "Blocks per set >= 1.6",           "block"),
    ("digs_per_set",     +1, 12.667, "Digs per set >= 12.7",            "floor defense"),
    ("ace_pct",          +1, 0.0510, "Ace % of serves >= 5.1%",         "serve"),
]


def _apply(df: pd.DataFrame, spec) -> tuple[pd.DataFrame, list[str]]:
    out, cols = df.copy(), []
    for metric, direction, threshold, _label, _phase in spec:
        s = pd.to_numeric(out[metric], errors="coerce")
        hit = (s >= threshold) if direction > 0 else (s <= threshold)
        col = f"b_{metric}"
        out[col] = hit.astype(float).where(s.notna())
        cols.append(col)
    return out, cols


def score(df: pd.DataFrame, include_context: bool = False) -> pd.DataFrame:
    """Add a b_<metric> column per benchmark plus `bench_hit` (0-7) to a match table.

    `hit_margin` is derived here if absent, so callers only need hit_pct and
    opp_hit_pct. With include_context=True the context metrics are also flagged
    (as b_ columns) for display, but they never enter `bench_hit`.
    """
    df = df.copy()
    if "hit_margin" not in df.columns:
        df["hit_margin"] = pd.to_numeric(df["hit_pct"], errors="coerce") - pd.to_numeric(
            df["opp_hit_pct"], errors="coerce")
    out, graded = _apply(df, VOLLEYBALL_7)
    out["bench_hit"] = out[graded].sum(axis=1, min_count=1)
    if include_context:
        out, _ = _apply(out, CONTEXT_METRICS)
    return out


def season_grade(scored: pd.DataFrame, by=("team", "season_label")) -> pd.DataFrame:
    """Average grade per match, plus per-benchmark hit rate, by team-season."""
    cols = [f"b_{m}" for m, *_ in VOLLEYBALL_7]
    agg = {"matches": ("bench_hit", "size"), "bench_hit": ("bench_hit", "mean")}
    agg.update({c: (c, "mean") for c in cols})
    return scored.groupby(list(by)).agg(**agg).reset_index()
