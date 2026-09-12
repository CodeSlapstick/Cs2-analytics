# -*- coding: utf-8 -*-
"""
backend/etl_loader.py — เอาผลจาก parser (dict/JSON ที่ normalize แล้ว) ใส่ PostgreSQL

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

ฟีเจอร์ (opening / trade / buy type / clutch / KAST) คำนวณที่นี่ด้วย backend/features.py
แล้วเก็บลง player_rounds — คำนวณครั้งเดียวตอนโหลด ไม่ต้องคิดใหม่ทุกครั้งที่หน้าเว็บถาม
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))      # ให้รัน python backend/etl_loader.py จากรากโปรเจกต์ได้

from backend.db import DATABASE_URL as DB_URL  # noqa: E402  (โหลด .env ตอน import)
from backend.db import apply_schema  # noqa: E402
from backend.features import assign_teams, compute_features  # noqa: E402


def _int(v):
    return int(v) if v not in (None, "") else None


def _float(v):
    return float(v) if v is not None else None


async def _upsert_players(conn, players: list[dict]) -> None:
    if players:
        await conn.executemany("""
            INSERT INTO players (steam_id, name) VALUES ($1, $2)
            ON CONFLICT (steam_id) DO UPDATE SET name = EXCLUDED.name;
        """, [(int(p["steam_id"]), str(p["name"])) for p in players])


# SQL ของตารางลูกแต่ละตัว — วางไว้ระดับโมดูลเพื่อให้ฟังก์ชันสร้างแถวอ่านสั้นลง
SQL_KILLS = """
    INSERT INTO kills (
        round_id, tick, attacker_id, victim_id, assister_id, attacker_side, victim_side, weapon,
        headshot, hitgroup, attacker_blind, thru_smoke, noscope, assisted_flash, penetrated,
        distance, attacker_x, attacker_y, attacker_z, attacker_place, victim_x, victim_y, victim_z, victim_place
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
              $16, $17, $18, $19, $20, $21, $22, $23, $24);
"""
SQL_DAMAGES = """
    INSERT INTO damages (round_id, tick, attacker_id, victim_id, weapon, damage, hitgroup)
    VALUES ($1, $2, $3, $4, $5, $6, $7);
"""
SQL_PLAYER_ROUNDS = """
    INSERT INTO player_rounds (
        round_id, steam_id, side, equip_value, balance, survived,
        buy_type, kills, deaths, assists, headshots, damage,
        opening_kill, opening_death, trade_kills, was_traded, clutch_vs, clutch_won, kast, features_version
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
    ON CONFLICT (round_id, steam_id) DO NOTHING;
"""
SQL_MATCH_PLAYERS = """
    INSERT INTO match_players (match_id, steam_id, start_side, rounds, team_clan) VALUES ($1, $2, $3, $4, $5)
    ON CONFLICT (match_id, steam_id) DO NOTHING;
"""
SQL_GRENADES = """
    INSERT INTO grenades (round_id, tick, thrower_id, side, type,
                          throw_x, throw_y, land_x, land_y, land_tick, end_tick)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11);
"""
SQL_POSITIONS = """
    INSERT INTO player_positions (match_id, round_num, tick, steam_id, side, x, y, z, health, place)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10);
"""


async def _insert_many(conn, sql: str, rows: list[tuple]) -> int:
    """executemany ที่ข้ามให้เองเมื่อไม่มีแถว คืนจำนวนแถวที่ใส่ (ไว้ทำสรุปท้ายฟังก์ชัน)"""
    if rows:
        await conn.executemany(sql, rows)
    return len(rows)


async def _insert_rounds(conn, match_id: int, rounds: list[dict]) -> dict[int, int]:
    """ใส่ตารางรอบทีละแถวเพื่อเก็บ id ที่ DB คืนมา คืน map round_num -> rounds.id"""
    round_id_map: dict[int, int] = {}
    for r in rounds:
        rid = await conn.fetchval("""
            INSERT INTO rounds (match_id, round_num, start_tick, bomb_plant_tick, winner_side, end_reason,
                                bomb_plant_x, bomb_plant_y, bomb_site)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id;
        """, match_id, int(r["round_num"]), _int(r.get("start_tick")), _int(r.get("bomb_plant_tick")),
           r.get("winner_side"), r.get("end_reason"),
           _float(r.get("bomb_plant_x")), _float(r.get("bomb_plant_y")), r.get("bomb_site"))
        round_id_map[int(r["round_num"])] = rid
    return round_id_map


def _kill_rows(kills: list[dict], rid_of) -> list[tuple]:
    return [
        (rid_of(k), int(k["tick"]), _int(k.get("attacker_id")), int(k["victim_id"]), _int(k.get("assister_id")),
         k.get("attacker_side"), k.get("victim_side"), k.get("weapon", "unknown"),
         bool(k.get("headshot", False)), k.get("hitgroup"),
         bool(k.get("attacker_blind", False)), bool(k.get("thru_smoke", False)),
         bool(k.get("noscope", False)), bool(k.get("assisted_flash", False)), int(k.get("penetrated", 0)),
         _float(k.get("distance")), _float(k.get("attacker_x")), _float(k.get("attacker_y")), _float(k.get("attacker_z")),
         k.get("attacker_place"), _float(k.get("victim_x")), _float(k.get("victim_y")), _float(k.get("victim_z")),
         k.get("victim_place"))
        for k in kills if rid_of(k)
    ]


def _damage_rows(damages: list[dict], rid_of) -> list[tuple]:
    return [
        (rid_of(d), int(d["tick"]), _int(d.get("attacker_id")), int(d["victim_id"]),
         d.get("weapon"), int(d.get("damage", 0)), d.get("hitgroup"))
        for d in damages if rid_of(d)
    ]


def _player_round_rows(feats, round_id_map: dict[int, int]) -> list[tuple]:
    return [
        (round_id_map[f.round_num], f.steam_id, f.side, f.equip_value, f.balance, f.survived,
         f.buy_type, f.kills, f.deaths, f.assists, f.headshots, f.damage,
         f.opening_kill, f.opening_death, f.trade_kills, f.was_traded, f.clutch_vs, f.clutch_won, f.kast,
         f.features_version)
        for f in feats if f.round_num in round_id_map
    ]


def _match_player_rows(feats, doc: dict, match_id: int) -> list[tuple]:
    """ใครเล่นในแมตช์นี้ + อยู่ทีมไหน (ชื่อทีมคงที่ทั้งแมตช์ ไม่ใช่ side ที่สลับกันทุกครึ่ง)

    start_side มาจากรอบแรกสุดที่คนนั้นลงเล่น จึงต้องไล่ feats ตามลำดับ round_num
    """
    team_of = assign_teams([{"steam_id": x["steam_id"], "round_num": x["round_num"], "side": x["side"],
                             "clan": x.get("team_clan")} for x in doc.get("player_rounds", [])])
    played: dict[int, dict] = {}
    for f in sorted(feats, key=lambda f: f.round_num):
        entry = played.setdefault(f.steam_id, {"start_side": f.side, "rounds": 0})
        entry["rounds"] += 1
    return [(match_id, sid, e["start_side"], e["rounds"], team_of.get(sid)) for sid, e in played.items()]


def _grenade_rows(grenades: list[dict], rid_of) -> list[tuple]:
    return [
        (rid_of(g), int(g["tick"]), _int(g.get("thrower_id")), g.get("side"), g["type"],
         _float(g.get("throw_x")), _float(g.get("throw_y")), _float(g.get("land_x")), _float(g.get("land_y")),
         _int(g.get("land_tick")), _int(g.get("end_tick")))
        for g in grenades if rid_of(g)
    ]


def _position_rows(positions: list[dict], match_id: int, round_id_map: dict[int, int]) -> list[tuple]:
    return [
        (match_id, int(p["round_num"]), int(p["tick"]), int(p["steam_id"]), p.get("side"),
         float(p["x"]), float(p["y"]), _float(p.get("z")), _int(p.get("health")), p.get("place"))
        for p in positions if int(p.get("round_num", 0)) in round_id_map
    ]


async def _replace_children(conn, match_id: int, doc: dict) -> dict:
    """ลบลูก ๆ เดิมของแมตช์แล้วใส่ใหม่ทั้งชุด — ต้องเรียกภายใน conn.transaction()"""
    await conn.execute("DELETE FROM rounds WHERE match_id = $1;", match_id)            # cascade ไปทุกตารางลูก
    await conn.execute("DELETE FROM match_players WHERE match_id = $1;", match_id)     # สองตารางนี้ผูกกับ match ตรง ๆ
    await conn.execute("DELETE FROM player_positions WHERE match_id = $1;", match_id)

    round_id_map = await _insert_rounds(conn, match_id, doc.get("rounds", []))

    def rid_of(row) -> int | None:
        return round_id_map.get(int(row.get("round_num", 1)))

    # ผู้เล่นรายรอบ + ฟีเจอร์ — compute_features คืนหนึ่งแถวต่อคนต่อรอบจาก doc["player_rounds"]
    feats = compute_features(doc)

    return {
        "rounds": len(round_id_map),
        "kills": await _insert_many(conn, SQL_KILLS, _kill_rows(doc.get("kills", []), rid_of)),
        "damages": await _insert_many(conn, SQL_DAMAGES, _damage_rows(doc.get("damages", []), rid_of)),
        "player_rounds": await _insert_many(conn, SQL_PLAYER_ROUNDS, _player_round_rows(feats, round_id_map)),
        "match_players": await _insert_many(conn, SQL_MATCH_PLAYERS, _match_player_rows(feats, doc, match_id)),
        # grenades / positions มีเฉพาะ schema_version >= 3 และ >= 4 — ไฟล์เก่าจะได้ list ว่างแล้วข้ามไปเอง
        "grenades": await _insert_many(conn, SQL_GRENADES, _grenade_rows(doc.get("grenades", []), rid_of)),
        "positions": await _insert_many(conn, SQL_POSITIONS, _position_rows(doc.get("positions", []), match_id, round_id_map)),
    }


async def load_match_doc(conn, doc: dict, *, match_id: int | None = None, force: bool = False) -> int:
    """เอา dict จาก parser เข้าฐานข้อมูล คืน matches.id

    match_id ให้มา  = แถว matches มีอยู่แล้ว (worker สร้างไว้ตอนอัปโหลด) -> เติมข้อมูลแมตช์ลงแถวนั้น
    match_id ไม่ให้ = หาจาก demo_file: เคยมี -> ข้าม (หรือทับถ้า force) / ไม่เคยมี -> สร้างแถวใหม่
    """
    info = doc.get("match", {})
    demo_file = info.get("demo_file")
    if not demo_file:
        raise ValueError("doc ไม่มี match.demo_file")
    meta = (info.get("map_name", "unknown"), int(info.get("tickrate", 128)), info.get("team_a"), info.get("team_b"))

    if match_id is None:
        existing = await conn.fetchrow("SELECT id FROM matches WHERE demo_file = $1;", demo_file)
        if existing and not force:
            print(f"[SKIP] แมตช์ {demo_file} มีอยู่ในระบบแล้ว (ID: {existing['id']})")
            return existing["id"]
        match_id = existing["id"] if existing else None
        if existing:
            print(f"[REPLACE] โหลด {demo_file} ทับของเดิม (ID: {match_id})")

    async with conn.transaction():
        await _upsert_players(conn, doc.get("players", []))
        if match_id is None:
            match_id = await conn.fetchval("""
                INSERT INTO matches (demo_file, map_name, tickrate, team_a, team_b, status)
                VALUES ($1, $2, $3, $4, $5, 'done') RETURNING id;
            """, demo_file, *meta)
        else:
            await conn.execute("""
                UPDATE matches SET demo_file = $2, map_name = $3, tickrate = $4, team_a = $5, team_b = $6
                WHERE id = $1;
            """, match_id, demo_file, *meta)
        counts = await _replace_children(conn, match_id, doc)

    print(f"[SUCCESS] โหลดแมตช์ {demo_file} สำเร็จ (Match ID: {match_id}, " +
          ", ".join(f"{k}: {v}" for k, v in counts.items()) + ")")
    return match_id


async def load_match_json(conn, json_path: Path, force: bool = False) -> int:
    """แบบเดิม: อ่านจากไฟล์ JSON ที่ parser เขียนไว้"""
    with open(json_path, encoding="utf-8") as f:
        doc = json.load(f)
    doc.setdefault("match", {}).setdefault("demo_file", json_path.stem + ".dem")
    return await load_match_doc(conn, doc, force=force)


async def main() -> None:
    parser = argparse.ArgumentParser(description="ETL JSON -> PostgreSQL")
    parser.add_argument("path", nargs="?", default="output/json", help="ไฟล์ JSON หรือโฟลเดอร์")
    parser.add_argument("--force", action="store_true", help="เขียนทับข้อมูลเดิม")
    args = parser.parse_args()

    conn = await asyncpg.connect(DB_URL)
    await apply_schema(conn)          # view ต้องตรงรุ่นกับตาราง (ตารางเอง: alembic upgrade head)

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
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
