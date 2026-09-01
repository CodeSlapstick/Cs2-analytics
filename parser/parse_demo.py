#!/usr/bin/env python3
"""
Parser service — แปลงไฟล์ .dem ของ CS2 เป็น normalized JSON

    python parser/parse_demo.py demo.dem -o data/matches/
    python parser/parse_demo.py demos/*.dem -o data/matches/ --tickrate 64
    python parser/parse_demo.py demo.dem --summary        # ดูสรุปเฉย ๆ ไม่เขียนไฟล์

รูปแบบผลลัพธ์อยู่ใน docs/normalized-match.md — ไฟล์ที่ได้ส่งต่อเข้า ETL ได้เลย:

    npm run etl -- data/matches

หลักการสำคัญของไฟล์นี้: **ดึงข้อเท็จจริงดิบอย่างเดียว ไม่คำนวณสถิติ**
(ใครฆ่าใคร ตอน tick ไหน ตรงพิกัดไหน / รอบไหนใครชนะ) ส่วน opening duel, trade,
clutch, ADR, KPI ไปคิดที่ ตอนวิเคราะห์ที่เดียว เพื่อไม่ให้สูตรอยู่
สองที่แล้วเพี้ยนกันเวลาแก้ข้างเดียว

หมายเหตุเรื่องชื่อคอลัมน์: awpy/demoparser2 เปลี่ยนชื่อคอลัมน์อยู่เรื่อย ๆ ระหว่างเวอร์ชัน
โค้ดนี้จึงค้นหาคอลัมน์จาก "ชื่อที่เป็นไปได้หลายแบบ" แทนที่จะยึดชื่อเดียวตายตัว
ถ้าหาไม่เจอจริง ๆ จะข้ามส่วนนั้นพร้อมเตือน แทนที่จะพังทั้งไฟล์
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import polars as pl
    from awpy import Demo
except ImportError as exc:  # pragma: no cover
    print(f"ต้องติดตั้ง dependency ก่อน: pip install -r parser/requirements.txt ({exc})", file=sys.stderr)
    raise SystemExit(1)

# คอนโซล Windows ดีฟอลต์เป็น cp874/cp1252 ซึ่งพิมพ์ข้อความไทยและเครื่องหมาย ✓ ไม่ได้
# บังคับเป็น UTF-8 ตั้งแต่ต้น ไม่งั้นสคริปต์จะพังตอน print ทั้งที่ parse สำเร็จแล้ว
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

SCHEMA_VERSION = 1
T_TEAM = 2   # ทีมที่เริ่มครึ่งแรกฝั่ง T
CT_TEAM = 3  # ทีมที่เริ่มครึ่งแรกฝั่ง CT

UTIL_ALIASES = {
    "molotov": "inferno",
    "incgrenade": "inferno",
    "inferno": "inferno",
    "hegrenade": "hegrenade",
}

# awpy คืน grenade_type เป็นชื่อคลาสในเกม เช่น "CSmokeGrenadeProjectile"
# แปลงเป็นชื่อสั้นชุดเดียวกับที่ฝั่ง damage ใช้ เพื่อให้ derive.js เทียบชื่อได้ตรงกัน
GRENADE_CLASS_ALIASES = {
    "csmokegrenadeprojectile": "smokegrenade",
    "cflashbangprojectile": "flashbang",
    "chegrenadeprojectile": "hegrenade",
    "cmolotovprojectile": "inferno",
    "cincendiarygrenadeprojectile": "inferno",
    "cdecoyprojectile": "decoy",
}


# ---------------------------------------------------------------------------
# helper สำหรับอ่าน DataFrame แบบทนต่อการเปลี่ยนชื่อคอลัมน์
# ---------------------------------------------------------------------------
def col(df: "pl.DataFrame", *candidates: str) -> str | None:
    """คืนชื่อคอลัมน์แรกที่มีอยู่จริงใน df (ไม่สนตัวพิมพ์เล็กใหญ่)"""
    if df is None or df.is_empty():
        return None
    lower = {c.lower(): c for c in df.columns}
    for name in candidates:
        if name in df.columns:
            return name
        if name.lower() in lower:
            return lower[name.lower()]
    return None


def as_str_id(value) -> str | None:
    """steamid ออกมาเป็น u64/float/str แล้วแต่เวอร์ชัน — บังคับให้เป็นสตริง 17 หลัก"""
    if value is None:
        return None
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text if text.isdigit() and len(text) == 17 else None


def norm_side(value) -> str | None:
    """'CT' / 'TERRORIST' / 'ct' / 't' / 3 / 2 -> 'ct' หรือ 't'"""
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("ct", "3", "counter-terrorist", "counterterrorist"):
        return "ct"
    if text in ("t", "2", "terrorist", "terrorists"):
        return "t"
    if text.startswith("ct"):
        return "ct"
    if text.startswith("t"):
        return "t"
    return None


def num(value):
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else round(out, 2)  # กัน NaN


def to_int(value):
    v = num(value)
    return None if v is None else int(v)


# ---------------------------------------------------------------------------


def build_player_table(dem, warn) -> tuple[dict[str, dict], dict[int, dict[str, str]]]:
    """
    คืน (ผู้เล่น -> ข้อมูล, รอบ -> {steamid: ฝั่งในรอบนั้น})

    team_number ยึดจาก "ฝั่งที่เล่นในรอบแรก" ไม่ใช่ฝั่งปัจจุบัน เพราะ CS2 สลับฝั่ง
    ตอนครึ่งหลัง ถ้ายึดฝั่งปัจจุบันคนคนเดียวจะกลายเป็นคนละทีมกลางแมตช์
    """
    ticks = getattr(dem, "ticks", None)
    if ticks is None or ticks.is_empty():
        raise SystemExit("ไม่พบ tick data ในไฟล์นี้ — parse ไม่สำเร็จ")

    c_round = col(ticks, "round_num", "round")
    c_steam = col(ticks, "steamid", "steam_id", "player_steamid")
    c_side = col(ticks, "side", "team_name", "team")
    c_name = col(ticks, "name", "player_name", "last_place_name")
    if not (c_round and c_steam and c_side):
        raise SystemExit(f"tick data ขาดคอลัมน์ที่ต้องใช้ (มี: {ticks.columns[:12]} …)")

    keep = [c for c in (c_round, c_steam, c_side, c_name) if c]
    rows = ticks.select(keep).unique().sort(c_round).to_dicts()

    sides_by_round: dict[int, dict[str, str]] = {}
    first_side: dict[str, str] = {}
    names: dict[str, str] = {}

    for row in rows:
        sid = as_str_id(row.get(c_steam))
        rnd = to_int(row.get(c_round))
        side = norm_side(row.get(c_side))
        if not sid or rnd is None or side is None:
            continue
        sides_by_round.setdefault(rnd, {})[sid] = side
        if sid not in first_side:
            first_side[sid] = side
        if c_name and row.get(c_name):
            names.setdefault(sid, str(row[c_name]))

    if not first_side:
        raise SystemExit("อ่านผู้เล่นจาก tick data ไม่ได้เลย (steamid ไม่ใช่ 17 หลักทั้งหมด — เป็นบอทหรือเปล่า)")

    # ฝั่งของรอบแรกสุดที่มีข้อมูล
    first_round = min(sides_by_round)
    players: dict[str, dict] = {}
    for sid, side in first_side.items():
        side_in_first = sides_by_round.get(first_round, {}).get(sid, side)
        players[sid] = {
            "steam64_id": sid,
            "name": names.get(sid, f"Player_{sid[-4:]}"),
            "team_number": T_TEAM if side_in_first == "t" else CT_TEAM,
        }

    if len(players) > 12:
        warn(f"พบผู้เล่น {len(players)} คน (ปกติ 10) — อาจมีคนเข้าออกกลางแมตช์")
    return players, sides_by_round


def build_rounds(dem, players, sides_by_round, warn) -> list[dict]:
    rounds_df = getattr(dem, "rounds", None)
    if rounds_df is None or rounds_df.is_empty():
        raise SystemExit("ไม่พบข้อมูลรอบ (rounds) — ไฟล์อาจไม่สมบูรณ์หรือเป็น demo ที่ยังไม่จบแมตช์")

    c_num = col(rounds_df, "round_num", "round")
    c_winner = col(rounds_df, "winner", "winner_side")
    c_reason = col(rounds_df, "reason", "end_reason")
    c_start = col(rounds_df, "start", "start_tick")
    c_freeze = col(rounds_df, "freeze_end", "freeze_end_tick")
    c_end = col(rounds_df, "end", "end_tick")
    c_official = col(rounds_df, "official_end", "official_end_tick")
    c_plant = col(rounds_df, "bomb_plant", "bomb_plant_tick", "bomb_planted")

    team_of = {sid: p["team_number"] for sid, p in players.items()}
    out = []
    for i, row in enumerate(rounds_df.sort(c_num).to_dicts(), start=1):
        raw_round = to_int(row.get(c_num)) or i
        winner_side = norm_side(row.get(c_winner)) if c_winner else None

        # แปลง "ฝั่งที่ชนะ" เป็น "ทีมที่ชนะ" โดยดูจากว่ารอบนั้นใครอยู่ฝั่งไหน
        # (เชื่อข้อมูลจริงในรอบนั้น ดีกว่าเดาจากกติกาสลับฝั่ง MR12/overtime)
        winner_team = None
        if winner_side:
            votes = {T_TEAM: 0, CT_TEAM: 0}
            for sid, side in sides_by_round.get(raw_round, {}).items():
                if side == winner_side and sid in team_of:
                    votes[team_of[sid]] += 1
            if votes[T_TEAM] or votes[CT_TEAM]:
                winner_team = T_TEAM if votes[T_TEAM] >= votes[CT_TEAM] else CT_TEAM
            else:
                # ไม่มี tick ของรอบนั้น — ถอยไปใช้กติกาสลับฝั่งครึ่งละ 12 รอบ
                swapped = i > 12
                winner_team = (
                    (CT_TEAM if swapped else T_TEAM) if winner_side == "t" else (T_TEAM if swapped else CT_TEAM)
                )
                warn(f"รอบ {i}: ไม่มี tick data ใช้กติกาสลับฝั่ง MR12 แทนในการหาทีมที่ชนะ")

        plant_tick = to_int(row.get(c_plant)) if c_plant else None
        out.append(
            {
                "round_number": i,  # เรียง 1..N ใหม่เสมอ (ETL บังคับว่าห้ามข้าม)
                "_source_round": raw_round,
                "winner_team_number": winner_team,
                "winner_side": winner_side,
                "end_reason": str(row.get(c_reason)) if c_reason and row.get(c_reason) is not None else None,
                "bomb_planted": bool(plant_tick) if plant_tick is not None else bool(row.get(c_plant)) if c_plant else False,
                "start_tick": to_int(row.get(c_start)) if c_start else None,
                "freeze_end_tick": to_int(row.get(c_freeze)) if c_freeze else None,
                "end_tick": to_int(row.get(c_end)) if c_end else None,
                "official_end_tick": to_int(row.get(c_official)) if c_official else None,
            }
        )
    return out


def build_kill_events(dem, players, round_map, warn) -> list[dict]:
    kills = getattr(dem, "kills", None)
    if kills is None or kills.is_empty():
        warn("ไม่พบ kill event ในไฟล์นี้")
        return []

    c_round = col(kills, "round_num", "round")
    c_tick = col(kills, "tick")
    c_att = col(kills, "attacker_steamid", "attacker_steam_id")
    c_vic = col(kills, "victim_steamid", "victim_steam_id", "user_steamid")
    c_ass = col(kills, "assister_steamid", "assister_steam_id")
    c_weapon = col(kills, "weapon", "weapon_name")
    c_hs = col(kills, "headshot")
    c_hitgroup = col(kills, "hitgroup")
    c_flash = col(kills, "assistedflash", "assisted_flash")
    c_noscope = col(kills, "noscope")
    c_smoke = col(kills, "thrusmoke", "through_smoke")
    ax, ay, az = col(kills, "attacker_X", "attacker_x"), col(kills, "attacker_Y", "attacker_y"), col(kills, "attacker_Z", "attacker_z")
    vx, vy, vz = col(kills, "victim_X", "victim_x"), col(kills, "victim_Y", "victim_y"), col(kills, "victim_Z", "victim_z")
    # ชื่อ callout ในเกม ("LongA", "Mid") ใช้ตั้งชื่อโซนที่ ML แบ่งได้ ให้โค้ชอ่านรู้เรื่อง
    c_aplace = col(kills, "attacker_place", "attacker_last_place_name")
    c_vplace = col(kills, "victim_place", "user_place", "victim_last_place_name")

    events = []
    for row in kills.to_dicts():
        rnd = round_map.get(to_int(row.get(c_round)))
        if rnd is None:
            continue
        victim = as_str_id(row.get(c_vic)) if c_vic else None
        if victim not in players:
            continue
        attacker = as_str_id(row.get(c_att)) if c_att else None
        assister = as_str_id(row.get(c_ass)) if c_ass else None
        events.append(
            {
                "type": "kill",
                "round_number": rnd,
                "tick": to_int(row.get(c_tick)) if c_tick else None,
                "actor_steam64": attacker if attacker in players else None,
                "victim_steam64": victim,
                "assister_steam64": assister if assister in players else None,
                "weapon": str(row.get(c_weapon)) if c_weapon and row.get(c_weapon) else None,
                "headshot": bool(row.get(c_hs)) if c_hs else False,
                "damage": 100,
                "actor_x": num(row.get(ax)) if ax else None,
                "actor_y": num(row.get(ay)) if ay else None,
                "actor_z": num(row.get(az)) if az else None,
                "victim_x": num(row.get(vx)) if vx else None,
                "victim_y": num(row.get(vy)) if vy else None,
                "victim_z": num(row.get(vz)) if vz else None,
                "meta": {
                    "hitgroup": str(row.get(c_hitgroup)) if c_hitgroup and row.get(c_hitgroup) else None,
                    "assistedflash": bool(row.get(c_flash)) if c_flash else False,
                    "noscope": bool(row.get(c_noscope)) if c_noscope else False,
                    "through_smoke": bool(row.get(c_smoke)) if c_smoke else False,
                    "actor_place": str(row.get(c_aplace)) if c_aplace and row.get(c_aplace) else None,
                    "victim_place": str(row.get(c_vplace)) if c_vplace and row.get(c_vplace) else None,
                },
            }
        )
    return events


def build_damage_events(dem, players, round_map, warn) -> list[dict]:
    dmg = getattr(dem, "damages", None)
    if dmg is None or dmg.is_empty():
        warn("ไม่พบ damage event — ADR และดาเมจยูทิลิตี้จะเป็น 0")
        return []

    c_round = col(dmg, "round_num", "round")
    c_tick = col(dmg, "tick")
    c_att = col(dmg, "attacker_steamid", "attacker_steam_id")
    c_vic = col(dmg, "victim_steamid", "victim_steam_id", "user_steamid")
    c_weapon = col(dmg, "weapon", "weapon_name")
    # dmg_health เป็นดาเมจดิบ นับ overkill ด้วย (ยิงคนเหลือ 38 hp ด้วยกระสุน 121 = 121)
    # dmg_health_real คือเลือดที่หายจริง = min(dmg_health, เลือดก่อนโดน) ซึ่งเป็นนิยาม
    # ที่ HLTV/Leetify ใช้คิด ADR ถ้าใช้ตัวดิบ ADR จะเฟ้อขึ้นราว 40%
    c_dmg = col(dmg, "dmg_health_real", "dmg_health", "damage", "dmg")
    ax, ay, az = col(dmg, "attacker_X", "attacker_x"), col(dmg, "attacker_Y", "attacker_y"), col(dmg, "attacker_Z", "attacker_z")
    vx, vy, vz = col(dmg, "victim_X", "victim_x"), col(dmg, "victim_Y", "victim_y"), col(dmg, "victim_Z", "victim_z")

    events = []
    for row in dmg.to_dicts():
        rnd = round_map.get(to_int(row.get(c_round)))
        if rnd is None:
            continue
        attacker = as_str_id(row.get(c_att)) if c_att else None
        victim = as_str_id(row.get(c_vic)) if c_vic else None
        if attacker not in players or victim not in players:
            continue
        weapon = str(row.get(c_weapon)).lower() if c_weapon and row.get(c_weapon) else None
        events.append(
            {
                "type": "damage",
                "round_number": rnd,
                "tick": to_int(row.get(c_tick)) if c_tick else None,
                "actor_steam64": attacker,
                "victim_steam64": victim,
                "assister_steam64": None,
                # ชื่ออาวุธยูทิลิตี้ทำให้เป็นมาตรฐานเดียว (molotov/incgrenade -> inferno)
                # เพราะ derive.js ใช้ชื่อนี้แยกว่าดาเมจไหนเป็นดาเมจยูทิลิตี้
                "weapon": UTIL_ALIASES.get(weapon, weapon),
                "headshot": False,
                "damage": to_int(row.get(c_dmg)) if c_dmg else None,
                "actor_x": num(row.get(ax)) if ax else None,
                "actor_y": num(row.get(ay)) if ay else None,
                "actor_z": num(row.get(az)) if az else None,
                "victim_x": num(row.get(vx)) if vx else None,
                "victim_y": num(row.get(vy)) if vy else None,
                "victim_z": num(row.get(vz)) if vz else None,
                "meta": None,
            }
        )
    return events


def grenade_name(raw) -> str | None:
    """ "CSmokeGrenadeProjectile" -> "smokegrenade" (ชื่อที่ไม่รู้จักคืนตัวพิมพ์เล็กตามเดิม)"""
    if not raw:
        return None
    key = str(raw).lower()
    return GRENADE_CLASS_ALIASES.get(key, UTIL_ALIASES.get(key, key))


def build_grenade_events(dem, players, round_map, warn) -> list[dict]:
    """
    awpy คืน "เส้นทางการเคลื่อนที่" ของระเบิดเป็นหลายสิบแถวต่อหนึ่งลูก
    เราสนใจแค่ "ขว้างกี่ลูก" จึงเก็บแถวแรกของแต่ละ entity_id ในแต่ละรอบเท่านั้น

    และตารางนี้ปน entity สองแบบ: ลูกที่ "ถืออยู่ในมือ" (CSmokeGrenade, CFlashbang, …
    ถูกติดตามทุก tick ตลอดที่ยังไม่ได้ขว้าง) กับลูกที่ "ขว้างออกไปแล้ว" (ลงท้ายด้วย
    Projectile) ถ้านับรวมทั้งสองแบบ ยอดยูทิลิตี้จะเฟ้อขึ้นเท่าตัว จึงเก็บเฉพาะ
    Projectile — ยกเว้น awpy รุ่นที่ไม่ได้ตั้งชื่อแบบนี้ ให้นับทุกแถวไปตามเดิม
    """
    nades = getattr(dem, "grenades", None)
    if nades is None or nades.is_empty():
        return []

    c_round = col(nades, "round_num", "round")
    c_tick = col(nades, "tick")
    c_thrower = col(nades, "thrower_steamid", "thrower_steam_id", "steamid")
    c_type = col(nades, "grenade_type", "weapon", "type")
    c_entity = col(nades, "entity_id", "grenade_entity_id", "id")
    gx, gy, gz = col(nades, "X", "x"), col(nades, "Y", "y"), col(nades, "Z", "z")
    if not c_thrower:
        warn("grenade data ไม่มีคอลัมน์ผู้ขว้าง — ข้ามส่วนยูทิลิตี้")
        return []

    rows = nades.sort(c_tick or c_round).to_dicts()
    if c_type:
        thrown = [r for r in rows if str(r.get(c_type) or "").lower().endswith("projectile")]
        if thrown:
            rows = thrown
        else:
            warn("grenade data ไม่มี entity แบบ Projectile — นับทุกแถว ยอดอาจเฟ้อ")

    seen = set()
    events = []
    for row in rows:
        rnd = round_map.get(to_int(row.get(c_round)))
        if rnd is None:
            continue
        thrower = as_str_id(row.get(c_thrower))
        if thrower not in players:
            continue
        key = (rnd, row.get(c_entity) if c_entity else (thrower, to_int(row.get(c_tick)) if c_tick else None))
        if key in seen:
            continue
        seen.add(key)
        events.append(
            {
                "type": "grenade",
                "round_number": rnd,
                "tick": to_int(row.get(c_tick)) if c_tick else None,
                "actor_steam64": thrower,
                "victim_steam64": None,
                "assister_steam64": None,
                "weapon": grenade_name(row.get(c_type)) if c_type else None,
                "headshot": False,
                "damage": None,
                "actor_x": num(row.get(gx)) if gx else None,
                "actor_y": num(row.get(gy)) if gy else None,
                "actor_z": num(row.get(gz)) if gz else None,
                "victim_x": None, "victim_y": None, "victim_z": None,
                "meta": {"thrown": True},
            }
        )
    return events


def build_bomb_events(dem, players, round_map) -> list[dict]:
    bomb = getattr(dem, "bomb", None)
    if bomb is None or bomb.is_empty():
        return []

    c_round = col(bomb, "round_num", "round")
    c_tick = col(bomb, "tick")
    c_status = col(bomb, "status", "event", "action")
    c_player = col(bomb, "steamid", "player_steamid", "user_steamid")
    c_site = col(bomb, "site", "bombsite", "which_bomb_zone")
    bx, by, bz = col(bomb, "X", "x"), col(bomb, "Y", "y"), col(bomb, "Z", "z")

    events = []
    for row in bomb.to_dicts():
        rnd = round_map.get(to_int(row.get(c_round)))
        if rnd is None:
            continue
        actor = as_str_id(row.get(c_player)) if c_player else None
        events.append(
            {
                "type": "bomb",
                "round_number": rnd,
                "tick": to_int(row.get(c_tick)) if c_tick else None,
                "actor_steam64": actor if actor in players else None,
                "victim_steam64": None,
                "assister_steam64": None,
                "weapon": "c4",
                "headshot": False,
                "damage": None,
                "actor_x": num(row.get(bx)) if bx else None,
                "actor_y": num(row.get(by)) if by else None,
                "actor_z": num(row.get(bz)) if bz else None,
                "victim_x": None, "victim_y": None, "victim_z": None,
                "meta": {
                    "status": str(row.get(c_status)) if c_status and row.get(c_status) else None,
                    "site": str(row.get(c_site)) if c_site and row.get(c_site) else None,
                },
            }
        )
    return events


def external_id(path: Path, header: dict, map_name: str) -> str:
    """
    คีย์ประจำแมตช์ที่คงที่ — คำนวณจากเนื้อไฟล์ ไม่ใช่ชื่อไฟล์
    เปลี่ยนชื่อไฟล์แล้วโหลดใหม่ต้องไม่กลายเป็นแมตช์ใหม่
    """
    digest = hashlib.sha1()
    with path.open("rb") as fh:
        digest.update(fh.read(2 * 1024 * 1024))  # 2 MB แรกพอแยกแมตช์ได้แล้ว
    digest.update(str(path.stat().st_size).encode())
    return f"{map_name}-{digest.hexdigest()[:12]}"


def parse_demo(path: Path, tickrate: int, verbose: bool) -> dict:
    warnings: list[str] = []

    def warn(msg: str) -> None:
        warnings.append(msg)
        print(f"  ! {msg}", file=sys.stderr)

    print(f"[parse] {path.name} …", file=sys.stderr)
    dem = Demo(path=path, tickrate=tickrate, verbose=verbose)
    dem.parse()

    header = dict(getattr(dem, "header", {}) or {})
    map_name = header.get("map_name") or header.get("map") or "unknown_map"

    players, sides_by_round = build_player_table(dem, warn)
    rounds = build_rounds(dem, players, sides_by_round, warn)
    round_map = {r.pop("_source_round"): r["round_number"] for r in rounds}

    events = []
    events += build_kill_events(dem, players, round_map, warn)
    events += build_damage_events(dem, players, round_map, warn)
    events += build_grenade_events(dem, players, round_map, warn)
    events += build_bomb_events(dem, players, round_map)
    events.sort(key=lambda e: (e["round_number"], e["tick"] or 0))

    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return {
        "schema_version": SCHEMA_VERSION,
        "match": {
            "external_id": external_id(path, header, map_name),
            "map_name": map_name,
            "started_at": None,   # demo ไม่ได้บอกเวลาเริ่มจริง ใช้เวลาไฟล์เป็นตัวแทนเวลาจบ
            "finished_at": mtime.isoformat(),
            "tickrate": tickrate,
            "source": "demo",
            "demo_file": path.name,
            "server_name": header.get("server_name") or None,
        },
        "players": list(players.values()),
        "rounds": rounds,
        "events": events,
        "_warnings": warnings,
    }


def summarize(doc: dict) -> str:
    kinds: dict[str, int] = {}
    for e in doc["events"]:
        kinds[e["type"]] = kinds.get(e["type"], 0) + 1
    score2 = sum(1 for r in doc["rounds"] if r["winner_team_number"] == T_TEAM)
    score3 = len(doc["rounds"]) - score2
    lines = [
        f"  แมตช์  : {doc['match']['external_id']} ({doc['match']['map_name']})",
        f"  ผู้เล่น : {len(doc['players'])} คน",
        f"  รอบ    : {len(doc['rounds'])} (ทีมเริ่ม T {score2} : {score3} ทีมเริ่ม CT)",
        f"  events : {', '.join(f'{k}={v}' for k, v in sorted(kinds.items())) or 'ไม่มี'}",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="แปลงไฟล์ .dem เป็น normalized JSON สำหรับ ETL")
    ap.add_argument("demos", nargs="+", type=Path, help="ไฟล์ .dem หนึ่งไฟล์ขึ้นไป")
    ap.add_argument("-o", "--out", type=Path, help="ไฟล์ปลายทาง หรือโฟลเดอร์ปลายทาง")
    ap.add_argument("--tickrate", type=int, default=64, help="tickrate ของเซิร์ฟเวอร์ (ดีฟอลต์ 64 = matchmaking)")
    ap.add_argument("--summary", action="store_true", help="แสดงสรุปอย่างเดียว ไม่เขียนไฟล์")
    ap.add_argument("--pretty", action="store_true", help="จัดรูปแบบ JSON ให้อ่านง่าย (ไฟล์ใหญ่ขึ้นมาก)")
    ap.add_argument("--verbose", action="store_true", help="แสดง log ของ awpy ด้วย")
    args = ap.parse_args()

    failed = 0
    for demo_path in args.demos:
        if not demo_path.exists():
            print(f"✗ ไม่พบไฟล์: {demo_path}", file=sys.stderr)
            failed += 1
            continue
        try:
            doc = parse_demo(demo_path, args.tickrate, args.verbose)
        except SystemExit as exc:
            print(f"✗ {demo_path.name}: {exc}", file=sys.stderr)
            failed += 1
            continue
        except Exception as exc:  # noqa: BLE001 — อยากให้ไฟล์อื่นที่เหลือ parse ต่อได้
            print(f"✗ {demo_path.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            failed += 1
            continue

        print(summarize(doc), file=sys.stderr)
        if args.summary:
            continue

        doc.pop("_warnings", None)
        if args.out and args.out.is_dir():
            target = args.out / f"{doc['match']['external_id']}.json"
        elif args.out:
            target = args.out
        else:
            target = Path(f"{doc['match']['external_id']}.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2 if args.pretty else None),
            encoding="utf-8",
        )
        print(f"✓ เขียน {target}", file=sys.stderr)
        # บรรทัดเดียวที่ลง stdout และเป็น ASCII ล้วน — ให้โปรแกรมอื่นอ่าน path ต่อได้
        # โดยไม่ต้องแกะข้อความไทย ซึ่งพึ่งการเข้ารหัสของคอนโซล (หน้าอัปโหลดใช้บรรทัดนี้)
        print(f"OUTPUT_JSON={target}", flush=True)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
