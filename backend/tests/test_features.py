# -*- coding: utf-8 -*-
"""ฟีเจอร์ของผู้เล่น (backend/features.py): 4 นิยาม · ความสอดคล้องบนเดโมจริง · ผูกทีมข้ามครึ่ง"""
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import pytest

from backend import features as d
from backend.features import (
    FALLBACK_NAMES,
    aggregate_players,
    assign_teams,
    build_rounds,
    clutches,
    compute_features,
    opening_kill,
    trade_pairs,
)
from backend.tests.conftest import kill, make_doc, roster

# ==================================================================================================
# ทดสอบ 4 นิยามใน backend/features.py ด้วยสถานการณ์ที่คำนวณคำตอบด้วยมือได้
# ==================================================================================================
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


# ==================================================================================================
# feature layer บนเดโมจริง (fixture JSON) — เช็คความสอดคล้องที่ต้องเป็นจริงเสมอ ไม่ใช่ตัวเลขตายตัว
# ==================================================================================================
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
    from backend.parser import SCHEMA_VERSION
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


# ==================================================================================================
# ผูกผู้เล่นกับทีม: คนเดิม (steamid เดิม) ต้องอยู่ทีมเดิมทั้งครึ่งแรกและครึ่งหลัง
# ==================================================================================================
ROOT = Path(__file__).resolve().parent.parent.parent
ALPHA = [101, 102, 103, 104, 105]
BRAVO = [201, 202, 203, 204, 205]


def side_of(team_starts_ct: bool, rnd: int) -> str:
    """MR12: สลับที่รอบ 13 และ overtime สลับทุก 3 รอบตั้งแต่รอบ 25 (ไว้ทดสอบว่าไม่ต้องรู้กฎนี้ก็ผูกถูก)"""
    block = 0 if rnd <= 12 else 1 if rnd <= 24 else 2 + (rnd - 25) // 3
    ct = team_starts_ct if block % 2 == 0 else not team_starts_ct
    return "ct" if ct else "t"


def rows(n_rounds, a=ALPHA, b=BRAVO, clan_a=None, clan_b=None, skip=()):
    out = []
    for r in range(1, n_rounds + 1):
        for sid in a:
            if (sid, r) not in skip:
                out.append({"steam_id": sid, "round_num": r, "side": side_of(True, r), "clan": clan_a})
        for sid in b:
            if (sid, r) not in skip:
                out.append({"steam_id": sid, "round_num": r, "side": side_of(False, r), "clan": clan_b})
    return out


def test_same_player_same_team_both_halves_with_clans():
    team = assign_teams(rows(24, clan_a="Alpha", clan_b="Bravo"))
    assert {team[s] for s in ALPHA} == {"Alpha"}
    assert {team[s] for s in BRAVO} == {"Bravo"}


def test_fallback_without_clan_team_a_is_first_half_ct():
    team = assign_teams(rows(24))
    assert {team[s] for s in ALPHA} == {FALLBACK_NAMES[0]}      # เริ่มเกม CT
    assert {team[s] for s in BRAVO} == {FALLBACK_NAMES[1]}


def test_fallback_uses_first_half_side_even_if_data_starts_later():
    # เดโมขาดช่วงต้น: รอบแรกที่มีข้อมูลคือรอบ 5 (ยังครึ่งแรก) — ทีมที่อยู่ CT ตอนนั้นคือ Team A
    data = [r for r in rows(24) if r["round_num"] >= 5]
    team = assign_teams(data)
    assert team[101] == "Team A" and team[201] == "Team B"


def test_overtime_side_switches_do_not_split_a_team():
    team = assign_teams(rows(30, clan_a="Alpha", clan_b="Bravo"))
    assert Counter(team.values()) == {"Alpha": 5, "Bravo": 5}


def test_substitute_joins_the_right_team_through_teammates():
    # 105 ออกหลังรอบ 13, 106 ลงแทนตั้งแต่รอบ 14 — ไม่เคยเล่นครึ่งแรก และไม่มี clan tag
    skip = {(105, r) for r in range(14, 25)}
    data = rows(24, clan_a="Alpha", clan_b="Bravo", skip=skip)
    data += [{"steam_id": 106, "round_num": r, "side": side_of(True, r), "clan": None} for r in range(14, 25)]
    team = assign_teams(data)
    assert team[106] == "Alpha" and team[105] == "Alpha"


def test_partial_clan_follows_majority_of_teammates():
    data = rows(24, clan_a="Alpha", clan_b="Bravo")
    for r in data:
        if r["steam_id"] in (104, 204):
            r["clan"] = ""                                   # สองคนนี้ไม่มี tag
    team = assign_teams(data)
    assert team[104] == "Alpha" and team[204] == "Bravo"


def test_real_csv_every_player_keeps_one_team_across_halves():
    """data/all_kills.csv (50 เดโมจริง): ทุก steamid อยู่ทีมเดียวทั้งครึ่งแรกและครึ่งหลัง และแต่ละเดโมมีสองทีม"""
    df = pd.read_csv(ROOT / "data" / "all_kills.csv")
    assert {"attacker_team_clan", "victim_team_clan", "round_winner_side", "attacker_blind"} <= set(df.columns)
    long = pd.concat([
        df[["demo_file", "round_num", "attacker_steamid", "attacker_team_clan"]].set_axis(["demo", "rnd", "sid", "team"], axis=1),
        df[["demo_file", "round_num", "victim_steamid", "victim_team_clan"]].set_axis(["demo", "rnd", "sid", "team"], axis=1),
    ]).dropna(subset=["sid"])
    assert long["team"].notna().all()
    halves: dict[tuple, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for r in long.itertuples():
        halves[(r.demo, int(r.sid))]["H1" if r.rnd <= 12 else "H2"].add(r.team)
    both = 0
    for (demo, sid), h in halves.items():
        teams = set().union(*h.values())
        assert len(teams) == 1, f"{demo} {sid}: {teams}"
        both += int("H1" in h and "H2" in h)
    assert both > 400        # คนส่วนใหญ่โผล่ทั้งสองครึ่ง — เทสต์นี้จึงตรวจการข้ามครึ่งจริง
    assert (long.groupby("demo")["team"].nunique() == 2).all()


def test_parser_output_teams_match_demo_clans(sample_doc):
    pr = sample_doc["player_rounds"]
    assert all("team_clan" in x for x in pr)
    team = assign_teams([{**x, "clan": x["team_clan"]} for x in pr])
    assert Counter(team.values()) == {"GamerLegion": 5, "K27 Esports": 5}


@pytest.mark.parametrize("bad", [[], [{"steam_id": None, "round_num": 1, "side": "ct"}], [{"steam_id": 1, "round_num": 1, "side": "spec"}]])
def test_empty_or_invalid_rows(bad):
    assert assign_teams(bad) == {}


# ---- Rating 2.0 (ค่าประมาณ) --------------------------------------------------------------------
def test_rating2_of_an_average_player_lands_near_one():
    """ผู้เล่นระดับกลางของโปร (KPR .68, DPR .65, KAST 70%, ADR 78) ควรได้ราว ๆ 1.00"""
    from backend.features import rating2_approx
    r = rating2_approx(kills=68, deaths=65, assists=10, damage=7800, kast_rounds=70, rounds=100)
    assert 0.85 <= r <= 1.15


def test_rating2_moves_the_right_way():
    from backend.features import rating2_approx
    base = dict(kills=68, deaths=65, assists=10, damage=7800, kast_rounds=70, rounds=100)
    assert rating2_approx(**{**base, "kills": 90}) > rating2_approx(**base)      # ฆ่ามากขึ้น = สูงขึ้น
    assert rating2_approx(**{**base, "deaths": 85}) < rating2_approx(**base)     # ตายมากขึ้น = ต่ำลง
    assert rating2_approx(**{**base, "damage": 9500}) > rating2_approx(**base)   # ดาเมจมากขึ้น = สูงขึ้น
    assert rating2_approx(**{**base, "kast_rounds": 85}) > rating2_approx(**base)


def test_rating2_without_rounds_is_zero_not_a_guess():
    from backend.features import impact_rating, rating2_approx
    assert rating2_approx(kills=0, deaths=0, assists=0, damage=0, kast_rounds=0, rounds=0) == 0.0
    assert impact_rating(10, 2, 0) == 0.0


def test_rating2_accepts_decimals_from_sql():
    """SUM()/AVG() ของ PostgreSQL คืน Decimal — เคยทำให้ /api/players/{id}/summary พัง 500"""
    from decimal import Decimal

    from backend.features import rating2_approx
    d = rating2_approx(kills=Decimal(68), deaths=Decimal(65), assists=Decimal(10), damage=Decimal(7800),
                       kast_rounds=Decimal(70), rounds=Decimal(100))
    assert d == rating2_approx(kills=68, deaths=65, assists=10, damage=7800, kast_rounds=70, rounds=100)

