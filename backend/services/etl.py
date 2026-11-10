# -*- coding: utf-8 -*-
"""
backend/services/etl.py — เอาผลจาก parser (dict/JSON ที่ normalize แล้ว) ใส่ PostgreSQL

    python backend/etl_loader.py                      # โหลดทุกไฟล์ใน output/json (ข้ามที่เคยโหลด)
    python backend/etl_loader.py output/json/X.json   # ไฟล์เดียว
    python backend/etl_loader.py --force              # โหลดทับของเดิม (ใช้ backfill ฟีเจอร์ให้แมตช์เก่าด้วย)

    จากโค้ดอื่น:
        from backend.etl_loader import load_match_doc, load_match_json
        match_id = await load_match_doc(conn, doc, match_id=42)      # worker: แถว matches มีอยู่แล้ว (status=queued)
        match_id = await load_match_json(conn, Path("x.json"))       # CLI: ให้หาเอาว่าเคยโหลดไหม

idempotent ด้วยวิธีเดียว
    ก่อน INSERT ลูก ๆ ของแมตช์ (rounds -> kills/damages/player_rounds/grenades) จะ DELETE rounds ของแมตช์นั้นทิ้งก่อนเสมอ
    (ตารางลูกทั้งหมด ON DELETE CASCADE จาก rounds) แล้วค่อยใส่ใหม่ในทรานแซกชันเดียว
    รันซ้ำแมตช์เดิมกี่ครั้งจึงได้ข้อมูลชุดเดียว และ matches.id ไม่เปลี่ยน (หน้าเว็บที่ poll อยู่ไม่หลุด)

ฟีเจอร์ (opening / trade / buy type / clutch / KAST) คำนวณที่นี่ด้วย backend/services/features.py
แล้วเก็บลง player_rounds — คำนวณครั้งเดียวตอนโหลด ไม่ต้องคิดใหม่ทุกครั้งที่หน้าเว็บถาม
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))      # ให้รัน python backend/etl_loader.py จากรากโปรเจกต์ได้

from backend.config.database import DATABASE_URL as DB_URL  # noqa: E402  (โหลด .env ตอน import)
from backend.config.database import apply_schema  # noqa: E402
from backend.services.features import assign_teams, compute_features  # noqa: E402

# _int: ฟังก์ชันแปลงค่าเป็นจำนวนเต็ม
# 1. รับค่า v เข้ามา -> 2. เช็คว่าไม่ใช่ None หรือข้อความว่าง -> 3. แปลงเป็น int หรือคืน None
def _int(v):
    return int(v) if v not in (None, "") else None

# _float: ฟังก์ชันแปลงค่าเป็นเลขทศนิยม
def _float(v):
    return float(v) if v is not None else None

# ฟังก์ชันตรวจสอบและแปลง SteamID ให้ถูกต้องตามขอบเขต 64-bit
# 1. รับค่าเข้ามา -> 2. ดักตัด boolean/float ทิ้ง แล้วลองแปลงเป็น int -> 3. เช็คขอบเขต 64-bit แล้วคืนค่า id หรือ None
def _player_id(value) -> int | None:
    if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
        return None
    try:
        steam_id = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return steam_id if 0 < steam_id <= 2**63 - 1 else None

# _upsert_players: ฟังก์ชันบันทึกหรืออัปเดตชื่อผู้เล่นหลักลงตาราง players
# 1. แปลงรายชื่อเป็นคู่ (steam_id, name) -> 2. กรองเฉพาะคนที่มี steam_id ถูกต้อง -> 3. สั่งรันคำสั่ง SQL แบบ UPSERT
async def _upsert_players(conn, players: list[dict]) -> None:
    rows = [(_player_id(p.get("steam_id")), str(p.get("name") or "Unknown player")) for p in players]
    rows = [(steam_id, name) for steam_id, name in rows if steam_id is not None]
    if rows:
        await conn.executemany("""
            INSERT INTO players (steam_id, name) VALUES ($1, $2)
            ON CONFLICT (steam_id) DO UPDATE SET name = EXCLUDED.name;
        """, rows)

#เช็ค SteamID จากทุกเหตุการณ์มาลงทะเบียน กันForeign Keyหลุด
async def _upsert_referenced_players(conn, doc: dict) -> set[int]:
    """Register every valid player reference and return the IDs confirmed in the database."""
    sources = (("kills", ("attacker_id", "victim_id", "assister_id")),
               ("damages", ("attacker_id", "victim_id")),
               ("grenades", ("thrower_id",)),
               ("player_rounds", ("steam_id",)),
               ("positions", ("steam_id",)))
    all_ids = {_player_id(p.get("steam_id")) for p in doc.get("players", [])}
    all_ids.update(_player_id(row.get(key)) for group, keys in sources
                   for row in doc.get(group, []) for key in keys)
    ids = sorted(all_ids - {None})
    if not ids:
        return set()
    await conn.executemany("""
        INSERT INTO players (steam_id, name) VALUES ($1, $2)
        ON CONFLICT (steam_id) DO NOTHING;
    """, [(steam_id, f"Unknown player {steam_id}") for steam_id in ids])
    records = await conn.fetch("SELECT steam_id FROM players WHERE steam_id = ANY($1::bigint[]);", ids)
    return {int(record["steam_id"]) for record in records}

# ตรวจสอบว่า SteamID นี้มีตัวตนอยู่ในฐานข้อมูลจริงไหม
# 1. ตรวจความถูกต้องของไอดีผ่าน _player_id -> 2. เช็คว่าไอดีอยู่ใน known_ids หรือไม่ -> 3. ถ้ามีให้คืนไอดี ถ้าไม่มีให้คืน None
def _known_player_id(value, known_ids: set[int] | None) -> int | None:
    steam_id = _player_id(value)
    return steam_id if steam_id is not None and (known_ids is None or steam_id in known_ids) else None

# SQL ของตารางลูกแต่ละตัว — วางไว้ระดับโมดูลเพื่อให้ฟังก์ชันสร้างแถวอ่านสั้นลง

# บันทึกเหตุการณ์การฆ่าอย่างละเอียด ทั้งคนฆ่าและคนโดนฆฆ่า
SQL_KILLS = """
    INSERT INTO kills (
        round_id, tick, attacker_id, victim_id, assister_id, attacker_side, victim_side, weapon,
        headshot, hitgroup, attacker_blind, thru_smoke, noscope, assisted_flash, penetrated,
        distance, attacker_x, attacker_y, attacker_z, attacker_place, victim_x, victim_y, victim_z, victim_place
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
              $16, $17, $18, $19, $20, $21, $22, $23, $24);
"""
# บันทึกการทำดาเมจและส่วนของร่างกายที่โดนกระสุน
SQL_DAMAGES = """
    INSERT INTO damages (round_id, tick, attacker_id, victim_id, weapon, damage, hitgroup)
    VALUES ($1, $2, $3, $4, $5, $6, $7);
"""
# บันทึกสถิติขั้นสูงรายคนในแต่ละรอบ คะแนน, เงินที่เหลือ,
SQL_PLAYER_ROUNDS = """
    INSERT INTO player_rounds (
        round_id, steam_id, side, equip_value, balance, survived,
        buy_type, kills, deaths, assists, headshots, damage,
        opening_kill, opening_death, trade_kills, was_traded, clutch_vs, clutch_won, kast, features_version
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
    ON CONFLICT (round_id, steam_id) DO NOTHING;
"""

# ผูกผู้เล่นเข้ากับแมตช์และทีมหลัก
SQL_MATCH_PLAYERS = """
    INSERT INTO match_players (match_id, steam_id, start_side, rounds, team_clan) VALUES ($1, $2, $3, $4, $5)
    ON CONFLICT (match_id, steam_id) DO NOTHING;
"""

# บันทึกชนิด พิกัดปา จุดตก และวิถีการลอยของระเบิด
SQL_GRENADES = """
    INSERT INTO grenades (round_id, tick, thrower_id, side, type,
                          throw_x, throw_y, land_x, land_y, land_tick, end_tick, trajectory)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb);
"""

# บันทึกรอยเท้าและสถานะผู้เล่นความถี่ 8 Hz สำหรับเรนเดอร์ 2D Replay
SQL_POSITIONS = """
    INSERT INTO player_positions (match_id, round_num, tick, steam_id, side, x, y, z, health, place,
                                  active_weapon, armor, has_helmet, has_defuser, money, has_bomb, yaw, flash_remaining)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
    ON CONFLICT (match_id, round_num, tick, steam_id) DO NOTHING;
"""

# คุมการบันทึกข้อมูลแบบเป็นชุด (Batch) อย่างปลอดภัย
# 1. รับคำสั่ง SQL และรายการข้อมูล rows -> 2. ถ้ามีข้อมูล ให้สั่ง executemany บันทึกรอบเดียว -> 3. คืนค่าจำนวนแถวที่บันทึกสำเร็จ
async def _insert_many(conn, sql: str, rows: list[tuple]) -> int:
    """executemany ที่ข้ามให้เองเมื่อไม่มีแถว คืนจำนวนแถวที่ใส่ (ไว้ทำสรุปท้ายฟังก์ชัน)"""
    if rows:
        await conn.executemany(sql, rows)
    return len(rows)

# บันทึกข้อมูลรอบลงตาราง rounds และสร้างแผนที่จับคู่ (เลขรอบ -> id ใน DB)
# 1. วนลูปอ่านข้อมูลทีละรอบจากเดโม -> 2. INSERT ลงตาราง rounds พร้อมดึง id ที่เพิ่งสร้างคืนมา (RETURNING id) -> 3. เก็บลง dict แผนผัง {round_num: id} แล้วส่งคืน
async def _insert_rounds(conn, match_id: int, rounds: list[dict]) -> dict[int, int]:
    """ใส่ตารางรอบทีละแถวเพื่อเก็บ id ที่ DB คืนมา คืน map round_num -> rounds.id"""
    round_id_map: dict[int, int] = {}
    for r in rounds:
        rid = await conn.fetchval("""
            INSERT INTO rounds (match_id, round_num, start_tick, end_tick, bomb_plant_tick, bomb_resolved_tick,
                                winner_side, end_reason, bomb_plant_x, bomb_plant_y, bomb_site, defuse_intervals)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12) RETURNING id;
        """, match_id, int(r["round_num"]), _int(r.get("start_tick")), _int(r.get("end_tick")),
           _int(r.get("bomb_plant_tick")), _int(r.get("bomb_resolved_tick")),
           r.get("winner_side"), r.get("end_reason"),
           _float(r.get("bomb_plant_x")), _float(r.get("bomb_plant_y")), r.get("bomb_site"),
           json.dumps(r.get("defuses", [])))
        round_id_map[int(r["round_num"])] = rid
    return round_id_map

# คัดกรองและแปลงข้อมูลคนตายให้พร้อมบันทึกลงตาราง kills (24 คอลัมน์)
# 1. รับรายการคิล ฟังก์ชันหารหัสรอบ และชุดผู้เล่นที่ยืนยันแล้ว -> 2. กรองทิ้งคดีที่ไม่มีรหัสรอบหรือคนตายไม่มีตัวตน -> 3. แพ็กข้อมูล 24 รายการเป็น tuple แล้วคืนกลับเป็น list
def _kill_rows(kills: list[dict], rid_of, known_ids: set[int] | None = None) -> list[tuple]:
    return [
        (rid_of(k), int(k["tick"]), _known_player_id(k.get("attacker_id"), known_ids),
         _known_player_id(k.get("victim_id"), known_ids), _known_player_id(k.get("assister_id"), known_ids),
         k.get("attacker_side"), k.get("victim_side"), k.get("weapon", "unknown"),
         bool(k.get("headshot", False)), k.get("hitgroup"),
         bool(k.get("attacker_blind", False)), bool(k.get("thru_smoke", False)),
         bool(k.get("noscope", False)), bool(k.get("assisted_flash", False)), int(k.get("penetrated", 0)),
         _float(k.get("distance")), _float(k.get("attacker_x")), _float(k.get("attacker_y")), _float(k.get("attacker_z")),
         k.get("attacker_place"), _float(k.get("victim_x")), _float(k.get("victim_y")), _float(k.get("victim_z")),
         k.get("victim_place"))
        for k in kills if rid_of(k) and _known_player_id(k.get("victim_id"), known_ids) is not None
    ]

# คัดกรองและแปลงข้อมูลการทำดาเมจให้พร้อมลงตาราง damages (7 คอลัมน์) #คนโดนยิงห้ามปล่อยว่าง
# 1. รับรายการดาเมจ ฟังก์ชันหารหัสรอบ และชุดผู้เล่นที่ยืนยันแล้ว -> 2. กรองทิ้งแถวที่ไม่มีรหัสรอบหรือคนโดนยิงไม่มีตัวตน -> 3. แพ็กข้อมูล 7 รายการเป็น tuple แล้วคืนกลับเป็น list
def _damage_rows(damages: list[dict], rid_of, known_ids: set[int] | None = None) -> list[tuple]:
    return [
        (rid_of(d), int(d["tick"]), _known_player_id(d.get("attacker_id"), known_ids),
         _known_player_id(d.get("victim_id"), known_ids),
         d.get("weapon"), int(d.get("damage", 0)), d.get("hitgroup"))
        for d in damages if rid_of(d) and _known_player_id(d.get("victim_id"), known_ids) is not None
    ]

# แปลงสถิติสรุปรายบุคคลประจำรอบให้พร้อมลงตาราง player_rounds (20 คอลัมน์)
# 1. รับผลการคำนวณฟีเจอร์ แผนที่รหัสรอบ และชุดผู้เล่นที่ยืนยันแล้ว -> 2. กรองเฉพาะรอบที่มีอยู่ใน DB และผู้เล่นมีตัวตนจริง -> 3. ดึงสถิติ 20 รายการแพ็กเป็น tuple แล้วคืนกลับเป็น list
def _player_round_rows(feats, round_id_map: dict[int, int], known_ids: set[int] | None = None) -> list[tuple]:
    return [
        (round_id_map[f.round_num], f.steam_id, f.side, f.equip_value, f.balance, f.survived,
         f.buy_type, f.kills, f.deaths, f.assists, f.headshots, f.damage,
         f.opening_kill, f.opening_death, f.trade_kills, f.was_traded, f.clutch_vs, f.clutch_won, f.kast,
         f.features_version)
        for f in feats if f.round_num in round_id_map and _known_player_id(f.steam_id, known_ids) is not None
    ]

# จัดการรายชื่อผู้เล่น สังกัดทีม และฝั่งที่เริ่มเล่นตอนเปิดแมตช์
# 1. วิเคราะห์หาชื่อทีมถาวรของแต่ละคน -> 2. จัดเรียงฟีเจอร์ตามเลขรอบเพื่อจับว่าใครเริ่มเล่นฝั่งไหนในรอบแรกสุด -> 3. นับจำนวนรอบที่ลงเล่น -> 4. กรองเฉพาะคนที่มีตัวตนแล้วแพ็กส่งออกเป็น tuple
def _match_player_rows(feats, doc: dict, match_id: int, known_ids: set[int] | None = None) -> list[tuple]:
    """ใครเล่นในแมตช์นี้ + อยู่ทีมไหน (ชื่อทีมคงที่ทั้งแมตช์ ไม่ใช่ side ที่สลับกันทุกครึ่ง)

    start_side มาจากรอบแรกสุดที่คนนั้นลงเล่น จึงต้องไล่ feats ตามลำดับ round_num
    """
    team_of = assign_teams([{"steam_id": x["steam_id"], "round_num": x["round_num"], "side": x["side"],
                             "clan": x.get("team_clan")} for x in doc.get("player_rounds", [])])
    played: dict[int, dict] = {}
    for f in sorted(feats, key=lambda f: f.round_num):
        entry = played.setdefault(f.steam_id, {"start_side": f.side, "rounds": 0})
        entry["rounds"] += 1
    return [(match_id, sid, e["start_side"], e["rounds"], team_of.get(sid))
            for sid, e in played.items() if _known_player_id(sid, known_ids) is not None]

# คัดกรองและแพ็กข้อมูลการปาระเบิดลงตาราง grenades (12 คอลัมน์)
# 1. ตรวจสอบว่าระเบิดลูกนั้นผูกกับรหัสรอบใน DB ได้ (rid_of) -> 2. กรองพิกัด เวลา และประเภทระเบิด -> 3. แปลง trajectory เป็น JSON string -> 4. คืนค่าเป็น list[tuple]
def _grenade_rows(grenades: list[dict], rid_of, known_ids: set[int] | None = None) -> list[tuple]:
    return [
        (rid_of(g), int(g["tick"]), _known_player_id(g.get("thrower_id"), known_ids), g.get("side"), g["type"],
         _float(g.get("throw_x")), _float(g.get("throw_y")), _float(g.get("land_x")), _float(g.get("land_y")),
         _int(g.get("land_tick")), _int(g.get("end_tick")),
         json.dumps(g["trajectory"], separators=(",", ":")) if g.get("trajectory") else None)
        for g in grenades if rid_of(g)
    ]

# แพ็กพิกัดรอยเท้าผู้เล่นความถี่ 8 Hz ลงตาราง player_positions (18 คอลัมน์)
# 1. กรองเฉพาะรอบที่มีอยู่ใน DB และผู้เล่นยืนยันตัวตนแล้ว -> 2. ดึงสถานะผู้เล่น 18 รายการ (พิกัด, เลือด, อาวุธ, มุมหันหน้า) -> 3. ลบแถวที่ซ้ำซ้อนออก (Deduplication) แล้วคืนค่า
def _position_rows(positions: list[dict], match_id: int, round_id_map: dict[int, int],
                   known_ids: set[int] | None = None) -> list[tuple]:
    rows = [
        (match_id, int(p["round_num"]), int(p["tick"]), _known_player_id(p.get("steam_id"), known_ids), p.get("side"),
         float(p["x"]), float(p["y"]), _float(p.get("z")), _int(p.get("health")), p.get("place"),
         p.get("active_weapon"), _int(p.get("armor")),
         bool(p["has_helmet"]) if p.get("has_helmet") is not None else None,
         bool(p["has_defuser"]) if p.get("has_defuser") is not None else None,
         _int(p.get("money")), bool(p["has_bomb"]) if p.get("has_bomb") is not None else None,
         _float(p.get("yaw")), _float(p.get("flash_remaining")))
        for p in positions if int(p.get("round_num", 0)) in round_id_map
        and _known_player_id(p.get("steam_id"), known_ids) is not None
    ]
    return list(dict.fromkeys(rows))

# ล้างตารางแมทซ์ที่อัพลงไม่เสร็จทิ้ง แล้วลงใหม่
# 1. DELETE ข้อมูลเก่าในตาราง rounds, match_players, player_positions -> 2. INSERT ตาราง rounds เพื่อเอาสมุดแผนที่ round_id_map -> 3. สร้างฟังก์ชัน rid_of เพื่อแปลงเลขรอบ -> 4. คำนวณฟีเจอร์สถิติ (feats) -> 5. เทข้อมูลลงตารางลูกทั้ง 6 ตารางที่เหลือผ่าน _insert_many พร้อมคืนค่าสรุปจำนวนแถว
async def _replace_children(conn, match_id: int, doc: dict, known_ids: set[int]) -> dict:
    """ลบลูก ๆ เดิมของแมตช์แล้วใส่ใหม่ทั้งชุด — ต้องเรียกภายใน conn.transaction()"""
    await conn.execute("DELETE FROM rounds WHERE match_id = $1;", match_id)            # cascade ไปทุกตารางลูก
    await conn.execute("DELETE FROM match_players WHERE match_id = $1;", match_id)     # สองตารางนี้ผูกกับ match ตรง ๆ
    await conn.execute("DELETE FROM player_positions WHERE match_id = $1;", match_id)

    round_id_map = await _insert_rounds(conn, match_id, doc.get("rounds", []))

    def rid_of(row) -> int | None:
        return round_id_map.get(int(row.get("round_num", 1)))
    # แปลงเลขรอบในเกม ให้กลายเป็น ID ประจำรอบในฐานข้อมูล
    feats = compute_features(doc)

    return {
        "rounds": len(round_id_map),
        "kills": await _insert_many(conn, SQL_KILLS, _kill_rows(doc.get("kills", []), rid_of, known_ids)),
        "damages": await _insert_many(conn, SQL_DAMAGES, _damage_rows(doc.get("damages", []), rid_of, known_ids)),
        "player_rounds": await _insert_many(conn, SQL_PLAYER_ROUNDS, _player_round_rows(feats, round_id_map, known_ids)),
        "match_players": await _insert_many(conn, SQL_MATCH_PLAYERS, _match_player_rows(feats, doc, match_id, known_ids)),
        "grenades": await _insert_many(conn, SQL_GRENADES, _grenade_rows(doc.get("grenades", []), rid_of, known_ids)),
        "positions": await _insert_many(conn, SQL_POSITIONS,
                                         _position_rows(doc.get("positions", []), match_id, round_id_map, known_ids)),
    }

# ทางเข้าหลักของ ETL ในการบันทึกข้อมูลแมตช์ทั้งก้อนลงฐานข้อมูล
# 1. ตรวจสอบชื่อไฟล์เดโมและข้อมูล -> 2. จัดการหาหรือสร้าง match_id ในตาราง matches -> 3. เปิด Transaction คลุม -> 4. ลงทะเบียนผู้เล่นหลักและผู้เล่นที่ถูกอ้างอิง -> 5. สั่ง _replace_children เทข้อมูลตารางลูกทั้งหมด -> 6. คืนค่า match_id
async def load_match_doc(conn, doc: dict, *, match_id: int | None = None, force: bool = False) -> int:
    """เอา dict จาก parser เข้าฐานข้อมูล คืน matches.id

    match_id ให้มา  = แถว matches มีอยู่แล้ว (worker สร้างไว้ตอนอัปโหลด) -> เติมข้อมูลแมตช์ลงแถวนั้น
    match_id ไม่ให้ = หาจาก demo_file: เคยมี -> ข้าม (หรือทับถ้า force) / ไม่เคยมี -> สร้างแถวใหม่
    """

    # หยิบข้อมูลหมวดหมู่่่ที่ทำไว้
    info = doc.get("match", {})
    demo_file = info.get("demo_file")

    # ถ้าไม่มีชื่อไฟล์ให้หยุด
    if not demo_file:
        raise ValueError("doc ไม่มี match.demo_file")
    # รวบรวมข้อมูลเพื่อส่งเข้า sql   
    meta = (info.get("map_name", "unknown"), int(info.get("tickrate", 128)), info.get("team_a"), info.get("team_b"))
    
    # ทำงานต่อเมื่อคนเรียกไม่ได้ส่ง match_id มา
    if match_id is None:
        existing = await conn.fetchrow("SELECT id FROM matches WHERE demo_file = $1;", demo_file)
        if existing and not force:
            print(f"[SKIP] แมตช์ {demo_file} มีอยู่ในระบบแล้ว (ID: {existing['id']})")
            return existing["id"]
        match_id = existing["id"] if existing else None
        if existing:
            print(f"[REPLACE] โหลด {demo_file} ทับของเดิม (ID: {match_id})")
    
    # ลงทะเบียนผู้เล่น
    async with conn.transaction():
        # หยิบ players จาก doc แล้วให้ _upsert_players บันทึกลงตาราง players
        await _upsert_players(conn, doc.get("players", []))
        # ถ้าไม่มี match_id ให้สร้างแถวใหม่
        if match_id is None:
            match_id = await conn.fetchval("""
                INSERT INTO matches (demo_file, map_name, tickrate, team_a, team_b, status, uploader_type)
                VALUES ($1, $2, $3, $4, $5, 'done', 'legacy') RETURNING id;
            """, demo_file, *meta)
        else:
            # เติมชื่อไฟล์ แผนที่ tickrate และชื่อทีมจาก doc
            await conn.execute("""
                UPDATE matches SET demo_file = $2, map_name = $3, tickrate = $4, team_a = $5, team_b = $6
                WHERE id = $1;
            """, match_id, demo_file, *meta)

        # เขาไปดู idผู้เล่น ในเหตุการณ์ต่างๆใน doc เผื่อมีการตกหล่น   
        known_ids = await _upsert_referenced_players(conn, doc)
        # เขียนตารางรายละเอียด เช่น รอบ คิล ดาเมจ
        counts = await _replace_children(conn, match_id, doc, known_ids)

    print(f"[SUCCESS] โหลดแมตช์ {demo_file} สำเร็จ (Match ID: {match_id}, " +
          ", ".join(f"{k}: {v}" for k, v in counts.items()) + ")")
    return match_id

# สะพานเชื่อมสำหรับอ่านข้อมูลจากไฟล์ .json บนดิสก์แล้วส่งต่อให้ load_match_doc สำหรับDev
# 1. เปิดและอ่านไฟล์ JSON เข้าสู่หน่วยความจำ -> 2. ตรวจสอบ/เติมชื่อไฟล์ .dem กลับเข้าไปหากไม่มี -> 3. ส่งต่อให้ load_match_doc ทำการบันทึกลงฐานข้อมูล
async def load_match_json(conn, json_path: Path, force: bool = False) -> int:
    """แบบเดิม: อ่านจากไฟล์ JSON ที่ parser เขียนไว้"""
    with open(json_path, encoding="utf-8") as f:
        doc = json.load(f)
    doc.setdefault("match", {}).setdefault("demo_file", json_path.stem + ".dem")
    return await load_match_doc(conn, doc, force=force)

# ติดป้ายกำกับแมตช์ระดับโปร/ชุดอ้างอิงสำหรับเทรนโมเดล โดยอิงจากไฟล์ .dem ในโฟลเดอร์ที่ระบุ
# 1. สแกนหาชื่อไฟล์ .dem ทั้งหมดในโฟลเดอร์ -> 2. สั่ง SQL UPDATE ฟิลด์ source = 'reference' เฉพาะแมตช์ที่มีชื่อไฟล์ตรงกัน -> 3. สรุปยอดแมตช์ที่ติดป้ายสำเร็จและแจ้งเตือนไฟล์ที่ยังไม่ได้โหลดเข้า DB
async def mark_reference(conn, folder: Path) -> int:
    """ทำเครื่องหมายว่าแมตช์ไหนคือ "ชุดอ้างอิงที่ใช้เทรนโมเดล" — ดูจากไฟล์ .dem ที่อยู่ในโฟลเดอร์นั้นจริง ๆ

    เดโมของผู้ใช้อยู่คนละโฟลเดอร์ (demos/uploads/) จึงไม่มีทางถูกทำเครื่องหมายเป็นชุดอ้างอิงโดยบังเอิญ
    รันซ้ำได้ และไม่เปลี่ยน source ของแมตช์อื่น เพราะเดโมอ้างอิงที่ archive แล้วอาจไม่มีไฟล์ต้นทางในเครื่อง
    """
    names = sorted(p.name for p in folder.rglob("*.dem"))
    if not names:
        print(f"ไม่พบไฟล์ .dem ใน {folder} — ไม่ได้ทำเครื่องหมายอะไร")
        return 0
    rows = await conn.fetch("""
        UPDATE matches SET source = 'reference' WHERE demo_file = ANY($1::text[])
        RETURNING demo_file, source;
    """, names)
    ref = sum(1 for r in rows if r["source"] == "reference")
    missing = sorted(set(names) - {r["demo_file"] for r in rows})
    print(f"[SOURCE] ทำเครื่องหมายชุดอ้างอิง {ref} แมตช์ (จาก {len(names)} ไฟล์ใน {folder})")
    if missing:
        print(f"[SOURCE] ไฟล์ที่ยังไม่ได้โหลดเข้าฐานข้อมูล {len(missing)} ไฟล์: {', '.join(missing[:3])}…")
    return ref

# แก้ไขบั๊กไซต์วางระเบิด (bomb_site) ในตาราง rounds ย้อนหลังทั้งหมด
# 1. ดึงพิกัดวางระเบิด (X, Y) และชื่อแผนที่จากทุกรอบใน DB -> 2. ส่งพิกัดให้สูตร site_of ตัดสินใหม่ว่าเป็นไซต์ A, B หรือไม่มีการวาง (NULL) -> 3. สั่ง UPDATE ข้อมูลที่ถูกต้องกลับลงตาราง rounds รวดเดียวด้วย executemany -> 4. สรุปยอดและพิมพ์รายงานจำนวนรอบที่แก้ไขสำเร็จ
async def fix_bomb_sites(conn) -> int:
    """แก้ rounds.bomb_site ของแถวที่โหลดไว้แล้ว — awpy เคยส่ง 'bombsite_b' มาทุกแถวซึ่งผิด

    ตัดสินใหม่จากพิกัดจุดวางบอมบ์ด้วยสูตรเดียวกับ parser (backend/services/review.py site_of)
    รันซ้ำได้ · รอบที่ไม่มีพิกัด (ไม่ได้วางบอมบ์) จะถูกตั้งเป็น NULL ไม่ใช่เดาให้
    """
    from backend.services.review import site_of

    rows = await conn.fetch("""
        SELECT r.id, m.map_name, r.bomb_plant_x, r.bomb_plant_y
        FROM rounds r JOIN matches m ON m.id = r.match_id
    """)
    updates = [(r["id"], site_of(r["bomb_plant_x"], r["bomb_plant_y"], r["map_name"] or "")) for r in rows]
    await conn.executemany("UPDATE rounds SET bomb_site = $2 WHERE id = $1", updates)
    named = sum(1 for _, s in updates if s)
    by_site: dict[str, int] = {}
    for _, s in updates:
        if s:
            by_site[s] = by_site.get(s, 0) + 1
    print(f"[SITE] ตั้งไซต์ให้ {named} รอบจากทั้งหมด {len(updates)} รอบ — " +
          " · ".join(f"{k} {v}" for k, v in sorted(by_site.items())))
    return named

# จุดสตาร์ทรวมคำสั่ง CLI หลังบ้าน ควบคุมว่าจะโหลดข้อมูล, ปั๊มตราแมตช์โปร หรือซ่อมไซต์บอมบ์
# 1. ตั้งค่าและรับคำสั่งจาก Terminal (argparse) -> 2. ต่อ Database (asyncpg) และอัปเดตวิว (apply_schema) -> 3. เช็กคำสั่งพิเศษ (--mark-reference หรือ --fix-bomb-sites ถ้าสั่งมาให้ทำแล้วปิดงานทันที) -> 4. ถ้าไม่มีคำสั่งพิเศษ ให้โหลดไฟล์ JSON เข้า DB ทีละไฟล์หรือทั้งโฟลเดอร์ -> 5. ปิดการเชื่อมต่อ DB
async def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description="ETL JSON -> PostgreSQL")
    parser.add_argument("path", nargs="?", default="output/json", help="ไฟล์ JSON หรือโฟลเดอร์")
    parser.add_argument("--force", action="store_true", help="เขียนทับข้อมูลเดิม")
    parser.add_argument("--mark-reference", nargs="?", const="demos/reference", metavar="FOLDER",
                        help="ทำเครื่องหมายแมตช์ในโฟลเดอร์นี้เป็นชุดอ้างอิง (ที่เหลือเป็นของผู้ใช้) แล้วจบ")
    parser.add_argument("--fix-bomb-sites", action="store_true",
                        help="คำนวณ rounds.bomb_site ใหม่จากพิกัดจุดวางบอมบ์ แล้วจบ")
    args = parser.parse_args()

    conn = await asyncpg.connect(DB_URL)
    await apply_schema(conn)          # view ต้องตรงรุ่นกับตาราง (ตารางเอง: alembic upgrade head)

    if args.mark_reference:
        await mark_reference(conn, Path(args.mark_reference))
        await conn.close()
        return

    if args.fix_bomb_sites:
        await fix_bomb_sites(conn)
        await conn.close()
        return

    target = Path(args.path)
    if target.is_file():
        await load_match_json(conn, target, force=args.force)
    elif target.is_dir():
        files = sorted(target.glob("*.json"))
        if not files:
            print(f"ไม่พบไฟล์ JSON ในโฟลเดอร์ {target}")
        for jf in files:
            await load_match_json(conn, jf, force=args.force)
    else:
        print(f"ไม่พบ path: {target}")
    # Bulk inserts can leave PostgreSQL without representative planner stats.
    # Refresh only the tables written by this loader after the batch completes.
    await conn.execute("""
        ANALYZE matches, match_players, rounds, kills, damages,
                player_rounds, player_positions, grenades
    """)
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
