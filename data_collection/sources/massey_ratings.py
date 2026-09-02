"""Collector for Massey Ratings college volleyball ratings.

https://masseyratings.com publishes computer strength ratings for college
volleyball split by division/association. There's no bulk download or API
-- each division is one HTML page with one ratings table -- so this parses
the table directly with pandas.

NOT VERIFIED END-TO-END: `masseyratings.com` is denied by this sandbox's
egress policy (a 403 at the proxy, before any request reaches the site), so
this collector has only been checked for import/syntax correctness, not run
against the live site. Run it from a machine with normal internet access
and sanity-check the parsed columns before relying on it -- Massey's table
layout has changed before and isn't guaranteed to match what's assumed here.
"""
from __future__ import annotations

import json

import pandas as pd
import requests

from .common import DATA_ROOT, DEFAULT_HEADERS

# path segment -> human label. Massey's current-season URLs (no year in the
# path); for prior seasons Massey has historically used a `cvolYYYY` prefix
# (e.g. masseyratings.com/cvol2022/naia/ratings) but coverage/URL stability
# for past years is not guaranteed -- verify before scripting a historical
# backfill.
DIVISIONS = {
    "ncaa-d1": "NCAA Division I",
    "ncaa-d2": "NCAA Division II",
    "ncaa-d3": "NCAA Division III",
    "naia": "NAIA",
    "njcaa": "NJCAA",
}

BASE_URL = "https://masseyratings.com/cvol/{division}/ratings"
OUT_DIR = DATA_ROOT / "massey_ratings"


def fetch_division(session: requests.Session, division: str) -> pd.DataFrame | None:
    url = BASE_URL.format(division=division)
    resp = session.get(url, headers=DEFAULT_HEADERS, timeout=30)
    resp.raise_for_status()
    tables = pd.read_html(resp.text)
    if not tables:
        return None
    # Massey's ratings page typically has one large table; take the biggest.
    return max(tables, key=len)


def collect() -> list[dict]:
    session = requests.Session()
    results: list[dict] = []
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for division, label in DIVISIONS.items():
        try:
            df = fetch_division(session, division)
        except Exception as exc:  # noqa: BLE001 -- report and move on
            results.append({"source": "massey_ratings", "division": division, "status": "failed", "error": str(exc)})
            print(f"[massey] {division}: FAILED ({exc})")
            continue

        if df is None or df.empty:
            results.append({"source": "massey_ratings", "division": division, "status": "empty"})
            print(f"[massey] {division}: no table found")
            continue

        dest = OUT_DIR / f"massey_{division}.csv"
        df.to_csv(dest, index=False)
        results.append({
            "source": "massey_ratings",
            "division": division,
            "status": "downloaded",
            "path": str(dest),
            "rows": len(df),
        })
        print(f"[massey] {division} ({label}): {len(df)} rows -> {dest.name}")

    return results


if __name__ == "__main__":
    out = collect()
    with open(OUT_DIR / "_collection_log.json", "w") as f:
        json.dump(out, f, indent=2)
