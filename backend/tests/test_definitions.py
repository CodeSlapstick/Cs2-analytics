# -*- coding: utf-8 -*-
"""ทดสอบ 4 นิยามใน backend/features/definitions.py ด้วยสถานการณ์ที่คำนวณคำตอบด้วยมือได้"""
from backend.features import definitions as d
from backend.features.compute import (
    aggregate_players,
    build_rounds,
    clutches,
    compute_features,
    opening_kill,
    trade_pairs,
)
from backend.tests.conftest import kill, make_doc, roster

CT = [101, 102, 103, 104, 105]
T = [201, 202, 203, 204, 205]
R1 = {"round_num": 1, "start_tick": 1000, "bomb_plant_tick": None, "winner_side": "t", "end_reason": "ct_killed"}


def by(rows, round_num, steam_id):
    return next(r for r in rows if r.round_num == round_num and r.steam_id == steam_id)


# ---------------------------------------------------------------------------
# 1) opening kill — คิลแรกของรอบหลัง freeze-time จบ
# ---------------------------------------------------------------------------
def test_opening_kill_is_first_duel_after_freeze_end():
    doc = make_doc(rounds=[R1], player_rounds=roster(1, CT, T), kills=[
        kill(1, 900, 201, 101, "t", "ct"),          # ก่อน freeze จบ — ไม่นับ
        kill(1, 1500, 102, 202, "ct", "t"),         # <- opening
        kill(1, 1600, 203, 102, "t", "ct"),
    ])
    ctx = build_rounds(doc)[1]
    assert opening_kill(ctx)["tick"] == 1500
    rows = compute_features(doc)
    assert by(rows, 1, 102).opening_kill is True
    assert by(rows, 1, 202).opening_death is True
    assert by(rows, 1, 201).opening_kill is False   # คิลก่อน freeze จบไม่ใช่การเปิดรอบ


def test_opening_kill_ignores_team_kill_and_no_attacker():
    doc = make_doc(rounds=[R1], player_rounds=roster(1, CT, T), kills=[
        kill(1, 1200, 101, 102, "ct", "ct"),                          # ทีมคิล
        {"round_num": 1, "tick": 1300, "attacker_id": None, "victim_id": 103,
         "attacker_side": None, "victim_side": "ct", "weapon": "world"},   # ตกที่สูง
        kill(1, 1400, 201, 104, "t", "ct"),                           # <- opening
    ])
    assert opening_kill(build_rounds(doc)[1])["attacker_id"] == 201


def test_round_without_duel_has_no_opening():
    doc = make_doc(rounds=[R1], player_rounds=roster(1, CT, T), kills=[])
    assert opening_kill(build_rounds(doc)[1]) is None
    assert not any(r.opening_kill for r in compute_features(doc))


# ---------------------------------------------------------------------------
# 2) trade — คนฆ่าเหยื่อตายภายใน 5 วินาทีด้วยมือเพื่อนของเหยื่อ
# ---------------------------------------------------------------------------
def test_trade_within_window_by_teammate():
    w = d.trade_window_ticks(128)
    doc = make_doc(rounds=[R1], player_rounds=roster(1, CT, T), kills=[
        kill(1, 2000, 201, 101, "t", "ct"),          # T201 ฆ่า CT101
        kill(1, 2000 + w, 102, 201, "ct", "t"),      # CT102 เก็บ 201 คืนพอดีขอบหน้าต่าง -> trade
    ])
    pairs = trade_pairs(build_rounds(doc)[1], 128)
    assert [(a["victim_id"], b["attacker_id"]) for a, b in pairs] == [(101, 102)]
    rows = compute_features(doc)
    assert by(rows, 1, 101).was_traded is True
    assert by(rows, 1, 102).trade_kills == 1
    assert by(rows, 1, 101).kast is True            # ตายแต่ถูกเก็บคืน = T ของ KAST


def test_trade_one_tick_late_does_not_count():
    w = d.trade_window_ticks(128)
    doc = make_doc(rounds=[R1], player_rounds=roster(1, CT, T), kills=[
        kill(1, 2000, 201, 101, "t", "ct"),
        kill(1, 2000 + w + 1, 102, 201, "ct", "t"),
    ])
    assert trade_pairs(build_rounds(doc)[1], 128) == []
    assert by(compute_features(doc), 1, 101).was_traded is False


def test_trade_window_scales_with_tickrate():
    doc64 = make_doc(tickrate=64, rounds=[R1], player_rounds=roster(1, CT, T), kills=[
        kill(1, 2000, 201, 101, "t", "ct"),
        kill(1, 2000 + 5 * 64, 102, 201, "ct", "t"),    # 5 วินาทีที่ 64 tick
        kill(1, 2000 + 5 * 128, 103, 202, "ct", "t"),   # ไม่เกี่ยว: 202 ไม่ได้ฆ่าใคร
    ])
    assert len(trade_pairs(build_rounds(doc64)[1], 64)) == 1


def test_killer_of_killer_must_be_victims_teammate():
    doc = make_doc(rounds=[R1], player_rounds=roster(1, CT, T), kills=[
        kill(1, 2000, 201, 101, "t", "ct"),
        kill(1, 2100, 202, 201, "t", "t"),           # เพื่อนร่วมทีมของ 201 ยิง 201 เอง — ไม่ใช่ trade
    ])
    assert trade_pairs(build_rounds(doc)[1], 128) == []


def test_one_kill_can_trade_two_deaths():
    doc = make_doc(rounds=[R1], player_rounds=roster(1, CT, T), kills=[
        kill(1, 2000, 201, 101, "t", "ct"),
        kill(1, 2100, 201, 102, "t", "ct"),
        kill(1, 2200, 103, 201, "ct", "t"),          # เก็บคนที่ฆ่าเพื่อนไปสองคน
    ])
    rows = compute_features(doc)
    assert by(rows, 1, 103).trade_kills == 2
    assert by(rows, 1, 101).was_traded and by(rows, 1, 102).was_traded


# ---------------------------------------------------------------------------
# 3) buy type — ต่อคน: Full >= 4000, Force 2000-4000, Eco < 2000, Pistol รอบ 1 และ 13
# ---------------------------------------------------------------------------
def test_buy_type_thresholds():
    assert d.buy_type(1999, 2) == "eco"
    assert d.buy_type(2000, 2) == "force"
    assert d.buy_type(3999, 2) == "force"
    assert d.buy_type(4000, 2) == "full"
    assert d.buy_type(0, 2) == "eco"
    assert d.buy_type(None, 2) is None


def test_pistol_rounds_override_money():
    assert d.buy_type(650, 1) == "pistol"
    assert d.buy_type(9000, 13) == "pistol"
    assert d.buy_type(650, 2) == "eco"
    assert d.PISTOL_ROUNDS == (1, 13)


def test_buy_type_lands_in_player_round_rows():
    r2 = {**R1, "round_num": 2}
    doc = make_doc(rounds=[R1, r2],
                   player_rounds=roster(1, CT, T) + roster(2, CT, T, equip={101: 1500, 102: 2500, 103: 5200}))
    rows = compute_features(doc)
    assert by(rows, 1, 101).buy_type == "pistol"
    assert by(rows, 2, 101).buy_type == "eco"
    assert by(rows, 2, 102).buy_type == "force"
    assert by(rows, 2, 103).buy_type == "full"


# ---------------------------------------------------------------------------
# 4) clutch — เหลือคนเดียว เจอศัตรู >= 1 และรอบยังไม่จบ
# ---------------------------------------------------------------------------
def test_clutch_detected_when_side_drops_to_one():
    # T ตายทีละคนจนเหลือ 205 คนเดียวตอน CT ยังอยู่ 3 คน -> 1v3 แล้วชนะ
    # ปลายรอบ CT ก็เหลือ 105 คนเดียวตอน T ยังมี 1 -> 1v1 ของฝั่ง CT ด้วย (นับทั้งสองฝั่ง) แต่แพ้
    doc = make_doc(rounds=[R1], player_rounds=roster(1, CT, T), kills=[
        kill(1, 1100, 101, 201, "ct", "t"),
        kill(1, 1200, 205, 102, "t", "ct"),
        kill(1, 1300, 101, 202, "ct", "t"),
        kill(1, 1400, 205, 103, "t", "ct"),
        kill(1, 1500, 101, 203, "ct", "t"),
        kill(1, 1600, 101, 204, "ct", "t"),          # T เหลือ 205 คนเดียว, CT เหลือ 101 104 105
        kill(1, 1700, 205, 101, "t", "ct"),
        kill(1, 1800, 205, 104, "t", "ct"),          # CT เหลือ 105 คนเดียว vs 1
        kill(1, 1900, 205, 105, "t", "ct"),
    ])
    ev = sorted((e.side, e.steam_id, e.vs, e.won, e.at_tick) for e in clutches(build_rounds(doc)[1]))
    assert ev == [("ct", 105, 1, False, 1800), ("t", 205, 3, True, 1600)]
    rows = compute_features(doc)
    assert (by(rows, 1, 205).clutch_vs, by(rows, 1, 205).clutch_won) == (3, True)
    assert (by(rows, 1, 105).clutch_vs, by(rows, 1, 105).clutch_won) == (1, False)
    assert by(rows, 1, 101).clutch_vs == 0      # คนอื่นไม่เคยอยู่ในสถานการณ์ clutch


def test_no_clutch_when_round_ends_before_anyone_is_alone():
    # 2v2 แล้ว CT กู้ระเบิดจบรอบ — ไม่มีฝั่งไหนเหลือคนเดียว จึงไม่มี clutch
    doc = make_doc(rounds=[{**R1, "winner_side": "ct", "end_reason": "bomb_defused"}],
                   player_rounds=roster(1, CT, T), kills=[
        kill(1, 1100, 201, 101, "t", "ct"), kill(1, 1150, 201, 102, "t", "ct"), kill(1, 1160, 201, 103, "t", "ct"),
        kill(1, 1200, 104, 201, "ct", "t"), kill(1, 1300, 104, 202, "ct", "t"), kill(1, 1400, 104, 203, "ct", "t"),
    ])
    assert clutches(build_rounds(doc)[1]) == []
    assert all(r.clutch_vs == 0 and r.clutch_won is None for r in compute_features(doc))


def test_one_v_one_counts_for_both_sides_and_loser_marked():
    doc = make_doc(rounds=[{**R1, "winner_side": "ct"}], player_rounds=roster(1, CT[:2], T[:2]), kills=[
        kill(1, 1100, 101, 201, "ct", "t"),          # 2v1: T เหลือ 202 คนเดียว vs 2
        kill(1, 1200, 202, 101, "t", "ct"),          # 1v1: CT เหลือ 102
        kill(1, 1300, 102, 202, "ct", "t"),
    ])
    ev = {e.side: e for e in clutches(build_rounds(doc)[1])}
    assert (ev["t"].steam_id, ev["t"].vs, ev["t"].won) == (202, 2, False)
    assert (ev["ct"].steam_id, ev["ct"].vs, ev["ct"].won) == (102, 1, True)


def test_clutch_needs_rosters():
    # ไม่มี player_rounds = ไม่รู้ว่าใครอยู่ทีมไหน -> ตัดสิน clutch ไม่ได้ ต้องไม่เดา
    doc = make_doc(rounds=[R1], kills=[kill(1, 1100, 101, 201, "ct", "t")])
    assert clutches(build_rounds(doc)[1]) == []


# ---------------------------------------------------------------------------
# ADR / KAST
# ---------------------------------------------------------------------------
def test_adr_counts_enemy_damage_only_and_kast_rules():
    r2 = {**R1, "round_num": 2, "winner_side": "ct"}
    doc = make_doc(
        rounds=[R1, r2],
        player_rounds=roster(1, CT, T, survived=(101, 103)) + roster(2, CT, T, survived=(101, 102)),
        kills=[kill(1, 1500, 101, 201, "ct", "t", assister=102), kill(2, 1500, 201, 103, "t", "ct")],
        damages=[
            {"round_num": 1, "tick": 1400, "attacker_id": 101, "victim_id": 201, "damage": 70},
            {"round_num": 1, "tick": 1450, "attacker_id": 101, "victim_id": 102, "damage": 30},   # ยิงเพื่อน ไม่นับ
            {"round_num": 2, "tick": 1400, "attacker_id": 101, "victim_id": 202, "damage": 50},
        ],
    )
    rows = compute_features(doc)
    agg = aggregate_players(rows)
    assert agg[101]["damage"] == 120 and agg[101]["adr"] == 60.0     # 120 / 2 รอบ
    assert by(rows, 1, 102).kast is True     # assist
    assert by(rows, 1, 101).kast is True     # kill + survived
    assert by(rows, 1, 103).kast is True     # รอด
    assert by(rows, 2, 103).kast is False    # ตาย ไม่มีคิล ไม่มีแอสซิสต์ ไม่ถูกเก็บคืน
    assert by(rows, 1, 203).kast is False    # ไม่ทำอะไรและไม่รอด
    assert agg[103]["kast"] == 50.0          # รอด 1 ใน 2 รอบ
    assert agg[101]["kast"] == 100.0
