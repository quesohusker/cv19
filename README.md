# cv19 — Moon Rover Monte Carlo Simulation

A discrete 2-D random-walk simulation of a moon rover, with Monte Carlo
analysis and rendered path figures.

- `moon_rover_sim.py` — main simulation: 10,000 chained runs of 100,000
  steps each (one continuous billion-step random walk), plus summary charts.
- `moon_rover_path_hd.py` — re-renders just the 2-D path panel at high
  resolution.

## Run it locally

Everything runs on your own machine; figures are written next to the
scripts as `.png` files.

### 1. Prerequisites

- Python 3.10+ (developed against 3.11)
- `git`

### 2. Clone the repo

```bash
git clone https://github.com/quesohusker/cv19.git
cd cv19
```

### 3. Create the Python environment

```bash
./setup.sh
source .venv/bin/activate
```

`setup.sh` creates a `.venv/` virtual environment and installs the
dependencies from `requirements.txt` (numpy, scipy, matplotlib). It only
needs to be run once; afterward just `source .venv/bin/activate` in each
new shell.

<details>
<summary>Manual setup (equivalent to setup.sh)</summary>

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```
</details>

### 4. Run a simulation

```bash
python moon_rover_sim.py       # full run + summary figure -> moon_rover_simulation.png
python moon_rover_path_hd.py   # HD path panel            -> moon_rover_path_hd.png
```

The simulation has no fixed random seed, so each run produces a unique
path and fresh output images stored locally.

## Running with Claude Code locally

To drive this project with Claude Code (and its agents) from your own
machine instead of the web:

1. Install Node.js 18+.
2. Install the CLI: `npm install -g @anthropic-ai/claude-code`
3. From the repo directory, run: `claude`
4. Authenticate on first launch (Anthropic account or API key).

All agent runs, data, and generated outputs then live in your local
working copy.
