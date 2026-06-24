"""Render just the 2-D path panel at high resolution, reusing saved positions."""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.collections import LineCollection

# ── Re-run simulation to recover positions ─────────────────────────────────────
from scipy import stats
import time

def run_chained(n_sims=10_000, n_steps=100_000, seed=42):
    rng = np.random.default_rng(seed)
    pos_x = np.empty(n_sims)
    pos_y = np.empty(n_sims)
    x = y = 0.0
    t0 = time.perf_counter()
    for i in range(n_sims):
        r = rng.random(n_steps, dtype=np.float32)
        dy = np.where(r < 0.25, np.int8(1),  np.where(r < 0.50, np.int8(-1), np.int8(0)))
        dx = np.where(r >= 0.75, np.int8(-1), np.where(r >= 0.50, np.int8(1),  np.int8(0)))
        x += int(dx.sum())
        y += int(dy.sum())
        pos_x[i] = x
        pos_y[i] = y
        if (i + 1) % 1000 == 0:
            print(f"\r  {i+1:,}/{n_sims:,}", end="", flush=True)
    print(f"  ({time.perf_counter()-t0:.1f}s)")
    return pos_x, pos_y

print("Regenerating positions...")
x_pos, y_pos = run_chained()
k = np.arange(1, len(x_pos) + 1)

# ── Plot ───────────────────────────────────────────────────────────────────────
DARK  = "#0d0d1a"
PANEL = "#0a0a1a"
TEXT  = "#e8e8ff"

fig, ax = plt.subplots(figsize=(14, 14), facecolor=DARK)
ax.set_facecolor(PANEL)

# Draw path as a colored line (segments coloured by checkpoint number)
points = np.column_stack([x_pos, y_pos]).reshape(-1, 1, 2)
segments = np.concatenate([points[:-1], points[1:]], axis=1)
norm = mcolors.Normalize(vmin=1, vmax=len(k))
lc = LineCollection(segments, cmap="plasma", norm=norm, linewidth=0.35, alpha=0.55)
lc.set_array(k[:-1])
ax.add_collection(lc)

# Scatter the checkpoints on top, smaller alpha so line dominates
sc = ax.scatter(x_pos, y_pos, c=k, cmap="plasma", norm=norm,
                s=1.2, alpha=0.25, rasterized=False, zorder=3)

# Origin and end markers
ax.scatter(0, 0, c="red", s=220, marker="*", zorder=6,
           edgecolors="white", linewidths=0.5, label="Start  (0, 0)")
ax.scatter(x_pos[-1], y_pos[-1], c="lime", s=140, marker="X", zorder=6,
           linewidths=1.5, label=f"End  ({x_pos[-1]:+.0f}, {y_pos[-1]:+.0f}) m")

# Colorbar
cb = plt.colorbar(sc, ax=ax, fraction=0.035, pad=0.02)
cb.set_label("Checkpoint  #", color=TEXT, fontsize=13)
cb.ax.yaxis.set_tick_params(color=TEXT, labelsize=10)
plt.setp(cb.ax.yaxis.get_ticklabels(), color=TEXT)

# Labels and style
ax.set_title("Moon Rover  —  2-D Path  (colour = time)\n"
             "1 continuous random walk  ·  10,000 checkpoints  ×  100,000 steps each",
             color=TEXT, fontsize=15, fontweight="bold", pad=16)
ax.set_xlabel("X Position  (m)", color=TEXT, fontsize=13)
ax.set_ylabel("Y Position  (m)", color=TEXT, fontsize=13)
ax.tick_params(colors=TEXT, labelsize=11)
for spine in ax.spines.values():
    spine.set_edgecolor("#334466")
ax.grid(True, color="#1a1a3a", linewidth=0.6, linestyle="--")
ax.set_aspect("equal")
ax.legend(fontsize=11, facecolor="#14142b", labelcolor=TEXT,
          edgecolor="#334466", markerscale=2)

plt.tight_layout()
out = "/home/user/cv19/moon_rover_path_hd.png"
plt.savefig(out, dpi=300, bbox_inches="tight", facecolor=DARK)
print(f"Saved → {out}")
plt.close()
