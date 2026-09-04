#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
downsample_ticks.py — ดึงตำแหน่งผู้เล่นจากเดโม แต่เก็บแค่วินาทีละครั้ง (1 Hz)

    python pipeline/downsample_ticks.py              # อ่านทุกไฟล์ที่ยังไม่เคยอ่าน
    python pipeline/downsample_ticks.py --limit 1    # ลองไฟล์เดียวก่อน
    python pipeline/downsample_ticks.py --hz 2       # เก็บ 2 ครั้งต่อวินาทีแทน

ทำไมต้อง downsample
    เดโม CS2 บันทึกที่ 64 หรือ 128 tick ต่อวินาที ถ้าเก็บทุก tick จะได้
        128 tick/วิ x 10 คน x 2,100 วิ  =  2,688,000 แถว ต่อ "หนึ่งแมตช์"
    50 แมตช์ก็ 134 ล้านแถว — เปิดด้วย pandas ไม่ไหว และ 99% เป็นข้อมูลซ้ำ
    เพราะคนวิ่งเร็วสุดในเกม ~250 หน่วย/วินาที ระหว่าง tick ติดกันขยับแค่ ~2 หน่วย

    เก็บวินาทีละครั้งเหลือ 10 คน x 2,100 วิ = 21,000 แถวต่อแมตช์ (เล็กลง 128 เท่า)
    ยังพอบอกได้ว่าใครไปทางไหน โรเทตตอนไหน ยืนโซนไหนนานแค่ไหน
    ไม่พอสำหรับวิเคราะห์การเล็ง/การดวลระดับเสี้ยววินาที — อันนั้นใช้ตาราง kills แทน

หัวใจของไฟล์นี้
    ไม่ได้ "อ่านทุก tick แล้วค่อยทิ้ง" — แบบนั้นเปลืองแรมเท่าเดิม
    แต่คำนวณล่วงหน้าว่าอยากได้ tick ไหนบ้าง แล้วส่งรายการนั้นให้ parser
    ผ่าน parse_ticks(ticks=[...]) ตัว parser (เขียนด้วย Rust) จะข้าม tick ที่ไม่ขอให้เลย
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
CACHE_DIR = ROOT / "output" / "ticks_cache"
OUT = ROOT / "data" / "positions_1hz.parquet"

# event ที่ต้องอ่านก่อน เพื่อรู้ว่าแต่ละรอบเริ่ม-จบที่ tick ไหน
# อ่านแค่ event พวกนี้เบามาก เพราะไม่แตะข้อมูลตำแหน่งเลย
ROUND_EVENTS = ["round_start", "round_freeze_end", "round_end", "round_officially_ended", "bomb_planted"]

# prop ที่อยากได้ต่อผู้เล่นต่อ tick
#   is_alive สำคัญ — คนตายแล้วยังมีพิกัดค้างอยู่ตรงที่ตาย ถ้าไม่กรองออก
#   จะกลายเป็น "ยืนนิ่งตรงนั้นทั้งรอบ" ทำให้ heatmap เพี้ยน
TICK_PROPS = [
    # ตำแหน่ง — เหตุผลหลักที่ทำไฟล์นี้
    "X", "Y", "Z", "last_place_name", "is_alive", "health", "team_name",
    # เศรษฐกิจ — ยังไม่ได้ใช้ในไฟล์นี้ แต่เก็บไว้เลยเพราะงาน buy type (feature engineering)
    # กับ ML enemy buy ต้องใช้ ถ้าไม่เก็บตอนนี้ต้องกลับมา parse เดโมใหม่ทั้งกองอีกรอบ
    "balance",                   # เงินในกระเป๋า ณ ตอนนั้น
    "current_equip_value",       # มูลค่าของที่ถืออยู่
    "round_start_equip_value",   # มูลค่าตอนรอบเริ่ม -> ใช้แยก eco / force / full buy
    "cash_spent_this_round",
    "armor_value", "has_helmet", "has_defuser",
]

for _s in (sys.stdout, sys.stderr):     # ให้คอนโซล Windows พิมพ์ไทยได้
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def wanted_ticks(rounds: pl.DataFrame, tickrate: int, hz: float) -> dict[int, tuple[int, int]]:
    """คำนวณว่าอยากได้ tick ไหนบ้าง คืน {tick: (เลขรอบ, วินาทีที่เท่าไรของรอบ)}

    เก็บเฉพาะช่วง "ในรอบจริง" คือตั้งแต่ freeze time จบ ถึงรอบจบ
    ช่วง freeze time กับช่วงคั่นระหว่างรอบไม่เอา เพราะทุกคนยืนนิ่งอยู่ที่เกิด
    ไม่มีข้อมูลอะไร แต่กินพื้นที่เท่ากัน
    """
    step = max(1, round(tickrate / hz))      # 128 tick/วิ หาร 1 Hz = เอาทุก ๆ 128 tick
    out: dict[int, tuple[int, int]] = {}
    for r in rounds.iter_rows(named=True):
        start = r["freeze_end"] or r["start"]
        end = r["official_end"] or r["end"]
        if start is None or end is None:
            continue
        for t in range(int(start), int(end), step):
            out[t] = (r["round_num"], (t - int(start)) // tickrate)
    return out


def parse_one(path: Path, hz: float) -> pl.DataFrame:
    """อ่านเดโมหนึ่งไฟล์ คืนตำแหน่งผู้เล่นที่ downsample แล้ว"""
    dem = Demo(path)

    # รอบแรก: อ่านแค่ event ของรอบ เพื่อรู้ขอบเขตเวลา — ยังไม่แตะตำแหน่ง
    dem.events = dem.parse_events(ROUND_EVENTS)
    rounds = create_round_df(dem.events)
    tickrate = int(dem.tickrate)

    want = wanted_ticks(rounds, tickrate, hz)
    if not want:
        return pl.DataFrame()

    # รอบสอง: ขอเฉพาะ tick ที่คำนวณไว้
    # ใช้ dem.parser ตรง ๆ เพราะ awpy ตัวห่อไม่เปิดให้ส่ง ticks= เข้าไป
    raw = dem.parser.parse_ticks(wanted_props=TICK_PROPS, ticks=sorted(want))
    df = pl.from_pandas(raw)

    # ปะเลขรอบกับวินาทีของรอบกลับเข้าไป (มาจาก dict ที่คำนวณไว้ก่อนแล้ว)
    lookup = pl.DataFrame({
        "tick": list(want.keys()),
        "round_num": [v[0] for v in want.values()],
        "second_in_round": [v[1] for v in want.values()],
    })

    return (
        df.join(lookup, on="tick", how="inner")
          .filter(pl.col("is_alive"))            # ตัดคนตายทิ้ง (ดูคอมเมนต์ที่ TICK_PROPS)
          .with_columns(
              pl.lit(path.name).alias("demo_file"),
              pl.lit(dem.header.get("map_name", "unknown")).alias("map_name"),
          )
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="ดึงตำแหน่งผู้เล่นแบบ 1 Hz จากเดโมทั้งโฟลเดอร์")
    ap.add_argument("--limit", type=int, help="อ่านแค่กี่ไฟล์ (ไว้ทดสอบ)")
    ap.add_argument("--force", action="store_true", help="อ่านใหม่ทุกไฟล์ ไม่ใช้แคช")
    ap.add_argument("--hz", type=float, default=1.0, help="เก็บกี่ครั้งต่อวินาที (ค่าตั้งต้น 1)")
    args = ap.parse_args()

    demos = sorted(DEMO_DIR.glob("*.dem"))[: args.limit]
    if not demos:
        sys.exit(f"ไม่เจอไฟล์ .dem ใน {DEMO_DIR} — เอาเดโมมาวางในโฟลเดอร์นี้ก่อน")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for i, path in enumerate(demos, 1):
        # แคชรายไฟล์ — เดโมไฟล์ละหลายร้อย MB ถ้าพังกลางทางจะได้ไม่ต้องเริ่มใหม่หมด
        cache = CACHE_DIR / f"{path.stem}_{args.hz}hz.parquet"
        if cache.exists() and not args.force:
            print(f"[{i}/{len(demos)}] {path.name} — ใช้แคช")
            frames.append(pl.read_parquet(cache))
            continue

        t0 = time.time()
        try:
            df = parse_one(path, args.hz)
        except Exception as e:                      # เดโมเสียหนึ่งไฟล์ ไม่ควรทำให้ทั้ง batch ล่ม
            print(f"[{i}/{len(demos)}] {path.name} — พัง: {e}")
            continue

        df.write_parquet(cache)
        frames.append(df)
        print(f"[{i}/{len(demos)}] {path.name} — {len(df):,} แถว ({time.time() - t0:.0f}s)")

    if not frames:
        sys.exit("ไม่ได้ข้อมูลเลย")

    out = pl.concat(frames, how="diagonal_relaxed")
    OUT.parent.mkdir(exist_ok=True)
    out.write_parquet(OUT)

    mb = OUT.stat().st_size / 1024**2
    print(f"\n{len(out):,} แถว จาก {out['demo_file'].n_unique()} แมตช์")
    print(f"เซฟแล้ว: {OUT} ({mb:.1f} MB)")


if __name__ == "__main__":
    main()
