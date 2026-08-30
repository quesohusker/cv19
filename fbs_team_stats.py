"""
FBS team stats: cumulative-through-week rankings and z-scores.
=============================================================

For every FBS team, for every week of every season, this computes
cumulative-through-that-week team statistics (an offense "for" version and a
defense "against"/allowed version of each), then converts them into:

  1. a 1..n rank per stat per week   (rank 1 = worst, rank n = best)
  2. a z-score per stat per week     (higher z = better)

normalized so that a HIGHER rank number and a HIGHER z-score ALWAYS mean better
performance -- including defensive "against" stats, where allowing fewer
yards/points produces a higher (better) rank/z, not a lower one.

Outputs (see OUTPUT below):
  <BASE_DIR>/<year>/team_ranks.csv         one row per team per week, rank per stat
  <BASE_DIR>/<year>/team_zscores.csv       one row per team per week, z per stat
  <BASE_DIR>/<year>/team_stats.csv         (optional) the underlying per-game stat
                                           values that feed the ranking -- handy
                                           for sanity-checking against CFBstats
  <BASE_DIR>/team_ranks_all_seasons.csv    all seasons stacked
  <BASE_DIR>/team_zscores_all_seasons.csv  all seasons stacked
  <BASE_DIR>/team_stats_all_seasons.csv    MASTER stats file: the per-game stat
                                           values across all seasons (the numbers
                                           you'd compare to CFBstats)

The master/all-seasons files are built INCREMENTALLY: run_all_seasons() only
processes seasons not already in them, so once 2005-2025 are built, dropping a
2026 folder in and re-running processes just 2026 and appends it. Each season's
rows are independent (ranks/z are computed only within a season-week), so
appending -- or replacing a reprocessed season -- is exact. Use rebuild=True to
rebuild everything from scratch.

HOW TO RUN
----------
In Jupyter (on the Mac where the external drive is mounted):

    %run fbs_team_stats.py          # runs main() over every season it finds
    # or, cell by cell:
    from fbs_team_stats import *
    inspect_season(2025)            # print diagnostics for one season first
    run_all_seasons()              # build 2005-2025 + master files (incremental)
    # later, when 2026 lands, the SAME call appends only 2026:
    run_all_seasons()

Or from a shell:  python fbs_team_stats.py

The seasons are auto-discovered from BASE_DIR (any numeric sub-folder that
contains a combined.csv), so when 2026 lands, re-running "just works".

WHAT WAS VERIFIED AGAINST REAL DATA
-----------------------------------
The playType / driveResult / column mappings below were built by inspecting a
real 2025 combined.csv (not from CFBD's documented schema). Notable findings
that this code relies on -- and that the diagnostics re-check every season:
  * drive elapsed time is stored split as `drive_elapsed.minutes` / `.seconds`.
  * points come from game-level `game_homePoints` / `game_awayPoints`.
  * on punt/kickoff RETURN plays, offense = the kicking/punting team and
    defense = the RETURNING team, so return yardage accrues to `defense`.
  * kickoff-return `yardsGained` is inconsistent in the source (sometimes the
    kick distance, sometimes the return distance) -> KO return YARDS are noisy;
    return COUNTS are reliable. This is flagged, not hidden.
  * extra-point (PAT kick) plays do NOT appear as their own playType in 2025,
    so XP made/attempted is not derivable -- the code warns and skips rather
    than silently emitting zeros.

Approximations are labelled `_approx` in the column name (see below).
Deliberately OUT of scope (not reliably derivable): penalties / penalty yards,
first downs.
"""

# %% ----------------------------------------------------------------- imports
from __future__ import annotations

import os
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

# %% ------------------------------------------------------------------ config

# Root that holds one sub-folder per season (e.g. .../CFDB Stats/2025/combined.csv).
# Override with the env var CFDB_BASE_DIR, or just edit this string.
BASE_DIR = os.environ.get("CFDB_BASE_DIR", "/Volumes/1TB external/CFDB Stats")

# Write the underlying per-game cumulative stat values too (not just ranks/z).
# These are the numbers you'd eyeball against CFBstats.com. Cheap; leave on.
WRITE_STATS = True

# Ranking method for ties. "min" = competition ranking (tied teams share the
# lower rank number). rank 1 = worst, rank n = best; n = # FBS teams ranked that
# week. z-scores use population/sample std (ddof=1); a week with <2 teams -> NaN.
RANK_METHOD = "min"

# Only regular-season games are used (postseason week numbers restart at 1 and
# would collide with regular-season weeks).
REGULAR_SEASON_VALUE = "regular"

# Red-zone approximation: a drive "scored" if its driveResult is one of these.
# Verified against real values: 'TD','FG' are the OFFENSE scoring. The '<x> TD'
# variants (e.g. 'INT TD', 'PUNT RETURN TD') are the OPPONENT scoring on a
# turnover/return and are deliberately excluded.
DRIVE_SCORING_RESULTS = {"TD", "FG"}

# ----- playType classification (verified against real 2025 combined.csv) -----
# Every stat is derived from these sets. Anything in the data that isn't
# classified here AND isn't in PLAYTYPES_IGNORED triggers a per-season warning,
# so newly-renamed strings in other seasons get surfaced instead of dropped.
RUSH_TYPES            = {"Rush", "Rushing Touchdown"}
RUSH_TD_TYPES         = {"Rushing Touchdown"}
PASS_COMPLETION_TYPES = {"Pass Reception", "Passing Touchdown", "Pass Completion"}
PASS_TD_TYPES         = {"Passing Touchdown"}
PASS_INCOMPLETE_TYPES = {"Pass Incompletion"}
# An interception is a (failed) pass attempt; yardsGained on these is the return
# yardage and belongs to the defense, so it is NOT counted toward passing yards.
# ("Pass Interception" is the older-season (2006-2013) spelling of the same event.)
INTERCEPTION_TYPES    = {"Pass Interception Return", "Interception Return Touchdown",
                         "Interception", "Pass Interception"}
SACK_TYPES            = {"Sack"}
# Fumbles LOST by the offense (a turnover). 'Fumble Recovery (Own)' is not a
# turnover; bare 'Fumble' is ambiguous and is left out to avoid over-counting.
FUMBLE_LOST_TYPES     = {"Fumble Recovery (Opponent)", "Fumble Return Touchdown"}
FG_MADE_TYPES         = {"Field Goal Good"}
FG_ATT_TYPES          = {"Field Goal Good", "Field Goal Missed", "Blocked Field Goal",
                         "Blocked Field Goal Touchdown", "Missed Field Goal Return",
                         "Missed Field Goal Return Touchdown"}  # older-season spelling
# Extra-point kicks (absent from 2025 data -> the code will warn and skip if the
# season has no matching rows). Listed for seasons that do carry them.
XP_MADE_TYPES         = {"Extra Point Good"}
XP_ATT_TYPES          = {"Extra Point Good", "Extra Point Missed",
                         "Blocked PAT", "Blocked Extra Point", "Extra Point Blocked"}
PUNT_RETURN_TYPES     = {"Punt Return", "Punt Return Touchdown"}
KICKOFF_RETURN_TYPES  = {"Kickoff Return (Offense)", "Kickoff Return Touchdown"}
BLOCKED_KICK_TYPES    = {"Blocked Field Goal", "Blocked Field Goal Touchdown",
                         "Blocked Punt", "Blocked Punt Touchdown"}

# playTypes we knowingly do nothing with (so they don't trigger the "unknown
# playType" warning). Kickoff/Punt themselves are here because we take return
# yardage from the dedicated *Return* playTypes, not the bare kick.
PLAYTYPES_IGNORED = {
    "Timeout", "Penalty", "End Period", "End of Game", "End of Half",
    "End of Regulation", "End of 4th Quarter", "Uncategorized", "placeholder",
    "Safety", "Defensive 2pt Conversion", "Kickoff", "Punt",
    "Two Point Rush", "Two Point Pass", "2pt Conversion",
    # Fumbles that are NOT turnovers (own recovery) or ambiguous (bare 'Fumble');
    # only FUMBLE_LOST_TYPES count as lost/forced. Listed here so they don't warn.
    "Fumble", "Fumble Recovery (Own)",
} | FG_MADE_TYPES | FG_ATT_TYPES | XP_MADE_TYPES | XP_ATT_TYPES

# Every playType we understand (used only for the unknown-playType warning).
PLAYTYPES_KNOWN = (
    RUSH_TYPES | PASS_COMPLETION_TYPES | PASS_INCOMPLETE_TYPES | INTERCEPTION_TYPES
    | SACK_TYPES | FUMBLE_LOST_TYPES | PUNT_RETURN_TYPES | KICKOFF_RETURN_TYPES
    | BLOCKED_KICK_TYPES | PLAYTYPES_IGNORED
)

# %% -------------------------------------------------- column-name resolution
# Logical field -> ordered candidate column names. The real 2025 file uses the
# first candidate in each list; alternates guard against older-season drift.
COLUMN_CANDIDATES = {
    "game_id":      ["gameId", "game_id"],
    "drive_id":     ["driveId", "drive_id"],
    "season":       ["game_season", "season", "drive_season"],
    "week":         ["game_week", "week"],
    "season_type":  ["game_seasonType", "seasonType", "game_season_type"],
    "offense":      ["offense"],
    "defense":      ["defense"],
    "play_type":    ["playType", "play_type"],
    "yards_gained": ["yardsGained", "yards_gained"],
    "down":         ["down"],
    "distance":     ["distance"],
    "yards_to_goal":["yardsToGoal", "yards_to_goal"],
    "home_team":    ["game_homeTeam", "game_home_team", "home"],
    "away_team":    ["game_awayTeam", "game_away_team", "away"],
    "home_points":  ["game_homePoints", "game_home_points"],
    "away_points":  ["game_awayPoints", "game_away_points"],
    "home_class":   ["game_homeClassification", "game_home_classification"],
    "away_class":   ["game_awayClassification", "game_away_classification"],
    "drive_offense":["drive_offense"],
    "drive_defense":["drive_defense"],
    "drive_result": ["drive_driveResult", "drive_result", "driveResult"],
    "elapsed_min":  ["drive_elapsed.minutes", "drive_elapsed_minutes"],
    "elapsed_sec":  ["drive_elapsed.seconds", "drive_elapsed_seconds"],
    "elapsed_flat": ["drive_elapsed", "drive_elapsedSeconds"],  # fallback forms
}


def _resolve(available, candidates):
    """Return the first candidate present in `available`, else None."""
    for c in candidates:
        if c in available:
            return c
    return None


def resolve_columns(all_cols, season):
    """Map logical field -> actual column name, warning about anything missing."""
    avail = set(all_cols)
    cols = {}
    for key, cands in COLUMN_CANDIDATES.items():
        cols[key] = _resolve(avail, cands)
    # Elapsed time can be split (min/sec) OR a single flat column.
    has_split = cols["elapsed_min"] and cols["elapsed_sec"]
    if not has_split and not cols["elapsed_flat"]:
        warnings.warn(f"[{season}] no drive-elapsed column found -> "
                      f"time-of-possession will be NaN")
    # Hard-required fields; without them we cannot proceed.
    required = ["game_id", "season", "week", "season_type", "offense", "defense",
                "play_type", "yards_gained", "down", "distance", "yards_to_goal",
                "home_team", "away_team", "home_points", "away_points",
                "home_class", "away_class"]
    missing = [k for k in required if cols[k] is None]
    if missing:
        raise KeyError(f"[{season}] combined.csv missing required columns: {missing}")
    # Soft-optional fields; warn but continue (stat just becomes NaN).
    for k in ["drive_id", "drive_offense", "drive_defense", "drive_result"]:
        if cols[k] is None:
            warnings.warn(f"[{season}] optional column '{k}' not found -> "
                          f"dependent stats (TOP / red-zone) will be NaN")
    return cols


# %% ---------------------------------------------------------- the stat table
# Each ranked stat: the output column name, the "sign" for normalization
# (+1 => higher raw value is better, -1 => lower raw value is better), and how
# it is finalized ("pergame" = cumulative total / games played; "max" = running
# max; "rate" = cumulative numerator / cumulative denominator).
#
# Volume-only stats (rush/pass attempts, FG/XP made&attempted, return counts)
# are intentionally NOT ranked -- they carry no inherent "better" direction.
# They're still computed and land in team_stats.csv as raw counts.
@dataclass(frozen=True)
class Stat:
    name: str          # output column
    sign: int          # +1 higher-better, -1 lower-better
    kind: str          # "pergame" | "max" | "rate"
    num: str = ""      # cumulative component column (numerator, or the total)
    den: str = ""      # cumulative component column (denominator, "rate" only)


# fmt: off
RANKED_STATS = [
    # ---- record ----
    Stat("win_pct",               +1, "rate",    num="win", den="games_played"),
    # ---- scoring ----
    Stat("points_for",            +1, "pergame", num="points_for"),
    Stat("points_against",        -1, "pergame", num="points_against"),   # allow fewer = better
    # ---- rushing ----
    Stat("rush_yds_for",          +1, "pergame", num="rush_yds_for"),
    Stat("rush_yds_against",      -1, "pergame", num="rush_yds_against"),
    Stat("rush_td_for",           +1, "pergame", num="rush_td_for"),
    Stat("rush_td_against",       -1, "pergame", num="rush_td_against"),
    Stat("longest_rush_for",      +1, "max",     num="longest_rush_for"),
    Stat("longest_rush_against",  -1, "max",     num="longest_rush_against"),
    # ---- passing ----
    Stat("pass_yds_for",          +1, "pergame", num="pass_yds_for"),
    Stat("pass_yds_against",      -1, "pergame", num="pass_yds_against"),
    Stat("pass_td_for",           +1, "pergame", num="pass_td_for"),
    Stat("pass_td_against",       -1, "pergame", num="pass_td_against"),
    Stat("longest_pass_for",      +1, "max",     num="longest_pass_for"),
    Stat("longest_pass_against",  -1, "max",     num="longest_pass_against"),
    Stat("comp_pct_for",          +1, "rate",    num="comp_for",     den="pass_att_for"),
    Stat("comp_pct_against",      -1, "rate",    num="comp_against",  den="pass_att_against"),
    # ---- turnovers (flip: committing = bad, forcing = good) ----
    Stat("int_thrown",            -1, "pergame", num="int_thrown"),       # offense commits -> bad
    Stat("int_made",              +1, "pergame", num="int_made"),         # defense forces -> good
    Stat("fumbles_lost",          -1, "pergame", num="fumbles_lost"),
    Stat("fumbles_recovered",     +1, "pergame", num="fumbles_recovered"),
    # ---- sacks (flip: allowed = bad, made = good) ----
    Stat("sacks_allowed",         -1, "pergame", num="sacks_allowed"),
    Stat("sacks_made",            +1, "pergame", num="sacks_made"),
    Stat("sack_yds_allowed",      -1, "pergame", num="sack_yds_allowed"),
    Stat("sack_yds_made",         +1, "pergame", num="sack_yds_made"),
    # ---- special teams ----
    Stat("punt_ret_yds_for",      +1, "pergame", num="punt_ret_yds_for"),
    Stat("punt_ret_yds_against",  -1, "pergame", num="punt_ret_yds_against"),
    # NOTE: kickoff-return YARDS are noisy in the source (yardsGained mixes kick
    # and return distance). Ranked, but treat with caution; counts are reliable.
    Stat("ko_ret_yds_for",        +1, "pergame", num="ko_ret_yds_for"),
    Stat("ko_ret_yds_against",    -1, "pergame", num="ko_ret_yds_against"),
    Stat("blocked_kicks_made",    +1, "pergame", num="blocked_kicks_made"),
    Stat("kicks_had_blocked",     -1, "pergame", num="kicks_had_blocked"),
    # ---- possession ----
    Stat("top_for",               +1, "pergame", num="top_for"),          # seconds/game
    Stat("top_against",           -1, "pergame", num="top_against"),
    # ---- approximations (see module docstring) ----
    Stat("third_down_pct_for_approx",     +1, "rate", num="third_conv_for",     den="third_att_for"),
    Stat("third_down_pct_against_approx", -1, "rate", num="third_conv_against",  den="third_att_against"),
    Stat("fourth_down_pct_for_approx",    +1, "rate", num="fourth_conv_for",    den="fourth_att_for"),
    Stat("fourth_down_pct_against_approx",-1, "rate", num="fourth_conv_against", den="fourth_att_against"),
    Stat("red_zone_pct_for_approx",       +1, "rate", num="rz_scored_for",      den="rz_trips_for"),
    Stat("red_zone_pct_against_approx",   -1, "rate", num="rz_scored_against",   den="rz_trips_against"),
]
# fmt: on

# Volume-only components kept in team_stats.csv (as per-game averages) but never
# ranked -- no inherent good/bad direction.
VOLUME_PERGAME = [
    "rush_att_for", "rush_att_against", "pass_att_for", "pass_att_against",
    "comp_for", "comp_against", "punt_ret_n_for", "punt_ret_n_against",
    "ko_ret_n_for", "ko_ret_n_against", "fg_made_for", "fg_att_for",
    "xp_made_for", "xp_att_for",
]


# %% -------------------------------------------------- per-play value builder
def _build_play_values(df, cols):
    """One row per play -> the numeric contribution of that play to each metric.

    Returns a DataFrame indexed like `df` with the grouping keys (game_id, week,
    offense, defense) plus one column per per-play metric value. Every metric is
    later grouped by BOTH `offense` and `defense`, which is what produces the
    "for" and the "against"/allowed sides from a single pass.
    """
    pt = df[cols["play_type"]].astype("string")
    yg = pd.to_numeric(df[cols["yards_gained"]], errors="coerce").astype("float64")
    down = pd.to_numeric(df[cols["down"]], errors="coerce")
    dist = pd.to_numeric(df[cols["distance"]], errors="coerce")

    is_rush    = pt.isin(RUSH_TYPES)
    is_rush_td = pt.isin(RUSH_TD_TYPES)
    is_comp    = pt.isin(PASS_COMPLETION_TYPES)
    is_incomp  = pt.isin(PASS_INCOMPLETE_TYPES)
    is_int     = pt.isin(INTERCEPTION_TYPES)
    is_pass_td = pt.isin(PASS_TD_TYPES)
    is_pass_att = is_comp | is_incomp | is_int          # sacks are NOT attempts
    is_sack    = pt.isin(SACK_TYPES)
    is_fumlost = pt.isin(FUMBLE_LOST_TYPES)
    is_puntret = pt.isin(PUNT_RETURN_TYPES)
    is_koret   = pt.isin(KICKOFF_RETURN_TYPES)
    is_blocked = pt.isin(BLOCKED_KICK_TYPES)
    is_fg_made = pt.isin(FG_MADE_TYPES)
    is_fg_att  = pt.isin(FG_ATT_TYPES)
    is_xp_made = pt.isin(XP_MADE_TYPES)
    is_xp_att  = pt.isin(XP_ATT_TYPES)
    # Scrimmage plays for the down-conversion approximation: rush + pass + sack.
    is_scrim   = is_rush | is_pass_att | is_sack

    # 3rd/4th down conversion is APPROXIMATE: CFBD play-by-play has no explicit
    # "converted" flag, so we call it converted when yardsGained >= distance on
    # that down. This misses conversions via defensive penalty (automatic first
    # down) and can misfire on a drive's final play. Hence the _approx suffix.
    converted = yg >= dist

    z = 0.0
    v = pd.DataFrame({
        cols["game_id"]: df[cols["game_id"]].to_numpy(),
        cols["week"]:    df[cols["week"]].to_numpy(),
        cols["offense"]: df[cols["offense"]].to_numpy(),
        cols["defense"]: df[cols["defense"]].to_numpy(),
    }, index=df.index)

    # --- summed metrics (grouped by offense -> "for"/"committed";
    #                      grouped by defense -> "against"/"forced") ---
    v["rush_att"]   = is_rush.astype(float)
    v["rush_yds"]   = np.where(is_rush, yg, z)
    v["rush_td"]    = is_rush_td.astype(float)
    v["pass_att"]   = is_pass_att.astype(float)
    v["comp"]       = is_comp.astype(float)
    v["pass_yds"]   = np.where(is_comp, yg, z)        # completions only
    v["pass_td"]    = is_pass_td.astype(float)
    v["intc"]       = is_int.astype(float)
    v["sack"]       = is_sack.astype(float)
    v["sackyds"]    = np.where(is_sack, yg.abs(), z)
    v["fum"]        = is_fumlost.astype(float)
    v["puntret_yds"] = np.where(is_puntret, yg, z)
    v["koret_yds"]   = np.where(is_koret, yg, z)
    v["puntret_n"]   = is_puntret.astype(float)
    v["koret_n"]     = is_koret.astype(float)
    v["blocked"]    = is_blocked.astype(float)
    v["fg_made"]    = is_fg_made.astype(float)
    v["fg_att"]     = is_fg_att.astype(float)
    v["xp_made"]    = is_xp_made.astype(float)
    v["xp_att"]     = is_xp_att.astype(float)
    v["third_att"]  = (is_scrim & (down == 3)).astype(float)
    v["third_conv"] = (is_scrim & (down == 3) & converted).astype(float)
    v["fourth_att"] = (is_scrim & (down == 4)).astype(float)
    v["fourth_conv"] = (is_scrim & (down == 4) & converted).astype(float)

    # --- max metrics (longest play; running max, not a sum) ---
    v["longrush"] = np.where(is_rush, yg, np.nan)
    v["longpass"] = np.where(is_comp, yg, np.nan)

    return v


# The metric columns produced above and how each aggregates within a game.
_SUM_METRICS = ["rush_att", "rush_yds", "rush_td", "pass_att", "comp", "pass_yds",
                "pass_td", "intc", "sack", "sackyds", "fum", "puntret_yds",
                "koret_yds", "puntret_n", "koret_n", "blocked", "fg_made",
                "fg_att", "xp_made", "xp_att", "third_att", "third_conv",
                "fourth_att", "fourth_conv"]
_MAX_METRICS = ["longrush", "longpass"]

# How a per-play metric maps onto (offense-grouped name, defense-grouped name).
# offense-grouped = what the OFFENSE team did; defense-grouped = the DEFENSE team.
# For most stats offense->"for", defense->"against". For events credited to the
# defender (sacks, INTs, fumble recoveries, returns, blocks) the mapping flips.
_OFF_RENAME = {   # column when grouped by the offense team
    "rush_att": "rush_att_for", "rush_yds": "rush_yds_for", "rush_td": "rush_td_for",
    "pass_att": "pass_att_for", "comp": "comp_for", "pass_yds": "pass_yds_for",
    "pass_td": "pass_td_for", "intc": "int_thrown", "sack": "sacks_allowed",
    "sackyds": "sack_yds_allowed", "fum": "fumbles_lost",
    "puntret_yds": "punt_ret_yds_against",  # offense = punting team -> yards allowed
    "koret_yds": "ko_ret_yds_against",
    "puntret_n": "punt_ret_n_against", "koret_n": "ko_ret_n_against",
    "blocked": "kicks_had_blocked",         # offense = kicking team -> got blocked
    "fg_made": "fg_made_for", "fg_att": "fg_att_for",
    "xp_made": "xp_made_for", "xp_att": "xp_att_for",
    "third_att": "third_att_for", "third_conv": "third_conv_for",
    "fourth_att": "fourth_att_for", "fourth_conv": "fourth_conv_for",
    "longrush": "longest_rush_for", "longpass": "longest_pass_for",
}
_DEF_RENAME = {   # column when grouped by the defense team
    "rush_att": "rush_att_against", "rush_yds": "rush_yds_against", "rush_td": "rush_td_against",
    "pass_att": "pass_att_against", "comp": "comp_against", "pass_yds": "pass_yds_against",
    "pass_td": "pass_td_against", "intc": "int_made", "sack": "sacks_made",
    "sackyds": "sack_yds_made", "fum": "fumbles_recovered",
    "puntret_yds": "punt_ret_yds_for",      # defense = returning team -> its return yards
    "koret_yds": "ko_ret_yds_for",
    "puntret_n": "punt_ret_n_for", "koret_n": "ko_ret_n_for",
    "blocked": "blocked_kicks_made",        # defense = blocker
    "fg_made": "fg_made_against", "fg_att": "fg_att_against",
    "xp_made": "xp_made_against", "xp_att": "xp_att_against",
    "third_att": "third_att_against", "third_conv": "third_conv_against",
    "fourth_att": "fourth_att_against", "fourth_conv": "fourth_conv_against",
    "longrush": "longest_rush_against", "longpass": "longest_pass_against",
}


# %% ------------------------------------------------ per-game team aggregation
def _aggregate_per_game(df, cols):
    """Collapse plays to one row per (game_id, week, team) with every component.

    Produces both the offense ("for") and defense ("against") sides in a single
    pass by grouping the same per-play values by `offense` and by `defense`.
    Also adds game-level points, drive-level time-of-possession, and the
    drive-level red-zone components.
    """
    gid, wk, off, dfn = cols["game_id"], cols["week"], cols["offense"], cols["defense"]
    v = _build_play_values(df, cols)

    # Group by offense team and by defense team.
    off_sum = v.groupby([gid, wk, off], observed=True)[_SUM_METRICS].sum()
    off_max = v.groupby([gid, wk, off], observed=True)[_MAX_METRICS].max()
    off = off_sum.join(off_max).rename(columns={**_OFF_RENAME}).reset_index()
    off = off.rename(columns={cols["offense"]: "team"})

    def_sum = v.groupby([gid, wk, dfn], observed=True)[_SUM_METRICS].sum()
    def_max = v.groupby([gid, wk, dfn], observed=True)[_MAX_METRICS].max()
    deff = def_sum.join(def_max).rename(columns={**_DEF_RENAME}).reset_index()
    deff = deff.rename(columns={cols["defense"]: "team"})

    # Keep only each frame's own semantic columns (offense side keeps "for"/
    # committed names, defense side keeps "against"/forced names).
    keys = [gid, wk, "team"]
    off = off[keys + list(_OFF_RENAME.values())]
    deff = deff[keys + list(_DEF_RENAME.values())]

    per_game = off.merge(deff, on=keys, how="outer")

    # ----- points (game level, NOT derived from scoring plays) -----
    per_game = per_game.merge(_points_per_game(df, cols), on=[gid, "team"], how="left")

    # ----- time of possession (drive level, deduped by drive id) -----
    top = _top_per_game(df, cols)
    if top is not None:
        per_game = per_game.merge(top, on=[gid, "team"], how="left")
    else:
        per_game["top_for"] = np.nan
        per_game["top_against"] = np.nan

    # ----- red zone (drive level) -----
    rz = _redzone_per_game(df, cols)
    if rz is not None:
        per_game = per_game.merge(rz, on=[gid, "team"], how="left")
    else:
        for c in ["rz_trips_for", "rz_scored_for", "rz_trips_against", "rz_scored_against"]:
            per_game[c] = np.nan

    per_game["games_played"] = 1
    per_game = per_game.rename(columns={gid: "game_id", wk: "week"})
    # Sum/count components: NaN from the outer merge means "no such play" -> 0.
    # Max components keep NaN (no long play) but fill 0 so the later cummax is
    # well-defined (longest is non-negative). TOP/RZ NaN handled downstream.
    fill0 = [c for c in per_game.columns
             if c not in ("game_id", "week", "team", "top_for", "top_against",
                          "rz_trips_for", "rz_scored_for",
                          "rz_trips_against", "rz_scored_against")]
    per_game[fill0] = per_game[fill0].fillna(0.0)
    return per_game


def _points_per_game(df, cols):
    """One row per (game_id, team): points for/against and win/loss/tie flags."""
    g = df.drop_duplicates(cols["game_id"])
    hp = pd.to_numeric(g[cols["home_points"]], errors="coerce").to_numpy()
    ap = pd.to_numeric(g[cols["away_points"]], errors="coerce").to_numpy()
    home = pd.DataFrame({
        cols["game_id"]: g[cols["game_id"]].to_numpy(),
        "team": g[cols["home_team"]].to_numpy(),
        "points_for": hp, "points_against": ap,
        "win": (hp > ap).astype(float), "loss": (hp < ap).astype(float),
        "tie": (hp == ap).astype(float),
    })
    away = pd.DataFrame({
        cols["game_id"]: g[cols["game_id"]].to_numpy(),
        "team": g[cols["away_team"]].to_numpy(),
        "points_for": ap, "points_against": hp,
        "win": (ap > hp).astype(float), "loss": (ap < hp).astype(float),
        "tie": (ap == hp).astype(float),
    })
    return pd.concat([home, away], ignore_index=True)


def _drive_elapsed_seconds(dd, cols):
    """Vector of elapsed seconds per drive row, from split or flat columns."""
    if cols["elapsed_min"] and cols["elapsed_sec"]:
        m = pd.to_numeric(dd[cols["elapsed_min"]], errors="coerce")
        s = pd.to_numeric(dd[cols["elapsed_sec"]], errors="coerce")
        return m * 60 + s
    if cols["elapsed_flat"]:
        col = dd[cols["elapsed_flat"]]
        if col.dtype == object or str(col.dtype).startswith("string"):
            # Try "MM:SS" strings.
            parts = col.astype("string").str.split(":", expand=True)
            if parts.shape[1] >= 2:
                m = pd.to_numeric(parts[0], errors="coerce")
                s = pd.to_numeric(parts[1], errors="coerce")
                return m * 60 + s
        return pd.to_numeric(col, errors="coerce")   # assume already seconds
    return None


def _top_per_game(df, cols):
    """Time of possession per (game_id, team), deduped by drive id.

    Do NOT sum elapsed at the play level -- that double-counts every drive by
    its play count. Dedup to one row per drive first.
    """
    if not (cols["drive_id"] and cols["drive_offense"] and cols["drive_defense"]):
        return None
    dd = df.drop_duplicates(cols["drive_id"]).copy()
    sec = _drive_elapsed_seconds(dd, cols)
    if sec is None:
        return None
    dd = dd.assign(_elapsed=sec)
    gid = cols["game_id"]
    for_ = (dd.groupby([gid, cols["drive_offense"]], observed=True)["_elapsed"].sum()
            .rename("top_for").reset_index()
            .rename(columns={cols["drive_offense"]: "team"}))
    ag = (dd.groupby([gid, cols["drive_defense"]], observed=True)["_elapsed"].sum()
          .rename("top_against").reset_index()
          .rename(columns={cols["drive_defense"]: "team"}))
    return for_.merge(ag, on=[gid, "team"], how="outer")


def _redzone_per_game(df, cols):
    """Red-zone trips and scores per (game_id, team) -- APPROXIMATE.

    A drive "reached the red zone" if any of its plays had yardsToGoal <= 20; it
    "scored" if the drive's driveResult is in DRIVE_SCORING_RESULTS (TD/FG by the
    offense). Attributed to drive_offense ("for") and drive_defense ("against").
    """
    if not (cols["drive_id"] and cols["drive_offense"]
            and cols["drive_defense"] and cols["drive_result"]):
        return None
    did = cols["drive_id"]
    y2g = pd.to_numeric(df[cols["yards_to_goal"]], errors="coerce")
    reached = (df.assign(_y2g=y2g).groupby(did, observed=True)["_y2g"].min() <= 20)
    dd = df.drop_duplicates(did).set_index(did)
    scored = dd[cols["drive_result"]].astype("string").isin(DRIVE_SCORING_RESULTS)
    drv = pd.DataFrame({
        cols["game_id"]: dd[cols["game_id"]].to_numpy(),
        "off": dd[cols["drive_offense"]].to_numpy(),
        "def": dd[cols["drive_defense"]].to_numpy(),
        "reached": reached.reindex(dd.index).fillna(False).to_numpy(),
        "scored": scored.to_numpy(),
    })
    drv["rz_trip"] = drv["reached"].astype(float)
    drv["rz_score"] = (drv["reached"] & drv["scored"]).astype(float)
    gid = cols["game_id"]
    for_ = (drv.groupby([gid, "off"], observed=True)[["rz_trip", "rz_score"]].sum()
            .rename(columns={"rz_trip": "rz_trips_for", "rz_score": "rz_scored_for"})
            .reset_index().rename(columns={"off": "team"}))
    ag = (drv.groupby([gid, "def"], observed=True)[["rz_trip", "rz_score"]].sum()
          .rename(columns={"rz_trip": "rz_trips_against", "rz_score": "rz_scored_against"})
          .reset_index().rename(columns={"def": "team"}))
    return for_.merge(ag, on=[gid, "team"], how="outer")


# %% --------------------------------------------- cumulative-through-week grid
def _cumulative_by_week(per_game, season_weeks):
    """Per (team, week) cumulative components through that week (byes carried).

    Builds a full team x week grid so a team on a bye in week N still gets a
    row -- its cumulative equals the cumulative through the last week it played.
    Rows before a team's first game (cumulative games == 0) are dropped.
    """
    # Which components are running maxes vs sums.
    max_cols = ["longest_rush_for", "longest_rush_against",
                "longest_pass_for", "longest_pass_against"]
    id_cols = ["game_id", "week", "team", "games_played"]
    comp_cols = [c for c in per_game.columns if c not in id_cols]
    sum_cols = [c for c in comp_cols if c not in max_cols]

    # Collapse multiple games in the same week (rare) to one row per (team, week).
    agg = {c: "sum" for c in sum_cols}
    agg.update({c: "max" for c in max_cols})
    weekly = per_game.groupby(["team", "week"], observed=True).agg(agg)
    # games_played counts distinct games that week.
    gp = per_game.groupby(["team", "week"], observed=True)["game_id"].nunique()
    weekly["games_played"] = gp

    teams = per_game["team"].unique()
    full_idx = pd.MultiIndex.from_product([teams, season_weeks], names=["team", "week"])
    weekly = weekly.reindex(full_idx)

    # Missing (team, week) rows are byes: 0 for sums/counts, 0 for maxes (the
    # running max carries the higher prior value), NaN preserved for TOP/RZ sums
    # is not needed here since those are summed components (0 == "no trips").
    weekly[sum_cols + ["games_played"]] = weekly[sum_cols + ["games_played"]].fillna(0.0)
    weekly[max_cols] = weekly[max_cols].fillna(0.0)

    weekly = weekly.sort_index(level=["team", "week"])

    # This week's game outcome (non-cumulative): W / L / T / bye / split (>1 game).
    wr = _week_result(weekly)

    grp = weekly.groupby(level="team", observed=True)
    cum = grp[sum_cols + ["games_played"]].cumsum()
    cum[max_cols] = grp[max_cols].cummax()

    cum = cum[cum["games_played"] >= 1].reset_index()   # drop pre-first-game weeks
    cum["week_result"] = cum.set_index(["team", "week"]).index.map(wr)
    return cum


def _week_result(weekly):
    """Series mapping (team, week) -> that week's game result string.

    Uses the per-week (pre-cumsum) games count and win/loss/tie sums.
    "bye" when no game that week; "split" for the rare two-games-one-week mix.
    """
    g = weekly["games_played"]
    w = weekly.get("win", 0.0)
    l = weekly.get("loss", 0.0)
    t = weekly.get("tie", 0.0)
    res = np.where(g == 0, "bye",
          np.where((w > 0) & (l == 0) & (t == 0), "W",
          np.where((l > 0) & (w == 0) & (t == 0), "L",
          np.where((t > 0) & (w == 0) & (l == 0), "T", "split"))))
    return pd.Series(res, index=weekly.index)


def _finalize_stats(cum):
    """Turn cumulative components into the actual per-game / rate / max values."""
    out = cum[["team", "week", "games_played"]].copy()
    g = cum["games_played"].to_numpy()

    # Win/loss record: cumulative counts + this week's result. win_pct is ranked
    # (a "rate" stat) below; wins/losses/ties/week_result ride along as context.
    for src, dst in (("win", "wins"), ("loss", "losses"), ("tie", "ties")):
        if src in cum:
            out[dst] = cum[src].to_numpy().astype("int64")
    if "week_result" in cum:
        out["week_result"] = cum["week_result"].to_numpy()

    def safe_div(num, den):
        num = np.asarray(num, dtype="float64")
        den = np.asarray(den, dtype="float64")
        return np.divide(num, den, out=np.full_like(num, np.nan), where=den != 0)

    # Ranked stats.
    for st in RANKED_STATS:
        if st.kind == "pergame":
            if st.num not in cum:
                out[st.name] = np.nan
                continue
            out[st.name] = cum[st.num].to_numpy() / g          # counting -> per game
        elif st.kind == "max":
            out[st.name] = cum[st.num].to_numpy() if st.num in cum else np.nan
        elif st.kind == "rate":
            if st.num in cum and st.den in cum:
                out[st.name] = safe_div(cum[st.num], cum[st.den])
            else:
                out[st.name] = np.nan

    # Volume-only components, as per-game averages (not ranked).
    for c in VOLUME_PERGAME:
        if c in cum:
            out[c] = cum[c].to_numpy() / g
    return out


# %% ----------------------------------------------------- rank + z-score pass
def _rank_and_z(stats, fbs_teams):
    """Given finalized per-(team,week) stats, produce rank and z frames.

    Only FBS teams are ranked (rank 1..n among FBS teams that have a row that
    week). Direction is applied via each Stat.sign so that a higher rank number
    and a higher z-score always mean better.
    """
    df = stats[stats["team"].isin(fbs_teams)].copy()
    base = ["season", "team", "week", "games_played"] if "season" in df else ["team", "week", "games_played"]
    # Carry the win/loss record along as context so each file is self-contained.
    context = [c for c in ("wins", "losses", "ties", "week_result") if c in df]
    id_cols = base + context

    ranks = df[id_cols].copy()
    zs = df[id_cols].copy()
    grp_keys = ["season", "week"] if "season" in df else ["week"]

    gcols = [df[k] for k in grp_keys]
    for st in RANKED_STATS:
        if st.name not in df:
            continue
        good = st.sign * df[st.name]                 # higher = better after sign
        grp = good.groupby(gcols, observed=True)
        # rank: ascending on "good" so smallest good -> rank 1 (worst).
        rank = grp.rank(method=RANK_METHOD, ascending=True)
        # z: standardize "good" within the week (ddof=1; <2 teams -> NaN).
        mu = grp.transform("mean")
        sd = grp.transform("std")
        # When a stat has no spread that week -- every team identical, which is
        # what a season-wide data gap looks like (all 0 / all NaN) -- there is no
        # meaningful ordering, so emit NaN rather than a fake "everyone tied at 1".
        no_signal = sd.isna() | (sd == 0)
        ranks[st.name] = rank.where(~no_signal)
        zs[st.name] = ((good - mu) / sd).where(~no_signal)
    return ranks, zs


# %% ---------------------------------------------------------- season driver
def _discover_seasons(base_dir):
    """Numeric sub-folders of base_dir that contain a combined.csv, sorted."""
    out = []
    if not os.path.isdir(base_dir):
        return out
    for name in os.listdir(base_dir):
        p = os.path.join(base_dir, name, "combined.csv")
        if name.isdigit() and os.path.isfile(p):
            out.append(int(name))
    return sorted(out)


def _read_combined(path):
    """Read only the columns we need (keeps memory sane on 100MB+ files)."""
    header = pd.read_csv(path, nrows=0)
    want = set()
    for cands in COLUMN_CANDIDATES.values():
        for c in cands:
            if c in header.columns:
                want.add(c)
                break
    return pd.read_csv(path, usecols=sorted(want), low_memory=False)


def process_season(season, base_dir=BASE_DIR, verbose=True):
    """Build finalized per-game stats, ranks, and z-scores for one season."""
    path = os.path.join(base_dir, str(season), "combined.csv")
    if verbose:
        print(f"[{season}] reading {path}")
    df = _read_combined(path)
    cols = resolve_columns(df.columns, season)

    # Regular season only.
    df = df[df[cols["season_type"]].astype("string").str.lower() == REGULAR_SEASON_VALUE].copy()
    if df.empty:
        warnings.warn(f"[{season}] no regular-season rows found")
        return None

    _warn_unknown_playtypes(df, cols, season)
    _warn_empty_categories(df, cols, season)

    # FBS scope: a team is FBS if it appears as an FBS home team OR FBS away team.
    fbs = (set(df.loc[df[cols["home_class"]].astype("string").str.lower() == "fbs", cols["home_team"]])
           | set(df.loc[df[cols["away_class"]].astype("string").str.lower() == "fbs", cols["away_team"]]))
    if verbose:
        print(f"[{season}] {len(fbs)} FBS teams, {df[cols['game_id']].nunique()} regular games")

    season_weeks = sorted(pd.to_numeric(df[cols["week"]], errors="coerce").dropna().unique().tolist())
    per_game = _aggregate_per_game(df, cols)
    cum = _cumulative_by_week(per_game, season_weeks)
    stats = _finalize_stats(cum)
    stats.insert(0, "season", season)

    ranks, zs = _rank_and_z(stats, fbs)
    stats_fbs = stats[stats["team"].isin(fbs)].copy()

    # Write per-season files.
    out_dir = os.path.join(base_dir, str(season))
    ranks.sort_values(["week", "team"]).to_csv(os.path.join(out_dir, "team_ranks.csv"), index=False)
    zs.sort_values(["week", "team"]).to_csv(os.path.join(out_dir, "team_zscores.csv"), index=False)
    if WRITE_STATS:
        stats_fbs.sort_values(["week", "team"]).to_csv(os.path.join(out_dir, "team_stats.csv"), index=False)
    if verbose:
        print(f"[{season}] wrote team_ranks.csv / team_zscores.csv"
              f"{' / team_stats.csv' if WRITE_STATS else ''} "
              f"({len(ranks)} team-week rows)")
    return {"season": season, "fbs": fbs, "stats": stats_fbs, "ranks": ranks,
            "zscores": zs, "season_weeks": season_weeks}


def _warn_unknown_playtypes(df, cols, season):
    seen = set(df[cols["play_type"]].dropna().astype("string").unique())
    unknown = sorted(seen - PLAYTYPES_KNOWN)
    if unknown:
        warnings.warn(f"[{season}] unclassified playType values (ignored): {unknown}. "
                      f"Add them to the classification sets if they matter.")


def _warn_empty_categories(df, cols, season):
    """Warn when an expected stat category has zero matching rows this season."""
    pt = df[cols["play_type"]].astype("string")
    checks = {
        "rushing (Rush)": RUSH_TYPES,
        "passing (completions)": PASS_COMPLETION_TYPES,
        "sacks": SACK_TYPES,
        "interceptions": INTERCEPTION_TYPES,
        "fumbles lost": FUMBLE_LOST_TYPES,
        "field goals": FG_ATT_TYPES,
        "extra points": XP_ATT_TYPES,
        "punt returns": PUNT_RETURN_TYPES,
        "kickoff returns": KICKOFF_RETURN_TYPES,
        "blocked kicks": BLOCKED_KICK_TYPES,
    }
    for label, types in checks.items():
        if not pt.isin(types).any():
            warnings.warn(f"[{season}] no plays matched '{label}' -> that stat "
                          f"will be 0/NaN this season (data coverage gap).")


# %% ------------------------------------------------------------- top level
# The three master files stacked across all seasons. team_stats_all_seasons.csv
# is the "master stats file": the underlying per-game cumulative stat values
# (the numbers to compare against CFBstats), one row per team per week per season.
MASTER_FILES = {
    "ranks":   "team_ranks_all_seasons.csv",
    "zscores": "team_zscores_all_seasons.csv",
    "stats":   "team_stats_all_seasons.csv",
}


def _seasons_in_master(base_dir):
    """Seasons already present in the master ranks file (empty set if none)."""
    p = os.path.join(base_dir, MASTER_FILES["ranks"])
    if not os.path.isfile(p):
        return set()
    m = pd.read_csv(p, usecols=["season"])
    return set(int(s) for s in m["season"].unique())


def _upsert_master(base_dir, key, new_rows, replace_seasons):
    """Merge freshly computed season rows into a master file (add or replace).

    Each season's rows are independent of every other season (ranks/z-scores are
    computed only within a season-week), so appending a new season -- or
    replacing a reprocessed one -- is exact. Rows for `replace_seasons` are
    dropped from the existing master before the new rows are added, so a rerun
    of a season overwrites cleanly rather than duplicating.
    """
    path = os.path.join(base_dir, MASTER_FILES[key])
    frames = []
    if os.path.isfile(path):
        old = pd.read_csv(path)
        if "season" in old:
            old = old[~old["season"].isin(replace_seasons)]
        frames.append(old)
    if new_rows is not None and len(new_rows):
        frames.append(new_rows)
    if not frames:
        return
    out = pd.concat(frames, ignore_index=True)
    # Keep the master tidy and stable: sorted by season, then week, then team.
    sort_keys = [c for c in ("season", "week", "team") if c in out.columns]
    out = out.sort_values(sort_keys).reset_index(drop=True)
    out.to_csv(path, index=False)


def run_all_seasons(base_dir=BASE_DIR, seasons=None, rebuild=False, verbose=True):
    """Process seasons and (upsert-)write the per-season files and master files.

    Incremental by default: only seasons NOT already in the master files are
    processed, so once 2005-2025 are built, dropping a 2026 folder in and
    re-running processes just 2026 and appends it -- no reprocessing of prior
    seasons.  Pass rebuild=True to reprocess everything from scratch, or
    seasons=[...] to force specific seasons (they are reprocessed and their rows
    replaced in the masters).

    Returns the list of seasons processed this run.
    """
    discovered = _discover_seasons(base_dir)
    if not discovered:
        raise FileNotFoundError(f"No <year>/combined.csv folders found under {base_dir!r}. "
                                f"Set CFDB_BASE_DIR or pass base_dir=.")
    requested = discovered if seasons is None else [int(s) for s in seasons]

    already = set() if rebuild else _seasons_in_master(base_dir)
    if seasons is None and not rebuild:
        todo = [s for s in requested if s not in already]        # incremental append
    else:
        todo = list(requested)                                   # explicit / rebuild
    if rebuild:
        # Start the masters fresh so stale seasons don't linger.
        for fn in MASTER_FILES.values():
            p = os.path.join(base_dir, fn)
            if os.path.isfile(p):
                os.remove(p)

    if verbose:
        print(f"Seasons on disk: {discovered}")
        print(f"Already in master: {sorted(already) or '(none)'}")
        print(f"Processing this run: {todo or '(nothing new)'}")

    new_ranks, new_z, new_stats = [], [], []
    for s in todo:
        res = process_season(s, base_dir=base_dir, verbose=verbose)
        if res is None:
            continue
        new_ranks.append(res["ranks"])
        new_z.append(res["zscores"])
        new_stats.append(res["stats"])

    processed = [r["season"].iloc[0] for r in new_ranks] if new_ranks else []
    replace = set(processed)
    _upsert_master(base_dir, "ranks",
                   pd.concat(new_ranks, ignore_index=True) if new_ranks else None, replace)
    _upsert_master(base_dir, "zscores",
                   pd.concat(new_z, ignore_index=True) if new_z else None, replace)
    if WRITE_STATS:
        _upsert_master(base_dir, "stats",
                       pd.concat(new_stats, ignore_index=True) if new_stats else None, replace)

    if verbose:
        keys = ("ranks", "zscores", "stats") if WRITE_STATS else ("ranks", "zscores")
        names = " / ".join(MASTER_FILES[k] for k in keys)
        print(f"\nMaster files under {base_dir}:\n   {names}")
        print(f"   seasons now in master: {sorted(_seasons_in_master(base_dir))}")
    return processed


# %% -------------------------------------------------------------- diagnostics
def inspect_season(season, base_dir=BASE_DIR, n_playtypes=100):
    """Print the schema / value diagnostics for one season BEFORE trusting output.

    Mirrors the "inspect the actual columns first" step: column list, unique
    playType and driveResult values, elapsed representation, points typing.
    """
    path = os.path.join(base_dir, str(season), "combined.csv")
    df = _read_combined(path)
    print(f"=== {season}: {path}")
    print(f"columns ({df.shape[1]} kept of the file):")
    print("  " + ", ".join(df.columns))
    cols = resolve_columns(df.columns, season)
    reg = df[df[cols["season_type"]].astype("string").str.lower() == REGULAR_SEASON_VALUE]
    print(f"\nregular-season rows: {len(reg):,}   games: {reg[cols['game_id']].nunique()}")
    print(f"weeks: {sorted(pd.to_numeric(reg[cols['week']], errors='coerce').dropna().unique().tolist())}")
    print("\nplayType value_counts:")
    print(reg[cols["play_type"]].value_counts().head(n_playtypes).to_string())
    if cols["drive_result"]:
        print("\ndrive_driveResult value_counts:")
        print(reg[cols["drive_result"]].value_counts().to_string())
    print("\nelapsed columns present:",
          [k for k in ("elapsed_min", "elapsed_sec", "elapsed_flat") if cols[k]])
    _warn_unknown_playtypes(reg, cols, season)
    _warn_empty_categories(reg, cols, season)


# %% -------------------------------------------------------------- validation
def validate_season(season, base_dir=BASE_DIR, sample_team=None):
    """Spot-check correctness of one season against the raw combined.csv.

    Checks:
      (1) manual recompute of a few stats for one team through a chosen week;
      (2) every FBS team has the expected number of week-rows;
      (3) a known-bad defense ranks LOW on '*_against' stats (direction flip).
    Prints results; raises AssertionError on a hard mismatch.
    """
    res = process_season(season, base_dir=base_dir, verbose=False)
    assert res is not None
    stats, ranks, fbs = res["stats"], res["ranks"], res["fbs"]
    season_weeks = res["season_weeks"]

    path = os.path.join(base_dir, str(season), "combined.csv")
    raw = _read_combined(path)
    cols = resolve_columns(raw.columns, season)
    raw = raw[raw[cols["season_type"]].astype("string").str.lower() == REGULAR_SEASON_VALUE].copy()

    print(f"\n================ VALIDATION {season} ================")

    # (1) Manual spot-check for one team through a mid-season week.
    if sample_team is None:
        sample_team = sorted(fbs)[0]
    wk = season_weeks[min(len(season_weeks) - 1, 6)]   # ~week 7
    _spotcheck_team_week(raw, cols, stats, sample_team, wk)

    # (2) Week-row counts: each FBS team should have rows from its first game
    # week through the season's last week (byes included), no gaps.
    print("\n-- week-row counts --")
    problems = 0
    smax = max(season_weeks)
    for team in sorted(fbs):
        sub = ranks[ranks["team"] == team]
        if sub.empty:
            print(f"   !! {team}: NO rows"); problems += 1; continue
        wmin, wmax = sub["week"].min(), sub["week"].max()
        expected = [w for w in season_weeks if wmin <= w <= smax]
        got = sorted(sub["week"].unique().tolist())
        if got != expected:
            print(f"   !! {team}: weeks {got} != expected {expected}"); problems += 1
    print(f"   {len(fbs)} FBS teams checked, {problems} with unexpected week-rows"
          f" (last week of season = {smax}).")

    # (3) Direction flip: worst points-allowed defense should rank near 1.
    print("\n-- defensive direction flip (points_against) --")
    last = stats[stats["week"] == smax]
    worst = last.loc[last["points_against"].idxmax()]     # most points allowed/game
    best = last.loc[last["points_against"].idxmin()]
    r = ranks[ranks["week"] == smax]
    n = r["points_against"].notna().sum()
    worst_rank = r.loc[r["team"] == worst["team"], "points_against"].iloc[0]
    best_rank = r.loc[r["team"] == best["team"], "points_against"].iloc[0]
    print(f"   most points allowed/game: {worst['team']} "
          f"({worst['points_against']:.1f}) -> rank {worst_rank:.0f} of {n} (should be near 1)")
    print(f"   fewest points allowed/game: {best['team']} "
          f"({best['points_against']:.1f}) -> rank {best_rank:.0f} of {n} (should be near {n})")
    assert worst_rank < best_rank, "direction flip FAILED for points_against"
    print("   OK: fewer points allowed -> higher (better) rank.")
    return res


def _spotcheck_team_week(raw, cols, stats, team, week):
    """Recompute rushing yds/game, pass yds/game, points/game from scratch."""
    print(f"-- manual spot-check: {team} through week {week} --")
    gid, wk = cols["game_id"], cols["week"]
    tp = raw[(pd.to_numeric(raw[wk], errors="coerce") <= week)
             & ((raw[cols["offense"]] == team) | (raw[cols["defense"]] == team))]
    games = tp[gid].unique()
    # games played through week (as offense or defense in the game)
    gp = len(set(raw[(pd.to_numeric(raw[wk], errors="coerce") <= week)
                     & ((raw[cols["home_team"]] == team) | (raw[cols["away_team"]] == team))][gid]))
    pt = raw[cols["play_type"]].astype("string")
    yg = pd.to_numeric(raw[cols["yards_gained"]], errors="coerce")
    m_week = pd.to_numeric(raw[wk], errors="coerce") <= week
    is_rush = pt.isin(RUSH_TYPES)
    is_comp = pt.isin(PASS_COMPLETION_TYPES)
    off = raw[cols["offense"]] == team
    rush_yds = yg[m_week & off & is_rush].sum()
    pass_yds = yg[m_week & off & is_comp].sum()
    # points from games
    g = raw.drop_duplicates(gid)
    gm = g[(pd.to_numeric(g[wk], errors="coerce") <= week)
           & ((g[cols["home_team"]] == team) | (g[cols["away_team"]] == team))]
    pf = 0
    for _, row in gm.iterrows():
        pf += (row[cols["home_points"]] if row[cols["home_team"]] == team
               else row[cols["away_points"]])
    man = {"games": gp, "rush_yds/g": rush_yds / gp, "pass_yds/g": pass_yds / gp,
           "points/g": pf / gp}

    row = stats[(stats["team"] == team) & (stats["week"] == week)]
    if row.empty:
        print("   (team has no row this week -- try another team/week)"); return
    row = row.iloc[0]
    pipe = {"games": row["games_played"], "rush_yds/g": row["rush_yds_for"],
            "pass_yds/g": row["pass_yds_for"], "points/g": row["points_for"]}
    print(f"   {'stat':14s} {'manual':>10s} {'pipeline':>10s}  ok?")
    ok_all = True
    for k in man:
        a, b = man[k], pipe[k]
        ok = abs(a - b) < 1e-6
        ok_all &= ok
        print(f"   {k:14s} {a:10.3f} {b:10.3f}  {'OK' if ok else 'MISMATCH'}")
    assert ok_all, f"spot-check mismatch for {team} week {week}"
    print("   OK: pipeline matches hand calculation.")


# %% -------------------------------------------------------------------- main
def main():
    run_all_seasons()


if __name__ == "__main__":
    main()
