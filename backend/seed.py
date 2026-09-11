import asyncio
import os

import asyncpg
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cs2_analytics")

async def seed():
    conn = await asyncpg.connect(DB_URL)
    print("เชื่อมต่อฐานข้อมูลเพื่อ Seed สำเร็จ")

    # 1. Seed Players
    await conn.execute("""
        INSERT INTO players (steam_id, name) VALUES
        (76561198000000001, 's1mple'),
        (76561198000000002, 'ZywOo'),
        (76561198000000003, 'm0NESY'),
        (76561198000000004, 'NiKo'),
        (76561198000000005, 'donk')
        ON CONFLICT (steam_id) DO UPDATE SET name = EXCLUDED.name;
    """)

    # 2. Seed Match (Idempotent)
    match_id = await conn.fetchval("""
        INSERT INTO matches (demo_file, map_name, tickrate, team_a, team_b)
        VALUES ('seed_dev_match_01.dem', 'de_mirage', 128, 'Team NAVI', 'Team Vitality')
        ON CONFLICT (demo_file) DO UPDATE SET map_name = EXCLUDED.map_name
        RETURNING id;
    """)

    # 3. Seed Rounds
    await conn.execute("DELETE FROM rounds WHERE match_id = $1;", match_id)
    r1 = await conn.fetchval("""
        INSERT INTO rounds (match_id, round_num, start_tick, winner_side, end_reason)
        VALUES ($1, 1, 1000, 'ct', 't_killed') RETURNING id;
    """, match_id)

    # 4. Seed Damages
    await conn.execute("""
        INSERT INTO damages (round_id, tick, attacker_id, victim_id, weapon, damage, hitgroup) VALUES
        ($1, 1100, 76561198000000001, 76561198000000002, 'ak47', 100, 'head'),
        ($1, 1150, 76561198000000003, 76561198000000004, 'm4a1_silencer', 80, 'chest'),
        ($1, 1180, 76561198000000001, 76561198000000004, 'ak47', 20, 'stomach');
    """, r1)

    # 5. Seed Kills
    await conn.execute("""
        INSERT INTO kills (round_id, tick, attacker_id, victim_id, weapon, headshot, attacker_side, victim_side) VALUES
        ($1, 1100, 76561198000000001, 76561198000000002, 'ak47', true, 'ct', 't'),
        ($1, 1180, 76561198000000001, 76561198000000004, 'ak47', false, 'ct', 't');
    """, r1)

    print("Seed ข้อมูลตัวอย่างสำหรับ dev เรียบร้อยแล้ว")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(seed())
