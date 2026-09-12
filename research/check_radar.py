#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_radar.py — ตรวจว่าค่าปรับเทียบเรดาร์ใน assets/radars.json ถูกต้องไหม

    python research/tools/check_radar.py                        ตรวจทุกแมพที่มีค่าปรับเทียบ
    python research/tools/check_radar.py de_dust2               ตรวจแมพเดียว
    python research/tools/check_radar.py de_dust2 --try -2476 3239 4.4    ลองค่าใหม่โดยยังไม่แก้ไฟล์
    python research/tools/check_radar.py de_dust2 --png         เซฟภาพจุดตายทับเรดาร์ไว้ดูด้วยตา

ปัญหาที่สคริปต์นี้แก้
    ค่า pos_x / pos_y / scale ผิดแล้ว "ไม่มี error" ให้เห็นเลย ภาพเรดาร์ยังขึ้นปกติ
    heatmap ยังวาดออกมาสวย ๆ แค่จุดไปตกผิดที่ทั้งหมด อ่านผลแล้วสรุปผิดโดยไม่รู้ตัว

วิธีตรวจ
    ภาพเรดาร์ของ CS2 เป็น PNG ที่ "พื้นที่เดินได้ทึบ ส่วนนอกแมพโปร่งใส"
    เอาพิกัดจุดที่คนตายจริงมาฉายลงภาพด้วยสูตรเดียวกับหน้าเว็บ
        px = (game_x - pos_x) / scale
        py = (pos_y - game_y) / scale
    แล้วนับว่ากี่ % ตกลงบนพิกเซลที่ทึบ — คนตายต้องอยู่ในที่ที่เดินได้เสมอ

    ค่าที่ถูก  99%+     ค่าที่ผิด  ร่วงชัดเจน (ค่าเก่าสมัย CSGO ของ dust2 ได้ 80.3%)

    เกณฑ์นี้ตรวจได้เพราะ "เฉลยอยู่ในข้อมูลอยู่แล้ว" ไม่ใช่คะแนนที่เราตั้งเอง
    เป็นแนวคิดเดียวกับที่ใช้ทั้งโปรเจกต์
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---- จุดตายจริง: ลอง PostgreSQL ก่อน (มีทุกแมตช์ที่อัปโหลด) ต่อไม่ได้ค่อยถอยไป data/all_kills.csv
CSV = ROOT / "data" / "all_kills.csv"

# JOIN เดียวได้ตารางหน้าตาเหมือน csv — alias ชื่อคอลัมน์ให้ตรงกับที่ demoparser.py เคยสร้าง
# ใส่เครื่องหมายคำพูดครอบ "victim_X" เพราะ PostgreSQL แปลงชื่อที่ไม่มีเครื่องหมายเป็นตัวเล็กหมด
SQL = """
SELECT m.demo_file, m.map_name, m.tickrate,
       r.round_num, r.start_tick AS round_start_tick, r.bomb_plant_tick, r.winner_side AS round_winner,
       k.tick, k.attacker_side, k.victim_side,
       k.victim_x   AS "victim_X",   k.victim_y   AS "victim_Y",   k.victim_place,
       k.attacker_x AS "attacker_X", k.attacker_y AS "attacker_Y", k.attacker_place,
       k.weapon, k.headshot
FROM kills k
JOIN rounds r  ON r.id = k.round_id
JOIN matches m ON m.id = r.match_id
WHERE ($1::text IS NULL OR m.map_name = $1)
ORDER BY m.demo_file, r.round_num, k.tick, k.id
"""


def _from_db(map_name: str | None) -> pd.DataFrame:
    import asyncpg

    from backend.db import DATABASE_URL, redacted_url

    async def go():
        conn = await asyncpg.connect(DATABASE_URL, timeout=5)
        try:
            return await conn.fetch(SQL, map_name)
        finally:
            await conn.close()

    rows = asyncio.run(go())
    df = pd.DataFrame([dict(r) for r in rows])
    df.attrs["source"] = f"PostgreSQL {redacted_url()}"
    return df


def _from_csv(map_name: str | None) -> pd.DataFrame:
    if not CSV.exists():
        raise FileNotFoundError(f"ไม่พบ {CSV} — รัน python research/prep/demoparser.py ก่อน")
    df = pd.read_csv(CSV)
    if map_name and "map_name" in df.columns:
        df = df[df["map_name"] == map_name]
    df.attrs["source"] = f"csv {CSV.name}"     # ตั้งหลังกรอง เพราะ attrs ไม่รับประกันว่าจะติดไปกับผลของการกรอง
    return df


def load_kills(map_name: str | None = None, source: str = "auto") -> pd.DataFrame:
    """คืนคิลของแมพที่ขอ (None = ทุกแมพ) จากแหล่งที่เลือก: "db" / "csv" / "auto"

    auto = ลอง DB ก่อน ถ้าต่อไม่ได้หรือไม่มีคิลของแมพนั้น ถอยไป csv พร้อมพิมพ์บอก
    ตั้งค่าเริ่มต้นได้ด้วย environment ML_SOURCE (เช่นใน Dockerfile ตั้ง ML_SOURCE=csv)
    """
    source = (source or os.environ.get("ML_SOURCE") or "auto").lower()
    if source == "db":
        return _from_db(map_name)
    if source == "csv":
        return _from_csv(map_name)
    if source != "auto":
        raise ValueError(f"source ต้องเป็น db / csv / auto ไม่ใช่ {source!r}")

    try:
        df = _from_db(map_name)
        if not df.empty:
            return df
        print(f"!! ต่อ DB ได้แต่ไม่มีคิลของแมพ {map_name} — ถอยไปใช้ csv")
    except Exception as e:                        # DB ปิดอยู่ / ไม่มี asyncpg / รหัสผ่านผิด — ถอยไป csv ทั้งหมด
        print(f"!! ต่อ DB ไม่ได้ ({type(e).__name__}) — ถอยไปใช้ csv")
    return _from_csv(map_name)


RADARS = ROOT / "assets" / "radars.json"
ASSETS = ROOT / "assets"
ALPHA_MIN = 8       # อัลฟ่าต่ำกว่านี้ถือว่าโปร่งใส (นอกแมพ)
PASS_PCT = 99.0     # ต่ำกว่านี้ถือว่าค่าปรับเทียบน่าสงสัย

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def project(xs, ys, cal):
    """พิกัดเกม -> พิกเซลบนภาพ (สูตรเดียวกับ frontend/static/map.js และ /api/radar)"""
    return (xs - cal["pos_x"]) / cal["scale"], (cal["pos_y"] - ys) / cal["scale"]


def check(map_name: str, cal: dict, source: str = "auto", save_png: bool = False) -> float:
    df = load_kills(map_name, source=source)
    df = df.dropna(subset=["victim_X", "victim_Y"])
    if df.empty:
        print(f"{map_name}: ไม่มีจุดตายในข้อมูล — ตรวจไม่ได้ (โหลดเดโมของแมพนี้เข้ามาก่อน)")
        return float("nan")

    img = Image.open(ASSETS / cal["image"].lstrip("/")).convert("RGBA")
    size = img.size[0]
    if img.size[0] != img.size[1]:
        print(f"{map_name}: !! ภาพไม่เป็นจัตุรัส {img.size} — สูตรนี้รองรับเฉพาะภาพจัตุรัส")
    if size != cal["size"]:
        print(f"{map_name}: !! ภาพจริง {size}px แต่ radars.json เขียน size={cal['size']} — แก้ให้ตรงกันก่อน")

    px, py = project(df["victim_X"].to_numpy(float), df["victim_Y"].to_numpy(float), cal)
    inside = (px >= 0) & (px < size) & (py >= 0) & (py < size)

    alpha = np.array(img)[:, :, 3]
    walkable = inside.copy()
    xi = np.clip(px.astype(int), 0, size - 1)
    yi = np.clip(py.astype(int), 0, size - 1)
    walkable[inside] = alpha[yi[inside], xi[inside]] > ALPHA_MIN

    pct_in, pct_ok = inside.mean() * 100, walkable.mean() * 100
    mark = "ผ่าน" if pct_ok >= PASS_PCT else "น่าสงสัย"
    print(f"{map_name}: {len(df):,} จุด | ในกรอบภาพ {pct_in:5.1f}% | บนพื้นที่เดินได้ {pct_ok:5.1f}%  -> {mark}"
          f"   (pos {cal['pos_x']}/{cal['pos_y']} scale {cal['scale']})")

    if save_png:
        out = ROOT / "output" / f"check_radar_{map_name}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        canvas = Image.alpha_composite(Image.new("RGBA", img.size, (10, 19, 34, 255)), img)
        a = np.array(canvas)
        for x, y, ok in zip(xi[inside], yi[inside], walkable[inside]):
            colour = (110, 231, 168) if ok else (255, 90, 70)      # เขียว = ตกถูกที่, แดง = ตกนอกพื้นที่เดินได้
            a[max(y - 1, 0):y + 2, max(x - 1, 0):x + 2, :3] = colour
        Image.fromarray(a).convert("RGB").save(out)
        print(f"          เซฟภาพตรวจไว้ที่ {out}  (เขียว = ตกถูกที่, แดง = ตกนอกแมพ)")

    return pct_ok


def main() -> None:
    ap = argparse.ArgumentParser(description="ตรวจค่าปรับเทียบเรดาร์ด้วยจุดตายจริง")
    ap.add_argument("map", nargs="?", help="ชื่อแมพ เช่น de_dust2 (ไม่ใส่ = ตรวจทุกแมพใน radars.json)")
    ap.add_argument("--try", dest="trial", nargs=3, type=float, metavar=("POS_X", "POS_Y", "SCALE"),
                    help="ลองค่าชุดใหม่โดยยังไม่แก้ radars.json")
    ap.add_argument("--source", default="auto", help="db / csv / auto (ค่าตั้งต้น auto)")
    ap.add_argument("--png", action="store_true", help="เซฟภาพจุดตายทับเรดาร์ไว้ดูด้วยตา")
    args = ap.parse_args()

    data = json.loads(RADARS.read_text(encoding="utf-8"))
    maps = {k: v for k, v in data.items() if isinstance(v, dict) and not k.startswith("_")}

    if args.map:
        if args.map not in maps and not args.trial:
            sys.exit(f"ไม่มี {args.map} ใน radars.json — ใส่ --try POS_X POS_Y SCALE เพื่อลองค่าใหม่")
        cal = dict(maps.get(args.map, {"image": f"/maps/{args.map}.png", "size": 1024}))
        if args.trial:
            cal["pos_x"], cal["pos_y"], cal["scale"] = args.trial[0], args.trial[1], args.trial[2]
        maps = {args.map: cal}

    worst = 100.0
    for name, cal in maps.items():
        pct = check(name, cal, source=args.source, save_png=args.png)
        if pct == pct:                      # ไม่ใช่ NaN (แมพที่ไม่มีข้อมูลไม่นับเป็นตก)
            worst = min(worst, pct)

    if worst < PASS_PCT:
        sys.exit(f"\nมีแมพที่ต่ำกว่า {PASS_PCT}% — ค่าปรับเทียบน่าจะผิด อย่าเพิ่งเชื่อ heatmap ของแมพนั้น")
    print(f"\nทุกแมพที่ตรวจได้ผ่านเกณฑ์ {PASS_PCT}%")


if __name__ == "__main__":
    main()
