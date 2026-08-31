#!/usr/bin/env bash
# Create a local Python environment for the moon-rover simulations.
# Usage: ./setup.sh   (then: source .venv/bin/activate)
set -euo pipefail

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo
echo "Environment ready."
echo "Activate it in this shell with:  source .venv/bin/activate"
echo "Then run a simulation, e.g.:      python moon_rover_sim.py"
