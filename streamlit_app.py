"""QuesoHusker's Volleyball — Analysis & Benchmarks.

Read-only front end over the precomputed tables in app_data/. Mirrors the structure
and design system of the CFB app: global season + two-team selection, a stat
comparison, a benchmark scorecard, and opponent-adjusted power rankings. No game
predictions -- volleyball match outcomes are not what this project set out to forecast.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app import data as D
from app import theme as T

st.set_page_config(page_title="QuesoHusker's Volleyball", page_icon="🏐", layout="wide")
st.markdown(T.CSS, unsafe_allow_html=True)

GRADE_MAX = len(D.graded_benchmarks())

# label, own column, opponent column (None = single row), formatter
STAT_CATALOG = [
    ("Side-out %",            "sideout_pct",     "opp_sideout_pct",     "pct1"),
    ("Point-score %",         "point_score_pct", "opp_point_score_pct", "pct1"),
    ("First-ball side-out %", "fbso_pct",        "opp_fbso_pct",        "pct1"),
    ("Transition side-out %", "trans_so_pct",    None,                  "pct1"),
    ("Hitting efficiency",    "hit_pct",         "opp_hit_pct",         "dec3"),
    ("Kill % of attacks",     "kill_pct",        "opp_kill_pct",        "pct1"),
    ("Attack error rate",     "att_err_pct",     None,                  "pct1"),
    ("Blocks per set",        "blocks_per_set",  "opp_blocks_per_set",  "dec2"),
    ("Digs per set",          "digs_per_set",    "opp_digs_per_set",    "dec1"),
    ("Ace % of serves",       "ace_pct",         "opp_ace_pct",         "pct1"),
    ("Reception error rate",  "rec_err_pct",     "opp_rec_err_pct",     "pct1"),
    ("Rally win %",           "rally_win_pct",   None,                  "pct1"),
]
# rows where a LOWER value is better
LOWER_IS_BETTER = {"Attack error rate", "Reception error rate"}


def fmt(value, kind: str) -> str:
    if value is None or pd.isna(value):
        return "&mdash;"
    if kind == "pct1":
        return f"{value * 100:.1f}%"
    if kind == "dec3":
        return f"{value:.3f}"
    if kind == "dec2":
        return f"{value:.2f}"
    return f"{value:.1f}"


def team_picker(season: str, label: str, default: str | None, key: str) -> str:
    teams = sorted(D.team_seasons().query("season == @season").team.unique())
    idx = teams.index(default) if default in teams else 0
    return st.selectbox(label, teams, index=idx, key=key)


def season_frames(season: str, team: str):
    """(season averages, most recent match, opponent name) for one team."""
    tm = D.team_matches(season, team)
    if tm.empty:
        return None, None, None
    numeric = tm.select_dtypes("number").mean()
    last = tm.iloc[-1]
    return numeric, last, last.opponent


# ---------------------------------------------------------------- comparison
def page_comparison(season: str, home: str, away: str) -> None:
    st.markdown(f'<h1 class="app">Stat <span class="accent">Comparison</span></h1>',
                unsafe_allow_html=True)
    h_avg, h_last, h_opp = season_frames(season, home)
    a_avg, a_last, a_opp = season_frames(season, away)
    if h_avg is None or a_avg is None:
        st.info("No graded matches for one of these teams in this season.")
        return

    rows = []
    for label, own, opp_col, kind in STAT_CATALOG:
        variants = [("off", own)] + ([("def / allowed", opp_col)] if opp_col else [])
        for suffix, col in variants:
            if col not in h_avg.index or col not in a_avg.index:
                continue
            hs, as_ = h_avg[col], a_avg[col]
            row_label = f"{label} &mdash; {suffix}" if opp_col else label
            # "better" is judged on the season column
            lower_better = (label in LOWER_IS_BETTER) ^ (suffix == "def / allowed")
            if pd.isna(hs) or pd.isna(as_):
                h_better = a_better = False
            elif lower_better:
                h_better, a_better = hs < as_, as_ < hs
            else:
                h_better, a_better = hs > as_, as_ > hs
            rows.append((row_label, fmt(h_last.get(col), kind), fmt(hs, kind), h_better,
                         fmt(a_last.get(col), kind), fmt(as_, kind), a_better))

    html = ['<table class="cmp"><thead>',
            f'<tr><th></th><th class="grp" colspan="2">{T.chip(home)}</th>'
            f'<th class="grp sep" colspan="2">{T.chip(away)}</th></tr>',
            f'<tr><th class="lab">Stat</th><th class="sub">Last ({h_opp})</th>'
            f'<th class="sub">Season</th><th class="sub sep">Last ({a_opp})</th>'
            f'<th class="sub">Season</th></tr></thead><tbody>']
    for label, hl, hsv, hb, al, asv, ab in rows:
        hcls = "num better" if hb else "num"
        acls = "num better" if ab else "num"
        html.append(f'<tr><td class="lab">{label}</td><td class="num">{hl}</td>'
                    f'<td class="{hcls}">{hsv}</td><td class="num sep">{al}</td>'
                    f'<td class="{acls}">{asv}</td></tr>')
    html.append("</tbody></table>")
    st.markdown("".join(html), unsafe_allow_html=True)
    st.markdown('<p class="sublabel">Green = better of the two on the season. '
                'Offense rows favor the higher value; allowed rows favor the lower.</p>',
                unsafe_allow_html=True)


# ---------------------------------------------------------------- benchmarks
def page_benchmarks(season: str, home: str, away: str) -> None:
    st.markdown(f'<h1 class="app">The Volleyball <span class="accent">{GRADE_MAX}</span></h1>',
                unsafe_allow_html=True)
    st.markdown('<p class="sublabel">Seven benchmarks per match. Thresholds are the values '
                'that best separated winning from losing performances across 2021-2023, '
                'validated out of sample.</p>', unsafe_allow_html=True)

    frames = {t: season_frames(season, t) for t in (home, away)}
    if any(f[0] is None for f in frames.values()):
        st.info("No graded matches for one of these teams in this season.")
        return

    html = ['<table class="cmp"><thead>',
            f'<tr><th></th><th class="grp" colspan="2">{T.chip(home)}</th>'
            f'<th class="grp sep" colspan="2">{T.chip(away)}</th></tr>',
            f'<tr><th class="lab">Benchmark</th>'
            f'<th class="sub">Last ({frames[home][2]})</th><th class="sub">Season</th>'
            f'<th class="sub sep">Last ({frames[away][2]})</th>'
            f'<th class="sub">Season</th></tr></thead><tbody>']

    for b in D.graded_benchmarks():
        metric, flag = b["metric"], b["flag_column"]
        kind = "dec3" if "efficiency" in b["label"] or "margin" in metric else "pct1"
        if metric in ("ace_to_err",):
            kind = "dec2"
        cells = []
        for team in (home, away):
            avg, last, _ = frames[team]
            last_met = None if pd.isna(last.get(flag)) else bool(last[flag])
            cells.append(T.bench_pill(team, fmt(last.get(metric), kind), last_met))
            rate = avg.get(flag)
            cells.append(T.bench_pill(team, f"{rate * 100:.0f}%" if pd.notna(rate) else "",
                                      None if pd.isna(rate) else rate >= 0.5))
        html.append(f'<tr><td class="lab">{b["label"]}</td><td class="num">{cells[0]}</td>'
                    f'<td class="num">{cells[1]}</td><td class="num sep">{cells[2]}</td>'
                    f'<td class="num">{cells[3]}</td></tr>')

    totals = []
    for team in (home, away):
        avg, last, _ = frames[team]
        totals.append((f"{int(last.grade)} / {GRADE_MAX}", f"{avg.grade:.2f} / {GRADE_MAX}"))
    html.append(f'<tr><td class="lab"><b>Met (of {GRADE_MAX})</b></td>'
                f'<td class="num"><b>{totals[0][0]}</b></td><td class="num"><b>{totals[0][1]}</b></td>'
                f'<td class="num sep"><b>{totals[1][0]}</b></td>'
                f'<td class="num"><b>{totals[1][1]}</b></td></tr></tbody></table>')
    st.markdown("".join(html), unsafe_allow_html=True)
    st.markdown('<p class="sublabel">Last-match cells show the match value; season cells show '
                'the share of matches in which the team cleared that benchmark.</p>',
                unsafe_allow_html=True)


# ------------------------------------------------------------------ rankings
def page_rankings(season: str, home: str, away: str) -> None:
    st.markdown('<h1 class="app">Power <span class="accent">Rankings</span></h1>',
                unsafe_allow_html=True)
    c1, c2 = st.columns([2, 1])
    conf = c1.selectbox("Conference", ["All D1"] + D.conferences(season))
    min_m = c2.slider("Min matches", 5, 30, 10)

    r = D.rankings(season, None if conf == "All D1" else conf, min_m)
    if r.empty:
        st.info("No teams match that filter.")
        return
    st.markdown('<p class="sublabel">Opponent-adjusted side-out rating, in percentage points '
                'against an average D1 team. Offense is side-out ability; defense is '
                'suppressing the opponent&rsquo;s side-out. Ranks stay national when a '
                'conference is selected.</p>', unsafe_allow_html=True)

    html = ['<table class="grid"><thead><tr><th>Rank</th><th>Team</th><th>Record</th>'
            '<th>Conference</th><th style="text-align:right">Overall</th>'
            '<th style="text-align:right">Offense</th><th style="text-align:right">Defense</th>'
            f'<th style="text-align:right">Grade /{GRADE_MAX}</th></tr></thead><tbody>']
    for _, row in r.iterrows():
        hl = ' class="hl"' if row.team in (home, away) else ""
        rec = f"{int(row.wins)}-{int(row.losses)}" if pd.notna(row.wins) else "&mdash;"
        grade = f"{row.grade:.2f}" if pd.notna(row.grade) else "&mdash;"
        html.append(
            f'<tr{hl}><td class="n">{int(row.rank_overall)}</td><td>{T.chip(row.team, ".85rem")}</td>'
            f'<td>{rec}</td><td>{row.conference or ""}</td>'
            f'<td class="n">{row.rating_overall:+.1f}</td>'
            f'<td class="n">{row.rating_off:+.1f}</td>'
            f'<td class="n">{row.rating_def:+.1f}</td><td class="n">{grade}</td></tr>')
    html.append("</tbody></table>")
    st.markdown("".join(html), unsafe_allow_html=True)


# ---------------------------------------------------------------------- about
def page_about() -> None:
    meta = D.meta()
    st.markdown('<h1 class="app">How it <span class="accent">works</span></h1>',
                unsafe_allow_html=True)
    st.markdown(
        f"Each match is scored against **{GRADE_MAX} benchmarks**; the grade is how many were "
        "cleared. Thresholds are empirical, not chosen by feel: each is the value that best "
        "separated winning from losing performances across 2021-2023, constrained so that "
        "30-70% of team-matches clear it, then validated out of sample on 2024.")
    st.dataframe(pd.DataFrame(D.graded_benchmarks())[["label", "phase", "direction", "threshold"]]
                 .rename(columns={"label": "Benchmark", "phase": "Phase",
                                  "direction": "Direction", "threshold": "Threshold"}),
                 width='stretch', hide_index=True)

    st.subheader("Grade tracks season success")
    st.dataframe(pd.DataFrame([{"Season": k, "r (grade vs win%)": v}
                               for k, v in meta["grade_vs_win_pct_by_season"].items()]),
                 width='stretch', hide_index=True)
    st.markdown('<p class="sublabel">The grade is a description of how a team played, not a '
                'forecast of the next match. Ranking is done by the opponent-adjusted rating '
                'instead, because the grade is unadjusted and rewards a soft schedule.</p>',
                unsafe_allow_html=True)

    st.subheader("Context metrics — shown, never scored")
    st.markdown('<p class="sublabel">Real stats that fail as benchmarks: either algebraically '
                'redundant with a graded one, or too weak to carry equal weight in a count.</p>',
                unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(D.context_benchmarks())[["label", "phase"]]
                 .rename(columns={"label": "Metric", "phase": "Phase"}),
                 width='stretch', hide_index=True)

    st.subheader("Caveats")
    for c in meta["caveats"]:
        st.markdown(f"- {c}")
    st.caption(f"Built {meta['built_at']} · {meta['source']}")


# ------------------------------------------------------------------- shell
st.sidebar.markdown("### 🏐 QuesoHusker's Volleyball")
season = st.sidebar.selectbox("Season", D.seasons())
home = team_picker(season, "Team", "Nebraska", "home")
away = team_picker(season, "Opponent", "Wisconsin", "away")
st.sidebar.caption(f"NCAA women's D1 · {min(D.seasons())}-{max(D.seasons())} · "
                   f"{D.meta()['team_match_rows']:,} graded team-matches")

tabs = st.tabs(["Stat Comparison", f"The Volleyball {GRADE_MAX}", "Power Rankings", "How it works"])
with tabs[0]:
    page_comparison(season, home, away)
with tabs[1]:
    page_benchmarks(season, home, away)
with tabs[2]:
    page_rankings(season, home, away)
with tabs[3]:
    page_about()
