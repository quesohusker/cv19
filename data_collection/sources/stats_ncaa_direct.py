"""Fallback direct scraper skeleton for stats.ncaa.org.

Only use this to fill specific, known gaps in the two scraped-dump sources
(e.g. the current in-progress season before someone publishes a fresh
`ncaavolleyballr` pull, or men's D2 volleyball, which neither dump covers).
It is deliberately a skeleton, not a full crawler: stats.ncaa.org has no
API, its HTML is heavy and inconsistent across pages, and it rate-limits/
blocks IPs that hit it too fast. `ncaavolleyballr`'s own R scrapers (see
`data-raw/ncaa.R` in that repo) are the reference implementation for the
full team-discovery -> roster -> per-player-page crawl; this module is
meant for pulling one team/season page at a time by hand, not for
re-deriving that whole crawl in Python.

NOT VERIFIED END-TO-END: `stats.ncaa.org` is denied by this sandbox's
egress policy, so this has only been checked for import/syntax
correctness. Before running it for real:
  - Confirm the URL pattern for the page you want (team IDs and "org ID"
    numbers are opaque and specific to each team/season -- browse
    stats.ncaa.org by hand to find them, there's no listing endpoint).
  - Keep REQUEST_DELAY_S >= 2 (matches the pace the mattwaite/ncaavolleyballr
    scrapers use) or expect to get blocked.
"""
from __future__ import annotations

import time

import pandas as pd
import requests

from .common import DATA_ROOT, DEFAULT_HEADERS

BASE_URL = "https://stats.ncaa.org"
REQUEST_DELAY_S = 2.0
OUT_DIR = DATA_ROOT / "stats_ncaa_direct"


def fetch_team_page(session: requests.Session, team_id: int, year_stat_category_id: int) -> pd.DataFrame:
    """Fetch one team's season stats table.

    `team_id` and `year_stat_category_id` come from stats.ncaa.org URLs like
    stats.ncaa.org/teams/<team_id>?year_stat_category_id=<id> -- there is no
    way to enumerate these programmatically from outside; they have to be
    collected by browsing the site (or reusing IDs already captured in
    ncaavolleyballr's or mattwaite's scraped data/url_csvs files).
    """
    url = f"{BASE_URL}/teams/{team_id}"
    resp = session.get(url, headers=DEFAULT_HEADERS, params={"year_stat_category_id": year_stat_category_id}, timeout=30)
    resp.raise_for_status()
    tables = pd.read_html(resp.text)
    if not tables:
        raise ValueError(f"no tables found on {url}")
    return max(tables, key=len)


def collect(team_ids: list[tuple[int, int]]) -> list[dict]:
    """Fetch a caller-supplied list of (team_id, year_stat_category_id) pairs.

    Deliberately does not try to discover team IDs itself -- see the module
    docstring. Call this with IDs you've gathered for the specific gap
    you're filling.
    """
    session = requests.Session()
    results: list[dict] = []
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for team_id, category_id in team_ids:
        try:
            df = fetch_team_page(session, team_id, category_id)
        except Exception as exc:  # noqa: BLE001
            results.append({"source": "stats_ncaa_direct", "team_id": team_id, "status": "failed", "error": str(exc)})
            print(f"[stats.ncaa.org] team {team_id}: FAILED ({exc})")
            time.sleep(REQUEST_DELAY_S)
            continue

        dest = OUT_DIR / f"team_{team_id}_cat_{category_id}.csv"
        df.to_csv(dest, index=False)
        results.append({"source": "stats_ncaa_direct", "team_id": team_id, "status": "downloaded", "path": str(dest)})
        print(f"[stats.ncaa.org] team {team_id}: {len(df)} rows -> {dest.name}")
        time.sleep(REQUEST_DELAY_S)

    return results


if __name__ == "__main__":
    print(__doc__)
    print("\nThis module needs a list of (team_id, year_stat_category_id) pairs")
    print("to do anything -- import collect() and call it directly rather than")
    print("running this file standalone.")
