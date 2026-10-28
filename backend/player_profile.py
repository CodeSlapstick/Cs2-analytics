"""Player search and filter-consistent profile aggregation from parsed demos only."""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import date
from typing import Any

from backend.features import rating2_approx
from backend.player_role_service import (
    build_match_profiles,
    compatibility_reason,
    infer_match,
    load_role_model,
)


def _number(value: Any) -> float:
    return float(value or 0)


def rating1(rows: Iterable[dict[str, Any]]) -> float | None:
    """Published HLTV Rating 1.0 formula, evaluated over one filtered round set."""
    facts = list(rows)
    if not facts:
        return None
    rounds = len(facts)
    kills = sum(int(row.get("kills") or 0) for row in facts)
    deaths = sum(int(row.get("deaths") or 0) for row in facts)
    multikill = sum((int(row.get("kills") or 0) ** 2) for row in facts)
    value = ((kills / rounds) / 0.679 + 0.7 * (((rounds - deaths) / rounds) / 0.317)
             + (multikill / rounds) / 1.277) / 2.7
    return round(value, 2)


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    rounds = len(rows)
    kills = sum(int(row.get("kills") or 0) for row in rows)
    deaths = sum(int(row.get("deaths") or 0) for row in rows)
    assists = sum(int(row.get("assists") or 0) for row in rows)
    headshots = sum(int(row.get("headshots") or 0) for row in rows)
    damage = sum(int(row.get("damage") or 0) for row in rows)
    kast_rounds = sum(bool(row.get("kast")) for row in rows)
    survived = sum(bool(row.get("survived")) for row in rows)
    won = sum(bool(row.get("won")) for row in rows)
    return {
        "matches": len({int(row["match_id"]) for row in rows}),
        "rounds": rounds,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "headshots": headshots,
        "kd": round(kills / deaths, 2) if deaths else (None if not kills else float(kills)),
        "hs_rate": round(100 * headshots / kills, 1) if kills else None,
        "adr": round(damage / rounds, 1),
        "kast": round(100 * kast_rounds / rounds, 1),
        "win_rate": round(100 * won / rounds, 1),
        "survival_rate": round(100 * survived / rounds, 1),
        "rating": rating1(rows),
        "rating2_approx": rating2_approx(kills=kills, deaths=deaths, assists=assists,
                                          damage=damage, kast_rounds=kast_rounds, rounds=rounds),
    }


def _entry(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    def side_stats(side: str | None) -> dict[str, int]:
        selected = rows if side is None else [row for row in rows if row.get("side") == side]
        return {
            "kills": sum(bool(row.get("opening_kill")) for row in selected),
            "deaths": sum(bool(row.get("opening_death")) for row in selected),
        }
    return {"both": side_stats(None), "t": side_stats("t"), "ct": side_stats("ct")}


def _match_result(rows: list[dict[str, Any]]) -> str:
    if rows and rows[0].get("_match_result"):
        return str(rows[0]["_match_result"])
    won = sum(bool(row.get("won")) for row in rows)
    return "win" if won * 2 > len(rows) else "draw" if won * 2 == len(rows) else "loss"


def summarize_rows(rows: list[dict[str, Any]], weapons: list[dict[str, Any]]) -> dict[str, Any]:
    totals = aggregate_rows(rows)
    by_match: dict[int, list[dict[str, Any]]] = defaultdict(list)
    by_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_match[int(row["match_id"])].append(row)
        by_map[str(row.get("map_name") or "unknown")].append(row)

    recent = []
    for match_rows in sorted(by_match.values(), key=lambda group: (group[0]["imported_at"], group[0]["match_id"]), reverse=True):
        first = match_rows[0]
        stats = aggregate_rows(match_rows)
        recent.append({
            "match_id": first["match_id"], "demo_file": first["demo_file"], "map_name": first["map_name"],
            "team_a": first.get("team_a"), "team_b": first.get("team_b"), "team": first.get("team_clan"),
            "imported_at": first["imported_at"], "rounds": len(match_rows),
            "rounds_won": sum(bool(row.get("won")) for row in match_rows), "result": _match_result(match_rows),
            "kills": stats["kills"], "deaths": stats["deaths"], "assists": stats["assists"],
            "adr": stats["adr"], "kast": stats["kast"], "rating": stats["rating"],
        })

    maps = []
    for map_name, map_rows in by_map.items():
        match_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in map_rows:
            match_groups[int(row["match_id"])].append(row)
        results = [_match_result(group) for group in match_groups.values()]
        stats = aggregate_rows(map_rows)
        maps.append({
            "map_name": map_name, "matches": len(match_groups), "wins": results.count("win"),
            "losses": results.count("loss"), "rounds": len(map_rows),
            "win_rate": round(100 * results.count("win") / len(results), 1),
            "rating": stats["rating"], "adr": stats["adr"], "kd": stats["kd"],
        })
    maps.sort(key=lambda item: (-item["matches"], item["map_name"]))

    clutch_rows = [row for row in rows if int(row.get("features_version") or 0) > 0]
    clutch_available = bool(clutch_rows)
    clutches = []
    for vs in range(1, 6):
        attempts = [row for row in clutch_rows if int(row.get("clutch_vs") or 0) == vs]
        clutches.append({"vs": vs, "attempts": len(attempts), "wins": sum(bool(row.get("clutch_won")) for row in attempts)})

    imported = [row["imported_at"] for row in rows]
    return {
        "totals": totals,
        "entry": _entry(rows),
        "clutches": clutches if clutch_available else None,
        "recent_matches": recent,
        "maps": maps,
        "weapons": weapons,
        "data_range": {"from": min(imported) if imported else None, "to": max(imported) if imported else None,
                       "basis": "imported_at"},
    }


async def search_players(conn: Any, query: str, limit: int) -> dict[str, Any]:
    records = await conn.fetch("""
        WITH matched AS (
          SELECT p.steam_id, p.name, p.avatar, a.username,
                 COUNT(DISTINCT f.match_id)::int AS matches,
                 COUNT(*) OVER()::int AS total
          FROM players p
          JOIN player_round_facts f ON f.steam_id = p.steam_id
          LEFT JOIN accounts a ON a.steam_id = p.steam_id
          WHERE strpos(lower(p.name), lower($1)) > 0
             OR strpos(lower(COALESCE(a.username, '')), lower($1)) > 0
             OR strpos(p.steam_id::text, $1) > 0
          GROUP BY p.steam_id, p.name, p.avatar, a.username
        )
        SELECT matched.*, latest.team_clan AS latest_team, latest.demo_file AS latest_match,
               latest.imported_at AS latest_at
        FROM matched
        LEFT JOIN LATERAL (
          SELECT mp.team_clan, m.demo_file, m.imported_at
          FROM match_players mp JOIN matches m ON m.id = mp.match_id
          WHERE mp.steam_id = matched.steam_id AND m.status = 'done'
          ORDER BY m.imported_at DESC, m.id DESC LIMIT 1
        ) latest ON TRUE
        ORDER BY (lower(matched.name) = lower($2)) DESC, matched.matches DESC, lower(matched.name), matched.steam_id
        LIMIT $3
    """, query, query, limit)
    items = []
    total = 0
    for raw in records:
        row = dict(raw)
        total = int(row.pop("total") or 0)
        row["steam_id"] = str(row["steam_id"])
        items.append(row)
    has_players = bool(await conn.fetchval("SELECT EXISTS(SELECT 1 FROM player_round_facts LIMIT 1)"))
    return {"items": items, "total": total, "has_players": has_players}


async def _behavior(conn: Any, steam_id: int, match_ids: list[int], selected_side: str = "all") -> dict[str, Any]:
    if not match_ids:
        return {"available": False, "reason": "insufficient_data", "sides": []}
    matches = [dict(row) for row in await conn.fetch(
        "SELECT id, map_name, tickrate, source FROM matches WHERE id = ANY($1::int[])", match_ids)]
    round_rows = [dict(row) for row in await conn.fetch("""
        SELECT r.match_id, r.round_num, pr.steam_id, p.name, pr.side, pr.assists, pr.opening_kill,
               pr.opening_death, pr.trade_kills, pr.was_traded
        FROM player_rounds pr JOIN rounds r ON r.id = pr.round_id JOIN players p ON p.steam_id = pr.steam_id
        WHERE r.match_id = ANY($1::int[]) ORDER BY r.match_id, r.round_num
    """, match_ids)]
    kill_rows = [dict(row) for row in await conn.fetch("""
        SELECT r.match_id, r.round_num, r.start_tick, r.bomb_plant_tick, k.tick, k.attacker_id,
               k.victim_id, k.assister_id, k.attacker_side, k.victim_side, k.attacker_place,
               k.victim_place, k.assisted_flash
        FROM kills k JOIN rounds r ON r.id = k.round_id
        WHERE r.match_id = ANY($1::int[]) ORDER BY r.match_id, r.round_num, k.tick
    """, match_ids)]
    rounds_by_match: dict[int, list[dict[str, Any]]] = defaultdict(list)
    kills_by_match: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in round_rows:
        rounds_by_match[int(row["match_id"])].append(row)
    for row in kill_rows:
        kills_by_match[int(row["match_id"])].append(row)

    inferred: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for match in matches:
        model = load_role_model(map_name=match.get("map_name"))
        if compatibility_reason(model, match.get("map_name"), match.get("source")):
            continue
        profiles = build_match_profiles(rounds_by_match[match["id"]], kills_by_match[match["id"]], match.get("tickrate") or 128)
        for result in infer_match(profiles, model, {str(steam_id)}):
            if result.get("available") and (selected_side == "all" or result.get("side") == selected_side):
                inferred[result["side"]].append(result)

    sides = []
    for side in ("ct", "t"):
        profiles = inferred.get(side, [])
        if not profiles:
            sides.append({"side": side, "available": False, "reason": "insufficient_data"})
            continue
        roles = Counter(profile["role"] for profile in profiles)
        role = roles.most_common(1)[0][0]
        representative = next(profile for profile in profiles if profile["role"] == role)
        sides.append({
            "side": side, "available": True, "role": role, "profiles": len(profiles),
            "rounds": sum(int(profile["rounds"]) for profile in profiles),
            "signals": representative.get("signals", []), "metrics": representative.get("metrics", {}),
        })
    available = any(item.get("available") for item in sides)
    result = {"available": available, "unit": "player-match-side", "sides": sides}
    if not available:
        result["reason"] = "insufficient_data"
    return result


async def build_profile(conn: Any, steam_id: int, *, recent: int = 0, date_from: date | None = None,
                        date_to: date | None = None, map_name: str | None = None,
                        side: str = "all") -> dict[str, Any] | None:
    identity = await conn.fetchrow("""
        SELECT p.steam_id, p.name, COALESCE(a.avatar, p.avatar) AS avatar, a.username,
               COUNT(DISTINCT f.match_id)::int AS all_matches
        FROM players p JOIN player_round_facts f ON f.steam_id = p.steam_id
        LEFT JOIN accounts a ON a.steam_id = p.steam_id
        WHERE p.steam_id = $1 GROUP BY p.steam_id, p.name, p.avatar, a.avatar, a.username
    """, steam_id)
    if not identity:
        return None

    records = await conn.fetch("""
        WITH eligible AS (
          SELECT m.id, m.imported_at
          FROM player_round_facts f JOIN matches m ON m.id = f.match_id
          WHERE f.steam_id = $1
            AND ($2::date IS NULL OR m.imported_at::date >= $2)
            AND ($3::date IS NULL OR m.imported_at::date <= $3)
            AND ($4::text IS NULL OR m.map_name = $4)
          GROUP BY m.id, m.imported_at
        ), candidates AS (
          SELECT id, imported_at, ROW_NUMBER() OVER (ORDER BY imported_at DESC, id DESC) AS position
          FROM eligible
        ), selected AS (SELECT id FROM candidates WHERE $5 = 0 OR position <= $5)
        SELECT f.*, pr.clutch_vs, pr.clutch_won, pr.features_version,
               m.demo_file, m.map_name, m.team_a, m.team_b, m.imported_at, mp.team_clan
        FROM player_round_facts f
        JOIN selected s ON s.id = f.match_id
        JOIN player_rounds pr ON pr.round_id = f.round_id AND pr.steam_id = f.steam_id
        JOIN matches m ON m.id = f.match_id
        LEFT JOIN match_players mp ON mp.match_id = f.match_id AND mp.steam_id = f.steam_id
        WHERE f.steam_id = $1 AND ($6 = 'all' OR f.side = $6)
        ORDER BY m.imported_at DESC, m.id DESC, f.round_num
    """, steam_id, date_from, date_to, map_name, recent, side)
    facts = [dict(row) for row in records]
    match_ids = sorted({int(row["match_id"]) for row in facts})
    if match_ids:
        outcomes = await conn.fetch("""
            SELECT match_id,
                   CASE WHEN COUNT(*) FILTER (WHERE won) * 2 > COUNT(*) THEN 'win'
                        WHEN COUNT(*) FILTER (WHERE won) * 2 = COUNT(*) THEN 'draw'
                        ELSE 'loss' END AS result
            FROM player_round_facts
            WHERE steam_id = $1 AND match_id = ANY($2::int[])
            GROUP BY match_id
        """, steam_id, match_ids)
        result_by_match = {int(row["match_id"]): row["result"] for row in outcomes}
        for fact in facts:
            fact["_match_result"] = result_by_match.get(int(fact["match_id"]))
    round_ids = [int(row["round_id"]) for row in facts]
    weapons = []
    if round_ids:
        weapons = [dict(row) for row in await conn.fetch("""
            SELECT k.weapon, COUNT(*)::int AS kills,
                   COUNT(*) FILTER (WHERE k.headshot)::int AS headshots,
                   ROUND(100.0 * COUNT(*) FILTER (WHERE k.headshot) / COUNT(*), 1) AS hs_rate,
                   NULL::numeric AS accuracy
            FROM kills k
            WHERE k.round_id = ANY($1::int[]) AND k.attacker_id = $2
              AND k.attacker_side <> k.victim_side
            GROUP BY k.weapon ORDER BY kills DESC, k.weapon LIMIT 8
        """, round_ids, steam_id)]

    summary = summarize_rows(facts, weapons)
    all_maps = [row["map_name"] for row in await conn.fetch("""
        SELECT DISTINCT m.map_name FROM player_round_facts f JOIN matches m ON m.id = f.match_id
        WHERE f.steam_id = $1 ORDER BY m.map_name
    """, steam_id)]
    latest = await conn.fetchrow("""
        SELECT mp.team_clan FROM match_players mp JOIN matches m ON m.id = mp.match_id
        WHERE mp.steam_id = $1 ORDER BY m.imported_at DESC, m.id DESC LIMIT 1
    """, steam_id)
    return {
        "player": {"steam_id": str(identity["steam_id"]), "name": identity["name"],
                   "avatar": identity["avatar"], "account_name": identity["username"],
                   "latest_team": latest["team_clan"] if latest else None},
        **summary,
        "behavior": await _behavior(conn, steam_id, match_ids, side),
        "filters": {"recent": recent, "date_from": date_from, "date_to": date_to,
                    "map": map_name, "side": side, "available_maps": all_maps},
        "source": {"all_matches": identity["all_matches"], "selected_matches": summary["totals"]["matches"] if summary["totals"] else 0,
                   "selected_rounds": summary["totals"]["rounds"] if summary["totals"] else 0,
                   "date_basis": "imported_at"},
        "formulas": {
            "rating": "Calculated with the published HLTV Rating 1.0 formula: (KillRating + 0.7×SurvivalRating + MultiKillRating) / 2.7; not an official stat feed",
            "rating2": "Community-estimated Rating 2.0; not an official HLTV Rating 2.0 value",
            "hs_rate": "headshot kills / kills",
            "adr": "enemy damage / rounds",
            "kast": "rounds with a kill, assist, survival or traded death / rounds",
            "round_win_rate": "rounds won while the player was on the winning side / selected rounds",
        },
        "unsupported": ["weapon_accuracy", "match_played_at"],
    }
