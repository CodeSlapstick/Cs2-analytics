# -*- coding: utf-8 -*-
"""fixtures ร่วมของ pytest — เดโมตัวอย่างที่ parse แล้ว (JSON) และตัวช่วยสร้าง doc สังเคราะห์"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))          # ให้ `pytest` จากรากโปรเจกต์ import backend.* ได้โดยไม่ต้องติดตั้ง

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def sample_doc() -> dict:
    """เดโมจริง 1 ไฟล์ที่ parser แกะไว้ (6 รอบ 31 คิล) — ใช้ทดสอบ feature layer โดยไม่ต้องมี .dem"""
    return json.loads((FIXTURES / "sample_match.json").read_text(encoding="utf-8"))


def make_doc(*, rounds, kills=(), player_rounds=(), damages=(), tickrate=128) -> dict:
    """สร้าง doc สังเคราะห์ในรูปเดียวกับ parser — ไว้เขียนเทสต์ที่คำนวณคำตอบด้วยมือได้"""
    return {
        "schema_version": 3,
        "match": {"demo_file": "Test-vs-Test-Mirage.dem", "map_name": "de_mirage", "tickrate": tickrate},
        "players": [],
        "rounds": list(rounds),
        "kills": list(kills),
        "damages": list(damages),
        "player_rounds": list(player_rounds),
        "grenades": [],
    }


def kill(round_num, tick, attacker, victim, a_side, v_side, *, assister=None, headshot=False) -> dict:
    return {"round_num": round_num, "tick": tick, "attacker_id": attacker, "victim_id": victim,
            "assister_id": assister, "attacker_side": a_side, "victim_side": v_side,
            "weapon": "ak47", "headshot": headshot}


def roster(round_num, ct: list[int], t: list[int], *, equip=None, survived=()) -> list[dict]:
    """player_rounds ของหนึ่งรอบ: ใครอยู่ฝั่งไหน (equip ใส่เป็น dict {steam_id: มูลค่า} ได้)"""
    equip = equip or {}
    rows = []
    for side, ids in (("ct", ct), ("t", t)):
        for sid in ids:
            rows.append({"round_num": round_num, "steam_id": sid, "side": side,
                         "equip_value": equip.get(sid, 4500), "balance": 0, "survived": sid in survived})
    return rows
