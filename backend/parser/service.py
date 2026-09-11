#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parser_service.py — อ่านไฟล์ .dem หนึ่งไฟล์ ออกมาเป็น JSON ที่ normalize แล้ว

    python -m backend.parser.service                       # ทุกไฟล์ใน demos/ -> output/json/<ชื่อเดโม>.json
    python -m backend.parser.service demos/X.dem           # ไฟล์เดียว
    python -m backend.parser.service --limit 1 --force     # ลอง 1 ไฟล์ ไม่สนแคช

    หรือเรียกจากโค้ดอื่น:
        from backend.parser.service import parse_demo
        doc = parse_demo(Path("demos/X.dem"))               # dict พร้อม json.dumps

"normalized" แปลว่าอะไร
    ไม่ใช่ตารางแบน ๆ ที่ชื่อผู้เล่นซ้ำทุกแถวเหมือน all_kills.csv
    แต่แยกเป็น 7 ก้อนตามตารางใน backend/models.py แล้วอ้างถึงกันด้วยคีย์:
        match          1 ก้อน   ข้อมูลระดับแมตช์
        players        n แถว    steam_id -> ชื่อ (เก็บครั้งเดียว)
        rounds         n แถว    คีย์คือ round_num
        kills          n แถว    อ้าง rounds ด้วย round_num, อ้าง players ด้วย steam_id
        damages        n แถว    ทุกครั้งที่มีคนโดนดาเมจ ไม่ใช่แค่ครั้งที่ตาย — ADR ใช้ตัวนี้
        player_rounds  n แถว    หนึ่งแถวต่อคนต่อรอบ: ฝั่ง / มูลค่าอุปกรณ์ / รอดถึงจบรอบไหม — KAST, win rate, เศรษฐกิจ ใช้ตัวนี้
        grenades       n แถว    ระเบิดทุกลูกที่ขว้าง — utility per round ใช้ตัวนี้
    ETL loader (backend/) รับไฟล์นี้แล้ว INSERT ตามลำดับ players -> match -> rounds -> kills -> damages -> player_rounds -> grenades ได้เลย
    ชื่อฟิลด์ตั้งให้ตรงกับคอลัมน์ใน backend/models.py ทุกตัว จะได้ไม่ต้อง map ชื่ออีกรอบ

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
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from awpy import Demo
from awpy.parsers.rounds import apply_round_num, create_round_df

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))      # ให้รัน python -m backend.parser.service จากรากโปรเจกต์ได้
from backend.parser.constants import (  # noqa: E402  ชุด event/prop เดียวกับตัวสร้าง all_kills.csv
    EVENTS,
    GRENADE_TYPES,
    PLAYER_PROPS,
)

# GRENADE_TYPES อยู่ใน backend.parser.constants แล้ว      # noqa: E402  ตารางชื่อระเบิดชุดเดียวกับ grenades.parquet

DEMO_DIR = ROOT / "demos"
OUT_DIR = ROOT / "output" / "json"

SCHEMA_VERSION = 5      # ขยับเมื่อโครง JSON เปลี่ยนแบบที่ ETL เดิมอ่านไม่ได้  (2 = damages, 3 = player_rounds + grenades, 4 = positions 1 Hz, 5 = team_clan + จุดวางบอมบ์)

# ชื่อไฟล์เดโมจาก HLTV มีแบบแผน "ทีมA-vs-ทีมB-แมพ.dem" -> แกะชื่อทีมจากชื่อไฟล์
TEAMS_RE = re.compile(r"^(?P<a>.+?)-vs-(?P<b>.+?)-[^-]+\.dem$", re.IGNORECASE)

# คอลัมน์จาก awpy -> ชื่อคอลัมน์ในตาราง kills ของ backend/models.py
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

# คอลัมน์จาก awpy -> ชื่อคอลัมน์ในตาราง damages ของ backend/models.py
#   ใน player_hurt "คนโดน" ใช้ prefix user_ ไม่ใช่ victim_ เหมือน player_death
#   health_lost ไม่ได้มาจากเดโมตรง ๆ แต่คำนวณเองใน parse_demo (ดูคอมเมนต์ตรงนั้น)
DAMAGE_COLUMNS = {
    "tick": "tick",
    "attacker_steamid": "attacker_id", "user_steamid": "victim_id",
    "weapon": "weapon", "health_lost": "damage", "hitgroup": "hitgroup",
}

# สถานะผู้เล่นที่ต้องดู "ณ tick" (ไม่มีอีเวนต์ไหนบอก) — ขอแค่ 2 tick ต่อรอบ ไม่ใช่ทุก tick
#   ทำไมใช้ current_equip_value ไม่ใช่ round_start_equip_value
#   ตัวหลังในเดโม CS2 ค้างค่าเก่า (เห็น 200 ทั้งที่ถือ M4 อยู่) ส่วนตัวแรก ณ tick ที่ freeze จบ
#   คือมูลค่าจริง ซึ่งตรงกับนิยาม "equipment value at freeze-time end" ของ HLTV พอดี
TICK_PROPS = ["team_name", "is_alive", "current_equip_value", "balance",
              "X", "Y", "Z", "last_place_name", "health",
              "team_clan_name"]   # ห้าตัวหลังใช้กับตำแหน่ง 1 Hz (positions)

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
    dem.events = dem.parse_events([*EVENTS, "player_hurt"], player_props=PLAYER_PROPS)
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
        pl.col("bomb_site").cast(pl.Utf8).alias("bomb_site"),
    )).sort("round_num")
    # จุดที่วางบอมบ์ = ตำแหน่งคนวาง ณ event bomb_planted (ไอคอนบอมบ์บนแผนที่หน้า Round Review)
    bp = dem.events.get("bomb_planted") if isinstance(dem.events, dict) else None
    if bp is not None and len(bp):
        plant = (bp.select(pl.col("tick").cast(pl.Int32).alias("bomb_plant_tick"),
                           pl.col("user_X").cast(pl.Float64).alias("bomb_plant_x"),
                           pl.col("user_Y").cast(pl.Float64).alias("bomb_plant_y"))
                 .unique("bomb_plant_tick", keep="first"))
        rounds = rounds.join(plant, on="bomb_plant_tick", how="left")
    else:
        rounds = rounds.with_columns(pl.lit(None, pl.Float64).alias("bomb_plant_x"), pl.lit(None, pl.Float64).alias("bomb_plant_y"))

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

    # --- damages: player_hurt ไม่มีเลขรอบติดมา ต้องปะเองจากขอบเขต tick ของแต่ละรอบ ---
    #   apply_round_num คือฟังก์ชันเดียวกับที่ awpy ใช้ปะเลขรอบให้ตาราง kills เกณฑ์จึงตรงกันแน่นอน
    #   แถวที่ปะไม่ได้ (round_num ว่าง) คือดาเมจตอน warmup หรือระหว่างพักรอบ — ตัดทิ้ง
    #   ส่วน user_steamid ว่างแปลว่าหาคนโดนไม่เจอ ซึ่ง damages.victim_id เป็น NOT NULL จึงตัดทิ้งเหมือนกัน
    #
    #   ทำไมไม่ใช้ dmg_health ที่เดโมให้มา
    #   dmg_health คือ "ดาเมจดิบของกระสุน" — AWP เข้าตัวขึ้น 148 ทั้งที่คนโดนเหลือเลือดแค่ 7
    #   เอาไปรวมแล้ว ADR จะพองเกินจริง (ทดลองแล้วได้ 148 ต่อรอบ ทั้งที่โปรระดับโลกอยู่ 70-100)
    #   ADR ตามเกณฑ์ HLTV นับเฉพาะเลือดที่เสียจริง = เลือดก่อนโดน - เลือดหลังโดน
    #   health ในอีเวนต์คือเลือด "หลังโดน" ส่วนเลือดก่อนโดนคือ health ของนัดก่อนหน้าของคนเดิมในรอบเดิม
    #   (ไม่มีนัดก่อนหน้า = ยังไม่เคยโดนในรอบนี้ = 100)
    damages = _clean(
        apply_round_num(dem.events["player_hurt"], dem.rounds)
        .drop_nulls(["round_num", "user_steamid"])
        .sort(["round_num", "tick"])
        .with_columns(
            (pl.col("health").shift(1).over(["round_num", "user_steamid"]).fill_null(100) - pl.col("health"))
            .clip(0, 100)
            .alias("health_lost")
        )
        .select(["round_num", *DAMAGE_COLUMNS])
        .rename(DAMAGE_COLUMNS)
        .with_columns(
            pl.col(["round_num", "tick", "damage"]).cast(pl.Int32),
            pl.col(["attacker_id", "victim_id"]).cast(pl.Int64),
        )
        .sort(["round_num", "tick"])
    )

    # --- player_rounds: หนึ่งแถวต่อคนต่อรอบ — ฝั่ง / มูลค่าอุปกรณ์ / รอดถึงจบรอบไหม ---
    #   tick "start" = freeze จบ (ฝั่ง + เงิน)   tick "end" = round_end (ใครยังรอด)
    #   ใช้ end ไม่ใช่ official_end เพราะช่วงหลัง round_end ยังยิงกันได้ คนที่ตายตอนนั้นไม่นับว่าเสียรอบ
    want: dict[int, tuple[int, str]] = {}
    pos_want: dict[int, int] = {}          # tick -> round_num ของตำแหน่ง 1 Hz (ห้ามเก็บทุก tick — ดูคอมเมนต์ positions)
    for r in dem.rounds.iter_rows(named=True):
        fe = r["freeze_end"] or r["start"]
        en = r["end"] or r["official_end"]
        if fe is not None:
            want[int(fe)] = (r["round_num"], "start")
        if en is not None:
            want[int(en)] = (r["round_num"], "end")
        if fe is not None and en is not None:
            for t in range(int(fe), int(en), tickrate):      # วินาทีละครั้ง ตั้งแต่ freeze จบถึงรอบจบ
                pos_want[t] = int(r["round_num"])
    # ขอ parser ทีเดียวทั้ง tick ของ player_rounds และของ positions — parser (Rust) ข้าม tick ที่ไม่ขอให้เอง
    all_ticks = pl.from_pandas(dem.parser.parse_ticks(wanted_props=TICK_PROPS, ticks=sorted(set(want) | set(pos_want))))
    ticks = all_ticks.join(
        pl.DataFrame({"tick": list(want), "round_num": [v[0] for v in want.values()], "at": [v[1] for v in want.values()]}),
        on="tick",
    )
    # ตอน freeze จบ "ผู้เล่นจริง" ทุกคนต้องมีชีวิต — โค้ชอยู่ในทีมเดียวกัน (team_name เหมือนกัน) แต่ is_alive = False
    # ถ้าไม่กรอง โค้ชจะโผล่เป็นผู้เล่นคนที่ 11-12 ของรอบ แล้วไปดึงค่าเฉลี่ย KAST/rating ของทั้งชุดลง
    at_start = ticks.filter((pl.col("at") == "start") & pl.col("is_alive"))
    at_end = ticks.filter(pl.col("at") == "end").select("round_num", "steamid", pl.col("is_alive").alias("survived"))
    player_rounds = _clean(
        at_start.join(at_end, on=["round_num", "steamid"], how="left")
        .select(
            pl.col("round_num").cast(pl.Int32),
            pl.col("steamid").cast(pl.Int64).alias("steam_id"),
            pl.when(pl.col("team_name") == "CT").then(pl.lit("ct")).otherwise(pl.lit("t")).alias("side"),
            pl.col("current_equip_value").cast(pl.Int32).alias("equip_value"),
            pl.col("balance").cast(pl.Int32),
            pl.col("survived").fill_null(False),
            pl.col("team_clan_name").alias("team_clan"),      # clan tag ณ รอบนั้น — loader ผูกเป็นทีมคงที่ด้วย teams.assign_teams
        )
        .sort(["round_num", "steam_id"])
    )

    # --- positions: ตำแหน่งผู้เล่น 1 Hz เฉพาะช่วงที่รอบกำลังเล่นและคนนั้นยังมีชีวิต ---
    #   เดโมบันทึก 64-128 tick/วินาที ถ้าเก็บทุก tick จะได้ ~2.7 ล้านแถวต่อแมตช์ และ 99% ซ้ำกัน
    #   วินาทีละครั้งเหลือ ~21,000 แถว ยังพอบอกได้ว่าใครไปทางไหน โรเทตตอนไหน
    #   คนตายแล้วยังมีพิกัดค้างตรงที่ตาย ถ้าไม่กรอง is_alive จะกลายเป็น "ยืนนิ่งตรงนั้นทั้งรอบ"
    positions = _clean(
        all_ticks.join(pl.DataFrame({"tick": list(pos_want), "round_num": list(pos_want.values())}), on="tick")
        .filter(pl.col("is_alive"))
        .select(
            pl.col("round_num").cast(pl.Int32),
            pl.col("tick").cast(pl.Int32),
            pl.col("steamid").cast(pl.Int64).alias("steam_id"),
            pl.when(pl.col("team_name") == "CT").then(pl.lit("ct")).otherwise(pl.lit("t")).alias("side"),
            pl.col("X").cast(pl.Float32).alias("x"),
            pl.col("Y").cast(pl.Float32).alias("y"),
            pl.col("Z").cast(pl.Float32).alias("z"),
            pl.col("health").cast(pl.Int16),
            pl.col("last_place_name").alias("place"),
        )
        .sort(["round_num", "tick", "steam_id"])
    )

    # --- grenades: ระเบิดทุกลูก จาก weapon_fire (grenade_thrown ไม่มีในเดโม 14 จาก 50 ไฟล์ — ดู parse_grenades.py) ---
    fired = dem.parser.parse_event("weapon_fire", player=["team_name"])
    if hasattr(fired, "columns") and len(fired):
        grenades = (
            apply_round_num(pl.from_pandas(fired).with_columns(pl.col("weapon").str.replace("^weapon_", "")), dem.rounds)
            .filter(pl.col("weapon").is_in(list(GRENADE_TYPES)))
            .drop_nulls(["round_num"])
            .select(
                pl.col("round_num").cast(pl.Int32),
                pl.col("tick").cast(pl.Int32),
                pl.col("user_steamid").cast(pl.Int64).alias("thrower_id"),
                pl.when(pl.col("user_team_name") == "CT").then(pl.lit("ct")).otherwise(pl.lit("t")).alias("side"),
                pl.col("weapon").replace_strict(GRENADE_TYPES, default="other").alias("type"),
            )
            .sort(["round_num", "tick"])
        )
    else:
        grenades = pl.DataFrame(schema={"round_num": pl.Int32, "tick": pl.Int32, "thrower_id": pl.Int64, "side": pl.Utf8, "type": pl.Utf8})

    # --- players: ทุก steam_id ที่โผล่ ชื่อล่าสุดที่เห็นชนะ ---
    #   รวมคนจาก tick ด้วย จะได้ครบ 10 คนแม้บางคนไม่เคยฆ่าหรือตายเลย (FK ของ player_rounds/grenades ต้องการ)
    players = (
        pl.concat([
            dem.kills.select(pl.col("attacker_steamid").cast(pl.Int64).alias("steam_id"), pl.col("attacker_name").alias("name")),
            dem.kills.select(pl.col("victim_steamid").cast(pl.Int64).alias("steam_id"), pl.col("victim_name").alias("name")),
            dem.kills.select(pl.col("assister_steamid").cast(pl.Int64).alias("steam_id"), pl.col("assister_name").alias("name")),
            at_start.select(pl.col("steamid").cast(pl.Int64).alias("steam_id"), pl.col("name")),
        ])
        .drop_nulls("steam_id")
        .with_columns(pl.col("steam_id").cast(pl.Int64))
        .unique(subset="steam_id", keep="last", maintain_order=True)
        .sort("steam_id")
    )

    team_a, team_b = teams_from_filename(path.name)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "match": {
            "demo_file": path.name,
            "map_name": dem.header.get("map_name", "unknown"),
            "tickrate": tickrate,
            "team_a": team_a,
            "team_b": team_b,
        },
        "counts": {"players": len(players), "rounds": len(rounds), "kills": len(kills), "damages": len(damages),
                   "player_rounds": len(player_rounds), "grenades": len(grenades), "positions": len(positions)},
        "players": players.to_dicts(),
        "rounds": rounds.to_dicts(),
        "kills": kills.to_dicts(),
        "damages": damages.to_dicts(),
        "player_rounds": player_rounds.to_dicts(),
        "grenades": grenades.to_dicts(),
        "positions": positions.to_dicts(),
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
    totals = {"players": 0, "rounds": 0, "kills": 0, "damages": 0, "player_rounds": 0, "grenades": 0}
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
        print(f"[{i}/{len(demos)}] {path.name} — {c['rounds']} รอบ {c['kills']} คิล {c['damages']} ดาเมจ {c['grenades']} ระเบิด "
              f"{target.stat().st_size / 1024:.0f} KB ({time.time() - t0:.1f}s)")

    print(f"\nเสร็จ {done} · ข้าม {skipped} · พัง {failed}  ->  {args.out}")
    if done:
        print(f"รวมที่ parse รอบนี้: {totals['rounds']:,} รอบ {totals['kills']:,} คิล "
              f"{totals['damages']:,} ดาเมจ {totals['grenades']:,} ระเบิด {totals['players']:,} นักแข่ง")


if __name__ == "__main__":
    main()
