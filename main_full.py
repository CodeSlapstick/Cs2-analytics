#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CS2 Map Zone Scoring + Unsupervised Clustering  (Progress 1 demo)
=================================================================

    python main.py                 # รันจบในคำสั่งเดียว -> ได้ PNG 2 ภาพ + สรุปภาษาไทย
    python main.py --demos 3       # ใช้ไฟล์ .dem แค่ 3 ไฟล์ (เร็วขึ้น)
    python main.py --synthetic     # บังคับใช้ข้อมูลจำลอง (ไว้เทียบ / ตอนไม่มีไฟล์ .dem)
    python main.py --grid 25 --w-kill 4    # ปรับกริด/น้ำหนักคะแนนได้จาก command line

โจทย์: แบ่งแมพเป็นโซน แล้วให้คะแนนแต่ละโซนตาม "ความรุนแรงของการปะทะ"
       จากนั้นใช้ unsupervised learning (DBSCAN) หา hotspot ขึ้นมาเองจากข้อมูลดิบ
       แล้วเช็คว่า hotspot ที่ ML หาเจอ ตรงกับโซนคะแนนสูงที่เราคำนวณด้วยสูตรไหม

ทำไมต้องมีสองวิธีแล้วเอามาเทียบกัน:
  - Zone score (STEP 2) คือกริดตายตัว + สูตรที่ "คนตั้งน้ำหนักเอง" -> อธิบายง่าย
    แต่เส้นกริดอาจผ่ากลางจุดปะทะ ทำให้จุดเดียวถูกหั่นไปคนละช่อง
  - DBSCAN (STEP 3) ไม่รู้จักกริดเลย มันจับกลุ่มจากความหนาแน่นของจุดจริง
    ขอบเขตโซนจึงวิ่งตามการเล่นจริง และไม่ต้องบอกล่วงหน้าว่ามีกี่โซน
  ถ้าสองวิธีนี้ชี้ไปที่เดียวกัน = ผลน่าเชื่อถือ (cross-validation แบบง่าย ๆ)

ข้อมูล: อ่านจากไฟล์ .dem จริงในโฟลเดอร์ demo/ ผ่าน awpy
        ถ้าไม่พบไฟล์ .dem จะสลับไปใช้ synthetic dataset อัตโนมัติ (ดู make_synthetic_events)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Rectangle

from sklearn.cluster import DBSCAN
from sklearn.neighbors import NearestNeighbors

# คอนโซล Windows ดีฟอลต์เป็น cp874/cp1252 พิมพ์ไทยไม่ได้ -> บังคับ UTF-8 ตั้งแต่ต้น
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent
DEMO_DIR = ROOT / "demo"
OUT_DIR = ROOT / "output"
RADAR_IMG = ROOT / "frontend" / "public" / "maps" / "de_dust2.webp"
RADARS_JSON = ROOT / "backend" / "data" / "radars.json"

# ---------------------------------------------------------------------------
# CONFIG — น้ำหนักของสูตรให้คะแนนโซน (ปรับได้จาก CLI)
# ---------------------------------------------------------------------------
# score_raw = kill*W_KILL + damage_sum*W_DAMAGE + weapon_fire*W_FIRE  แล้ว normalize 0-100
W_KILL, W_DAMAGE, W_FIRE = 3.0, 0.1, 1.0
GRID_N = 20            # แบ่งเป็น GRID_N x GRID_N ช่อง
ANNOTATE_MIN = 1.0     # โซนที่คะแนนต่ำกว่านี้ไม่ต้องเขียนตัวเลข (กันภาพรก)

# --- ค่าตั้งของ DBSCAN (STEP 3) ---
# ตัดหางบน 10% ของกราฟ k-distance ทิ้งก่อนหา "หัวเข่า" — เหตุผลเต็มอยู่ใน auto_eps()
KNEE_TRIM = 0.90
# กลุ่มที่มีจุดน้อยกว่า 2% ของทั้งหมด ถือเป็นการปะทะประปราย ไม่นับเป็น hotspot
# (หลักเดียวกับ MIN_POINTS_PER_ZONE ใน parser/map_zones.py ของโปรเจกต์)
MIN_CLUSTER_FRAC = 0.02

# ---------------------------------------------------------------------------
# สี — ชุดที่ผ่านการตรวจ contrast/ตาบอดสีมาแล้ว
# ---------------------------------------------------------------------------
SURFACE = "#fcfcfb"
INK, INK_2, INK_MUTED = "#0b0b0b", "#52514e", "#8a8880"
# sequential blue 100 -> 700 : ใช้กับ "ปริมาณ" (คะแนนโซน) — ไล่เฉดเดียว ไม่ใช้สายรุ้ง
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#1c5cab", "#104281"]
CMAP_SCORE = LinearSegmentedColormap.from_list("seq_blue", SEQ_BLUE)
# categorical — ใช้กับ "ตัวตน" (cluster id) ตามลำดับสลอตตายตัว ห้ามวนซ้ำมั่ว
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
       "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
NOISE_GRAY = "#b8b6ae"

_installed = {f.name for f in font_manager.fontManager.ttflist}
THAI_FONT = next((f for f in ("Leelawadee UI", "Tahoma", "Leelawadee", "Noto Sans Thai")
                  if f in _installed), None)
if THAI_FONT:
    plt.rcParams["font.family"] = THAI_FONT
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "text.color": INK, "axes.labelcolor": INK_2,
    "xtick.color": INK_MUTED, "ytick.color": INK_MUTED,
    "axes.edgecolor": "#dcdad2", "axes.unicode_minus": False,
})


# ===========================================================================
# STEP 1 — โหลดข้อมูล
# ===========================================================================
# สคีมาของตาราง events (เหมือนกันทั้งข้อมูลจริงและข้อมูลจำลอง):
#   x, y          พิกัดในเกมของ "จุดที่เกิดเหตุ"
#                 kill/damage ใช้พิกัดเหยื่อ (= พื้นที่ที่อันตราย)
#                 weapon_fire ใช้พิกัดคนยิง (= พื้นที่ที่คนกดยิงจริง)
#   tick, round   เวลาในเกม / รอบที่เท่าไร
#   side          ฝั่งของผู้เล่นที่ยืนอยู่ตรง (x,y) นั้น -> 'CT' หรือ 'T'
#   event_type    'kill' | 'damage' | 'weapon_fire'
#   player_id     steamid ของผู้เล่นที่ (x,y)
#   damage        ดาเมจของอีเวนต์นั้น (เฉพาะ damage/kill, ที่เหลือ 0) -> ใช้ในสูตรคะแนน
#   opponent_side ฝั่งของ "คู่ปะทะ" = ฝั่งคนยิง (ใช้ตัดสิน dominant_side ของโซน)

EVENT_COLS = ["x", "y", "tick", "round", "side", "event_type",
              "player_id", "damage", "opponent_side"]


def _side(v):
    """awpy คืน 'ct'/'t' -> ทำให้เป็น 'CT'/'T'"""
    if v is None:
        return None
    t = str(v).strip().lower()
    return "CT" if t.startswith("ct") else ("T" if t.startswith("t") else None)


def _to_pandas(df, cols):
    """polars -> pandas โดยไม่บังคับว่าต้องมี pyarrow"""
    have = [c for c in cols if c in df.columns]
    sub = df.select(have)
    try:
        return sub.to_pandas()
    except Exception:
        return pd.DataFrame(sub.to_dicts())


def events_from_demo(path: Path, tickrate: int = 64) -> pd.DataFrame:
    """แปลงไฟล์ .dem หนึ่งไฟล์เป็นตาราง events ตามสคีมาข้างบน"""
    from awpy import Demo

    dem = Demo(path=path, tickrate=tickrate)
    dem.parse()
    frames = []

    kills = getattr(dem, "kills", None)
    if kills is not None and not kills.is_empty():
        k = _to_pandas(kills, ["victim_X", "victim_Y", "tick", "round_num",
                               "victim_side", "victim_steamid", "attacker_side", "dmg_health"])
        frames.append(pd.DataFrame({
            "x": k["victim_X"], "y": k["victim_Y"], "tick": k["tick"], "round": k["round_num"],
            "side": k["victim_side"].map(_side), "event_type": "kill",
            "player_id": k["victim_steamid"].astype("string"),
            "damage": pd.to_numeric(k["dmg_health"], errors="coerce").fillna(0.0)
            if "dmg_health" in k.columns else 0.0,
            "opponent_side": k["attacker_side"].map(_side),
        }))

    dmg = getattr(dem, "damages", None)
    if dmg is not None and not dmg.is_empty():
        d = _to_pandas(dmg, ["victim_X", "victim_Y", "tick", "round_num",
                             "victim_side", "victim_steamid", "attacker_side", "dmg_health"])
        frames.append(pd.DataFrame({
            "x": d["victim_X"], "y": d["victim_Y"], "tick": d["tick"], "round": d["round_num"],
            "side": d["victim_side"].map(_side), "event_type": "damage",
            "player_id": d["victim_steamid"].astype("string"),
            "damage": pd.to_numeric(d["dmg_health"], errors="coerce").fillna(0.0),
            "opponent_side": d["attacker_side"].map(_side),
        }))

    shots = getattr(dem, "shots", None)
    if shots is not None and not shots.is_empty():
        s = _to_pandas(shots, ["player_X", "player_Y", "tick", "round_num",
                               "player_side", "player_steamid", "weapon"])
        # ตัดการ "ฟัน" ด้วยมีดออก — ผู้เล่นถือมีดวิ่งไปมาตลอดเกม นั่นคือการเคลื่อนที่
        # ไม่ใช่การปะทะ ถ้าไม่ตัดออกจะกลายเป็น noise กองใหญ่แถวจุดเกิดและทางเดิน
        s = s[~s["weapon"].astype(str).str.contains("knife", case=False, na=False)]
        frames.append(pd.DataFrame({
            "x": s["player_X"], "y": s["player_Y"], "tick": s["tick"], "round": s["round_num"],
            "side": s["player_side"].map(_side), "event_type": "weapon_fire",
            "player_id": s["player_steamid"].astype("string"),
            "damage": 0.0, "opponent_side": None,
        }))

    if not frames:
        return pd.DataFrame(columns=EVENT_COLS)
    out = pd.concat(frames, ignore_index=True)
    out["map_name"] = dem.header.get("map_name", "unknown")
    out["source"] = path.name
    return out.dropna(subset=["x", "y"])


def make_synthetic_events(n: int = 2600, seed: int = 42) -> pd.DataFrame:
    """
    *** ข้อมูลจำลองสำหรับ demo เท่านั้น ***
    พร้อมเปลี่ยนเป็น demo จริงผ่าน awpy ได้ทันทีที่มีไฟล์ .dem — โค้ดเส้นทางนั้น
    อยู่ที่ events_from_demo() ข้างบน และคืนตารางหน้าตาเดียวกันเป๊ะ (EVENT_COLS)
    ฟังก์ชันนี้จะถูกเรียกก็ต่อเมื่อหาไฟล์ .dem ไม่เจอ หรือสั่ง --synthetic เท่านั้น

    จำลองให้เหมือนของจริง: มี 4 จุดที่เหตุการณ์ถี่ผิดปกติ (mid / A site / B site / long)
    บวก noise กระจายทั่วแมพ เพื่อทดสอบว่า DBSCAN แยก hotspot ออกจาก noise ได้จริง
    """
    rng = np.random.default_rng(seed)
    # (ชื่อ, x, y, การกระจาย, สัดส่วนอีเวนต์, ฝั่งที่คุมพื้นที่นี้)
    hotspots = [
        ("Mid",       -400,  800, 210, 0.22, "CT"),
        ("A site",     900, 1900, 240, 0.24, "CT"),
        ("B site",   -1750, 2450, 230, 0.20, "T"),
        ("Long A",     700,  200, 260, 0.16, "T"),
    ]
    rows = []
    n_noise = int(n * (1 - sum(h[4] for h in hotspots)))
    for _, cx, cy, sd, frac, dom in hotspots:
        m = int(n * frac)
        rows.append(pd.DataFrame({
            "x": rng.normal(cx, sd, m), "y": rng.normal(cy, sd, m),
            # ฝั่งที่คุมโซนชนะการปะทะที่นี่ ~70% ของครั้ง
            "opponent_side": rng.choice([dom, "T" if dom == "CT" else "CT"], m, p=[0.7, 0.3]),
        }))
    rows.append(pd.DataFrame({  # noise กระจายทั่วแมพ
        "x": rng.uniform(-2300, 1900, n_noise), "y": rng.uniform(-1200, 3100, n_noise),
        "opponent_side": rng.choice(["CT", "T"], n_noise),
    }))
    df = pd.concat(rows, ignore_index=True)
    n_all = len(df)
    df["event_type"] = rng.choice(["kill", "damage", "weapon_fire"], n_all, p=[0.08, 0.22, 0.70])
    df["side"] = np.where(df["opponent_side"] == "CT", "T", "CT")   # เหยื่อคือฝั่งตรงข้ามคนยิง
    df["round"] = rng.integers(1, 25, n_all)
    df["tick"] = df["round"] * 8000 + rng.integers(0, 7000, n_all)
    df["player_id"] = rng.integers(1, 11, n_all).astype(str)
    df["damage"] = np.where(df["event_type"] == "weapon_fire", 0.0,
                            rng.integers(8, 100, n_all).astype(float))
    df.loc[df["event_type"] == "weapon_fire", "opponent_side"] = None
    df["map_name"], df["source"] = "de_dust2 (synthetic)", "synthetic"
    return df.sample(frac=1, random_state=seed).reset_index(drop=True)


def load_events(max_demos, force_synthetic):
    """คืน (ตาราง events, ใช้ข้อมูลจำลองหรือเปล่า) — มี cache ให้รันซ้ำได้ทันที"""
    dems = sorted(DEMO_DIR.glob("*.dem")) if DEMO_DIR.is_dir() else []
    if max_demos:
        dems = dems[:max_demos]

    if force_synthetic or not dems:
        if not dems and not force_synthetic:
            print(f"! ไม่พบไฟล์ .dem ใน {DEMO_DIR} — สลับไปใช้ข้อมูลจำลองอัตโนมัติ")
        return make_synthetic_events(), True

    OUT_DIR.mkdir(exist_ok=True)
    cache, manifest = OUT_DIR / "events_cache.csv", OUT_DIR / "events_cache.json"
    key = [[d.name, d.stat().st_size] for d in dems]
    if cache.exists() and manifest.exists() and json.loads(manifest.read_text()) == key:
        print(f"» ใช้ cache ที่ parse ไว้แล้ว ({cache.name}) — ลบไฟล์นี้ถ้าอยาก parse ใหม่")
        return pd.read_csv(cache), False

    print(f"» parse ไฟล์ .dem จริง {len(dems)} ไฟล์ ด้วย awpy ...")
    frames = []
    for i, d in enumerate(dems, 1):
        t0 = time.time()
        try:
            ev = events_from_demo(d)
            frames.append(ev)
            print(f"   [{i}/{len(dems)}] {d.name}  {len(ev):>6,} events  ({time.time()-t0:.1f}s)")
        except Exception as exc:
            print(f"   [{i}/{len(dems)}] {d.name}  ! ข้าม: {exc}")
    if not frames:
        print("! parse ไม่สำเร็จสักไฟล์ — สลับไปใช้ข้อมูลจำลอง")
        return make_synthetic_events(), True

    out = pd.concat(frames, ignore_index=True)
    out.to_csv(cache, index=False)
    manifest.write_text(json.dumps(key))
    return out, False


# ===========================================================================
# STEP 2 — ให้คะแนนโซนบนกริด
# ===========================================================================
def score_zones(ev, grid_n, w_kill, w_dmg, w_fire):
    """
    แบ่งกริด grid_n x grid_n ตามขอบเขต x,y ของข้อมูล แล้วให้คะแนนแต่ละช่อง

        score_raw = kill*w_kill + damage_sum*w_dmg + weapon_fire*w_fire
        score     = 100 * score_raw / max(score_raw)      (normalize 0-100)

    dominant_side = ฝั่งที่ "ชนะการปะทะ" ในโซนนี้บ่อยกว่า คือฝั่งของคนยิงที่ทำ kill สำเร็จ
                    (ถ้าโซนนั้นไม่มี kill เลย ใช้ฝั่งที่กดยิงจากโซนนี้บ่อยกว่าแทน)
    """
    x0, x1 = ev["x"].min(), ev["x"].max()
    y0, y1 = ev["y"].min(), ev["y"].max()
    xe = np.linspace(x0, x1, grid_n + 1)
    ye = np.linspace(y0, y1, grid_n + 1)

    # np.clip กันจุดที่ตกขอบขวา/บนพอดีให้ยังอยู่ในช่องสุดท้าย ไม่หลุดออกนอกกริด
    ev = ev.copy()
    ev["ix"] = np.clip(np.digitize(ev["x"], xe) - 1, 0, grid_n - 1)
    ev["iy"] = np.clip(np.digitize(ev["y"], ye) - 1, 0, grid_n - 1)

    is_kill = ev["event_type"] == "kill"
    is_fire = ev["event_type"] == "weapon_fire"
    ev["_k"] = is_kill.astype(int)
    ev["_f"] = is_fire.astype(int)
    ev["_d"] = np.where(is_fire, 0.0, pd.to_numeric(ev["damage"], errors="coerce").fillna(0.0))

    tab = (ev.groupby(["iy", "ix"])
             .agg(kill_count=("_k", "sum"), fire_count=("_f", "sum"),
                  damage_sum=("_d", "sum"), events=("_k", "size"))
             .reset_index())

    tab["score_raw"] = (tab["kill_count"] * w_kill
                        + tab["damage_sum"] * w_dmg
                        + tab["fire_count"] * w_fire)
    mx = tab["score_raw"].max()
    tab["score"] = (100 * tab["score_raw"] / mx).round(1) if mx > 0 else 0.0

    # --- dominant_side ---
    kills = ev[is_kill]
    win = (kills.groupby(["iy", "ix", "opponent_side"]).size().rename("n").reset_index()
           .sort_values("n", ascending=False).drop_duplicates(["iy", "ix"])
           .set_index(["iy", "ix"])["opponent_side"])
    fire = ev[is_fire]
    fb = (fire.groupby(["iy", "ix", "side"]).size().rename("n").reset_index()
          .sort_values("n", ascending=False).drop_duplicates(["iy", "ix"])
          .set_index(["iy", "ix"])["side"])
    idx = pd.MultiIndex.from_frame(tab[["iy", "ix"]])
    dom = win.reindex(idx)
    dom = dom.fillna(fb.reindex(idx)) if len(fb) else dom
    tab["dominant_side"] = dom.fillna("-").to_numpy()

    tab["zone_id"] = ("Z" + tab["ix"].astype(str).str.zfill(2)
                      + "-" + tab["iy"].astype(str).str.zfill(2))
    tab["x_range"] = [f"({xe[i]:.0f}, {xe[i+1]:.0f})" for i in tab["ix"]]
    tab["y_range"] = [f"({ye[j]:.0f}, {ye[j+1]:.0f})" for j in tab["iy"]]
    tab["cx"] = (xe[tab["ix"]] + xe[tab["ix"] + 1]) / 2
    tab["cy"] = (ye[tab["iy"]] + ye[tab["iy"] + 1]) / 2
    tab = tab.sort_values("score", ascending=False).reset_index(drop=True)

    grid = np.zeros((grid_n, grid_n))
    grid[tab["iy"], tab["ix"]] = tab["score"]
    return tab, grid, xe, ye


# ===========================================================================
# STEP 3 — DBSCAN + หา eps อัตโนมัติด้วย k-distance elbow
# ===========================================================================
def auto_eps(xy, k, trim=KNEE_TRIM):
    """
    หา eps เองจากกราฟ k-distance โดยไม่ต้องมีคนมานั่งลองค่า

    วิธี: เรียงระยะทางจากทุกจุดไปยังเพื่อนบ้านลำดับที่ k จากน้อยไปมาก จะได้กราฟ
    ที่แบนยาว ๆ (จุดที่อยู่ในบริเวณหนาแน่น) แล้วหักศอกพุ่งขึ้น (จุดที่โดดเดี่ยว)
    "หัวเข่า" ของกราฟคือระยะที่แยกสองพวกนี้ออกจากกัน = ค่า eps ที่เหมาะ

    หาหัวเข่าด้วยวิธี maximum-distance-from-chord: ลากคอร์ดจากจุดแรกไปจุดสุดท้าย
    แล้วเลือกจุดบนกราฟที่ห่างจากคอร์ดนั้นมากที่สุด (หลักการเดียวกับ Kneedle)

    ทำไมต้อง trim (ตัดหางบน 10% ทิ้งก่อนลากคอร์ด):
    ข้อมูลจริงมีจุดโดดเดี่ยวสุดขั้วอยู่ไม่กี่จุด (คนตายมุมแมพที่ไม่มีใครไป) ระยะของมัน
    สูงกว่าจุดทั่วไปหลายเท่า ถ้าลากคอร์ดไปถึงจุดสุดท้ายจริง ๆ ปลายคอร์ดจะถูกดึงขึ้นไป
    สูงมากจนคอร์ดเกือบตั้งฉาก "หัวเข่า" ที่หาได้จึงเลื่อนไปทางขวาเกินจุดที่กลุ่มเริ่ม
    เชื่อมติดกัน (percolation) — ผลคือ DBSCAN คืนก้อนยักษ์ก้อนเดียวกลืนทั้งแมพ
    (วัดจริงกับข้อมูลชุดนี้: trim=1.00 -> 1 ก้อนกิน 93% ของจุด / trim=0.90 -> 31 ก้อนแยกกันดี)
    """
    nn = NearestNeighbors(n_neighbors=k).fit(xy)
    dist, _ = nn.kneighbors(xy)
    kd = np.sort(dist[:, -1])                       # ระยะไปเพื่อนบ้านที่ k เรียงจากน้อยไปมาก
    cut = kd[:max(10, int(len(kd) * trim))]
    i = np.arange(len(cut), dtype=float)
    x1, y1, x2, y2 = i[0], cut[0], i[-1], cut[-1]
    d = np.abs((y2 - y1) * i - (x2 - x1) * cut + x2 * y1 - y2 * x1) / np.hypot(y2 - y1, x2 - x1)
    knee = int(np.argmax(d))
    return float(cut[knee]), kd, knee


# อีเวนต์ที่เอาเข้า DBSCAN — ดีฟอลต์คือ 'conflict'
#   conflict = kill + damage  ->  "จุดที่การปะทะเกิดผลจริง"
#   ทำไมไม่ใช้ทุกอีเวนต์: weapon_fire คิดเป็น ~81% ของข้อมูล และเกิดได้ทั่วแมพ
#   (สเปรย์ข้ามแมพ, ขว้างระเบิดจากที่เกิด, ยิงลม) ความหนาแน่นของมันจึงกลบสัญญาณ
#   จนพื้นที่เดินได้ทั้งแมพเชื่อมเป็นก้อนเดียว — ทดสอบแล้วได้ 141 ก้อนเศษ ๆ ที่ตีความไม่ได้
#   ส่วน kill อย่างเดียวก็น้อยไป (1,142 จุด) ประเมินความหนาแน่นไม่นิ่ง
CLUSTER_SUBSETS = {
    "conflict": ("kill", "damage"),
    "kill": ("kill",),
    "all": ("kill", "damage", "weapon_fire"),
}


def run_dbscan(ev, min_samples, cluster_on="conflict", min_frac=MIN_CLUSTER_FRAC):
    """คืน (จุดที่เข้า cluster พร้อมคอลัมน์ cluster, ตาราง centroid, ข้อมูลการจูน)"""
    pts = ev[ev["event_type"].isin(CLUSTER_SUBSETS[cluster_on])].copy().reset_index(drop=True)
    xy = pts[["x", "y"]].to_numpy(dtype=float)
    n = len(xy)
    # min_samples: ใช้กฎ 2*ln(n) — ข้อมูลยิ่งเยอะยิ่งต้องการเพื่อนบ้านมากขึ้นถึงจะนับว่า
    # "หนาแน่นจริง" ไม่ใช่บังเอิญ (ค่าต่ำเกินไปจะเหมาเอา noise มาเป็น cluster)
    k = min_samples or max(6, int(round(2 * np.log(n))))
    eps, kd, knee = auto_eps(xy, k)
    labels = DBSCAN(eps=eps, min_samples=k).fit_predict(xy)

    # กลุ่มเล็กเกินเกณฑ์ -> ตีกลับเป็น noise แล้วเรียงเลข cluster ใหม่ตามขนาด
    # เพื่อให้ C0 = hotspot ใหญ่สุดเสมอ อ่านง่ายตอนนำเสนอ
    floor = max(k, int(min_frac * n))
    sizes = pd.Series(labels[labels >= 0]).value_counts()
    keep = [c for c in sizes.index if sizes[c] >= floor]
    remap = {c: i for i, c in enumerate(sorted(keep, key=lambda c: -sizes[c]))}
    labels = np.array([remap.get(l, -1) for l in labels])
    pts["cluster"] = labels

    cents = []
    for c in sorted(remap.values()):
        m = labels == c
        p = xy[m]
        cents.append({
            "cluster": int(c), "n": int(m.sum()),
            "cx": float(p[:, 0].mean()), "cy": float(p[:, 1].mean()),
            # รัศมีที่ครอบ 80% ของจุดในกลุ่ม — ใช้วาดวงให้เห็นขนาดโซนคร่าว ๆ
            "radius": float(np.percentile(np.hypot(*(p - p.mean(0)).T), 80)),
            "kills": int((pts.loc[m, "event_type"] == "kill").sum()),
        })
    cents = pd.DataFrame(cents)
    return pts, cents, {"eps": eps, "min_samples": k, "kd": kd, "knee": knee,
                        "n_points": n, "n_noise": int((labels == -1).sum()),
                        "cluster_on": cluster_on, "floor": floor,
                        "n_dropped": len(sizes) - len(keep)}


# ===========================================================================
# STEP 4 — ภาพสำหรับสไลด์
# ===========================================================================
def load_radar():
    """คืน (ภาพเรดาร์, extent ในพิกัดเกม) — ถ้าไม่มีไฟล์คืน (None, None)"""
    if not (RADAR_IMG.exists() and RADARS_JSON.exists()):
        return None, None
    try:
        from PIL import Image
        cal = json.loads(RADARS_JSON.read_text(encoding="utf-8"))["de_dust2"]
        img = np.asarray(Image.open(RADAR_IMG).convert("L"), dtype=float) / 255.0
        span = cal["size"] * cal["scale"]
        return img, (cal["pos_x"], cal["pos_x"] + span, cal["pos_y"] - span, cal["pos_y"])
    except Exception:
        return None, None


def _base_map(ax, radar, extent, ev, dim=True):
    """
    วางพื้นหลังเรดาร์ + ตั้งกรอบภาพให้พอดีข้อมูล

    dim=True  ใช้กับภาพ cluster — กดแมพให้เข้มลง จุดสีจะเด่นขึ้น
    dim=False ใช้กับ heatmap — ต้องให้แมพสว่างพอที่จะมองทะลุช่องสีมาเห็นแนวตึกได้
    """
    if radar is not None:
        # ภาพเรดาร์ต้นฉบับพื้นเป็นสีดำเกือบสนิท ถ้าจะให้สว่างต้อง "ยกพื้นดำขึ้นเป็นเทา"
        # ด้วย vmin ติดลบมาก ๆ ไม่ใช่ไปบีบ vmax (บีบแล้วยิ่งดำ)
        vmin, vmax = (-0.35, 1.5) if dim else (-0.95, 1.15)
        ax.imshow(radar, extent=extent, cmap="gray", vmin=vmin, vmax=vmax,
                  origin="upper", zorder=0, interpolation="bilinear")
    pad = 250
    ax.set_xlim(ev["x"].min() - pad, ev["x"].max() + pad)
    ax.set_ylim(ev["y"].min() - pad, ev["y"].max() + pad)
    ax.set_aspect("equal")
    ax.set_xlabel("พิกัด X ในเกม" if THAI_FONT else "game X")
    ax.set_ylabel("พิกัด Y ในเกม" if THAI_FONT else "game Y")
    for s in ax.spines.values():
        s.set_linewidth(0.8)


def plot_zone_heatmap(ev, tab, grid, xe, ye, radar, extent, meta, path):
    fig, ax = plt.subplots(figsize=(12.5, 11.5))
    _base_map(ax, radar, extent, ev, dim=False)

    masked = np.ma.masked_where(grid <= 0, grid)     # ช่องที่ไม่มีเหตุการณ์ = โปร่งใส เห็นแมพ
    # ความทึบไล่ตามคะแนนด้วย ไม่ใช่แค่สี — ช่องคะแนนน้อยจึงจางพอให้เห็นแนวแมพข้างใต้
    # ไม่งั้นกริด 400 ช่องจะกลายเป็นผืนสีทึบบังแมพจนดูไม่ออกว่าโซนไหนอยู่ตรงไหนของแมพ
    alpha = 0.42 + 0.48 * np.sqrt(np.clip(grid, 0, 100) / 100.0)
    mesh = ax.pcolormesh(xe, ye, masked, cmap=CMAP_SCORE, vmin=0, vmax=100,
                         alpha=alpha, edgecolors="#ffffff", linewidth=0.35, zorder=2)

    for _, r in tab.iterrows():
        if r["score"] < ANNOTATE_MIN:
            continue
        ax.text(r["cx"], r["cy"], f"{r['score']:.0f}", ha="center", va="center",
                fontsize=5.6, zorder=4,
                color="#ffffff" if r["score"] > 55 else INK)

    for rank, (_, r) in enumerate(tab.head(3).iterrows(), 1):
        w, h = xe[1] - xe[0], ye[1] - ye[0]
        ax.add_patch(Rectangle((r["cx"] - w / 2, r["cy"] - h / 2), w, h, fill=False,
                               edgecolor="#e34948", linewidth=2.2, zorder=5))
        ax.annotate(f"#{rank}  {r['zone_id']}  ({r['score']:.0f})",
                    xy=(r["cx"], r["cy"] + h / 2), xytext=(0, 7), textcoords="offset points",
                    ha="center", fontsize=9, fontweight="bold", color="#b62a2a", zorder=6,
                    bbox=dict(boxstyle="round,pad=0.28", fc="#ffffff", ec="#e34948", lw=1.1))

    cb = fig.colorbar(mesh, ax=ax, fraction=0.036, pad=0.02)
    # ไม่ใช้ set_label เพราะ matplotlib หมุนข้อความ 90° แล้วอักษรไทยจะอ่านกลับหัว
    cb.ax.set_title("คะแนนโซน\n(0–100)" if THAI_FONT else "zone score\n(0-100)",
                    color=INK_2, fontsize=9.5, pad=8)
    cb.outline.set_linewidth(0.6)

    src = "ข้อมูลจำลอง (synthetic)" if meta["synthetic"] else f"ไฟล์ .dem จริง {meta['n_demos']} ไฟล์"
    ax.set_title(f"Zone Score Heatmap — de_dust2  ({meta['grid_n']}×{meta['grid_n']} grid)",
                 fontsize=17, fontweight="bold", pad=34, color=INK)
    ax.text(0.5, 1.012,
            f"score = kill×{meta['w_kill']:g} + damage×{meta['w_dmg']:g} + weapon_fire×{meta['w_fire']:g}"
            f"  ·  {meta['n_events']:,} events  ·  {src}  ·  กรอบแดง = 3 โซนคะแนนสูงสุด",
            transform=ax.transAxes, ha="center", va="bottom", fontsize=9.5, color=INK_2)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def plot_clusters(ev, pts, cents, info, tab, radar, extent, meta, path):
    fig, ax = plt.subplots(figsize=(12.5, 11.5))
    _base_map(ax, radar, extent, ev)

    noise = pts[pts["cluster"] == -1]
    ax.scatter(noise["x"], noise["y"], s=7, c=NOISE_GRAY, alpha=0.55,
               linewidths=0, zorder=2)

    handles = []
    for rank, (_, c) in enumerate(cents.iterrows()):
        # ชุดสี categorical มี 8 สลอต และห้ามวนใช้ซ้ำ — hotspot ลำดับที่ 9 ขึ้นไป
        # ใช้สีกลางร่วมกัน แต่ยังมีวงกลม + ป้าย C# กำกับทุกก้อน จึงยังแยกออกจากกันได้
        col = CAT[rank] if rank < len(CAT) else "#6f6d66"
        m = pts["cluster"] == c["cluster"]
        ax.scatter(pts.loc[m, "x"], pts.loc[m, "y"], s=11, c=col, alpha=0.8,
                   linewidths=0, zorder=3)
        ax.add_patch(Circle((c["cx"], c["cy"]), c["radius"], fill=False, ec=col,
                            lw=2.0, ls="--", alpha=0.95, zorder=4))
        ax.plot(c["cx"], c["cy"], marker="o", ms=9, mfc=col, mec="#ffffff", mew=1.8, zorder=6)
        # ป้ายกำกับตรงจุดศูนย์กลางทุกกลุ่ม -> ตัวตนของ cluster ไม่ได้พึ่งสีอย่างเดียว
        ax.annotate(f"C{int(c['cluster'])}", xy=(c["cx"], c["cy"]), xytext=(0, 12),
                    textcoords="offset points", ha="center", fontsize=10.5,
                    fontweight="bold", color=INK, zorder=7,
                    bbox=dict(boxstyle="round,pad=0.24", fc="#ffffff", ec=col, lw=1.3))
        if rank < len(CAT):
            handles.append(Line2D([], [], marker="o", ls="", ms=8, mfc=col, mec="none",
                                  label=f"C{int(c['cluster'])} — {int(c['n']):,} จุด, "
                                        f"{int(c['kills'])} kills"))
    if len(cents) > len(CAT):
        handles.append(Line2D([], [], marker="o", ls="", ms=8, mfc="#6f6d66", mec="none",
                              label=f"C{len(CAT)}–C{len(cents)-1} — hotspot ที่เล็กกว่า"))
    handles.append(Line2D([], [], marker="o", ls="", ms=7, mfc=NOISE_GRAY, mec="none",
                          label=f"noise — {len(noise):,} จุด (ไม่รวมกลุ่ม)"))

    # ดาวชี้โซนคะแนนสูงสุดจาก STEP 2 ไว้เทียบด้วยตาว่า ML เจอที่เดียวกันไหม
    t1 = tab.iloc[0]
    ax.plot(t1["cx"], t1["cy"], marker="*", ms=24, mfc="#eda100", mec=INK, mew=1.1, zorder=8)
    handles.append(Line2D([], [], marker="*", ls="", ms=13, mfc="#eda100", mec=INK, mew=0.9,
                          label=f"โซนคะแนนสูงสุด STEP 2 ({t1['zone_id']})"))

    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.015, 1.0),
              frameon=True, fontsize=9, labelcolor=INK_2, borderpad=0.8,
              facecolor=SURFACE, edgecolor="#dcdad2")

    # inset: กราฟ k-distance + จุดหักศอกที่โปรแกรมเลือกเอง (โชว์ว่า auto-tune จริง)
    # พื้นขาวรองทั้งกล่อง (ไม่ใช่แค่พื้นที่กราฟ) ไม่งั้น title/label ของ inset
    # จะไปตกบนภาพแมพสีเข้มจนอ่านไม่ออก
    ax.add_patch(Rectangle((0.030, 0.030), 0.345, 0.250, transform=ax.transAxes,
                           fc="#ffffff", ec="#b9b7ae", lw=1.0, zorder=8.5))
    ins = ax.inset_axes([0.088, 0.088, 0.265, 0.150], zorder=9)
    ins.patch.set_alpha(1.0)
    kd, knee = info["kd"], info["knee"]
    ins.plot(kd, color=CAT[0], lw=1.6)
    ins.axvline(knee, color="#e34948", lw=1.2, ls="--")
    ins.plot([knee], [kd[knee]], marker="o", ms=5, color="#e34948")
    ins.annotate(f"eps = {info['eps']:.0f}", xy=(knee, kd[knee]), xytext=(6, -16),
                 textcoords="offset points", fontsize=8, color="#b62a2a", fontweight="bold")
    ins.set_title(f"k-distance elbow (k={info['min_samples']})", fontsize=9,
                  color=INK, pad=4, fontweight="bold")
    ins.set_xlabel("จุดปะทะทั้งหมด เรียงตามระยะ", fontsize=7, color=INK_2, labelpad=2)
    ins.set_ylabel(f"ระยะถึงเพื่อนบ้านที่ {info['min_samples']}", fontsize=7,
                   color=INK_2, labelpad=2)
    ins.xaxis.set_major_locator(plt.MaxNLocator(4))
    ins.yaxis.set_major_locator(plt.MaxNLocator(4))
    ins.tick_params(labelsize=6.5, colors=INK_MUTED, length=2, pad=1.5)
    ins.set_facecolor("#ffffff")
    for sp in ins.spines.values():
        sp.set_color("#b9b7ae")

    src = "ข้อมูลจำลอง (synthetic)" if meta["synthetic"] else f"ไฟล์ .dem จริง {meta['n_demos']} ไฟล์"
    what = {"conflict": "kill + damage", "kill": "kill", "all": "ทุกอีเวนต์"}[info["cluster_on"]]
    ax.set_title("DBSCAN Cluster Map — hotspot ที่ ML หาเจอเอง (de_dust2)",
                 fontsize=17, fontweight="bold", pad=34, color=INK)
    ax.text(0.5, 1.012,
            f"eps={info['eps']:.0f} (auto จาก k-distance elbow) · min_samples={info['min_samples']}"
            f" · พบ {len(cents)} hotspot · จุดที่ใช้ = {what} {info['n_points']:,} จุด · {src}",
            transform=ax.transAxes, ha="center", va="bottom", fontsize=9.5, color=INK_2)
    fig.savefig(path, dpi=150, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


# ===========================================================================
def main():
    ap = argparse.ArgumentParser(description="CS2 zone scoring + DBSCAN hotspot demo")
    ap.add_argument("--demos", type=int, default=None, help="ใช้ไฟล์ .dem กี่ไฟล์ (ดีฟอลต์: ทั้งหมด)")
    ap.add_argument("--synthetic", action="store_true", help="บังคับใช้ข้อมูลจำลอง")
    ap.add_argument("--grid", type=int, default=GRID_N)
    ap.add_argument("--w-kill", type=float, default=W_KILL)
    ap.add_argument("--w-damage", type=float, default=W_DAMAGE)
    ap.add_argument("--w-fire", type=float, default=W_FIRE)
    ap.add_argument("--min-samples", type=int, default=None, help="ดีฟอลต์คำนวณเองจาก 2*ln(n)")
    ap.add_argument("--cluster-on", choices=list(CLUSTER_SUBSETS), default="conflict",
                    help="อีเวนต์ที่เอาเข้า DBSCAN (ดีฟอลต์ conflict = kill+damage)")
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    t0 = time.time()

    # ---- STEP 1 ----
    ev, synthetic = load_events(args.demos, args.synthetic)
    radar, extent = load_radar()
    if extent is not None and not synthetic:
        # ตัดจุดที่หลุดออกนอกกรอบภาพเรดาร์ทิ้ง (พิกัดเพี้ยน/นอกพื้นที่เล่น)
        ev = ev[(ev.x >= extent[0]) & (ev.x <= extent[1]) &
                (ev.y >= extent[2]) & (ev.y <= extent[3])].reset_index(drop=True)
    n_demos = int(ev["source"].nunique()) if ("source" in ev.columns and not synthetic) else 0
    counts = ev["event_type"].value_counts().to_dict()
    print(f"\nSTEP 1  events ทั้งหมด {len(ev):,} แถว  {counts}")

    meta = {"synthetic": synthetic, "n_demos": n_demos, "n_events": len(ev),
            "grid_n": args.grid, "w_kill": args.w_kill, "w_dmg": args.w_damage,
            "w_fire": args.w_fire}

    # ---- STEP 2 ----
    tab, grid, xe, ye = score_zones(ev, args.grid, args.w_kill, args.w_damage, args.w_fire)
    cols = ["zone_id", "x_range", "y_range", "kill_count", "damage_sum",
            "fire_count", "score", "dominant_side"]
    tab[cols].to_csv(OUT_DIR / "zone_scores.csv", index=False, encoding="utf-8-sig")
    print(f"\nSTEP 2  ตารางคะแนนโซน ({int((tab['score'] > 0).sum())} โซนที่มีเหตุการณ์ "
          f"จาก {args.grid**2} ช่อง) — 10 อันดับแรก:")
    with pd.option_context("display.width", 170, "display.max_columns", 20):
        print(tab[cols].head(10).to_string(index=False))

    # ---- STEP 3 ----
    pts, cents, info = run_dbscan(ev, args.min_samples, args.cluster_on)
    print(f"\nSTEP 3  DBSCAN บนจุด '{args.cluster_on}' {info['n_points']:,} จุด: "
          f"eps={info['eps']:.1f} (auto), min_samples={info['min_samples']}"
          f" -> {len(cents)} hotspot, noise {info['n_noise']:,} จุด "
          f"(ตัดกลุ่มที่เล็กกว่า {info['floor']} จุดทิ้ง {info['n_dropped']} กลุ่ม)")
    if not cents.empty:
        print(cents[["cluster", "n", "kills", "cx", "cy", "radius"]].round(1).to_string(index=False))

    # เทียบ centroid ของ DBSCAN กับโซนคะแนนสูงสุดจาก STEP 2
    # เกณฑ์ "ตรงกัน" = centroid ห่างจากกลางโซนไม่เกิน (รัศมีของ cluster + ครึ่งเส้นทแยงมุมช่อง)
    # แปลว่า "โซนคะแนนสูงนั้นตกอยู่ในอาณาเขตของ hotspot ก้อนนั้นจริง"
    cell = float(np.hypot(xe[1] - xe[0], ye[1] - ye[0]))
    print(f"\n   เทียบผลสองวิธี (ช่องกริดมีเส้นทแยงมุม {cell:.0f} หน่วย):")
    matched, hit_clusters = 0, []
    for rank, (_, r) in enumerate(tab.head(3).iterrows(), 1):
        if cents.empty:
            break
        d = np.hypot(cents["cx"] - r["cx"], cents["cy"] - r["cy"])
        j = int(d.idxmin())
        lim = cents.loc[j, "radius"] + cell / 2
        ok = bool(d[j] <= lim)
        matched += ok
        hit_clusters.append(int(cents.loc[j, "cluster"]))
        print(f"   โซนอันดับ {rank} {r['zone_id']} (score {r['score']:.0f}) -> "
              f"ใกล้ C{cents.loc[j,'cluster']} ที่สุด ห่าง {d[j]:.0f} หน่วย "
              f"(เกณฑ์ {lim:.0f}) {'[ตรงกัน]' if ok else '[ไม่ตรง]'}")

    # ---- STEP 4 ----
    p1, p2 = OUT_DIR / "zone_score_heatmap.png", OUT_DIR / "dbscan_cluster_map.png"
    plot_zone_heatmap(ev, tab, grid, xe, ye, radar, extent, meta, p1)
    plot_clusters(ev, pts, cents, info, tab, radar, extent, meta, p2)
    print(f"\nSTEP 4  บันทึกภาพแล้ว:\n   {p1}\n   {p2}\n   {OUT_DIR / 'zone_scores.csv'}")

    # ---- STEP 5 : สรุปสำหรับพูดหน้าอาจารย์ ----
    print("\n" + "=" * 78)
    print("สรุปผล (ภาษาไทย) — สำหรับนำเสนอ")
    print("=" * 78)
    src = "ข้อมูลจำลอง 1 แมพ" if synthetic else f"ไฟล์ .dem จริง {n_demos} ไฟล์ (de_dust2)"
    print(f"• ข้อมูลที่ใช้: {src} รวม {len(ev):,} เหตุการณ์ (kill / damage / weapon_fire)")
    print(f"• พบ hotspot ทั้งหมด {len(cents)} จุด จาก DBSCAN "
          f"(รันบนจุดปะทะ kill+damage {info['n_points']:,} จุด "
          f"อีก {info['n_noise']:,} จุดถูกจัดเป็น noise คือเหตุการณ์ที่กระจัดกระจาย ไม่รวมกลุ่มพอ)")
    print("• โซนที่คะแนนสูงสุด 3 อันดับ:")
    for rank, (_, r) in enumerate(tab.head(3).iterrows(), 1):
        print(f"    {rank}. {r['zone_id']}  คะแนน {r['score']:.0f}/100  "
              f"(x={r['x_range']}, y={r['y_range']})")
        print(f"       kill {r['kill_count']} · damage รวม {r['damage_sum']:.0f} · "
              f"ยิง {r['fire_count']} ครั้ง · ฝ่ายที่คุมโซน: {r['dominant_side']}")
    print(f"• DBSCAN ใช้ eps={info['eps']:.0f} และ min_samples={info['min_samples']}")
    print(f"    - eps ไม่ได้ตั้งเอง แต่คำนวณจากกราฟ k-distance: เรียงระยะจากทุกจุดไปเพื่อนบ้าน")
    print(f"      ลำดับที่ {info['min_samples']} แล้วหา 'จุดหักศอก' ของกราฟ ซึ่งคือระยะที่แยก")
    print(f"      จุดในบริเวณหนาแน่นออกจากจุดโดดเดี่ยว จึงเป็นรัศมีที่ข้อมูลบอกเองว่าเหมาะ")
    print(f"    - min_samples={info['min_samples']} มาจากกฎ 2·ln(n) ตามจำนวนจุดที่เข้า DBSCAN "
          f"{info['n_points']:,} จุด")
    print(f"      ยิ่งข้อมูลเยอะ ยิ่งต้องมีเพื่อนบ้านมากขึ้นถึงจะนับว่าหนาแน่นจริง ไม่ใช่บังเอิญ")
    if not cents.empty:
        uniq = len(set(hit_clusters))
        print(f"• ผลตรวจสอบไขว้: โซนคะแนนสูง 3 อันดับ มี {matched}/3 โซนที่ตกอยู่ในอาณาเขต hotspot ของ DBSCAN"
              f" (ไปตรงกับ hotspot {uniq} ก้อนที่ต่างกัน: "
              f"{', '.join('C%d' % c for c in dict.fromkeys(hit_clusters))})")
        if matched == 3 and uniq == 3:
            print("    -> สองวิธีที่คิดกันคนละแบบ (สูตรที่คนตั้งน้ำหนักเอง vs. ML ที่หาเองจากความหนาแน่น)")
            print("       ชี้ไปพื้นที่เดียวกัน และเป็นคนละก้อนกันจริง ไม่ใช่ก้อนใหญ่ก้อนเดียวกลืนทุกโซน")
            print("       ผลจึงยืนยันกันเอง (cross-validation) ว่าโซนสำคัญที่หาได้ไม่ได้มาจากสูตรที่ตั้งเอง")
        elif matched:
            print(f"    -> ตรงกัน {matched} จาก 3 โซน ส่วนที่ไม่ตรงคือโซนที่คะแนนสูงจากดาเมจ/การยิงสะสม")
            print("       แต่จุดปะทะไม่ได้เกาะกลุ่มหนาแน่นพอให้ DBSCAN นับเป็น hotspot")
        else:
            print("    -> ยังไม่ตรงกันเลย: สูตรให้คะแนนกับความหนาแน่นของจุดปะทะกำลังชี้คนละที่")
            print("       ต้องกลับไปดูน้ำหนักในสูตร (--w-kill/--w-damage/--w-fire) หรือขนาดกริดก่อนสรุป")
    print(f"\n(ใช้เวลาทั้งหมด {time.time() - t0:.1f} วินาที)")


if __name__ == "__main__":
    main()
