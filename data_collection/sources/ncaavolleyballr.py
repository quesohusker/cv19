"""Collector for the JeffreyRStevens/ncaavolleyballr pre-scraped dataset.

This is the richest free source: NCAA women's (2020-2025, D1/D2/D3) and
men's (2020-2024, D1/D3 -- no D2) volleyball team-season, player-season,
team-match, player-match, and play-by-play data, scraped from
stats.ncaa.org and published as Git LFS objects.

The CSVs themselves are Git LFS objects, which the anonymous git-read lane
this collector runs under does not serve. We work around that by hitting
media.githubusercontent.com directly (the same URL GitHub's own "view raw"
link on an LFS file resolves to) instead of `git lfs pull`.

The file list is discovered dynamically from the package's own data
vignette (`vignettes/data.Rmd`) rather than hardcoded, so a future run
picks up new seasons the maintainer adds without code changes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from .common import DATA_ROOT, DEFAULT_HEADERS, download_file

REPO = "JeffreyRStevens/ncaavolleyballr"
BRANCH = "main"
VIGNETTE_URL = (
    f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/vignettes/data.Rmd"
)
# Small lookup/reference tables shipped as .rda (R data) files in the repo,
# not Git LFS -- plain raw.githubusercontent.com fetches work for these.
REFERENCE_FILES = [
    "mvb_teams.rda",
    "wvb_teams.rda",
    "ncaa_teams.rda",
    "ncaa_conferences.rda",
    "ncaa_sports.rda",
]

OUT_DIR = DATA_ROOT / "ncaavolleyballr"


# The vignette has a known documentation bug: its "Women's Division 2 2023"
# team-match link is mislabeled and points at the 2022 file a second time,
# so `wvb_teammatch_div2_2023.csv` never appears. Patch it in manually --
# confirmed to exist at this URL by listing the repo's data-csv/ directory
# directly (git clone), just not linked from data.Rmd.
KNOWN_MISSING_FROM_VIGNETTE = [
    f"https://media.githubusercontent.com/media/{REPO}/refs/heads/{BRANCH}/data-csv/wvb_teammatch_div2_2023.csv",
]


def discover_csv_urls(session: requests.Session) -> list[str]:
    resp = session.get(VIGNETTE_URL, headers=DEFAULT_HEADERS, timeout=30)
    resp.raise_for_status()
    urls = re.findall(r"https://media\.githubusercontent\.com/media/\S+?\.csv", resp.text)
    urls.extend(KNOWN_MISSING_FROM_VIGNETTE)
    # de-dupe while preserving order
    return list(dict.fromkeys(urls))


def collect() -> list[dict]:
    session = requests.Session()
    results: list[dict] = []

    urls = discover_csv_urls(session)
    print(f"[ncaavolleyballr] discovered {len(urls)} data files from data.Rmd")
    for i, url in enumerate(urls, 1):
        filename = url.rsplit("/", 1)[-1]
        dest = OUT_DIR / "data-csv" / filename
        result = download_file(url, dest, session=session)
        result["source"] = "ncaavolleyballr"
        results.append(result)
        print(f"[ncaavolleyballr] ({i}/{len(urls)}) {result['status']:>10}  {filename}")

    for fname in REFERENCE_FILES:
        url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/data/{fname}"
        dest = OUT_DIR / "reference" / fname
        result = download_file(url, dest, session=session)
        result["source"] = "ncaavolleyballr-reference"
        results.append(result)
        print(f"[ncaavolleyballr] reference {result['status']:>10}  {fname}")

    _convert_reference_rda_to_csv()
    return results


def _convert_reference_rda_to_csv() -> None:
    """Best-effort conversion of the .rda lookup tables to CSV via pyreadr.

    Skipped silently if pyreadr isn't installed -- the .rda files are still
    downloaded and usable from R directly.
    """
    try:
        import pyreadr
    except ImportError:
        print("[ncaavolleyballr] pyreadr not installed; leaving reference tables as .rda")
        return

    ref_dir = OUT_DIR / "reference"
    for rda in sorted(ref_dir.glob("*.rda")):
        try:
            result = pyreadr.read_r(str(rda))
        except Exception as exc:  # pyreadr raises plain Exception on parse issues
            print(f"[ncaavolleyballr] could not convert {rda.name}: {exc}")
            continue
        for obj_name, df in result.items():
            csv_path = ref_dir / f"{rda.stem}.csv"
            df.to_csv(csv_path, index=False)
            print(f"[ncaavolleyballr] converted {rda.name} -> {csv_path.name} ({len(df)} rows)")


if __name__ == "__main__":
    out = collect()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "_collection_log.json", "w") as f:
        json.dump(out, f, indent=2)
