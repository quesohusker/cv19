"""Orchestration: plan the sweep, execute it, record what happened."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from . import endpoints as ep
from . import planner
from .client import BadRequest, CFBDClient, CFBDError, NotFound
from .store import Store, count_rows

log = logging.getLogger(__name__)


@dataclass
class Summary:
    """Tallies for the end-of-run report."""

    ok: int = 0
    empty: int = 0
    skipped: int = 0
    failed: int = 0
    rows: int = 0
    started: float = field(default_factory=time.time)
    errors: List[str] = field(default_factory=list)

    @property
    def elapsed(self) -> float:
        return time.time() - self.started

    def render(self, client: Optional[CFBDClient] = None) -> str:
        mins = self.elapsed / 60.0
        lines = [
            "",
            "=" * 62,
            f"  pulled   {self.ok:>8,} call(s)   {self.rows:,} rows",
            f"  empty    {self.empty:>8,}",
            f"  skipped  {self.skipped:>8,}  (already in the manifest)",
            f"  failed   {self.failed:>8,}",
            f"  elapsed  {mins:>8.1f} min",
        ]
        if client:
            mb = client.bytes_in / 1_048_576
            lines.append(f"  api      {client.calls:>8,} requests, {mb:,.1f} MB")
        if self.errors:
            lines.append("")
            lines.append(f"  first {min(len(self.errors), 10)} error(s):")
            for msg in self.errors[:10]:
                lines.append(f"    - {msg}")
        lines.append("=" * 62)
        return "\n".join(lines)


class Runner:
    """Executes a planned sweep against the API."""

    def __init__(
        self,
        client: CFBDClient,
        store: Store,
        *,
        years: Sequence[int],
        dry_run: bool = False,
        stop_on_error: bool = False,
        extra_season_types: bool = False,
    ) -> None:
        self.client = client
        self.store = store
        self.years = list(years)
        self.dry_run = dry_run
        self.stop_on_error = stop_on_error
        self.extra_season_types = extra_season_types
        self.summary = Summary()
        #: Endpoints that answered 400 and were re-planned more finely.
        self._degraded: Dict[str, str] = {}

    # -- planning ----------------------------------------------------------
    def plan(self, selected: Sequence[ep.Endpoint]):
        """Plan phase 1.

        Returns ``(tasks, dependent_endpoints)`` -- the id-keyed endpoints are
        handed back unplanned because their inputs do not exist on disk yet.
        """
        independent, dependent = planner.split_phases(selected)

        tasks = []
        for endpoint in independent:
            tasks.extend(self._plan_one(endpoint))
        return planner.prioritise(tasks), dependent

    def _plan_one(self, endpoint: ep.Endpoint, teams=None) -> List[planner.Task]:
        """Plan one endpoint, honouring any strategy a previous run was forced onto."""
        strategy = self.store.degraded.get(endpoint.path)
        if strategy:
            self._degraded[endpoint.path] = strategy
            log.debug("%s: using remembered strategy %s", endpoint.path, strategy)
            if strategy == ep.YEAR_TEAM and teams is None:
                teams = planner.harvest_teams(self.store, self.years)
        return planner.plan_endpoint(
            endpoint,
            self.years,
            strategy=strategy,
            store=self.store,
            teams=teams,
            extra_season_types=self.extra_season_types,
        )

    def plan_dependent(self, dependent: Sequence[ep.Endpoint]) -> List[planner.Task]:
        """Plan id-keyed endpoints once their source data is on disk."""
        teams = planner.harvest_teams(self.store, self.years)
        tasks = []
        for endpoint in dependent:
            tasks.extend(self._plan_one(endpoint, teams=teams))
        return tasks

    # -- execution ---------------------------------------------------------
    def run(self, tasks: Sequence[planner.Task]) -> None:
        total = len(tasks)
        queue = list(tasks)
        index = 0

        while index < len(queue):
            task = queue[index]
            index += 1
            key = task.key

            if self.store.is_done(key):
                self.summary.skipped += 1
                continue

            if self.dry_run:
                print(f"  would GET {key}")
                self.summary.ok += 1
                continue

            if index % 25 == 0 or index == 1:
                log.info("[%d/%d] %s", index, len(queue), key)

            try:
                payload = self.client.get(task.endpoint.path, task.params)
            except BadRequest as exc:
                replacement = self._handle_bad_request(task, exc)
                if replacement:
                    queue.extend(replacement)
                continue
            except NotFound:
                # A game/player id that no longer resolves is not a failure.
                self.store.record(key, "empty", reason="404")
                self.summary.empty += 1
                continue
            except CFBDError as exc:
                self._fail(key, exc)
                if self.stop_on_error:
                    raise
                continue

            rows = count_rows(payload)
            if rows == 0:
                self.store.record(key, "empty", rows=0)
                self.summary.empty += 1
                continue

            path = self.store.write(task.endpoint.slug, task.params, payload)
            self.store.record(key, "ok", rows=rows, path=path)
            self.summary.ok += 1
            self.summary.rows += rows

        log.debug("planned %d, executed queue of %d", total, len(queue))

    # -- error handling ----------------------------------------------------
    def _handle_bad_request(
        self, task: planner.Task, exc: BadRequest
    ) -> List[planner.Task]:
        """Re-plan an endpoint at finer granularity after an HTTP 400.

        Several CFBD endpoints accept ``year`` alone for some queries but
        require ``week`` or ``team`` for others. Rather than hard-coding a
        guess, degrade to the declared fallback strategy the first time the
        API objects, then re-plan that endpoint's remaining work.
        """
        endpoint = task.endpoint
        path = endpoint.path

        if not endpoint.fallback or path in self._degraded:
            self._fail(task.key, exc)
            return []

        self._degraded[path] = endpoint.fallback
        # Remember that the coarse call is a dead end so a resumed run does not
        # spend quota rediscovering it.
        self.store.record(
            task.key,
            "skipped",
            endpoint=path,
            degraded_to=endpoint.fallback,
        )
        log.warning(
            "%s rejected %s; re-planning with strategy %s",
            path,
            task.params,
            endpoint.fallback,
        )
        teams = (
            planner.harvest_teams(self.store, self.years)
            if endpoint.fallback == ep.YEAR_TEAM
            else None
        )
        return planner.plan_endpoint(
            endpoint,
            self.years,
            strategy=endpoint.fallback,
            store=self.store,
            teams=teams,
            extra_season_types=self.extra_season_types,
        )

    def _fail(self, key: str, exc: Exception) -> None:
        msg = f"{key}: {exc}"
        log.error("%s", msg)
        self.store.record(key, "error", error=str(exc)[:500])
        self.summary.failed += 1
        self.summary.errors.append(msg)
