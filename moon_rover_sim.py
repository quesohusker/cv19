"""
Moon Rover Monte Carlo Simulation
----------------------------------
Movement rules (discrete 1-meter steps, one axis at a time):
  +y : 50.0%
  -y : 25.0%
  +x : 12.5%
  -x : 12.5%

10,000 simulations × 100,000 steps each.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.gridspec import GridSpec
from scipy import stats
import time

# ── Simulation ─────────────────────────────────────────────────────────────────

def run_monte_carlo(n_sims: int = 10_000, n_steps: int = 100_000,
                    chunk_size: int = 200, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """
    Vectorised Monte Carlo rover simulation.

    Processes simulations in chunks to keep peak memory around 80–160 MB.
    Returns arrays of final (x, y) positions for all simulations.
    """
    rng = np.random.default_rng(seed)
    final_x = np.empty(n_sims, dtype=np.int32)
    final_y = np.empty(n_sims, dtype=np.int32)

    t0 = time.perf_counter()
    for start in range(0, n_sims, chunk_size):
        n = min(chunk_size, n_sims - start)

        # Random floats in [0, 1) — float32 halves memory vs float64
        r = rng.random((n, n_steps), dtype=np.float32)

        # Thresholds: +y < 0.50 | -y < 0.75 | +x < 0.875 | -x else
        # Y displacement per step
        dy = np.where(r < 0.50, np.int8(1),
             np.where(r < 0.75, np.int8(-1), np.int8(0)))

        # X displacement per step
        dx = np.where(r >= 0.875, np.int8(-1),
             np.where(r >= 0.750, np.int8(1),  np.int8(0)))

        final_x[start:start + n] = dx.sum(axis=1)
        final_y[start:start + n] = dy.sum(axis=1)

        elapsed = time.perf_counter() - t0
        done = start + n
        rate = done / elapsed if elapsed > 0 else 0
        print(f"\r  {done:>6,}/{n_sims:,} simulations  ({rate:.0f}/s)", end="", flush=True)

    print(f"\n  Done in {time.perf_counter() - t0:.1f}s")
    return final_x.astype(np.float64), final_y.astype(np.float64)


print("=" * 60)
print("  Moon Rover Monte Carlo Simulation")
print("  10,000 sims × 100,000 steps")
print("=" * 60)

x_pos, y_pos = run_monte_carlo()
distances = np.sqrt(x_pos**2 + y_pos**2)

# ── Statistics ─────────────────────────────────────────────────────────────────

mu_d,  sd_d  = distances.mean(), distances.std()
mu_x,  sd_x  = x_pos.mean(),    x_pos.std()
mu_y,  sd_y  = y_pos.mean(),    y_pos.std()
pct = {p: np.percentile(distances, p) for p in [5, 10, 25, 50, 75, 90, 95]}

print(f"\n  Expected Y drift  (theory): {0.25 * 100_000:,.0f} m")
print(f"  Observed mean Y:            {mu_y:,.0f} m")
print(f"  Observed mean X:            {mu_x:,.1f} m")
print(f"\n  Distance from origin:")
print(f"    Mean ± SD : {mu_d:,.0f} ± {sd_d:,.0f} m")
print(f"    Min / Max : {distances.min():,.0f} / {distances.max():,.0f} m")
for p, v in pct.items():
    print(f"    P{p:<3}      : {v:,.0f} m")

# ── Plotting ───────────────────────────────────────────────────────────────────

fig = plt.figure(figsize=(18, 14), facecolor="#0d0d1a")
fig.suptitle(
    "Moon Rover Monte Carlo Simulation\n"
    "10,000 simulations  ×  100,000 steps each",
    fontsize=17, fontweight="bold", color="white", y=0.99
)

gs = GridSpec(2, 3, figure=fig, hspace=0.42, wspace=0.38,
              left=0.06, right=0.97, top=0.93, bottom=0.08)

DARK  = "#0d0d1a"
PANEL = "#14142b"
TEXT  = "#e0e0f0"

def style_ax(ax, title, xlabel, ylabel):
    ax.set_facecolor(PANEL)
    ax.set_title(title, color=TEXT, fontsize=11, pad=8)
    ax.set_xlabel(xlabel, color=TEXT, fontsize=9)
    ax.set_ylabel(ylabel, color=TEXT, fontsize=9)
    ax.tick_params(colors=TEXT, labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333355")
    ax.grid(True, color="#222244", linewidth=0.5, linestyle="--")


# ── 1. Scatter: final positions ────────────────────────────────────────────────
ax1 = fig.add_subplot(gs[0, 0])
sc = ax1.scatter(x_pos, y_pos, c=distances, cmap="plasma",
                 s=2, alpha=0.35, rasterized=True)
cb1 = plt.colorbar(sc, ax=ax1, pad=0.02)
cb1.ax.yaxis.set_tick_params(color=TEXT, labelsize=7)
cb1.set_label("Distance from origin (m)", color=TEXT, fontsize=8)
plt.setp(cb1.ax.yaxis.get_ticklabels(), color=TEXT)

ax1.scatter(0, 0, c="red", s=80, marker="*", zorder=6, label="Origin (0,0)")
ax1.scatter(mu_x, mu_y, c="cyan", s=60, marker="+", zorder=6,
            linewidths=2, label=f"Mean ({mu_x:.0f}, {mu_y:.0f}) m")
ax1.legend(fontsize=7, facecolor=PANEL, labelcolor=TEXT, edgecolor="#333355")
style_ax(ax1, "Final Rover Positions", "X Position (m)", "Y Position (m)")


# ── 2. 2-D density heatmap ─────────────────────────────────────────────────────
ax2 = fig.add_subplot(gs[0, 1])
h2, xed, yed, img = ax2.hist2d(
    x_pos, y_pos, bins=80, cmap="inferno",
    norm=mcolors.LogNorm()
)
cb2 = plt.colorbar(img, ax=ax2, pad=0.02)
cb2.ax.yaxis.set_tick_params(color=TEXT, labelsize=7)
cb2.set_label("Count (log scale)", color=TEXT, fontsize=8)
plt.setp(cb2.ax.yaxis.get_ticklabels(), color=TEXT)
style_ax(ax2, "Position Density Heatmap", "X Position (m)", "Y Position (m)")


# ── 3. X-position marginal ─────────────────────────────────────────────────────
ax3 = fig.add_subplot(gs[0, 2])
counts_x, edges_x, _ = ax3.hist(
    x_pos, bins=60, color="#5588ff", edgecolor="#223388",
    alpha=0.8, density=True
)
mu_xf, sd_xf = stats.norm.fit(x_pos)
xf = np.linspace(x_pos.min(), x_pos.max(), 400)
ax3.plot(xf, stats.norm.pdf(xf, mu_xf, sd_xf), "w--", lw=1.5,
         label=f"Normal fit  μ={mu_xf:.0f}, σ={sd_xf:.0f} m")
ax3.axvline(0, color="red", lw=1, linestyle=":", alpha=0.8)
ax3.legend(fontsize=7, facecolor=PANEL, labelcolor=TEXT, edgecolor="#333355")
style_ax(ax3, "X-Position Distribution  (symmetric)", "X Position (m)", "Density")


# ── 4. Distance probability histogram ─────────────────────────────────────────
ax4 = fig.add_subplot(gs[1, 0:2])
n_bins = 80
counts_d, edges_d = np.histogram(distances, bins=n_bins)
centers_d = (edges_d[:-1] + edges_d[1:]) / 2
width_d   = edges_d[1] - edges_d[0]
probs_d   = counts_d / counts_d.sum()

bars = ax4.bar(centers_d, probs_d, width=width_d,
               color="#22aacc", edgecolor="#115577", alpha=0.85,
               label="Simulated probability")

# Normal fit overlay
mu_df, sd_df = stats.norm.fit(distances)
df = np.linspace(distances.min(), distances.max(), 600)
pdf_df = stats.norm.pdf(df, mu_df, sd_df) * width_d
ax4.plot(df, pdf_df, color="orange", lw=2,
         label=f"Normal fit   μ={mu_df:,.0f} m,  σ={sd_df:,.0f} m")

# Percentile markers
for p, v in {25: "#88ff88", 50: "white", 75: "#ffaa44"}.items():
    ax4.axvline(pct[p], color=v, lw=1.2, linestyle="--", alpha=0.8,
                label=f"P{p} = {pct[p]:,.0f} m")

ax4.legend(fontsize=8, facecolor=PANEL, labelcolor=TEXT, edgecolor="#333355",
           loc="upper left")
style_ax(ax4,
         "Probability Distribution of Distance from Origin",
         "Distance from Origin (m)", "Probability")


# ── 5. Cumulative distribution ─────────────────────────────────────────────────
ax5 = fig.add_subplot(gs[1, 2])
sorted_d = np.sort(distances)
cdf_emp  = np.linspace(1 / len(sorted_d), 1.0, len(sorted_d))
ax5.plot(sorted_d, cdf_emp, color="#22aacc", lw=2, label="Empirical CDF")

cdf_fit = stats.norm.cdf(df, mu_df, sd_df)
ax5.plot(df, cdf_fit, "orange", lw=1.5, linestyle="--", label="Normal fit")

for p in [10, 25, 50, 75, 90]:
    v = pct[p]
    ax5.axvline(v, color="gray", lw=0.8, linestyle=":", alpha=0.7)
    ax5.text(v + sd_df * 0.08, p / 100, f"P{p}", fontsize=6.5,
             color="#aaaacc", va="center")

ax5.set_ylim(0, 1.05)
ax5.legend(fontsize=8, facecolor=PANEL, labelcolor=TEXT, edgecolor="#333355")
style_ax(ax5, "Cumulative Probability of Distance",
         "Distance from Origin (m)", "Cumulative Probability")


# ── Stats annotation ───────────────────────────────────────────────────────────
stats_lines = (
    f"Movement probabilities          Simulation results\n"
    f"  +Y (north)  : 50.0%           Mean Y pos : {mu_y:>10,.0f} m\n"
    f"  −Y (south)  : 25.0%           Mean X pos : {mu_x:>10,.1f} m\n"
    f"  +X (east)   : 12.5%           SD   Y pos : {sd_y:>10,.0f} m\n"
    f"  −X (west)   : 12.5%           SD   X pos : {sd_x:>10,.0f} m\n"
    f"                                 Mean dist  : {mu_d:>10,.0f} m\n"
    f"Steps / sim   : 100,000         SD   dist  : {sd_d:>10,.0f} m\n"
    f"# simulations :  10,000         P50  dist  : {pct[50]:>10,.0f} m"
)
fig.text(0.50, 0.003, stats_lines, fontsize=8.5, color=TEXT,
         ha="center", va="bottom",
         bbox=dict(boxstyle="round,pad=0.5", facecolor="#1a1a33",
                   edgecolor="#334466", alpha=0.9),
         fontfamily="monospace")

out_path = "/home/user/cv19/moon_rover_simulation.png"
plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=DARK)
print(f"\nChart saved → {out_path}")
plt.close()
