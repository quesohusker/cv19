"""Collector for mattwaite/NCAAWomensVolleyballData.

Fills in NCAA D1 women's volleyball match stats, player-season stats, and
player-career stats for **2018-2021** -- the two seasons before
`ncaavolleyballr`'s data starts (2020), plus overlap years useful for
cross-checking. No play-by-play, no D2/D3; the repo appears inactive since
2021 (its own README mentions planned 2022 updates that never landed --
there's no 2022 file to fetch).

`raw.githubusercontent.com` serves this repo's files directly (not Git
LFS), so no special handling is needed beyond a plain GET.

The file list below is hardcoded because this repo has no directory-listing
API available from this environment (only individual raw file fetches).
It was captured from a full clone on 2026-09-02; if the upstream repo adds
files later, add them here.
"""
from __future__ import annotations

import json

import requests

from .common import DATA_ROOT, download_file

REPO = "mattwaite/NCAAWomensVolleyballData"
BRANCH = "main"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"

# Final, analysis-ready stat tables.
DATA_FILES = [
    "data/ncaa_volleyball_playercareerstats_2021.csv",
    "data/ncaa_volleyball_playermatchstats_2021.csv",
    "data/ncaa_womens_volleyball_matchstats_2018.csv",
    "data/ncaa_womens_volleyball_matchstats_2019.csv",
    "data/ncaa_womens_volleyball_matchstats_2020.csv",
    "data/ncaa_womens_volleyball_matchstats_2021.csv",
    "data/ncaa_womens_volleyball_playerstats_2018.csv",
    "data/ncaa_womens_volleyball_playerstats_2019.csv",
    "data/ncaa_womens_volleyball_playerstats_2020.csv",
    "data/ncaa_womens_volleyball_playerstats_2021.csv",
]

# Intermediate URL lists the upstream R scrapers used (team/player page
# URLs). Not stat data, but small and potentially useful for anyone
# extending the scraper to later seasons.
URL_LIST_FILES = [
    "url_csvs/NCAA Volleyball - 2018.csv",
    "url_csvs/NCAA Volleyball - 2019.csv",
    "url_csvs/NCAA Volleyball - 2020.csv",
    "url_csvs/NCAA Volleyball - 2021.csv",
    "url_csvs/ncaa_volleyball_playermatchstaturls_2021.csv",
    "url_csvs/ncaa_womens_volleyball_teamurls_2018.csv",
    "url_csvs/ncaa_womens_volleyball_teamurls_2019.csv",
    "url_csvs/ncaa_womens_volleyball_teamurls_2020.csv",
    "url_csvs/ncaa_womens_volleyball_teamurls_2021.csv",
]

OUT_DIR = DATA_ROOT / "mattwaite_early_years"


def collect() -> list[dict]:
    session = requests.Session()
    results: list[dict] = []

    for rel_path in DATA_FILES + URL_LIST_FILES:
        url = f"{RAW_BASE}/{requests.utils.requote_uri(rel_path)}"
        dest = OUT_DIR / rel_path
        result = download_file(url, dest, session=session)
        result["source"] = "mattwaite_early_years"
        results.append(result)
        print(f"[mattwaite] {result['status']:>10}  {rel_path}")

    return results


if __name__ == "__main__":
    out = collect()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "_collection_log.json", "w") as f:
        json.dump(out, f, indent=2)
