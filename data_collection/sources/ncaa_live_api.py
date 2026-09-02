"""Collector for live/current-season NCAA data via henrygd/ncaa-api.

https://github.com/henrygd/ncaa-api fronts ncaa.com with a free JSON API.
It mirrors ncaa.com's own URL structure -- `GET /<path>` on the API returns
the JSON backing the ncaa.com page at `ncaa.com/<path>`. Useful as a
gap-filler for whatever the current, in-progress season the historical
scraped dumps (`ncaavolleyballr`, `mattwaite_early_years`) don't have yet:
live standings, rankings, and scores.

Endpoint shapes below are taken directly from the project's README
(routes confirmed to exist: /standings, /rankings, /scoreboard, /schedule).
The exact sport slugs for volleyball (`volleyball-women`, `volleyball-men`)
are inferred from ncaa.com's own stats URLs
(ncaa.com/stats/volleyball-women/d1) and have NOT been confirmed against
the API itself.

NOT VERIFIED END-TO-END: both `ncaa-api.henrygd.me` (the public demo
instance) and ncaa.com are denied by this sandbox's egress policy, so this
collector has only been checked for import/syntax correctness. The public
instance is also rate-limited to 5 req/sec/IP and explicitly described by
its author as a demo, not for reliable long-term use -- for anything beyond
occasional pulls, self-host it (`docker run --rm -p 3000:3000 henrygd/ncaa-api`)
and point API_BASE at your own instance.
"""
from __future__ import annotations

import json
import time

import requests

from .common import DATA_ROOT, DEFAULT_HEADERS

API_BASE = "https://ncaa-api.henrygd.me"  # override with a self-hosted instance
DIVISIONS = ["d1", "d2", "d3"]
SPORTS = ["volleyball-women", "volleyball-men"]
REQUEST_DELAY_S = 0.25  # stay well under the 5 req/sec/IP public-instance limit

OUT_DIR = DATA_ROOT / "ncaa_live_api"


def _get(session: requests.Session, path: str) -> dict | list | None:
    resp = session.get(f"{API_BASE}{path}", headers=DEFAULT_HEADERS, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def collect() -> list[dict]:
    session = requests.Session()
    results: list[dict] = []
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for sport in SPORTS:
        for division in DIVISIONS:
            if sport == "volleyball-men" and division != "d1":
                # Men's volleyball outside D1 is a small, unevenly-sponsored
                # field; skip speculative calls likely to just 404.
                continue

            for route_name, path in {
                "standings": f"/standings/{sport}/{division}",
                "rankings": f"/rankings/{sport}/{division}",  # some sports need a poll slug suffix; verify live
            }.items():
                try:
                    data = _get(session, path)
                except requests.RequestException as exc:
                    results.append({
                        "source": "ncaa_live_api", "sport": sport, "division": division,
                        "route": route_name, "status": "failed", "error": str(exc),
                    })
                    print(f"[ncaa-live] {sport}/{division}/{route_name}: FAILED ({exc})")
                    time.sleep(REQUEST_DELAY_S)
                    continue

                if data is None:
                    results.append({
                        "source": "ncaa_live_api", "sport": sport, "division": division,
                        "route": route_name, "status": "not_found",
                    })
                    print(f"[ncaa-live] {sport}/{division}/{route_name}: 404")
                    time.sleep(REQUEST_DELAY_S)
                    continue

                dest = OUT_DIR / sport / division / f"{route_name}.json"
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "w") as f:
                    json.dump(data, f, indent=2)
                results.append({
                    "source": "ncaa_live_api", "sport": sport, "division": division,
                    "route": route_name, "status": "downloaded", "path": str(dest),
                })
                print(f"[ncaa-live] {sport}/{division}/{route_name}: OK -> {dest}")
                time.sleep(REQUEST_DELAY_S)

    return results


if __name__ == "__main__":
    out = collect()
    with open(OUT_DIR / "_collection_log.json", "w") as f:
        json.dump(out, f, indent=2)
