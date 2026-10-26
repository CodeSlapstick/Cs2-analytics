# -*- coding: utf-8 -*-
"""All PostgreSQL reads used by the report feature. No recommendations belong here."""
from typing import Any

import asyncpg


class ReportNotFoundError(LookupError):
    pass


class ReportRepository:
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def load(self, match_id: int, side: str, steam_id: str | None = None) -> dict[str, Any]:
        match = await self.conn.fetchrow(
            "SELECT * FROM match_summary WHERE id = $1 AND source = 'upload' AND status = 'done'", match_id
        )
        if not match:
            raise ReportNotFoundError("match")
        side_sql = "" if side == "all" else "AND f.side = $2"
        args: list[Any] = [match_id] if side == "all" else [match_id, side]
        player_arg = len(args) + 1
        player_sql = ""
        if steam_id is not None:
            player_sql = f"AND f.steam_id = ${player_arg}::bigint"
            args.append(int(steam_id))
        players = await self.conn.fetch(f"""
            SELECT f.steam_id::text AS steam_id, p.name, COUNT(*) AS rounds,
                   SUM(f.kills)::int AS kills, SUM(f.deaths)::int AS deaths,
                   SUM(f.assists)::int AS assists,
                   ROUND(SUM(f.damage)::numeric / GREATEST(COUNT(*), 1), 1)::float AS adr,
                   ROUND(100.0 * COUNT(*) FILTER (WHERE f.kast) / GREATEST(COUNT(*), 1), 1)::float AS kast,
                   ROUND((
                     (SUM(f.kills)::numeric / GREATEST(COUNT(*), 1)) / 0.679
                     + 0.7 * ((COUNT(*) - SUM(f.deaths))::numeric / GREATEST(COUNT(*), 1)) / 0.317
                     + ((COUNT(*) FILTER (WHERE f.kills = 1) + 4 * COUNT(*) FILTER (WHERE f.kills = 2)
                         + 9 * COUNT(*) FILTER (WHERE f.kills = 3) + 16 * COUNT(*) FILTER (WHERE f.kills = 4)
                         + 25 * COUNT(*) FILTER (WHERE f.kills >= 5))::numeric / GREATEST(COUNT(*), 1)) / 1.277
                   ) / 2.7, 2)::float AS rating,
                   COUNT(*) FILTER (WHERE f.opening_kill)::int AS opening_kills,
                   COUNT(*) FILTER (WHERE f.opening_death)::int AS opening_deaths,
                   COALESCE(SUM(f.trade_kills), 0)::int AS trade_kills,
                   COUNT(*) FILTER (WHERE f.deaths > 0 AND f.was_traded)::int AS traded_deaths
            FROM player_round_facts f JOIN players p USING (steam_id)
            WHERE f.match_id = $1 {side_sql} {player_sql}
            GROUP BY f.steam_id, p.name ORDER BY rating DESC, kills DESC""", *args)
        if steam_id is not None and not players:
            raise ReportNotFoundError("player")
        rounds = await self.conn.fetch("""
            SELECT r.round_num, r.winner_side, r.end_reason, r.start_tick,
                   COUNT(k.id)::int AS deaths_count,
                   MIN((k.tick - r.start_tick)::float / NULLIF(m.tickrate, 0)) AS first_death_t,
                   e.ct_buy_type, e.t_buy_type, e.ct_equip, e.t_equip
            FROM rounds r JOIN matches m ON m.id = r.match_id
            LEFT JOIN kills k ON k.round_id = r.id
            LEFT JOIN round_economy e ON e.round_id = r.id
            WHERE r.match_id = $1
            GROUP BY r.id, m.tickrate, e.ct_buy_type, e.t_buy_type, e.ct_equip, e.t_equip
            ORDER BY r.round_num""", match_id)
        hotspots = await self.conn.fetch("""
            SELECT COALESCE(k.victim_place, 'ไม่ระบุตำแหน่ง') AS place, COUNT(*)::int AS deaths
            FROM kills k JOIN rounds r ON r.id = k.round_id
            WHERE r.match_id = $1 AND ($2 = 'all' OR k.victim_side = $2)
            GROUP BY COALESCE(k.victim_place, 'ไม่ระบุตำแหน่ง')
            ORDER BY deaths DESC, place LIMIT 5""", match_id, side)
        benchmark = await self.conn.fetchrow("""
            WITH recent AS (
              SELECT id FROM matches WHERE source = 'upload' AND status = 'done'
                AND map_name = $2 AND id <> $1 ORDER BY imported_at DESC LIMIT 5
            )
            SELECT COUNT(DISTINCT f.match_id)::int AS matches,
                   ROUND(AVG(f.damage)::numeric, 1)::float AS adr,
                   ROUND(100.0 * AVG(f.kast::int), 1)::float AS kast
            FROM player_round_facts f WHERE f.match_id IN (SELECT id FROM recent)
              AND ($3 = 'all' OR f.side = $3)""", match_id, match["map_name"], side)
        return {"match": dict(match), "players": [dict(x) for x in players], "rounds": [dict(x) for x in rounds],
                "hotspots": [dict(x) for x in hotspots], "benchmark": dict(benchmark) if benchmark else {}}
