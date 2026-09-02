# Data Collection Report — 2026-09-02

Result of running `python collect_all.py` in this sandbox. Data lives locally under `data/` (gitignored, not in this repo — see `data_collection/README.md` for why). This file documents what's there.

## What was downloaded

**8.78 GB total, 154 files, ~81 million data rows, zero failed downloads.**

### `ncaavolleyballr` — 8.75 GB, 130 CSVs + 5 reference tables

Team season, player season, team match, player match, and play-by-play stats, scraped from stats.ncaa.org.

| | Women's | Men's |
|---|---|---|
| **Division 1** | 2020–2025 (6 seasons) | 2020–2024 (5 seasons) |
| **Division 2** | 2020–2024 (5 seasons) | **not available** |
| **Division 3** | 2020–2024 (5 seasons) | 2020–2024 (5 seasons) |

Row counts (data rows, excl. header), summed across divisions:

| Level | Women's rows | Men's rows |
|---|---:|---:|
| Team season | 5,304 | 835 |
| Player season | 84,996 | 12,887 |
| Team match | 141,322 | 21,776 |
| Player match | 805,226 | 113,016 |
| **Play-by-play** | **71,044,383** | **8,708,251** |

(80,937,996 data rows total across both sexes and all five levels.)

Play-by-play is one row per rally event (serve/attack/kill/error/etc. with player and score context) — it's the reason for the 8.75 GB, and the reason this is the most useful source for anything beyond box-score analysis.

**2020 is a visibly smaller season across every category** (e.g. women's D1 team-match rows are roughly half of 2021's) — consistent with the COVID-shortened, partly-cancelled 2020 schedule, not a scraping gap. Men's D1 team-season counts also climb steadily (43 teams in 2020 → 66 in 2024) — that's real: men's D1 volleyball has been expanding rapidly (new programs, new conferences), not missing data in the early years.

### `mattwaite_early_years` — 30 MB, 19 files

Women's Division 1 only: team-match stats and player-season stats for **2018–2021**, plus player career stats and match-level player stats for 2021. No play-by-play, no D2/D3. This is what extends women's D1 coverage back to 2018 instead of starting at 2020.

Combined, **women's D1 team/player stats now run 2018–2025 (8 seasons)** with only one real join gap: mattwaite's naming is inconsistent team-to-team (`"Maryland Terrapins`, `A&M-Corpus Christi Islanders`) while ncaavolleyballr ships an ID-based lookup table (`reference/ncaa_teams.csv`) — matching them requires name-based fuzzy joining, not a clean key join. See Concerns below.

## What's missing

- **Current season (Fall 2026).** Neither dump includes it — `ncaavolleyballr`'s newest data is the 2025 season for women's D1 (and 2024 for everything else). Filling this in needs a live source: `sources/ncaa_live_api.py` or `sources/stats_ncaa_direct.py`, both drafted but **not runnable from this sandbox** (see Concerns).
- **Men's Division 2 volleyball**, entirely. Neither free source covers it. (Worth checking whether stats.ncaa.org tracks it at all — some low-sponsorship sports have thin or no structured stats pages.)
- **Women's play-by-play before 2020**, and **all men's/mattwaite data has no play-by-play before 2020** — rally-level detail only goes back to 2020 across the board.
- **Ratings/rankings** (Massey Ratings, NCAA RPI). Drafted in `sources/massey_ratings.py` but not run here — see Concerns.
- **Anything below Division 3** (NAIA, NJCAA) except what Massey's site nominally covers (also not pulled here).
- **Roster/biographical depth** — the player-season files carry jersey number, position, and (inconsistently by year) height/class, but no hometown, high school, recruiting ranking, or transfer-portal history.
- **Spatial/tracking detail** — the play-by-play is event-level (who did what, when, what the score became), not court-location or ball-trajectory data. That level of detail exists only in proprietary systems (DataVolley, Volleymetrics/Hudl) that require a program's own scouting files — there's no free equivalent.
- **Video.** Out of scope for all free sources found.

## Concerns

1. **Three of five sources never actually ran.** `massey_ratings.py`, `ncaa_live_api.py`, and `stats_ncaa_direct.py` are written and importable but this sandbox's egress policy blocks `masseyratings.com`, `ncaa-api.henrygd.me`, and `stats.ncaa.org` outright (proxy-level 403, before the request reaches the site). They need to be run from a normal machine or CI runner, and should be treated as **untested against the live sites** until then — table layouts and API paths were inferred from documentation/URL conventions, not confirmed against a live response.

2. **Cross-source joins are name-based, not ID-based, across the 2018–2019 boundary.** `ncaavolleyballr` ships a team ID lookup (`reference/ncaa_teams.csv`); `mattwaite_early_years` doesn't use the same IDs. Team-name spelling, mascots, and conference labels drift year to year (realignment, rebrands) — joining 2018–2019 mattwaite data to 2020+ ncaavolleyballr data by name will silently drop or mismatch some teams unless that's handled explicitly (fuzzy-match + manual review of unmatched names, not a plain join).

3. **stats.ncaa.org has no authoritative bulk/API access** — both dumps exist because someone scraped an HTML site not built for this. That means: no guarantee of long-term availability at these GitHub URLs (`ncaavolleyballr`'s LFS storage or `mattwaite`'s repo could disappear or go stale — the mattwaite repo already looks abandoned since 2021, per its own README's unmet "coming 2022" plan), no schema stability guarantee season to season (a couple of the mattwaite files have visibly inconsistent column names year to year, e.g. `mp` vs `mp.x`/`mp.y` from repeated-merge artifacts), and no recourse if a column is silently wrong. Spot-checks here looked clean (single header row, sane team counts, no truncation), but nothing here has been validated against a second, independent source — treat it as "probably right," not verified.

4. **Direct stats.ncaa.org scraping (`stats_ncaa_direct.py`) is a last resort, not a plan.** It has no team/season discovery mechanism (IDs must be gathered by hand or reused from the two dumps), needs a hard 2-second delay between requests, and can still get an IP rate-limited or blocked on any real-sized pull. Only use it for small, targeted gaps, not to backfill missing divisions or years at scale.

5. **Terms of use weren't reviewed.** None of these sources publish a clear data-reuse license. `ncaavolleyballr` and `mattwaite_early_years` are openly published on GitHub for reuse; NCAA.com/stats.ncaa.org's own terms weren't checked here. Fine for personal analytics; worth a real look before any redistribution or commercial use.

6. **8.8 GB is a lot to keep regenerating.** Re-running `collect_all.py` re-downloads everything from GitHub each time (no partial-diff support beyond skip-if-same-size). If this becomes a recurring pull, consider syncing `data/` to persistent storage (S3/GCS) instead of re-fetching, and only re-running the collector for genuinely new seasons.

## Bottom line

For historical analysis, this is a strong, mostly-complete free dataset: women's D1 volleyball 2018–2025 at box-score level, 2020–2025 at rally level, D2/D3 and men's 2020–2024 alongside it. The real gaps are the **current season** and **men's D2**, and both need live/direct scraping that this sandbox couldn't reach — run the three drafted-but-unverified collectors from an unrestricted environment to close them.
