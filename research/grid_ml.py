#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Grid ML — แบ่งแมพเป็นตาราง แล้วให้โมเดลเรียนว่า "ตรงไหนฝั่งไหนได้เปรียบ"

    python research/grid_ml.py

โจทย์
    ทุกแถวใน csv คือการดวลหนึ่งครั้งที่จบด้วยมีคนตาย
    เอาพิกัดจุดที่คนตายหย่อนลงช่องกริด แล้วถามว่า
    "การดวลในช่องนี้ ฝ่าย CT เป็นคนยิงชนะกี่เปอร์เซ็นต์"
    เฉลย y = 1 ถ้าคนยิงเป็น CT, y = 0 ถ้าคนยิงเป็น T

ทำไมโจทย์นี้ดีกว่าสูตรให้คะแนนที่ตั้งน้ำหนักเอง
    สูตรแบบ kill*3 + damage*0.1 พิสูจน์ไม่ได้ว่าถูกหรือผิด เพราะไม่มีอะไรมาตรวจ
    แต่ "ใครชนะการดวล" มีคำตอบอยู่ในข้อมูลอยู่แล้ว จึงวัดคะแนนโมเดลได้ตรง ๆ

สองอย่างที่ทำให้ตัวเลขไม่หลอกตัวเอง
    1. แบ่ง train/test ด้วย GroupKFold โดย group = แมตช์
       ถ้าสุ่มแบ่งรายแถว คิลจากแมตช์เดียวกันจะไปโผล่ทั้งสองฝั่ง คะแนนจะสวยเกินจริง
    2. ใช้แค่ตำแหน่งเป็นฟีเจอร์
       headshot / distance / weapon รู้ได้หลังดวลจบแล้ว ใส่เข้าไปคือโกงตัวเอง
"""
import base64  # Base64 encoding/decoding
import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")            # วาดลงไฟล์ ไม่ต้องมีหน้าจอ
import matplotlib.pyplot as plt
from PIL import Image, ImageFilter
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

# ===========================================================================
# CONFIG — ปรับตรงนี้ที่เดียว
# ===========================================================================
MAP = "de_mirage"  # แมพที่วิเคราะห์ — csv จะถูกกรองเหลือเฉพาะแมพนี้ก่อนใช้งาน
GRID_N = 32        # แบ่งแมพเป็นกี่ช่องต่อด้าน — 32 ให้คะแนนดีที่สุดจากการไล่ลอง
                   #   8 -> +10.0% | 16 -> +14.5% | 32 -> +16.9% | 40 -> +15.3%
                   #   เกิน 32 แล้วแย่ลง เพราะเหลือคิลเฉลี่ยช่องละ 20 ครั้ง น้อยเกินจะสรุป
N_SPLITS = 5       # แบ่งข้อมูลเป็นกี่กองตอนวัดผล
MIN_KILLS = 5      # ช่องที่มีดวลน้อยกว่านี้ ปล่อยว่างในรูป เพราะน้อยเกินกว่าจะสรุป
C_PENALTY = 0.3    # ยิ่งต่ำยิ่งดึงช่องที่ข้อมูลน้อยกลับเข้าหาค่าเฉลี่ย ไม่ให้สวิงไป 0 หรือ 1

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "all_kills.csv"     # สร้างด้วย python research/demoparser.py (ทางถอยเมื่อไม่มี DB)
OUT = ROOT / "output"

# แหล่งข้อมูล: auto = ลอง PostgreSQL ก่อน (เดโมที่อัปโหลดผ่านเว็บอยู่ที่นั่น) ต่อไม่ได้ค่อยถอยไป csv
#   python research/grid_ml.py --source=db     บังคับ DB
#   python research/grid_ml.py --source=csv    บังคับ csv (Docker ที่ไม่มี DB)
SOURCE = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--source=")), "auto")
sys.path.insert(0, str(ROOT))                   # ให้ import research.datasource ได้เมื่อรันเป็นสคริปต์
from research.datasource import load_kills  # noqa: E402

for _s in (sys.stdout, sys.stderr):     # ให้คอนโซล Windows พิมพ์ไทยได้
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


# ===========================================================================
# STEP 1 — โหลดข้อมูล
# ===========================================================================
# กรองให้เหลือแมพเดียว (load_kills ทำให้) เพราะกริดผูกกับภาพเรดาร์ของแมพนั้น
# เอาพิกัดจากคนละแมพมาปนกันคือหย่อนจุดลงตารางที่ไม่ใช่ของมัน ผลจะมั่วโดยไม่มี error
df = load_kills(MAP, source=SOURCE)
SOURCE_DESC = df.attrs.get("source", SOURCE)
n_raw = len(df)
if df.empty:
    sys.exit(f"ไม่มีข้อมูลแมพ {MAP} ใน {SOURCE_DESC}")
print(f"แหล่งข้อมูล: {SOURCE_DESC}")


# ===========================================================================
# STEP 2 — หาว่าแต่ละแถวมาจากเดโมไฟล์ไหน
# ===========================================================================
# ตัว parse ติดชื่อไฟล์มาให้ในคอลัมน์ demo_file แล้ว จึงใช้ได้ตรง ๆ
#
# csv รุ่นเก่าไม่มีคอลัมน์นี้ ต้องเดาเอาจาก tick: พอขึ้นไฟล์ใหม่ tick (นาฬิกาในเกม)
# จะรีเซ็ตกลับไปค่าน้อย ผลต่างจากแถวก่อนหน้าจึงติดลบตรงรอยต่อพอดี
# วิธีนั้นพังเงียบ ๆ ถ้ามีใคร sort ตารางก่อน — เก็บไว้เป็นทางถอยของ csv รุ่นเก่าเท่านั้น
if "demo_file" in df.columns:
    df["match_id"] = df["demo_file"]
else:
    df["match_id"] = (df["tick"].diff() < 0).cumsum()


# ===========================================================================
# STEP 3 — บริบทของรอบ ณ ตอนที่การดวลเริ่ม
# ===========================================================================
# กฎเดียวที่ห้ามผิด: ฟีเจอร์ต้องเป็นสิ่งที่ "รู้ได้ก่อนการดวลจะจบ"
#   ใช้ได้   คนเหลือกี่ต่อกี่ / ระเบิดลงหรือยัง / นาทีที่เท่าไรของรอบ
#   ใช้ไม่ได้ headshot, weapon, distance — สามอย่างนี้รู้ได้ก็ต่อเมื่อดวลจบไปแล้ว
#            ใส่เข้าไปคะแนนจะสวยขึ้นทันทีแบบหลอกตัวเอง
#
# นับคนเหลือจาก "การตายทุกแบบ" ไม่ใช่เฉพาะการดวล เพราะตกที่สูงหรือโดนทีมคิล
# ก็ทำให้คนในทีมหายไปจริง ๆ จึงต้องนับก่อนกรองเหลือเฉพาะการดวลในสเต็ปถัดไป
df = df.sort_values(["match_id", "round_num", "tick"], kind="stable")
grp = df.groupby(["match_id", "round_num"], sort=False)

# cumcount แบบเลื่อนหนึ่งช่อง = "ก่อนแถวนี้ ฝั่งนั้นตายไปแล้วกี่คน"
# ต้องเป็น "ก่อน" ไม่ใช่ "รวมแถวนี้" ไม่งั้นคือรู้ผลการดวลที่กำลังจะทายอยู่แล้ว
dead_ct = grp["victim_side"].transform(lambda s: (s == "ct").cumsum().shift(1).fillna(0))
dead_t = grp["victim_side"].transform(lambda s: (s == "t").cumsum().shift(1).fillna(0))
df["alive_ct"] = (5 - dead_ct).clip(0, 5)
df["alive_t"] = (5 - dead_t).clip(0, 5)
df["adv"] = df["alive_ct"] - df["alive_t"]          # บวก = CT มีคนมากกว่า

if "round_start_tick" in df.columns:
    rate = df["tickrate"].fillna(128)
    df["t_round"] = (df["tick"] - df["round_start_tick"]) / rate
    df["planted"] = (df["bomb_plant_tick"].notna() & (df["tick"] >= df["bomb_plant_tick"])).astype(int)
else:
    # csv รุ่นเก่าไม่มีบริบทรอบ — ให้ทุกแถวเป็นค่าเดียวกัน โมเดลที่ใช้ฟีเจอร์นี้จะกลายเป็น
    # โมเดลเดียวกับที่ไม่ใช้ ไม่ใช่ค่าที่มั่ว
    df["t_round"] = 0.0
    df["planted"] = 0
    print("!! csv ไม่มีคอลัมน์บริบทรอบ — รัน python research/demoparser.py --force ก่อน")


# ===========================================================================
# STEP 4 — เก็บเฉพาะการดวลจริง แล้วสร้างเฉลย
# ===========================================================================
#   ไม่มีคนยิง   = ตายเพราะ C4 ระเบิด หรือตกที่สูง -> attacker_side ว่าง
#   ฝั่งเดียวกัน = ทีมคิล
has_attacker = df["attacker_side"].notna()
enemy_duel = df["attacker_side"] != df["victim_side"]
df = df[has_attacker & enemy_duel].copy()

df["y"] = (df["attacker_side"] == "ct").astype(int)


# ===========================================================================
# STEP 5 — สองวิธีแบ่งพื้นที่: ตารางสี่เหลี่ยม กับ callout ของแมพเอง
# ===========================================================================
# ขอบเขตกริดเอาจากภาพเรดาร์ ไม่ใช่จากค่าต่ำสุด-สูงสุดของข้อมูล
# ถ้าเอาจากข้อมูล เส้นกริดจะขยับทุกครั้งที่เพิ่มเดโม แล้วผลรันคนละครั้งเทียบกันไม่ได้
radar = json.loads((ROOT / "assets" / "radars.json").read_text(encoding="utf-8"))[MAP]

span = radar["size"] * radar["scale"]      # 1024 พิกเซล x 6.056 = 6201 หน่วยในเกม
x_left = radar["pos_x"]                    # ขอบซ้ายของแมพ
y_top = radar["pos_y"]                     # ขอบบน (ค่ามาก เพราะแกน y ในเกมนับขึ้น)
x_right = x_left + span
y_bottom = y_top - span
cell_size = span / GRID_N                  # 6201 / 16 = 387.6 หน่วยต่อหนึ่งช่อง

# (พิกัด - ขอบ) // ขนาดช่อง = อยู่ช่องที่เท่าไร
# np.clip บีบให้อยู่ในช่วง 0 ถึง GRID_N-1 กันจุดที่ตกริมขอบพอดีหลุดออกนอกตาราง
df["cx"] = np.clip((df["victim_X"] - x_left) // cell_size, 0, GRID_N - 1).astype(int)
df["cy"] = np.clip((df["victim_Y"] - y_bottom) // cell_size, 0, GRID_N - 1).astype(int)
df["cell"] = df["cx"].astype(str) + "_" + df["cy"].astype(str)

# callout คือชื่อพื้นที่ที่ตัวเกมบอกมาเอง (BombsiteA, Catwalk, TRamp, ...)
# ขอบเขตของมันวิ่งตามผนังจริงของแมพ ไม่ใช่เส้นตรงที่เราขีดทับลงไป
# จึงไม่มีช่องไหนคาบเกี่ยวกำแพงครึ่งหนึ่งทางเดินครึ่งหนึ่งเหมือนตารางสี่เหลี่ยม
df["zone"] = df["victim_place"].fillna("Unknown")

print(f"{n_raw:,} แถว -> ใช้ได้ {len(df):,} การดวล | {df['match_id'].nunique()} แมตช์")
print(f"  ตาราง {GRID_N}x{GRID_N} มีคนตายจริง {df['cell'].nunique()} ช่อง")
print(f"  callout ของแมพ      {df['zone'].nunique()} โซน")


# ===========================================================================
# STEP 6 — เทียบสี่โมเดลบนชุดแบ่งเดียวกัน
# ===========================================================================
# ทุกโมเดลใช้ GroupKFold ชุดเดียวกัน (group = แมตช์) จึงเทียบกันได้ตรง ๆ
# ถ้าแบ่งคนละชุด ตัวเลขที่ต่างกันอาจมาจากการแบ่งที่โชคดีกว่า ไม่ใช่จากตัวโมเดล
y = df["y"].to_numpy()
groups = df["match_id"].to_numpy()
splits = list(GroupKFold(n_splits=N_SPLITS).split(df, y, groups))


def onehot(*cols):
    """แตกคอลัมน์หมวดหมู่เป็น 0/1 คอลัมน์ละค่า แล้วต่อกันเป็นตารางฟีเจอร์เดียว"""
    return pd.concat([pd.get_dummies(df[c], prefix=c) for c in cols], axis=1)


# แบ่งคนเหลือกี่ต่อกี่เป็นหมวด ไม่ใช่ตัวเลขต่อเนื่อง
# เพราะผลของ "+1 คน" ตอน 5v4 กับตอน 2v1 ไม่เท่ากัน การบังคับให้เป็นเส้นตรงจะบิดข้อมูล
adv_cat = df["adv"].clip(-4, 4).astype(int).astype(str)
# ต้นรอบกับท้ายรอบคนละเรื่องกัน แบ่งหยาบ ๆ พอ ไม่ต้องละเอียดจนแต่ละถังมีข้อมูลน้อย
time_cat = pd.cut(df["t_round"], [-1, 15, 30, 50, 1e9], labels=["0-15s", "15-30s", "30-50s", "50s+"])

# ฟีเจอร์บริบทของรอบ แยกออกมาเป็นก้อนเดียวเพื่อเอาไปผสมกับวิธีแบ่งพื้นที่แบบไหนก็ได้
situation = pd.concat([
    pd.get_dummies(adv_cat, prefix="adv"),
    pd.get_dummies(time_cat, prefix="t"),
    df[["planted"]],
], axis=1)

# ไล่จากง่ายไปยาก เพื่อตอบว่า "อะไรกันแน่ที่ทำให้คะแนนดีขึ้น"
# ถ้าใส่ทุกอย่างพร้อมกันตั้งแต่แรก จะรู้แค่ว่ารวม ๆ แล้วดี แต่ไม่รู้ว่าเพราะตัวไหน
GRID_LABEL = f"ตำแหน่ง: ตาราง {GRID_N}x{GRID_N}"
MODELS = {
    "สถานการณ์ล้วน": situation,
    "ตำแหน่ง: callout": onehot("zone"),
    GRID_LABEL: onehot("cell"),
    "callout + สถานการณ์": pd.concat([pd.get_dummies(df["zone"], prefix="zone"), situation], axis=1),
    "ตาราง + สถานการณ์": pd.concat([pd.get_dummies(df["cell"], prefix="cell"), situation], axis=1),
}

results = {}
pred_base = np.zeros(len(df))
for train_idx, test_idx in splits:
    pred_base[test_idx] = y[train_idx].mean()      # ใช้ค่าเฉลี่ยจากฝั่งสอนเท่านั้น
brier_base = brier_score_loss(y, pred_base)

for label, X in MODELS.items():
    Xv = X.to_numpy(dtype=float)
    pred = np.zeros(len(df))
    for train_idx, test_idx in splits:
        m = LogisticRegression(C=C_PENALTY, max_iter=2000)
        m.fit(Xv[train_idx], y[train_idx])
        # predict_proba คืนสองคอลัมน์ [โอกาสเป็น 0, โอกาสเป็น 1] เอาคอลัมน์ 1 = โอกาสที่คนยิงเป็น CT
        pred[test_idx] = m.predict_proba(Xv[test_idx])[:, 1]
    results[label] = {
        "brier": brier_score_loss(y, pred),
        "auc": roc_auc_score(y, pred),
        "gain_pct": (1 - brier_score_loss(y, pred) / brier_base) * 100,
        "n_features": Xv.shape[1],
    }

print(f"\nวัดผลด้วย GroupKFold {N_SPLITS} กอง แบ่งตามแมตช์ | คนยิงเป็น CT รวม {y.mean():.3f}")
print(f"  {'baseline (ไม่ดูอะไรเลย)':<26} Brier {brier_base:.4f}")
for label, r in results.items():
    print(f"  {label:<26} Brier {r['brier']:.4f}  AUC {r['auc']:.3f}  "
          f"{r['gain_pct']:+.1f}%  ({r['n_features']} ฟีเจอร์)")
print("  Brier ยิ่งต่ำยิ่งดี | AUC 0.5 = เดาสุ่ม | ต้องชนะ baseline ก่อนถึงจะมีความหมาย")

# ค่าที่ STEP ถัด ๆ ไปใช้ ยังยึดโมเดลตารางเป็นตัวหลักเพื่อวาดรูปกริดเหมือนเดิม
X = MODELS[GRID_LABEL]
model = LogisticRegression(C=C_PENALTY, max_iter=2000)
brier_grid = results[GRID_LABEL]["brier"]
auc = results[GRID_LABEL]["auc"]
gain_pct = results[GRID_LABEL]["gain_pct"]


# ===========================================================================
# STEP 6 — สรุปเป็นตารางรายช่อง
# ===========================================================================
# เทรนใหม่ด้วยข้อมูลทั้งหมด เพื่อเอาไปวาดรูปเท่านั้น
# ไม่ใช่โมเดลที่เอาไปคิดคะแนนข้างบน (ตัวนี้เห็นเฉลยครบทุกแถวแล้ว เอาไปวัดผลไม่ได้)
model.fit(X, y)
df["pred"] = model.predict_proba(X)[:, 1]

cells = df.groupby(["cx", "cy"]).agg(
    kills=("y", "size"),                                  # จำนวนดวลในช่องนี้
    ct_win=("y", "mean"),                                 # CT ชนะจริงกี่ส่วน
    pred=("pred", "mean"),                                # โมเดลทายเท่าไร
    place=("victim_place", lambda s: s.mode().iloc[0]),   # ชื่อ callout ที่พบบ่อยสุดในช่อง
).reset_index()
cells = cells.sort_values("kills", ascending=False)

print("\n5 ช่องที่ปะทะกันหนักสุด")
print(cells.head(5).to_string(index=False,
                              formatters={"ct_win": "{:.2f}".format, "pred": "{:.2f}".format}))


# ===========================================================================
# STEP 7 — วาดรูปสองช่องทับภาพเรดาร์
# ===========================================================================
# matplotlib วาดตารางสีจาก array 2 มิติ ที่เรียง index เป็น [แถว, คอลัมน์] = [y, x]
# ระวังสลับ ถ้าเขียน [cx, cy] รูปจะพลิกทแยงมุมโดยไม่มี error ให้รู้ตัว
kills_grid = np.full((GRID_N, GRID_N), np.nan)
edge_grid = np.full((GRID_N, GRID_N), np.nan)

for cell in cells.itertuples():
    kills_grid[cell.cy, cell.cx] = cell.kills
    if cell.kills >= MIN_KILLS:            # ช่องที่ข้อมูลน้อยเกิน ปล่อยเป็น nan = เว้นว่างในรูป
        edge_grid[cell.cy, cell.cx] = cell.pred

img = np.asarray(Image.open(ROOT / "assets" / radar["image"].lstrip("/")).convert("RGB"))
xe = np.linspace(x_left, x_right, GRID_N + 1)    # เส้นแบ่งช่อง มี 17 เส้นสำหรับ 16 ช่อง
ye = np.linspace(y_bottom, y_top, GRID_N + 1)
extent = [x_left, x_right, y_bottom, y_top]      # บอกว่าภาพเรดาร์กินพื้นที่พิกัดเกมช่วงไหน

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))

# --- ช่องซ้าย: ปะทะกันตรงไหนบ่อย ---
ax1.imshow(img, extent=extent, origin="upper")
mesh1 = ax1.pcolormesh(xe, ye, np.ma.masked_invalid(kills_grid), cmap="Reds", alpha=0.6)
fig.colorbar(mesh1, ax=ax1, shrink=0.7, label="kills")
ax1.set_title("Where fights happen - kills per cell")

# --- ช่องขวา: ตรงไหนใครได้เปรียบ ---
# vmin/vmax ตรึงสเกลสีไว้ตายตัว สีระดับเดียวกันจึงหมายถึงค่าเดียวกันเสมอทุกครั้งที่รัน
# coolwarm_r ที่ลงท้าย _r คือกลับด้านสี ให้ค่าสูง (CT ชนะ) เป็นน้ำเงินตามสีฝั่งในเกม
ax2.imshow(img, extent=extent, origin="upper")
mesh2 = ax2.pcolormesh(xe, ye, np.ma.masked_invalid(edge_grid),
                       cmap="coolwarm_r", alpha=0.6, vmin=0.25, vmax=0.75)
fig.colorbar(mesh2, ax=ax2, shrink=0.7, label="P(CT wins the duel)")
ax2.set_title("Who holds the edge (blue = CT, red = T)")

for ax in (ax1, ax2):
    ax.set_xticks([])
    ax.set_yticks([])

fig.suptitle(f"{MAP} · {GRID_N}x{GRID_N} grid · {len(df):,} duels from "
             f"{df['match_id'].nunique()} matches "
             f"(right panel skips cells with fewer than {MIN_KILLS} kills)")
fig.tight_layout()

OUT.mkdir(exist_ok=True)
fig.savefig(OUT / "grid_ml_map.png", dpi=140)
cells.to_csv(OUT / "grid_ml_cells.csv", index=False, encoding="utf-8-sig")

# ===========================================================================
# STEP 7.5 — หน้ากากพื้นที่ที่มีคนตายจริง
# ===========================================================================
# ปัญหาของตารางสี่เหลี่ยม: เส้นกริดไม่รู้จักผนัง ช่องหนึ่งจึงกินทั้งทางเดินและกำแพง
# เวลาทาสีทั้งช่อง สีเลยล้นออกไปนอกแมพ ดูเหมือนกริดวางเหลื่อมทั้งที่คณิตศาสตร์ถูก
#
# แก้ด้วยการทำหน้ากากจาก "จุดที่มีคนตายจริง" แล้วให้หน้าเว็บทาสีเฉพาะในหน้ากาก
# ไม่ได้วาดขอบเขตแมพขึ้นมาเอง — ขอบที่ได้จึงมาจากข้อมูล ไม่ใช่จากการเดาด้วยมือ
MASK_PX = 512                    # ทำที่ครึ่งความละเอียดของภาพเรดาร์ พอแล้วและไฟล์เล็กกว่าสี่เท่า
MASK_REACH = 9                   # ขยายรอบจุดกี่พิกเซล (~110 หน่วยในเกม) ให้จุดที่กระจายกันต่อกันติด

mask_img = Image.new("L", (MASK_PX, MASK_PX), 0)
px = mask_img.load()
scale_to_mask = MASK_PX / radar["size"]
for vx, vy in zip(df["victim_X"], df["victim_Y"]):
    mx = int((vx - x_left) / radar["scale"] * scale_to_mask)
    my = int((y_top - vy) / radar["scale"] * scale_to_mask)
    if 0 <= mx < MASK_PX and 0 <= my < MASK_PX:
        px[mx, my] = 255

# MaxFilter = ขยายจุดขาวออกไปรอบตัว จุดเดี่ยว ๆ ที่อยู่ใกล้กันจะเชื่อมเป็นผืนเดียว
# แล้ว blur+threshold อีกทีให้ขอบเรียบ ไม่เป็นฟันปลาตามตำแหน่งจุดดิบ
mask_img = mask_img.filter(ImageFilter.MaxFilter(MASK_REACH * 2 + 1))
mask_img = mask_img.filter(ImageFilter.GaussianBlur(3)).point(lambda v: 255 if v > 60 else 0)

_buf = io.BytesIO()
mask_img.save(_buf, format="png", optimize=True)
mask_uri = "data:image/png;base64," + base64.b64encode(_buf.getvalue()).decode()
print(f"\nหน้ากากพื้นที่: {MASK_PX}x{MASK_PX} ครอบคลุม "
      f"{np.count_nonzero(np.asarray(mask_img)) / MASK_PX**2:.0%} ของภาพ "
      f"({len(_buf.getvalue()) / 1024:.0f} KB)")


# ===========================================================================
# STEP 8 - เขียน json ก้อนเดียวให้หน้าเว็บใช้
# ===========================================================================
# หน้าเว็บใน frontend/ ต้องการทั้งค่ารายช่อง คะแนนโมเดล และค่าปรับเทียบเรดาร์
# ถ้าปล่อยให้มันไปอ่าน csv เองแล้วคำนวณซ้ำ ตัวเลขสองที่จะเริ่มเพี้ยนจากกันวันไหนก็ได้
# จึงให้ไฟล์นี้เป็นเจ้าของตัวเลขที่เดียว แล้ว dump ออกไปให้หน้าเว็บใช้ตรง ๆ
payload = {
    "map": MAP,
    "grid_n": GRID_N,
    "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),   # หน้าเว็บใช้บอกว่าผลเก่าแค่ไหน
    "source": SOURCE_DESC,                                                     # เทรนจาก DB หรือ csv
    "min_kills": MIN_KILLS,
    # ส่งค่าปรับเทียบไปด้วย หน้าเว็บจะได้แปลงพิกัดในเกม -> พิกเซลบนภาพเรดาร์ได้เอง
    "radar": {k: radar[k] for k in ("image", "size", "pos_x", "pos_y", "scale")},
    "metrics": {
        "matches": int(df["match_id"].nunique()),
        "duels": int(len(df)),
        "rows_raw": int(n_raw),
        "ct_win_overall": float(y.mean()),
        "brier_base": float(brier_base),
        "brier_grid": float(brier_grid),
        "auc": float(auc),
        "gain_pct": float(gain_pct),
        "n_splits": N_SPLITS,
    },
    "play_mask": mask_uri,      # png ขาว=พื้นที่มีคนตาย ดำ=นอกพื้นที่ ใช้เป็น mask ของ svg
    "cells": cells.to_dict(orient="records"),
    # จุดตายดิบ ไว้ให้หน้าเว็บวาดทับเป็น scatter - ปัดเป็นจำนวนเต็มพอ ไฟล์จะได้ไม่บวม
    "kills": [[int(r.victim_X), int(r.victim_Y), int(r.y)] for r in df.itertuples()],
}
(OUT / "grid_ml.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

print("\nเซฟแล้ว:")
for _f in ("grid_ml_map.png", "grid_ml_cells.csv", "grid_ml.json"):
    print(f"  {OUT / _f}")
