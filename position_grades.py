"""
Position Group Grading Rubric for FBS teams.
============================================

Consumes `team_zscores_all_seasons.csv` (produced by fbs_team_stats.py) and
produces A+..F letter grades + 0-100 composite scores for six position groups
(QB, OL, RB, WR/TE, DL/EDGE, Secondary), per team, per week or season-long.

IMPORTANT -- direction is already baked into the z-scores
--------------------------------------------------------
The source file is PRE-DIRECTIONAL: every column is stored so that a HIGHER
z-score is BETTER, including defensive/"allowed" metrics (e.g. a high
`yards_per_pass_att_against` z means the defense allowed FEWER yards/attempt than
average). That sign flip was applied when the z-scores were built.

The grading rubric was written against *raw* z-scores and marks several metrics
with `* [-1]` (int_thrown, sack_rate_allowed, tfl_allowed_approx, fumbles_lost,
and every *_against metric). Those flips are ALREADY IN this file, so re-applying
them would double-invert and grade elite defenses as awful. Therefore, with the
default `pre_directional=True`, this module uses every column AS-IS (no flips).

If you ever point this at a RAW z-score file (against-metrics NOT pre-flipped),
construct with `pre_directional=False` and the columns in RAW_LOWER_IS_BETTER
will be negated for you.

HOW TO RUN (Jupyter on the Mac with the drive mounted)
------------------------------------------------------
    from position_grades import PositionGroupEvaluator
    ev = PositionGroupEvaluator("/Volumes/1TB external/CFDB Stats/team_zscores_all_seasons.csv")

    ev.grade(season=2024, week=10)                 # every team, week 10 of 2024
    ev.grade(season=2024, team="Ohio State")       # season-long (final week)
    ev.grade(season=2024, aggregate="mean")        # season-long via weekly mean
    ev.grade_wide(season=2024)                      # team x group score matrix
    ev.plot_radar(season=2024, team="Ohio State")  # radar of the 6 grades
    ev.plot_compare(["Ohio State", "Michigan"], season=2024)  # grouped bars
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

# ------------------------------------------------------------------- rubric
# Each position group -> list of components. A component is a display name, a
# weight (fraction of the composite), and one or more source columns whose
# z-scores are averaged together (this is how the QB "Risk & Ball Security"
# 20% bucket combines interceptions + sack rate into a single 20% component).
# Weights within a group sum to 1.0.
RUBRIC = {
    "QB": [
        {"name": "Efficiency (YPA)",        "weight": 0.35, "cols": ["yards_per_pass_att_for"]},
        {"name": "High-Leverage Passing",   "weight": 0.25, "cols": ["pass_ypa_3rd_down_for"]},
        {"name": "Ball Accuracy",           "weight": 0.20, "cols": ["comp_pct_for"]},
        {"name": "Risk & Ball Security",    "weight": 0.20, "cols": ["int_thrown", "sack_rate_allowed"]},
    ],
    "OL": [
        {"name": "Run Push",                "weight": 0.40, "cols": ["yards_per_rush_for"]},
        {"name": "Pass Protection",         "weight": 0.30, "cols": ["sack_rate_allowed"]},
        {"name": "Penetration Allowed",     "weight": 0.30, "cols": ["tfl_allowed_approx"]},
    ],
    "RB": [
        {"name": "Rushing Efficiency",      "weight": 0.50, "cols": ["yards_per_rush_for"]},
        {"name": "Big-Play Threat",         "weight": 0.30, "cols": ["longest_rush_for"]},
        {"name": "Ball Security",           "weight": 0.20, "cols": ["fumbles_lost"]},
    ],
    "WR/TE": [
        {"name": "Explosive Passing",       "weight": 0.45, "cols": ["yards_per_pass_att_for"]},
        {"name": "Big-Play Threat",         "weight": 0.35, "cols": ["longest_pass_for"]},
        {"name": "Conversion Reliability",  "weight": 0.20, "cols": ["third_down_pct_for_approx"]},
    ],
    "DL/EDGE": [
        {"name": "Pass Rush Disruption",    "weight": 0.40, "cols": ["sack_rate_made"]},
        {"name": "Backfield Penetration",   "weight": 0.35, "cols": ["tfl_made_approx"]},
        {"name": "Run Defense (POA)",       "weight": 0.25, "cols": ["yards_per_rush_against"]},
    ],
    "Secondary": [
        {"name": "Passing Stinginess",      "weight": 0.40, "cols": ["yards_per_pass_att_against"]},
        {"name": "3rd Down Coverage",       "weight": 0.30, "cols": ["pass_ypa_3rd_down_against"]},
        {"name": "Takeaways",               "weight": 0.20, "cols": ["int_made"]},
        {"name": "Limiting Big Plays",      "weight": 0.10, "cols": ["longest_pass_against"]},
    ],
}
GROUPS = list(RUBRIC)

# Columns that are "lower is better" in RAW z-scores -- i.e. the rubric's `* [-1]`
# markers. In team_zscores_all_seasons.csv these are ALREADY flipped so higher =
# better, so they are only negated when pre_directional=False (a raw z file).
RAW_LOWER_IS_BETTER = {
    "int_thrown", "sack_rate_allowed", "tfl_allowed_approx", "fumbles_lost",
    "yards_per_rush_against", "yards_per_pass_att_against",
    "pass_ypa_3rd_down_against", "longest_pass_against",
}

# 0-100 score -> letter grade. (low, high] bins, top-down; F is the floor.
GRADE_BINS = [
    (90.0, "A+"), (85.0, "A"), (80.0, "A-"),
    (77.0, "B+"), (73.0, "B"), (70.0, "B-"),
    (67.0, "C+"), (63.0, "C"), (60.0, "C-"),
    (57.0, "D+"), (53.0, "D"), (50.0, "D-"),
    (0.0,  "F"),
]

# Scale: score = clip(BASE + SPREAD * z, 0, 100). BASE=65 puts an average unit
# (z=0) at 65 -> the middle of the C band, so the average team grades a C.
# SPREAD=15 keeps the original stretch (z=+1 -> B, z~+1.7 -> A+, z<-1 -> F).
BASE_SCORE, SPREAD = 65.0, 15.0

MIN_SEASON, MAX_SEASON = 2014, 2025
ID_COLS = ["season", "team", "week", "games_played", "wins", "losses", "ties", "week_result"]


def letter_grade(score):
    """Map a 0-100 score to its letter grade; NaN -> 'N/A'."""
    if score is None or (isinstance(score, float) and np.isnan(score)):
        return "N/A"
    for lo, letter in GRADE_BINS:
        if score >= lo:
            return letter
    return "F"


def score_from_z(z, base=BASE_SCORE, spread=SPREAD):
    """0-100 score from a composite z: clip(base + spread*z, 0, 100)."""
    return np.clip(base + spread * z, 0.0, 100.0)


class PositionGroupEvaluator:
    """Grade FBS position groups from a pre-directional z-score file.

    Parameters
    ----------
    source : str | pandas.DataFrame
        Path to team_zscores_all_seasons.csv (or a DataFrame already loaded).
    min_season, max_season : int
        Inclusive season filter (default 2014-2025, the fully-covered range).
    pre_directional : bool
        True (default) -> columns are already "higher = better" (this file), so
        no sign flips. False -> negate RAW_LOWER_IS_BETTER columns first.
    """

    def __init__(self, source, min_season=MIN_SEASON, max_season=MAX_SEASON,
                 pre_directional=True, base=BASE_SCORE, spread=SPREAD):
        df = source if isinstance(source, pd.DataFrame) else pd.read_csv(source)
        if "season" not in df.columns:
            raise ValueError("source is missing a 'season' column -- is this the "
                             "z-scores file (team_zscores_all_seasons.csv)?")
        df = df[(df["season"] >= min_season) & (df["season"] <= max_season)].copy()
        if df.empty:
            raise ValueError(f"no rows in season range [{min_season}, {max_season}]")

        # Apply direction only if the caller says the file is raw (not this one).
        if not pre_directional:
            for c in RAW_LOWER_IS_BETTER:
                if c in df.columns:
                    df[c] = -df[c]

        self.df = df
        self.pre_directional = pre_directional
        self.base = base          # z=0 -> this score (default 65 => average = C)
        self.spread = spread      # points per 1 std of z (default 15)
        self._warn_missing_columns()

    # ---- setup / introspection ------------------------------------------
    def _all_rubric_cols(self):
        return sorted({c for comps in RUBRIC.values() for comp in comps for c in comp["cols"]})

    def _warn_missing_columns(self):
        missing = [c for c in self._all_rubric_cols() if c not in self.df.columns]
        if missing:
            import warnings
            warnings.warn(f"rubric columns not found in the file (grades that use "
                          f"them will redistribute weight): {missing}")

    # ---- row selection ---------------------------------------------------
    def _select(self, season=None, week=None, team=None, aggregate=None):
        """Return one row per (season, team) with the z-columns to grade.

        - week given          -> that exact week's cumulative z-scores.
        - week None, agg=None
          or agg='final'      -> each team's final available week (season-long).
        - agg='mean'          -> each team's weekly z-scores averaged.
        """
        d = self.df
        if season is not None:
            d = d[d["season"] == season]
        if team is not None:
            teams = {team} if isinstance(team, str) else set(team)
            d = d[d["team"].isin(teams)]
        if d.empty:
            return d.copy()

        if week is not None:
            return d[d["week"] == week].copy()

        agg = aggregate or "final"
        num_cols = [c for c in d.columns if c not in ("team", "week_result")]
        if agg == "mean":
            out = d.groupby(["season", "team"], as_index=False)[
                [c for c in num_cols if c not in ("season",)]].mean(numeric_only=True)
            out["week"] = -1                      # -1 marks a season-mean aggregate
            return out
        if agg == "final":
            idx = d.groupby(["season", "team"])["week"].idxmax()
            return d.loc[idx].copy()
        raise ValueError(f"aggregate must be None, 'final', or 'mean'; got {aggregate!r}")

    # ---- core scoring ----------------------------------------------------
    def _composite_z(self, frame, group):
        """Vectorized weighted-composite z for one group over `frame` rows.

        Missing components (all their columns NaN) are dropped and the remaining
        weights are renormalized for that row -- weight redistribution -- so a
        team missing one metric is still graded on the rest.
        """
        n = len(frame)
        num = np.zeros(n)
        wsum = np.zeros(n)
        for comp in RUBRIC[group]:
            cols = [c for c in comp["cols"] if c in frame.columns]
            if not cols:
                continue
            comp_val = frame[cols].mean(axis=1, skipna=True).to_numpy()  # NaN if all NaN
            present = ~np.isnan(comp_val)
            num[present] += comp["weight"] * comp_val[present]
            wsum[present] += comp["weight"]
        with np.errstate(invalid="ignore", divide="ignore"):
            comp_z = np.where(wsum > 0, num / wsum, np.nan)
        return comp_z

    # ---- public API ------------------------------------------------------
    def grade(self, season=None, week=None, team=None, aggregate=None, groups=None):
        """Itemized grades: one row per (team, season, group).

        Columns: season, team, week, group, composite_z, score, grade
        (`week` is -1 for a season 'mean' aggregate; the actual final week for
        the default season-long 'final' view).
        """
        frame = self._select(season, week, team, aggregate)
        groups = groups or GROUPS
        if frame.empty:
            return pd.DataFrame(columns=["season", "team", "week", "group",
                                         "composite_z", "score", "grade"])
        rows = []
        base = frame[["season", "team", "week"]].reset_index(drop=True)
        for g in groups:
            z = self._composite_z(frame.reset_index(drop=True), g)
            score = score_from_z(z, self.base, self.spread)
            part = base.copy()
            part["group"] = g
            part["composite_z"] = z
            part["score"] = np.round(score, 1)
            part["grade"] = [letter_grade(s) for s in score]
            rows.append(part)
        out = pd.concat(rows, ignore_index=True)
        return out.sort_values(["season", "team", "group"]).reset_index(drop=True)

    def grade_wide(self, season=None, week=None, team=None, aggregate=None, value="score"):
        """Team x group matrix of `value` ('score' or 'grade')."""
        long = self.grade(season, week, team, aggregate)
        if long.empty:
            return long
        wide = long.pivot_table(index=["season", "team"], columns="group",
                                values=value, aggfunc="first")
        return wide.reindex(columns=GROUPS)

    def grade_all(self, scope="season", aggregate="final", out_path=None):
        """Grade EVERY team across ALL seasons in one call.

        scope="season" -> one row per (season, team, group), season-long
                          (aggregate 'final' = final-week cumulative, or 'mean').
        scope="weekly"  -> one row per (season, team, week, group), every week.

        Returns the itemized long DataFrame; also writes it to `out_path` if given.
        """
        if scope == "season":
            frame = self._select(season=None, week=None, team=None, aggregate=aggregate)
        elif scope == "weekly":
            frame = self.df.copy()
        else:
            raise ValueError("scope must be 'season' or 'weekly'")

        frame = frame.reset_index(drop=True)
        base = frame[["season", "team", "week"]]
        rows = []
        for g in GROUPS:
            z = self._composite_z(frame, g)
            score = score_from_z(z, self.base, self.spread)
            part = base.copy()
            part["group"] = g
            part["composite_z"] = z
            part["score"] = np.round(score, 1)
            part["grade"] = [letter_grade(s) for s in score]
            rows.append(part)
        sort_keys = ["season", "team", "week", "group"]
        out = pd.concat(rows, ignore_index=True).sort_values(sort_keys).reset_index(drop=True)
        if out_path:
            out.to_csv(out_path, index=False)
        return out

    # ---- visualization ---------------------------------------------------
    def plot_radar(self, season, team, week=None, aggregate=None, ax=None):
        """Radar chart of one team's six position-group scores (0-100)."""
        import matplotlib.pyplot as plt

        long = self.grade(season=season, week=week, team=team, aggregate=aggregate)
        if long.empty:
            raise ValueError(f"no data for {team} in {season}"
                             f"{f' week {week}' if week else ''}")
        long = long.set_index("group").reindex(GROUPS)
        scores = long["score"].fillna(0).to_numpy()
        grades = long["grade"].tolist()

        angles = np.linspace(0, 2 * np.pi, len(GROUPS), endpoint=False)
        vals = np.concatenate([scores, scores[:1]])
        ang = np.concatenate([angles, angles[:1]])

        if ax is None:
            _, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))
        ax.plot(ang, vals, color="#2b6cb0", linewidth=2)
        ax.fill(ang, vals, color="#2b6cb0", alpha=0.25)
        ax.set_xticks(angles)
        ax.set_xticklabels([f"{g}\n{gr}" for g, gr in zip(GROUPS, grades)], fontsize=10)
        ax.set_ylim(0, 100)
        ax.set_yticks([20, 40, 60, 80, 100])
        ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=8, color="gray")
        wk = "season" if week is None else f"week {week}"
        ax.set_title(f"{team} — {season} ({wk}) position-group grades",
                     fontsize=13, pad=24)
        return ax

    def plot_compare(self, teams, season, week=None, aggregate=None, ax=None):
        """Grouped bar chart comparing several teams across the six groups."""
        import matplotlib.pyplot as plt

        wide = self.grade_wide(season=season, week=week, team=teams, aggregate=aggregate)
        if wide.empty:
            raise ValueError("no data for the requested teams/season")
        wide = wide.reset_index().set_index("team").reindex(
            [t for t in teams if t in wide.reset_index()["team"].values])

        x = np.arange(len(GROUPS))
        nteams = len(wide)
        w = 0.8 / max(nteams, 1)
        if ax is None:
            _, ax = plt.subplots(figsize=(12, 6))
        for i, (tm, row) in enumerate(wide.iterrows()):
            ax.bar(x + i * w - 0.4 + w / 2, row[GROUPS].to_numpy(dtype=float),
                   width=w, label=str(tm))
        ax.axhline(self.base, color="gray", linestyle="--", linewidth=1, alpha=0.7)  # avg (C)
        ax.set_xticks(x)
        ax.set_xticklabels(GROUPS)
        ax.set_ylim(0, 100)
        ax.set_ylabel("Composite score (0-100)")
        wk = "season" if week is None else f"week {week}"
        ax.set_title(f"Position-group grades — {season} ({wk})")
        ax.legend(loc="upper right", fontsize=9)
        return ax


# ---------------------------------------------------------- demo / self-test
if __name__ == "__main__":
    path = os.environ.get(
        "CFDB_ZSCORES",
        "/Volumes/1TB external/CFDB Stats/team_zscores_all_seasons.csv")
    ev = PositionGroupEvaluator(path)
    latest = int(ev.df["season"].max())
    print(f"Loaded {len(ev.df):,} team-week rows, seasons "
          f"{int(ev.df['season'].min())}-{latest}.\n")
    print(f"Season-long grades, {latest}, sample:")
    print(ev.grade_wide(season=latest, value="grade").head(10).to_string())
