#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CS2 Map Zone Analysis — เวอร์ชันพื้นฐาน (เขียนให้อ่านง่าย ไว้ศึกษา/ลองปรับค่าเล่น)

ทำอะไรบ้าง
  STEP 1  โหลดเหตุการณ์ (kill / damage / weapon_fire) จากไฟล์ .dem ในโฟลเดอร์ demo/
  STEP 2  แบ่งแมพเป็นกริด GRID_N x GRID_N แล้วให้คะแนนแต่ละช่องตามความรุนแรงของการปะทะ
  STEP 3  ใช้ DBSCAN (unsupervised) หา hotspot จากจุดปะทะจริง โดยไม่สนเส้นกริด
  STEP 4  วาดภาพ 2 ใบ + เซฟ CSV ลงโฟลเดอร์ output/
  STEP 5  พิมพ์สรุปว่าสองวิธีชี้ไปที่เดียวกันไหม

รัน:  python main.py
อยากลองอะไรก็แก้ที่บล็อก CONFIG ข้างล่างแล้วรันใหม่ (ไม่ต้องแตะส่วนอื่น)
ของเดิมเวอร์ชันเต็ม (พื้นหลังเรดาร์ + auto-tune eps + CLI) เก็บไว้ที่ main_full.py
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")           # เซฟเป็นไฟล์ ไม่ต้องเปิดหน้าต่าง
import matplotlib.pyplot as plt
from sklearn.cluster import DBSCAN
from sklearn.neighbors import NearestNeighbors

# ===========================================================================
# CONFIG — ปรับตรงนี้ที่เดียว
# ===========================================================================
USE_SYNTHETIC = False   # True = ใช้ข้อมูลจำลอง (ไม่ต้องมีไฟล์ .dem)
MAX_DEMOS     = 2       # parse ไฟล์ .dem กี่ไฟล์ (ยิ่งเยอะยิ่งช้า ไฟล์ละ ~1-2 นาที)

GRID_N   = 20           # แบ่งแมพเป็นกี่ช่อง (20 = 20x20 = 400 ช่อง)
W_KILL   = 3.0          # สูตรคะแนน: kill*W_KILL + damage*W_DAMAGE + weapon_fire*W_FIRE
W_DAMAGE = 0.1
W_FIRE   = 1.0

# DBSCAN — ลองเปลี่ยนแล้วดูว่าจำนวน hotspot เปลี่ยนยังไง
CLUSTER_ON  = ["kill", "damage"]  # เอาอีเวนต์ไหนเข้า DBSCAN (ใส่ "weapon_fire" ด้วยก็ได้)
EPS         = 150       # รัศมีที่ถือว่า "ใกล้กัน" (หน่วยพิกัดเกม) — None = ให้โปรแกรมเดาให้
MIN_SAMPLES = 12        # ต้องมีเพื่อนบ้านในรัศมีกี่จุด ถึงนับว่าเป็นบริเวณหนาแน่น

ROOT     = Path(__file__).resolve().parent.parent   # รากโปรเจกต์ (ไฟล์นี้อยู่ใน Exparser/)
DEMO_DIR = ROOT / "demos"
OUT_DIR  = ROOT / "output"

for _s in (sys.stdout, sys.stderr):     # ให้คอนโซล Windows พิมพ์ไทยได้
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


# ===========================================================================
# STEP 1 — โหลดข้อมูล
# ===========================================================================
# ตาราง events ที่ทุกฟังก์ชันใช้ร่วมกัน มีคอลัมน์:
#   x, y        พิกัดจุดเกิดเหตุ (kill/damage ใช้พิกัดเหยื่อ, weapon_fire ใช้พิกัดคนยิง)
#   round       รอบที่เท่าไร
#   side        ฝั่งของคนที่ยืนอยู่ตรง (x,y) -> 'CT' หรือ 'T'
#   event_type  'kill' | 'damage' | 'weapon_fire'
#   damage      ดาเมจของอีเวนต์นั้น (weapon_fire = 0)
#   killer_side ฝั่งของคนยิง (ใช้ดูว่าใครคุมโซนนั้น)

def _side(v):
    """awpy คืนค่ามาเป็น 'ct'/'t' -> ทำให้เป็น 'CT'/'T'"""
    t = str(v).strip().lower()
    return "CT" if t.startswith("ct") else ("T" if t.startswith("t") else None)


def events_from_demo(path):
    """แปลงไฟล์ .dem 1 ไฟล์ เป็นตาราง events"""
    from awpy import Demo

    dem = Demo(path=path, tickrate=64)
    dem.parse()
    frames = []

    for attr, etype in (("kills", "kill"), ("damages", "damage")):
        tbl = getattr(dem, attr, None)
        if tbl is None or tbl.is_empty():
            continue
        d = tbl.to_pandas()
        frames.append(pd.DataFrame({
            "x": d["victim_X"], "y": d["victim_Y"], "round": d["round_num"],
            "side": d["victim_side"].map(_side), "event_type": etype,
            "damage": pd.to_numeric(d["dmg_health"], errors="coerce").fillna(0.0)
                      if "dmg_health" in d.columns else 0.0,
            "killer_side": d["attacker_side"].map(_side),
        }))

    shots = getattr(dem, "shots", None)
    if shots is not None and not shots.is_empty():
        s = shots.to_pandas()
        # ตัดการฟันมีดออก — คนถือมีดวิ่งไปทั้งแมพ นั่นคือการเคลื่อนที่ ไม่ใช่การปะทะ
        s = s[~s["weapon"].astype(str).str.contains("knife", case=False, na=False)]
        frames.append(pd.DataFrame({
            "x": s["player_X"], "y": s["player_Y"], "round": s["round_num"],
            "side": s["player_side"].map(_side), "event_type": "weapon_fire",
            "damage": 0.0, "killer_side": None,
        }))

    out = pd.concat(frames, ignore_index=True)
    out["source"] = path.name
    return out.dropna(subset=["x", "y"])


def make_synthetic_events(n=2600, seed=42):
    """ข้อมูลจำลอง: 4 จุดที่ปะทะกันหนัก + noise ทั่วแมพ ไว้ทดสอบว่า DBSCAN แยกออกจริงไหม"""
    rng = np.random.default_rng(seed)
    hotspots = [("Mid", -400, 800, 210, 0.22, "CT"), ("A site", 900, 1900, 240, 0.24, "CT"),
                ("B site", -1750, 2450, 230, 0.20, "T"), ("Long A", 700, 200, 260, 0.16, "T")]
    rows = []
    for _, cx, cy, sd, frac, owner in hotspots:
        m = int(n * frac)
        rows.append(pd.DataFrame({
            "x": rng.normal(cx, sd, m), "y": rng.normal(cy, sd, m),
            # ฝั่งที่คุมโซนนี้ชนะการปะทะราว 70%
            "killer_side": rng.choice([owner, "T" if owner == "CT" else "CT"], m, p=[0.7, 0.3]),
        }))
    n_noise = int(n * (1 - sum(h[4] for h in hotspots)))
    rows.append(pd.DataFrame({
        "x": rng.uniform(-2300, 1900, n_noise), "y": rng.uniform(-1200, 3100, n_noise),
        "killer_side": rng.choice(["CT", "T"], n_noise),
    }))
    df = pd.concat(rows, ignore_index=True)
    df["event_type"] = rng.choice(["kill", "damage", "weapon_fire"], len(df), p=[.08, .22, .70])
    df["side"] = np.where(df["killer_side"] == "CT", "T", "CT")   # เหยื่อคือฝั่งตรงข้ามคนยิง
    df["round"] = rng.integers(1, 25, len(df))
    df["damage"] = np.where(df["event_type"] == "weapon_fire", 0.0,
                            rng.integers(8, 100, len(df)).astype(float))
    df.loc[df["event_type"] == "weapon_fire", "killer_side"] = None
    df["source"] = "synthetic"
    return df


def load_events():
    """คืน (ตาราง events, ใช้ข้อมูลจำลองหรือเปล่า) — parse แล้วเก็บ cache ไว้ รันซ้ำได้เร็ว"""
    dems = sorted(DEMO_DIR.glob("*.dem"))[:MAX_DEMOS] if DEMO_DIR.is_dir() else []
    if USE_SYNTHETIC or not dems:
        if not dems and not USE_SYNTHETIC:
            print(f"! ไม่พบไฟล์ .dem ใน {DEMO_DIR} — ใช้ข้อมูลจำลองแทน")
        return make_synthetic_events(), True

    cache = OUT_DIR / f"events_{len(dems)}demos.csv"
    if cache.exists():
        print(f"» ใช้ cache {cache.name} (ลบไฟล์นี้ถ้าอยาก parse ใหม่)")
        return pd.read_csv(cache), False

    print(f"» parse ไฟล์ .dem {len(dems)} ไฟล์ ...")
    frames = []
    for i, d in enumerate(dems, 1):
        t0 = time.time()
        ev = events_from_demo(d)
        frames.append(ev)
        print(f"   [{i}/{len(dems)}] {d.name}  {len(ev):,} events ({time.time() - t0:.0f}s)")
    df = pd.concat(frames, ignore_index=True)
    df.to_csv(cache, index=False)
    return df, False


# ===========================================================================
# STEP 2 — ให้คะแนนโซนบนกริด
# ===========================================================================
def score_zones(ev):
    """
    แบ่งกริดตามขอบเขต x,y ของข้อมูล แล้วให้คะแนนแต่ละช่อง
        score_raw = kill*W_KILL + damage*W_DAMAGE + weapon_fire*W_FIRE
        score     = 100 * score_raw / max(score_raw)      (ปรับให้อยู่ในช่วง 0-100)
    คืน (ตารางโซนเรียงตามคะแนน, กริด 2 มิติไว้วาดภาพ, เส้นแบ่งแกน x, เส้นแบ่งแกน y)
    """
    xe = np.linspace(ev["x"].min(), ev["x"].max(), GRID_N + 1)
    ye = np.linspace(ev["y"].min(), ev["y"].max(), GRID_N + 1)

    ev = ev.copy()
    # clip กันจุดที่อยู่ริมขอบขวา/ขอบบนพอดี ไม่ให้หลุดออกนอกกริด
    ev["ix"] = np.clip(np.digitize(ev["x"], xe) - 1, 0, GRID_N - 1)
    ev["iy"] = np.clip(np.digitize(ev["y"], ye) - 1, 0, GRID_N - 1)
    ev["is_kill"] = (ev["event_type"] == "kill").astype(int)
    ev["is_fire"] = (ev["event_type"] == "weapon_fire").astype(int)
    ev["dmg"] = pd.to_numeric(ev["damage"], errors="coerce").fillna(0.0)

    tab = (ev.groupby(["iy", "ix"])
             .agg(kills=("is_kill", "sum"), fires=("is_fire", "sum"),
                  damage=("dmg", "sum"), events=("is_kill", "size"))
             .reset_index())

    raw = tab["kills"] * W_KILL + tab["damage"] * W_DAMAGE + tab["fires"] * W_FIRE
    tab["score"] = (100 * raw / raw.max()).round(1) if raw.max() > 0 else 0.0

    # ใครคุมโซนนี้ = ฝั่งที่ทำ kill สำเร็จในโซนนี้บ่อยกว่า
    kills = ev[ev["is_kill"] == 1]
    owner = (kills.groupby(["iy", "ix", "killer_side"]).size().rename("n").reset_index()
                  .sort_values("n", ascending=False).drop_duplicates(["iy", "ix"])
                  .set_index(["iy", "ix"])["killer_side"])
    tab["owner"] = owner.reindex(pd.MultiIndex.from_frame(tab[["iy", "ix"]])).fillna("-").to_numpy()

    tab["zone"] = ("Z" + tab["ix"].astype(str).str.zfill(2)
                   + "-" + tab["iy"].astype(str).str.zfill(2))
    tab["cx"] = (xe[tab["ix"]] + xe[tab["ix"] + 1]) / 2     # จุดกลางช่อง ไว้วาด/เทียบระยะ
    tab["cy"] = (ye[tab["iy"]] + ye[tab["iy"] + 1]) / 2
    tab = tab.sort_values("score", ascending=False).reset_index(drop=True)

    grid = np.zeros((GRID_N, GRID_N))
    grid[tab["iy"], tab["ix"]] = tab["score"]
    return tab, grid, xe, ye


# ===========================================================================
# STEP 3 — DBSCAN หา hotspot
# ===========================================================================
def suggest_eps(xy, k):
    """
    เดาค่า eps จากกราฟ k-distance: เรียงระยะจากทุกจุดไปเพื่อนบ้านลำดับที่ k จากน้อยไปมาก
    กราฟจะแบนยาว ๆ (จุดที่อยู่ในบริเวณหนาแน่น) แล้วหักศอกพุ่งขึ้น (จุดโดดเดี่ยว)
    "หัวเข่า" ของกราฟคือระยะที่แยกสองพวกนี้ออกจากกัน = eps ที่ข้อมูลบอกเองว่าเหมาะ
    """
    dist, _ = NearestNeighbors(n_neighbors=k).fit(xy).kneighbors(xy)
    kd = np.sort(dist[:, -1])[:int(len(xy) * 0.9)]      # ตัดหางบน 10% ทิ้ง กันจุดสุดขั้วดึงผล
    i = np.arange(len(kd), dtype=float)
    chord = np.interp(i, [i[0], i[-1]], [kd[0], kd[-1]])   # เส้นตรงจากจุดแรกไปจุดสุดท้าย
    return float(kd[np.argmax(chord - kd)])                # จุดที่ห่างจากเส้นตรงมากที่สุด


def run_dbscan(ev):
    """คืน (จุดที่ใช้ พร้อมคอลัมน์ cluster, ตารางสรุปแต่ละ hotspot, eps ที่ใช้จริง)"""
    pts = ev[ev["event_type"].isin(CLUSTER_ON)].copy().reset_index(drop=True)
    xy = pts[["x", "y"]].to_numpy(dtype=float)

    hint = suggest_eps(xy, MIN_SAMPLES)
    eps = EPS if EPS else hint
    print(f"   (eps ที่กราฟ k-distance แนะนำ = {hint:.0f} / ที่ใช้จริง = {eps:.0f})")

    pts["cluster"] = DBSCAN(eps=eps, min_samples=MIN_SAMPLES).fit_predict(xy)

    # เรียงเลขกลุ่มใหม่ตามขนาด ให้ C0 = hotspot ใหญ่สุดเสมอ อ่านง่ายเวลานำเสนอ
    sizes = pts.loc[pts["cluster"] >= 0, "cluster"].value_counts()
    remap = {c: i for i, c in enumerate(sizes.index)}
    pts["cluster"] = pts["cluster"].map(lambda c: remap.get(c, -1))

    rows = []
    for c in sorted(remap.values()):
        p = pts[pts["cluster"] == c]
        rows.append({
            "cluster": c, "n": len(p),
            "kills": int((p["event_type"] == "kill").sum()),
            "cx": p["x"].mean(), "cy": p["y"].mean(),
            # รัศมีที่ครอบ 80% ของจุดในกลุ่ม ไว้วาดวงให้เห็นขนาดโซนคร่าว ๆ
            "radius": float(np.percentile(
                np.hypot(p["x"] - p["x"].mean(), p["y"] - p["y"].mean()), 80)),
        })
    return pts, pd.DataFrame(rows), eps


# ===========================================================================
# STEP 4 — วาดภาพ
# ===========================================================================
def plot_zones(tab, grid, xe, ye, path):
    fig, ax = plt.subplots(figsize=(9, 8))
    mesh = ax.pcolormesh(xe, ye, np.ma.masked_where(grid <= 0, grid),   # ช่องว่าง = ไม่ระบายสี
                         cmap="YlOrRd", vmin=0, vmax=100,
                         edgecolors="white", linewidth=0.3)
    fig.colorbar(mesh, ax=ax, label="zone score (0-100)")

    for rank, (_, r) in enumerate(tab.head(3).iterrows(), 1):     # ป้าย 3 โซนแรงสุด
        ax.annotate(f"#{rank} {r['zone']}", (r["cx"], r["cy"]), ha="center", fontsize=9,
                    fontweight="bold", bbox=dict(boxstyle="round", fc="white", ec="red"))

    ax.set_aspect("equal")
    ax.set_xlabel("game X")
    ax.set_ylabel("game Y")
    ax.set_title(f"STEP 2 - Zone Score ({GRID_N}x{GRID_N} grid)\n"
                 f"score = kill*{W_KILL:g} + damage*{W_DAMAGE:g} + fire*{W_FIRE:g}")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def plot_clusters(pts, cents, eps, top_zone, path):
    fig, ax = plt.subplots(figsize=(9, 8))
    noise = pts[pts["cluster"] == -1]
    ax.scatter(noise["x"], noise["y"], s=6, c="lightgray", label=f"noise ({len(noise):,})")

    colors = plt.get_cmap("tab10").colors
    for _, c in cents.iterrows():
        col = colors[int(c["cluster"]) % 10]
        m = pts["cluster"] == c["cluster"]
        ax.scatter(pts.loc[m, "x"], pts.loc[m, "y"], s=8, color=col,
                   label=f"C{int(c['cluster'])} - {int(c['n']):,} pts / {int(c['kills'])} kills")
        ax.add_patch(plt.Circle((c["cx"], c["cy"]), c["radius"], fill=False, ec=col, ls="--"))
        ax.annotate(f"C{int(c['cluster'])}", (c["cx"], c["cy"]), ha="center", fontweight="bold",
                    bbox=dict(boxstyle="round", fc="white", ec=col))

    # ดาว = โซนคะแนนสูงสุดจาก STEP 2 ไว้ดูด้วยตาว่า ML เจอที่เดียวกันไหม
    ax.plot(top_zone["cx"], top_zone["cy"], marker="*", ms=20, mfc="gold", mec="black",
            ls="", label=f"top zone STEP 2 ({top_zone['zone']})")

    ax.set_aspect("equal")
    ax.set_xlabel("game X")
    ax.set_ylabel("game Y")
    ax.set_title(f"STEP 3 - DBSCAN hotspots (eps={eps:.0f}, min_samples={MIN_SAMPLES})")
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)


# ===========================================================================
def main():
    OUT_DIR.mkdir(exist_ok=True)
    t0 = time.time()

    # ---- STEP 1 ----
    ev, synthetic = load_events()
    print(f"\nSTEP 1  events {len(ev):,} แถว  {ev['event_type'].value_counts().to_dict()}")

    # ---- STEP 2 ----
    tab, grid, xe, ye = score_zones(ev)
    cols = ["zone", "kills", "damage", "fires", "score", "owner"]
    tab[cols].to_csv(OUT_DIR / "zone_scores.csv", index=False, encoding="utf-8-sig")
    print(f"\nSTEP 2  มีเหตุการณ์ {int((tab['score'] > 0).sum())} ช่อง จาก {GRID_N ** 2} ช่อง "
          f"— 10 อันดับแรก:")
    print(tab[cols].head(10).to_string(index=False))

    # ---- STEP 3 ----
    print(f"\nSTEP 3  DBSCAN บนอีเวนต์ {CLUSTER_ON}")
    pts, cents, eps = run_dbscan(ev)
    print(f"   ใช้จุดปะทะ {len(pts):,} จุด -> {len(cents)} hotspot, "
          f"noise {int((pts['cluster'] == -1).sum()):,} จุด")
    if not cents.empty:
        print(cents.round(0).to_string(index=False))
        cents.to_csv(OUT_DIR / "hotspots.csv", index=False, encoding="utf-8-sig")

    # ---- STEP 4 ----
    plot_zones(tab, grid, xe, ye, OUT_DIR / "zone_score_heatmap.png")
    plot_clusters(pts, cents, eps, tab.iloc[0], OUT_DIR / "dbscan_cluster_map.png")
    print(f"\nSTEP 4  เซฟลงโฟลเดอร์ {OUT_DIR.name}/ แล้ว: "
          "zone_score_heatmap.png, dbscan_cluster_map.png, zone_scores.csv, hotspots.csv")

    # ---- STEP 5 : สรุป ----
    print("\n" + "=" * 70)
    print("สรุปผล")
    print("=" * 70)
    print(f"• ข้อมูลที่ใช้: {'ข้อมูลจำลอง' if synthetic else 'ไฟล์ .dem จริง'} "
          f"รวม {len(ev):,} เหตุการณ์")
    print("• โซนคะแนนสูงสุด 3 อันดับ (จากสูตรที่เราตั้งน้ำหนักเอง):")
    for rank, (_, r) in enumerate(tab.head(3).iterrows(), 1):
        print(f"    {rank}. {r['zone']}  {r['score']:.0f}/100  "
              f"(kill {r['kills']} · damage {r['damage']:.0f} · ยิง {r['fires']} ครั้ง "
              f"· ฝ่ายที่คุมโซน {r['owner']})")

    # เทียบสองวิธี: โซนคะแนนสูงตกอยู่ในอาณาเขตของ hotspot ก้อนไหนหรือเปล่า
    if not cents.empty:
        cell = float(np.hypot(xe[1] - xe[0], ye[1] - ye[0]))    # เส้นทแยงมุมของช่องกริด
        matched = 0
        print("• เทียบกับ hotspot ที่ DBSCAN หาเจอเอง:")
        for _, r in tab.head(3).iterrows():
            d = np.hypot(cents["cx"] - r["cx"], cents["cy"] - r["cy"])
            j = int(d.idxmin())
            lim = cents.loc[j, "radius"] + cell / 2     # เกณฑ์ = รัศมีกลุ่ม + ครึ่งช่องกริด
            ok = d[j] <= lim
            matched += ok
            print(f"    โซน {r['zone']} -> ใกล้ C{cents.loc[j, 'cluster']} ที่สุด "
                  f"ห่าง {d[j]:.0f} (เกณฑ์ {lim:.0f}) {'[ตรงกัน]' if ok else '[ไม่ตรง]'}")
        print(f"  => ตรงกัน {matched}/3 โซน — สูตรที่คนตั้งน้ำหนักเอง กับ ML ที่หาเองจาก")
        print("     ความหนาแน่นของจุดปะทะ ชี้ไปที่เดียวกันไหม คือตัวบอกว่าผลน่าเชื่อถือแค่ไหน")

    print(f"\n(ใช้เวลา {time.time() - t0:.1f} วินาที)")


if __name__ == "__main__":
    main()
