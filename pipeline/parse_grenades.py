#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_grenades.py — ดึง "การขว้างระเบิด" ทุกลูกออกจากเดโม

    python pipeline/parse_grenades.py

ทำไมต้องมีไฟล์นี้
    ตาราง kills บอกได้แค่ "ผล" ของ utility (attackerblind, thrusmoke)
    แต่ไม่รู้ว่าใครขว้างอะไรกี่ลูกตอนไหน — ซึ่งเป็นสิ่งที่ feature "utility" ต้องการ
    event weapon_fire ในเดโมมีครบ: ใครขว้าง ทีมไหน ระเบิดชนิดไหน tick ไหน

ผลลัพธ์  data/grenades.parquet   หนึ่งแถว = หนึ่งลูกที่ขว้าง
"""
import argparse
import sys
import time
from pathlib import Path

import polars as pl
from awpy import Demo
from awpy.parsers.rounds import create_round_df

ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT / "demos"
CACHE_DIR = ROOT / "output" / "grenades_cache"
OUT = ROOT / "data" / "grenades.parquet"

ROUND_EVENTS = ["round_start", "round_freeze_end", "round_end", "round_officially_ended", "bomb_planted"]

# ชื่ออาวุธในเดโม -> ชื่อสั้นที่เราใช้ (molotov กับ incendiary คือของเดียวกันคนละฝั่ง)
GRENADE_TYPES = {
    "flashbang": "flash", "smokegrenade": "smoke", "hegrenade": "he",
    "molotov": "molotov", "incgrenade": "molotov", "decoy": "decoy",
}

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def parse_one(path: Path) -> pl.DataFrame:
    dem = Demo(path)
    dem.events = dem.parse_events(ROUND_EVENTS)
    rounds = create_round_df(dem.events)
    tickrate = int(dem.tickrate)

    # ใช้ weapon_fire แทน grenade_thrown — event grenade_thrown ไม่มีในเดโม 14 จาก 50 ไฟล์
    # (parser คืน list ว่าง) แต่ weapon_fire มีทุกไฟล์ และการขว้างระเบิดก็นับเป็น "ยิง" หนึ่งครั้ง
    # ชื่ออาวุธมาแบบ weapon_smokegrenade -> ตัด weapon_ ออกให้เหลือ smokegrenade
    fired = dem.parser.parse_event("weapon_fire", player=["team_name"])
    if not hasattr(fired, "columns"):          # ไม่มี event นี้เลย -> parser คืน list ว่าง
        return pl.DataFrame()
    thrown = (
        pl.from_pandas(fired)
          .with_columns(pl.col("weapon").str.replace("^weapon_", ""))
          .filter(pl.col("weapon").is_in(list(GRENADE_TYPES)))
    )
    if thrown.is_empty():
        return pl.DataFrame()

    # ปะเลขรอบ: ลูกที่ขว้างที่ tick t อยู่ในรอบที่ start <= t < official_end
    bounds = rounds.select(
        "round_num",
        pl.coalesce("freeze_end", "start").alias("r_start"),
        pl.coalesce("official_end", "end").alias("r_end"),
    )
    thrown = (
        thrown.join(bounds, how="cross")
              .filter((pl.col("tick") >= pl.col("r_start")) & (pl.col("tick") < pl.col("r_end")))
    )

    return thrown.select(
        pl.lit(path.name).alias("demo_file"),
        "round_num",
        "tick",
        ((pl.col("tick") - pl.col("r_start")) // tickrate).alias("second_in_round"),
        pl.col("user_steamid").cast(pl.Int64).alias("steamid"),
        pl.col("user_name").alias("name"),
        # ในเดโมเรียก TERRORIST / CT — ทำให้ตรงกับ ct / t ใน all_kills.csv
        pl.when(pl.col("user_team_name") == "CT").then(pl.lit("ct")).otherwise(pl.lit("t")).alias("side"),
        pl.col("weapon").replace_strict(GRENADE_TYPES, default="other").alias("type"),
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="ดึงการขว้างระเบิดจากเดโมทั้งโฟลเดอร์")
    ap.add_argument("--limit", type=int, help="อ่านแค่กี่ไฟล์ (ไว้ทดสอบ)")
    ap.add_argument("--force", action="store_true", help="อ่านใหม่ทุกไฟล์ ไม่ใช้แคช")
    args = ap.parse_args()

    demos = sorted(DEMO_DIR.glob("*.dem"))[: args.limit]
    if not demos:
        sys.exit(f"ไม่เจอไฟล์ .dem ใน {DEMO_DIR}")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for i, path in enumerate(demos, 1):
        # แคชรายไฟล์ + จับ error รายไฟล์ — เดโมเสียหนึ่งไฟล์ไม่ควรทำให้ทั้ง batch ล่ม
        cache = CACHE_DIR / f"{path.stem}.parquet"
        if cache.exists() and not args.force:
            print(f"[{i}/{len(demos)}] {path.name} — ใช้แคช")
            frames.append(pl.read_parquet(cache))
            continue

        t0 = time.time()
        try:
            df = parse_one(path)
        except Exception as e:
            print(f"[{i}/{len(demos)}] {path.name} — พัง: {e}")
            continue

        df.write_parquet(cache)
        frames.append(df)
        print(f"[{i}/{len(demos)}] {path.name} — {len(df):,} ลูก ({time.time() - t0:.0f}s)")

    frames = [f for f in frames if not f.is_empty()]
    if not frames:
        sys.exit("ไม่ได้ข้อมูลเลย")

    out = pl.concat(frames)
    OUT.parent.mkdir(exist_ok=True)
    out.write_parquet(OUT)
    print(f"\n{len(out):,} ลูก จาก {out['demo_file'].n_unique()} แมตช์")
    print(out["type"].value_counts(sort=True))
    print(f"เซฟแล้ว: {OUT}")


if __name__ == "__main__":
    main()
