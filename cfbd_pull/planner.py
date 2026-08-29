"""Expansion of endpoints into concrete API calls.

The planner turns each :class:`~cfbd_pull.endpoints.Endpoint` into the list of
parameter combinations needed to pull it exhaustively. Some endpoints are keyed
by identifiers that must first be harvested from other endpoints (game ids,
player ids, coach ids), so planning happens in two phases:

    1. Endpoints that need no harvested input.
    2. Endpoints keyed by ids, planned once phase 1 has populated the store.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from . import endpoints as ep
from .store import Store, task_key

log = logging.getLogger(__name__)

#: Endpoint parameter names differ from the tidy names used internally. CFBD
#: query parameters are camelCase.
PARAM_ALIASES = {
    "season_type": "seasonType",
    "game_id": "gameId",
    "player_id": "playerId",
    "coach_id": "coachId",
    "team": "team",
    "year": "year",
    "week": "week",
    "down": "down",
    "distance": "distance",
    "id": "id",
}


@dataclass
class Task:
    """One planned API call."""

    endpoint: ep.Endpoint
    params: Dict[str, Any]

    @property
    def key(self) -> str:
        return task_key(self.endpoint.path, self.params)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Task {self.key}>"


def _wire(params: Dict[str, Any]) -> Dict[str, Any]:
    """Translate internal parameter names to CFBD's camelCase query names."""
    return {PARAM_ALIASES.get(k, k): v for k, v in params.items()}


def _years_for(endpoint: ep.Endpoint, years: Sequence[int]) -> List[int]:
    if endpoint.min_year is None:
        return list(years)
    return [y for y in years if y >= endpoint.min_year]


def plan_endpoint(
    endpoint: ep.Endpoint,
    years: Sequence[int],
    *,
    strategy: Optional[str] = None,
    store: Optional[Store] = None,
    teams: Optional[Sequence[str]] = None,
    extra_season_types: bool = False,
) -> List[Task]:
    """Expand one endpoint into the calls needed to sweep it.

    ``strategy`` overrides the endpoint's declared strategy -- the runner uses
    this to re-plan at finer granularity after an HTTP 400.
    """
    strat = strategy or endpoint.strategy
    fixed = dict(endpoint.fixed_params)
    tasks: List[Task] = []
    yrs = _years_for(endpoint, years)

    if strat in (ep.STATIC, ep.META, ep.LIVE):
        tasks.append(Task(endpoint, dict(fixed)))

    elif strat == ep.YEAR:
        for year in yrs:
            tasks.append(Task(endpoint, {**fixed, "year": year}))

    elif strat == ep.YEAR_WEEK:
        season_types = list(ep.SEASON_TYPES)
        if extra_season_types:
            season_types += list(ep.EXTRA_SEASON_TYPES)
        for year in yrs:
            for stype in season_types:
                weeks = (
                    ep.REGULAR_WEEKS
                    if stype in ("regular", "spring_regular")
                    else ep.POSTSEASON_WEEKS
                )
                for week in weeks:
                    params = {**fixed, "year": year, "week": week}
                    params["seasonType"] = stype
                    tasks.append(Task(endpoint, params))

    elif strat == ep.YEAR_TEAM:
        if not teams:
            log.warning("%s needs a team list; skipping", endpoint.path)
            return []
        for year in yrs:
            for team in teams:
                tasks.append(Task(endpoint, {**fixed, "year": year, "team": team}))

    elif strat == ep.DOWN_DIST:
        for down in range(1, 5):
            for distance in range(1, 100):
                tasks.append(Task(endpoint, {**fixed, "down": down, "distance": distance}))

    elif strat == ep.GAME_ID:
        if store is None:
            return []
        param = "id" if endpoint.path == "/game/box/advanced" else "gameId"
        for game_id in harvest_game_ids(store, yrs):
            tasks.append(Task(endpoint, {**fixed, param: game_id}))

    elif strat == ep.YEAR_PLAYER:
        if store is None:
            return []
        for year, player_id in harvest_player_ids(store, yrs):
            tasks.append(Task(endpoint, {**fixed, "year": year, "playerId": player_id}))

    elif strat == ep.COACH_ID:
        if store is None:
            return []
        for coach_id in harvest_coach_ids(store):
            tasks.append(Task(endpoint, {**fixed, "coachId": coach_id}))

    elif strat == ep.MANUAL:
        return []

    else:  # pragma: no cover - registry guarantees coverage
        raise ValueError(f"unknown strategy {strat!r} for {endpoint.path}")

    return tasks


# --------------------------------------------------------------------------
# Harvesting identifiers from already-downloaded payloads
# --------------------------------------------------------------------------
def harvest_game_ids(store: Store, years: Sequence[int]) -> List[int]:
    """Collect game ids from previously pulled /games responses."""
    wanted = set(years)
    ids = set()
    for row in store.iter_rows(ep.BY_PATH["/games"].slug):
        gid = row.get("id")
        season = row.get("season") or row.get("year")
        if gid is None:
            continue
        if season is not None and wanted and season not in wanted:
            continue
        ids.add(gid)
    if not ids:
        log.warning("no game ids found -- pull /games first")
    return sorted(ids)


def harvest_player_ids(store: Store, years: Sequence[int]) -> List[tuple]:
    """Collect (season, player id) pairs from stored rosters."""
    wanted = set(years)
    pairs = set()
    for row in store.iter_rows(ep.BY_PATH["/roster"].slug):
        pid = row.get("id") or row.get("athleteId")
        season = row.get("year") or row.get("season")
        if pid is None or season is None:
            continue
        if wanted and season not in wanted:
            continue
        pairs.add((season, pid))
    if not pairs:
        log.warning("no player ids found -- pull /roster first")
    return sorted(pairs)


def harvest_coach_ids(store: Store) -> List[int]:
    """Collect coach ids from stored /coaches responses."""
    ids = set()
    for row in store.iter_rows(ep.BY_PATH["/coaches"].slug):
        cid = row.get("id") or row.get("coachId")
        if cid is not None:
            ids.add(cid)
    if not ids:
        log.warning("no coach ids found -- pull /coaches first")
    return sorted(ids)


def harvest_teams(store: Store, years: Sequence[int]) -> List[str]:
    """Collect distinct team names from stored /teams responses."""
    names = set()
    for row in store.iter_rows(ep.BY_PATH["/teams"].slug):
        name = row.get("school")
        if name:
            names.add(name)
    return sorted(names)


#: Endpoints whose planning depends on data harvested from other endpoints.
DEPENDENT_STRATEGIES = {ep.GAME_ID, ep.YEAR_PLAYER, ep.COACH_ID, ep.YEAR_TEAM}


def split_phases(selected: Iterable[ep.Endpoint]):
    """Split endpoints into (independent, dependent) planning phases."""
    independent, dependent = [], []
    for e in selected:
        (dependent if e.strategy in DEPENDENT_STRATEGIES else independent).append(e)
    return independent, dependent


def prioritise(tasks: List[Task]) -> List[Task]:
    """Pull the endpoints other endpoints depend on first."""
    seed = {"/games", "/teams", "/roster", "/coaches"}
    return sorted(tasks, key=lambda t: (t.endpoint.path not in seed, t.endpoint.path))
