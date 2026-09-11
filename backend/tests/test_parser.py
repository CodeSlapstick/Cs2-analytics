# -*- coding: utf-8 -*-
"""parser บนไฟล์ .dem จริง — ต้องมีเดโมในเครื่อง (ไฟล์ละ 100+ MB จึงไม่อยู่ใน git)

    ตั้ง CS2_TEST_DEMO=path/to/file.dem   หรือมีไฟล์ใน demos/ อย่างน้อยหนึ่งไฟล์
    ไม่มีทั้งสองอย่าง -> เทสต์นี้ถูก skip (CI ดาวน์โหลดเดโมมาให้เองถ้าตั้ง CS2_TEST_DEMO_URL)
"""
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


def _demo_path() -> Path | None:
    env = os.environ.get("CS2_TEST_DEMO")
    if env and Path(env).is_file():
        return Path(env)
    found = sorted((ROOT / "demos").glob("*.dem"), key=lambda p: p.stat().st_size)
    return found[0] if found else None      # เอาไฟล์เล็กสุด ให้เทสต์เร็ว


DEMO = _demo_path()
pytestmark = pytest.mark.skipif(DEMO is None, reason="ไม่มีไฟล์ .dem ให้ทดสอบ (ตั้ง CS2_TEST_DEMO)")


@pytest.fixture(scope="module")
def doc():
    from backend.parser.service import SCHEMA_VERSION, parse_demo
    d = parse_demo(DEMO)
    assert d["schema_version"] == SCHEMA_VERSION
    return d


def test_document_shape(doc):
    assert set(doc) >= {"schema_version", "match", "counts", "players", "rounds", "kills", "damages",
                        "player_rounds", "grenades"}
    assert doc["match"]["demo_file"] == DEMO.name
    assert doc["match"]["tickrate"] in (64, 128)
    assert doc["match"]["map_name"].startswith("de_")


def test_counts_match_lists(doc):
    for key in ("players", "rounds", "kills", "damages", "player_rounds", "grenades"):
        assert doc["counts"][key] == len(doc[key])
    assert doc["counts"]["rounds"] >= 1


def test_rounds_are_consistent(doc):
    nums = [r["round_num"] for r in doc["rounds"]]
    assert nums == list(range(1, len(nums) + 1))
    for r in doc["rounds"]:
        assert r["winner_side"] in ("ct", "t")
        assert r["start_tick"] is not None


def test_every_event_belongs_to_a_round_and_a_known_player(doc):
    rounds = {r["round_num"] for r in doc["rounds"]}
    players = {p["steam_id"] for p in doc["players"]}
    for k in doc["kills"]:
        assert k["round_num"] in rounds
        assert k["victim_id"] in players
    for pr in doc["player_rounds"]:
        assert pr["round_num"] in rounds and pr["steam_id"] in players and pr["side"] in ("ct", "t")
    # 10 คนต่อรอบ (โค้ช/ผู้ชมถูกตัดออกแล้ว)
    per_round = {}
    for pr in doc["player_rounds"]:
        per_round[pr["round_num"]] = per_round.get(pr["round_num"], 0) + 1
    assert all(n == 10 for n in per_round.values())


def test_positions_are_one_hz_and_alive_only(doc):
    """ตำแหน่งต้องเป็นวินาทีละครั้ง (ห่างกัน = tickrate) ไม่เกิน 10 คนต่อ tick และไม่มีคนตายปนมา"""
    pos = doc["positions"]
    assert pos and doc["counts"]["positions"] == len(pos)
    tickrate = doc["match"]["tickrate"]
    by_round: dict[int, set[int]] = {}
    for p in pos:
        by_round.setdefault(p["round_num"], set()).add(p["tick"])
        assert p["side"] in ("ct", "t") and p["health"] > 0
    for n, ticks in by_round.items():
        ts = sorted(ticks)
        assert all(b - a == tickrate for a, b in zip(ts, ts[1:], strict=False)), f"รอบ {n} ไม่ใช่ 1 Hz"
        per_tick = {}
        for p in pos:
            if p["round_num"] == n:
                per_tick[p["tick"]] = per_tick.get(p["tick"], 0) + 1
        assert max(per_tick.values()) <= 10
    # ไม่มี tick ก่อน freeze จบ หรือหลังรอบจบ
    rounds = {r["round_num"]: r for r in doc["rounds"]}
    assert all(rounds[p["round_num"]]["start_tick"] <= p["tick"] < rounds[p["round_num"]]["end_tick"] for p in pos)


def test_team_clan_and_bomb_position(doc):
    """schema 5: ทุกแถว player_rounds มี team_clan และทุกรอบที่วางบอมบ์มีพิกัดวางบอมบ์"""
    assert all("team_clan" in x for x in doc["player_rounds"])
    planted = [r for r in doc["rounds"] if r["bomb_plant_tick"] is not None]
    assert all(r["bomb_plant_x"] is not None and r["bomb_plant_y"] is not None for r in planted)


def test_feature_layer_runs_on_real_parse(doc):
    from backend.features.compute import compute_features
    rows = compute_features(doc)
    assert len(rows) == len(doc["player_rounds"])
