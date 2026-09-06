# QuesoHusker's Volleyball — app

Streamlit front end for NCAA women's D1 volleyball benchmark grading and
opponent-adjusted power rankings. Mirrors the structure and design system of the
CFB app, minus game predictions.

## Run it

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py      # from the repo root
```

The app reads only `app_data/` (2.4 MB, committed). It never touches raw
play-by-play, so it starts instantly and runs inside Streamlit Cloud's memory limit.

## Deploy to Streamlit Community Cloud

1. Push this repo to GitHub.
2. At share.streamlit.io, create an app pointing at this repo.
3. Main file path: `streamlit_app.py`. Nothing else to configure — `requirements.txt`
   and `.streamlit/config.toml` (dark theme, Nebraska-red accent) are picked up
   automatically.

## Layout

| path | role |
|---|---|
| `streamlit_app.py` | the app; must stay at repo root for Streamlit Cloud's default main path |
| `app/data.py` | cached loaders and query helpers over `app_data/` |
| `app/theme.py` | palette, team colors, chip/pill renderers from the design system |
| `app_data/` | precomputed tables the app reads (committed) |
| `analytics/` | the pipeline that produces `app_data/` |

## Rebuilding the data

The app is read-only over precomputed artifacts. To refresh them after new pbp lands:

```bash
python analytics/rally_engine.py data/ncaavolleyballr/data-csv/wvb_pbp_div1_2026.csv \
    --out-dir data/rallies
python analytics/build_match_metrics.py --years 2021 2022 2023 2024 2025 2026
python analytics/build_app_data.py          # also writes power_ratings.parquet
```

Then commit the changed files under `app_data/`.

## Views

- **Stat Comparison** — two teams, last match and season averages, better-of-two in green.
- **The Volleyball 7** — benchmark scorecard, last match and season hit rate, `Met (of 7)` total.
- **Power Rankings** — opponent-adjusted side-out rating with offense/defense splits,
  conference filter, national ranks preserved under filtering.
- **How it works** — thresholds, the grade-to-win% relationship, context metrics, caveats.

## Two numbers, two jobs

The **grade** describes a match and tracks season success (r = +0.96 with season win
percentage). It is unadjusted, so it rewards a soft schedule and should not rank teams.

The **power rating** is a ridge regression of side-out rate on team offense and
opponent defense. It is what the rankings sort by, and it is what removes the
schedule distortions the raw grade shows.
