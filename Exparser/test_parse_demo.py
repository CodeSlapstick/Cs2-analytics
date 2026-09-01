#!/usr/bin/env python3
"""
เทสต์ของ Exparser — รันด้วย `python Exparser/test_parse_demo.py` (ไม่ต้องมี pytest)

ยังไม่มีไฟล์ .dem จริงในมือ (ข้อ 1 ของ roadmap คือไปขอไฟล์จากทีม UTCC eSports)
เทสต์ชุดนี้จึงสร้าง "ของปลอมที่หน้าตาเหมือนผลลัพธ์ awpy" ขึ้นมาแทน คือ polars
DataFrame ที่มีคอลัมน์ชื่อเดียวกับที่ awpy 2.x คืนมา แล้วตรวจว่าโค้ดแปลงข้อมูล
ของเราทำงานถูกไหม

สิ่งที่เทสต์นี้ครอบคลุม (ตรรกะของเราเอง):
  - แปลง "ฝั่งที่ชนะ" เป็น "ทีมที่ชนะ" ได้ถูกแม้ทีมสลับฝั่งตอนครึ่งหลัง
  - จับคู่ผู้เล่นกับทีมจากฝั่งในรอบแรก ไม่ใช่ฝั่งปัจจุบัน
  - ตัด event ของบอท/ผู้ชม (steamid ไม่ใช่ 17 หลัก) ทิ้ง
  - นับระเบิดหนึ่งลูกเป็นหนึ่งครั้ง ไม่ใช่นับทุกจุดในเส้นทางการเคลื่อนที่

สิ่งที่เทสต์นี้ครอบคลุมไม่ได้: ชื่อคอลัมน์จริงของ awpy ในเครื่องที่รัน demo จริง
(ต้องรอไฟล์ .dem จริงถึงจะยืนยันได้ — โค้ดจึงเผื่อชื่อคอลัมน์ไว้หลายแบบ)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

for _stream in (sys.stdout, sys.stderr):  # คอนโซล Windows ต้องบังคับเป็น UTF-8 ก่อน
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import polars as pl  # noqa: E402

from parse_demo import (  # noqa: E402
    CT_TEAM,
    T_TEAM,
    as_str_id,
    build_grenade_events,
    grenade_name,
    build_kill_events,
    build_player_table,
    build_rounds,
    norm_side,
)

OK = 0
FAILED = 0


def check(name, got, want):
    global OK, FAILED
    if got == want:
        OK += 1
        print(f"  ✓ {name}")
    else:
        FAILED += 1
        print(f"  ✗ {name}\n      ได้    : {got!r}\n      ควรได้ : {want!r}")


class FakeDemo:
    """หน้าตาเหมือน awpy.Demo หลังเรียก .parse() แล้ว"""

    def __init__(self, ticks, rounds, kills=None, grenades=None):
        self.ticks = ticks
        self.rounds = rounds
        self.kills = kills if kills is not None else pl.DataFrame()
        self.grenades = grenades if grenades is not None else pl.DataFrame()
        self.damages = pl.DataFrame()
        self.bomb = pl.DataFrame()


A = "76561198000000001"  # เริ่มฝั่ง T
B = "76561198000000002"  # เริ่มฝั่ง T
C = "76561198000000003"  # เริ่มฝั่ง CT
D = "76561198000000004"  # เริ่มฝั่ง CT
BOT = "BOT_Wade"


def make_ticks():
    """รอบ 1–2 อยู่ฝั่งเดิม, รอบ 13 สลับฝั่งแล้ว (ครึ่งหลังของ MR12)"""
    rows = []
    for rnd, swapped in ((1, False), (2, False), (13, True)):
        for sid, start_side in ((A, "TERRORIST"), (B, "TERRORIST"), (C, "CT"), (D, "CT")):
            side = start_side
            if swapped:
                side = "CT" if start_side == "TERRORIST" else "TERRORIST"
            rows.append({"round_num": rnd, "steamid": sid, "side": side, "name": f"P{sid[-1]}"})
    return pl.DataFrame(rows)


def make_rounds():
    return pl.DataFrame(
        [
            # รอบ 1: ฝั่ง t ชนะ = ทีมที่เริ่ม T (ทีม 2)
            {"round_num": 1, "winner": "t", "reason": "t_win", "start": 100, "freeze_end": 200, "end": 900, "official_end": 950, "bomb_plant": None},
            # รอบ 2: ฝั่ง ct ชนะ = ทีมที่เริ่ม CT (ทีม 3)
            {"round_num": 2, "winner": "ct", "reason": "ct_win", "start": 1000, "freeze_end": 1100, "end": 1800, "official_end": 1850, "bomb_plant": 1500},
            # รอบ 13 (ครึ่งหลัง สลับฝั่งแล้ว): ฝั่ง ct ชนะ = ทีมที่เริ่ม T (ทีม 2)
            {"round_num": 13, "winner": "ct", "reason": "ct_win", "start": 2000, "freeze_end": 2100, "end": 2800, "official_end": 2850, "bomb_plant": None},
        ]
    )


def test_helpers():
    print("helper functions")
    check("as_str_id ยอมรับ steam64 17 หลัก", as_str_id(76561198000000001), A)
    check("as_str_id ตัด .0 ที่ติดมากับ float", as_str_id("76561198000000001.0"), A)
    check("as_str_id ปฏิเสธชื่อบอท", as_str_id(BOT), None)
    check("norm_side CT", norm_side("CT"), "ct")
    check("norm_side TERRORIST", norm_side("TERRORIST"), "t")
    check("norm_side ค่าที่ไม่รู้จัก", norm_side("SPECTATOR"), None)


def test_players_and_rounds():
    print("\nผู้เล่นและรอบ")
    dem = FakeDemo(make_ticks(), make_rounds())
    players, sides = build_player_table(dem, lambda m: None)

    check("จับผู้เล่นครบ 4 คน (ไม่นับบอท)", sorted(players), sorted([A, B, C, D]))
    check("A เริ่มฝั่ง T -> ทีม 2", players[A]["team_number"], T_TEAM)
    check("C เริ่มฝั่ง CT -> ทีม 3", players[C]["team_number"], CT_TEAM)
    check("รอบ 13 A ย้ายไปฝั่ง ct แล้ว", sides[13][A], "ct")

    rounds = build_rounds(dem, players, sides, lambda m: None)
    check("รอบถูกเรียงใหม่เป็น 1..N", [r["round_number"] for r in rounds], [1, 2, 3])
    check("รอบ 1: ฝั่ง t ชนะ = ทีม 2", rounds[0]["winner_team_number"], T_TEAM)
    check("รอบ 2: ฝั่ง ct ชนะ = ทีม 3", rounds[1]["winner_team_number"], CT_TEAM)
    check("ครึ่งหลัง: ฝั่ง ct ชนะ = ทีม 2 (เพราะสลับฝั่งแล้ว)", rounds[2]["winner_team_number"], T_TEAM)
    check("bomb_planted อ่านจาก tick การวางระเบิด", [r["bomb_planted"] for r in rounds], [False, True, False])


def test_events():
    print("\nevent")
    kills = pl.DataFrame(
        [
            {"round_num": 1, "tick": 300, "attacker_steamid": A, "victim_steamid": C, "assister_steamid": B,
             "weapon": "ak47", "headshot": True, "hitgroup": "head", "assistedflash": True,
             "attacker_X": 10.0, "attacker_Y": 20.0, "attacker_Z": 30.0,
             "victim_X": 40.0, "victim_Y": 50.0, "victim_Z": 60.0},
            # คิลของบอท — ต้องถูกตัดทิ้งเพราะเหยื่อไม่ใช่ผู้เล่นที่เรารู้จัก
            {"round_num": 1, "tick": 400, "attacker_steamid": A, "victim_steamid": BOT, "assister_steamid": None,
             "weapon": "ak47", "headshot": False, "hitgroup": "chest", "assistedflash": False,
             "attacker_X": 0.0, "attacker_Y": 0.0, "attacker_Z": 0.0,
             "victim_X": 0.0, "victim_Y": 0.0, "victim_Z": 0.0},
            # อยู่รอบที่ไม่มีใน rounds -> ถูกตัดทิ้ง
            {"round_num": 99, "tick": 500, "attacker_steamid": A, "victim_steamid": D, "assister_steamid": None,
             "weapon": "awp", "headshot": False, "hitgroup": "chest", "assistedflash": False,
             "attacker_X": 1.0, "attacker_Y": 1.0, "attacker_Z": 1.0,
             "victim_X": 2.0, "victim_Y": 2.0, "victim_Z": 2.0},
        ]
    )
    # เส้นทางระเบิดหนึ่งลูก = หลายแถว (entity_id เดียวกัน) ต้องนับเป็นครั้งเดียว
    grenades = pl.DataFrame(
        [
            {"round_num": 1, "tick": 210, "thrower_steamid": B, "grenade_type": "smokegrenade", "entity_id": 7, "X": 1.0, "Y": 2.0, "Z": 3.0},
            {"round_num": 1, "tick": 215, "thrower_steamid": B, "grenade_type": "smokegrenade", "entity_id": 7, "X": 5.0, "Y": 6.0, "Z": 7.0},
            {"round_num": 1, "tick": 260, "thrower_steamid": C, "grenade_type": "flashbang", "entity_id": 8, "X": 9.0, "Y": 9.0, "Z": 9.0},
        ]
    )

    dem = FakeDemo(make_ticks(), make_rounds(), kills, grenades)
    players, sides = build_player_table(dem, lambda m: None)
    rounds = build_rounds(dem, players, sides, lambda m: None)
    round_map = {r.pop("_source_round"): r["round_number"] for r in rounds}

    kill_events = build_kill_events(dem, players, round_map, lambda m: None)
    check("เหลือคิลที่ใช้ได้ 1 รายการ", len(kill_events), 1)
    check("พิกัดผู้ยิงติดมาด้วย (ไว้ทำ heatmap)", (kill_events[0]["actor_x"], kill_events[0]["actor_y"]), (10.0, 20.0))
    check("แฟลชแอสซิสต์ติดมาใน meta", kill_events[0]["meta"]["assistedflash"], True)

    nade_events = build_grenade_events(dem, players, round_map, lambda m: None)
    check("นับระเบิด 2 ลูก (ไม่ใช่ 3 จุดในเส้นทาง)", len(nade_events), 2)
    check("ระเบิดลูกแรกเป็นของ B", nade_events[0]["actor_steam64"], B)


def test_grenade_projectile_filter():
    """
    ไฟล์ .dem จริง (awpy 2.0.2) ปน entity สองแบบในตารางเดียว: ลูกที่ถืออยู่ในมือ
    (CSmokeGrenade — ถูกติดตามทุก tick ตลอดที่ยังไม่ขว้าง) กับลูกที่ขว้างออกไปแล้ว
    (CSmokeGrenadeProjectile) ถ้านับรวมกัน ยอดยูทิลิตี้จะเฟ้อขึ้นเท่าตัว
    """
    print("\nกรองเฉพาะระเบิดที่ขว้างออกไปจริง")
    grenades = pl.DataFrame(
        [
            # ลูกที่ยังถืออยู่ในมือ — ต้องไม่ถูกนับ
            {"round_num": 1, "tick": 100, "thrower_steamid": B, "grenade_type": "CSmokeGrenade", "entity_id": 20, "X": None, "Y": None, "Z": None},
            {"round_num": 1, "tick": 105, "thrower_steamid": C, "grenade_type": "CFlashbang", "entity_id": 21, "X": None, "Y": None, "Z": None},
            # ขว้างออกไปแล้ว — สองแถวแรกคือลูกเดียวกัน นับครั้งเดียว
            {"round_num": 1, "tick": 210, "thrower_steamid": B, "grenade_type": "CSmokeGrenadeProjectile", "entity_id": 22, "X": 1.0, "Y": 2.0, "Z": 3.0},
            {"round_num": 1, "tick": 215, "thrower_steamid": B, "grenade_type": "CSmokeGrenadeProjectile", "entity_id": 22, "X": 5.0, "Y": 6.0, "Z": 7.0},
            {"round_num": 1, "tick": 260, "thrower_steamid": C, "grenade_type": "CMolotovProjectile", "entity_id": 23, "X": 9.0, "Y": 9.0, "Z": 9.0},
        ]
    )
    dem = FakeDemo(make_ticks(), make_rounds(), None, grenades)
    players, sides = build_player_table(dem, lambda m: None)
    rounds = build_rounds(dem, players, sides, lambda m: None)
    round_map = {r.pop("_source_round"): r["round_number"] for r in rounds}

    events = build_grenade_events(dem, players, round_map, lambda m: None)
    check("นับเฉพาะลูกที่ขว้างจริง 2 ลูก (ไม่นับลูกที่ถืออยู่)", len(events), 2)
    check("แปลงชื่อคลาสเป็นชื่อสั้น", [e["weapon"] for e in events], ["smokegrenade", "inferno"])
    check("grenade_name ชื่อที่ไม่รู้จักคืนตัวพิมพ์เล็ก", grenade_name("CNewThing"), "cnewthing")


def main():
    test_helpers()
    test_players_and_rounds()
    test_events()
    test_grenade_projectile_filter()
    print(f"\nผ่าน {OK} ข้อ, ไม่ผ่าน {FAILED} ข้อ")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
