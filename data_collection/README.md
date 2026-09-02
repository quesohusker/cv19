# College Volleyball Data Collection

Scripts that pull together every free NCAA volleyball dataset identified in
[`college_volleyball_data_sources.md`](../college_volleyball_data_sources.md)
and land it in a consistent local layout under `data/` (gitignored — this is
code, not a data dump; see "Why the data isn't in git" below).

## Quick start

```bash
cd data_collection
pip install -r requirements.txt
python collect_all.py
```

This runs every collector in `sources/` and writes `data/manifest.json`
summarizing what was pulled, how big it is, and what failed.

Run a single source instead of everything:

```bash
python -m sources.ncaavolleyballr
python -m sources.mattwaite_early_years
```

## Sources, and what each one covers

| Script | Source | Coverage | Status in this sandbox |
|---|---|---|---|
| `sources/ncaavolleyballr.py` | [JeffreyRStevens/ncaavolleyballr](https://github.com/JeffreyRStevens/ncaavolleyballr) pre-scraped GitHub LFS data | Team season, player season, team match, player match, and **play-by-play**. Women's D1/D2/D3 2020–2025, men's D1/D3 2020–2024 (no men's D2 — see report). | Works — downloaded directly. |
| `sources/mattwaite_early_years.py` | [mattwaite/NCAAWomensVolleyballData](https://github.com/mattwaite/NCAAWomensVolleyballData) | Women's D1 team-match, player-season, and player-career stats, 2018–2021. No play-by-play, no D2/D3. Fills in the two seasons before `ncaavolleyballr`'s data starts. | Works — downloaded directly. |
| `sources/massey_ratings.py` | [Massey Ratings](https://masseyratings.com/cvol/ncaa-d1/ratings) | Computer strength ratings, D1/D2/D3/NAIA/NJCAA, current season (site doesn't publish a bulk historical archive). | **Blocked in this sandbox** — `masseyratings.com` is denied by the outbound egress policy here. Code is drafted and tested for structure, not for live execution. Run it from an unrestricted machine. |
| `sources/ncaa_live_api.py` | [henrygd/ncaa-api](https://github.com/henrygd/ncaa-api) (self-hosted or the public `ncaa-api.henrygd.me` instance) | Live current-season scores, standings, rankings — a gap-filler for whatever hasn't shown up in the scraped historical dumps yet. | **Blocked in this sandbox** — the host is denied by egress policy. Drafted, not run. |
| `sources/stats_ncaa_direct.py` | [stats.ncaa.org](https://stats.ncaa.org) | Skeleton for scraping a specific team/season directly when it's missing from both dumps above (e.g. the in-progress current season, D2 men's). | **Blocked in this sandbox** — `stats.ncaa.org` is denied by egress policy. Skeleton only; needs the same throttling (~2s/request) the upstream scrapers use, or NCAA will rate-limit/block the IP. |

## Why the data isn't in git

The full `ncaavolleyballr` pull is roughly **8.7 GB**, almost all of it
play-by-play CSVs (the largest single file is ~775 MB). That's far past
what belongs in a git repository (and past GitHub's 100 MB per-file limit
without LFS of its own). `data/` is gitignored; re-run `collect_all.py`
to repopulate it anywhere. If you want a persistent copy, sync `data/` to
S3/GCS/a shared drive rather than committing it.

## Notes for re-running elsewhere

- `ncaavolleyballr.py` and `mattwaite_early_years.py` only need outbound
  HTTPS to `media.githubusercontent.com` / `raw.githubusercontent.com`
  and work anywhere, including here.
- `massey_ratings.py`, `ncaa_live_api.py`, and `stats_ncaa_direct.py` need
  outbound HTTPS to their respective hosts. None of the three worked from
  this sandboxed session — its egress proxy allowlists only a small set of
  domains (npm/pypi/crates registries, `api.anthropic.com`,
  `raw.githubusercontent.com`, etc.) and returns a policy 403 for
  everything else, `masseyratings.com`, `stats.ncaa.org`, and
  `ncaa-api.henrygd.me` included. Run those three from a normal machine or
  CI runner instead.
- `stats_ncaa_direct.py` hits the NCAA's own stats portal, which is
  fragile and rate-limits aggressively. Keep the 2-second delay between
  requests (already in the script) and expect occasional IP blocks on
  large pulls — this is why the pre-scraped dumps above are the primary
  path, and direct scraping is only a fallback for gaps.
