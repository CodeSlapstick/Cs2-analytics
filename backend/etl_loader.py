import argparse
import asyncio
import json
import os
from pathlib import Path
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cs2_analytics")

async def load_match_json(conn, json_path: Path, force: bool = False):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    match_info = data.get("match", {})
    players_data = data.get("players", [])
    rounds_data = data.get("rounds", [])
    kills_data = data.get("kills", [])
    damages_data = data.get("damages", [])
    player_rounds_data = data.get("player_rounds", [])   # schema_version >= 3
    grenades_data = data.get("grenades", [])              # schema_version >= 3

    demo_file = match_info.get("demo_file", json_path.stem + ".dem")

    # 1. เช็กความซ้ำซ้อน (Idempotency)
    existing_match = await conn.fetchrow("SELECT id FROM matches WHERE demo_file = $1;", demo_file)
    if existing_match:
        if not force:
            print(f"[SKIP] แมตช์ {demo_file} มีอยู่ในระบบแล้ว (ID: {existing_match['id']})")
            return existing_match['id']
        else:
            print(f"[REPLACE] ลบข้อมูลเดิมของ {demo_file} เพื่อโหลดใหม่...")
            await conn.execute("DELETE FROM matches WHERE id = $1;", existing_match['id'])

    async with conn.transaction():
        # 2. Insert Players (ON CONFLICT DO UPDATE)
        for p in players_data:
            await conn.execute("""
                INSERT INTO players (steam_id, name)
                VALUES ($1, $2)
                ON CONFLICT (steam_id) DO UPDATE SET name = EXCLUDED.name;
            """, int(p["steam_id"]), str(p["name"]))

        # 3. Insert Matches
        match_id = await conn.fetchval("""
            INSERT INTO matches (demo_file, map_name, tickrate, team_a, team_b)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id;
        """, demo_file, match_info.get("map_name", "unknown"), int(match_info.get("tickrate", 128)),
           match_info.get("team_a"), match_info.get("team_b"))

        # 4. Insert Rounds
        round_id_map = {}
        for r in rounds_data:
            round_num = int(r["round_num"])
            rid = await conn.fetchval("""
                INSERT INTO rounds (match_id, round_num, start_tick, bomb_plant_tick, winner_side, end_reason)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id;
            """, match_id, round_num, r.get("start_tick"), r.get("bomb_plant_tick"),
               r.get("winner_side"), r.get("end_reason"))
            round_id_map[round_num] = rid

        # 5. Insert Kills
        for k in kills_data:
            round_num = int(k["round_num"])
            rid = round_id_map.get(round_num)
            if not rid:
                continue

            await conn.execute("""
                INSERT INTO kills (
                    round_id, tick, attacker_id, victim_id, assister_id,
                    attacker_side, victim_side, weapon, headshot, hitgroup,
                    attacker_blind, thru_smoke, noscope, assisted_flash,
                    penetrated, distance, attacker_x, attacker_y, attacker_z,
                    attacker_place, victim_x, victim_y, victim_z, victim_place
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16, $17, $18, $19,
                    $20, $21, $22, $23, $24
                );
            """,
                rid, int(k["tick"]),
                int(k["attacker_id"]) if k.get("attacker_id") else None,
                int(k["victim_id"]),
                int(k["assister_id"]) if k.get("assister_id") else None,
                k.get("attacker_side"), k.get("victim_side"), k.get("weapon", "unknown"),
                bool(k.get("headshot", False)), k.get("hitgroup"),
                bool(k.get("attacker_blind", False)), bool(k.get("thru_smoke", False)),
                bool(k.get("noscope", False)), bool(k.get("assisted_flash", False)),
                int(k.get("penetrated", 0)),
                float(k["distance"]) if k.get("distance") is not None else None,
                float(k["attacker_x"]) if k.get("attacker_x") is not None else None,
                float(k["attacker_y"]) if k.get("attacker_y") is not None else None,
                float(k["attacker_z"]) if k.get("attacker_z") is not None else None,
                k.get("attacker_place"),
                float(k["victim_x"]) if k.get("victim_x") is not None else None,
                float(k["victim_y"]) if k.get("victim_y") is not None else None,
                float(k["victim_z"]) if k.get("victim_z") is not None else None,
                k.get("victim_place")
            )

        # 6. Insert Damages (ถ้ามีใน JSON)
        for d in damages_data:
            round_num = int(d.get("round_num", 1))
            rid = round_id_map.get(round_num)
            if not rid:
                continue
            await conn.execute("""
                INSERT INTO damages (round_id, tick, attacker_id, victim_id, weapon, damage, hitgroup)
                VALUES ($1, $2, $3, $4, $5, $6, $7);
            """, rid, int(d["tick"]), int(d["attacker_id"]) if d.get("attacker_id") else None,
               int(d["victim_id"]), d.get("weapon"), int(d.get("damage", 0)), d.get("hitgroup"))

        # 7. Insert player_rounds (ถ้ามีใน JSON — schema_version >= 3)
        #    executemany ยิงทีเดียวทั้งก้อน เร็วกว่า execute ทีละแถวหลายสิบเท่า
        pr_rows = [
            (round_id_map[int(x["round_num"])], int(x["steam_id"]), x["side"],
             x.get("equip_value"), x.get("balance"), bool(x.get("survived", False)))
            for x in player_rounds_data if int(x["round_num"]) in round_id_map
        ]
        if pr_rows:
            await conn.executemany("""
                INSERT INTO player_rounds (round_id, steam_id, side, equip_value, balance, survived)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (round_id, steam_id) DO NOTHING;
            """, pr_rows)

        # 8. Insert grenades (ถ้ามีใน JSON — schema_version >= 3)
        g_rows = [
            (round_id_map[int(g["round_num"])], int(g["tick"]),
             int(g["thrower_id"]) if g.get("thrower_id") else None, g.get("side"), g["type"])
            for g in grenades_data if int(g["round_num"]) in round_id_map
        ]
        if g_rows:
            await conn.executemany("""
                INSERT INTO grenades (round_id, tick, thrower_id, side, type)
                VALUES ($1, $2, $3, $4, $5);
            """, g_rows)

    print(f"[SUCCESS] โหลดแมตช์ {demo_file} สำเร็จ (Match ID: {match_id}, Rounds: {len(rounds_data)}, "
          f"Kills: {len(kills_data)}, Damages: {len(damages_data)}, PlayerRounds: {len(player_rounds_data)}, Grenades: {len(grenades_data)})")
    return match_id

async def main():
    parser = argparse.ArgumentParser(description="ETL JSON -> PostgreSQL")
    parser.add_argument("path", nargs="?", default="output/json", help="Path ไปยังไฟล์ JSON หรือโฟลเดอร์")
    parser.add_argument("--force", action="store_true", help="เขียนทับข้อมูลเดิม")
    args = parser.parse_args()

    conn = await asyncpg.connect(DB_URL)

    # สร้าง/อัปเดตตารางกับ view ตาม schema.sql ก่อนเสมอ — ปลอดภัยเพราะทุกคำสั่งเป็น IF NOT EXISTS
    # หรือ DROP+CREATE VIEW ที่ไม่แตะข้อมูล ถ้าไม่ทำตรงนี้ ตารางใหม่ (player_rounds, grenades) จะไม่มีให้ INSERT
    schema_sql = Path(__file__).resolve().parent / "schema.sql"
    await conn.execute(schema_sql.read_text(encoding="utf-8"))
    print(f"[SCHEMA] ใช้ {schema_sql.name} แล้ว")

    target = Path(args.path)

    if target.is_file():
        await load_match_json(conn, target, force=args.force)
    elif target.is_dir():
        json_files = list(target.glob("*.json"))
        if not json_files:
            print(f"ไม่พบไฟล์ JSON ในโฟลเดอร์ {target}")
        for jf in json_files:
            await load_match_json(conn, jf, force=args.force)
    else:
        print(f"ไม่พบ path: {target}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
