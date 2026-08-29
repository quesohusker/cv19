"""Offline tests -- no network required.

Run with:  python -m cfbd_pull.tests.test_offline
      or:  pytest cfbd_pull/tests/test_offline.py
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from cfbd_pull import endpoints as ep
from cfbd_pull.cli import parse_years
from cfbd_pull.client import BadRequest
from cfbd_pull.runner import Runner
from cfbd_pull.store import Store, file_stem, partition_of


class FakeClient:
    """Stand-in for CFBDClient that never touches the network."""

    def __init__(self, die_after=None, reject_coarse=()):
        self.n = 0
        self.calls = 0
        self.retries = 0
        self.bytes_in = 0
        self.die_after = die_after
        self.reject_coarse = set(reject_coarse)
        self.seen = []

    def get(self, path, params=None):
        params = params or {}
        self.n += 1
        self.calls += 1
        self.seen.append((path, dict(params)))
        if self.die_after and self.n > self.die_after:
            raise KeyboardInterrupt
        if path in self.reject_coarse and "week" not in params:
            raise BadRequest("400: week required")
        if path == "/games":
            return [
                {"id": 400 + i, "season": params.get("year"), "homeTeam": "Nebraska"}
                for i in range(3)
            ]
        return [{"path": path, **params}]


class TempStoreCase(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp(prefix="cfbd-test-")

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)


class TestRegistry(unittest.TestCase):
    def test_all_endpoints_present(self):
        self.assertEqual(len(ep.ENDPOINTS), 74)

    def test_paths_unique(self):
        paths = [e.path for e in ep.ENDPOINTS]
        self.assertEqual(len(paths), len(set(paths)))

    def test_every_strategy_is_known(self):
        known = {
            ep.STATIC, ep.YEAR, ep.YEAR_WEEK, ep.YEAR_TEAM, ep.GAME_ID,
            ep.YEAR_PLAYER, ep.COACH_ID, ep.DOWN_DIST, ep.MANUAL, ep.LIVE, ep.META,
        }
        for e in ep.ENDPOINTS:
            self.assertIn(e.strategy, known, e.path)
            self.assertIn(e.tier, ep.TIER_ORDER, e.path)

    def test_slugs_unique_and_safe(self):
        slugs = [e.slug for e in ep.ENDPOINTS]
        self.assertEqual(len(slugs), len(set(slugs)))
        for s in slugs:
            self.assertNotIn("/", s)

    def test_tiers_are_cumulative(self):
        core = len(ep.select(ep.CORE))
        full = len(ep.select(ep.FULL))
        exhaustive = len(ep.select(ep.EXHAUSTIVE))
        self.assertLess(core, full)
        self.assertLess(full, exhaustive)

    def test_manual_endpoints_never_selected(self):
        for e in ep.select(ep.EXHAUSTIVE):
            self.assertNotEqual(e.strategy, ep.MANUAL)


class TestYearParsing(unittest.TestCase):
    def test_single(self):
        self.assertEqual(parse_years("2024"), [2024])

    def test_range(self):
        self.assertEqual(parse_years("2020-2023"), [2020, 2021, 2022, 2023])

    def test_mixed_and_deduped(self):
        self.assertEqual(parse_years("2019,2021-2022,2019"), [2019, 2021, 2022])

    def test_inverted_range_rejected(self):
        with self.assertRaises(ValueError):
            parse_years("2024-2020")

    def test_all_spans_history(self):
        years = parse_years("all")
        self.assertEqual(years[0], 1869)
        self.assertGreater(len(years), 150)


class TestLayout(unittest.TestCase):
    def test_season_partition(self):
        self.assertEqual(partition_of({"year": 2023, "week": 3}), "2023")
        self.assertEqual(partition_of({}), "static")

    def test_year_excluded_from_filename(self):
        self.assertEqual(file_stem({"year": 2023}), "all")
        self.assertEqual(file_stem({"year": 2023, "week": 3}), "week-3")

    def test_values_sanitised(self):
        self.assertNotIn("/", file_stem({"team": "Texas A&M/x"}))


class TestSweep(TempStoreCase):
    def test_writes_by_season_and_resumes(self):
        sel = [ep.BY_PATH[p] for p in ("/games", "/venues")]

        store = Store(self.out)
        runner = Runner(FakeClient(), store, years=[2023])
        tasks, _ = runner.plan(sel)
        runner.run(tasks)
        self.assertGreater(runner.summary.ok, 0)
        self.assertEqual(runner.summary.failed, 0)

        # season data partitioned by year, reference data under static/
        self.assertTrue(os.path.isdir(os.path.join(self.out, "2023", "games")))
        self.assertTrue(os.path.isdir(os.path.join(self.out, "static", "venues")))
        self.assertEqual(store.seasons(), [2023])
        self.assertEqual(len(list(store.iter_rows("games"))), 3)

        # a second run re-pulls nothing
        store2 = Store(self.out)
        runner2 = Runner(FakeClient(), store2, years=[2023])
        tasks2, _ = runner2.plan(sel)
        runner2.run(tasks2)
        self.assertEqual(runner2.summary.ok, 0)
        self.assertEqual(runner2.summary.skipped, len(tasks2))

    def test_degrades_on_400_and_remembers(self):
        sel = [ep.BY_PATH["/lines"]]  # declares a YEAR_WEEK fallback

        store = Store(self.out)
        client = FakeClient(reject_coarse={"/lines"})
        runner = Runner(client, store, years=[2023])
        tasks, _ = runner.plan(sel)
        runner.run(tasks)

        self.assertEqual(runner.summary.failed, 0)
        written = os.listdir(os.path.join(self.out, "2023", "lines"))
        self.assertEqual(len(written), 18)  # weeks 0-16 + postseason
        self.assertEqual(Store(self.out).degraded, {"/lines": ep.YEAR_WEEK})

        # the coarse call is not attempted again on a later run
        client2 = FakeClient(reject_coarse={"/lines"})
        runner2 = Runner(client2, Store(self.out), years=[2023])
        tasks2, _ = runner2.plan(sel)
        runner2.run(tasks2)
        self.assertNotIn(("/lines", {"year": 2023}), client2.seen)

    def test_interrupted_fallback_resumes(self):
        sel = [ep.BY_PATH["/lines"]]

        store = Store(self.out)
        runner = Runner(FakeClient(die_after=5, reject_coarse={"/lines"}), store,
                        years=[2023])
        tasks, _ = runner.plan(sel)
        with self.assertRaises(KeyboardInterrupt):
            runner.run(tasks)
        partial = len(os.listdir(os.path.join(self.out, "2023", "lines")))
        self.assertLess(partial, 18)

        # resuming must re-plan the remaining week calls, not the coarse one
        runner2 = Runner(FakeClient(), Store(self.out), years=[2023])
        tasks2, _ = runner2.plan(sel)
        runner2.run(tasks2)
        self.assertEqual(len(os.listdir(os.path.join(self.out, "2023", "lines"))), 18)

    def test_dependent_endpoints_planned_from_harvested_ids(self):
        store = Store(self.out)
        runner = Runner(FakeClient(), store, years=[2023])
        tasks, dependent = runner.plan(
            [ep.BY_PATH["/games"], ep.BY_PATH["/game/box/advanced"]]
        )
        # phase 1 holds only /games; the id-keyed endpoint waits for phase 2
        self.assertEqual([t.endpoint.path for t in tasks], ["/games"])
        self.assertEqual([e.path for e in dependent], ["/game/box/advanced"])

        runner.run(tasks)
        dep_tasks = runner.plan_dependent(dependent)
        self.assertEqual(len(dep_tasks), 3)  # one per harvested game id
        self.assertEqual({t.params["id"] for t in dep_tasks}, {400, 401, 402})

    def test_min_year_respected(self):
        store = Store(self.out)
        runner = Runner(FakeClient(), store, years=[1990, 2023])
        tasks, _ = runner.plan([ep.BY_PATH["/player/portal"]])  # min_year=2021
        self.assertEqual([t.params["year"] for t in tasks], [2023])

    def test_empty_response_recorded_not_written(self):
        class Empty(FakeClient):
            def get(self, path, params=None):
                super().get(path, params)
                return []

        store = Store(self.out)
        runner = Runner(Empty(), store, years=[2023])
        tasks, _ = runner.plan([ep.BY_PATH["/venues"]])
        runner.run(tasks)
        self.assertEqual(runner.summary.empty, 1)
        self.assertEqual(runner.summary.ok, 0)
        self.assertFalse(os.path.isdir(os.path.join(self.out, "static", "venues")))


class TestDestinationGuard(unittest.TestCase):
    def test_unmounted_volume_refused(self):
        from cfbd_pull.store import DriveNotMounted, ensure_destination

        with self.assertRaises(DriveNotMounted):
            ensure_destination("/Volumes/DefinitelyNotMounted12345/CFDB Stats")


if __name__ == "__main__":
    unittest.main(verbosity=2)
