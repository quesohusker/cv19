"""
QuesoHusker's Weekly CFB Analysis and Predictions
=================================================

A Streamlit app over the cv19 data pipeline. Four views (top tabs):
  * Stat Comparison  -- any two teams: last game (vs opponent) AND season avg
  * Jon's 14         -- the 14 elite-program benchmarks: last game AND season
  * Power Rankings   -- weekly opponent-adjusted ratings, filterable by conference
  * Game Predictions -- per-game 2026 forecast, filter/sort by conference, with
                        an expandable per-game stat + Jon's-14 detail

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
    "power": os.path.join(MASTER, "power_ratings_weekly.csv"),
    "conf": os.path.join(MASTER, "team_conferences.csv"),
    "sched": os.path.join(MASTER, "pregame_win_probability_all_seasons.csv"),
    "bench": os.path.join(SCRATCH, "benchmark_winpct_seasons.csv"),
    "bench_games": os.path.join(SCRATCH, "benchmark_winpct_games.csv"),
    "margin": os.path.join(PRED, "margin_predictor_2026.csv"),
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
    "South Carolina": ("#73000a", "#000000"),
    "Ole Miss": ("#14213d", "#ce1126"), "Mississippi State": ("#5d1725", "#ffffff"),
    "Kentucky": ("#0033a0", "#ffffff"), "Arkansas": ("#9d2235", "#ffffff"),
    "Vanderbilt": ("#866d4b", "#000000"),
}


def team_colors(team):
    return TEAM_COLORS.get(team, NEUTRAL)


def chip(team, big=False):
    """Return an HTML pill in the team's colors."""
    fg, bg = team_colors(team)
    size = "1.4rem" if big else "0.95rem"
    pad = "0.35rem 0.9rem" if big else "0.1rem 0.5rem"
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
    ("explosive", 9.0, ">=", "Explosive plays 9+"),
    ("third_down_rate", 0.44, ">=", "3rd-down rate 44%+"),
    ("rz_td_rate", 0.67, ">=", "Red-zone TD rate 67%+"),
    ("sacks_allowed", 1.6, "<=", "Sacks allowed ≤1.6"),
    ("pts_allowed", 20.0, "<=", "Points allowed ≤20"),
    ("ypc_allowed", 3.7, "<=", "Yards/carry allowed ≤3.7"),
    ("opp_rz_trips", 3.2, "<=", "Opp RZ trips ≤3.2"),
    ("opp_rz_td_rate", 0.55, "<=", "Opp RZ TD rate ≤55%"),
    ("sacks_made", 2.5, ">=", "Sacks 2.5+"),
    ("turnover_margin", 0.5, ">=", "Turnover margin +0.5+"),
    ("takeaways", 1.75, ">=", "Takeaways 1.75+"),
]
PCT_BENCH = {"third_down_rate", "rz_td_rate", "opp_rz_td_rate"}   # show as %


def met(value, thr, direction):
    if pd.isna(value):
        return False
    return value >= thr if direction == ">=" else value <= thr


def bench_cell(val, is_met, color, pct=False):
    """Benchmark value cell. Met -> team-color pill, white text (readable on any
    background); not met -> muted gray; NaN -> —."""
    if pd.isna(val):
        return "<span style='color:#6b7280'>—</span>"
    txt = f"{val*100:.0f}%" if pct else f"{val:.2f}"
    if is_met:
        return (f"<span style='background:{color};color:#fff;padding:0.05rem 0.4rem;"
                f"border-radius:6px;font-weight:700'>✓ {txt}</span>")
    return f"<span style='color:#9aa0a6;font-weight:600'>{txt}</span>"


# --------------------------------------------------------------------------- #
# stat catalog for the comparison view
#   label, for_col, against_col, fmt   (against_col=None => single stat)
# --------------------------------------------------------------------------- #
CATALOG = [
    ("Win %", "win_pct", None, "{:.3f}"),
    ("Points / game", "points_for", "points_against", "{:.1f}"),
    ("Rushing yds / game", "rush_yds_for", "rush_yds_against", "{:.1f}"),
    ("Passing yds / game", "pass_yds_for", "pass_yds_against", "{:.1f}"),
    ("Yards / carry", "yards_per_rush_for", "yards_per_rush_against", "{:.2f}"),
    ("Yards / pass att", "yards_per_pass_att_for", "yards_per_pass_att_against", "{:.2f}"),
    ("Completion %", "comp_pct_for", "comp_pct_against", "{:.1%}"),
    ("3rd-down %", "third_down_pct_for_approx", "third_down_pct_against_approx", "{:.1%}"),
    ("Red-zone score %", "red_zone_pct_for_approx", "red_zone_pct_against_approx", "{:.1%}"),
    ("Sacks / game", "sacks_made", "sacks_allowed", "{:.2f}"),
    ("Interceptions / game", "int_made", "int_thrown", "{:.2f}"),
    ("Time of possession (s)", "top_for", "top_against", "{:.0f}"),
]


# --------------------------------------------------------------------------- #
# cached loaders
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def _read(path):
    return pd.read_csv(path, low_memory=False) if os.path.isfile(path) else None


@st.cache_data(show_spinner=False)
def load_stats_raw():
    """Full weekly (cumulative-by-week) team stats -- one row per team/week."""
    return _read(PATHS["stats"])


@st.cache_data(show_spinner=False)
def load_team_season_stats():
    """One season-final (latest-week) cumulative row per (season, team)."""
    df = load_stats_raw()
    if df is None:
        return None
    df = df.sort_values(["season", "team", "week"])
    return df.groupby(["season", "team"], as_index=False).tail(1).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_bench():
    return _read(PATHS["bench"])


@st.cache_data(show_spinner=False)
def load_bench_games():
    return _read(PATHS["bench_games"])


@st.cache_data(show_spinner=False)
def load_power():
    return _read(PATHS["power"])


@st.cache_data(show_spinner=False)
def load_conferences():
    """(season, team, conference) lookup, or None if not built yet."""
    return _read(PATHS["conf"])


@st.cache_data(show_spinner=False)
def load_sched():
    """Universal (game_id, season, week, home_team, away_team) schedule."""
    return _read(PATHS["sched"])


@st.cache_data(show_spinner=False)
def load_predictions():
    return _read(PATHS["margin"])


def missing(name):
    st.warning(f"Data file not found: `{PATHS[name]}`.\n\n"
               f"Run the pipeline (`./pipeline.sh --ignore-gate --no-commit`) or set "
               f"`CFDB_BASE_DIR` to your project folder.")


# --------------------------------------------------------------------------- #
# per-game reconstruction helpers  (last game, opponent, benchmarks)
# --------------------------------------------------------------------------- #
def opp_for(sched, season, team, week):
    """Opponent of `team` in (season, week), or None."""
    if sched is None or week is None:
        return None
    s = sched[(sched["season"] == season) & (sched["week"] == week)]
    row = s[(s["home_team"] == team) | (s["away_team"] == team)]
    if not len(row):
        return None
    r = row.iloc[0]
    return r["away_team"] if r["home_team"] == team else r["home_team"]


def season_final_row(raw, season, team):
    """Latest cumulative (season-to-date average) row for a team."""
    if raw is None:
        return None
    sub = raw[(raw["season"] == season) & (raw["team"] == team)].sort_values("week")
    return sub.iloc[-1] if len(sub) else None


def last_game_stats(raw, sched, season, team):
    """De-cumulate the weekly (cumulative-average) stats into the SINGLE most
    recent game. Returns (Series, week, opponent) or (None, None, None).

    Additive per-game averages de-cumulate exactly; the main rate stats are
    recomputed from their de-cumulated numerator/denominator so they're exact
    too. (Approximate '..._approx' rates de-cumulate on a games-weighted basis.)
    """
    if raw is None:
        return None, None, None
    sub = raw[(raw["season"] == season) & (raw["team"] == team)].sort_values("week")
    if not len(sub):
        return None, None, None
    gp = pd.to_numeric(sub["games_played"], errors="coerce").fillna(0).values
    inc = [i for i in range(len(sub)) if gp[i] > (gp[i - 1] if i > 0 else 0)]
    if not inc:
        return None, None, None
    cur = sub.iloc[inc[-1]]
    k = int(round(float(cur["games_played"])))
    prev = None
    if k > 1:
        pv = sub[np.isclose(pd.to_numeric(sub["games_played"], errors="coerce"), k - 1)]
        prev = pv.iloc[-1] if len(pv) else None

    lg = {}
    for c in sub.columns:
        if c in ("season", "team", "week", "week_result"):
            continue
        cv = pd.to_numeric(pd.Series([cur.get(c)]), errors="coerce").iloc[0]
        if prev is None or k <= 1:
            lg[c] = cv
        else:
            pvv = pd.to_numeric(pd.Series([prev.get(c)]), errors="coerce").iloc[0]
            lg[c] = cv * k - pvv * (k - 1)

    def rate(n, d):
        dv = lg.get(d)
        return lg[n] / dv if (dv not in (0, None) and pd.notna(dv)) else np.nan

    lg["comp_pct_for"] = rate("comp_for", "pass_att_for")
    lg["comp_pct_against"] = rate("comp_against", "pass_att_against")
    lg["yards_per_rush_for"] = rate("rush_yds_for", "rush_att_for")
    lg["yards_per_rush_against"] = rate("rush_yds_against", "rush_att_against")
    lg["yards_per_pass_att_for"] = rate("pass_yds_for", "pass_att_for")
    lg["yards_per_pass_att_against"] = rate("pass_yds_against", "pass_att_against")

    week = int(cur["week"])
    return pd.Series(lg), week, opp_for(sched, season, team, week)


def bench_last_game(bgames, sched, season, team):
    """The 14 benchmark metrics for a team's most recent game.
    Returns (Series, week, opponent) or (None, None, None)."""
    if bgames is None:
        return None, None, None
    bg = bgames[(bgames["season"] == season) & (bgames["team"] == team)].copy()
    for c in ("team_fbs", "opp_fbs"):
        if c in bg.columns:
            bg = bg[bg[c] == True]  # noqa: E712
    if not len(bg):
        return None, None, None

    wk, opp = None, None
    if sched is not None and "gameId" in bg.columns:
        s = sched[["game_id", "week", "home_team", "away_team"]].rename(
            columns={"game_id": "gameId"})
        bg = bg.merge(s, on="gameId", how="left")
        if bg["week"].notna().any():
            bg = bg.sort_values("week")
            row = bg.iloc[-1]
            wk = int(row["week"]) if pd.notna(row["week"]) else None
            if pd.notna(row.get("home_team")):
                opp = row["away_team"] if row["home_team"] == team else row["home_team"]
            return row, wk, opp
    # no schedule join -> gameId is roughly chronological within a season
    row = bg.sort_values("gameId").iloc[-1] if "gameId" in bg.columns else bg.iloc[-1]
    return row, wk, opp


# --------------------------------------------------------------------------- #
# reusable renderers (used by the tabs AND the per-game prediction expanders)
# --------------------------------------------------------------------------- #
def _fmt(v, fmt):
    return fmt.format(v) if pd.notna(v) else "—"


@st.cache_data(show_spinner=False)
def render_matchup_stats(season, ta, tb):
    """Side-by-side stat table: Last game + Season avg for each team."""
    raw, sched = load_stats_raw(), load_sched()
    ra, rb = season_final_row(raw, season, ta), season_final_row(raw, season, tb)
    if ra is None or rb is None:
        return f"<p class='muted'>No {season} stats for one of these teams.</p>"
    la, wka, oppa = last_game_stats(raw, sched, season, ta)
    lb, wkb, oppb = last_game_stats(raw, sched, season, tb)

    def g(series, col):
        return series.get(col, np.nan) if series is not None else np.nan

    def valcell(series, col, fmt, sep=False, best=False):
        # season/last value cell (win% shown as a decimal here; the LAST column's
        # single-game win% is rendered W/L by _winloss_cell instead)
        txt = _fmt(g(series, col), fmt)
        cls = "num" + (" sep" if sep else "") + (" better" if best else "")
        return f"<td class='{cls}'>{txt}</td>"

    rows = []
    for label, fcol, acol, fmt in CATALOG:
        entries = [(label, fcol, True)] if acol is None else [
            (f"{label} — off", fcol, True), (f"{label} — def/allowed", acol, False)]
        for lab, col, higher_better in entries:
            va, vb = g(ra, col), g(rb, col)
            a_best = b_best = False
            if pd.notna(va) and pd.notna(vb) and va != vb:
                a_best = (va > vb) if higher_better else (va < vb)
                b_best = not a_best
            last_a = valcell(la, col, fmt) if col != "win_pct" else \
                _winloss_cell(la, col)
            last_b = valcell(lb, col, fmt, sep=True) if col != "win_pct" else \
                _winloss_cell(lb, col, sep=True)
            rows.append(
                f"<tr><td class='lab'>{lab}</td>"
                f"{last_a}{valcell(ra, col, fmt, best=a_best)}"
                f"{last_b}{valcell(rb, col, fmt, sep=False, best=b_best)}</tr>")

    la_lbl = f"Last Game ({oppa})" if oppa else "Last Game"
    lb_lbl = f"Last Game ({oppb})" if oppb else "Last Game"
    header = (
        "<table class='cmp'><thead>"
        f"<tr><th></th><th class='grp' colspan='2'>{chip(ta)}</th>"
        f"<th class='grp sep' colspan='2'>{chip(tb)}</th></tr>"
        "<tr><th class='lab'>Stat</th>"
        f"<th class='sub'>{la_lbl}</th><th class='sub'>Season</th>"
        f"<th class='sub sep'>{lb_lbl}</th><th class='sub'>Season</th></tr>"
        "</thead><tbody>")
    return header + "".join(rows) + "</tbody></table>"


def _winloss_cell(series, col, sep=False):
    v = series.get(col, np.nan) if series is not None else np.nan
    cls = "num" + (" sep" if sep else "")
    if pd.isna(v):
        return f"<td class='{cls}'>—</td>"
    return f"<td class='{cls}'>{'W' if v >= 0.5 else 'L'}</td>"


def _bench_count(series):
    if series is None:
        return None
    return sum(1 for col, thr, d, _ in BENCHMARKS if met(series.get(col, np.nan), thr, d))


@st.cache_data(show_spinner=False)
def render_matchup_bench(season, ta, tb):
    """Side-by-side Jon's-14 table: Last game + Season for each team."""
    bench, bgames, sched = load_bench(), load_bench_games(), load_sched()
    if bench is None:
        return "<p class='muted'>No benchmark data.</p>"
    sa = bench[(bench["season"] == season) & (bench["team"] == ta)]
    sb = bench[(bench["season"] == season) & (bench["team"] == tb)]
    if not len(sa) or not len(sb):
        return (f"<p class='muted'>No {season} benchmark data for one of these "
                f"teams (benchmarks cover 2014–latest).</p>")
    sa, sb = sa.iloc[0], sb.iloc[0]
    la, wka, oppa = bench_last_game(bgames, sched, season, ta)
    lb, wkb, oppb = bench_last_game(bgames, sched, season, tb)
    fa, fb = team_colors(ta)[0], team_colors(tb)[0]

    rows = []
    for col, thr, direction, label in BENCHMARKS:
        pct = col in PCT_BENCH
        cells = [
            ("", la, fa, False), ("", sa, fa, False),
            ("sep", lb, fb, True), ("", sb, fb, False),
        ]
        tds = []
        for extra, series, color, is_sep in cells:
            v = series.get(col, np.nan) if series is not None else np.nan
            inner = bench_cell(v, met(v, thr, direction), color, pct=pct)
            tds.append(f"<td class='num {extra}'>{inner}</td>")
        rows.append(f"<tr><td class='lab'>{label}</td>{''.join(tds)}</tr>")

    tot = (f"<tr class='tot'><td class='lab'><b>Met (of 14)</b></td>"
           f"<td class='num'><b>{_dash(_bench_count(la))}</b></td>"
           f"<td class='num'><b>{int(sa.get('benchmarks_met', 0))}</b></td>"
           f"<td class='num sep'><b>{_dash(_bench_count(lb))}</b></td>"
           f"<td class='num'><b>{int(sb.get('benchmarks_met', 0))}</b></td></tr>")

    la_lbl = f"Last Game ({oppa})" if oppa else "Last Game"
    lb_lbl = f"Last Game ({oppb})" if oppb else "Last Game"

    def cap(team, srow):
        gms = int(srow.get("games", 0))
        return f"{team}: season avg over {gms} game{'s' if gms != 1 else ''}"

    header = (
        "<table class='cmp'><thead>"
        f"<tr><th></th><th class='grp' colspan='2'>{chip(ta)}</th>"
        f"<th class='grp sep' colspan='2'>{chip(tb)}</th></tr>"
        "<tr><th class='lab'>Benchmark</th>"
        f"<th class='sub'>{la_lbl}</th><th class='sub'>Season</th>"
        f"<th class='sub sep'>{lb_lbl}</th><th class='sub'>Season</th></tr>"
        "</thead><tbody>")
    caption = (f"<div class='cap'>{cap(ta, sa)} &nbsp;·&nbsp; {cap(tb, sb)}</div>")
    return header + "".join(rows) + tot + "</tbody></table>" + caption


def _dash(v):
    return "—" if v is None else str(v)


# --------------------------------------------------------------------------- #
# page config + header + styles
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="QuesoHusker's Weekly CFB", page_icon="\U0001F33D",
                   layout="wide")

st.markdown("""
<style>
.cmp{border-collapse:collapse;width:100%;font-size:0.85rem;margin-top:0.3rem}
.cmp th,.cmp td{padding:2px 8px;border-bottom:1px solid rgba(128,128,128,0.22)}
.cmp td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.cmp td.lab,.cmp th.lab{text-align:left;white-space:nowrap;color:#c9ccd1}
.cmp th.grp{text-align:center;padding-bottom:4px}
.cmp th.sub{text-align:right;color:#9aa0a6;font-weight:600;font-size:0.72rem}
.cmp .sep{border-left:2px solid rgba(128,128,128,0.35)}
.cmp tbody tr:hover{background:rgba(128,128,128,0.10)}
.cmp td.better{font-weight:800;color:#22c55e}
.cmp tr.tot td{border-top:2px solid rgba(128,128,128,0.4);border-bottom:none}
.cap{color:#9aa0a6;font-size:0.75rem;margin:0.3rem 0 0.2rem}
.muted{color:#9aa0a6}
</style>
""", unsafe_allow_html=True)

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
with tab_cmp:
    if stats is None:
        missing("stats")
    elif team_a and team_b:
        st.markdown(render_matchup_stats(season, team_a, team_b), unsafe_allow_html=True)
        st.caption("Green = better of the two on the season. Offense = the team's "
                   "own production; def/allowed = what it gave up.")


# --------------------------------------------------------------------------- #
# view: Jon's 14
# --------------------------------------------------------------------------- #
with tab_bench:
    if load_bench() is None:
        missing("bench")
    elif team_a and team_b:
        st.markdown("How each team stacks up against the 14 elite-program "
                    "benchmarks (explosive plays set at 9+/game). ✓ = benchmark met.")
        st.markdown(render_matchup_bench(season, team_a, team_b), unsafe_allow_html=True)


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
            latest.insert(0, "Rank", latest.index + 1)   # national rank

            confs = load_conferences()
            cols = ["Rank", "team", "rating_overall", "rating_off", "rating_def"]
            csel = "All"
            if confs is not None:
                cmap = (confs[confs["season"] == season]
                        .set_index("team")["conference"].to_dict())
                latest["Conference"] = latest["team"].map(cmap)
                opts = ["All"] + sorted(latest["Conference"].dropna().unique())
                csel = st.selectbox("Conference", opts, index=0, key="power_conf")
                cols.insert(2, "Conference")

            st.markdown(f"**Power ratings — {season}, through week {wk-1}** "
                        f"(points vs. an average FBS team; higher is better).")

            view = latest if csel == "All" else latest[latest["Conference"] == csel]
            show = view[cols].rename(columns={
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
            if csel != "All":
                st.caption(f"{len(show)} {csel} team(s); Rank is national (of "
                           f"{len(latest)} FBS teams).")


# --------------------------------------------------------------------------- #
# view: Game Predictions
# --------------------------------------------------------------------------- #
def _game_row(g):
    home, away = g["home_team"], g["away_team"]
    pm, ph = g["predicted_margin"], g["p_home_win"]
    fav = home if pm >= 0 else away
    favp = ph if pm >= 0 else 1 - ph
    cols = st.columns([1.4, 3, 2.4])
    cols[0].markdown(f"Wk {int(g['week'])}")
    cols[1].markdown(f"{chip(away)} &nbsp;at&nbsp; {chip(home)}", unsafe_allow_html=True)
    cols[2].markdown(
        f"<div style='text-align:right'>{chip(fav)} by <b>{abs(pm):.1f}</b> "
        f"&nbsp;|&nbsp; win prob <b>{favp:.0%}</b></div>", unsafe_allow_html=True)
    if pd.notna(g.get("actual_margin", np.nan)):
        res_home = g["actual_margin"] > 0
        hit = res_home == (pm >= 0)
        cols[2].markdown(
            f"<div style='text-align:right;color:{'#16a34a' if hit else '#dc2626'};"
            f"font-size:0.85rem'>final margin {g['actual_margin']:+.0f} "
            f"{'✓' if hit else '✗'}</div>", unsafe_allow_html=True)


with tab_pred:
    preds = load_predictions()
    if preds is None:
        missing("margin")
    else:
        pred_season = int(preds["season"].iloc[0]) if "season" in preds else 2026
        confs = load_conferences()
        cmap = {}
        if confs is not None:
            cmap = (confs[confs["season"] == pred_season]
                    .set_index("team")["conference"].to_dict())

        colf1, colf2, colf3 = st.columns([1, 1.3, 1.3])
        weeks = sorted(preds["week"].unique())
        week_opts = ["All upcoming"] + [int(w) for w in weeks]
        # default to the next upcoming week (not the whole rest of the season)
        up = preds[preds["actual_margin"].isna()] if "actual_margin" in preds else preds
        up_weeks = sorted(up["week"].unique())
        wk_index = week_opts.index(int(up_weeks[0])) if len(up_weeks) else 0
        wsel = colf1.selectbox("Week", week_opts, index=wk_index)
        conf_opts = ["All"] + (sorted({c for c in cmap.values()}) if cmap else [])
        csel = colf2.selectbox("Conference", conf_opts, index=0, key="pred_conf")
        team_filter = colf3.selectbox("Team filter", ["(any)"] + all_teams)

        d = preds.copy()
        if wsel == "All upcoming":
            d = d[d["actual_margin"].isna()] if "actual_margin" in d else d
        else:
            d = d[d["week"] == wsel]
        d["home_conf"] = d["home_team"].map(cmap)
        d["away_conf"] = d["away_team"].map(cmap)
        if csel != "All":
            d = d[(d["home_conf"] == csel) | (d["away_conf"] == csel)]
        if team_filter != "(any)":
            d = d[(d["home_team"] == team_filter) | (d["away_team"] == team_filter)]

        # sort by conference when "All" is shown; else by week
        if csel == "All" and cmap:
            d["_ck"] = d["home_conf"].fillna("~ Other")
            d = d.sort_values(["_ck", "week", "game_id"])
        else:
            d = d.sort_values(["week", "game_id"])

        DETAIL_LIMIT = 40      # only build per-game expanders for a manageable slate
        if not len(d):
            st.info("No games match this filter.")
        else:
            show_detail = len(d) <= DETAIL_LIMIT
            head = (f"**{len(d)} game(s)** — predicted margin & win probability "
                    f"(model {preds['model_version'].iloc[0]}).")
            if show_detail:
                head += " Expand a game for the stat comparison and each team's Jon's 14."
            else:
                head += (f" Showing more than {DETAIL_LIMIT} games — filter by week, "
                         f"conference, or team to expand per-game detail.")
            st.markdown(head)
            group_by_conf = (csel == "All" and bool(cmap))
            cur_conf = None
            for _, g in d.iterrows():
                if group_by_conf and g["home_conf"] != cur_conf:
                    cur_conf = g["home_conf"]
                    st.markdown(f"##### {cur_conf or 'Other / independent'}")
                _game_row(g)
                if show_detail:
                    with st.expander("▸ Stats comparison & Jon's 14"):
                        st.markdown("**Stat comparison**")
                        st.markdown(render_matchup_stats(pred_season, g["away_team"],
                                                         g["home_team"]),
                                    unsafe_allow_html=True)
                        st.markdown("**Jon's 14**")
                        st.markdown(render_matchup_bench(pred_season, g["away_team"],
                                                         g["home_team"]),
                                    unsafe_allow_html=True)
            if group_by_conf:
                st.caption("Games grouped by the home team's conference.")

st.caption("Data: cv19 pipeline — refreshed nightly.")
