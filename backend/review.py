# -*- coding: utf-8 -*-
"""
backend/review.py — ประกอบข้อมูลหน้า Round Review จากแถวในฐานข้อมูล + output/grid_ml1.json
    ส่วนแรกของไฟล์คือสูตรแปลงพิกัดเกม -> ช่องกริด / พิกเซลเรดาร์ (ห้ามเขียนสูตรนี้ที่อื่น)

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
from functools import lru_cache
from pathlib import Path

import numpy as np

from backend.features import other_side

# ==================================================================================================
# พิกัด: เกม <-> ช่องกริด / พิกเซลบนภาพเรดาร์ (สูตรชุดเดียวของทั้งรีโป)
# backend/review.py — แปลงพิกัดในเกม <-> ช่องกริด / พิกเซลบนภาพเรดาร์  (สูตรชุดเดียวของทั้งรีโป)
#
#     from backend.review import radar_frame, cells_of, cell_of, world_to_pixel
#     frame = radar_frame("de_mirage")
#     cx, cy = cell_of(x, y, frame, grid_n=32)        # ช่องไหนของกริด (เหมือน research/grid_ml1.py เป๊ะ)
#     px, py = world_to_pixel(x, y, frame)            # พิกเซลบนภาพเรดาร์ (มุมบนซ้าย = 0, 0)
#
# ที่มาของสูตร
#     ยกมาจาก research/grid_ml1.py (STEP 5) ซึ่งตรวจแล้วว่าถูก — ตอนนี้ grid_ml1.py import จากที่นี่แทน
#     ขอบเขตกริดเอาจากภาพเรดาร์ (assets/radars.json) ไม่ใช่จากค่าต่ำสุด-สูงสุดของข้อมูล
#     ช่องจึงไม่ขยับเมื่อเพิ่มเดโม และช่องที่ API คำนวณตรงกับช่องใน grid_ml1.json เสมอ
#
#     ห้ามเขียนสูตรแปลงพิกัดที่อื่นอีก — ถ้าต้องการแปลงพิกัด ให้ import จากไฟล์นี้
# ==================================================================================================
ROOT = Path(__file__).resolve().parent.parent
RADARS_JSON = ROOT / "assets" / "radars.json"


@dataclass(frozen=True)
class RadarFrame:
    """ค่าปรับเทียบภาพเรดาร์ของแมพหนึ่ง (จาก radars.json) + ขอบเขตที่ภาพกินในพิกัดเกม"""
    map_name: str
    image: str      # path ภายใต้ assets/ เช่น "/maps/de_mirage.png"
    size: int       # ภาพเป็นจัตุรัส size x size พิกเซล
    pos_x: float    # พิกัดเกมของมุมบนซ้ายของภาพ
    pos_y: float
    scale: float    # หนึ่งพิกเซล = กี่หน่วยเกม

    @property
    def span(self) -> float:
        """ความกว้างของภาพเป็นหน่วยเกม (1024 พิกเซล x 5.0 = 5120 บน Mirage)"""
        return self.size * self.scale

    @property
    def x_left(self) -> float:
        return self.pos_x

    @property
    def x_right(self) -> float:
        return self.pos_x + self.span

    @property
    def y_top(self) -> float:
        return self.pos_y            # แกน y ในเกมนับขึ้น ขอบบนของภาพจึงเป็นค่ามาก

    @property
    def y_bottom(self) -> float:
        return self.pos_y - self.span

    @property
    def extent(self) -> tuple[float, float, float, float]:
        """(x_left, x_right, y_bottom, y_top) — แบบที่ matplotlib imshow(extent=...) ต้องการ"""
        return (self.x_left, self.x_right, self.y_bottom, self.y_top)

    def cell_size(self, grid_n: int) -> float:
        return self.span / grid_n


def load_radars() -> dict:
    return json.loads(RADARS_JSON.read_text(encoding="utf-8"))


@lru_cache(maxsize=32)
def radar_frame(map_name: str) -> RadarFrame | None:
    """ค่าปรับเทียบของแมพ — None ถ้าแมพนี้ยังไม่มีใน radars.json"""
    r = load_radars().get(map_name)
    if not isinstance(r, dict):
        return None
    return RadarFrame(map_name, r["image"], int(r["size"]), float(r["pos_x"]), float(r["pos_y"]), float(r["scale"]))


def cells_of(xs, ys, frame: RadarFrame, grid_n: int) -> tuple[np.ndarray, np.ndarray]:
    """พิกัดเกม -> ช่องกริด (cx, cy) แบบ vectorized — สูตรเดียวกับ research/grid_ml1.py

    (พิกัด - ขอบ) // ขนาดช่อง = อยู่ช่องที่เท่าไร
    np.clip บีบให้อยู่ในช่วง 0 ถึง grid_n-1 กันจุดที่ตกริมขอบพอดีหลุดออกนอกตาราง
    cy นับจากขอบล่าง (y_bottom) ขึ้นไป — แถว 0 คือแถวล่างสุดของแมพ
    """
    cell = frame.cell_size(grid_n)
    cx = np.clip((np.asarray(xs, dtype=float) - frame.x_left) // cell, 0, grid_n - 1).astype(int)
    cy = np.clip((np.asarray(ys, dtype=float) - frame.y_bottom) // cell, 0, grid_n - 1).astype(int)
    return cx, cy


def cell_of(x: float, y: float, frame: RadarFrame, grid_n: int) -> tuple[int, int]:
    """จุดเดียว — เรียกตัว vectorized ข้างบน เพื่อให้ผลตรงกันทุกทศนิยม ไม่มีสูตรสองชุด"""
    cx, cy = cells_of([x], [y], frame, grid_n)
    return int(cx[0]), int(cy[0])


def cell_rect_world(cx: int, cy: int, frame: RadarFrame, grid_n: int) -> tuple[float, float, float, float]:
    """ขอบของช่องในพิกัดเกม (x0, y0, x1, y1) — y0 คือขอบล่าง"""
    cell = frame.cell_size(grid_n)
    x0 = frame.x_left + cx * cell
    y0 = frame.y_bottom + cy * cell
    return x0, y0, x0 + cell, y0 + cell


def world_to_pixel(x: float, y: float, frame: RadarFrame) -> tuple[float, float]:
    """พิกัดเกม -> พิกเซลบนภาพเรดาร์ (มุมบนซ้ายของภาพ = 0, 0 และ y พิกเซลนับลง)

    ตรงกับ imshow(extent=frame.extent, origin="upper") ที่ grid_ml1.py ใช้วาดรูป
    """
    return (x - frame.pos_x) / frame.scale, (frame.pos_y - y) / frame.scale


def cell_rect_pixel(cx: int, cy: int, frame: RadarFrame, grid_n: int) -> tuple[float, float, float]:
    """มุมบนซ้ายของช่องเป็นพิกเซล + ความกว้างช่องเป็นพิกเซล (x, y, w) — ช่องเป็นจัตุรัส"""
    x0, _, _, y1 = cell_rect_world(cx, cy, frame, grid_n)
    px, py = world_to_pixel(x0, y1, frame)
    return px, py, frame.cell_size(grid_n) / frame.scale


def in_frame(x: float, y: float, frame: RadarFrame) -> bool:
    """จุดนี้อยู่บนภาพเรดาร์ไหม (ถ้าไม่อยู่ วาดแล้วจะหลุดขอบรูป)"""
    return frame.x_left <= x < frame.x_right and frame.y_bottom < y <= frame.y_top


def nearest_within(x: float, y: float, centers: list[tuple[float, float]], radius: float) -> int | None:
    """index ของจุดศูนย์กลางที่ใกล้ที่สุด ถ้าห่างไม่เกิน radius — ไม่งั้น None

    กฎเดียวกับที่ sklearn MeanShift(cluster_all=False) ใช้แปะป้ายจุดตอน grid_ml1 หา hotspot:
    ยอดที่ใกล้ที่สุด และระยะ <= bandwidth  (เกินจากนั้น = ไม่อยู่ใน hotspot ไหน)
    """
    if not centers:
        return None
    c = np.asarray(centers, dtype=float)
    d = np.hypot(c[:, 0] - x, c[:, 1] - y)
    i = int(np.argmin(d))
    return i if d[i] <= radius else None


# ==================================================================================================
# ข้อมูลหน้ารอบ (Round Review) + grid_ml1.json
# ==================================================================================================
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


# ควัน / ไฟ อยู่นานเท่าไรถ้าเดโมไม่มี event ตอนหมด (ค่าในเกม CS2) — แฟลช / HE ทำงานทันทีที่แตก
NADE_DEFAULT_SEC = {"smoke": 20.0, "molotov": 7.0}
# รัศมีที่วาดบนแผนที่ (หน่วยเกม) — ขนาดโดยประมาณของกลุ่มควันและกองไฟ ลูกอื่นวาดเป็นจุด
NADE_RADIUS = {"smoke": 144, "molotov": 120}


def _person_factory(roster: list[dict], in_round: list[dict]):
    """คืน (person, info, side_now, colours) — person(sid, name, side) ประกอบข้อมูลคนหนึ่งคนให้หน้าเว็บ

    สีมาจาก roster ทั้งแมตช์ ไม่ใช่เฉพาะรอบนี้ คนคนเดิมจึงได้สีเดิมทุกรอบ
    """
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

    return person, info, side_now, colours


def _death_rows(kills: list[dict], person, *, start, tickrate: int,
                frame: RadarFrame | None, model: GridModel | None) -> list[dict]:
    """การตายทุกครั้งในรอบ พร้อมพิกเซลบนเรดาร์และบริบทจาก grid_ml1"""
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
    return deaths


def _nade_rows(grenades: list[dict], person, *, start, tickrate: int, frame: RadarFrame | None) -> list[dict]:
    """ระเบิด: จุดตก (วาดวง) + จุดขว้าง (เส้นประ) เป็นพิกเซล และช่วงเวลาที่มีผล"""
    nades = []
    for g in grenades:
        land_t, end_t = _t(g.get("land_tick"), start, tickrate), _t(g.get("end_tick"), start, tickrate)
        if land_t is not None and (end_t is None or end_t < land_t):
            end_t = round(land_t + NADE_DEFAULT_SEC.get(g["type"], 0.0), 1)
        tx, ty, lx, ly = g.get("throw_x"), g.get("throw_y"), g.get("land_x"), g.get("land_y")
        nades.append({
            "type": g["type"],
            "thrower": person(g.get("thrower_id"), g.get("thrower_name"), g.get("side")),
            "t_throw": _t(g["tick"], start, tickrate), "t_land": land_t, "t_end": end_t,
            "throw_px": world_to_pixel(tx, ty, frame) if frame and None not in (tx, ty) else None,
            "land_px": world_to_pixel(lx, ly, frame) if frame and None not in (lx, ly) else None,
            "r_px": round(NADE_RADIUS.get(g["type"], 0) / frame.scale, 1) if frame else 0,
        })
    return nades


def _team_rows(side_now: dict[int, str], info: dict[int, dict], colours: dict[int, str],
               deaths: list[dict]) -> list[dict]:
    """จัดกล่องทีมตาม team_clan ไม่ใช่ side; หัวกล่องบอก side ของรอบนี้ CT อยู่ซ้าย/บน"""
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
    return sorted(teams.values(), key=lambda t: (t["side_this_round"] != "ct", t["clan"]))


def _bomb_marker(rnd: dict, frame: RadarFrame | None) -> dict | None:
    """ไอคอนบอมบ์บนแผนที่ — None ถ้ารอบนั้นไม่มีการวาง"""
    if rnd.get("bomb_plant_x") is None or rnd.get("bomb_plant_y") is None:
        return None
    px = world_to_pixel(rnd["bomb_plant_x"], rnd["bomb_plant_y"], frame) if frame else None
    return {"x": rnd["bomb_plant_x"], "y": rnd["bomb_plant_y"], "px": px, "site": rnd.get("bomb_site")}


def _round_summary(deaths: list[dict], winner: str | None) -> dict:
    """สรุปรอบ: ใครตายคนแรก ฝั่งนั้นแพ้ไหม และการตายแบบเสียเปรียบของแต่ละฝั่ง"""
    first = deaths[0] if deaths else None
    disadv = {"ct": 0, "t": 0}
    for d in deaths:
        if d["disadvantaged"] and d["victim"] and d["victim"]["side"] in disadv:
            disadv[d["victim"]["side"]] += 1
    return {
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


def build_round_detail(*, match: dict, rnd: dict, roster: list[dict], in_round: list[dict], kills: list[dict],
                       frame: RadarFrame | None, model: GridModel | None, grenades: list[dict] = ()) -> dict:
    """payload ของหนึ่งรอบ

    match    {id, demo_file, map_name, tickrate, team_a, team_b}
    rnd      {round_num, start_tick, winner_side, end_reason, bomb_plant_tick, bomb_plant_x, bomb_plant_y, bomb_site}
    roster   ทุกคนในแมตช์ [{steam_id, name, team}]  — ใช้ให้สีคงที่ทั้งแมตช์
    in_round คนที่เล่นรอบนี้ [{steam_id, side, survived}]
    kills    การตายในรอบนี้ เรียงตาม tick แล้ว (คอลัมน์ตามตาราง kills + attacker_name/victim_name/assister_name)
    grenades ระเบิดในรอบนี้ (คอลัมน์ตามตาราง grenades + thrower_name) — ใครขว้างอะไร จากไหน ตกที่ไหน
    """
    tickrate = int(match["tickrate"] or 128)
    start = rnd["start_tick"]
    winner = rnd.get("winner_side")
    person, info, side_now, colours = _person_factory(roster, in_round)

    deaths = _death_rows(kills, person, start=start, tickrate=tickrate, frame=frame, model=model)
    nades = _nade_rows(grenades, person, start=start, tickrate=tickrate, frame=frame)

    return {
        "match": {k: match.get(k) for k in ("id", "demo_file", "map_name", "tickrate", "team_a", "team_b")},
        "round": {"num": rnd["round_num"], "winner_side": winner, "end_reason": rnd.get("end_reason"),
                  "bomb_planted_t": _t(rnd.get("bomb_plant_tick"), start, tickrate), "bomb": _bomb_marker(rnd, frame)},
        "radar": None if not frame else {"image": "/assets" + frame.image, "size": frame.size, "map": frame.map_name},
        "grid": None if not model or not frame or model.map_name != frame.map_name else {
            "source": model.source, "ct_win_overall": model.ct_win_overall, "min_kills": model.min_kills},
        "teams": _team_rows(side_now, info, colours, deaths),
        "deaths": deaths,
        "grenades": nades,
        "summary": _round_summary(deaths, winner),
    }


# ---------------------------------------------------------------------------
# โหมดเล่นย้อน (playback): ตำแหน่งผู้เล่นรายวินาทีของหนึ่งรอบ
#   parser เก็บตำแหน่งวินาทีละครั้ง (1 Hz) เฉพาะช่วงที่รอบเล่นอยู่และเฉพาะคนที่ยังไม่ตาย
#   -> คนที่ตายแล้วหายไปจากเฟรมเอง และไม่มีข้อมูลช่วงซื้อของก่อน freeze จบ
#   ที่นี่แปลงเป็นพิกเซลบนภาพเรดาร์ให้เลย หน้าเว็บจึงไม่ต้องมีสูตรแปลงพิกัดของตัวเอง (กฎเดียวกับส่วนอื่นของไฟล์นี้)
# ---------------------------------------------------------------------------
POSITION_HZ = 1.0        # ความถี่ที่เดโมถูกเก็บ — ระหว่างสองเฟรมหน้าเว็บวาดประมาณให้ต่อเนื่อง ไม่ใช่ข้อมูลจริง


def build_round_positions(positions: list[dict], *, start_tick, tickrate: int, frame: RadarFrame | None) -> dict:
    """[{tick, steam_id, side, x, y, health, place}] -> {step, t_end, frames:[{t, players:[...]}]}"""
    by_t: dict[float, list[dict]] = {}
    for r in positions:
        t = _t(r["tick"], start_tick, tickrate)
        if t is None or r.get("x") is None or r.get("y") is None or frame is None:
            continue
        px, py = world_to_pixel(r["x"], r["y"], frame)
        by_t.setdefault(t, []).append({
            "steamid": str(r["steam_id"]),
            "px": [round(px, 1), round(py, 1)],
            "hp": int(r.get("health") or 0),
            "side": r.get("side"),
            "place": r.get("place"),
        })
    frames = [{"t": t, "players": sorted(pl, key=lambda p: p["steamid"])} for t, pl in sorted(by_t.items())]
    return {
        "step": POSITION_HZ,
        "t_end": frames[-1]["t"] if frames else 0.0,
        "frames": frames,
        # ข้อความนี้ให้หน้าเว็บแสดงกำกับเสมอ — ผู้ใช้ต้องรู้ว่าอะไรคือข้อมูลจริง อะไรคือการวาดประมาณ
        "note": "ตำแหน่งถูกเก็บวินาทีละครั้ง · ช่วงระหว่างวินาทีเป็นการวาดให้ต่อเนื่อง ไม่ใช่ข้อมูลจากเดโม",
    }

