"""Convert NCAA play-by-play CSVs into a rally-level fact table.

The rally is volleyball's natural possession unit -- every rally starts with a serve
and ends with a point for exactly one team. Almost every team metric worth having
(sideout%, point-score%, first-ball sideout%, point-source mix, per-player passing
and serving value) is an aggregation over this one table.

PBP SCHEMA SEMANTICS (determined empirically -- these are not documented upstream
and one of them is genuinely counterintuitive):

  * Non-terminal events (Serve / Reception / Set / Attack / Dig): `team` is the acting
    team and `player` is the actor.

  * Terminal events: `team` is the team AWARDED THE POINT, not the acting team.
    `player` is still the acting player -- so on an error event, `player` belongs to
    the team that did NOT get the point. Reading `team` as "the team that did this"
    inverts every error, roughly a quarter of all rallies.

    Validated on the 2024 women's D1 season by cross-checking the terminal event's
    `team` against the independent score-column progression: 705,496 agreements,
    1 disagreement.

  * `score` is "away-home" and updates on the terminal event row. Orientation was
    checked per-match across 5,117 matches; it is consistent.

Coverage on that same season: 5,117 of ~5,145 matches (99.5%), 815,095 rallies,
0.18% malformed rows (a parser artifact upstream where substitution/timeout text
lands in the `event` column -- those rows are skipped).

Compression matters for anything that has to serve a web app: 642 MB of raw pbp CSV
becomes a 7.0 MB zstd parquet rally table (92x), in ~23s.
"""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

# Events that end a rally and award a point. On these rows, `team` == rally winner.
TERMINAL_EVENTS = frozenset({
    "Kill", "First ball kill", "Ace", "Block", "Attack error", "Service error",
    "Set error", "Ball handling error", "Block error", "Dig error", "Sanction point",
})

# Everything the upstream parser produces that we recognize. Anything else is an
# upstream parsing artifact (substitution/timeout text spilled into `event`).
KNOWN_EVENTS = TERMINAL_EVENTS | {
    "Serve", "Reception", "Set", "Attack", "Dig", "Challenge request", "Sanction",
}

RALLY_FIELDS = (
    "date", "away_team", "home_team", "set_no", "rally_no",
    "serve_team", "recv_team", "winner", "server", "passer",
    "end_event", "end_player", "first_ball", "touches",
    "score_away", "score_home",
)


def _score(raw: str) -> tuple[int | None, int | None]:
    try:
        away, home = raw.split("-")
        return int(away), int(home)
    except (ValueError, AttributeError):
        return None, None


def extract_rallies(pbp_path: Path) -> dict[str, list]:
    """Walk a pbp CSV once and emit one record per completed rally."""
    cols: dict[str, list] = {name: [] for name in RALLY_FIELDS}
    stats = {"rows": 0, "malformed": 0, "abandoned": 0}

    rally = None
    rally_no = 0
    prev_set_key = None

    with open(pbp_path, newline="") as f:
        for row in csv.DictReader(f):
            stats["rows"] += 1
            event = row["event"]
            if event not in KNOWN_EVENTS:
                stats["malformed"] += 1
                continue

            away, home = row["away_team"], row["home_team"]
            set_key = (row["date"], away, home, row["set"])
            if set_key != prev_set_key:
                rally_no = 0
                prev_set_key = set_key

            if event == "Serve":
                if rally is not None:
                    stats["abandoned"] += 1
                serve_team = row["team"]
                if serve_team not in (away, home):
                    rally = None
                    continue
                rally_no += 1
                score_away, score_home = _score(row["score"])
                rally = {
                    "date": row["date"], "away_team": away, "home_team": home,
                    "set_no": row["set"], "rally_no": rally_no,
                    "serve_team": serve_team,
                    "recv_team": home if serve_team == away else away,
                    "server": row["player"], "passer": None,
                    "first_ball": False, "touches": 1,
                    "score_away": score_away, "score_home": score_home,
                }
                continue

            if rally is None or set_key != (
                rally["date"], rally["away_team"], rally["home_team"], rally["set_no"]
            ):
                continue

            rally["touches"] += 1
            if event == "Reception" and rally["passer"] is None:
                rally["passer"] = row["player"]
            elif event == "First ball kill":
                rally["first_ball"] = True

            if event in TERMINAL_EVENTS:
                winner = row["team"]  # see module docstring: this is the point winner
                if winner in (away, home):
                    rally["winner"] = winner
                    rally["end_event"] = event
                    rally["end_player"] = row["player"]
                    for name in RALLY_FIELDS:
                        cols[name].append(rally.get(name))
                rally = None

    return cols, stats


def to_parquet(cols: dict[str, list], dest: Path) -> pa.Table:
    """Dictionary-encode the high-cardinality string columns and write zstd parquet."""
    def dict_col(name):
        return pa.array(cols[name]).dictionary_encode()

    table = pa.table({
        "date": pa.array(cols["date"]),
        "away_team": dict_col("away_team"),
        "home_team": dict_col("home_team"),
        "set_no": pa.array(
            [int(x) if str(x).isdigit() else None for x in cols["set_no"]], pa.int8()
        ),
        "rally_no": pa.array(cols["rally_no"], pa.int16()),
        "serve_team": dict_col("serve_team"),
        "recv_team": dict_col("recv_team"),
        "winner": dict_col("winner"),
        "server": dict_col("server"),
        "passer": dict_col("passer"),
        "end_event": dict_col("end_event"),
        "end_player": dict_col("end_player"),
        "first_ball": pa.array(cols["first_ball"], pa.bool_()),
        "touches": pa.array(cols["touches"], pa.int16()),
        "score_away": pa.array(cols["score_away"], pa.int16()),
        "score_home": pa.array(cols["score_home"], pa.int16()),
    })
    dest.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, dest, compression="zstd")
    return table


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pbp_files", nargs="+", type=Path, help="pbp CSVs to convert")
    parser.add_argument("--out-dir", type=Path, default=Path("data/rallies"))
    args = parser.parse_args()

    for src in args.pbp_files:
        started = time.time()
        cols, stats = extract_rallies(src)
        dest = args.out_dir / (src.stem.replace("_pbp_", "_rallies_") + ".parquet")
        table = to_parquet(cols, dest)
        src_mb = src.stat().st_size / 1e6
        out_mb = dest.stat().st_size / 1e6
        print(
            f"{src.name}: {stats['rows']:,} rows -> {table.num_rows:,} rallies | "
            f"{src_mb:,.0f}MB -> {out_mb:,.1f}MB ({src_mb / out_mb:.0f}x) | "
            f"{stats['malformed']:,} malformed, {stats['abandoned']:,} abandoned | "
            f"{time.time() - started:.0f}s"
        )


if __name__ == "__main__":
    main()
