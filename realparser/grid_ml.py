#!/usr/bin/env python3
"""
Grid ML - split the map into cells and learn which side wins fights where.

The task
    Every row in the csv is one duel that ended in a death.
    Drop the death location into a grid cell and ask:
    "how often does CT come out of a fight in this cell as the killer?"
    y = 1 if the attacker was CT, y = 0 if the attacker was T

Why not the old hand-weighted score
    A W_KILL / W_DAMAGE formula can never be shown to be right or wrong,
    because there is nothing to check it against. "Who won the duel" is
    already in the data, so the model can actually be scored.

Two things that keep the numbers honest
    1. Split train/test with GroupKFold, grouped by match.
       A plain random row split puts kills from the same match on both
       sides of the split, which makes the score look better than it is.
    2. Only location is used as a feature.
       headshot / distance / weapon are all known only after the duel is
       over - feeding them in would be cheating.

Run:  python realparser/grid_ml.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

# ---------------------------------------------------------------- CONFIG ----
GRID_N = 16          # cells per side; finer grid = sharper detail, less data per cell
N_SPLITS = 5         # number of folds
MIN_KILLS = 5        # cells with fewer kills than this are left blank - too noisy

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "realparser" / "all_kills_25demos.csv"
OUT = ROOT / "output"


# -------------------------------------------------- 1) load data + grid it ----
df = pd.read_csv(CSV)
n_raw = len(df)

# Drop rows that are not a duel between the two sides: fall damage, self-inflicted
# grenade kills, team kills.
df = df[df["attacker_side"].notna() & (df["attacker_side"] != df["victim_side"])].copy()

# This csv is several demos concatenated with no column saying which file a row
# came from. But round_num and tick both restart at every new demo, so a drop in
# either value marks a boundary between files.
df["match_id"] = ((df["round_num"].diff() < 0) | (df["tick"].diff() < 0)).cumsum()

df["y"] = (df["attacker_side"] == "ct").astype(int)

# Grid bounds come from the radar image, not from the data's own min/max. If they
# came from the data, the cells would shift every time a demo is added and results
# from different runs could no longer be compared.
radar = json.loads((ROOT / "assets" / "radars.json").read_text(encoding="utf-8"))["de_dust2"]
span = radar["size"] * radar["scale"]
x0, y1 = radar["pos_x"], radar["pos_y"]          # top-left corner, in game units
x1, y0 = x0 + span, y1 - span                    # bottom-right corner
cell_w = cell_h = span / GRID_N

df["cx"] = np.clip((df["victim_X"] - x0) // cell_w, 0, GRID_N - 1).astype(int)
df["cy"] = np.clip((df["victim_Y"] - y0) // cell_h, 0, GRID_N - 1).astype(int)
df["cell"] = df["cx"].astype(str) + "_" + df["cy"].astype(str)

print(f"{n_raw} rows -> {len(df)} usable | {df['match_id'].nunique()} matches | "
      f"{GRID_N}x{GRID_N} grid, {df['cell'].nunique()} cells with kills")


# ------------------------------------------------------- 2) train + score ----
# One 0/1 column per cell, so the model learns each cell's value independently.
# Safe to do before splitting: this step never touches y, so nothing leaks.
X = pd.get_dummies(df["cell"])
y = df["y"].to_numpy()

# Low C penalises extreme values, pulling cells with only a few kills back
# towards 50/50 instead of letting them swing to 0 or 1.
model = LogisticRegression(C=0.3, max_iter=2000)

pred_grid = np.zeros(len(df))     # what the model predicts
pred_base = np.zeros(len(df))     # baseline: ignore location, predict the overall mean

for tr, te in GroupKFold(n_splits=N_SPLITS).split(X, y, df["match_id"]):
    pred_base[te] = y[tr].mean()
    pred_grid[te] = model.fit(X.iloc[tr], y[tr]).predict_proba(X.iloc[te])[:, 1]

brier_base = brier_score_loss(y, pred_base)
brier_grid = brier_score_loss(y, pred_grid)

print(f"\nGroupKFold, {N_SPLITS} folds, grouped by match | CT duel win rate {y.mean():.3f}")
print(f"  baseline (overall mean)   Brier {brier_base:.4f}")
print(f"  {GRID_N}x{GRID_N} grid              Brier {brier_grid:.4f}   "
      f"AUC {roc_auc_score(y, pred_grid):.3f}   "
      f"{(1 - brier_grid / brier_base) * 100:+.1f}% vs baseline")
print("  Lower Brier is better | AUC 0.5 = coin flip | the baseline is the bar to clear")


# ------------------------------------------------- 3) per-cell table + map ----
# Refit on everything just for the picture - not the model that was scored above.
df["pred"] = model.fit(X, y).predict_proba(X)[:, 1]

cells = df.groupby(["cx", "cy"]).agg(
    kills=("y", "size"),
    ct_win=("y", "mean"),
    pred=("pred", "mean"),
    place=("victim_place", lambda s: s.mode().iloc[0]),
).reset_index().sort_values("kills", ascending=False)

print("\nTop 5 cells by number of fights")
print(cells.head(5).to_string(index=False, formatters={"ct_win": "{:.2f}".format,
                                                       "pred": "{:.2f}".format}))

# Lay the per-cell values out in (GRID_N, GRID_N) arrays for pcolormesh.
kills = np.zeros((GRID_N, GRID_N))
adv = np.full((GRID_N, GRID_N), np.nan)
for r in cells.itertuples():
    kills[r.cy, r.cx] = r.kills
    if r.kills >= MIN_KILLS:
        adv[r.cy, r.cx] = r.pred

from PIL import Image
img = np.asarray(Image.open(ROOT / "assets" / radar["image"].lstrip("/")).convert("RGB"))
xe, ye = np.linspace(x0, x1, GRID_N + 1), np.linspace(y0, y1, GRID_N + 1)

fig, axes = plt.subplots(1, 2, figsize=(16, 8))
panels = [(np.where(kills > 0, kills, np.nan), "Reds", {},
           "Where fights happen - kills per cell", "kills"),
          (adv, "coolwarm_r", dict(vmin=0.25, vmax=0.75),
           "Who holds the edge (blue = CT, red = T)", "P(CT wins the duel)")]

for ax, (grid, cmap, lim, title, label) in zip(axes, panels):
    ax.imshow(img, extent=[x0, x1, y0, y1], origin="upper")
    mesh = ax.pcolormesh(xe, ye, np.ma.masked_invalid(grid), cmap=cmap, alpha=0.6, **lim)
    fig.colorbar(mesh, ax=ax, shrink=0.7, label=label)
    ax.set_title(title)
    ax.set_xticks([]); ax.set_yticks([])

fig.suptitle(f"de_dust2 · {GRID_N}x{GRID_N} grid · {len(df)} kills from "
             f"{df['match_id'].nunique()} matches"
             f"  (right panel skips cells with fewer than {MIN_KILLS} kills)")
fig.tight_layout()

OUT.mkdir(exist_ok=True)
fig.savefig(OUT / "grid_ml_map.png", dpi=140)
cells.to_csv(OUT / "grid_ml_cells.csv", index=False)
print(f"\n-> {OUT / 'grid_ml_map.png'}\n-> {OUT / 'grid_ml_cells.csv'}")
