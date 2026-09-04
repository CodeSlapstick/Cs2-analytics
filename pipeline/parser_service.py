#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parser_service.py — อ่านไฟล์ .dem หนึ่งไฟล์ ออกมาเป็น JSON ที่ normalize แล้ว

    python pipeline/parser_service.py                       # ทุกไฟล์ใน demos/ -> output/json/<ชื่อเดโม>.json
    python pipeline/parser_service.py demos/X.dem           # ไฟล์เดียว
    python pipeline/parser_service.py --limit 1 --force     # ลอง 1 ไฟล์ ไม่สนแคช

    หรือเรียกจากโค้ดอื่น:
        from pipeline.parser_service import parse_demo
        doc = parse_demo(Path("demos/X.dem"))               # dict พร้อม json.dumps

"normalized" แปลว่าอะไร
    ไม่ใช่ตารางแบน ๆ ที่ชื่อผู้เล่นซ้ำทุกแถวเหมือน all_kills.csv
    แต่แยกเป็น 4 ก้อนตามตารางใน backend/schema.sql แล้วอ้างถึงกันด้วยคีย์:
        match    1 ก้อน      ข้อมูลระดับแมตช์
        players  n แถว       steam_id -> ชื่อ (เก็บครั้งเดียว)
        rounds   n แถว       คีย์คือ round_num
        kills    n แถว       อ้าง rounds ด้วย round_num, อ้าง players ด้วย steam_id
    ETL loader (backend/) รับไฟล์นี้แล้ว INSERT ตามลำดับ players -> match -> rounds -> kills ได้เลย
    ชื่อฟิลด์ตั้งให้ตรงกับคอลัมน์ใน schema.sql ทุกตัว จะได้ไม่ต้อง map ชื่ออีกรอบ

หนึ่งเดโม = หนึ่งไฟล์ JSON
    เพราะ "แมตช์" คือหน่วยที่ ETL ใช้ตัดสินว่าโหลดแล้วหรือยัง (matches.demo_file UNIQUE)
    รันซ้ำจึงข้ามได้ทีละไฟล์ ไม่ต้องไล่ดูทีละแถว

ทำไมไม่ต่อยอดจาก all_kills.csv
    csv คือ "ผลลัพธ์รวม" ที่สร้างจากเดโมอีกที ถ้า ETL อ่านจาก csv จะเพิ่มเดโมใหม่ทีละไฟล์ไม่ได้
    ไฟล์นี้อ่านจาก .dem ตรง ๆ (1-2 วินาทีต่อไฟล์) เดโมใหม่มาก็ parse แค่ไฟล์นั้น
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
from awpy import Demo
from awpy.parsers.rounds import create_round_df

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))      # ให้รัน python pipeline/parser_service.py จากรากโปรเจกต์ได้
from pipeline.demoparser import EVENTS, PLAYER_PROPS   # noqa: E402  ชุด event/prop เดียวกับตัวสร้าง all_kills.csv

DEMO_DIR = ROOT / "demos"
OUT_DIR = ROOT / "output" / "json"

SCHEMA_VERSION = 1      # ขยับเมื่อโครง JSON เปลี่ยนแบบที่ ETL เดิมอ่านไม่ได้

# ชื่อไฟล์เดโมจาก HLTV มีแบบแผน "ทีมA-vs-ทีมB-แมพ.dem" (regex เดียวกับ backend/load_kills.py)
TEAMS_RE = re.compile(r"^(?P<a>.+?)-vs-(?P<b>.+?)-[^-]+\.dem$", re.IGNORECASE)

# คอลัมน์จาก awpy -> ชื่อคอลัมน์ในตาราง kills ของ schema.sql
KILL_COLUMNS = {
    "tick": "tick",
    "attacker_steamid": "attacker_id", "victim_steamid": "victim_id", "assister_steamid": "assister_id",
    "attacker_side": "attacker_side", "victim_side": "victim_side",
    "weapon": "weapon", "headshot": "headshot", "hitgroup": "hitgroup",
    "attackerblind": "attacker_blind", "thrusmoke": "thru_smoke", "noscope": "noscope", "assistedflash": "assisted_flash",
    "penetrated": "penetrated", "distance": "distance",
    "attacker_X": "attacker_x", "attacker_Y": "attacker_y", "attacker_Z": "attacker_z", "attacker_place": "attacker_place",
    "victim_X": "victim_x", "victim_Y": "victim_y", "victim_Z": "victim_z", "victim_place": "victim_place",
}

for _s in (sys.stdout, sys.stderr):     # ให้คอนโซล Windows พิมพ์ไทยได้
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def teams_from_filename(demo_file: str) -> tuple[str | None, str | None]:
    m = TEAMS_RE.match(demo_file)
    return (m["a"], m["b"]) if m else (None, None)


def _clean(df: pl.DataFrame) -> pl.DataFrame:
    """NaN ของ float -> null เพื่อให้ออกมาเป็น null ใน JSON (json ไม่มี NaN)"""
    return df.with_columns([pl.col(c).fill_nan(None) for c, t in df.schema.items() if t in (pl.Float32, pl.Float64)])


def parse_demo(path: Path) -> dict:
    """อ่านเดโมหนึ่งไฟล์ คืน dict โครง normalized พร้อม json.dumps"""
    dem = Demo(path)
    dem.events = dem.parse_events(EVENTS, player_props=PLAYER_PROPS)
    dem.rounds = create_round_df(dem.events)
    tickrate = int(dem.tickrate)

    # --- rounds: เอาจากตารางรอบโดยตรง จะได้ครบแม้รอบที่ไม่มีคิลเลย ---
    rounds = _clean(dem.rounds.select(
        pl.col("round_num").cast(pl.Int32),
        # start_tick = จังหวะ freeze time จบ ถ้าไม่มี event นั้นถอยไปใช้ round_start
        pl.coalesce("freeze_end", "start").cast(pl.Int32).alias("start_tick"),
        pl.coalesce("official_end", "end").cast(pl.Int32).alias("end_tick"),
        pl.col("bomb_plant").cast(pl.Int32).alias("bomb_plant_tick"),
        pl.col("winner").alias("winner_side"),
        pl.col("reason").alias("end_reason"),
    )).sort("round_num")

    # --- kills: เปลี่ยนชื่อคอลัมน์ให้ตรง schema ตัดคอลัมน์ที่ DB ไม่เก็บ ---
    kills = _clean(
        dem.kills.select(["round_num", *KILL_COLUMNS])
                 .rename(KILL_COLUMNS)
                 .with_columns(
                     pl.col("round_num").cast(pl.Int32),
                     pl.col("tick").cast(pl.Int32),
                     pl.col("penetrated").cast(pl.Int32),
                     pl.col(["attacker_id", "victim_id", "assister_id"]).cast(pl.Int64),
                     pl.col(["headshot", "attacker_blind", "thru_smoke", "noscope", "assisted_flash"]).cast(pl.Boolean),
                 )
                 .sort(["round_num", "tick"])
    )

    # --- players: ทุก steam_id ที่โผล่ ชื่อล่าสุดที่เห็นชนะ (เหมือน load_kills.py) ---
    players = (
        pl.concat([
            dem.kills.select(pl.col("attacker_steamid").alias("steam_id"), pl.col("attacker_name").alias("name")),
            dem.kills.select(pl.col("victim_steamid").alias("steam_id"), pl.col("victim_name").alias("name")),
            dem.kills.select(pl.col("assister_steamid").alias("steam_id"), pl.col("assister_name").alias("name")),
        ])
        .drop_nulls("steam_id")
        .with_columns(pl.col("steam_id").cast(pl.Int64))
        .unique(subset="steam_id", keep="last", maintain_order=True)
        .sort("steam_id")
    )

    team_a, team_b = teams_from_filename(path.name)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "match": {
            "demo_file": path.name,
            "map_name": dem.header.get("map_name", "unknown"),
            "tickrate": tickrate,
            "team_a": team_a,
            "team_b": team_b,
        },
        "counts": {"players": len(players), "rounds": len(rounds), "kills": len(kills)},
        "players": players.to_dicts(),
        "rounds": rounds.to_dicts(),
        "kills": kills.to_dicts(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="แปลง .dem เป็น JSON แบบ normalized ไฟล์ละแมตช์")
    ap.add_argument("demos", nargs="*", type=Path, help="ไฟล์ .dem (ไม่ใส่ = ทุกไฟล์ใน demos/)")
    ap.add_argument("--out", type=Path, default=OUT_DIR, help=f"โฟลเดอร์ผลลัพธ์ (ค่าตั้งต้น {OUT_DIR.relative_to(ROOT)})")
    ap.add_argument("--limit", type=int, help="อ่านแค่กี่ไฟล์ (ไว้ทดสอบ)")
    ap.add_argument("--force", action="store_true", help="เขียนทับ JSON ที่มีอยู่แล้ว")
    args = ap.parse_args()

    demos = args.demos or sorted(DEMO_DIR.glob("*.dem"))
    demos = demos[: args.limit]
    if not demos:
        sys.exit(f"ไม่เจอไฟล์ .dem ใน {DEMO_DIR}")

    args.out.mkdir(parents=True, exist_ok=True)
    totals = {"players": 0, "rounds": 0, "kills": 0}
    done = failed = skipped = 0
    for i, path in enumerate(demos, 1):
        target = args.out / f"{path.stem}.json"
        if target.exists() and not args.force:        # JSON เดิมคือแคช — เดโมไฟล์เดิมให้ผลเดิมเสมอ
            print(f"[{i}/{len(demos)}] {path.name} — มีแล้ว ข้าม")
            skipped += 1
            continue

        t0 = time.time()
        try:
            doc = parse_demo(path)
        except Exception as e:                        # เดโมเสียหนึ่งไฟล์ ไม่ควรทำให้ทั้ง batch ล่ม
            print(f"[{i}/{len(demos)}] {path.name} — พัง: {e}")
            failed += 1
            continue

        # เขียนลงไฟล์ชั่วคราวก่อนแล้วค่อยเปลี่ยนชื่อ — ถ้าพังกลางทางจะไม่เหลือ JSON ครึ่งไฟล์ให้ ETL อ่านผิด
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp.replace(target)

        for k in totals:
            totals[k] += doc["counts"][k]
        done += 1
        c = doc["counts"]
        print(f"[{i}/{len(demos)}] {path.name} — {c['rounds']} รอบ {c['kills']} คิล "
              f"{target.stat().st_size / 1024:.0f} KB ({time.time() - t0:.1f}s)")

    print(f"\nเสร็จ {done} · ข้าม {skipped} · พัง {failed}  ->  {args.out}")
    if done:
        print(f"รวมที่ parse รอบนี้: {totals['rounds']:,} รอบ {totals['kills']:,} คิล {totals['players']:,} นักแข่ง")


if __name__ == "__main__":
    main()
