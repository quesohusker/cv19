"""Detect whether a volleyball attack was run "in system", from play-by-play alone.

DEFINITION USED
---------------
An attack is in system when the team's DESIGNATED SETTER took the second ball --
that is, the player on the `Set` event preceding the attack has roster position "S".
When the pass or dig is bad, the setter usually cannot reach the ball and a libero,
DS or outside hits it instead; that is exactly the out-of-system state.

The natural extra condition -- "and the ball went to an OH or MB" -- was tested and
dropped. About 95% of all attacks already go to a primary attacker (OH/MB/RS/OPP),
so the condition is nearly always true and adds noise rather than signal. All of the
information is in WHO SET the ball.

Requires joining pbp player names to the player-season roster for positions. Names
are formatted inconsistently across schools ("Halle Schroder", "HERRON, Keira",
"Rachow,Zoe"), so `normalize_name` handles the "Last, First" variants; measured
join coverage on 2024 women's D1 is 99.8% of 1.3M attack attempts.

WHAT IT SHOWS (2024 women's D1, 1,305,241 attack attempts)
----------------------------------------------------------
The effect on an individual attack is large and unambiguous:

    phase        setter set it     someone else set it     gap
    first ball   37.2% kill        27.6% kill              +9.6 pts
                 .217 efficiency   .123 efficiency         +.094
    transition   34.9% kill        26.3% kill              +8.6 pts
                 .203 efficiency   .109 efficiency         +.094

Middle usage is the cleanest visible tell: 28.6% of in-system first-ball attacks go
to a middle, against 8.1% out of system. If the middle is being used, the pass was
good. Middles also finish best of any position (40.3% kill, .262 efficiency).

THE POSSESSION-LEVEL VARIANT (also tested, also rejected)
--------------------------------------------------------
Measuring in-system as a share of POSSESSIONS rather than of attacks is the better
construction, and worth recording because it fixes a real flaw. The attack-level rate
conditions on an attack having happened, so possessions that produced no attack at
all -- aces, reception errors, overpasses -- silently leave the denominator. Putting
them back in gives "of all serve-receive possessions, how many produced a designated
setter -> hitter attack".

That change fixes the sign. The attack-level rate correlates NEGATIVELY with winning
and shows negative benchmark lift; the possession rate correlates +0.130 with winning,
+0.296 with first-ball side-out%, -0.361 with reception error rate, and carries
positive lift (+13 to +22 depending on threshold).

It still does not earn a place in the graded set:

  * League mean is 67.4%, not 80%. Across 2024 D1, ZERO of 340 teams averaged 80%,
    and the 95th percentile is 73.6%. An 80% bar is cleared in 6.3% of team-matches --
    a blowout flag, not a standard.
  * Adding it at any threshold LOWERS set AUC (0.9623 -> 0.9572-0.9615).
  * It is the weakest forward predictor measured in this project: first-half
    possession rate predicts second-half win% at r=+0.155 (r2=0.024), against +0.487
    for raw win-loss record and +0.509 for side-out%.
  * Between-team spread is still small: CV 11.0%, versus 21.9% for hitting efficiency.

Split-half reliability is again high (+0.769), reinforcing the same conclusion as the
attack-level version: system rate is a real and stable team property that does not
vary enough between D1 teams to grade on.

The general lesson, visible across every ball-control metric tested here: at D1 level
getting in system is close to table stakes (67-83% for nearly everyone, CV 3-11%),
while what a team DOES with an in-system ball varies far more (hitting efficiency
CV 21.9%). Terminating separates teams; passing mostly does not.

WHY IT IS NOT A TEAM BENCHMARK
------------------------------
The effect is large but the BETWEEN-TEAM VARIATION is not. Every D1 team runs in
system at nearly the same rate: league mean 83.4% on first ball, 5th-95th percentile
only 77.9% to 88.2% (CV 10.0%, against 21.8% for hitting efficiency). Multiplying
that 10.3-point spread by the 6.1-point kill gap, the difference between a 95th- and
5th-percentile team is about 0.62 points of kill% across a season.

Accordingly it fails as a benchmark: negative lift at every threshold tried, and
adding it to the graded set lowers AUC (0.9630 -> 0.9562 at the best cut).

It is, however, one of the most STABLE team traits measured here -- split-half
reliability r=+0.822, higher than hitting efficiency (+0.613) or side-out% (+0.663).
So it is a real, repeatable property of a team that simply does not vary enough
between D1 teams to decide matches. Use it for player-level work (which passers keep
the offense in system, how a setter performs in and out of system) and for match
diagnosis, not for grading or ranking teams.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import pandas as pd

TERMINAL_EVENTS = frozenset({
    "Kill", "First ball kill", "Ace", "Block", "Attack error", "Service error",
    "Set error", "Ball handling error", "Block error", "Dig error", "Sanction point",
})
SETTER_POSITIONS = frozenset({"S"})
PRIMARY_ATTACKERS = frozenset({"OH", "MB", "MH", "RS", "OPP"})


def normalize_name(name: str) -> str:
    """Fold the inconsistent pbp/roster name formats onto one key."""
    if not name:
        return ""
    n = name.strip()
    if "," in n:  # "HERRON, Keira" / "Rachow,Zoe" -> "Keira HERRON"
        parts = [p.strip() for p in n.split(",", 1)]
        if len(parts) == 2 and parts[1]:
            n = f"{parts[1]} {parts[0]}"
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z ]", " ", n)).strip().upper()


def load_positions(playerseason_csv: Path) -> dict[tuple[str, str], str]:
    """(team, normalized player name) -> roster position."""
    with open(playerseason_csv, newline="") as f:
        return {
            (r["Team"], normalize_name(r["Player"])): r["Pos"]
            for r in csv.DictReader(f)
        }


def extract_attacks(pbp_csv: Path, positions: dict[tuple[str, str], str]) -> pd.DataFrame:
    """One row per attack attempt: setter, attacker, positions, phase, outcome.

    Phase is "first_ball" after a Reception and "transition" after a Dig, so an
    attack can be judged against the right baseline -- transition kill rates are
    lower in both system states.
    """
    rows: list[dict] = []
    rally = None
    pending_set = None
    phase = None

    with open(pbp_csv, newline="") as f:
        for row in csv.DictReader(f):
            event, team = row["event"], row["team"]
            away, home = row["away_team"], row["home_team"]
            if team not in (away, home):
                continue

            if event == "Serve":
                rally = (row["date"], away, home, row["set"])
                pending_set, phase = None, "first_ball"
                continue
            if rally is None:
                continue

            if event == "Reception":
                phase = "first_ball"
            elif event == "Dig":
                phase = "transition"
            elif event == "Set":
                pending_set = (team, row["player"])
                continue
            elif event == "Attack":
                setter = pending_set[1] if (pending_set and pending_set[0] == team) else None
                rows.append({
                    "date": rally[0], "away_team": rally[1], "home_team": rally[2],
                    "set_no": rally[3], "team": team, "phase": phase,
                    "setter": setter, "attacker": row["player"],
                    "set_pos": positions.get((team, normalize_name(setter))) if setter else None,
                    "att_pos": positions.get((team, normalize_name(row["player"]))),
                    "outcome": "in_play",
                })
                pending_set = None
                continue

            # resolve the attack that was just left hanging
            if rows and rows[-1]["outcome"] == "in_play":
                if event in ("Kill", "First ball kill") and rows[-1]["team"] == team:
                    rows[-1]["outcome"] = "kill"
                elif event == "Attack error":
                    rows[-1]["outcome"] = "error"
                elif event == "Block":
                    rows[-1]["outcome"] = "blocked"
            if event in TERMINAL_EVENTS:
                rally, pending_set = None, None

    df = pd.DataFrame(rows)
    df["in_system"] = df.set_pos.isin(SETTER_POSITIONS)
    df["to_primary"] = df.att_pos.isin(PRIMARY_ATTACKERS)
    df["kill"] = (df.outcome == "kill").astype(int)
    df["hit_eff"] = df.kill - df.outcome.isin(["error", "blocked"]).astype(int)
    return df


def team_match_rates(attacks: pd.DataFrame) -> pd.DataFrame:
    """In-system rate per team per match, split by phase. Diagnostic, not a benchmark."""
    keys = ["date", "away_team", "home_team", "team"]
    out = attacks.groupby(keys).agg(
        attacks=("kill", "size"),
        in_system_rate=("in_system", "mean"),
        middle_share=("att_pos", lambda s: s.isin(["MB", "MH"]).mean()),
        kill_rate=("kill", "mean"),
    ).reset_index()
    first_ball = (attacks[attacks.phase == "first_ball"]
                  .groupby(keys).in_system.mean().rename("fb_in_system_rate").reset_index())
    return out.merge(first_ball, on=keys, how="left")
