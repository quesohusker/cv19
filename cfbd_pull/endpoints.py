"""Registry of every CollegeFootballData.com (CFBD) API endpoint.

Paths and parameter names were extracted from the official ``cfbd`` Python SDK
(v5.24.2), which is generated from CFBD's OpenAPI spec -- so the paths and the
names of required parameters are accurate rather than guessed.

Each endpoint declares a *strategy*, which tells the planner how to enumerate
the calls needed to pull the endpoint exhaustively:

    STATIC       one call, no parameters (reference data)
    YEAR         one call per season
    YEAR_WEEK    one call per (season, season_type, week)
    YEAR_TEAM    one call per (season, team)
    GAME_ID      one call per game id, harvested from /games
    YEAR_PLAYER  one call per (season, player id), harvested from rosters
    COACH_ID     one call per coach id, harvested from /coaches
    DOWN_DIST    one call per (down, distance) -- a fixed static grid
    MANUAL       needs input that cannot be enumerated (e.g. a search term)
    LIVE         only meaningful during a live game
    META         account/diagnostic endpoints, not football data

``fallback`` names a finer-grained strategy to retry with if the API rejects
the coarse call with HTTP 400. Several CFBD endpoints accept ``year`` alone in
some cases but demand ``week`` or ``team`` in others; rather than hard-coding a
guess, the runner degrades automatically.

``tier`` controls how much gets pulled:
    core        reference data + season/team-level aggregates (cheap)
    full        core + per-week plays, drives and box scores (heavy)
    exhaustive  full + per-game and per-player detail (very heavy)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

BASE_URL = "https://api.collegefootballdata.com"

# Season types worth sweeping for week-partitioned endpoints. CFBD also defines
# "allstar", "spring_regular" and "spring_postseason", which carry almost no
# data; they are included only at the exhaustive tier.
SEASON_TYPES = ("regular", "postseason")
EXTRA_SEASON_TYPES = ("allstar", "spring_regular", "spring_postseason")

# Regular-season weeks run 1..15 in the modern era (week 0 exists since 2015).
# Postseason is a single bucket.
REGULAR_WEEKS = range(0, 17)
POSTSEASON_WEEKS = (1,)

STATIC = "STATIC"
YEAR = "YEAR"
YEAR_WEEK = "YEAR_WEEK"
YEAR_TEAM = "YEAR_TEAM"
GAME_ID = "GAME_ID"
YEAR_PLAYER = "YEAR_PLAYER"
COACH_ID = "COACH_ID"
DOWN_DIST = "DOWN_DIST"
MANUAL = "MANUAL"
LIVE = "LIVE"
META = "META"

CORE = "core"
FULL = "full"
EXHAUSTIVE = "exhaustive"

TIER_ORDER = {CORE: 0, FULL: 1, EXHAUSTIVE: 2}


@dataclass(frozen=True)
class Endpoint:
    """One CFBD REST endpoint and how to sweep it."""

    path: str
    group: str
    strategy: str
    tier: str = CORE
    fallback: Optional[str] = None
    #: Extra fixed query parameters sent on every call for this endpoint.
    fixed_params: Dict[str, object] = field(default_factory=dict)
    #: Seasons before this have no data; the planner skips them.
    min_year: Optional[int] = None
    notes: str = ""

    @property
    def slug(self) -> str:
        """Filesystem-safe name derived from the path."""
        return self.path.strip("/").replace("/", "__") or "root"


# --------------------------------------------------------------------------
# The registry: all 74 endpoints exposed by the CFBD API.
# --------------------------------------------------------------------------
ENDPOINTS: List[Endpoint] = [
    # -- reference / static -------------------------------------------------
    Endpoint("/venues", "venues", STATIC),
    Endpoint("/draft/positions", "draft", STATIC),
    Endpoint("/draft/teams", "draft", STATIC),
    Endpoint("/plays/types", "plays", STATIC),
    Endpoint("/plays/stats/types", "plays", STATIC),
    Endpoint("/stats/categories", "stats", STATIC),
    Endpoint("/metrics/fg/ep", "metrics", STATIC),
    Endpoint("/coaches/tenures", "coaches", STATIC),
    Endpoint("/recruiting/groups", "recruiting", STATIC),
    Endpoint(
        "/ppa/predicted",
        "metrics",
        DOWN_DIST,
        tier=FULL,
        notes="Static expected-points curve; 4 downs x 1..99 yards to go.",
    ),
    # -- teams / conferences ------------------------------------------------
    Endpoint("/teams", "teams", YEAR),
    Endpoint("/teams/fbs", "teams", YEAR),
    Endpoint("/conferences", "conferences", YEAR),
    Endpoint("/conferences/affiliations", "conferences", YEAR),
    Endpoint("/conferences/changes", "conferences", YEAR),
    Endpoint("/roster", "teams", YEAR, fallback=YEAR_TEAM),
    Endpoint("/talent", "teams", YEAR, min_year=2015),
    Endpoint("/teams/ats", "teams", YEAR, min_year=2013),
    Endpoint(
        "/teams/matchup",
        "teams",
        MANUAL,
        notes="Requires an explicit team1/team2 pair; not enumerable.",
    ),
    # -- coaches ------------------------------------------------------------
    Endpoint("/coaches", "coaches", YEAR),
    Endpoint("/coaches/seasons", "coaches", YEAR),
    Endpoint("/coaches/profile", "coaches", COACH_ID, tier=EXHAUSTIVE),
    # -- games --------------------------------------------------------------
    Endpoint("/games", "games", YEAR, fixed_params={"seasonType": "both"}),
    Endpoint("/calendar", "games", YEAR),
    Endpoint("/records", "games", YEAR),
    Endpoint("/games/media", "games", YEAR),
    Endpoint("/games/weather", "games", YEAR, fallback=YEAR_WEEK, min_year=2016),
    Endpoint("/games/teams", "games", YEAR_WEEK, tier=FULL),
    Endpoint("/games/players", "games", YEAR_WEEK, tier=FULL),
    Endpoint("/game/box/advanced", "games", GAME_ID, tier=EXHAUSTIVE),
    Endpoint(
        "/scoreboard",
        "games",
        LIVE,
        notes="Live scoreboard for the current week only.",
    ),
    # -- drives & plays -----------------------------------------------------
    Endpoint("/drives", "plays", YEAR, fallback=YEAR_WEEK, tier=FULL),
    Endpoint("/plays", "plays", YEAR_WEEK, tier=FULL),
    Endpoint(
        "/plays/stats",
        "plays",
        YEAR_WEEK,
        tier=FULL,
        notes="Server caps responses at 2000 records, so week granularity matters.",
    ),
    Endpoint("/live/plays", "plays", LIVE),
    # -- betting ------------------------------------------------------------
    Endpoint("/lines", "betting", YEAR, fallback=YEAR_WEEK, min_year=2013),
    # -- rankings / ratings -------------------------------------------------
    Endpoint("/rankings", "rankings", YEAR),
    Endpoint("/ratings/sp", "ratings", YEAR),
    Endpoint("/ratings/sp/conferences", "ratings", YEAR),
    Endpoint("/ratings/srs", "ratings", YEAR),
    Endpoint("/ratings/srs/expanded", "ratings", YEAR),
    Endpoint("/ratings/elo", "ratings", YEAR),
    Endpoint("/ratings/fpi", "ratings", YEAR, min_year=2005),
    Endpoint("/ratings/core", "ratings", YEAR),
    # -- team & player stats ------------------------------------------------
    Endpoint("/stats/season", "stats", YEAR),
    Endpoint("/stats/season/advanced", "stats", YEAR),
    Endpoint("/stats/game/advanced", "stats", YEAR),
    Endpoint("/stats/game/havoc", "stats", YEAR),
    Endpoint("/stats/player/season", "stats", YEAR),
    Endpoint("/stats/player/success", "stats", YEAR),
    Endpoint("/stats/player/success/game", "stats", YEAR, tier=FULL),
    # -- advanced metrics (PPA / WEPA) --------------------------------------
    Endpoint("/ppa/teams", "metrics", YEAR),
    Endpoint("/ppa/games", "metrics", YEAR),
    Endpoint("/ppa/players/season", "metrics", YEAR),
    Endpoint("/ppa/players/games", "metrics", YEAR, tier=FULL),
    Endpoint("/metrics/wp/pregame", "metrics", YEAR),
    Endpoint("/metrics/wp", "metrics", GAME_ID, tier=EXHAUSTIVE),
    Endpoint("/wepa/team/season", "metrics", YEAR),
    Endpoint("/wepa/players/passing", "metrics", YEAR),
    Endpoint("/wepa/players/rushing", "metrics", YEAR),
    Endpoint("/wepa/players/kicking", "metrics", YEAR),
    # -- players ------------------------------------------------------------
    Endpoint("/player/usage", "players", YEAR),
    Endpoint("/player/returning", "players", YEAR),
    Endpoint("/player/portal", "players", YEAR, min_year=2021),
    Endpoint("/player/season/overview", "players", YEAR_PLAYER, tier=EXHAUSTIVE),
    Endpoint(
        "/player/search",
        "players",
        MANUAL,
        notes="Requires a search term; not enumerable.",
    ),
    # -- recruiting & draft -------------------------------------------------
    Endpoint("/recruiting/players", "recruiting", YEAR, min_year=2000),
    Endpoint("/recruiting/teams", "recruiting", YEAR, min_year=2000),
    Endpoint("/draft/picks", "draft", YEAR, min_year=1967),
    # -- playoffs -----------------------------------------------------------
    Endpoint("/playoffs/cfp", "playoffs", YEAR, min_year=2014),
    Endpoint("/playoffs/cfp/participants", "playoffs", YEAR, min_year=2014),
    Endpoint("/playoffs/cfp/games", "playoffs", YEAR, min_year=2014),
    # -- account metadata ---------------------------------------------------
    Endpoint("/info", "info", META),
    Endpoint("/info/usage", "info", META),
]

BY_PATH: Dict[str, Endpoint] = {e.path: e for e in ENDPOINTS}
GROUPS = sorted({e.group for e in ENDPOINTS})


def select(
    tier: str = CORE,
    groups: Optional[List[str]] = None,
    paths: Optional[List[str]] = None,
    include_live: bool = False,
    include_meta: bool = False,
) -> List[Endpoint]:
    """Return the endpoints to sweep for the given filters."""
    if paths:
        wanted = set(paths)
        unknown = wanted - set(BY_PATH)
        if unknown:
            raise ValueError(f"unknown endpoint path(s): {sorted(unknown)}")
        return [BY_PATH[p] for p in paths]

    max_tier = TIER_ORDER[tier]
    out = []
    for e in ENDPOINTS:
        if groups and e.group not in groups:
            continue
        if e.strategy == MANUAL:
            continue
        if e.strategy == LIVE and not include_live:
            continue
        if e.strategy == META and not include_meta:
            continue
        if TIER_ORDER[e.tier] > max_tier:
            continue
        out.append(e)
    return out
