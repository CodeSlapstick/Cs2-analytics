#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
อ่านไฟล์ .dem ทุกไฟล์ใน demos/ ด้วย awpy แล้วรวม kills เป็น csv ตารางเดียว

    python research/demoparser.py            # อ่านทั้งหมดที่ยังไม่เคยอ่าน
    python research/demoparser.py --limit 3  # ลองแค่ 3 ไฟล์แรก
    python research/demoparser.py --force    # อ่านใหม่หมด ไม่สนแคช

ทำไมไม่เรียก dem.parse() ตรง ๆ
    dem.parse() อ่าน tick ของผู้เล่นทุกคนทุกเฟรมด้วย ซึ่งเป็นงานหนักที่สุด
    และกินแรมหลาย GB ต่อไฟล์ แต่เราต้องการแค่ kills จึงอ่านเฉพาะ event ที่ dem.kills ใช้จริง:
    player_death เอาไว้ทำตาราง กับ round_* เอาไว้ปะเลขรอบให้แต่ละคิล
    ผลลัพธ์เหมือนกันทุกคอลัมน์ แต่เร็วกว่าหลายเท่า

แคชรายไฟล์
    เดโม 50 ไฟล์รวมกัน 16 GB ใช้เวลารันเป็นชั่วโมง ถ้าพังกลางทางแล้วต้องเริ่มใหม่หมดคือฝันร้าย
    จึงเซฟผลรายไฟล์ไว้ที่ output/kills_cache/ ก่อน แล้วค่อยเอามาต่อกันตอนท้าย
    รันซ้ำจะข้ามไฟล์ที่มีแคชแล้วทันที
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
CACHE_DIR = ROOT / "output" / "kills_cache"
OUT_CSV = ROOT / "data" / "all_kills.csv"

sys.path.insert(0, str(ROOT))
from backend.features.teams import assign_teams  # noqa: E402  ผูกทีมด้วยกฎชุดเดียวกับระบบหลัก

# event ที่ dem.kills ต้องใช้ — ตัดที่เหลือออกให้หมด
EVENTS = [
    "player_death",           # ตัวคิลเอง
    "round_start",            # สี่อันล่างนี้ create_round_df ใช้หาขอบเขตแต่ละรอบ
    "round_freeze_end",
    "round_end",
    "round_officially_ended",
    "bomb_planted",           # ไม่จำเป็นต่อ kills แต่ทำให้คอลัมน์ bomb_plant ในตารางรอบไม่ว่าง
]

# props ชุดเดียวกับที่ awpy ใส่ให้เป็น default
#   awpy จะเปลี่ยนชื่อให้เองตอนอ่าน: team_name -> side, last_place_name -> place
#   จึงได้คอลัมน์ attacker_side / victim_side / victim_place / victim_X ฯลฯ ออกมา
PLAYER_PROPS = ["last_place_name", "X", "Y", "Z", "health", "team_name",
                "team_clan_name"]   # ชื่อทีม (clan tag) — ใช้ผูกคนกับทีมข้ามครึ่ง (Round Review)

for _s in (sys.stdout, sys.stderr):     # ให้คอนโซล Windows พิมพ์ไทยได้
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def parse_one(path: Path) -> pl.DataFrame:
    """อ่านเดโมหนึ่งไฟล์ คืนตาราง kills ที่ติดบริบทของรอบมาด้วย"""
    dem = Demo(path)
    dem.events = dem.parse_events(EVENTS, player_props=PLAYER_PROPS)
    dem.rounds = create_round_df(dem.events)

    # แปะข้อมูลระดับรอบเข้าไปในทุกแถวคิล
    #   ทำที่นี่เพราะขอบเขตรอบมีอยู่แล้วตอน parse ถ้าไม่เก็บตอนนี้ ปลายทางจะกู้คืนไม่ได้เลย
    #   สามคอลัมน์นี้ทำให้คิดได้ว่า "การดวลนี้เกิดวินาทีที่เท่าไรของรอบ และตอนนั้นระเบิดลงหรือยัง"
    #   ซึ่งเป็นบริบทที่รู้ได้ก่อนการดวลจะจบ จึงเอาไปเป็นฟีเจอร์ของโมเดลได้โดยไม่โกง
    ctx = dem.rounds.select(
        pl.col("round_num"),
        pl.coalesce(pl.col("freeze_end"), pl.col("start")).alias("round_start_tick"),
        pl.col("bomb_plant").alias("bomb_plant_tick"),
        # ใครชนะรอบนี้ — ไม่ได้ใช้กับโมเดลทำนายการดวล แต่เป็น "เฉลย" ของคำถามระดับรอบ
        pl.col("winner").alias("round_winner"),
        pl.col("reason").alias("round_end_reason"),
    )

    kills = dem.kills.join(ctx, on="round_num", how="left").with_columns(
        # สองคอลัมน์นี้คือเหตุผลที่ต้องมีสคริปต์นี้ ไม่ใช่แค่ต่อ csv เอาเอง
        # ปลายทาง (grid_ml.py) ต้องแยกให้ออกว่าแถวไหนมาจากแมตช์ไหน ถึงจะแบ่ง train/test ได้ถูก
        pl.lit(path.name).alias("demo_file"),
        pl.lit(dem.header.get("map_name", "unknown")).alias("map_name"),
        pl.lit(dem.tickrate).alias("tickrate"),
    )
    return add_round_review_columns(kills)


def add_round_review_columns(kills: pl.DataFrame) -> pl.DataFrame:
    """คอลัมน์ที่หน้า Round Review ต้องใช้ (STEP 0)

    attacker_team_clan / victim_team_clan / assister_team_clan
        ชื่อทีมที่คงที่ทั้งแมตช์ — ผูกด้วย backend/features/teams.assign_teams
        (คนฝั่งเดียวกันในรอบเดียวกัน = ทีมเดียวกัน, ชื่อ = clan tag ที่พบบ่อยสุด, ไม่มี clan -> Team A/B ตาม side ครึ่งแรก)
    round_winner_side / attacker_blind
        ชื่อตาม brief — คอลัมน์เดิม round_winner / attackerblind ยังอยู่ เพราะ research/*.py อ้างชื่อเดิมอยู่
    """
    rows = []
    for who in ("attacker", "victim"):
        part = kills.select(
            pl.col(f"{who}_steamid").cast(pl.Int64).alias("steam_id"),
            pl.col("round_num"),
            pl.col(f"{who}_side").alias("side"),
            pl.col(f"{who}_team_clan_name").alias("clan") if f"{who}_team_clan_name" in kills.columns else pl.lit(None).alias("clan"),
        ).drop_nulls("steam_id")
        rows.extend(part.to_dicts())
    team_of = assign_teams(rows)

    def team_col(who: str) -> pl.Expr:
        return (pl.col(f"{who}_steamid").cast(pl.Int64)
                .replace_strict(team_of, default=None, return_dtype=pl.Utf8).alias(f"{who}_team_clan"))

    raw_clan = [c for c in kills.columns if c.endswith("_team_clan_name")]
    return kills.with_columns(
        team_col("attacker"), team_col("victim"), team_col("assister"),
        pl.col("round_winner").alias("round_winner_side"),
        pl.col("attackerblind").alias("attacker_blind"),
    ).drop(raw_clan)


def main() -> None:
    ap = argparse.ArgumentParser(description="รวม kills จากเดโมทั้งโฟลเดอร์เป็น csv เดียว")
    ap.add_argument("--limit", type=int, help="อ่านแค่กี่ไฟล์ (ไว้ทดสอบ)")
    ap.add_argument("--force", action="store_true", help="อ่านใหม่ทุกไฟล์ ไม่ใช้แคช")
    ap.add_argument("--out", type=Path, default=OUT_CSV, help=f"ไฟล์ผลลัพธ์ (ค่าตั้งต้น {OUT_CSV.name})")
    args = ap.parse_args()

    demos = sorted(DEMO_DIR.glob("*.dem"))      # .crdownload หรือไฟล์ดาวน์โหลดค้างจะไม่ติดมา
    if not demos:
        sys.exit(f"ไม่พบไฟล์ .dem ใน {DEMO_DIR}")
    if args.limit:
        demos = demos[: args.limit]

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    frames, failed = [], []

    for i, path in enumerate(demos, 1):
        cache = CACHE_DIR / f"{path.stem}.parquet"
        size_mb = path.stat().st_size / 1e6

        if cache.exists() and not args.force:
            frames.append(pl.read_parquet(cache))
            print(f"[{i}/{len(demos)}] ข้าม (มีแคชแล้ว) {path.name}", flush=True)
            continue

        print(f"[{i}/{len(demos)}] อ่าน {path.name} ({size_mb:.0f} MB) ...", end=" ", flush=True)
        t0 = time.perf_counter()
        try:
            kills = parse_one(path)
        except Exception as e:                  # เดโมเสีย/ดาวน์โหลดไม่ครบ ให้ข้ามไป อย่าให้ล้มทั้งรัน
            print(f"พัง: {type(e).__name__}: {e}", flush=True)
            failed.append((path.name, f"{type(e).__name__}: {e}"))
            continue
        kills.write_parquet(cache)
        frames.append(kills)
        print(f"{len(kills):,} คิล ใน {time.perf_counter() - t0:.0f} วินาที", flush=True)

    if not frames:
        sys.exit("ไม่มีไฟล์ไหนอ่านสำเร็จเลย")

    # how="diagonal_relaxed" กันกรณีเดโมบางไฟล์มีคอลัมน์ไม่ครบ (คนละเวอร์ชันเกม) ให้เติม null แทนที่จะ error
    final = pl.concat(frames, how="diagonal_relaxed")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    final.write_csv(args.out)

    print(f"\n=== เสร็จ: {final.n_unique('demo_file')} แมตช์ | {len(final):,} คิล ===")
    print(f"แมพ: {dict(final['map_name'].value_counts().iter_rows())}")
    print(f"เซฟที่ {args.out}")
    if failed:
        print(f"\nอ่านไม่สำเร็จ {len(failed)} ไฟล์:")
        for name, err in failed:
            print(f"  {name} — {err}")


if __name__ == "__main__":
    main()
