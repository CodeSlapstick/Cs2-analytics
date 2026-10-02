#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
อ่านไฟล์ .dem ทุกไฟล์ใน demos/ ด้วย awpy แล้วรวม kills เป็น csv ตารางเดียว

    python research/prep/demoparser.py            # อ่านทั้งหมดที่ยังไม่เคยอ่าน
    python research/prep/demoparser.py --limit 3  # ลองแค่ 3 ไฟล์แรก
    python research/prep/demoparser.py --force    # อ่านใหม่หมด ไม่สนแคช

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
# อ่านเฉพาะ demos/reference/ — เดโมที่ผู้ใช้อัปโหลดอยู่ที่ demos/uploads/ และต้องไม่หลุดเข้าชุดที่ใช้เทรนโมเดล
# (เคยเป็น demos/ ซึ่งเป็นโฟลเดอร์เดียวกับที่ระบบเขียนไฟล์อัปโหลดลงไป รันซ้ำเมื่อไรข้อมูลก็ปนกันเงียบ ๆ)
DEMO_DIR = ROOT / "demos" / "reference"
CACHE_DIR = ROOT / "output" / "kills_cache"
OUT_CSV = ROOT / "data" / "all_kills.csv"

sys.path.insert(0, str(ROOT))
from backend.features import assign_teams  # noqa: E402  ผูกทีมด้วยกฎชุดเดียวกับระบบหลัก

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


ROLE_EVENT_COLUMNS = [
    "round_time_seconds",
    "is_enemy_kill",
    "is_live_round_kill",
    "round_kill_order",
    "is_opening_kill",
    "is_opening_death",
    "is_early_engagement",
    "is_postplant_kill",
    "round_phase",
    "trade_kill_count",
    "is_trade_kill",
    "victim_was_traded",
    "is_site_engagement",
    "is_flash_assisted_kill",
    "attacker_won_round",
]

# ลำดับคอลัมน์สำหรับคนอ่าน: บริบทก่อน ตามด้วยสัญญาณ role และผู้เล่นแต่ละฝ่าย
# สคริปต์ปลายทางเลือกคอลัมน์ด้วยชื่ออยู่แล้ว การจัดลำดับจึงไม่เปลี่ยนความหมายของ schema
ALL_KILLS_COLUMN_GROUPS = {
    "Match & Round": [
        "demo_file", "map_name", "tickrate", "round_num", "tick", "round_start_tick",
        "round_time_seconds", "bomb_plant_tick", "round_phase", "round_winner_side",
        "round_winner", "round_end_reason", "ct_side", "t_side",
    ],
    "Role Signals": [
        "is_enemy_kill", "is_live_round_kill", "round_kill_order", "is_opening_kill",
        "is_opening_death", "is_early_engagement", "is_postplant_kill",
        "is_site_engagement", "is_flash_assisted_kill", "attacker_won_round",
        "trade_kill_count", "victim_was_traded", "is_trade_kill",
    ],
    "Attacker": [
        "attacker_name", "attacker_steamid", "attacker_side", "attacker_team_clan",
        "attacker_place", "attacker_X", "attacker_Y", "attacker_Z", "attacker_health",
        "attackerblind", "attacker_blind", "attackerinair",
    ],
    "Victim": [
        "victim_name", "victim_steamid", "victim_side", "victim_team_clan", "victim_place",
        "victim_X", "victim_Y", "victim_Z", "victim_health",
    ],
    "Assister / Support": [
        "assister_name", "assister_steamid", "assister_side", "assister_team_clan",
        "assister_place", "assister_X", "assister_Y", "assister_Z", "assister_health",
        "assistedflash",
    ],
    "Combat": [
        "weapon", "headshot", "hitgroup", "distance", "dmg_health", "dmg_armor",
        "penetrated", "thrusmoke", "noscope", "dominated", "revenge", "wipe",
    ],
    "Technical": [
        "weapon_fauxitemid", "weapon_itemid", "weapon_originalowner_xuid", "noreplay",
    ],
}


def order_all_kills_columns(kills: pl.DataFrame) -> pl.DataFrame:
    """เรียง schema เป็นหมวด และเก็บคอลัมน์จาก parser รุ่นใหม่ที่ยังไม่รู้จักไว้ท้ายไฟล์"""
    grouped = [column for columns in ALL_KILLS_COLUMN_GROUPS.values() for column in columns]
    known = [column for column in grouped if column in kills.columns]
    extra = [column for column in kills.columns if column not in grouped]
    return kills.select(known + extra)


def add_role_event_columns(kills: pl.DataFrame) -> pl.DataFrame:
    """เพิ่มฟีเจอร์ต่อคิลที่ใช้รวมเป็น player-role profile ได้โดยไม่แก้นิยามภายหลัง

    คอลัมน์เหล่านี้ยังเป็นข้อเท็จจริงระดับ event ไม่ใช่ role label:
    - opening = enemy kill แรกของรอบ
    - early = เกิดภายใน 25 วินาทีหลัง freeze time จบ
    - trade = ฆ่าคนที่เพิ่งฆ่าเพื่อนร่วมทีมภายใน 5 วินาที (นิยามเดียวกับ backend/features.py)
    - postplant = tick ของคิลอยู่หลัง bomb_plant_tick

    all_kills ไม่มี grenade throws, player positions หรือ planter id จึงไม่สร้างค่าปลอมสำหรับ
    utility, movement และ bomb carrier; โมเดลต้องอ่านตารางเหล่านั้นจาก DB เมื่อพร้อม
    """
    if kills.is_empty():
        return kills

    required = {
        "demo_file", "round_num", "tick", "tickrate", "round_start_tick", "bomb_plant_tick",
        "attacker_steamid", "victim_steamid", "attacker_side", "victim_side",
        "attacker_place", "victim_place", "assistedflash", "round_winner_side",
    }
    missing = sorted(required - set(kills.columns))
    if missing:
        raise ValueError(f"all_kills ขาดคอลัมน์ต้นทางสำหรับ role features: {', '.join(missing)}")

    # ลบ derived columns รุ่นเดิมก่อนเพื่อให้รันซ้ำกับ CSV/cache ที่เคย enrich แล้วได้ผลเดิม
    existing = [column for column in ROLE_EVENT_COLUMNS if column in kills.columns]
    if existing:
        kills = kills.drop(existing)

    ordered = (kills.sort(["demo_file", "round_num", "tick"])
               .with_row_index("_role_row"))
    rate = pl.col("tickrate").fill_null(128).clip(lower_bound=1)
    enemy = (
        pl.col("attacker_steamid").is_not_null()
        & pl.col("attacker_side").is_in(["ct", "t"])
        & pl.col("victim_side").is_in(["ct", "t"])
        & (pl.col("attacker_side") != pl.col("victim_side"))
    )
    ordered = ordered.with_columns(
        enemy.alias("is_enemy_kill"),
        (enemy & pl.col("round_start_tick").is_not_null() & (pl.col("tick") >= pl.col("round_start_tick")))
        .alias("is_live_round_kill"),
        pl.when(pl.col("round_start_tick").is_not_null() & (pl.col("tick") >= pl.col("round_start_tick")))
        .then((pl.col("tick") - pl.col("round_start_tick")) / rate)
        .otherwise(None)
        .alias("round_time_seconds"),
    ).with_columns(
        pl.when(pl.col("is_live_round_kill"))
        .then(pl.col("is_live_round_kill").cast(pl.Int64).cum_sum().over(["demo_file", "round_num"]))
        .otherwise(None)
        .cast(pl.Int64)
        .alias("round_kill_order"),
        (pl.col("is_live_round_kill") & pl.col("round_time_seconds").is_between(0, 25))
        .alias("is_early_engagement"),
        (
            pl.col("is_live_round_kill")
            & pl.col("bomb_plant_tick").is_not_null()
            & (pl.col("tick") >= pl.col("bomb_plant_tick"))
        ).alias("is_postplant_kill"),
    ).with_columns(
        pl.when(pl.col("is_postplant_kill")).then(pl.lit("postplant")).otherwise(pl.lit("preplant"))
        .alias("round_phase"),
        (
            pl.col("attacker_place").fill_null("").str.starts_with("Bombsite")
            | pl.col("victim_place").fill_null("").str.starts_with("Bombsite")
        ).alias("is_site_engagement"),
        pl.col("assistedflash").fill_null(False).cast(pl.Boolean).alias("is_flash_assisted_kill"),
        (
            pl.col("is_enemy_kill")
            & (pl.col("attacker_side") == pl.col("round_winner_side"))
        ).alias("attacker_won_round"),
    ).with_columns(
        (pl.col("round_kill_order") == 1).fill_null(False).alias("is_opening_kill"),
        (pl.col("round_kill_order") == 1).fill_null(False).alias("is_opening_death"),
    )

    # Trade ต้องมองย้อนหลายแถวและหนึ่งคิลอาจ trade ได้มากกว่าหนึ่ง death จึงคำนวณ
    # เป็นลำดับ event โดยตรงแทน window expression ที่จะทำข้อมูลกรณีนี้หาย
    trade_count = [0] * len(ordered)
    victim_traded = [False] * len(ordered)
    for round_rows in ordered.partition_by(["demo_file", "round_num"], maintain_order=True):
        prior: list[dict] = []
        for row in round_rows.iter_rows(named=True):
            if not row["is_live_round_kill"]:
                continue
            tickrate = row["tickrate"] or 128
            matched = [
                death for death in prior
                if row["tick"] > death["tick"]
                and row["tick"] <= death["tick"] + 5 * tickrate
                and row["victim_steamid"] == death["attacker_steamid"]
                and row["attacker_side"] == death["victim_side"]
            ]
            trade_count[row["_role_row"]] = len(matched)
            for death in matched:
                victim_traded[death["_role_row"]] = True
            prior.append(row)

    return ordered.with_columns(
        pl.Series("trade_kill_count", trade_count, dtype=pl.Int64),
        pl.Series("victim_was_traded", victim_traded, dtype=pl.Boolean),
    ).with_columns(
        (pl.col("trade_kill_count") > 0).alias("is_trade_kill"),
    ).drop("_role_row")


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
    final = order_all_kills_columns(add_role_event_columns(pl.concat(frames, how="diagonal_relaxed")))
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
