# -*- coding: utf-8 -*-
"""payload หน้า Round Review (backend/review.py) บนเดโมจริงใน fixture + กติกาของข้อความใน UI"""
import json
from pathlib import Path

import pytest

from backend.features.teams import assign_teams
from backend.geo import radar_frame
from backend.review import build_round_detail, build_round_list, grid_overlay, parse_grid_model

ROOT = Path(__file__).resolve().parent.parent.parent
FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def model():
    return parse_grid_model(json.loads((FIX / "grid_ml1.json").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def frame():
    return radar_frame("de_mirage")


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
    files = sorted([*src.glob("pages/*.tsx"), *src.glob("components/**/*.tsx")])
    assert len(files) >= 8 and (src / "components" / "review" / "RoundView.tsx") in files
    for f in files:
        text = f.read_text(encoding="utf-8")
        for bad in FORBIDDEN:
            assert bad not in text, f"{f.name} มีคำว่า {bad!r}"
