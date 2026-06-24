"""
Moon Rover Monte Carlo Simulation
----------------------------------
Movement rules (discrete 1-meter steps, one axis at a time):
  +y : 25.0%
  -y : 25.0%
  +x : 25.0%
  -x : 25.0%

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

        # Equal 25% thresholds: +y < 0.25 | -y < 0.50 | +x < 0.75 | -x else
        dy = np.where(r < 0.25, np.int8(1),
             np.where(r < 0.50, np.int8(-1), np.int8(0)))

        dx = np.where(r >= 0.75, np.int8(-1),
             np.where(r >= 0.50, np.int8(1),  np.int8(0)))

        final_x[start:start + n] = dx.sum(axis=1)
        final_y[start:start + n] = dy.sum(axis=1)

        elapsed = time.perf_counter() - t0
        done = start + n
        rate = done / elapsed if elapsed > 0 else 0
        print(f"\r  {done:>6,}/{n_sims:,} simulations  ({rate:.0f}/s)", end="", flush=True)

    print(f"\n  Done in {time.perf_counter() - t0:.1f}s")
    return final_x.astype(np.float64), final_y.astype(np.float64)


print("=" * 60)
print("  Moon Rover Monte Carlo Simulation  (equal probabilities)")
print("  10,000 sims × 100,000 steps")
print("=" * 60)

x_pos, y_pos = run_monte_carlo()
distances = np.sqrt(x_pos**2 + y_pos**2)

# ── Theoretical values (symmetric 2-D random walk) ────────────────────────────
# Each axis: Var[step] = (0.25)(1²) + (0.25)(1²) = 0.5  →  SD = √(n × 0.5)
sigma_axis  = np.sqrt(100_000 * 0.5)          # ~223.6 m per axis
# Distance ~ Rayleigh(σ_axis): E[R] = σ√(π/2), Mode = σ
rayleigh_sigma = sigma_axis
theory_mean_d  = rayleigh_sigma * np.sqrt(np.pi / 2)
theory_mode_d  = rayleigh_sigma

# ── Statistics ─────────────────────────────────────────────────────────────────

mu_d,  sd_d  = distances.mean(), distances.std()
mu_x,  sd_x  = x_pos.mean(),    x_pos.std()
mu_y,  sd_y  = y_pos.mean(),    y_pos.std()
pct = {p: np.percentile(distances, p) for p in [5, 10, 25, 50, 75, 90, 95]}

print(f"\n  Expected mean Y / X (theory): 0 m")
print(f"  Observed mean Y:              {mu_y:+.1f} m")
print(f"  Observed mean X:              {mu_x:+.1f} m")
print(f"\n  Per-axis SD (theory):  {sigma_axis:,.1f} m")
print(f"  Observed SD Y:         {sd_y:,.1f} m")
print(f"  Observed SD X:         {sd_x:,.1f} m")
print(f"\n  Distance from origin  (Rayleigh theory):")
print(f"    Theory mean : {theory_mean_d:,.1f} m")
print(f"    Theory mode : {theory_mode_d:,.1f} m")
print(f"    Obs. mean   : {mu_d:,.1f} m")
print(f"    Obs. SD     : {sd_d:,.1f} m")
print(f"    Min / Max   : {distances.min():,.0f} / {distances.max():,.0f} m")
for p, v in pct.items():
    print(f"    P{p:<3}        : {v:,.0f} m")

# ── Plotting ───────────────────────────────────────────────────────────────────

fig = plt.figure(figsize=(18, 14), facecolor="#0d0d1a")
fig.suptitle(
    "Moon Rover Monte Carlo Simulation  —  Equal Probabilities (25% each)\n"
    "10,000 simulations  ×  100,000 steps each",
    fontsize=16, fontweight="bold", color="white", y=0.99
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

# Draw reference circles at 1σ and 2σ
theta = np.linspace(0, 2 * np.pi, 300)
for mult, lbl in [(1, "1σ"), (2, "2σ")]:
    r_circle = mult * sigma_axis
    ax1.plot(r_circle * np.cos(theta), r_circle * np.sin(theta),
             "w--", lw=0.8, alpha=0.5)
    ax1.text(0, r_circle, lbl, color="white", fontsize=7,
             ha="center", va="bottom", alpha=0.7)

ax1.scatter(0, 0, c="red", s=100, marker="*", zorder=6, label="Origin (0,0)")
ax1.scatter(mu_x, mu_y, c="cyan", s=60, marker="+", zorder=6,
            linewidths=2, label=f"Mean ({mu_x:.0f}, {mu_y:.0f}) m")
ax1.legend(fontsize=7, facecolor=PANEL, labelcolor=TEXT, edgecolor="#333355")
ax1.set_aspect("equal")
style_ax(ax1, "Final Rover Positions  (circular diffusion)", "X Position (m)", "Y Position (m)")


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
ax2.set_aspect("equal")
style_ax(ax2, "Position Density Heatmap", "X Position (m)", "Y Position (m)")


# ── 3. X-position marginal ─────────────────────────────────────────────────────
ax3 = fig.add_subplot(gs[0, 2])
ax3.hist(x_pos, bins=60, color="#5588ff", edgecolor="#223388", alpha=0.8, density=True)
mu_xf, sd_xf = stats.norm.fit(x_pos)
xf = np.linspace(x_pos.min(), x_pos.max(), 400)
ax3.plot(xf, stats.norm.pdf(xf, mu_xf, sd_xf), "w--", lw=1.5,
         label=f"Normal fit  μ={mu_xf:.0f}, σ={sd_xf:.0f} m\n(theory σ={sigma_axis:.0f} m)")
ax3.axvline(0, color="red", lw=1, linestyle=":", alpha=0.8)
ax3.legend(fontsize=7, facecolor=PANEL, labelcolor=TEXT, edgecolor="#333355")
style_ax(ax3, "X-Position Distribution  (symmetric, zero drift)", "X Position (m)", "Density")


# ── 4. Distance probability histogram  +  Rayleigh fit ────────────────────────
ax4 = fig.add_subplot(gs[1, 0:2])
n_bins = 80
counts_d, edges_d = np.histogram(distances, bins=n_bins)
centers_d = (edges_d[:-1] + edges_d[1:]) / 2
width_d   = edges_d[1] - edges_d[0]
probs_d   = counts_d / counts_d.sum()

ax4.bar(centers_d, probs_d, width=width_d,
        color="#22aacc", edgecolor="#115577", alpha=0.85,
        label="Simulated probability")

# Rayleigh fit (theoretical distribution for 2-D symmetric random walk)
_, ray_scale = stats.rayleigh.fit(distances, floc=0)
df = np.linspace(0, distances.max() * 1.05, 600)
pdf_ray = stats.rayleigh.pdf(df, loc=0, scale=ray_scale) * width_d
ax4.plot(df, pdf_ray, color="orange", lw=2.5,
         label=f"Rayleigh fit   σ={ray_scale:,.0f} m  (theory {rayleigh_sigma:.0f} m)")

# Theory curve using exact σ
pdf_theory = stats.rayleigh.pdf(df, loc=0, scale=rayleigh_sigma) * width_d
ax4.plot(df, pdf_theory, color="#88ff88", lw=1.5, linestyle=":",
         label=f"Rayleigh theory  σ={rayleigh_sigma:.0f} m")

ax4.axvline(theory_mode_d, color="#ffaa44", lw=1.2, linestyle="--",
            label=f"Mode = {theory_mode_d:.0f} m  (= σ)")
ax4.axvline(theory_mean_d, color="white", lw=1.2, linestyle="--",
            label=f"Mean = {theory_mean_d:.0f} m  (= σ√π/2)")
ax4.axvline(pct[50], color="#88aaff", lw=1.2, linestyle=":",
            label=f"P50  = {pct[50]:.0f} m")

ax4.legend(fontsize=8, facecolor=PANEL, labelcolor=TEXT, edgecolor="#333355",
           loc="upper right", ncol=2)
style_ax(ax4,
         "Probability Distribution of Distance from Origin  —  Rayleigh Distribution",
         "Distance from Origin (m)", "Probability")


# ── 5. Cumulative distribution ─────────────────────────────────────────────────
ax5 = fig.add_subplot(gs[1, 2])
sorted_d = np.sort(distances)
cdf_emp  = np.linspace(1 / len(sorted_d), 1.0, len(sorted_d))
ax5.plot(sorted_d, cdf_emp, color="#22aacc", lw=2, label="Empirical CDF")

cdf_ray = stats.rayleigh.cdf(df, loc=0, scale=ray_scale)
ax5.plot(df, cdf_ray, "orange", lw=1.5, linestyle="--", label="Rayleigh fit CDF")

cdf_theory = stats.rayleigh.cdf(df, loc=0, scale=rayleigh_sigma)
ax5.plot(df, cdf_theory, "#88ff88", lw=1.2, linestyle=":", label="Rayleigh theory CDF")

for p in [10, 25, 50, 75, 90]:
    v = pct[p]
    ax5.axvline(v, color="gray", lw=0.8, linestyle=":", alpha=0.7)
    ax5.text(v + ray_scale * 0.03, p / 100, f"P{p}", fontsize=6.5,
             color="#aaaacc", va="center")

ax5.set_ylim(0, 1.05)
ax5.legend(fontsize=8, facecolor=PANEL, labelcolor=TEXT, edgecolor="#333355")
style_ax(ax5, "Cumulative Probability of Distance",
         "Distance from Origin (m)", "Cumulative Probability")


# ── Stats annotation ───────────────────────────────────────────────────────────
stats_lines = (
    f"Movement probabilities          Simulation results\n"
    f"  +Y (north)  : 25.0%           Mean Y pos : {mu_y:>+10.1f} m\n"
    f"  −Y (south)  : 25.0%           Mean X pos : {mu_x:>+10.1f} m\n"
    f"  +X (east)   : 25.0%           SD   Y pos : {sd_y:>10,.1f} m  (theory {sigma_axis:.1f} m)\n"
    f"  −X (west)   : 25.0%           SD   X pos : {sd_x:>10,.1f} m  (theory {sigma_axis:.1f} m)\n"
    f"                                 Mean dist  : {mu_d:>10,.1f} m  (theory {theory_mean_d:.1f} m)\n"
    f"Steps / sim   : 100,000         Mode dist  : {centers_d[probs_d.argmax()]:>10,.0f} m  (theory {theory_mode_d:.0f} m)\n"
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
