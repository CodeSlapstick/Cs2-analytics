# -*- coding: utf-8 -*-
"""ผูกผู้เล่นกับทีม: คนเดิม (steamid เดิม) ต้องอยู่ทีมเดิมทั้งครึ่งแรกและครึ่งหลัง"""
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import pytest

from backend.features.teams import FALLBACK_NAMES, assign_teams

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
