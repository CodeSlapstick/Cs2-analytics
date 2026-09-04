#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
features.py — สร้างฟีเจอร์ 5 ตัว: opening / trade / clutch / buy type / utility

    python pipeline/features.py

feature engineering คืออะไร
    ข้อมูลดิบบอกแค่ "ใครฆ่าใคร tick ไหน" — ยังไม่ใช่สิ่งที่โมเดลหรือ KPI ใช้ได้ตรง ๆ
    ไฟล์นี้แปลงเหตุการณ์ดิบเป็น "ความหมายในเกม" ที่คนดู CS เข้าใจ:
        opening  = คิลแรกของรอบ            (ใครเปิดรอบให้ทีม)
        trade    = ฆ่าคืนภายใน 5 วินาที      (ตายแล้วเพื่อนเก็บคืนได้ไหม)
        clutch   = เหลือคนเดียวเจอ N คน      (ใครพลิกรอบได้)
        buy type = มูลค่าอุปกรณ์ตอนรอบเริ่ม   (eco / force / full)
        utility  = ขว้างระเบิดกี่ลูก          (ใครใช้ util เก่ง)

แหล่งข้อมูล
    data/all_kills.csv          opening / trade / clutch      (50 แมตช์)
    data/positions_1hz.parquet  buy type                      (เฉพาะแมตช์ที่รัน downsample_ticks.py)
    data/grenades.parquet       utility                       (เฉพาะแมตช์ที่รัน parse_grenades.py)
    สองไฟล์หลังไม่มีก็รันได้ — ฟีเจอร์นั้นจะว่างไว้

ผลลัพธ์ (data/)
    features_kills.parquet    หนึ่งแถวต่อคิล    + is_opening / is_trade / was_traded / alive_*
    features_rounds.parquet   หนึ่งแถวต่อรอบ    opening ใคร, clutch ใคร, ทั้งสองฝั่งซื้ออะไร, ใช้ util กี่ลูก
    features_players.parquet  หนึ่งแถวต่อคน     สถิติรวม — ตั้งต้นสำหรับ role clustering (ML #2)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

TRADE_WINDOW_SEC = 5          # ฆ่าคืนภายในกี่วินาทีถึงนับเป็น trade (HLTV ใช้ 5)
PISTOL_ROUNDS = {1, 13}       # MR12: รอบ 1 กับ 13 เป็น pistol round เสมอ
# ขีดแบ่ง buy type จากมูลค่าอุปกรณ์ "รวมทั้งทีม" ตอน freeze time จบ (ตามเกณฑ์ HLTV)
BUY_BINS = [-1, 5000, 10000, 20000, 1e9]
BUY_LABELS = ["eco", "semi_eco", "semi_buy", "full"]

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


# ===========================================================================
# 0) โหลด + เตรียมตาราง kills
# ===========================================================================
# SteamID64 มี 17 หลัก เกินที่ float64 เก็บได้แม่น — ถ้าปล่อยให้ pandas เดา dtype คอลัมน์ที่มีช่องว่าง
# (attacker ว่างตอนตายเอง) จะกลายเป็น float แล้วหลักท้ายเพี้ยน จับคู่ attacker กับ victim ไม่ตรงกันเลย
STEAMID_COLS = {c: "Int64" for c in ("attacker_steamid", "victim_steamid", "assister_steamid")}
kills = pd.read_csv(DATA / "all_kills.csv", dtype=STEAMID_COLS)
kills = kills.sort_values(["demo_file", "round_num", "tick"], kind="stable").reset_index(drop=True)
kills["kill_id"] = np.arange(len(kills))
kills["second"] = (kills["tick"] - kills["round_start_tick"]) / kills["tickrate"]

# นับคนเหลือ "หลัง" และ "ก่อน" คิลนี้ — นับจากการตายทุกแบบ (ทีมคิล/ตกตึกก็ทำให้คนหายจริง)
rnd = kills.groupby(["demo_file", "round_num"], sort=False)
dead_ct = rnd["victim_side"].transform(lambda s: (s == "ct").cumsum())
dead_t = rnd["victim_side"].transform(lambda s: (s == "t").cumsum())
kills["alive_ct_after"] = (5 - dead_ct).clip(0, 5)
kills["alive_t_after"] = (5 - dead_t).clip(0, 5)
kills["alive_ct_before"] = kills["alive_ct_after"] + (kills["victim_side"] == "ct")
kills["alive_t_before"] = kills["alive_t_after"] + (kills["victim_side"] == "t")

# ฟีเจอร์ต่อจากนี้คิดจาก "การดวลกับศัตรู" เท่านั้น — ตัดทีมคิลกับตายเอง
duel = kills[kills["attacker_side"].notna() & (kills["attacker_side"] != kills["victim_side"])].copy()
duel["attacker_steamid"] = duel["attacker_steamid"].astype("int64")
duel["victim_steamid"] = duel["victim_steamid"].astype("int64")
print(f"kills {len(kills):,} แถว -> การดวล {len(duel):,} | {duel['demo_file'].nunique()} แมตช์")


# ===========================================================================
# 1) OPENING — คิลแรกของรอบ
# ===========================================================================
# ตารางเรียงตาม tick แล้ว แถวแรกของแต่ละรอบคือ opening
duel["is_opening"] = duel.groupby(["demo_file", "round_num"]).cumcount() == 0


# ===========================================================================
# 2) TRADE — ฆ่าคืนภายใน 5 วินาที
# ===========================================================================
# นิยาม: คิล B เป็น trade ของคิล A เมื่อ
#   - B.victim == A.attacker            (คนที่ฆ่าเพื่อนเรา ถูกฆ่า)
#   - อยู่รอบเดียวกัน และ 0 < B.tick - A.tick <= 5 วินาที
# วิธี: จับคู่ทุกคิลในรอบเดียวกัน (self-join) แล้วกรองตามเงื่อนไข
a = duel[["demo_file", "round_num", "kill_id", "tick", "attacker_steamid", "tickrate"]]
b = duel[["demo_file", "round_num", "kill_id", "tick", "victim_steamid"]].rename(
    columns={"kill_id": "kill_id_b", "tick": "tick_b", "victim_steamid": "victim_b"})
pairs = a.merge(b, on=["demo_file", "round_num"])
pairs = pairs[
    (pairs["victim_b"] == pairs["attacker_steamid"])
    & (pairs["tick_b"] > pairs["tick"])
    & (pairs["tick_b"] - pairs["tick"] <= TRADE_WINDOW_SEC * pairs["tickrate"])
]
duel["was_traded"] = duel["kill_id"].isin(pairs["kill_id"])      # คิลนี้ถูกแก้แค้นแล้ว
duel["is_trade"] = duel["kill_id"].isin(pairs["kill_id_b"])      # คิลนี้คือการแก้แค้น


# ===========================================================================
# 3) CLUTCH — เหลือคนเดียวเจอ N คน
# ===========================================================================
# ช่วงเวลาที่ฝั่งหนึ่งเหลือ 1 คนและอีกฝั่งเหลือ >= 1 คือ "สถานการณ์ clutch"
# จับที่คิลแรกที่ทำให้ฝั่งนั้นเหลือ 1 (เอา N = คนของศัตรูที่ยังอยู่ตอนนั้น)
#
# หาว่า "คนที่เหลือ" คือใคร: เอารายชื่อทีม ลบด้วยคนที่ตายไปแล้วในรอบ
# รายชื่อทีมต้องแยกตามช่วงที่ side คงที่ เพราะ CT/T สลับกันตอนครึ่งหลัง (MR12: หลังรอบ 12)
# และช่วงต่อเวลา (สลับทุก 3 รอบ) ถ้าไม่แยก รายชื่อจะปนกันสองทีม
def side_block(r: int) -> int:
    return 1 if r <= 12 else 2 if r <= 24 else 3 + (r - 25) // 3


kills["block"] = kills["round_num"].map(side_block)
roster: dict[tuple, set] = {}
for side in ("ct", "t"):
    att = kills[kills["attacker_side"] == side].dropna(subset=["attacker_steamid"])
    vic = kills[kills["victim_side"] == side]
    for (demo, blk), g in att.groupby(["demo_file", "block"]):
        roster.setdefault((demo, blk, side), set()).update(g["attacker_steamid"].astype("int64"))
    for (demo, blk), g in vic.groupby(["demo_file", "block"]):
        roster.setdefault((demo, blk, side), set()).update(g["victim_steamid"].astype("int64"))

clutch_rows = []
for (demo, r), g in kills.groupby(["demo_file", "round_num"], sort=False):
    winner = g["round_winner"].iloc[0]
    for side, other in (("ct", "t"), ("t", "ct")):
        hit = g[(g[f"alive_{side}_after"] == 1) & (g[f"alive_{other}_after"] >= 1)]
        if hit.empty:
            continue
        first = hit.iloc[0]
        dead_so_far = g[(g["tick"] <= first["tick"]) & (g["victim_side"] == side)]
        alive = roster.get((demo, side_block(r), side), set()) - set(dead_so_far["victim_steamid"].astype("int64"))
        clutch_rows.append({
            "demo_file": demo, "round_num": r,
            "clutch_side": side,
            "clutch_vs": int(first[f"alive_{other}_after"]),
            "clutch_steamid": alive.pop() if len(alive) == 1 else pd.NA,   # ระบุคนได้เมื่อรายชื่อครบเท่านั้น
            "clutch_won": winner == side,
        })
clutch = pd.DataFrame(clutch_rows)
# รอบที่เกิด 1v1 จะมีสองแถว (ทั้งสองฝั่ง) — เก็บทั้งคู่ไว้ แต่ตอนรวมต่อรอบเอาฝั่งที่ชนะ


# ===========================================================================
# 4) BUY TYPE — จากมูลค่าอุปกรณ์ตอน freeze time จบ
# ===========================================================================
# ใช้ current_equip_value ที่วินาที 0 ของรอบ (= ซื้อของเสร็จแล้ว)
# ไม่ใช้ round_start_equip_value เพราะเช็คแล้วมันไม่อัปเดตให้ทุกคน (ค้างที่ 200)
buy = pd.DataFrame()
pos_path = DATA / "positions_1hz.parquet"
if pos_path.exists():
    pos = pd.read_parquet(pos_path)
    start = pos[pos["second_in_round"] == 0].copy()
    start["side"] = np.where(start["team_name"] == "CT", "ct", "t")
    buy = (start.groupby(["demo_file", "round_num", "side"])["current_equip_value"].sum()
                .rename("team_equip").reset_index())
    buy["buy_type"] = pd.cut(buy["team_equip"], BUY_BINS, labels=BUY_LABELS).astype(str)
    buy.loc[buy["round_num"].isin(PISTOL_ROUNDS), "buy_type"] = "pistol"
    print(f"buy type: {buy['demo_file'].nunique()} แมตช์ (จาก positions_1hz.parquet)")
else:
    print("!! ไม่มี positions_1hz.parquet — ข้าม buy type (รัน pipeline/downsample_ticks.py ก่อน)")


# ===========================================================================
# 5) UTILITY — ขว้างระเบิดกี่ลูก
# ===========================================================================
util = pd.DataFrame()
gren_path = DATA / "grenades.parquet"
if gren_path.exists():
    gren = pd.read_parquet(gren_path)
    util = (gren.pivot_table(index=["demo_file", "round_num", "side"], columns="type",
                             values="tick", aggfunc="count", fill_value=0)
                .reset_index())
    util.columns.name = None
    print(f"utility: {gren['demo_file'].nunique()} แมตช์ (จาก grenades.parquet)")
else:
    print("!! ไม่มี grenades.parquet — ข้าม utility (รัน pipeline/parse_grenades.py ก่อน)")


# ===========================================================================
# 6) รวมเป็นตารางรายรอบ
# ===========================================================================
rounds = (kills.groupby(["demo_file", "round_num"])
               .agg(map_name=("map_name", "first"), winner=("round_winner", "first"),
                    end_reason=("round_end_reason", "first"))
               .reset_index())

op = duel[duel["is_opening"]][["demo_file", "round_num", "attacker_side", "attacker_steamid",
                               "victim_steamid", "second"]]
op.columns = ["demo_file", "round_num", "opening_side", "opening_attacker", "opening_victim", "opening_second"]
rounds = rounds.merge(op, how="left")
rounds["opening_side_won"] = rounds["opening_side"] == rounds["winner"]

if not clutch.empty:
    # ถ้ารอบหนึ่งมีสองฝั่งเข้า clutch (1v1) เอาฝั่งที่ชนะเป็นตัวแทนของรอบ
    c1 = clutch.sort_values("clutch_won", ascending=False).drop_duplicates(["demo_file", "round_num"])
    rounds = rounds.merge(c1, how="left")


def side_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """แปลงตารางที่มีแถว ct/t แยกกัน ให้เป็นคอลัมน์ ct_xxx / t_xxx ในแถวเดียวต่อรอบ"""
    wide = df.pivot(index=["demo_file", "round_num"], columns="side", values=cols)
    wide.columns = [f"{s}_{c}" for c, s in wide.columns]
    return wide.reset_index()


if not buy.empty:
    rounds = rounds.merge(side_cols(buy, ["team_equip", "buy_type"]), how="left")
if not util.empty:
    util_cols = [c for c in util.columns if c not in ("demo_file", "round_num", "side")]
    rounds = rounds.merge(side_cols(util, util_cols), how="left")
    # รอบที่ฝั่งนั้นไม่ได้ขว้างอะไรเลย (eco ล้วน) จะไม่มีแถวใน util -> ต้องเป็น 0 ไม่ใช่ "ไม่มีข้อมูล"
    # แต่แมตช์ที่ยังไม่ได้ parse grenade ปล่อยเป็น NaN ไว้ให้รู้ว่าไม่มีข้อมูลจริง ๆ
    has_gren = rounds["demo_file"].isin(util["demo_file"].unique())
    wide_util = [f"{s}_{c}" for s in ("ct", "t") for c in util_cols]
    rounds.loc[has_gren, wide_util] = rounds.loc[has_gren, wide_util].fillna(0)


# ===========================================================================
# 7) รวมเป็นตารางรายคน — ตั้งต้นสำหรับ role clustering
# ===========================================================================
names = pd.concat([duel[["attacker_steamid", "attacker_name"]].set_axis(["steamid", "name"], axis=1),
                   duel[["victim_steamid", "victim_name"]].set_axis(["steamid", "name"], axis=1)]
                  ).drop_duplicates("steamid", keep="last").set_index("steamid")["name"]

by_att = duel.groupby("attacker_steamid").agg(
    kills=("kill_id", "size"), opening_kills=("is_opening", "sum"), trade_kills=("is_trade", "sum"))
by_vic = duel.groupby("victim_steamid").agg(
    deaths=("kill_id", "size"), opening_deaths=("is_opening", "sum"), traded_deaths=("was_traded", "sum"))
rounds_seen = (pd.concat([duel[["demo_file", "round_num", "attacker_steamid"]].set_axis(["d", "r", "steamid"], axis=1),
                          duel[["demo_file", "round_num", "victim_steamid"]].set_axis(["d", "r", "steamid"], axis=1)])
                 .drop_duplicates().groupby("steamid").size().rename("rounds_seen"))

players = pd.concat([by_att, by_vic, rounds_seen], axis=1).fillna(0)
players.index.name = "steamid"
if not clutch.empty:
    cl = clutch.dropna(subset=["clutch_steamid"]).astype({"clutch_steamid": "int64"})
    cl = cl.groupby("clutch_steamid").agg(clutch_attempts=("clutch_won", "size"), clutch_wins=("clutch_won", "sum"))
    players = players.join(cl).fillna({"clutch_attempts": 0, "clutch_wins": 0})
if not util.empty:
    per_player = gren.pivot_table(index="steamid", columns="type", values="tick", aggfunc="count", fill_value=0)
    per_player.columns = [f"util_{c}" for c in per_player.columns]
    players = players.join(per_player)   # NaN = แมตช์ของคนนี้ยังไม่ได้ parse grenade

players.insert(0, "name", players.index.map(names))
for c in ("kills", "deaths", "opening_kills", "opening_deaths", "trade_kills", "traded_deaths", "rounds_seen"):
    players[c] = players[c].astype(int)
players["kd"] = (players["kills"] / players["deaths"].clip(lower=1)).round(2)
# เปิดรอบบ่อยแค่ไหน (เป็น entry ไม่ว่าจะฆ่าหรือตาย) — ตัวแยก entry fragger ออกจากคนอื่น
players["opening_rate"] = ((players["opening_kills"] + players["opening_deaths"]) / players["rounds_seen"]).round(3)
# ตายแล้วเพื่อนเก็บคืนได้กี่ส่วน — สูง = ตายแบบมีเพื่อนคุม ต่ำ = ตายเดี่ยว
players["traded_rate"] = (players["traded_deaths"] / players["deaths"].clip(lower=1)).round(3)
players = players.reset_index()


# ===========================================================================
# 8) เซฟ + สรุปให้เช็คด้วยตา
# ===========================================================================
duel.to_parquet(DATA / "features_kills.parquet", index=False)
rounds.to_parquet(DATA / "features_rounds.parquet", index=False)
players.to_parquet(DATA / "features_players.parquet", index=False)

print(f"\nรอบทั้งหมด {len(rounds):,} | ผู้เล่น {len(players):,}")
print(f"\n[opening]  ฝั่งที่ได้คิลแรก ชนะรอบ {rounds['opening_side_won'].mean():.1%}  "
      f"(CT เปิดได้ {(rounds['opening_side'] == 'ct').mean():.1%} ของรอบ)")
print(f"[trade]    คิลที่ถูกแก้แค้นใน {TRADE_WINDOW_SEC} วิ: {duel['was_traded'].mean():.1%} ของการดวล")
if not clutch.empty:
    cw = clutch.groupby("clutch_vs")["clutch_won"].agg(["size", "mean"])
    print("[clutch]   อัตราชนะตามจำนวนศัตรู:")
    for n, row in cw.iterrows():
        print(f"             1v{n}: {row['mean']:.1%}  ({int(row['size'])} ครั้ง)")
if not buy.empty:
    print("[buy type]", buy["buy_type"].value_counts().to_dict())
if not util.empty:
    # นับจากตารางรอบ (รอบที่ไม่ได้ขว้างเลย = 0) เฉพาะแมตช์ที่มีข้อมูล grenade
    has_util = rounds[rounds["demo_file"].isin(util["demo_file"].unique())]
    per_side = pd.DataFrame({s: has_util[[f"{s}_{c}" for c in util_cols]].fillna(0).mean().set_axis(util_cols)
                             for s in ("ct", "t")}).T.round(2)
    print("[utility]  ลูกต่อรอบต่อฝั่ง:\n" + per_side.to_string())

print("\nตัวอย่างตารางรายคน (เรียงตาม opening_kills):")
show = ["name", "rounds_seen", "kills", "deaths", "kd", "opening_kills", "opening_deaths", "trade_kills", "traded_rate"]
if "clutch_wins" in players:
    show += ["clutch_attempts", "clutch_wins"]
print(players.sort_values("opening_kills", ascending=False)[show].head(8).to_string(index=False))
print("\nเซฟแล้ว: features_kills / features_rounds / features_players .parquet ใน data/")
