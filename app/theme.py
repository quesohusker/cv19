"""Design system for the volleyball app.

Values are lifted verbatim from cv19_design_system.html so this front end and the
CFB app stay visually identical: same dark surfaces, same Nebraska-red accent, same
chip and pill geometry, same tabular numerics.

Team colors are keyed to NCAA volleyball team names, which differ from the CFB
spelling ("Ohio St." not "Ohio State", "Southern California" not "USC"), so the CFB
dictionary is translated on the way in rather than duplicated by hand.
"""
from __future__ import annotations

# ---- surfaces -------------------------------------------------------------
BG = "#0e1117"
BG_PANEL = "#161a23"
BG_INPUT = "#262730"
BORDER = "rgba(128,128,128,0.22)"
BORDER_STRONG = "rgba(128,128,128,0.40)"
HOVER = "rgba(128,128,128,0.10)"

# ---- text -----------------------------------------------------------------
TEXT = "#fafafa"
MUTED = "#9aa0a6"
ROW_LABEL = "#c9ccd1"

# ---- accents --------------------------------------------------------------
ACCENT = "#e41c38"       # Nebraska red
GOOD = "#22c55e"         # better of two
HIT = "#16a34a"
MISS = "#dc2626"
NEUTRAL = ("#334155", "#94a3b8")

RADIUS_CHIP = "8px"
RADIUS_PILL = "6px"
FONT = ('"Source Sans Pro","Segoe UI",-apple-system,BlinkMacSystemFont,'
        "Roboto,Helvetica,Arial,sans-serif")

# ---- team colors ----------------------------------------------------------
# Ported from the CFB spec, then extended with the programs that matter in
# volleyball but not football. Extend freely -- one dictionary on purpose.
TEAM_COLORS: dict[str, tuple[str, str]] = {
    # Big Ten
    "Nebraska": ("#e41c38", "#f6f2e6"), "Ohio St.": ("#bb0000", "#666666"),
    "Michigan": ("#00274c", "#ffcb05"), "Penn St.": ("#041e42", "#ffffff"),
    "Michigan St.": ("#18453b", "#ffffff"), "Iowa": ("#111111", "#ffcd00"),
    "Wisconsin": ("#c5050c", "#ffffff"), "Minnesota": ("#7a0019", "#ffcc33"),
    "Illinois": ("#13294b", "#e84a27"), "Indiana": ("#990000", "#eeedeb"),
    "Purdue": ("#000000", "#ceb888"), "Northwestern": ("#4e2a84", "#ffffff"),
    "Maryland": ("#e21833", "#ffd520"), "Rutgers": ("#cc0033", "#111111"),
    "UCLA": ("#2d68c4", "#f2a900"), "Southern California": ("#990000", "#ffcc00"),
    "Oregon": ("#154733", "#fee123"), "Washington": ("#4b2e83", "#b7a57a"),
    # SEC
    "Alabama": ("#9e1b32", "#828a8f"), "Georgia": ("#ba0c2f", "#000000"),
    "Texas": ("#bf5700", "#ffffff"), "Oklahoma": ("#841617", "#fdf9d8"),
    "LSU": ("#461d7c", "#fdd023"), "Tennessee": ("#ff8200", "#ffffff"),
    "Florida": ("#0021a5", "#fa4616"), "Auburn": ("#0c2340", "#dd550c"),
    "Texas A&M": ("#500000", "#ffffff"), "Missouri": ("#f1b82d", "#000000"),
    "Kentucky": ("#0033a0", "#ffffff"), "Arkansas": ("#9d2235", "#ffffff"),
    "South Carolina": ("#73000a", "#000000"), "Ole Miss": ("#14213d", "#ce1126"),
    "Mississippi St.": ("#5d1725", "#ffffff"), "Vanderbilt": ("#866d4b", "#000000"),
    # ACC / Big 12 / independents
    "Pittsburgh": ("#003594", "#ffb81c"), "Louisville": ("#ad0000", "#000000"),
    "Stanford": ("#8c1515", "#ffffff"), "SMU": ("#0033a0", "#c8102e"),
    "Notre Dame": ("#0c2340", "#c99700"), "Clemson": ("#f56600", "#522d80"),
    "Miami (Fla.)": ("#f47321", "#005030"), "Florida St.": ("#782f40", "#ceb888"),
    "Georgia Tech": ("#b3a369", "#003057"), "North Carolina": ("#7bafd4", "#ffffff"),
    "NC State": ("#cc0000", "#000000"), "Virginia": ("#232d4b", "#f84c1e"),
    "Virginia Tech": ("#630031", "#cf4420"), "Duke": ("#003087", "#ffffff"),
    "Wake Forest": ("#9e7e38", "#000000"), "Syracuse": ("#f76900", "#000e54"),
    "Boston College": ("#98002e", "#bc9b6a"), "California": ("#003262", "#fdb515"),
    "Baylor": ("#154734", "#ffb81c"), "TCU": ("#4d1979", "#a3a9ac"),
    "Iowa St.": ("#c8102e", "#f1be48"), "Kansas": ("#0051ba", "#e8000d"),
    "Kansas St.": ("#512888", "#ffffff"), "Texas Tech": ("#cc0000", "#000000"),
    "Oklahoma St.": ("#ff7300", "#000000"), "BYU": ("#002e5d", "#ffffff"),
    "Utah": ("#cc0000", "#ffffff"), "Colorado": ("#000000", "#cfb87c"),
    "Arizona": ("#0c234b", "#cc0033"), "Arizona St.": ("#8c1d40", "#ffc627"),
    "Cincinnati": ("#e00122", "#000000"), "Houston": ("#c8102e", "#ffffff"),
    "West Virginia": ("#002855", "#eaaa00"), "UCF": ("#000000", "#bA9b37"),
    # volleyball-heavy mid-majors and others
    "Creighton": ("#00539b", "#ffffff"), "Marquette": ("#003366", "#ffcc00"),
    "Dayton": ("#c8102e", "#004b8d"), "San Diego": ("#003b70", "#75bee9"),
    "Hawaii": ("#024731", "#ffffff"), "Long Beach St.": ("#000000", "#febd11"),
    "Pepperdine": ("#00205b", "#f78d2d"), "UC Santa Barbara": ("#003660", "#febc11"),
    "Western Ky.": ("#c60c30", "#ffffff"), "UTEP": ("#ff8200", "#041e42"),
    "Northern Iowa": ("#4b116f", "#ffcc00"), "UNI": ("#4b116f", "#ffcc00"),
    "South Dakota St.": ("#0033a0", "#ffd100"), "Towson": ("#ffb500", "#000000"),
    "Hofstra": ("#f8c300", "#003591"), "American": ("#c41230", "#00609c"),
    "Rice": ("#00205b", "#c1c6c8"), "Loyola Marymount": ("#8a2432", "#0067a0"),
    "Washington St.": ("#981e32", "#5e6a71"), "Oregon St.": ("#dc4405", "#000000"),
    "Utah St.": ("#00263a", "#8a8d8f"), "Colorado St.": ("#1e4d2b", "#c8c372"),
    "Boise St.": ("#0033a0", "#d64309"), "Fresno St.": ("#db0032", "#002d62"),
    "San Diego St.": ("#a6192e", "#000000"), "UT Arlington": ("#0064b1", "#f58025"),
    "Florida A&M": ("#237c40", "#f88f2c"), "Tulane": ("#006747", "#418fde"),
    "Wright St.": ("#006a4d", "#000000"), "Lipscomb": ("#3b1e54", "#f2a900"),
    "Yale": ("#00356b", "#ffffff"), "Princeton": ("#ee7f2d", "#000000"),
}

# CFB spelling -> NCAA volleyball spelling, for anyone porting the football map.
CFB_NAME_ALIASES = {
    "Ohio State": "Ohio St.", "Penn State": "Penn St.",
    "Michigan State": "Michigan St.", "Florida State": "Florida St.",
    "Arizona State": "Arizona St.", "Iowa State": "Iowa St.",
    "Kansas State": "Kansas St.", "Oklahoma State": "Oklahoma St.",
    "Mississippi State": "Mississippi St.", "Boise State": "Boise St.",
    "USC": "Southern California", "Miami": "Miami (Fla.)",
}


def team_colors(team: str) -> tuple[str, str]:
    """Primary/secondary for a team, falling back to the neutral pill."""
    if team in TEAM_COLORS:
        return TEAM_COLORS[team]
    alias = CFB_NAME_ALIASES.get(team)
    if alias and alias in TEAM_COLORS:
        return TEAM_COLORS[alias]
    return NEUTRAL


def chip(team: str, size: str = ".95rem") -> str:
    """Team pill: primary background, always-white text, 2px inset ring of secondary."""
    primary, secondary = team_colors(team)
    return (f'<span style="display:inline-block;background:{primary};color:#fff;'
            f'padding:.15rem .6rem;border-radius:{RADIUS_CHIP};font-weight:700;'
            f'font-size:{size};white-space:nowrap;'
            f'box-shadow:inset 0 0 0 2px {secondary}55">{team}</span>')


def bench_pill(team: str, value: str, met: bool | None) -> str:
    """Benchmark cell: met -> team-color pill with a check; miss -> muted; missing -> em dash."""
    if met is None:
        return f'<span style="color:#6b7280">&mdash;</span>'
    if met:
        primary, _ = team_colors(team)
        return (f'<span style="background:{primary};color:#fff;padding:.05rem .4rem;'
                f'border-radius:{RADIUS_PILL};font-weight:700">&#10003; {value}</span>')
    return f'<span style="color:{MUTED};font-weight:600">{value}</span>'


CSS = f"""
<style>
  html, body, [class*="css"] {{ font-family: {FONT}; }}
  .block-container {{ padding-top: 2.2rem; }}
  h1.app {{ font-size:2rem; font-weight:800; margin:0 0 4px; }}
  h1.app .accent {{ color:{ACCENT}; }}
  .sublabel {{ color:{MUTED}; font-size:.85rem; margin:.2rem 0 1rem; }}
  table.cmp {{ border-collapse:collapse; width:100%; font-size:.85rem; margin-top:.3rem; }}
  table.cmp th, table.cmp td {{ padding:2px 8px; border-bottom:1px solid {BORDER}; }}
  table.cmp td.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
  table.cmp td.lab, table.cmp th.lab {{ text-align:left; white-space:nowrap; color:{ROW_LABEL}; }}
  table.cmp th.grp {{ text-align:center; padding-bottom:4px; }}
  table.cmp th.sub {{ text-align:right; color:{MUTED}; font-weight:600; font-size:.72rem; }}
  table.cmp .sep {{ border-left:2px solid {BORDER_STRONG}; }}
  table.cmp tbody tr:hover {{ background:{HOVER}; }}
  table.cmp td.better {{ font-weight:800; color:{GOOD}; }}
  table.grid {{ border-collapse:collapse; width:100%; font-size:.85rem; }}
  table.grid th {{ background:{BG_INPUT}; color:{ROW_LABEL}; text-align:left;
                   font-weight:600; padding:8px 10px; border-bottom:1px solid {BORDER}; }}
  table.grid td {{ padding:7px 10px; border-bottom:1px solid {BORDER}; }}
  table.grid td.n {{ text-align:right; font-variant-numeric:tabular-nums; }}
  table.grid tr:hover {{ background:{HOVER}; }}
  table.grid tr.hl {{ background:{ACCENT}22; }}
</style>
"""
