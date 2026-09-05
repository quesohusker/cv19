#!/usr/bin/env bash
#
# One-command execution script for the FBS analytics pipeline.
# ============================================================
#
# Updates the data/stat files for a season, then reruns the grading models.
# By default it touches ONLY THE CURRENT SEASON (prior seasons are left exactly
# as they are), then regrades every team/year off the refreshed z-scores.
#
# Run it from a terminal or Claude Code, from anywhere -- it operates on its own
# project folder (where <year>/combined.csv lives):
#
#   ./run.sh                    # update the current season + rerun the grades
#   ./run.sh --season 2026      # a specific season instead of "current"
#   ./run.sh --rebuild          # rebuild every season from scratch, then regrade
#   ./run.sh --validate         # also spot-check the season after building it
#   ./run.sh --skip-grades      # only update the stat files
#
# All flags are passed straight through to refresh.py (see: ./run.sh --help).
# Override the data location with --base-dir "..." or the CFDB_BASE_DIR env var,
# and the Python interpreter with the PYTHON env var (defaults to python3).
set -euo pipefail

# Operate relative to this script's own directory (the project root), so the
# pipeline's default base dir resolves to <project>/<year>/combined.csv.
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
    PY="python"
fi

echo "Using interpreter: $("$PY" --version 2>&1)  (override with PYTHON=...)"
echo "Project / data dir: $(pwd)"
echo

exec "$PY" refresh.py "$@"
