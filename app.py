"""
QuesoHusker's Weekly CFB Analysis and Predictions
=================================================

A Streamlit app over the cv19 data pipeline. Four views (top tabs):
  * Stat Comparison  -- any two teams, offense "for" and defense "against"
  * Jon's 14         -- the 14 elite-program benchmarks (explosive 9+)
  * Power Rankings   -- the weekly opponent-adjusted power ratings
  * Game Predictions -- per-game 2026 forecast (margin + win probability)

Everything lives in THIS ONE FILE on purpose -- team colors, thresholds, the
stat catalog, and the views -- so it's fast to iterate. Edit and re-run.

Run it:
    pip install streamlit          # once
    streamlit run app.py

Data: reads the local pipeline outputs under <project>/data/cfbd/ and
<project>/scratchpad/. Override the project root with CFDB_BASE_DIR.
"""
import os

import numpy as np
import pandas as pd
import streamlit as st

# --------------------------------------------------------------------------- #
# data locations
# --------------------------------------------------------------------------- #
APP_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("CFDB_BASE_DIR", APP_DIR)
MASTER = os.path.join(BASE, "data", "cfbd", "master")
PRED = os.path.join(BASE, "data", "cfbd", "predictions")
SCRATCH = os.path.join(BASE, "scratchpad")

PATHS = {
    "stats": os.path.join(MASTER, "team_stats_all_seasons.csv"),
    "ranks": os.path.join(MASTER, "team_ranks_all_seasons.csv"),
    "power": os.path.join(MASTER, "power_ratings_weekly.csv"),
    "bench": os.path.join(SCRATCH, "benchmark_winpct_seasons.csv"),
    "margin": os.path.join(PRED, "margin_predictor_2026.csv"),
    "wp": os.path.join(PRED, "in_game_wp_2026.csv"),
}

# --------------------------------------------------------------------------- #
# team colors  (primary, secondary) -- edit freely; unknown teams -> NEUTRAL
# --------------------------------------------------------------------------- #
NEUTRAL = ("#334155", "#94a3b8")
TEAM_COLORS = {
    # Big Ten
    "Nebraska": ("#e41c38", "#f6f2e6"), "Ohio State": ("#bb0000", "#666666"),
    "Michigan": ("#00274c", "#ffcb05"), "Penn State": ("#041e42", "#ffffff"),
    "Michigan State": ("#18453b", "#ffffff"), "Iowa": ("#111111", "#ffcd00"),
    "Wisconsin": ("#c5050c", "#ffffff"), "Minnesota": ("#7a0019", "#ffcc33"),
    "Illinois": ("#13294b", "#e84a27"), "Indiana": ("#990000", "#eeedeb"),
    "Purdue": ("#000000", "#ceb888"), "Northwestern": ("#4e2a84", "#ffffff"),
    "Maryland": ("#e21833", "#ffd520"), "Rutgers": ("#cc0033", "#111111"),
    "UCLA": ("#2d68c4", "#f2a900"), "USC": ("#990000", "#ffcc00"),
    "Oregon": ("#154733", "#fee123"), "Washington": ("#4b2e83", "#b7a57a"),
    # National powers / common opponents
    "Alabama": ("#9e1b32", "#828a8f"), "Georgia": ("#ba0c2f", "#000000"),
    "Notre Dame": ("#0c2340", "#c99700"), "Clemson": ("#f56600", "#522d80"),
    "Texas": ("#bf5700", "#ffffff"), "Oklahoma": ("#841617", "#fdf9d8"),
    "LSU": ("#461d7c", "#fdd023"), "Tennessee": ("#ff8200", "#ffffff"),
    "Florida": ("#0021a5", "#fa4616"), "Auburn": ("#0c2340", "#dd550c"),
    "Texas A&M": ("#500000", "#ffffff"), "Miami": ("#f47321", "#005030"),
    "Florida State": ("#782f40", "#ceb888"), "Oklahoma State": ("#ff7300", "#000000"),
    "Utah": ("#cc0000", "#ffffff"), "Colorado": ("#000000", "#cfb87c"),
    "Arizona": ("#0c234b", "#cc0033"), "Arizona State": ("#8c1d40", "#ffc627"),
    "Missouri": ("#f1b82d", "#000000"), "Kansas": ("#0051ba", "#e8000d"),
    "Kansas State": ("#512888", "#ffffff"), "Iowa State": ("#c8102e", "#f1be48"),
    "Baylor": ("#154734", "#ffb81c"), "TCU": ("#4d1979", "#a3a9ac"),
    "Cincinnati": ("#e00122", "#000000"), "Houston": ("#c8102e", "#ffffff"),
    "BYU": ("#002e5d", "#ffffff"), "Boise State": ("#0033a0", "#d64309"),
    "Notre Dame ": ("#0c2340", "#c99700"), "South Carolina": ("#73000a", "#000000"),
    "Ole Miss": ("#14213d", "#ce1126"), "Mississippi State": ("#5d1725", "#ffffff"),
    "Kentucky": ("#0033a0", "#ffffff"), "Arkansas": ("#9d2235", "#ffffff"),
    "Vanderbilt": ("#866d4b", "#000000"),
}


def team_colors(team):
    return TEAM_COLORS.get(team, NEUTRAL)


def chip(team, big=False):
    """Return an HTML pill in the team's colors."""
    fg, bg = team_colors(team)
    size = "1.4rem" if big else "1rem"
    pad = "0.35rem 0.9rem" if big else "0.15rem 0.6rem"
    return (f"<span style='background:{fg};color:#fff;padding:{pad};"
            f"border-radius:8px;font-weight:700;font-size:{size};"
            f"box-shadow:inset 0 0 0 2px {bg}55;white-space:nowrap'>{team}</span>")


# --------------------------------------------------------------------------- #
# the 14 benchmarks (explosive 9+)  -> (metric col, threshold, direction, label)
# --------------------------------------------------------------------------- #
BENCHMARKS = [
    ("pts", 32.0, ">=", "Points/game 32+"),
    ("yds_per_play", 6.1, ">=", "Yards/play 6.1+"),
    ("yds_per_pass_att", 8.0, ">=", "Yards/pass att 8.0+"),
    ("explosive", 9.0, ">=", "Explosive plays/game 9+"),
    ("third_down_rate", 0.44, ">=", "3rd-down rate 44%+"),
    ("rz_td_rate", 0.67, ">=", "Red-zone TD rate 67%+"),
    ("sacks_allowed", 1.6, "<=", "Sacks allowed/game ≤1.6"),
    ("pts_allowed", 20.0, "<=", "Points allowed/game ≤20"),
    ("ypc_allowed", 3.7, "<=", "Yards/carry allowed ≤3.7"),
    ("opp_rz_trips", 3.2, "<=", "Opp red-zone trips/game ≤3.2"),
    ("opp_rz_td_rate", 0.55, "<=", "Opp red-zone TD rate ≤55%"),
    ("sacks_made", 2.5, ">=", "Sacks/game 2.5+"),
    ("turnover_margin", 0.5, ">=", "Turnover margin/game +0.5+"),
    ("takeaways", 1.75, ">=", "Takeaways/game 1.75+"),
]


def met(value, thr, direction):
    if pd.isna(value):
        return False
    return value >= thr if direction == ">=" else value <= thr


def bench_cell(val, is_met, color):
    """Benchmark value cell. Met -> a team-color pill with WHITE text (readable
    on any background, dark team colors included); not met -> muted gray; NaN -> —."""
    if pd.isna(val):
        return "<span style='color:#6b7280'>—</span>"
    if is_met:
        return (f"<span style='background:{color};color:#fff;padding:0.12rem 0.55rem;"
                f"border-radius:6px;font-weight:700'>✓ {val:.2f}</span>")
    return f"<span style='color:#9aa0a6;font-weight:600'>{val:.2f}</span>"


# --------------------------------------------------------------------------- #
# stat catalog for the comparison view
#   label -> (for_col, against_col, fmt, higher_is_better_on_offense)
#   against_col=None => single (record-style) stat
# --------------------------------------------------------------------------- #
CATALOG = [
    ("Win %", "win_pct", None, "{:.3f}", True),
    ("Points / game", "points_for", "points_against", "{:.1f}", True),
    ("Rushing yds / game", "rush_yds_for", "rush_yds_against", "{:.1f}", True),
    ("Passing yds / game", "pass_yds_for", "pass_yds_against", "{:.1f}", True),
    ("Yards / carry", "yards_per_rush_for", "yards_per_rush_against", "{:.2f}", True),
    ("Yards / pass att", "yards_per_pass_att_for", "yards_per_pass_att_against", "{:.2f}", True),
    ("Completion %", "comp_pct_for", "comp_pct_against", "{:.1%}", True),
    ("3rd-down %", "third_down_pct_for_approx", "third_down_pct_against_approx", "{:.1%}", True),
    ("Red-zone score %", "red_zone_pct_for_approx", "red_zone_pct_against_approx", "{:.1%}", True),
    ("Sacks / game", "sacks_made", "sacks_allowed", "{:.2f}", True),
    ("Interceptions / game", "int_made", "int_thrown", "{:.2f}", True),
    ("Time of possession (s)", "top_for", "top_against", "{:.0f}", True),
]


# --------------------------------------------------------------------------- #
# cached loaders
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def _read(path):
    return pd.read_csv(path, low_memory=False) if os.path.isfile(path) else None


@st.cache_data(show_spinner=False)
def load_team_season_stats():
    """team_stats_all_seasons -> one season-final row per (season, team)."""
    df = _read(PATHS["stats"])
    if df is None:
        return None
    df = df.sort_values(["season", "team", "week"])
    return df.groupby(["season", "team"], as_index=False).tail(1).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_bench():
    return _read(PATHS["bench"])


@st.cache_data(show_spinner=False)
def load_power():
    return _read(PATHS["power"])


@st.cache_data(show_spinner=False)
def load_predictions():
    m = _read(PATHS["margin"])
    return m


def missing(name):
    st.warning(f"Data file not found: `{PATHS[name]}`.\n\n"
               f"Run the pipeline (`./pipeline.sh --ignore-gate --no-commit`) or set "
               f"`CFDB_BASE_DIR` to your project folder.")


# --------------------------------------------------------------------------- #
# page config + header
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="QuesoHusker's Weekly CFB", page_icon="\U0001F33D",
                   layout="wide")

st.markdown(
    "<h1 style='margin-bottom:0.4rem'>\U0001F33D QuesoHusker's Weekly CFB "
    "<span style='color:#e41c38'>Analysis &amp; Predictions</span></h1>",
    unsafe_allow_html=True)

# ---- shared pickers (sidebar) ----
stats = load_team_season_stats()
all_teams = sorted(stats["team"].unique()) if stats is not None else []
seasons = sorted(stats["season"].unique(), reverse=True) if stats is not None else [2026]

with st.sidebar:
    st.header("Selection")
    # Seasons listed newest-first, so the in-progress season is on top and
    # selected by default. (Jon's 14 / Stat Comparison show a note for a season
    # with no completed data yet.)
    season = st.selectbox("Season", seasons, index=0)
    default_a = all_teams.index("Nebraska") if "Nebraska" in all_teams else 0
    team_a = st.selectbox("Team A", all_teams, index=default_a) if all_teams else None
    b_opts = [t for t in all_teams if t != team_a]
    default_b = b_opts.index("Ohio State") if "Ohio State" in b_opts else 0
    team_b = st.selectbox("Team B", b_opts, index=default_b) if b_opts else None

tab_cmp, tab_bench, tab_power, tab_pred = st.tabs(
    ["\U0001F4CA Stat Comparison", "\U0001F3C6 Jon's 14", "\U0001F4C8 Power Rankings",
     "\U0001F52E Game Predictions"])


# --------------------------------------------------------------------------- #
# view: Stat Comparison
# --------------------------------------------------------------------------- #
def _row(df, season, team):
    r = df[(df["season"] == season) & (df["team"] == team)]
    return r.iloc[0] if len(r) else None


with tab_cmp:
    if stats is None:
        missing("stats")
    elif team_a and team_b:
        ra, rb = _row(stats, season, team_a), _row(stats, season, team_b)
        c1, c2 = st.columns(2)
        c1.markdown(chip(team_a, big=True), unsafe_allow_html=True)
        c2.markdown(chip(team_b, big=True), unsafe_allow_html=True)
        if ra is None or rb is None:
            st.info(f"No {season} data yet for one of these teams.")
        else:
            rows = []
            for label, fcol, acol, fmt, hib in CATALOG:
                def fmt_or_na(v):
                    return fmt.format(v) if pd.notna(v) else "—"
                if acol is None:
                    rows.append({"Stat": label,
                                 f"{team_a}": fmt_or_na(ra.get(fcol, np.nan)),
                                 f"{team_b}": fmt_or_na(rb.get(fcol, np.nan))})
                else:
                    rows.append({"Stat": f"{label} (offense)",
                                 f"{team_a}": fmt_or_na(ra.get(fcol, np.nan)),
                                 f"{team_b}": fmt_or_na(rb.get(fcol, np.nan))})
                    rows.append({"Stat": f"{label} (defense/allowed)",
                                 f"{team_a}": fmt_or_na(ra.get(acol, np.nan)),
                                 f"{team_b}": fmt_or_na(rb.get(acol, np.nan))})
            comp = pd.DataFrame(rows)
            st.dataframe(comp, use_container_width=True, hide_index=True,
                         height=min(60 + 35 * len(comp), 900))
            st.caption("Season-to-date, per-game where applicable. Offense = the "
                       "team's own production; defense/allowed = what it gave up.")


# --------------------------------------------------------------------------- #
# view: Jon's 14
# --------------------------------------------------------------------------- #
with tab_bench:
    bench = load_bench()
    if bench is None:
        missing("bench")
    elif team_a and team_b:
        st.markdown(f"How each team stacks up against the 14 elite-program "
                    f"benchmarks (explosive plays set at 9+/game).")
        ba = bench[(bench["season"] == season) & (bench["team"] == team_a)]
        bb = bench[(bench["season"] == season) & (bench["team"] == team_b)]
        if not len(ba) or not len(bb):
            st.info(f"No {season} benchmark data for one of these teams "
                    f"(benchmarks cover 2014–latest completed).")
        else:
            ba, bb = ba.iloc[0], bb.iloc[0]
            ga, gb = int(ba.get("games", 0)), int(bb.get("games", 0))
            if min(ga, gb) < 8:
                st.caption(f"Season in progress — averages are through "
                           f"{team_a}: {ga} game{'s' if ga != 1 else ''}, "
                           f"{team_b}: {gb} game{'s' if gb != 1 else ''}.")
            head = st.columns([3, 1, 1])
            head[0].markdown("**Benchmark**")
            head[1].markdown(chip(team_a), unsafe_allow_html=True)
            head[2].markdown(chip(team_b), unsafe_allow_html=True)
            fa = team_colors(team_a)[0]
            fb = team_colors(team_b)[0]
            for col, thr, direction, label in BENCHMARKS:
                va, vb = ba.get(col, np.nan), bb.get(col, np.nan)
                ma, mb = met(va, thr, direction), met(vb, thr, direction)
                r = st.columns([3, 1, 1])
                r[0].markdown(label)
                r[1].markdown(bench_cell(va, ma, fa), unsafe_allow_html=True)
                r[2].markdown(bench_cell(vb, mb, fb), unsafe_allow_html=True)
            st.divider()
            tot = st.columns([3, 1, 1])
            tot[0].markdown("**Benchmarks met (of 14)**")
            tot[1].markdown(f"**{int(ba.get('benchmarks_met', 0))}**")
            tot[2].markdown(f"**{int(bb.get('benchmarks_met', 0))}**")


# --------------------------------------------------------------------------- #
# view: Power Rankings
# --------------------------------------------------------------------------- #
with tab_power:
    power = load_power()
    if power is None:
        missing("power")
    else:
        ps = power[power["season"] == season]
        if not len(ps):
            st.info(f"No power ratings for {season} yet.")
        else:
            wk = int(ps["week"].max())
            latest = ps[ps["week"] == wk].copy()
            latest = latest.sort_values("rating_overall", ascending=False).reset_index(drop=True)
            latest.insert(0, "Rank", latest.index + 1)
            st.markdown(f"**Power ratings — {season}, through week {wk-1}** "
                        f"(points vs. an average FBS team; higher is better).")
            show = latest[["Rank", "team", "rating_overall", "rating_off",
                           "rating_def"]].rename(columns={
                "team": "Team", "rating_overall": "Overall",
                "rating_off": "Offense", "rating_def": "Defense"})
            hi = {team_a, team_b}

            def _hl(row):
                if row["Team"] in hi:
                    fg, _ = team_colors(row["Team"])
                    return [f"background-color:{fg}22"] * len(row)
                return [""] * len(row)

            st.dataframe(show.style.apply(_hl, axis=1).format(
                {"Overall": "{:+.1f}", "Offense": "{:+.1f}", "Defense": "{:+.1f}"}),
                use_container_width=True, hide_index=True, height=700)


# --------------------------------------------------------------------------- #
# view: Game Predictions
# --------------------------------------------------------------------------- #
with tab_pred:
    preds = load_predictions()
    if preds is None:
        missing("margin")
    else:
        colf1, colf2 = st.columns([1, 2])
        weeks = sorted(preds["week"].unique())
        wsel = colf1.selectbox("Week", ["All upcoming"] + [int(w) for w in weeks])
        team_filter = colf2.selectbox("Team filter", ["(any)"] + all_teams)

        d = preds.copy()
        if wsel == "All upcoming":
            d = d[d["actual_margin"].isna()] if "actual_margin" in d else d
        else:
            d = d[d["week"] == wsel]
        if team_filter != "(any)":
            d = d[(d["home_team"] == team_filter) | (d["away_team"] == team_filter)]
        d = d.sort_values(["week", "game_id"])

        if not len(d):
            st.info("No games match this filter.")
        else:
            st.markdown(f"**{len(d)} game(s)** — predicted margin & win probability "
                        f"(model {preds['model_version'].iloc[0]}).")
            for _, g in d.iterrows():
                home, away = g["home_team"], g["away_team"]
                pm = g["predicted_margin"]
                ph = g["p_home_win"]
                fav = home if pm >= 0 else away
                favp = ph if pm >= 0 else 1 - ph
                cols = st.columns([2, 3, 2])
                cols[0].markdown(f"Wk {int(g['week'])}", help="regular-season week")
                cols[1].markdown(
                    f"{chip(away)} &nbsp;at&nbsp; {chip(home)}", unsafe_allow_html=True)
                cols[2].markdown(
                    f"<div style='text-align:right'>{chip(fav)} "
                    f"by <b>{abs(pm):.1f}</b> &nbsp;|&nbsp; "
                    f"win prob <b>{favp:.0%}</b></div>", unsafe_allow_html=True)
                if pd.notna(g.get("actual_margin", np.nan)):
                    res = "home" if g["actual_margin"] > 0 else "away"
                    hit = (res == "home") == (pm >= 0)
                    cols[2].markdown(
                        f"<div style='text-align:right;color:{'#16a34a' if hit else '#dc2626'};"
                        f"font-size:0.85rem'>final margin {g['actual_margin']:+.0f} "
                        f"{'✓' if hit else '✗'}</div>", unsafe_allow_html=True)

st.caption("Data: cv19 pipeline — refreshed nightly.")
