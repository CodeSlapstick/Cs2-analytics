# -*- coding: utf-8 -*-
"""feature layer บนเดโมจริง (fixture JSON) — เช็คความสอดคล้องที่ต้องเป็นจริงเสมอ ไม่ใช่ตัวเลขตายตัว"""
from backend.features.compute import aggregate_players, compute_features


def test_one_row_per_player_per_round(sample_doc):
    rows = compute_features(sample_doc)
    assert len(rows) == sample_doc["counts"]["player_rounds"]
    assert len({(r.round_num, r.steam_id) for r in rows}) == len(rows)


def test_exactly_one_opening_kill_per_round_with_a_duel(sample_doc):
    rows = compute_features(sample_doc)
    for n in {r["round_num"] for r in sample_doc["rounds"]}:
        assert sum(r.opening_kill for r in rows if r.round_num == n) == 1
        assert sum(r.opening_death for r in rows if r.round_num == n) == 1


def test_deaths_and_kills_reconcile_with_kill_events(sample_doc):
    rows = compute_features(sample_doc)
    assert sum(r.deaths for r in rows) == len(sample_doc["kills"])
    duels = [k for k in sample_doc["kills"] if k.get("attacker_id") and k["attacker_side"] != k["victim_side"]]
    assert sum(r.kills for r in rows) == len(duels)


def test_aggregates_are_within_sane_ranges(sample_doc):
    agg = aggregate_players(compute_features(sample_doc))
    assert len(agg) == sample_doc["counts"]["players"]
    for a in agg.values():
        assert a["rounds"] == sample_doc["counts"]["rounds"]
        assert 0 <= a["kast"] <= 100
        assert 0 <= a["adr"] <= 300
        assert a["clutch_wins"] <= a["clutch_attempts"]
        assert a["traded_deaths"] <= a["deaths"]
    assert sum(a["opening_kills"] for a in agg.values()) == sample_doc["counts"]["rounds"]


def test_fixture_is_current_schema_with_positions(sample_doc):
    from backend.parser.service import SCHEMA_VERSION
    assert sample_doc["schema_version"] == SCHEMA_VERSION
    pos = sample_doc["positions"]
    assert len(pos) == sample_doc["counts"]["positions"] > 0
    # 1 Hz: จำนวน tick ที่ต่างกันในรอบ ต้องไม่เกินความยาวรอบเป็นวินาที + 1
    for r in sample_doc["rounds"]:
        ticks = {p["tick"] for p in pos if p["round_num"] == r["round_num"]}
        seconds = (r["end_tick"] - r["start_tick"]) / sample_doc["match"]["tickrate"]
        assert len(ticks) <= seconds + 1


def test_buy_type_present_for_every_row(sample_doc):
    rows = compute_features(sample_doc)
    assert all(r.buy_type in ("pistol", "full", "force", "eco") for r in rows)
    assert all(r.buy_type == "pistol" for r in rows if r.round_num in (1, 13))
