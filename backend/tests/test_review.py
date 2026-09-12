# -*- coding: utf-8 -*-
"""หน้ารอบ (backend/review.py): สูตรพิกัด = grid_ml1 · payload บนเดโมจริง · กติกาข้อความใน UI"""
import json
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

from backend.features import assign_teams
from backend.review import (
    build_round_detail,
    build_round_list,
    cell_rect_world,
    cells_of,
    death_context,
    grid_overlay,
    in_frame,
    nearest_within,
    parse_grid_model,
    radar_frame,
    world_to_pixel,
)

# ==================================================================================================
# สูตรพิกัดใน backend/review.py ต้องให้ผลเดียวกับ research/grid_ml1.py และจุดที่วาดต้องอยู่บนภาพเรดาร์เสมอ
# ==================================================================================================
ROOT = Path(__file__).resolve().parent.parent.parent
FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def kills() -> pd.DataFrame:
    return pd.read_csv(ROOT / "data" / "all_kills.csv")


@pytest.fixture(scope="module")
def model():
    return parse_grid_model(json.loads((FIX / "grid_ml1.json").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def cells_csv() -> pd.DataFrame:
    return pd.read_csv(FIX / "grid_ml1_cells.csv")


@pytest.fixture(scope="module")
def frame():
    return radar_frame("de_mirage")


def duels(df: pd.DataFrame) -> pd.DataFrame:
    """ตัวกรองเดียวกับ grid_ml1.py STEP 4: มีคนยิง และคนละฝั่ง"""
    d = df[df["map_name"] == "de_mirage"]
    return d[d["attacker_side"].notna() & (d["attacker_side"] != d["victim_side"])]


def test_every_death_point_drawn_is_inside_the_radar(kills, frame):
    for who in ("victim", "attacker"):
        d = kills.dropna(subset=[f"{who}_X", f"{who}_Y"])
        assert len(d) > 7000
        outside = [(x, y) for x, y in zip(d[f"{who}_X"], d[f"{who}_Y"], strict=True) if not in_frame(x, y, frame)]
        assert outside == [], f"{who}: {len(outside)} จุดหลุดกรอบเรดาร์"
        for x, y in zip(d[f"{who}_X"], d[f"{who}_Y"], strict=True):
            px, py = world_to_pixel(x, y, frame)
            assert 0 <= px <= frame.size and 0 <= py <= frame.size


def test_pixel_and_extent_agree(frame):
    # มุมบนซ้ายของภาพ = (0, 0), มุมล่างขวา = (size, size)
    assert world_to_pixel(frame.x_left, frame.y_top, frame) == (0, 0)
    assert world_to_pixel(frame.x_right, frame.y_bottom, frame) == (frame.size, frame.size)


def test_cells_reproduce_grid_ml1_duel_counts(kills, cells_csv, model, frame):
    """นับดวลต่อช่องด้วย backend.review แล้วต้องได้ช่องชุดเดียวกัน จำนวนเท่ากันทุกช่องกับ grid_ml1_cells.csv"""
    d = duels(kills)
    cx, cy = cells_of(d["victim_X"], d["victim_Y"], frame, model.grid_n)
    counts = Counter(zip(cx.tolist(), cy.tolist(), strict=True))
    kept = {c: n for c, n in counts.items() if n >= model.min_kills}
    expected = {(int(r.cx), int(r.cy)): int(r.kills) for r in cells_csv.itertuples()}
    assert kept == expected


def test_lookup_cell_to_cluster_matches_cells_csv_every_row(cells_csv, model, frame):
    for r in cells_csv.itertuples():
        x0, y0, x1, y1 = cell_rect_world(r.cx, r.cy, frame, model.grid_n)
        for x, y in (((x0 + x1) / 2, (y0 + y1) / 2), (x0 + 0.01, y0 + 0.01), (x1 - 0.01, y1 - 0.01)):
            ctx = death_context(x, y, "ct", True, model, frame)
            assert ctx["reason"] is None
            c = ctx["cell"]
            assert (c["cx"], c["cy"]) == (r.cx, r.cy)
            assert c["cluster_id"] == r.cluster
            assert c["cluster_name"] == r.cluster_name
            assert c["cell_ct_win"] == pytest.approx(r.ct_win, abs=1e-3)
            assert c["ct_win"] == model.clusters[r.cluster]["ct_win"]      # ct_win ของ "กลุ่ม" ไม่ใช่ของช่อง


def test_cell_with_too_few_duels_is_not_guessed_from_neighbours(cells_csv, model, frame):
    known = set(zip(cells_csv.cx, cells_csv.cy, strict=True))
    # ช่องที่ไม่มีข้อมูลพอ แต่มีเพื่อนบ้านที่มีข้อมูล — ต้องตอบว่าไม่พอ ไม่ใช่ยืมค่าข้างเคียงมา
    target = next((cx, cy) for cx in range(model.grid_n) for cy in range(model.grid_n)
                  if (cx, cy) not in known and (cx + 1, cy) in known and (cx - 1, cy) in known)
    x0, y0, x1, y1 = cell_rect_world(*target, frame, model.grid_n)
    ctx = death_context((x0 + x1) / 2, (y0 + y1) / 2, "t", True, model, frame)
    assert ctx["cell"] is None and ctx["reason"] == "insufficient" and ctx["disadvantaged"] is None
    assert ctx["cell_xy"] == {"cx": target[0], "cy": target[1]}


def test_hotspot_rule_reproduces_meanshift_membership(kills, model):
    """ยอดที่ใกล้สุดภายใน bandwidth = กฎที่ MeanShift(cluster_all=False) ใช้ — จำนวนดวลต่อ hotspot ต้องตรงกับ json"""
    d = duels(kills)
    centers = [(h["x"], h["y"]) for h in model.hotspots]
    got = Counter(nearest_within(x, y, centers, model.bandwidth) for x, y in zip(d["victim_X"], d["victim_Y"], strict=True))
    for i, h in enumerate(model.hotspots):
        assert got[i] == h["duels"], f"hotspot #{h['id']}"


def test_other_map_has_no_context(model):
    dust2 = radar_frame("de_dust2")
    assert dust2 is not None
    ctx = death_context(0, 0, "ct", True, model, dust2)
    assert ctx["reason"] == "no_model" and ctx["cell"] is None


# ==================================================================================================
# payload หน้า Round Review (backend/review.py) บนเดโมจริงใน fixture + กติกาของข้อความใน UI
# ==================================================================================================
def as_db_rows(doc: dict, round_num: int):
    """แปลง doc ของ parser ให้หน้าตาเหมือนที่ app.py query จากฐานข้อมูล"""
    names = {p["steam_id"]: p["name"] for p in doc["players"]}
    team = assign_teams([{**x, "clan": x["team_clan"]} for x in doc["player_rounds"]])
    roster = [{"steam_id": sid, "name": names.get(sid), "team": t} for sid, t in team.items()]
    rnd = next(r for r in doc["rounds"] if r["round_num"] == round_num)
    in_round = [{"steam_id": x["steam_id"], "side": x["side"], "survived": x["survived"]}
                for x in doc["player_rounds"] if x["round_num"] == round_num]
    kills = sorted((k for k in doc["kills"] if k["round_num"] == round_num), key=lambda k: k["tick"])
    kills = [{**k, "attacker_name": names.get(k["attacker_id"]), "victim_name": names.get(k["victim_id"]),
              "assister_name": names.get(k["assister_id"])} for k in kills]
    match = {"id": 1, **doc["match"]}
    return match, rnd, roster, in_round, kills


def detail(doc, n, model, frame):
    match, rnd, roster, in_round, kills = as_db_rows(doc, n)
    return build_round_detail(match=match, rnd=rnd, roster=roster, in_round=in_round, kills=kills, frame=frame, model=model)


def test_every_round_payload_is_consistent(sample_doc, model, frame):
    for r in sample_doc["rounds"]:
        n = r["round_num"]
        d = detail(sample_doc, n, model, frame)
        kills_here = [k for k in sample_doc["kills"] if k["round_num"] == n]
        deaths = d["deaths"]
        assert len(deaths) == len(kills_here)
        assert [x["order"] for x in deaths] == list(range(1, len(deaths) + 1))
        assert [x["t_round"] for x in deaths] == sorted(x["t_round"] for x in deaths)

        # จุดที่วางบนแผนที่อยู่ในภาพเรดาร์ทุกจุด
        for x in deaths:
            for key in ("victim_px", "attacker_px"):
                if x[key] is not None:
                    px, py = x[key]
                    assert 0 <= px <= frame.size and 0 <= py <= frame.size

        # ทีมจัดตามชื่อทีม ไม่ใช่ side: สองกล่อง กล่องละ 5 คน คนละ side ในรอบนี้
        assert [len(t["players"]) for t in d["teams"]] == [5, 5]
        assert {t["clan"] for t in d["teams"]} == {"GamerLegion", "K27 Esports"}
        assert {t["side_this_round"] for t in d["teams"]} == {"ct", "t"}
        dead = [p for t in d["teams"] for p in t["players"] if not p["survived"]]
        assert len(dead) == len({x["victim"]["steamid"] for x in deaths})

        # บริบทจาก grid_ml1: มีช่อง -> อยู่ในกลุ่มที่มีจริง, ไม่มีช่อง -> บอกว่าข้อมูลไม่พอ
        for x in deaths:
            assert x["reason"] in (None, "insufficient")
            if x["cell"]:
                assert x["cell"]["cluster_id"] in model.clusters
                assert x["cell"]["ct_win"] == model.clusters[x["cell"]["cluster_id"]]["ct_win"]
            else:
                assert x["disadvantaged"] is None

        s = d["summary"]
        if deaths:
            assert s["first_death"]["name"] == deaths[0]["victim"]["name"]
            assert s["first_death_side_lost"] == (deaths[0]["victim"]["side"] != r["winner_side"])
        assert sum(s["disadvantaged_deaths"].values()) == sum(bool(x["disadvantaged"]) for x in deaths)
        assert d["grid"]["source"]["matches"] == model.matches          # กฎข้อ 1: บอกที่มาทุกครั้ง
        assert f"{model.matches} แมตช์" in d["grid"]["source"]["label"]


def test_player_colours_are_stable_across_rounds(sample_doc, model, frame):
    seen: dict[str, str] = {}
    for r in sample_doc["rounds"]:
        for t in detail(sample_doc, r["round_num"], model, frame)["teams"]:
            for p in t["players"]:
                assert seen.setdefault(p["steamid"], p["color"]) == p["color"]
    assert len(set(seen.values())) == 10


def test_bomb_icon_position_when_planted(sample_doc, model, frame):
    planted = next(r for r in sample_doc["rounds"] if r["bomb_plant_tick"] is not None)
    d = detail(sample_doc, planted["round_num"], model, frame)
    assert d["round"]["bomb"]["px"] is not None and d["round"]["bomb_planted_t"] > 0
    not_planted = [r for r in sample_doc["rounds"] if r["bomb_plant_tick"] is None]
    for r in not_planted:
        assert detail(sample_doc, r["round_num"], model, frame)["round"]["bomb"] is None



def test_grenades_in_round_payload(sample_doc, model, frame):
    """ระเบิด: จุดตก/จุดขว้างเป็นพิกเซลบนเรดาร์ ชื่อ+สีคนขว้างตรงกับคนตาย ควันไม่มี event หมดใช้ค่าในเกม"""
    match, rnd, roster, in_round, kills = as_db_rows(sample_doc, 1)
    k = next(k for k in kills if k.get("victim_x") is not None)
    x, y = k["victim_x"], k["victim_y"]
    t0, tr = rnd["start_tick"], match["tickrate"]
    base = {"thrower_id": k["victim_id"], "thrower_name": k["victim_name"], "side": k["victim_side"], "throw_x": x, "throw_y": y}
    nades = [
        {**base, "type": "smoke", "tick": t0 + 5 * tr, "land_x": x, "land_y": y, "land_tick": t0 + 7 * tr, "end_tick": None},
        {**base, "type": "flash", "tick": t0 + 8 * tr, "land_x": x, "land_y": y, "land_tick": t0 + 9 * tr, "end_tick": t0 + 9 * tr},
        {**base, "type": "decoy", "tick": t0 + 10 * tr, "land_x": None, "land_y": None, "land_tick": None, "end_tick": None},
    ]
    d = build_round_detail(match=match, rnd=rnd, roster=roster, in_round=in_round, kills=kills, grenades=nades,
                           frame=frame, model=model)
    smoke, flash, decoy = d["grenades"]
    death = next(x for x in d["deaths"] if x["victim"]["steamid"] == str(k["victim_id"]))
    assert smoke["land_px"] == death["victim_px"] and smoke["throw_px"] == death["victim_px"]
    assert smoke["thrower"]["name"] == death["victim"]["name"] and smoke["thrower"]["color"] == death["victim"]["color"]
    assert (smoke["t_throw"], smoke["t_land"], smoke["t_end"]) == (5.0, 7.0, 27.0)   # ไม่มี end_tick -> 20 วินาที
    assert smoke["r_px"] == round(144 / frame.scale, 1) and flash["r_px"] == 0
    assert flash["t_land"] == flash["t_end"] == 9.0
    assert decoy["land_px"] is None and decoy["t_land"] is None
    assert detail(sample_doc, 1, model, frame)["grenades"] == []      # ไม่ส่งระเบิดมา = รายการว่าง ไม่พัง


def test_round_list(sample_doc):
    rounds = [{**r} for r in sample_doc["rounds"]]
    first = {r["round_num"]: min(k["tick"] for k in sample_doc["kills"] if k["round_num"] == r["round_num"]) for r in rounds}
    counts = {r["round_num"]: sum(k["round_num"] == r["round_num"] for k in sample_doc["kills"]) for r in rounds}
    out = build_round_list(rounds, first, counts, sample_doc["match"]["tickrate"])
    assert [x["round_num"] for x in out] == [r["round_num"] for r in rounds]
    assert sum(x["deaths_count"] for x in out) == len(sample_doc["kills"])
    assert all(x["first_death_t"] > 0 for x in out)


def test_grid_overlay_pixels_inside_radar(model, frame):
    o = grid_overlay(model, frame)
    assert len(o["cells"]) == len(model.cells) and len(o["hotspots"]) == len(model.hotspots)
    for c in o["cells"]:
        assert 0 <= c["x"] and c["x"] + c["w"] <= frame.size and 0 <= c["y"] and c["y"] + c["w"] <= frame.size
    assert [c["id"] for c in o["clusters"]] == sorted(model.clusters)      # กฎข้อ 4: เบอร์เดียวกับรูป เริ่มที่ 1


FORBIDDEN = ("โอกาสชนะรอบ", "เล่นแย่", "ยืนผิด", "win probability")


def test_review_ui_text_follows_the_rules():
    """กฎข้อ 2 และ 3: ห้ามเรียก ct_win ว่าโอกาสชนะรอบ และห้ามใช้ภาษาตัดสินคน ในโค้ดหน้า Round Review"""
    src = ROOT / "frontend" / "src"
    files = sorted(src.glob("*.tsx"))
    assert len(files) >= 5 and (src / "RoundView.tsx") in files
    for f in files:
        text = f.read_text(encoding="utf-8")
        for bad in FORBIDDEN:
            assert bad not in text, f"{f.name} มีคำว่า {bad!r}"


# ---- โหมดเล่นย้อน: เฟรมตำแหน่งรายวินาที ----------------------------------------------------------
def test_round_positions_are_one_frame_per_second_in_radar_pixels(frame):
    """คนที่ตายแล้วหายไปจากเฟรมเอง · พิกัดถูกแปลงเป็นพิกเซลให้แล้ว · เวลาเริ่มที่ 0 = freeze จบ"""
    from backend.review import build_round_positions
    start, tickrate = 1000, 128
    rows = [
        {"tick": 1000, "steam_id": 1, "side": "ct", "x": -1000.0, "y": 500.0, "health": 100, "place": "A"},
        {"tick": 1000, "steam_id": 2, "side": "t", "x": -900.0, "y": 400.0, "health": 100, "place": "B"},
        {"tick": 1128, "steam_id": 1, "side": "ct", "x": -980.0, "y": 505.0, "health": 72, "place": "A"},
        # steam_id 2 ตายไปแล้ว -> ไม่มีแถวในวินาทีที่ 1
    ]
    out = build_round_positions(rows, start_tick=start, tickrate=tickrate, frame=frame)
    assert out["step"] == 1.0 and out["t_end"] == 1.0
    assert [f["t"] for f in out["frames"]] == [0.0, 1.0]
    assert [len(f["players"]) for f in out["frames"]] == [2, 1]
    p = out["frames"][0]["players"][0]
    assert p["steamid"] == "1" and p["hp"] == 100 and p["side"] == "ct"
    assert all(0 <= v <= frame.size for v in p["px"])          # อยู่ในกรอบภาพเรดาร์
    assert out["frames"][1]["players"][0]["hp"] == 72
    assert "วินาทีละครั้ง" in out["note"]                        # ต้องบอกผู้ใช้เสมอว่าอะไรคือข้อมูลจริง


def test_round_positions_without_radar_or_coords_are_dropped_not_guessed(frame):
    from backend.review import build_round_positions
    rows = [{"tick": 1000, "steam_id": 1, "side": "ct", "x": None, "y": None, "health": 100, "place": None}]
    assert build_round_positions(rows, start_tick=1000, tickrate=128, frame=frame)["frames"] == []
    ok = [{"tick": 1000, "steam_id": 1, "side": "ct", "x": -1000.0, "y": 500.0, "health": 100, "place": None}]
    assert build_round_positions(ok, start_tick=1000, tickrate=128, frame=None)["frames"] == []

