#!/usr/bin/env bash
#
# Wrapper for the cv19 automatic pipeline. Finds a Python that has pandas+numpy
# (so launchd's minimal environment still works) and runs pipeline.py with it,
# forwarding any flags. This is what the launchd job and your manual runs call.
#
#   ./pipeline.sh                 # gated full run (skips if no game yesterday) + commit
#   ./pipeline.sh --dry-run       # print the plan, touch nothing
#   ./pipeline.sh --ignore-gate   # run regardless of the schedule
#   ./pipeline.sh --gate-only     # just print today's game-day decision
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-}"
if [ -n "$PY" ]; then
    "$PY" -c 'import pandas, numpy' >/dev/null 2>&1 || { echo "PYTHON=$PY lacks pandas+numpy" >&2; exit 1; }
else
    for c in python3 python /usr/local/bin/python3 /opt/homebrew/bin/python3 \
             /opt/anaconda3/bin/python "$HOME/anaconda3/bin/python" \
             "$HOME/miniconda3/bin/python" "$HOME/miniforge3/bin/python"; do
        if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import pandas, numpy' >/dev/null 2>&1; then
            PY="$c"; break
        fi
    done
fi
[ -n "$PY" ] || { echo "No Python with pandas+numpy found. Set PYTHON=/path/to/python." >&2; exit 1; }

# Pass the same interpreter down so the `python -m <module>` stages use it too.
exec "$PY" pipeline.py --python "$PY" "$@"
