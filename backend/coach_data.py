"""Shared SQL adapter for Coach training and match inference; no model fitting."""


async def load_coach_facts(conn, map_name: str, *, match_id: int | None = None, reference_only: bool = False):
    reference = "AND m.source = 'reference'" if reference_only else ""
    where = f"m.status = 'done' AND m.map_name = $1 AND ($2::int IS NULL OR m.id = $2) {reference}"
    facts = await conn.fetch(f"""
        SELECT r.id AS round_id, r.match_id, m.demo_file, m.source, r.round_num,
               r.start_tick, m.tickrate, r.winner_side, pr.steam_id, pr.side, pr.equip_value
        FROM rounds r JOIN matches m ON m.id = r.match_id JOIN player_rounds pr ON pr.round_id = r.id
        WHERE {where} ORDER BY r.match_id, r.round_num, pr.steam_id
    """, map_name, match_id)
    positions = await conn.fetch(f"""
        SELECT r.id AS round_id, pp.tick, pp.steam_id, pp.side, pp.place
        FROM player_positions pp JOIN rounds r ON r.match_id = pp.match_id AND r.round_num = pp.round_num
        JOIN matches m ON m.id = r.match_id
        WHERE {where} AND pp.health > 0
          AND pp.tick BETWEEN r.start_tick AND r.start_tick + 30 * m.tickrate
        ORDER BY r.id, pp.tick, pp.steam_id
    """, map_name, match_id)
    utility = await conn.fetch(f"""
        SELECT g.round_id, g.side, g.type, COUNT(*) AS n
        FROM grenades g JOIN rounds r ON r.id = g.round_id JOIN matches m ON m.id = r.match_id
        WHERE {where} AND g.tick BETWEEN r.start_tick AND r.start_tick + 30 * m.tickrate
        GROUP BY g.round_id, g.side, g.type
    """, map_name, match_id)
    return {"facts": [dict(r) for r in facts], "positions": [dict(r) for r in positions],
            "utility": [dict(r) for r in utility]}
