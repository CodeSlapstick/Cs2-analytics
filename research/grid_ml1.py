#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Grid ML (unsupervised) — ให้ข้อมูลจัดกลุ่มตัวเอง โดยไม่บอกโมเดลเลยว่าใครชนะ

    python research/models/grid_ml1.py

ต่างจาก grid_ml.py ตรงไหน
    grid_ml.py เป็น supervised: มีเฉลย (คนยิงเป็น CT หรือ T) ให้โมเดลเรียน แล้ววัดว่าทายถูกแค่ไหน
    ไฟล์นี้เป็น unsupervised: ซ่อนฝั่งไว้ตลอด ถามแค่ว่า "การปะทะบนแมพจัดกลุ่มตัวเองอย่างไร"

สองคำถาม สองอัลกอริทึม
    1. จุดปะทะอยู่ตรงไหน
       MeanShift บนพิกัดจุดตาย — ไต่ขึ้นหายอดความหนาแน่น จึงไม่ต้องบอกล่วงหน้าว่ามีกี่จุด
       บอกแค่รัศมีที่ถือว่า "อยู่ใกล้กัน" (BANDWIDTH เป็นหน่วยเกม)
    2. แต่ละช่องกริดเป็นการปะทะ "แบบไหน"
       สรุปโปรไฟล์ของช่อง (เกิดตอนไหนของรอบ / หลังวางระเบิดไหม / ดวลไกลแค่ไหน / ใช้ AWP บ่อยไหม)
       แล้ว KMeans จับช่องที่โปรไฟล์คล้ายกันไว้ด้วยกัน — ได้ "ประเภทพื้นที่" ที่ไม่มีใครตั้งชื่อให้ล่วงหน้า

unsupervised ไม่มีเฉลยให้เทียบ จึงต้องวัดสามอย่างแทน ไม่งั้นจะได้รูปสวยที่พิสูจน์อะไรไม่ได้
    1. silhouette        กลุ่มแยกจากกันชัดแค่ไหน — ใช้เลือกจำนวนกลุ่ม k
    2. เสถียรภาพ         สุ่มชุดแมตช์ใหม่ (bootstrap) แล้วดูว่ายังได้โครงสร้างเดิมไหม
                         ถ้าเปลี่ยนแมตช์แล้วกลุ่มเปลี่ยนหมด แปลว่าที่เจอคือ noise ไม่ใช่ตัวแมพ
    3. ตรวจกับของจริงทีหลัง เอา "ใครชนะ" ที่ซ่อนไว้ตลอดมาเทียบตอนจบ
                         ถ้ากลุ่มที่โมเดลหาเองแยกฝั่งที่ได้เปรียบออกจากกันได้ ทั้งที่ไม่เคยเห็นฝั่ง
                         แปลว่าโครงสร้างนั้นมีความหมายจริง
"""
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")            # วาดลงไฟล์ ไม่ต้องมีหน้าจอ
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Patch
from PIL import Image
from sklearn.cluster import KMeans, MeanShift
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

# ===========================================================================
# CONFIG — ปรับตรงนี้ที่เดียว
# ===========================================================================
MAP = "de_mirage"   # แมพที่วิเคราะห์ — csv จะถูกกรองเหลือเฉพาะแมพนี้ก่อนใช้งาน
GRID_N = 32         # แบ่งแมพเป็นกี่ช่องต่อด้าน — ใช้ค่าเดียวกับ grid_ml.py ช่องจะได้ตรงกัน เทียบกันได้
MIN_KILLS = 10      # ช่องต้องมีดวลอย่างน้อยเท่านี้ถึงจะสร้างโปรไฟล์ — สูงกว่า grid_ml.py (5)
                    #   เพราะโปรไฟล์เป็นสัดส่วน ถ้ามีแค่ 5 ดวล ค่าจะกระโดดทีละ 0.2 หยาบเกินจะจัดกลุ่ม
                    #   ที่ 10: เหลือ 192 จาก 341 ช่อง แต่ยังครอบคลุม 93% ของการดวลทั้งหมด

# --- คำถามที่ 1: จุดปะทะ (MeanShift) ---
BANDWIDTH = 300     # รัศมีที่ถือว่า "จุดตายอยู่ใกล้กัน" หน่วยเกม (300 ≈ 5.7 เมตร เท่ากับ grid ใน radars.json)
                    #   ยิ่งเล็กยิ่งซอยละเอียด: 200 -> 30 จุด | 250 -> 22 | 300 -> 17 | 350 -> 11
MIN_BIN_FREQ = 15   # ยอดที่มีจุดตายไม่ถึงเท่านี้ในรัศมี ไม่นับเป็นจุดปะทะ กันจุดตายโดด ๆ กลายเป็นยอด

# --- คำถามที่ 2: ประเภทช่อง (KMeans) ---
FEATURES = ["t_mean", "planted_share", "dist_mean", "awp_share"]   # โปรไฟล์ของช่อง — ไม่มีตัวไหนบอกฝั่ง
K_RANGE = range(2, 9)   # ไล่ลองจำนวนกลุ่มช่วงนี้
K_CLUSTERS = None       # None = เลือก k ที่ silhouette สูงสุดให้เอง | ใส่ตัวเลขถ้าจะล็อก
N_BOOT = 20             # สุ่มชุดแมตช์กี่รอบตอนวัดเสถียรภาพ
SEED = 0                # ให้รันซ้ำแล้วได้ผลเดิมทุกครั้ง

SNIPERS = {"awp", "ssg08"}      # ปืนซุ่ม — ใช้แยก "เลนซุ่มระยะไกล" ออกจากพื้นที่ปะทะประชิด

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "all_kills.csv"     # สร้างด้วย python research/prep/demoparser.py
OUT = ROOT / "output"

sys.path.insert(0, str(ROOT))           # ให้ import backend.* ได้เมื่อรันจากรากโปรเจกต์
from backend.review import cells_of, radar_frame  # noqa: E402  สูตรพิกัดชุดเดียวของทั้งรีโป

for _s in (sys.stdout, sys.stderr):     # ให้คอนโซล Windows พิมพ์ไทยได้
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


# ===========================================================================
# STEP 1 — โหลดข้อมูล
# ===========================================================================
df = pd.read_csv(CSV)
n_raw = len(df)

# กรองให้เหลือแมพเดียว เพราะกริดกับจุดปะทะผูกกับภาพเรดาร์ของแมพนั้น
if "map_name" in df.columns:
    df = df[df["map_name"] == MAP]
    if df.empty:
        sys.exit(f"ไม่มีข้อมูลแมพ {MAP} ใน {CSV.name} — มีแต่ {sorted(pd.read_csv(CSV)['map_name'].unique())}")


# ===========================================================================
# STEP 2 — หาว่าแต่ละแถวมาจากเดโมไฟล์ไหน
# ===========================================================================
# ใช้แบ่งกลุ่มตอนวัดเสถียรภาพ: สุ่มเป็น "แมตช์" ไม่ใช่รายแถว
# เหตุผลเดียวกับ GroupKFold ใน grid_ml.py — แถวจากแมตช์เดียวกันไม่ได้เป็นอิสระต่อกัน
if "demo_file" in df.columns:
    df["match_id"] = df["demo_file"]
else:
    df["match_id"] = (df["tick"].diff() < 0).cumsum()   # ทางถอยของ csv รุ่นเก่า (ดูคำอธิบายใน grid_ml.py)


# ===========================================================================
# STEP 3 — บริบทของรอบ ณ ตอนที่การดวลเกิด
# ===========================================================================
# สองอย่างนี้เป็นฟีเจอร์หลักของโปรไฟล์ช่อง ถ้า csv ไม่มีก็ทำต่อไม่ได้ ต้อง parse ใหม่
if "round_start_tick" not in df.columns:
    sys.exit("csv ไม่มีคอลัมน์บริบทรอบ (round_start_tick) — รัน python research/prep/demoparser.py --force ก่อน")

rate = df["tickrate"].fillna(128)
df["t_round"] = (df["tick"] - df["round_start_tick"]) / rate                  # วินาทีที่เท่าไรของรอบ
df["planted"] = (df["bomb_plant_tick"].notna() & (df["tick"] >= df["bomb_plant_tick"])).astype(int)


# ===========================================================================
# STEP 4 — เก็บเฉพาะการดวลจริง แล้ว "ซ่อน" เฉลยไว้
# ===========================================================================
#   ไม่มีคนยิง   = ตายเพราะ C4 ระเบิด หรือตกที่สูง -> attacker_side ว่าง
#   ฝั่งเดียวกัน = ทีมคิล
has_attacker = df["attacker_side"].notna()
enemy_duel = df["attacker_side"] != df["victim_side"]
df = df[has_attacker & enemy_duel].copy()

# นี่คือเฉลยของ grid_ml.py — ในไฟล์นี้ห้ามเข้าโมเดลเด็ดขาด
# เก็บไว้ใช้ครั้งเดียวใน STEP 8 เพื่อตรวจว่ากลุ่มที่โมเดลหาเองสอดคล้องกับของจริงไหม
df["ct_won"] = (df["attacker_side"] == "ct").astype(int)


# ===========================================================================
# STEP 5 — หย่อนลงกริด และคำนวณลักษณะของแต่ละดวล
# ===========================================================================
# ขอบเขตกริดเอาจากภาพเรดาร์ ไม่ใช่จากค่าต่ำสุด-สูงสุดของข้อมูล (เหตุผลเดียวกับ grid_ml.py)
radar = json.loads((ROOT / "assets" / "radars.json").read_text(encoding="utf-8"))[MAP]   # ไว้ใส่ payload + path รูป

# สูตรแปลงพิกัด -> ช่องกริดอยู่ที่ backend/review.py ที่เดียว (API หน้า Round Review ใช้ตัวเดียวกัน ช่องจึงตรงกันเสมอ)
frame = radar_frame(MAP)
span = frame.span                          # 1024 พิกเซล x 5.0 = 5120 หน่วยในเกม
x_left, x_right, y_bottom, y_top = frame.extent
cell_size = frame.cell_size(GRID_N)        # 5120 / 32 = 160 หน่วยต่อหนึ่งช่อง

df["cx"], df["cy"] = cells_of(df["victim_X"], df["victim_Y"], frame, GRID_N)

# ระยะดวลคิดจากพิกัดเอง ให้อยู่ในหน่วยเกมเดียวกับกริด (คอลัมน์ distance ของ parser คนละหน่วย)
df["dist_xy"] = np.hypot(df["attacker_X"] - df["victim_X"], df["attacker_Y"] - df["victim_Y"])
df["awp"] = df["weapon"].isin(SNIPERS).astype(int)

print(f"{n_raw:,} แถว -> ใช้ได้ {len(df):,} การดวล | {df['match_id'].nunique()} แมตช์")


def top_place(s):
    """ชื่อ callout ที่พบบ่อยสุดในกลุ่ม — ไว้ให้คนอ่านรู้ว่ากลุ่มนี้อยู่แถวไหนของแมพ"""
    m = s.dropna().mode()
    return m.iloc[0] if len(m) else "Unknown"


def resample_matches(d, rng):
    """bootstrap ตามแมตช์: สุ่มแมตช์ซ้ำได้จนครบจำนวนเดิม ได้ชุดข้อมูลขนาดเท่าเดิมแต่ส่วนผสมต่างไป"""
    ids = d["match_id"].unique()
    picked = rng.choice(ids, size=len(ids), replace=True)
    return pd.concat([d[d["match_id"] == m] for m in picked], ignore_index=True)


# สุ่มชุดแมตช์ไว้ชุดเดียว ใช้วัดเสถียรภาพทั้งสองคำถาม จะได้เทียบกันบนชุดเดียวกัน
BOOT_COLS = ["match_id", "victim_X", "victim_Y", "cx", "cy", "t_round", "planted", "dist_xy", "awp"]
rng = np.random.default_rng(SEED)
boots = [resample_matches(df[BOOT_COLS], rng) for _ in range(N_BOOT)]


# ===========================================================================
# STEP 6 — คำถามที่ 1: จุดปะทะอยู่ตรงไหน (MeanShift)
# ===========================================================================
# MeanShift มองจุดตายทั้งหมดเป็นภูเขาความหนาแน่น แล้วให้ทุกจุดไต่ขึ้นยอดที่ใกล้ที่สุด
# จุดที่ไต่ไปถึงยอดเดียวกัน = จุดปะทะเดียวกัน จำนวนยอดจึงมาจากข้อมูล ไม่ใช่จากคนตั้ง
# ต่างจาก KMeans ที่ต้องบอก k ล่วงหน้า และมักหั่นแมพเป็นโซนเท่า ๆ กันแม้ตรงนั้นไม่มีใครตาย
def find_hotspots(d):
    ms = MeanShift(bandwidth=BANDWIDTH, bin_seeding=True, min_bin_freq=MIN_BIN_FREQ,
                   cluster_all=False)   # จุดที่ห่างจากทุกยอดเกิน BANDWIDTH ให้เป็น -1 ไม่ยัดเข้ากลุ่มไหน
    ms.fit(d[["victim_X", "victim_Y"]].to_numpy())
    return ms.labels_, ms.cluster_centers_


labels, centers = find_hotspots(df)

# เรียงยอดตามจำนวนดวล มาก -> น้อย แล้วให้เบอร์ใหม่ เบอร์ 1 ในรูปคือจุดที่ปะทะหนักสุดเสมอ
order = np.argsort(-np.bincount(labels[labels >= 0]))
remap = {old: new for new, old in enumerate(order)}
df["hotspot"] = np.array([remap.get(lab, -1) for lab in labels])
centers = centers[order]

rows = []
for i, (hx, hy) in enumerate(centers):
    m = df[df["hotspot"] == i]
    r = np.hypot(m["victim_X"] - hx, m["victim_Y"] - hy)
    rows.append({
        "id": i + 1, "x": float(hx), "y": float(hy),
        "duels": len(m), "share": len(m) / len(df),
        "radius": float(np.percentile(r, 80)),        # รัศมีที่ครอบ 80% ของจุดในกลุ่ม ไว้วาดวงในรูป
        "place": top_place(m["victim_place"]),
        "t_mean": float(m["t_round"].mean()),
        "planted_share": float(m["planted"].mean()),
        "ct_win": float(m["ct_won"].mean()),          # ตรวจทีหลัง — ไม่ได้ใช้ตอนหาจุด
    })
hotspots = pd.DataFrame(rows)
noise_share = float((df["hotspot"] < 0).mean())

# เสถียรภาพ: สุ่มชุดแมตช์ใหม่แล้วหายอดอีกรอบ ยอดของจริงกี่ % ที่ยังมียอดคู่กันในระยะครึ่ง bandwidth
found = []
for b in boots:
    _, cb = find_hotspots(b)
    dist = np.linalg.norm(centers[:, None, :] - cb[None, :, :], axis=2)   # ระยะทุกคู่ (จริง x bootstrap)
    found.append((dist.min(axis=1) <= BANDWIDTH / 2).mean())
hotspot_stability = float(np.mean(found))

print(f"\nคำถามที่ 1 — MeanShift รัศมี {BANDWIDTH} หน่วย: เจอจุดปะทะ {len(hotspots)} จุด "
      f"ครอบคลุม {1 - noise_share:.0%} ของการดวล (ที่เหลือกระจายอยู่ห่างจากทุกยอด)")
print(f"  เสถียรภาพ: สุ่มแมตช์ใหม่ {N_BOOT} รอบ ยอดเดิมกลับมาเจอที่เดิม {hotspot_stability:.0%}")
print(hotspots[["id", "place", "duels", "share", "t_mean", "planted_share", "ct_win"]].to_string(
    index=False, formatters={"share": "{:.1%}".format, "t_mean": "{:.0f}s".format,
                             "planted_share": "{:.0%}".format, "ct_win": "{:.2f}".format}))
print("  ct_win = สัดส่วนที่ CT ชนะดวลในจุดนั้น เอามาแปะทีหลังเพื่อตรวจ โมเดลไม่เคยเห็นค่านี้")


# ===========================================================================
# STEP 7 — คำถามที่ 2: แต่ละช่องเป็นการปะทะแบบไหน (KMeans บนโปรไฟล์ช่อง)
# ===========================================================================
# หนึ่งแถว = หนึ่งช่องกริด สรุปจากทุกดวลที่จบในช่องนั้น
# ทุกฟีเจอร์เป็น "ลักษณะของการปะทะ" ไม่ใช่ "ใครชนะ" — ไม่มีคอลัมน์ไหนบอกฝั่ง
def cell_profiles(d):
    g = d.groupby(["cx", "cy"])
    p = pd.DataFrame({
        "kills": g.size(),
        "t_mean": g["t_round"].mean(),          # เกิดตอนไหนของรอบ (วินาที)
        "planted_share": g["planted"].mean(),   # สัดส่วนที่เกิดหลังระเบิดลง
        "dist_mean": g["dist_xy"].mean(),       # ระยะดวลเฉลี่ย (หน่วยเกม)
        "awp_share": g["awp"].mean(),           # สัดส่วนที่คนยิงใช้ปืนซุ่ม
    })
    return p[p["kills"] >= MIN_KILLS]


cells = cell_profiles(df)
print(f"\nคำถามที่ 2 — ช่องที่มีดวล >= {MIN_KILLS}: {len(cells)} จาก {df.groupby(['cx', 'cy']).ngroups} ช่อง "
      f"(ครอบคลุม {cells['kills'].sum() / len(df):.0%} ของการดวล)")

# ทุกฟีเจอร์คนละหน่วย (วินาที / สัดส่วน / หน่วยเกม) ต้องดึงมาสเกลเดียวกันก่อน
# ไม่งั้น KMeans จะฟังแต่ dist_mean ที่ตัวเลขเป็นร้อย แล้วมองข้ามสัดส่วนที่อยู่ระหว่าง 0-1
scaler = StandardScaler().fit(cells[FEATURES])
Z = scaler.transform(cells[FEATURES])


def fit_kmeans(X, k):
    # n_init=20 คือลองจุดเริ่มต้น 20 ชุดแล้วเอาชุดที่ดีสุด กัน KMeans ติดคำตอบแย่ ๆ จากจุดเริ่มที่โชคร้าย
    return KMeans(n_clusters=k, n_init=20, random_state=SEED).fit(X)


# ไล่ลอง k แล้ววัดสองอย่างต่อค่า
#   silhouette  ช่องอยู่ใกล้กลุ่มตัวเองมากกว่ากลุ่มข้างเคียงแค่ไหน (1 = แยกชัด, 0 = ก้ำกึ่ง, ติดลบ = จัดผิดกลุ่ม)
#   ARI         จัดกลุ่มบนชุดแมตช์ที่สุ่มใหม่ แล้วดูว่าช่องเดิมยังอยู่กลุ่มเดียวกันไหม (1 = เหมือนเดิมเป๊ะ, 0 = เท่าสุ่ม)
boot_profiles = [cell_profiles(b) for b in boots]
ks = sorted(set(K_RANGE) | ({K_CLUSTERS} if K_CLUSTERS else set()))   # k ที่ล็อกไว้ต้องโผล่ในตารางด้วย
scan = []
for k in ks:
    km = fit_kmeans(Z, k)
    ref = pd.Series(km.labels_, index=cells.index)
    aris = []
    for bp in boot_profiles:
        common = cells.index.intersection(bp.index)     # เทียบเฉพาะช่องที่มีข้อมูลพอทั้งสองชุด
        lab_b = pd.Series(fit_kmeans(StandardScaler().fit_transform(bp[FEATURES]), k).labels_, index=bp.index)
        aris.append(adjusted_rand_score(ref.loc[common], lab_b.loc[common]))
    scan.append({"k": k, "silhouette": float(silhouette_score(Z, km.labels_)), "ari": float(np.mean(aris))})
scan = pd.DataFrame(scan)

k_best = K_CLUSTERS or int(scan.loc[scan["silhouette"].idxmax(), "k"])
k_rule = f"ล็อกไว้ที่ {K_CLUSTERS}" if K_CLUSTERS else "silhouette สูงสุด"

print(f"\n  ไล่ลอง k (เลือกด้วย {k_rule}, bootstrap {N_BOOT} รอบ):")
for r in scan.itertuples():
    mark = "  <- ใช้ตัวนี้" if r.k == k_best else ""
    print(f"    k={r.k}  silhouette {r.silhouette:.3f}  ARI {r.ari:.2f}{mark}")

km = fit_kmeans(Z, k_best)

# เรียงกลุ่มตามเวลาเฉลี่ยในรอบ ต้นรอบ -> ท้ายรอบ เบอร์กลุ่มจะได้อ่านเป็นลำดับเหตุการณ์ได้
order = np.argsort(km.cluster_centers_[:, FEATURES.index("t_mean")])
remap = {old: new for new, old in enumerate(order)}
cells["cluster"] = [remap[lab] for lab in km.labels_]
centers_z = km.cluster_centers_[order]   # ค่ากลางแต่ละกลุ่มในหน่วย z-score (0 = เท่าค่าเฉลี่ยของทุกช่อง)

# ตั้งชื่อกลุ่มจากสองฟีเจอร์ที่เบี่ยงจากค่าเฉลี่ยมากสุด — ชื่อมาจากตัวเลข ไม่ได้นั่งตั้งเอง
WORDS = {   # (ต่ำกว่าค่าเฉลี่ย, สูงกว่าค่าเฉลี่ย)
    "t_mean": ("early round", "late round"),
    "planted_share": ("pre-plant", "post-plant"),
    "dist_mean": ("close range", "long range"),
    "awp_share": ("rifle", "AWP"),
}


def name_cluster(z):
    top = sorted(range(len(FEATURES)), key=lambda i: -abs(z[i]))[:2]
    parts = [WORDS[FEATURES[i]][int(z[i] > 0)] for i in top if abs(z[i]) >= 0.3]
    return " + ".join(parts) or "average"


cluster_names = [name_cluster(z) for z in centers_z]

# แปะข้อมูลอ่านประกอบ (ไม่ใช่ฟีเจอร์): callout ที่พบบ่อยสุด และเฉลยที่ซ่อนไว้
extra = df.groupby(["cx", "cy"]).agg(place=("victim_place", top_place), ct_win=("ct_won", "mean"))
cells = cells.join(extra)


# ===========================================================================
# STEP 8 — เปิดเฉลย: กลุ่มที่โมเดลหาเองสอดคล้องกับ "ใครชนะ" ไหม
# ===========================================================================
# ถ้ากลุ่มเป็นแค่ noise ทุกกลุ่มจะมี CT ชนะใกล้ค่ารวม (~0.54) เท่า ๆ กัน
# ถ้าต่างกันชัด แปลว่าลักษณะการปะทะที่โมเดลเจอเอง สัมพันธ์กับความได้เปรียบจริง
duel_cluster = df.join(cells[["cluster"]], on=["cx", "cy"])       # ดวลไหนอยู่ช่องที่ถูกจัดกลุ่มไหน
clusters = cells.groupby("cluster").agg(
    n_cells=("kills", "size"), duels=("kills", "sum"),
    t_mean=("t_mean", "mean"), planted_share=("planted_share", "mean"),
    dist_mean=("dist_mean", "mean"), awp_share=("awp_share", "mean"),
)
clusters["ct_win"] = duel_cluster.groupby("cluster")["ct_won"].mean()   # เฉลี่ยรายดวล ไม่ใช่รายช่อง
clusters["name"] = cluster_names
clusters["top_places"] = [
    ", ".join(cells[cells["cluster"] == c]["place"].value_counts().head(3).index) for c in clusters.index
]

print(f"\n  {k_best} ประเภทช่อง (เรียงต้นรอบ -> ท้ายรอบ) | CT ชนะดวลรวมทั้งแมพ {df['ct_won'].mean():.2f}")
for c, r in clusters.iterrows():
    print(f"    type {c + 1}: {r['name']:<28} {int(r['n_cells']):>3} ช่อง {int(r['duels']):>5} ดวล | "
          f"{r['t_mean']:.0f}s  post-plant {r['planted_share']:.0%}  dist {r['dist_mean']:.0f}u  "
          f"AWP {r['awp_share']:.0%} | CT ชนะ {r['ct_win']:.2f} | {r['top_places']}")
print("  CT ชนะ = เฉลยที่โมเดลไม่เคยเห็น ถ้าแต่ละประเภทต่างกันชัด แปลว่ากลุ่มที่เจอมีความหมาย")


# ===========================================================================
# STEP 9 — วาดรูปสี่ช่อง
# ===========================================================================
img = np.asarray(Image.open(ROOT / "assets" / radar["image"].lstrip("/")).convert("RGB"))
extent = [x_left, x_right, y_bottom, y_top]      # ภาพเรดาร์กินพื้นที่พิกัดเกมช่วงไหน
HOT_COLORS = [plt.cm.tab20(i % 20) for i in range(len(hotspots))]
TYPE_COLORS = [plt.cm.tab10(i) for i in range(k_best)]

fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(17, 15),
                                             gridspec_kw={"height_ratios": [1.35, 1]})

# --- บนซ้าย: จุดปะทะ ---
ax1.imshow(img, extent=extent, origin="upper")
noise = df[df["hotspot"] < 0]
ax1.scatter(noise["victim_X"], noise["victim_Y"], s=3, c="#bbbbbb", alpha=0.35, linewidths=0)
for i, h in hotspots.iterrows():
    m = df[df["hotspot"] == i]
    ax1.scatter(m["victim_X"], m["victim_Y"], s=4, color=HOT_COLORS[i], alpha=0.55, linewidths=0)
    ax1.add_patch(Circle((h["x"], h["y"]), h["radius"], fill=False, ec=HOT_COLORS[i], lw=1.6))
    ax1.text(h["x"], h["y"], str(int(h["id"])), ha="center", va="center", fontsize=8, fontweight="bold",
             color="white", bbox=dict(boxstyle="circle,pad=0.25", fc=HOT_COLORS[i], ec="white", lw=0.8))
ax1.set_title(f"Q1  Where fights cluster — MeanShift, bandwidth {BANDWIDTH} units\n"
              f"{len(hotspots)} hotspots hold {1 - noise_share:.0%} of duels · grey = not near any peak · "
              f"{hotspot_stability:.0%} of peaks recur under match bootstrap", fontsize=10)

# --- บนขวา: ประเภทช่อง ---
# วาดเป็นภาพ RGBA ซ้อนบนเรดาร์ ช่องที่ข้อมูลน้อยกว่า MIN_KILLS ปล่อยใส
# index ของ array เป็น [แถว, คอลัมน์] = [cy, cx] และ origin="lower" ให้แถว 0 อยู่ล่างสุด = y_bottom
rgba = np.zeros((GRID_N, GRID_N, 4))
for (cx, cy), r in cells.iterrows():
    rgba[cy, cx] = (*TYPE_COLORS[r["cluster"]][:3], 0.65)
ax2.imshow(img, extent=extent, origin="upper")
ax2.imshow(rgba, extent=extent, origin="lower", interpolation="nearest")
ax2.legend(handles=[Patch(color=TYPE_COLORS[c], label=f"type {c + 1}: {r['name']}  ({int(r['n_cells'])} cells)")
                    for c, r in clusters.iterrows()],
           loc="upper center", bbox_to_anchor=(0.5, -0.01), ncol=2, fontsize=9, frameon=False)
ax2.set_title(f"Q2  What kind of fight happens in each cell — KMeans k={k_best} on label-free cell profiles\n"
              f"{GRID_N}x{GRID_N} grid · cells with fewer than {MIN_KILLS} duels left blank", fontsize=10)

for ax in (ax1, ax2):
    ax.set_xticks([])
    ax.set_yticks([])

# --- ล่างซ้าย: เลือก k อย่างไร ---
ax3.plot(scan["k"], scan["silhouette"], "o-", color="#1f77b4", label="silhouette (higher = clearer split)")
ax3.set_ylim(scan["silhouette"].min() - 0.03, scan["silhouette"].max() + 0.03)   # เผื่อขอบ ไม่ให้จุดต่ำสุดหลุดกรอบ
ax3.set_xlabel("k (number of cell types)")
ax3.set_ylabel("silhouette", color="#1f77b4")
ax3b = ax3.twinx()
ax3b.plot(scan["k"], scan["ari"], "s--", color="#d62728",
          label=f"bootstrap ARI, {N_BOOT} resamples (higher = more stable)")
ax3b.set_ylabel("ARI", color="#d62728")
ax3b.set_ylim(0, 1)
ax3.axvline(k_best, color="grey", ls=":")
ax3.text(k_best + 0.08, ax3.get_ylim()[1], f"chosen k={k_best}", va="top", fontsize=9, color="grey")
h1, l1 = ax3.get_legend_handles_labels()
h2, l2 = ax3b.get_legend_handles_labels()
ax3.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=9)
ax3.set_title("How k was chosen: separation vs. stability", fontsize=10)
ax3.grid(alpha=0.3)

# --- ล่างขวา: โปรไฟล์ของแต่ละประเภท ---
# สีคือ z-score ของค่ากลาง (น้ำเงิน = ต่ำกว่าเฉลี่ยของทุกช่อง, แดง = สูงกว่า)
# ตัวเลขในช่องคือค่าจริง คอลัมน์สุดท้ายเป็นเฉลยที่ซ่อนไว้ ปล่อยเทาไว้ให้รู้ว่าไม่ได้ร่วมจัดกลุ่ม
heat = np.full((k_best, len(FEATURES) + 1), np.nan)
heat[:, :len(FEATURES)] = centers_z
cmap = plt.cm.RdBu_r.copy()
cmap.set_bad("#e8e8e8")
ax4.imshow(np.ma.masked_invalid(heat), cmap=cmap, vmin=-1.6, vmax=1.6, aspect="auto")
FMT = {"t_mean": "{:.0f} s", "planted_share": "{:.0%}", "dist_mean": "{:.0f} u", "awp_share": "{:.0%}"}
for c, r in clusters.iterrows():
    for j, f in enumerate(FEATURES):
        ax4.text(j, c, FMT[f].format(r[f]), ha="center", va="center", fontsize=10,
                 color="white" if abs(centers_z[c, j]) > 0.9 else "black")
    ax4.text(len(FEATURES), c, f"{r['ct_win']:.0%}", ha="center", va="center", fontsize=10, fontweight="bold")
ax4.set_xticks(range(len(FEATURES) + 1))
ax4.set_xticklabels(["time in round", "post-plant share", "duel distance", "AWP share", "CT wins duel\n(held out)"],
                    fontsize=9)
ax4.set_yticks(range(k_best))
ax4.set_yticklabels([f"type {c + 1}\n{n}" for c, n in enumerate(cluster_names)], fontsize=9)
ax4.set_title("Profile of each cell type (colour = z-score vs. all cells) · last column never used in fitting",
              fontsize=10)

fig.suptitle(f"{MAP} · unsupervised · {len(df):,} duels from {df['match_id'].nunique()} matches · "
             f"no side labels used in fitting", fontsize=13)
fig.tight_layout()

OUT.mkdir(exist_ok=True)
fig.savefig(OUT / "grid_ml1_map.png", dpi=140)


# ===========================================================================
# STEP 10 — เซฟตาราง และ json ก้อนเดียวให้หน้าเว็บใช้
# ===========================================================================
cells_out = cells.reset_index()
cells_out["cluster"] += 1                        # ให้เบอร์เริ่มที่ 1 เหมือนในรูป
cells_out["cluster_name"] = cells_out["cluster"].map(lambda c: cluster_names[c - 1])
cells_out.to_csv(OUT / "grid_ml1_cells.csv", index=False, encoding="utf-8-sig")
hotspots.to_csv(OUT / "grid_ml1_hotspots.csv", index=False, encoding="utf-8-sig")

payload = {
    "map": MAP,
    "grid_n": GRID_N,
    "min_kills": MIN_KILLS,
    "radar": {k: radar[k] for k in ("image", "size", "pos_x", "pos_y", "scale")},
    "metrics": {
        "matches": int(df["match_id"].nunique()),
        "duels": int(len(df)),
        "rows_raw": int(n_raw),
        "bandwidth": BANDWIDTH,
        "n_hotspots": int(len(hotspots)),
        "hotspot_coverage": 1 - noise_share,
        "hotspot_stability": hotspot_stability,
        "features": FEATURES,
        "k": k_best,
        "k_rule": k_rule,
        "silhouette": float(scan.loc[scan["k"] == k_best, "silhouette"].iloc[0]),
        "ari": float(scan.loc[scan["k"] == k_best, "ari"].iloc[0]),
        "k_scan": scan.to_dict(orient="records"),
        "n_boot": N_BOOT,
        "ct_win_overall": float(df["ct_won"].mean()),
    },
    "hotspots": hotspots.round(3).to_dict(orient="records"),
    "clusters": [
        {"id": c + 1, "name": r["name"], "n_cells": int(r["n_cells"]), "duels": int(r["duels"]),
         "ct_win": round(float(r["ct_win"]), 3), "top_places": r["top_places"],
         **{f: round(float(r[f]), 3) for f in FEATURES}}
        for c, r in clusters.iterrows()
    ],
    "cells": cells_out.round(3).to_dict(orient="records"),
}
(OUT / "grid_ml1.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

print("\nเซฟแล้ว:")
for _f in ("grid_ml1_map.png", "grid_ml1_cells.csv", "grid_ml1_hotspots.csv", "grid_ml1.json"):
    print(f"  {OUT / _f}")
