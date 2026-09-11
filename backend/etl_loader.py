# -*- coding: utf-8 -*-
"""
backend/etl_loader.py — เอาผลจาก parser (dict/JSON ที่ normalize แล้ว) ใส่ PostgreSQL

    python backend/etl_loader.py                      # โหลดทุกไฟล์ใน output/json (ข้ามที่เคยโหลด)
    python backend/etl_loader.py output/json/X.json   # ไฟล์เดียว
    python backend/etl_loader.py --force              # โหลดทับของเดิม

    จากโค้ดอื่น:
        from backend.etl_loader import load_match_doc, load_match_json
        match_id = await load_match_doc(conn, doc, match_id=42)      # worker: แถว matches มีอยู่แล้ว (status=queued)
        match_id = await load_match_json(conn, Path("x.json"))       # CLI: ให้หาเอาว่าเคยโหลดไหม

idempotent ด้วยวิธีเดียว
    ก่อน INSERT ลูก ๆ ของแมตช์ (rounds -> kills/damages/player_rounds/grenades) จะ DELETE rounds ของแมตช์นั้นทิ้งก่อนเสมอ
    (ตารางลูกทั้งหมด ON DELETE CASCADE จาก rounds) แล้วค่อยใส่ใหม่ในทรานแซกชันเดียว
    รันซ้ำแมตช์เดิมกี่ครั้งจึงได้ข้อมูลชุดเดียว และ matches.id ไม่เปลี่ยน (หน้าเว็บที่ poll อยู่ไม่หลุด)
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


async def _replace_children(conn, match_id: int, doc: dict) -> dict:
    """ลบลูก ๆ เดิมของแมตช์แล้วใส่ใหม่ทั้งชุด — ต้องเรียกภายใน conn.transaction()"""
    rounds = doc.get("rounds", [])
    kills = doc.get("kills", [])
    damages = doc.get("damages", [])
    player_rounds = doc.get("player_rounds", [])   # schema_version >= 3
    grenades = doc.get("grenades", [])             # schema_version >= 3

    await conn.execute("DELETE FROM rounds WHERE match_id = $1;", match_id)   # cascade ไปทุกตารางลูก

    round_id_map: dict[int, int] = {}
    for r in rounds:
        rid = await conn.fetchval("""
            INSERT INTO rounds (match_id, round_num, start_tick, bomb_plant_tick, winner_side, end_reason)
            VALUES ($1, $2, $3, $4, $5, $6) RETURNING id;
        """, match_id, int(r["round_num"]), _int(r.get("start_tick")), _int(r.get("bomb_plant_tick")),
           r.get("winner_side"), r.get("end_reason"))
        round_id_map[int(r["round_num"])] = rid

    def rid_of(row) -> int | None:
        return round_id_map.get(int(row.get("round_num", 1)))

    kill_rows = [
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
    if kill_rows:
        await conn.executemany("""
            INSERT INTO kills (
                round_id, tick, attacker_id, victim_id, assister_id, attacker_side, victim_side, weapon,
                headshot, hitgroup, attacker_blind, thru_smoke, noscope, assisted_flash, penetrated,
                distance, attacker_x, attacker_y, attacker_z, attacker_place, victim_x, victim_y, victim_z, victim_place
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                      $16, $17, $18, $19, $20, $21, $22, $23, $24);
        """, kill_rows)

    dmg_rows = [
        (rid_of(d), int(d["tick"]), _int(d.get("attacker_id")), int(d["victim_id"]),
         d.get("weapon"), int(d.get("damage", 0)), d.get("hitgroup"))
        for d in damages if rid_of(d)
    ]
    if dmg_rows:
        await conn.executemany("""
            INSERT INTO damages (round_id, tick, attacker_id, victim_id, weapon, damage, hitgroup)
            VALUES ($1, $2, $3, $4, $5, $6, $7);
        """, dmg_rows)

    pr_rows = [
        (rid_of(x), int(x["steam_id"]), x["side"], _int(x.get("equip_value")), _int(x.get("balance")),
         bool(x.get("survived", False)))
        for x in player_rounds if rid_of(x)
    ]
    if pr_rows:
        await conn.executemany("""
            INSERT INTO player_rounds (round_id, steam_id, side, equip_value, balance, survived)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (round_id, steam_id) DO NOTHING;
        """, pr_rows)

    g_rows = [
        (rid_of(g), int(g["tick"]), _int(g.get("thrower_id")), g.get("side"), g["type"])
        for g in grenades if rid_of(g)
    ]
    if g_rows:
        await conn.executemany("""
            INSERT INTO grenades (round_id, tick, thrower_id, side, type) VALUES ($1, $2, $3, $4, $5);
        """, g_rows)

    return {"rounds": len(round_id_map), "kills": len(kill_rows), "damages": len(dmg_rows),
            "player_rounds": len(pr_rows), "grenades": len(g_rows)}


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
