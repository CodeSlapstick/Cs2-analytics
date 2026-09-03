#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
โหลด data/all_kills.csv เข้า PostgreSQL

    python backend/load_kills.py              # โหลดเฉพาะแมตช์ที่ยังไม่มีใน DB
    python backend/load_kills.py --force      # ลบของเดิมแล้วโหลดใหม่ทั้งหมด
    python backend/load_kills.py --csv other.csv

ทำงานเป็น 4 ขั้น ตามลำดับที่ foreign key บังคับ
    1. players  — รวมทุก steamid ที่โผล่ในคอลัมน์ attacker / victim / assister
    2. matches  — หนึ่งแถวต่อ demo_file
    3. rounds   — หนึ่งแถวต่อ (demo_file, round_num)
    4. kills    — ทุกแถวของ csv ยัดทีเดียวด้วย COPY (เร็วกว่า INSERT ทีละแถวหลายสิบเท่า)

รันซ้ำได้ — แมตช์ที่มีอยู่แล้วจะถูกข้าม (ดูจาก demo_file) จึงใช้ต่อจาก
pipeline/demoparser.py ได้เลยตอนเพิ่มเดโมใหม่: parse -> csv -> รันไฟล์นี้
"""
import argparse
import asyncio
import re
import sys
from pathlib import Path

import pandas as pd

# ให้รันจากรากโปรเจกต์ได้ด้วย python backend/load_kills.py โดยไม่ต้องตั้ง PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.db import ROOT, apply_schema, connect, redacted_url  # noqa: E402

for _s in (sys.stdout, sys.stderr):     # ให้คอนโซล Windows พิมพ์ไทยได้
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

DEFAULT_CSV = ROOT / "data" / "all_kills.csv"

# ชื่อไฟล์เดโมจาก HLTV มีแบบแผน "ทีมA-vs-ทีมB-แมพ.dem" แกะชื่อทีมออกมาเก็บไว้ค้นหา
TEAMS_RE = re.compile(r"^(?P<a>.+?)-vs-(?P<b>.+?)-[^-]+\.dem$", re.IGNORECASE)


def teams_from_filename(demo_file: str) -> tuple[str | None, str | None]:
    m = TEAMS_RE.match(demo_file)
    return (m["a"], m["b"]) if m else (None, None)


def none_if_nan(v):
    """pandas ใช้ NaN แทนช่องว่าง แต่ PostgreSQL ต้องการ NULL"""
    return None if pd.isna(v) else v


def to_int(v):
    v = none_if_nan(v)
    return None if v is None else int(v)


def to_float(v):
    v = none_if_nan(v)
    return None if v is None else float(v)


async def main() -> None:
    ap = argparse.ArgumentParser(description="โหลด csv ชุดคิลเข้า PostgreSQL")
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--force", action="store_true", help="ลบแมตช์ที่มีอยู่แล้วโหลดใหม่")
    args = ap.parse_args()

    if not args.csv.exists():
        sys.exit(f"ไม่พบ {args.csv} — รัน python pipeline/demoparser.py ก่อน")

    # SteamID64 มี 17 หลัก เกินที่ float64 เก็บได้แม่น (ราว 15-16 หลัก) ถ้าปล่อยให้ pandas
    # เดาชนิดเอง คอลัมน์ที่มีช่องว่าง (attacker/assister) จะกลายเป็น float แล้วเลขท้ายเพี้ยน
    # -> foreign key ไม่ตรงกับ players จึงบังคับเป็น Int64 (int ที่ยอมให้มีช่องว่างได้) ตั้งแต่ตอนอ่าน
    steamid_cols = {c: "Int64" for c in ("attacker_steamid", "victim_steamid", "assister_steamid")}
    df = pd.read_csv(args.csv, dtype=steamid_cols)
    need = {"demo_file", "round_num", "round_winner", "victim_steamid", "map_name", "tickrate"}
    if missing := need - set(df.columns):
        sys.exit(f"csv ขาดคอลัมน์ {sorted(missing)} — รัน python pipeline/demoparser.py --force ให้ได้ csv รุ่นใหม่")
    print(f"อ่าน {args.csv.name}: {len(df):,} คิล จาก {df['demo_file'].nunique()} เดโม")

    print(f"ต่อ {redacted_url()}")
    conn = await connect()
    try:
        await apply_schema(conn)

        # ข้ามแมตช์ที่มีแล้ว (หรือลบทิ้งถ้า --force) — ON DELETE CASCADE จะพา rounds/kills ไปด้วย
        existing = {r["demo_file"] for r in await conn.fetch("SELECT demo_file FROM matches")}
        if args.force and existing:
            await conn.execute("DELETE FROM matches WHERE demo_file = ANY($1)", list(existing))
            print(f"ลบ {len(existing)} แมตช์เดิมทิ้ง (--force)")
            existing = set()
        df = df[~df["demo_file"].isin(existing)]
        if df.empty:
            print("ไม่มีแมตช์ใหม่ให้โหลด — ใช้ --force ถ้าต้องการโหลดซ้ำ")
            return

        async with conn.transaction():      # ทั้ง 4 ขั้นสำเร็จหมดหรือไม่เกิดเลย ไม่ทิ้งของครึ่ง ๆ กลาง ๆ ไว้
            # 1) players — ชื่อล่าสุดที่เห็นชนะ
            people = pd.concat([
                df[["attacker_steamid", "attacker_name"]].set_axis(["steam_id", "name"], axis=1),
                df[["victim_steamid", "victim_name"]].set_axis(["steam_id", "name"], axis=1),
                df[["assister_steamid", "assister_name"]].set_axis(["steam_id", "name"], axis=1),
            ]).dropna(subset=["steam_id"]).drop_duplicates("steam_id", keep="last")
            await conn.executemany(
                "INSERT INTO players (steam_id, name) VALUES ($1, $2) "
                "ON CONFLICT (steam_id) DO UPDATE SET name = EXCLUDED.name",
                [(int(s), str(n)) for s, n in zip(people["steam_id"], people["name"])],
            )

            # 2) matches
            match_ids: dict[str, int] = {}
            for demo_file, g in df.groupby("demo_file", sort=True):
                team_a, team_b = teams_from_filename(demo_file)
                match_ids[demo_file] = await conn.fetchval(
                    "INSERT INTO matches (demo_file, map_name, tickrate, team_a, team_b) "
                    "VALUES ($1, $2, $3, $4, $5) RETURNING id",
                    demo_file, str(g["map_name"].iloc[0]), int(g["tickrate"].iloc[0]), team_a, team_b,
                )

            # 3) rounds — ค่าประจำรอบเหมือนกันทุกแถวในรอบ หยิบแถวแรกพอ
            round_cols = ["demo_file", "round_num", "round_start_tick", "bomb_plant_tick", "round_winner", "round_end_reason"]
            rounds = df[round_cols].drop_duplicates(["demo_file", "round_num"])
            round_ids: dict[tuple[str, int], int] = {}
            for r in rounds.itertuples(index=False):
                round_ids[(r.demo_file, int(r.round_num))] = await conn.fetchval(
                    "INSERT INTO rounds (match_id, round_num, start_tick, bomb_plant_tick, winner_side, end_reason) "
                    "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
                    match_ids[r.demo_file], int(r.round_num), to_int(r.round_start_tick),
                    to_int(r.bomb_plant_tick), str(r.round_winner), none_if_nan(r.round_end_reason),
                )

            # 4) kills — COPY ทีเดียวทั้งก้อน
            records = []
            for k in df.itertuples(index=False):
                records.append((
                    round_ids[(k.demo_file, int(k.round_num))],
                    int(k.tick),
                    to_int(k.attacker_steamid), int(k.victim_steamid), to_int(k.assister_steamid),
                    none_if_nan(k.attacker_side), str(k.victim_side),
                    str(k.weapon), bool(k.headshot), none_if_nan(k.hitgroup),
                    bool(k.attackerblind), bool(k.thrusmoke), bool(k.noscope), bool(k.assistedflash),
                    int(k.penetrated), to_float(k.distance),
                    to_float(k.attacker_X), to_float(k.attacker_Y), to_float(k.attacker_Z), none_if_nan(k.attacker_place),
                    to_float(k.victim_X), to_float(k.victim_Y), to_float(k.victim_Z), none_if_nan(k.victim_place),
                ))
            await conn.copy_records_to_table(
                "kills",
                records=records,
                columns=[
                    "round_id", "tick",
                    "attacker_id", "victim_id", "assister_id",
                    "attacker_side", "victim_side",
                    "weapon", "headshot", "hitgroup",
                    "attacker_blind", "thru_smoke", "noscope", "assisted_flash",
                    "penetrated", "distance",
                    "attacker_x", "attacker_y", "attacker_z", "attacker_place",
                    "victim_x", "victim_y", "victim_z", "victim_place",
                ],
            )

        print(f"โหลดแล้ว: {len(match_ids)} แมตช์, {len(round_ids):,} รอบ, {len(records):,} คิล, {len(people):,} นักแข่ง")
        total = await conn.fetchrow("SELECT (SELECT COUNT(*) FROM matches) AS m, (SELECT COUNT(*) FROM kills) AS k")
        print(f"ใน DB ตอนนี้: {total['m']} แมตช์, {total['k']:,} คิล")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
