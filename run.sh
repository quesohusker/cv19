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

# Pick a Python that can actually import pandas + numpy. Honor $PYTHON if set;
# otherwise probe the usual suspects (PATH, Anaconda/Miniconda/Miniforge,
# Homebrew) so a plain ./run.sh works even when `python3` lacks the packages.
PY="${PYTHON:-}"
if [ -n "$PY" ]; then
    "$PY" -c 'import pandas, numpy' >/dev/null 2>&1 || {
        echo "PYTHON=$PY can't import pandas+numpy. Install them or point PYTHON elsewhere." >&2
        exit 1
    }
else
    for c in python3 python \
             /opt/anaconda3/bin/python "$HOME/anaconda3/bin/python" \
             "$HOME/miniconda3/bin/python" "$HOME/miniforge3/bin/python" \
             /opt/homebrew/bin/python3 /usr/local/bin/python3; do
        if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import pandas, numpy' >/dev/null 2>&1; then
            PY="$c"; break
        fi
    done
fi
if [ -z "$PY" ]; then
    echo "No Python with pandas+numpy found." >&2
    echo "Install them (e.g.  python3 -m pip install pandas numpy) or set PYTHON=/path/to/python." >&2
    exit 1
fi

echo "Using interpreter: $PY  ($("$PY" --version 2>&1))"
echo "Project / data dir: $(pwd)"
echo

exec "$PY" refresh.py "$@"
