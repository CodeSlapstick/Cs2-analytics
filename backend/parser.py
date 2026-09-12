# -*- coding: utf-8 -*-
"""
backend/parser.py — อ่านไฟล์ .dem หนึ่งไฟล์ ออกมาเป็น JSON ที่ normalize แล้ว

    python -m backend.parser                       # ทุกไฟล์ใน demos/ -> output/json/<ชื่อเดโม>.json
    python -m backend.parser demos/X.dem           # ไฟล์เดียว
    python -m backend.parser --limit 1 --force     # ลอง 1 ไฟล์ ไม่สนแคช

    หรือเรียกจากโค้ดอื่น:
        from backend.parser import parse_demo
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

# ==================================================================================================
# ค่าคงที่: event / prop ที่ขอจาก demoparser2 (ชุดเดียวกับ research/demoparser.py)
# backend/parser.py — ค่าคงที่ที่ parser ใช้ร่วมกับสคริปต์ใน research/
#
# แยกออกมาไฟล์เดียวเพื่อให้ service.py (ตัวจริงที่ระบบใช้) กับ research/prep/demoparser.py
# (ตัวสร้าง data/all_kills.csv) ใช้ชุด event/prop เดียวกันเป๊ะ ไม่งั้นวันหนึ่งสองที่จะเริ่มต่างกันเงียบ ๆ
# ==================================================================================================
# event ที่ต้องขอจาก demoparser2 — ชุดขั้นต่ำที่ awpy ใช้หาขอบเขตรอบและคิล
EVENTS = [
    "player_death",           # ตัวคิลเอง
    "round_start",            # สี่อันล่างนี้ create_round_df ใช้หาขอบเขตแต่ละรอบ
    "round_freeze_end",
    "round_end",
    "round_officially_ended",
    "bomb_planted",           # ไม่จำเป็นต่อ kills แต่ทำให้คอลัมน์ bomb_plant ในตารางรอบไม่ว่าง
]

# props ของผู้เล่นที่ให้ parser แนบมากับทุก event
#   awpy เปลี่ยนชื่อให้เองตอนอ่าน: team_name -> side, last_place_name -> place
PLAYER_PROPS = ["last_place_name", "X", "Y", "Z", "health", "team_name"]

# ชื่ออาวุธในเดโม -> ชื่อสั้นที่เราใช้ (molotov กับ incendiary คือของเดียวกันคนละฝั่ง)
GRENADE_TYPES = {
    "flashbang": "flash", "smokegrenade": "smoke", "hegrenade": "he",
    "molotov": "molotov", "incgrenade": "molotov", "decoy": "decoy",
}


# ==================================================================================================
# อ่านเดโมหนึ่งไฟล์ -> dict
# ==================================================================================================
ROOT = Path(__file__).resolve().parent.parent


DEMO_DIR = ROOT / "demos"
OUT_DIR = ROOT / "output" / "json"

SCHEMA_VERSION = 6      # ขยับเมื่อโครง JSON เปลี่ยนแบบที่ ETL เดิมอ่านไม่ได้  (2 = damages, 3 = player_rounds + grenades, 4 = positions 1 Hz, 5 = team_clan + จุดวางบอมบ์, 6 = ระเบิดขว้างจากไหน/ตกที่ไหน)

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


def _round_table(dem) -> pl.DataFrame:
    """ตารางรอบ + จุดที่วางบอมบ์ — เอาจากตารางรอบโดยตรง จะได้ครบแม้รอบที่ไม่มีคิลเลย"""
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
    if bp is None or not len(bp):
        return rounds.with_columns(pl.lit(None, pl.Float64).alias("bomb_plant_x"),
                                   pl.lit(None, pl.Float64).alias("bomb_plant_y"))
    plant = (bp.select(pl.col("tick").cast(pl.Int32).alias("bomb_plant_tick"),
                       pl.col("user_X").cast(pl.Float64).alias("bomb_plant_x"),
                       pl.col("user_Y").cast(pl.Float64).alias("bomb_plant_y"))
             .unique("bomb_plant_tick", keep="first"))
    return rounds.join(plant, on="bomb_plant_tick", how="left")


def _kill_table(dem) -> pl.DataFrame:
    """คิล — เปลี่ยนชื่อคอลัมน์ให้ตรง schema ตัดคอลัมน์ที่ DB ไม่เก็บ"""
    return _clean(
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


def _damage_table(dem) -> pl.DataFrame:
    """ดาเมจ — player_hurt ไม่มีเลขรอบติดมา ต้องปะเองจากขอบเขต tick ของแต่ละรอบ

    apply_round_num คือฟังก์ชันเดียวกับที่ awpy ใช้ปะเลขรอบให้ตาราง kills เกณฑ์จึงตรงกันแน่นอน
    แถวที่ปะไม่ได้ (round_num ว่าง) คือดาเมจตอน warmup หรือระหว่างพักรอบ — ตัดทิ้ง
    ส่วน user_steamid ว่างแปลว่าหาคนโดนไม่เจอ ซึ่ง damages.victim_id เป็น NOT NULL จึงตัดทิ้งเหมือนกัน

    ทำไมไม่ใช้ dmg_health ที่เดโมให้มา
    dmg_health คือ "ดาเมจดิบของกระสุน" — AWP เข้าตัวขึ้น 148 ทั้งที่คนโดนเหลือเลือดแค่ 7
    เอาไปรวมแล้ว ADR จะพองเกินจริง (ทดลองแล้วได้ 148 ต่อรอบ ทั้งที่โปรระดับโลกอยู่ 70-100)
    ADR ตามเกณฑ์ HLTV นับเฉพาะเลือดที่เสียจริง = เลือดก่อนโดน - เลือดหลังโดน
    health ในอีเวนต์คือเลือด "หลังโดน" ส่วนเลือดก่อนโดนคือ health ของนัดก่อนหน้าของคนเดิมในรอบเดิม
    (ไม่มีนัดก่อนหน้า = ยังไม่เคยโดนในรอบนี้ = 100)
    """
    return _clean(
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


def _wanted_ticks(dem, tickrate: int) -> tuple[dict[int, tuple[int, str]], dict[int, int]]:
    """tick ที่ต้องขอจาก parser คืน (tick ของ player_rounds, tick ของ positions)

    tick "start" = freeze จบ (ฝั่ง + เงิน)   tick "end" = round_end (ใครยังรอด)
    ใช้ end ไม่ใช่ official_end เพราะช่วงหลัง round_end ยังยิงกันได้ คนที่ตายตอนนั้นไม่นับว่าเสียรอบ
    """
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
    return want, pos_want


def _player_round_table(at_start: pl.DataFrame, at_end: pl.DataFrame) -> pl.DataFrame:
    """หนึ่งแถวต่อคนต่อรอบ — ฝั่ง / มูลค่าอุปกรณ์ / รอดถึงจบรอบไหม"""
    return _clean(
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


def _position_table(all_ticks: pl.DataFrame, pos_want: dict[int, int]) -> pl.DataFrame:
    """ตำแหน่งผู้เล่น 1 Hz เฉพาะช่วงที่รอบกำลังเล่นและคนนั้นยังมีชีวิต

    เดโมบันทึก 64-128 tick/วินาที ถ้าเก็บทุก tick จะได้ ~2.7 ล้านแถวต่อแมตช์ และ 99% ซ้ำกัน
    วินาทีละครั้งเหลือ ~21,000 แถว ยังพอบอกได้ว่าใครไปทางไหน โรเทตตอนไหน
    คนตายแล้วยังมีพิกัดค้างตรงที่ตาย ถ้าไม่กรอง is_alive จะกลายเป็น "ยืนนิ่งตรงนั้นทั้งรอบ"
    """
    return _clean(
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


def _grenade_rows(dem, tickrate: int) -> list[dict]:
    """ระเบิดทุกลูก จาก weapon_fire พร้อมจุดตกและเวลาที่ควัน/ไฟหมด

    ใช้ weapon_fire เพราะ grenade_thrown ไม่มีในเดโม 14 จาก 50 ไฟล์
    """
    fired = dem.parser.parse_event("weapon_fire", player=["team_name", "X", "Y"])
    if hasattr(fired, "columns") and len(fired):
        thrown = (
            apply_round_num(pl.from_pandas(fired).with_columns(pl.col("weapon").str.replace("^weapon_", "")), dem.rounds)
            .filter(pl.col("weapon").is_in(list(GRENADE_TYPES)))
            .drop_nulls(["round_num"])
            .select(
                pl.col("round_num").cast(pl.Int32),
                pl.col("tick").cast(pl.Int32),
                pl.col("user_steamid").cast(pl.Int64).alias("thrower_id"),
                pl.when(pl.col("user_team_name") == "CT").then(pl.lit("ct")).otherwise(pl.lit("t")).alias("side"),
                pl.col("weapon").replace_strict(GRENADE_TYPES, default="other").alias("type"),
                pl.col("user_X").cast(pl.Float32).alias("throw_x"),     # คนขว้างยืนตรงไหนตอนขว้าง
                pl.col("user_Y").cast(pl.Float32).alias("throw_y"),
            )
            .sort(["round_num", "tick"])
        )
    else:
        thrown = pl.DataFrame(schema={"round_num": pl.Int32, "tick": pl.Int32, "thrower_id": pl.Int64, "side": pl.Utf8,
                                      "type": pl.Utf8, "throw_x": pl.Float32, "throw_y": pl.Float32})
    # จุดที่แต่ละลูกตก + เวลาที่ควัน/ไฟหมด (หน้ารอบวาดบนแผนที่พร้อมชื่อคนขว้าง)
    return attach_landings(thrown.to_dicts(), read_detonations(dem.parser), tickrate)


def _player_table(dem, at_start: pl.DataFrame) -> pl.DataFrame:
    """ทุก steam_id ที่โผล่ ชื่อล่าสุดที่เห็นชนะ

    รวมคนจาก tick ด้วย จะได้ครบ 10 คนแม้บางคนไม่เคยฆ่าหรือตายเลย (FK ของ player_rounds/grenades ต้องการ)
    """
    def ids(col: str, name: str) -> pl.DataFrame:
        return dem.kills.select(pl.col(col).cast(pl.Int64).alias("steam_id"), pl.col(name).alias("name"))

    return (
        pl.concat([
            ids("attacker_steamid", "attacker_name"),
            ids("victim_steamid", "victim_name"),
            ids("assister_steamid", "assister_name"),
            at_start.select(pl.col("steamid").cast(pl.Int64).alias("steam_id"), pl.col("name")),
        ])
        .drop_nulls("steam_id")
        .with_columns(pl.col("steam_id").cast(pl.Int64))
        .unique(subset="steam_id", keep="last", maintain_order=True)
        .sort("steam_id")
    )


def parse_demo(path: Path) -> dict:
    """อ่านเดโมหนึ่งไฟล์ คืน dict โครง normalized พร้อม json.dumps"""
    dem = Demo(path)
    dem.events = dem.parse_events([*EVENTS, "player_hurt"], player_props=PLAYER_PROPS)
    dem.rounds = create_round_df(dem.events)
    tickrate = int(dem.tickrate)

    # ขอ parser ทีเดียวทั้ง tick ของ player_rounds และของ positions — parser (Rust) ข้าม tick ที่ไม่ขอให้เอง
    want, pos_want = _wanted_ticks(dem, tickrate)
    all_ticks = pl.from_pandas(dem.parser.parse_ticks(wanted_props=TICK_PROPS, ticks=sorted(set(want) | set(pos_want))))
    ticks = all_ticks.join(
        pl.DataFrame({"tick": list(want), "round_num": [v[0] for v in want.values()], "at": [v[1] for v in want.values()]}),
        on="tick",
    )
    # ตอน freeze จบ "ผู้เล่นจริง" ทุกคนต้องมีชีวิต — โค้ชอยู่ในทีมเดียวกัน (team_name เหมือนกัน) แต่ is_alive = False
    # ถ้าไม่กรอง โค้ชจะโผล่เป็นผู้เล่นคนที่ 11-12 ของรอบ แล้วไปดึงค่าเฉลี่ย KAST/rating ของทั้งชุดลง
    at_start = ticks.filter((pl.col("at") == "start") & pl.col("is_alive"))
    at_end = ticks.filter(pl.col("at") == "end").select("round_num", "steamid", pl.col("is_alive").alias("survived"))

    rounds = _round_table(dem)
    kills = _kill_table(dem)
    damages = _damage_table(dem)
    player_rounds = _player_round_table(at_start, at_end)
    positions = _position_table(all_ticks, pos_want)
    grenades = _grenade_rows(dem, tickrate)
    players = _player_table(dem, at_start)

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
        "grenades": grenades,
        "positions": positions.to_dicts(),
    }


# ---------------------------------------------------------------------------
# ระเบิด: จับคู่ "ลูกที่ขว้าง" กับ "จุดที่มันตก"
#   weapon_fire บอกว่าใครขว้างอะไรจากตรงไหน แต่ไม่บอกว่าตกที่ไหน
#   event ตอนตก/แตกบอกจุดตกและคนขว้าง แต่ decoy ไม่มี event นี้ และลูกที่ถือตายไม่มีจุดตก
#   จึงเก็บแถวตาม weapon_fire (จำนวนลูกเท่าเดิม) แล้วเติมจุดตกให้ลูกที่หาคู่เจอ
# ---------------------------------------------------------------------------
DETONATE_EVENTS = {"smoke": "smokegrenade_detonate", "flash": "flashbang_detonate",
                   "he": "hegrenade_detonate", "molotov": "inferno_startburn"}
EXPIRE_EVENTS = {"smoke": "smokegrenade_expired", "molotov": "inferno_expire"}
MAX_FLIGHT_SEC = 20     # ขว้างแล้วตกช้าสุดกี่วินาที (ลูกที่เด้งไกลที่สุดยังไม่ถึง 10 วินาที) — เกินนี้ไม่ใช่ลูกเดียวกัน


def _num(v, cast):
    return None if v is None or v != v else cast(v)      # v != v = NaN จาก pandas


def _event_rows(parser, name: str) -> list[dict]:
    try:
        df = parser.parse_event(name)
    except Exception:   # noqa: BLE001 — เดโมบางไฟล์ไม่มี event นี้เลย
        return []
    return df.to_dict("records") if hasattr(df, "columns") and len(df) else []


def read_detonations(parser) -> dict[str, list[dict]]:
    """{ชนิด: [{tick, thrower_id, x, y, end_tick}]} เรียงตาม tick — end_tick มาจาก event ตอนหมดของ entity เดียวกัน"""
    out: dict[str, list[dict]] = {}
    for gtype, event in DETONATE_EVENTS.items():
        dets = sorted(({"tick": int(r["tick"]), "thrower_id": _num(r.get("user_steamid"), int),
                        "x": _num(r.get("x"), float), "y": _num(r.get("y"), float),
                        "entityid": r.get("entityid"), "end_tick": None} for r in _event_rows(parser, event)),
                      key=lambda d: d["tick"])
        if gtype in EXPIRE_EVENTS:
            expires = sorted((int(r["tick"]), r.get("entityid")) for r in _event_rows(parser, EXPIRE_EVENTS[gtype]))
            for d in dets:     # entityid ถูกใช้ซ้ำได้ทั้งแมตช์ จึงเอา "ตัวแรกหลังตก" ของ entity เดียวกัน
                d["end_tick"] = next((t for t, e in expires if e == d["entityid"] and t >= d["tick"]), None)
        out[gtype] = dets
    return out


def attach_landings(throws: list[dict], detonations: dict[str, list[dict]], tickrate: int) -> list[dict]:
    """เติม land_x / land_y / land_tick / end_tick ให้ลูกที่ขว้าง

    คู่กัน = คนขว้างเดียวกัน ชนิดเดียวกัน ตกหลังขว้างไม่เกิน MAX_FLIGHT_SEC — ไล่ตามเวลา ลูกที่ขว้างก่อนได้จุดตกแรกที่ยังว่าง
    ลูกที่หาคู่ไม่เจอ (decoy / ถือตาย) ยังอยู่ครบ แค่ไม่มีจุดตก
    แฟลชกับ HE ทำงานทันทีที่แตก: end_tick = land_tick
    """
    window = MAX_FLIGHT_SEC * int(tickrate)
    used: set[tuple[str, int]] = set()
    out = []
    for g in sorted(throws, key=lambda g: g["tick"]):
        row = {**g, "land_x": None, "land_y": None, "land_tick": None, "end_tick": None}
        for i, d in enumerate(detonations.get(g["type"], [])):
            if d["tick"] > g["tick"] + window:
                break
            if (g["type"], i) in used or d["thrower_id"] != g.get("thrower_id") or d["tick"] < g["tick"]:
                continue
            used.add((g["type"], i))
            row.update(land_x=d["x"], land_y=d["y"], land_tick=d["tick"],
                       end_tick=d["end_tick"] if g["type"] in EXPIRE_EVENTS else d["tick"])
            break
        out.append(row)
    return out


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
