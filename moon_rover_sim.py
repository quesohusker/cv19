"""
Moon Rover Monte Carlo Simulation  —  Chained runs
----------------------------------------------------
Movement rules (discrete 1-meter steps, one axis at a time):
  +y : 25.0%   -y : 25.0%   +x : 25.0%   -x : 25.0%

10,000 simulations × 100,000 steps each.
Each simulation starts where the previous one ended — one continuous
1,000,000,000-step random walk with a checkpoint every 100,000 steps.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.gridspec import GridSpec
from scipy import stats
import time

# ── Simulation ─────────────────────────────────────────────────────────────────

def run_chained(n_sims: int = 10_000, n_steps: int = 100_000,
                seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """
    One continuous random walk; record position after every n_steps steps.
    Each chunk of n_steps is vectorised; only one chunk lives in memory at once.
    """
    rng = np.random.default_rng(seed)
    pos_x = np.empty(n_sims)
    pos_y = np.empty(n_sims)
    x = y = 0.0

    t0 = time.perf_counter()
    for i in range(n_sims):
        r = rng.random(n_steps, dtype=np.float32)

        # Equal 25% each: +y < 0.25 | -y < 0.50 | +x < 0.75 | -x else
        dy = np.where(r < 0.25, np.int8(1),
             np.where(r < 0.50, np.int8(-1), np.int8(0)))
        dx = np.where(r >= 0.75, np.int8(-1),
             np.where(r >= 0.50, np.int8(1),  np.int8(0)))

        x += int(dx.sum())
        y += int(dy.sum())
        pos_x[i] = x
        pos_y[i] = y

        if (i + 1) % 500 == 0:
            elapsed = time.perf_counter() - t0
            rate = (i + 1) / elapsed
            print(f"\r  {i+1:>6,}/{n_sims:,} checkpoints  ({rate:.0f}/s)", end="", flush=True)

    print(f"\n  Done in {time.perf_counter() - t0:.1f}s")
    return pos_x, pos_y


print("=" * 60)
print("  Moon Rover  —  Chained Simulations")
print("  10,000 checkpoints, each 100,000 steps apart")
print("=" * 60)

x_pos, y_pos = run_chained()

# Checkpoint indices (1-based) and distances from origin
k = np.arange(1, len(x_pos) + 1)
distances = np.sqrt(x_pos**2 + y_pos**2)

# ── Theory ─────────────────────────────────────────────────────────────────────
# After k*n steps: Var[axis] = k*n*0.5  →  σ_axis(k) = √(k*50000)
# Distance ~ Rayleigh(σ_axis(k))  →  E[R(k)] = σ_axis(k) * √(π/2)
sigma_per_step = np.sqrt(0.5)             # per single step
sigma_axis_k   = np.sqrt(k * 100_000 * 0.5)
theory_mean_d  = sigma_axis_k * np.sqrt(np.pi / 2)

# Final checkpoint statistics
final_sigma  = sigma_axis_k[-1]
final_mean_d = theory_mean_d[-1]

# ── Statistics ─────────────────────────────────────────────────────────────────
mu_x, sd_x = x_pos.mean(), x_pos.std()
mu_y, sd_y = y_pos.mean(), y_pos.std()
pct = {p: np.percentile(distances, p) for p in [5, 25, 50, 75, 95]}

print(f"\n  Final position: ({x_pos[-1]:+.0f}, {y_pos[-1]:+.0f}) m")
print(f"\n  Across all 10,000 checkpoints:")
print(f"    Mean X / Y     : {mu_x:+.0f} / {mu_y:+.0f} m  (expected 0)")
print(f"\n  Distance from origin at each checkpoint:")
print(f"    Mean   : {distances.mean():,.0f} m")
print(f"    SD     : {distances.std():,.0f} m")
print(f"    Min    : {distances.min():,.0f} m  (checkpoint {distances.argmin()+1:,})")
print(f"    Max    : {distances.max():,.0f} m  (checkpoint {distances.argmax()+1:,})")
for p, v in pct.items():
    print(f"    P{p:<3}   : {v:,.0f} m")
print(f"\n  Theory: final mean distance = {final_mean_d:,.0f} m  (σ_axis = {final_sigma:,.0f} m)")

# ── Plotting ───────────────────────────────────────────────────────────────────

fig = plt.figure(figsize=(18, 14), facecolor="#0d0d1a")
fig.suptitle(
    "Moon Rover  —  Chained Simulations  (each run starts where the last ended)\n"
    "One continuous random walk  ·  10,000 checkpoints  ×  100,000 steps",
    fontsize=15, fontweight="bold", color="white", y=0.99
)

gs = GridSpec(2, 3, figure=fig, hspace=0.42, wspace=0.38,
              left=0.06, right=0.97, top=0.93, bottom=0.08)

DARK  = "#0d0d1a"
PANEL = "#14142b"
TEXT  = "#e0e0f0"
CMAP  = "plasma"

def style_ax(ax, title, xlabel, ylabel):
    ax.set_facecolor(PANEL)
    ax.set_title(title, color=TEXT, fontsize=11, pad=8)
    ax.set_xlabel(xlabel, color=TEXT, fontsize=9)
    ax.set_ylabel(ylabel, color=TEXT, fontsize=9)
    ax.tick_params(colors=TEXT, labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333355")
    ax.grid(True, color="#222244", linewidth=0.5, linestyle="--")


# ── 1. 2-D path colored by time ────────────────────────────────────────────────
ax1 = fig.add_subplot(gs[0, 0])
sc = ax1.scatter(x_pos, y_pos, c=k, cmap=CMAP, s=1.5, alpha=0.4, rasterized=True)
cb1 = plt.colorbar(sc, ax=ax1, pad=0.02)
cb1.ax.yaxis.set_tick_params(color=TEXT, labelsize=7)
cb1.set_label("Checkpoint #", color=TEXT, fontsize=8)
plt.setp(cb1.ax.yaxis.get_ticklabels(), color=TEXT)

ax1.scatter(0, 0, c="red", s=100, marker="*", zorder=6, label="Start (0,0)")
ax1.scatter(x_pos[-1], y_pos[-1], c="lime", s=60, marker="X", zorder=6,
            label=f"End ({x_pos[-1]:+.0f}, {y_pos[-1]:+.0f}) m")
ax1.legend(fontsize=7, facecolor=PANEL, labelcolor=TEXT, edgecolor="#333355")
ax1.set_aspect("equal")
style_ax(ax1, "2-D Path  (color = time)", "X Position (m)", "Y Position (m)")


# ── 2. Distance from origin vs checkpoint number ───────────────────────────────
ax2 = fig.add_subplot(gs[0, 1])
ax2.plot(k, distances, color="#22aacc", lw=0.6, alpha=0.7, label="Distance from origin")
ax2.plot(k, theory_mean_d, color="orange", lw=2, linestyle="--",
         label=r"Theory $E[R] = \sigma_{axis}(k)\sqrt{\pi/2}$")
ax2.fill_between(k,
                 sigma_axis_k * stats.rayleigh.ppf(0.10),
                 sigma_axis_k * stats.rayleigh.ppf(0.90),
                 alpha=0.15, color="orange", label="10th–90th pct (theory)")
ax2.legend(fontsize=7, facecolor=PANEL, labelcolor=TEXT, edgecolor="#333355")
style_ax(ax2, "Distance from Origin  vs  Checkpoint",
         "Checkpoint #", "Distance (m)")


# ── 3. 2-D density heatmap of all visited checkpoints ─────────────────────────
ax3 = fig.add_subplot(gs[0, 2])
h, xed, yed, img = ax3.hist2d(x_pos, y_pos, bins=100, cmap="inferno",
                               norm=mcolors.LogNorm())
cb3 = plt.colorbar(img, ax=ax3, pad=0.02)
cb3.ax.yaxis.set_tick_params(color=TEXT, labelsize=7)
cb3.set_label("Count (log scale)", color=TEXT, fontsize=8)
plt.setp(cb3.ax.yaxis.get_ticklabels(), color=TEXT)
ax3.scatter(0, 0, c="red", s=60, marker="*", zorder=6)
ax3.set_aspect("equal")
style_ax(ax3, "Checkpoint Density Heatmap", "X Position (m)", "Y Position (m)")


# ── 4. X and Y positions over time ────────────────────────────────────────────
ax4 = fig.add_subplot(gs[1, 0])
ax4.plot(k, x_pos, color="#5588ff", lw=0.5, alpha=0.8, label="X position")
ax4.plot(k, y_pos, color="#ff8844", lw=0.5, alpha=0.8, label="Y position")
# ±1σ envelope
ax4.fill_between(k, -sigma_axis_k, sigma_axis_k,
                 alpha=0.10, color="white", label="±1σ (theory)")
ax4.fill_between(k, -2*sigma_axis_k, 2*sigma_axis_k,
                 alpha=0.06, color="white", label="±2σ (theory)")
ax4.axhline(0, color="red", lw=0.8, linestyle=":")
ax4.legend(fontsize=7, facecolor=PANEL, labelcolor=TEXT, edgecolor="#333355", ncol=2)
style_ax(ax4, "X and Y Positions Over Time", "Checkpoint #", "Position (m)")


# ── 5. Distance histogram across all checkpoints ──────────────────────────────
ax5 = fig.add_subplot(gs[1, 1])
n_bins = 80
counts_d, edges_d = np.histogram(distances, bins=n_bins)
centers_d = (edges_d[:-1] + edges_d[1:]) / 2
width_d   = edges_d[1] - edges_d[0]
probs_d   = counts_d / counts_d.sum()

ax5.bar(centers_d, probs_d, width=width_d,
        color="#22aacc", edgecolor="#115577", alpha=0.85,
        label="Checkpoint distances")
ax5.axvline(distances.mean(), color="white", lw=1.5, linestyle="--",
            label=f"Observed mean = {distances.mean():,.0f} m")
ax5.axvline(distances.max(), color="lime", lw=1, linestyle=":",
            label=f"Max = {distances.max():,.0f} m")
ax5.legend(fontsize=7.5, facecolor=PANEL, labelcolor=TEXT, edgecolor="#333355")
style_ax(ax5,
         "Distribution of Checkpoint Distances\n(mixture of Rayleigh — not a single Rayleigh)",
         "Distance from Origin (m)", "Probability")


# ── 6. Distance sqrt-scaled to verify growth law ──────────────────────────────
ax6 = fig.add_subplot(gs[1, 2])
# Normalise by √k — should fluctuate around a constant (σ_axis * √(n_steps) * √(π/2))
scale_factor = np.sqrt(np.pi / 2) * np.sqrt(100_000 * 0.5)  # theory E[R]/√k
normalised = distances / np.sqrt(k)
ax6.plot(k, normalised, color="#22aacc", lw=0.5, alpha=0.7, label=r"Distance / $\sqrt{k}$")
ax6.axhline(scale_factor, color="orange", lw=2, linestyle="--",
            label=f"Theory: {scale_factor:.1f} m/√checkpoint")
ax6.axhline(normalised.mean(), color="white", lw=1.2, linestyle=":",
            label=f"Observed mean: {normalised.mean():.1f} m/√checkpoint")
ax6.set_ylim(0, normalised.max() * 1.1)
ax6.legend(fontsize=7.5, facecolor=PANEL, labelcolor=TEXT, edgecolor="#333355")
style_ax(ax6, r"Distance / $\sqrt{k}$  — verifying $\sqrt{k}$ growth law",
         "Checkpoint #", r"Distance / $\sqrt{k}$  (m)")


# ── Stats annotation ───────────────────────────────────────────────────────────
stats_lines = (
    f"Movement probabilities          Simulation results\n"
    f"  +Y / −Y / +X / −X : 25% ea.  Final pos  : ({x_pos[-1]:+.0f}, {y_pos[-1]:+.0f}) m\n"
    f"  Steps / checkpoint : 100,000  Max dist   : {distances.max():>10,.0f} m  (chkpt {distances.argmax()+1:,})\n"
    f"  # checkpoints      :  10,000  Min dist   : {distances.min():>10,.0f} m  (chkpt {distances.argmin()+1:,})\n"
    f"  Total steps        :   1 B    Mean dist  : {distances.mean():>10,.0f} m\n"
    f"                                Theory mean: {final_mean_d:>10,.0f} m  (at final chkpt)\n"
    f"  Distance grows as √k × {scale_factor:.1f} m   (confirmed: {normalised.mean():.1f} m observed)"
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
