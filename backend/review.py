# -*- coding: utf-8 -*-
"""
backend/review.py — ประกอบข้อมูลหน้า Round Review จากแถวในฐานข้อมูล + output/grid_ml1.json

    ฟังก์ชันทุกตัวรับ dict/list ธรรมดา ไม่แตะฐานข้อมูลเอง — app.py เป็นคน query แล้วส่งเข้ามา
    จึงทดสอบด้วย pytest ได้โดยไม่ต้องมี PostgreSQL

grid_ml1.json
    อ่านครั้งเดียวแล้วเก็บในหน่วยความจำ (อ่านใหม่เฉพาะเมื่อไฟล์ถูกเขียนทับ) — ไม่รัน grid_ml1.py ตอน request
    ตัวเลขทุกตัวในนั้นมาจาก "ทั้งดาต้าเซ็ต N แมตช์" (รวมแมตช์ที่กำลังดูอยู่ด้วย) ไม่ใช่จากรอบนี้
    ct_win = สัดส่วนที่ CT เป็นฝ่ายชนะ "การดวล" ในช่อง/กลุ่มนั้น — ไม่ใช่โอกาสชนะรอบ
"""
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from backend.features.definitions import other_side
from backend.geo import RadarFrame, cell_of, cell_rect_pixel, nearest_within, world_to_pixel

ROOT = Path(__file__).resolve().parent.parent
GRID_JSON = Path(os.environ.get("GRID_ML1_JSON", ROOT / "output" / "grid_ml1.json"))

# สีประจำตัวผู้เล่น — ไม่ผูกกับสี CT/T เพราะทีมสลับฝั่งทุกครึ่ง (ทีมเดียวกันต้องสีเดิมทั้งแมตช์)
TEAM_PALETTES = (
    ("#22d3ee", "#34d399", "#a3e635", "#60a5fa", "#2dd4bf", "#86efac"),   # ทีมแรก (เรียงตามชื่อ): โทนฟ้า-เขียว
    ("#f472b6", "#c084fc", "#fb7185", "#facc15", "#fb923c", "#e879f9"),   # ทีมที่สอง: โทนชมพู-ม่วง-เหลือง
)
UNKNOWN_COLOUR = "#94a3b8"


# ---------------------------------------------------------------------------
# grid_ml1.json
# ---------------------------------------------------------------------------
@dataclass
class GridModel:
    map_name: str
    grid_n: int
    min_kills: int
    matches: int
    duels: int
    ct_win_overall: float
    bandwidth: float
    clusters: dict[int, dict]
    cells: dict[tuple[int, int], dict]
    hotspots: list[dict] = field(default_factory=list)

    @property
    def source(self) -> dict:
        """ข้อความอ้างที่มาที่ UI ต้องแสดงคู่กับตัวเลขเสมอ (กฎข้อ 1)"""
        return {"matches": self.matches, "duels": self.duels, "map": self.map_name,
                "label": f"ทั้งดาต้าเซ็ต {self.matches} แมตช์ ({self.duels:,} การดวลบน {self.map_name})"}


_cache: dict[str, tuple[float, GridModel]] = {}


def parse_grid_model(d: dict) -> GridModel:
    m = d["metrics"]
    return GridModel(
        map_name=d["map"], grid_n=int(d["grid_n"]), min_kills=int(d["min_kills"]),
        matches=int(m["matches"]), duels=int(m["duels"]), ct_win_overall=float(m["ct_win_overall"]),
        bandwidth=float(m["bandwidth"]),
        clusters={int(c["id"]): c for c in d["clusters"]},             # id เริ่มที่ 1 เรียงต้นรอบ -> ท้ายรอบ (เบอร์เดียวกับรูป)
        cells={(int(c["cx"]), int(c["cy"])): c for c in d["cells"]},
        hotspots=list(d["hotspots"]),
    )


def load_grid_model(path: Path = GRID_JSON) -> GridModel | None:
    """grid_ml1.json แบบ cache ในหน่วยความจำ — None ถ้ายังไม่เคยรัน research/grid_ml1.py"""
    path = Path(path)
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return None
    hit = _cache.get(str(path))
    if hit and hit[0] == mtime:
        return hit[1]
    model = parse_grid_model(json.loads(path.read_text(encoding="utf-8")))
    _cache[str(path)] = (mtime, model)
    return model


def grid_overlay(model: GridModel, frame: RadarFrame) -> dict:
    """ข้อมูลสำหรับ toggle ซ้อนบนแผนที่: ช่องทุกช่องเป็นพิกเซล + วง hotspot — คำนวณพิกเซลที่นี่ ไม่ใช่ใน frontend"""
    cells = []
    for (cx, cy), c in sorted(model.cells.items()):
        x, y, w = cell_rect_pixel(cx, cy, frame, model.grid_n)
        cells.append({"cx": cx, "cy": cy, "cluster_id": int(c["cluster"]), "x": x, "y": y, "w": w})
    hotspots = []
    for h in model.hotspots:
        px, py = world_to_pixel(h["x"], h["y"], frame)
        hotspots.append({"id": h["id"], "place": h["place"], "share": h["share"], "duels": h["duels"],
                         "ct_win": h["ct_win"], "px": px, "py": py, "r": h["radius"] / frame.scale})
    clusters = [{"id": cid, "name": c["name"], "ct_win": c["ct_win"], "n_cells": c["n_cells"], "duels": c["duels"]}
                for cid, c in sorted(model.clusters.items())]
    return {"available": True, "source": model.source, "ct_win_overall": model.ct_win_overall,
            "min_kills": model.min_kills, "clusters": clusters, "cells": cells, "hotspots": hotspots}


# ---------------------------------------------------------------------------
# บริบทของการตายหนึ่งครั้ง
# ---------------------------------------------------------------------------
def death_context(x: float | None, y: float | None, victim_side: str | None, is_duel: bool,
                  model: GridModel | None, frame: RadarFrame | None) -> dict:
    """ช่อง / กลุ่ม / hotspot ที่จุดตายตกอยู่ ตาม grid_ml1 — ไม่มีข้อมูลก็บอกว่าไม่มี ไม่เดา ไม่เฉลี่ยจากช่องข้าง ๆ

    reason: None = มีข้อมูลครบ | "no_model" = ยังไม่มี grid_ml1 ของแมพนี้
            "insufficient" = ช่องนี้มีดวลน้อยกว่า MIN_KILLS ใน grid_ml1 | "no_position" = ไม่มีพิกัด
    """
    out = {"cell": None, "hotspot": None, "reason": None, "disadvantaged": None, "enemy_win": None}
    if x is None or y is None:
        out["reason"] = "no_position"
        return out
    if model is None or frame is None or model.map_name != frame.map_name:
        out["reason"] = "no_model"
        return out

    cx, cy = cell_of(x, y, frame, model.grid_n)
    cell = model.cells.get((cx, cy))
    if cell is None:
        out["reason"] = "insufficient"
        out["cell_xy"] = {"cx": cx, "cy": cy}
        return out
    cid = int(cell["cluster"])
    cluster = model.clusters[cid]
    ct_win = float(cluster["ct_win"])
    out["cell"] = {"cx": cx, "cy": cy, "cluster_id": cid, "cluster_name": cluster["name"], "ct_win": ct_win,
                   "cell_ct_win": float(cell["ct_win"]), "cell_duels": int(cell["kills"])}

    i = nearest_within(x, y, [(h["x"], h["y"]) for h in model.hotspots], model.bandwidth)
    if i is not None:
        h = model.hotspots[i]
        out["hotspot"] = {"id": h["id"], "place": h["place"], "share": h["share"]}

    # "ช่องเสียเปรียบ" = ฝั่งตรงข้ามของคนตายชนะดวลในกลุ่มนี้เกินครึ่ง (ข้อเท็จจริงจากดาต้าเซ็ต ไม่ใช่การตัดสินคน)
    if victim_side in ("ct", "t"):
        enemy = other_side(victim_side)
        out["enemy_win"] = ct_win if enemy == "ct" else 1 - ct_win
        if is_duel:
            out["disadvantaged"] = out["enemy_win"] > 0.5
    return out


# ---------------------------------------------------------------------------
# ประกอบ payload
# ---------------------------------------------------------------------------
def _t(tick, start_tick, tickrate) -> float | None:
    if tick is None or start_tick is None or not tickrate:
        return None
    return round((int(tick) - int(start_tick)) / int(tickrate), 1)


def player_colours(roster: list[dict]) -> dict[int, str]:
    """สีต่อคน คงที่ทั้งแมตช์: ทีมเรียงตามชื่อ คนในทีมเรียงตาม steam_id"""
    teams = sorted({r["team"] or "" for r in roster})
    out = {}
    for ti, team in enumerate(teams):
        palette = TEAM_PALETTES[ti] if ti < len(TEAM_PALETTES) else (UNKNOWN_COLOUR,)
        members = sorted(int(r["steam_id"]) for r in roster if (r["team"] or "") == team)
        for i, sid in enumerate(members):
            out[sid] = palette[i % len(palette)]
    return out


def build_round_list(rounds: list[dict], first_deaths: dict[int, int], death_counts: dict[int, int],
                     tickrate: int) -> list[dict]:
    return [{
        "round_num": r["round_num"], "winner_side": r["winner_side"], "end_reason": r["end_reason"],
        "deaths_count": death_counts.get(r["round_num"], 0),
        "first_death_t": _t(first_deaths.get(r["round_num"]), r["start_tick"], tickrate),
    } for r in rounds]


def build_round_detail(*, match: dict, rnd: dict, roster: list[dict], in_round: list[dict], kills: list[dict],
                       frame: RadarFrame | None, model: GridModel | None) -> dict:
    """payload ของหนึ่งรอบ

    match    {id, demo_file, map_name, tickrate, team_a, team_b}
    rnd      {round_num, start_tick, winner_side, end_reason, bomb_plant_tick, bomb_plant_x, bomb_plant_y, bomb_site}
    roster   ทุกคนในแมตช์ [{steam_id, name, team}]  — ใช้ให้สีคงที่ทั้งแมตช์
    in_round คนที่เล่นรอบนี้ [{steam_id, side, survived}]
    kills    การตายในรอบนี้ เรียงตาม tick แล้ว (คอลัมน์ตามตาราง kills + attacker_name/victim_name/assister_name)
    """
    tickrate = int(match["tickrate"] or 128)
    start = rnd["start_tick"]
    colours = player_colours(roster)
    info = {int(r["steam_id"]): r for r in roster}
    side_now = {int(p["steam_id"]): p["side"] for p in in_round}

    def person(sid, name, side) -> dict | None:
        if sid is None:
            return None
        sid = int(sid)
        return {"steamid": str(sid), "name": name or info.get(sid, {}).get("name") or str(sid),
                "side": side or side_now.get(sid), "team": info.get(sid, {}).get("team"),
                "color": colours.get(sid, UNKNOWN_COLOUR)}

    deaths = []
    for i, k in enumerate(kills, 1):
        victim = person(k["victim_id"], k.get("victim_name"), k.get("victim_side"))
        attacker = person(k.get("attacker_id"), k.get("attacker_name"), k.get("attacker_side"))
        is_duel = bool(attacker) and k.get("attacker_side") in ("ct", "t") and k.get("attacker_side") != k.get("victim_side")
        vx, vy, ax, ay = k.get("victim_x"), k.get("victim_y"), k.get("attacker_x"), k.get("attacker_y")
        vpx = world_to_pixel(vx, vy, frame) if frame and vx is not None and vy is not None else None
        apx = world_to_pixel(ax, ay, frame) if frame and ax is not None and ay is not None else None
        ctx = death_context(vx, vy, k.get("victim_side"), is_duel, model, frame)
        deaths.append({
            "order": i, "tick": int(k["tick"]), "t_round": _t(k["tick"], start, tickrate),
            "victim": victim, "attacker": attacker,
            "assister": k.get("assister_name"),
            "is_duel": is_duel, "team_kill": bool(attacker) and not is_duel and k.get("attacker_side") == k.get("victim_side"),
            "weapon": k.get("weapon"), "headshot": bool(k.get("headshot")),
            "attacker_blind": bool(k.get("attacker_blind")), "thru_smoke": bool(k.get("thru_smoke")),
            "noscope": bool(k.get("noscope")), "penetrated": int(k.get("penetrated") or 0),
            # ระยะในหน่วยเกม คิดจากพิกัดเอง (ตัวเดียวกับ dist_xy ของ grid_ml1) — คอลัมน์ distance ของ parser คนละหน่วย
            "distance": round(math.hypot(ax - vx, ay - vy)) if None not in (ax, ay, vx, vy) else None,
            "victim_X": vx, "victim_Y": vy, "attacker_X": ax, "attacker_Y": ay,
            "victim_px": vpx, "attacker_px": apx,
            "place": k.get("victim_place"), "attacker_place": k.get("attacker_place"),
            **ctx,
        })

    # ---- ทีม: จัดตาม team_clan ไม่ใช่ side; หัวกล่องบอก side ของรอบนี้ ----
    teams: dict[str, dict] = {}
    for sid in sorted(side_now):
        p = info.get(sid, {"name": str(sid), "team": None})
        team = p.get("team") or ("?")
        t = teams.setdefault(team, {"clan": team, "side_this_round": side_now[sid], "players": []})
        death = next((d for d in deaths if d["victim"] and d["victim"]["steamid"] == str(sid)), None)
        t["players"].append({
            "name": p.get("name") or str(sid), "steamid": str(sid), "color": colours.get(sid, UNKNOWN_COLOUR),
            "side": side_now[sid],
            "survived": death is None,
            "died_at_t": death["t_round"] if death else None,
            "killed_by": (death["attacker"]["name"] if death and death["attacker"] else None),
            "weapon": death["weapon"] if death else None,
            "death_order": death["order"] if death else None,
            "kills": sum(1 for d in deaths if d["is_duel"] and d["attacker"] and d["attacker"]["steamid"] == str(sid)),
        })
    team_list = sorted(teams.values(), key=lambda t: (t["side_this_round"] != "ct", t["clan"]))   # CT ซ้าย/บน

    bomb = None
    if rnd.get("bomb_plant_x") is not None and rnd.get("bomb_plant_y") is not None:
        px = world_to_pixel(rnd["bomb_plant_x"], rnd["bomb_plant_y"], frame) if frame else None
        bomb = {"x": rnd["bomb_plant_x"], "y": rnd["bomb_plant_y"], "px": px, "site": rnd.get("bomb_site")}

    # ---- สรุปรอบ ----
    winner = rnd.get("winner_side")
    first = deaths[0] if deaths else None
    disadv = {"ct": 0, "t": 0}
    for d in deaths:
        if d["disadvantaged"] and d["victim"] and d["victim"]["side"] in disadv:
            disadv[d["victim"]["side"]] += 1
    summary = {
        "first_death": None if not first else {
            "order": 1, "name": first["victim"]["name"], "side": first["victim"]["side"],
            "place": first["place"], "t_round": first["t_round"],
            "by": first["attacker"]["name"] if first["attacker"] else None,
        },
        # ฝั่งที่เสียคนแรกของรอบ แพ้รอบนั้นไหม (None = ไม่มีคนตาย หรือไม่รู้ผลรอบ)
        "first_death_side_lost": (first["victim"]["side"] != winner) if first and winner in ("ct", "t") else None,
        "disadvantaged_deaths": disadv,
        "duel_deaths": sum(d["is_duel"] for d in deaths),
        "deaths_with_context": sum(d["cell"] is not None for d in deaths),
    }

    return {
        "match": {k: match.get(k) for k in ("id", "demo_file", "map_name", "tickrate", "team_a", "team_b")},
        "round": {"num": rnd["round_num"], "winner_side": winner, "end_reason": rnd.get("end_reason"),
                  "bomb_planted_t": _t(rnd.get("bomb_plant_tick"), start, tickrate), "bomb": bomb},
        "radar": None if not frame else {"image": "/assets" + frame.image, "size": frame.size, "map": frame.map_name},
        "grid": None if not model or not frame or model.map_name != frame.map_name else {
            "source": model.source, "ct_win_overall": model.ct_win_overall, "min_kills": model.min_kills},
        "teams": team_list,
        "deaths": deaths,
        "summary": summary,
    }
