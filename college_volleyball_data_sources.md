# College Volleyball Analytics: Data Sources

Research summary of where to get NCAA volleyball data for analytics work — official stats, scraping tools, pre-built datasets, ratings systems, and commercial platforms.

## Official NCAA sources

- **[stats.ncaa.org](https://stats.ncaa.org/rankings)** — The NCAA's official stats portal. Source of record for team/player box scores, season stats, and rankings across D1/D2/D3, men's and women's. The interface is old and has no bulk export or public API, so most practical use goes through a scraper (see below).
- **[NCAA.com stats pages](https://www.ncaa.com/stats/volleyball-women/d1)** — Cleaner leaderboards (kills, hitting %, assists, digs, blocks, aces) pulled from the same underlying data. Good for quick lookups, not for bulk analysis.
- **[NCAA.org championships/records](https://www.ncaa.org/championships/statistics-and-records/womens-volleyball/)** — Historical records book: All-Americans, championship results, single-season/career records.

## Scraping tools and pre-scraped datasets

- **[ncaavolleyballr](https://github.com/JeffreyRStevens/ncaavolleyballr)** (R package) — The most complete open tool for this. Pulls team/player season stats, match-level stats, and **play-by-play** for NCAA men's and women's volleyball, D1–D3, 2020–2025. The maintainers already scraped 2020–2024 and publish the raw files, so you often don't need to scrape yourself — see the [data article](https://jeffreyrstevens.github.io/ncaavolleyballr/articles/data.html).
- **[mattwaite/NCAAWomensVolleyballData](https://github.com/mattwaite/NCAAWomensVolleyballData)** — A repo of NCAA women's volleyball data scraped from stats.ncaa.org, with the R scrapers included. Useful as a second implementation / cross-check.
- **[henrygd/ncaa-api](https://github.com/henrygd/ncaa-api)** — General-purpose free API in front of ncaa.com (scores, stats, standings, schedules, rankings) covering many NCAA sports including volleyball. Rate-limited to 5 req/sec/IP. Good if you want live scores/standings rather than deep box-score detail.
- Note: NCAA's site blocks aggressive scraping — pace requests, and prefer the pre-scraped dumps above over re-scraping from scratch.

## Academic / research datasets

- **[Estimating individual contributions to team success in women's college volleyball](https://arxiv.org/pdf/2402.01083)** (arXiv, 2024) — Uses a detailed 2022 NCAA D1 women's volleyball dataset with player identity, skill type, contact location, and quality grade for every touch. Good reference for plus-minus / RAPM-style modeling and possibly a data source via the authors.
- **[veds12/volleyball-ml](https://github.com/veds12/volleyball-ml)** — Small dataset + ML models for predicting match outcomes; useful as a modeling example more than a primary data source.

## Ratings and rankings systems

- **[Massey Ratings — College Volleyball](https://masseyratings.com/cvol/ncaa-d1/ratings)** — Kenneth Massey's computer ratings, split out by division (D1/D2/D3, NAIA, NJCAA) and by men's/women's. Free, updated in-season, and Massey publishes methodology.
- **NCAA RPI** — The rating percentage index is the official NCAA selection-committee metric for volleyball (unlike basketball, volleyball hasn't moved to a NET-style system). Wikipedia's [RPI article](https://en.wikipedia.org/wiki/Rating_percentage_index) covers the formula; **[WarrenNolan.com](https://www.warrennolan.com/)** publishes live RPI for several NCAA sports and is worth checking for a volleyball-specific RPI page each season, though basketball/baseball are its most consistently maintained sports.

## Commercial / professional analytics platforms

These are the tools actual college programs use for scouting and video-based tracking. They're not open data sources, but worth knowing since a lot of program-level analytics work assumes one of these as the data-collection layer:

- **[DataVolley](https://www.dataproject.com/Products/US/en/Volleyball/DataVolley)** — The dominant standard for manual volleyball scouting/coding (`.dvw` files). Widely used at the college level; an R package (`datavolley`, part of the **[openvolley](https://datavolley.openvolley.org/)** project) can read these files if you have access to `.dvw` scouting files from a program.
- **[VolleyStation](https://www.datavolley.eu/en/software/volleyball/)** and **Click & Scout** — Alternative scouting-software formats, also readable by the openvolley R tooling.
- **[Volleymetrics](https://platform.softwareone.com/product/volleymetrics/PCP-6691-6429)** (acquired by Hudl) — Video-based automated tracking and analytics, used by ~350 collegiate/pro programs. Proprietary, no public data access.

## Stat definitions reference

For getting hitting percentage, kill efficiency, and similar formulas right before building any model:

- **[SoloStats — Volleyball Statistics Explained](https://www.solostatslive.com/definitions/volleyball-statistics-explained)**
- **[The Art of Coaching Volleyball — Calculating Hitting Efficiency](https://www.theartofcoachingvolleyball.com/calculating-hitting-efficiency/)**

## Recommended starting point

For a from-scratch analytics project: pull historical team/player/match data from `ncaavolleyballr`'s pre-scraped 2020–2024 files, layer in current-season data via `stats.ncaa.org` (through the same package) or `henrygd/ncaa-api` for anything live, and use Massey Ratings as an external strength-of-schedule check. Play-by-play from `ncaavolleyballr` is the richest free source if the goal is possession- or rally-level modeling rather than box-score aggregates.
