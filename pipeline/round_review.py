#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ดึงข้อมูลรายรอบของ "หนึ่งแมตช์" ออกมาเป็น json ให้หน้าเว็บรีวิวรอบใช้

    python pipeline/round_review.py                          # ใช้ไฟล์ตั้งต้น
    python pipeline/round_review.py demos/G2-vs-Aurora-Mirage.dem
    python pipeline/round_review.py --team Legacy            # เลือกว่าทีมไหนคือ "ของเรา"

ต่างจาก demoparser.py ตรงไหน
    demoparser.py รวมคิลของทุกแมตช์เข้าด้วยกันเพื่อเอาไปเทรนโมเดล ทิ้งบริบทของรอบไป
    ไฟล์นี้ทำตรงข้าม — เจาะแมตช์เดียวแต่เก็บว่าแต่ละรอบใครชนะ ชนะด้วยอะไร
    ระเบิดลงไซต์ไหน และคิลแต่ละครั้งเกิดวินาทีที่เท่าไรของรอบ

เรื่องฝั่งที่ต้องระวัง
    CT/T สลับกันตอนครึ่งหลัง ทีมเดิมจึงเป็นคนละ side คนละครึ่ง
    ถ้าเก็บแค่ side แล้วสรุปว่า "ทีมเราชนะกี่รอบ" จะได้ตัวเลขผิดทันที
    จึงอ่านชื่อทีมจริง (clan name) จากคิลในรอบนั้นมาเทียบทุกครั้ง
"""
import argparse
import json
import sys
from pathlib import Path

import polars as pl
from awpy import Demo
from awpy.parsers.rounds import create_round_df

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEMO = ROOT / "demos" / "Vitality-vs-Legacy-Mirage.dem"
OUT = ROOT / "output" / "round_review.json"
WIN_TABLE = ROOT / "output" / "round_win.json"     # สร้างด้วย pipeline/round_win.py

EVENTS = [
    "player_death", "round_start", "round_freeze_end", "round_end",
    "round_officially_ended", "bomb_planted", "bomb_defused",
]
PLAYER_PROPS = ["last_place_name", "X", "Y", "Z", "health", "team_name", "team_clan_name"]

# reason ที่ awpy คืนมาเป็นสตริงดิบ แปลงเป็นคำที่คนอ่านรู้เรื่อง
REASON_TH = {
    "ct_killed": "ยิง CT หมดทีม",
    "t_killed": "ยิง T หมดทีม",
    "bomb_exploded": "ระเบิดลง",
    "bomb_defused": "ปลดระเบิดได้",
    "target_bombed": "ระเบิดลง",
    "target_saved": "หมดเวลา",
    "time_ran_out": "หมดเวลา",
}

def load_win_table():
    """ตารางเปิดค่า P(CT ชนะรอบ) — ไม่มีก็รันต่อได้ แค่ไม่มีเส้นโอกาสชนะให้ดู"""
    if not WIN_TABLE.exists():
        return None
    return json.loads(WIN_TABLE.read_text(encoding="utf-8"))


def win_prob(wt, alive_ct, alive_t, planted, t_sec):
    """เปิดค่าจากตาราง — คืน None ถ้าสถานะอยู่นอกตาราง

    สองสถานะที่ตารางไม่มีและไม่ต้องมี: ฝั่งไหนเหลือ 0 คนคือรอบจบไปแล้ว
    ตอบได้แน่นอนโดยไม่ต้องใช้โมเดล จึงตอบ 0 หรือ 1 ตรง ๆ
    """
    if alive_ct <= 0:
        return 0.0
    if alive_t <= 0:
        return 1.0
    edges, names = wt["time_edges"], wt["time_names"]
    tcat = names[-1]
    for i, e in enumerate(edges):
        if t_sec < e:
            tcat = names[i]
            break
    key = f"{alive_ct}v{alive_t}|{int(planted)}|{tcat}"
    return wt["table"].get(key)


for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description="ดึงข้อมูลรายรอบของหนึ่งแมตช์เป็น json")
    ap.add_argument("demo", nargs="?", type=Path, default=DEFAULT_DEMO)
    ap.add_argument("--team", help="ชื่อทีมที่ถือว่าเป็น 'ของเรา' (ไม่ใส่ = ทีมแรกที่เจอ)")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    if not args.demo.exists():
        sys.exit(f"ไม่พบไฟล์ {args.demo}")

    print(f"อ่าน {args.demo.name} ...", flush=True)
    dem = Demo(args.demo)
    dem.events = dem.parse_events(EVENTS, player_props=PLAYER_PROPS)
    dem.rounds = create_round_df(dem.events)
    kills = dem.kills

    tickrate = dem.tickrate
    radar = json.loads((ROOT / "assets" / "radars.json").read_text(encoding="utf-8"))
    map_name = dem.header.get("map_name", "unknown")
    if map_name not in radar:
        sys.exit(f"ยังไม่มีค่าปรับเทียบเรดาร์ของ {map_name} ใน assets/radars.json")

    # --- ชื่อทีมสองทีม เอาจากคอลัมน์ฝั่งในแถวคิล ซึ่งบอกชื่อ clan ของทั้งสองฝั่งอยู่แล้ว ---
    clans = sorted({c for col in ("ct_team_clan_name", "t_team_clan_name")
                    for c in kills[col].drop_nulls().unique().to_list()})
    if len(clans) != 2:
        sys.exit(f"หาชื่อทีมไม่ได้สองทีมพอดี เจอ {clans}")
    ours = args.team or clans[0]
    if ours not in clans:
        sys.exit(f"ไม่มีทีมชื่อ {ours} ในแมตช์นี้ — มี {clans}")
    theirs = next(c for c in clans if c != ours)

    wt = load_win_table()
    if wt is None:
        print(f"!! ไม่พบ {WIN_TABLE.name} — จะไม่มีเส้นโอกาสชนะรอบ "
              f"(รัน python pipeline/round_win.py ก่อน)")

    rounds_out = []
    score = {ours: 0, theirs: 0}

    for r in dem.rounds.iter_rows(named=True):
        rn = r["round_num"]
        rk = kills.filter(pl.col("round_num") == rn).sort("tick")
        if rk.is_empty():
            continue

        # ตัดการตายที่ไม่ใช่การดวลออก ไม่งั้นบางรอบจะได้ 16 คิลทั้งที่ในรอบมีคนแค่ 10
        #   ตัวเองฆ่าตัวเอง / ตกที่สูง (weapon = "world") -> attacker เป็นคนเดียวกับ victim
        #   ตายก่อนหมด freeze time -> tick น้อยกว่าจุดเริ่มจับเวลา ไม่ได้อยู่ในรอบจริง
        rk = rk.filter(
            pl.col("attacker_name").is_not_null()
            & (pl.col("attacker_name") != pl.col("victim_name"))
            & (pl.col("tick") >= (r["freeze_end"] or r["start"]))
        )
        if rk.is_empty():
            continue

        # ใครอยู่ฝั่งไหนในรอบนี้ — อ่านสด ๆ ทุกรอบเพราะครึ่งหลังสลับข้าง
        # เก็บเป็นชื่อทีมไม่ใช่ "ของเรา/ของเขา" หน้าเว็บจะได้สลับมุมมองเองได้
        first = rk.row(0, named=True)
        ct_clan = first["ct_team_clan_name"]
        t_clan = first["t_team_clan_name"]
        winner_clan = ct_clan if r["winner"] == "ct" else t_clan
        score[winner_clan] += 1

        start = r["freeze_end"] or r["start"]        # จับเวลาตั้งแต่หมดช่วง freeze
        sec = lambda tick: round((tick - start) / tickrate, 1)
        pos = lambda v: None if v is None else round(v)

        kl = []
        for k in rk.iter_rows(named=True):
            kl.append({
                "t": sec(k["tick"]),
                "atk": k["attacker_name"],
                "atk_clan": k["attacker_team_clan_name"],
                "vic": k["victim_name"],
                "vic_clan": k["victim_team_clan_name"],
                "weapon": k["weapon"],
                "hs": bool(k["headshot"]),
                # พิกัดทั้งคนยิงและศพ ไว้ลากเป็นเส้นการดวลบนแผนที่
                "ax": pos(k["attacker_X"]), "ay": pos(k["attacker_Y"]),
                "x": pos(k["victim_X"]), "y": pos(k["victim_Y"]),
                "place": k["victim_place"],
            })

        # --- เส้นโอกาสชนะรอบ: จุดแรกคือตอนเริ่ม 5v5 แล้วขยับทุกครั้งที่มีคนตาย ---
        # ค่าที่เก็บคือ P(CT ชนะรอบ) เสมอ หน้าเว็บค่อยพลิกเองว่าตอนนั้น "ทีมเรา" คือฝั่งไหน
        wp = None
        if wt is not None:
            ct_alive, t_alive = 5, 5
            plant_t = r["bomb_plant"]
            start_wp = win_prob(wt, 5, 5, False, 0.0)
            wp = [{"t": 0.0, "p": start_wp, "i": None}]
            for i, k in enumerate(kl):
                if k["vic_clan"] == ct_clan:
                    ct_alive -= 1
                else:
                    t_alive -= 1
                planted = plant_t is not None and (start + k["t"] * tickrate) >= plant_t
                wp.append({"t": k["t"], "p": win_prob(wt, ct_alive, t_alive, planted, k["t"]), "i": i})
            # เติมจุดปิดท้ายที่เวลาจบรอบ ให้เส้นลากไปสุดรอบ ไม่ค้างกลางทาง
            wp.append({"t": sec(r["end"]), "p": wp[-1]["p"], "i": None})

        rounds_out.append({
            "n": rn,
            "wp": wp,
            "ct_clan": ct_clan,
            "t_clan": t_clan,
            "winner_clan": winner_clan,
            "reason": REASON_TH.get(r["reason"], r["reason"] or "—"),
            "bomb_site": None if r["bomb_site"] == "not_planted" else r["bomb_site"],
            "bomb_plant_t": None if r["bomb_plant"] is None else sec(r["bomb_plant"]),
            "length": sec(r["end"]),
            "kills": kl,
            # เปิดหัวได้หรือเสียหัว เป็นตัวชี้ผลรอบที่คนดูเกมดูกันจริง ๆ
            "opening_clan": kl[0]["atk_clan"] if kl else None,
            "score_after": dict(score),
        })

    # --- สถิติรายคนทั้งแมตช์ ไว้โชว์ว่าใครเป็นคนพาทีมไป ---
    # นับคิลเฉพาะที่ยิงข้ามฝั่ง (ทีมคิลไม่นับให้) ส่วนการตายนับทุกกรณีตามที่ในเกมนับ
    players = {}
    def slot(name, clan):
        return players.setdefault(name, {"name": name, "clan": clan, "k": 0, "d": 0, "hs": 0})

    for k in kills.iter_rows(named=True):
        if k["victim_name"]:
            slot(k["victim_name"], k["victim_team_clan_name"])["d"] += 1
        atk = k["attacker_name"]
        if atk and atk != k["victim_name"] and k["attacker_side"] != k["victim_side"]:
            p = slot(atk, k["attacker_team_clan_name"])
            p["k"] += 1
            if k["headshot"]:
                p["hs"] += 1

    payload = {
        "demo_file": args.demo.name,
        "map": map_name,
        "radar": {k: radar[map_name][k] for k in ("image", "size", "pos_x", "pos_y", "scale")},
        "tickrate": tickrate,
        "clans": [ours, theirs],          # ตัวแรกคือทีมที่ตั้งเป็น "ของเรา" ตอนเปิดหน้า
        "score": dict(score),
        "rounds": rounds_out,
        "players": sorted(players.values(), key=lambda p: -p["k"]),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    print(f"{ours} {score[ours]} - {score[theirs]} {theirs} | {len(rounds_out)} รอบ "
          f"| {sum(len(r['kills']) for r in rounds_out)} คิล | แมพ {map_name}")
    print(f"เซฟที่ {args.out}")


if __name__ == "__main__":
    main()
