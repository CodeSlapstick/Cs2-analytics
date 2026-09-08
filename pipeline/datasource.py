# -*- coding: utf-8 -*-
"""
pipeline/datasource.py — แหล่งข้อมูลคิลของโมเดล เลือกได้ว่าอ่านจาก PostgreSQL หรือ csv

    from pipeline.datasource import load_kills
    df = load_kills("de_mirage")                 # auto: ลอง DB ก่อน ต่อไม่ได้ค่อยถอยไป csv
    df = load_kills("de_mirage", source="db")    # บังคับ DB  (ตอนเทรนใหม่จากหน้าเว็บ)
    df = load_kills("de_mirage", source="csv")   # บังคับ csv (Docker ที่รันโดยไม่มี DB ตาม README)

    จากคอมมานด์ไลน์ของสคริปต์โมเดล:  python pipeline/grid_ml.py --source=db

ทำไมต้องมีไฟล์นี้
    เดิม grid_ml.py และ round_win.py อ่าน data/all_kills.csv ตรง ๆ ซึ่งเป็นชุดตายตัว 50 เดโม
    เดโมที่อัปโหลดผ่านหน้าเว็บลง PostgreSQL จึงไม่เคยเดินทางไปถึงโมเดลเลย
    ไฟล์นี้คืนตารางที่ "ชื่อคอลัมน์เหมือน csv ทุกตัว" โมเดลจึงไม่ต้องรู้ว่าแหล่งข้อมูลเปลี่ยน

    ชื่อคอลัมน์ที่ต้องรักษาไว้ (โมเดลอ้างถึงตรง ๆ — เปลี่ยนแล้วโมเดลพัง):
        demo_file  map_name  tickrate
        round_num  round_start_tick  bomb_plant_tick  round_winner
        tick  attacker_side  victim_side  victim_X  victim_Y  victim_place

    df.attrs["source"] บอกว่าข้อมูลมาจากไหน ไว้ให้สคริปต์พิมพ์และเขียนลงไฟล์ผลลัพธ์
    หน้าเว็บจะได้บอกได้ว่าโมเดลเทรนจากอะไร
"""
import asyncio
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
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
    sys.path.insert(0, str(ROOT))                 # ให้ import backend.db ได้แม้รันจาก pipeline/
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
        raise FileNotFoundError(f"ไม่พบ {CSV} — รัน python pipeline/demoparser.py ก่อน")
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
