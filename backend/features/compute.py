# -*- coding: utf-8 -*-
"""
backend/features/compute.py — คำนวณฟีเจอร์จากผลของ parser (dict ที่ backend/parser/service.py คืนมา)

    from backend.features.compute import compute_features, aggregate_players
    rows = compute_features(doc)              # หนึ่งแถวต่อคนต่อรอบ (PlayerRoundFeatures)
    per_player = aggregate_players(rows)      # รวมต่อคน: ADR / KAST / opening / trade / clutch

ทุกฟังก์ชันเป็น pure function บน dict/list — ไม่แตะฐานข้อมูล จึงทดสอบได้ด้วย pytest ล้วน ๆ
นิยามทุกตัวมาจาก backend/features/definitions.py ไฟล์นี้แค่ "ทำตาม" ไม่ตั้งเกณฑ์เอง
"""
from collections import defaultdict
from dataclasses import asdict, dataclass, field

from backend.features.definitions import (
    FEATURES_VERSION,
    SIDES,
    buy_type,
    is_duel,
    other_side,
    trade_window_ticks,
)


@dataclass
class PlayerRoundFeatures:
    """สิ่งที่ผู้เล่นหนึ่งคนทำในหนึ่งรอบ — ตรงกับคอลัมน์ของตาราง player_rounds"""
    round_num: int
    steam_id: int
    side: str
    equip_value: int | None = None
    balance: int | None = None
    survived: bool = False
    buy_type: str | None = None
    kills: int = 0            # เฉพาะการดวล (ทีมคิลไม่นับ)
    deaths: int = 0           # ตายทุกแบบ (รวม C4 / ตกที่สูง) เพราะคนหายไปจากรอบจริง
    assists: int = 0
    headshots: int = 0
    damage: int = 0           # ดาเมจใส่ศัตรูเท่านั้น
    opening_kill: bool = False
    opening_death: bool = False
    trade_kills: int = 0      # ฆ่าคนที่เพิ่งฆ่าเพื่อนเราภายในหน้าต่าง trade
    was_traded: bool = False  # เราตาย แล้วเพื่อนเก็บคืนได้
    clutch_vs: int = 0        # 0 = รอบนี้ไม่ได้อยู่ในสถานการณ์ clutch
    clutch_won: bool | None = None
    kast: bool = False
    features_version: int = FEATURES_VERSION

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ClutchEvent:
    round_num: int
    side: str
    steam_id: int
    vs: int
    won: bool
    at_tick: int


@dataclass
class RoundContext:
    """ข้อมูลของรอบเดียวที่ทุกนิยามใช้ร่วมกัน"""
    round_num: int
    start_tick: int | None
    winner_side: str | None
    kills: list[dict] = field(default_factory=list)          # เรียงตาม tick แล้ว
    roster: dict[str, set[int]] = field(default_factory=dict)  # side -> {steam_id} ที่เล่นในรอบนี้


# ---------------------------------------------------------------------------
# เตรียมข้อมูล
# ---------------------------------------------------------------------------
def build_rounds(doc: dict) -> dict[int, RoundContext]:
    ctx: dict[int, RoundContext] = {}
    for r in doc.get("rounds", []):
        n = int(r["round_num"])
        ctx[n] = RoundContext(n, r.get("start_tick"), r.get("winner_side"), [], {s: set() for s in SIDES})
    for pr in doc.get("player_rounds", []):
        n = int(pr["round_num"])
        if n in ctx and pr.get("side") in SIDES:
            ctx[n].roster[pr["side"]].add(int(pr["steam_id"]))
    for k in doc.get("kills", []):
        n = int(k.get("round_num", 0))
        if n in ctx:
            ctx[n].kills.append(k)
    for c in ctx.values():
        c.kills.sort(key=lambda k: int(k["tick"]))   # sort เสถียร: tick เท่ากันคงลำดับเดิมของ parser
    return ctx


# ---------------------------------------------------------------------------
# นิยามที่ 1 — opening kill
# ---------------------------------------------------------------------------
def opening_kill(ctx: RoundContext) -> dict | None:
    """คิลแรกของรอบหลัง freeze-time จบ (การดวลเท่านั้น) — None ถ้ารอบนี้ไม่มีการดวล"""
    for k in ctx.kills:
        if not is_duel(k):
            continue
        if ctx.start_tick is not None and int(k["tick"]) < int(ctx.start_tick):
            continue   # ตายก่อน freeze จบ (แทบไม่เกิดในเกมจริง แต่ตามนิยามต้องตัด)
        return k
    return None


# ---------------------------------------------------------------------------
# นิยามที่ 2 — trade
# ---------------------------------------------------------------------------
def trade_pairs(ctx: RoundContext, tickrate: int) -> list[tuple[dict, dict]]:
    """คู่ (การตายที่ถูกแก้แค้น, คิลที่แก้แค้น) — คนฆ่า A ตายด้วยมือเพื่อนของ A ภายในหน้าต่าง"""
    window = trade_window_ticks(tickrate)
    duels = [k for k in ctx.kills if is_duel(k)]
    pairs = []
    for a in duels:                                   # a = การตายของเหยื่อ
        for b in duels:                               # b = คิลที่อาจเป็นการแก้แค้น
            if b["victim_id"] != a["attacker_id"]:
                continue                              # ต้องฆ่า "คนที่ฆ่า a"
            dt = int(b["tick"]) - int(a["tick"])
            if not (0 < dt <= window):
                continue
            if b["attacker_side"] != a["victim_side"]:
                continue                              # คนแก้แค้นต้องเป็นฝั่งเดียวกับเหยื่อ
            pairs.append((a, b))
    return pairs


# ---------------------------------------------------------------------------
# นิยามที่ 4 — clutch
# ---------------------------------------------------------------------------
def clutches(ctx: RoundContext) -> list[ClutchEvent]:
    """จับวินาทีที่ฝั่งหนึ่งเหลือคนเดียวขณะที่ศัตรูยังเหลือ >= 1 — ได้อย่างมากฝั่งละหนึ่งเหตุการณ์ต่อรอบ"""
    alive = {s: set(ctx.roster.get(s, set())) for s in SIDES}
    if not alive["ct"] or not alive["t"]:
        return []                                     # ไม่รู้รายชื่อทีม (เดโมไม่มี player_rounds) ตัดสินไม่ได้
    found: dict[str, ClutchEvent] = {}

    def check(tick: int) -> None:
        for side in SIDES:
            if side in found:
                continue
            enemies = len(alive[other_side(side)])
            if len(alive[side]) == 1 and enemies >= 1:
                (who,) = alive[side]
                found[side] = ClutchEvent(ctx.round_num, side, who, enemies, ctx.winner_side == side, tick)

    check(int(ctx.start_tick or 0))                   # เผื่อทีมเริ่มรอบด้วยคนเดียว (คนหลุดออกจากเกม)
    for k in ctx.kills:
        side = k.get("victim_side")
        if side in SIDES:
            alive[side].discard(int(k["victim_id"]))
        check(int(k["tick"]))
    return list(found.values())


# ---------------------------------------------------------------------------
# รวมทุกนิยามเป็นแถว "คนต่อรอบ"
# ---------------------------------------------------------------------------
def compute_features(doc: dict) -> list[PlayerRoundFeatures]:
    tickrate = int(doc.get("match", {}).get("tickrate") or 128)
    ctxs = build_rounds(doc)
    rows: dict[tuple[int, int], PlayerRoundFeatures] = {}

    for pr in doc.get("player_rounds", []):
        n, sid = int(pr["round_num"]), int(pr["steam_id"])
        rows[(n, sid)] = PlayerRoundFeatures(
            round_num=n, steam_id=sid, side=pr["side"],
            equip_value=pr.get("equip_value"), balance=pr.get("balance"), survived=bool(pr.get("survived", False)),
            buy_type=buy_type(pr.get("equip_value"), n),
        )

    def row(n: int, sid) -> PlayerRoundFeatures | None:
        return rows.get((n, int(sid))) if sid else None

    for n, ctx in ctxs.items():
        for k in ctx.kills:
            if (v := row(n, k.get("victim_id"))):
                v.deaths += 1
            if is_duel(k) and (a := row(n, k["attacker_id"])):
                a.kills += 1
                a.headshots += int(bool(k.get("headshot")))
            if (s := row(n, k.get("assister_id"))):
                s.assists += 1

        if (o := opening_kill(ctx)):
            if (a := row(n, o["attacker_id"])):
                a.opening_kill = True
            if (v := row(n, o["victim_id"])):
                v.opening_death = True

        for dead, avenger in trade_pairs(ctx, tickrate):
            if (v := row(n, dead["victim_id"])):
                v.was_traded = True
            if (a := row(n, avenger["attacker_id"])):
                a.trade_kills += 1

        for c in clutches(ctx):
            if (p := row(n, c.steam_id)):
                p.clutch_vs, p.clutch_won = c.vs, c.won

    # ดาเมจใส่ศัตรู — ต้องรู้ฝั่งของทั้งคู่ในรอบนั้น
    side_of: dict[tuple[int, int], str] = {(n, sid): r.side for (n, sid), r in rows.items()}
    for d in doc.get("damages", []):
        n = int(d.get("round_num", 0))
        att, vic = d.get("attacker_id"), d.get("victim_id")
        if not att or not vic:
            continue
        sa, sv = side_of.get((n, int(att))), side_of.get((n, int(vic)))
        if sa and sv and sa != sv and (a := row(n, att)):
            a.damage += int(d.get("damage", 0))

    for r in rows.values():
        r.kast = r.kills > 0 or r.assists > 0 or r.survived or r.was_traded
    return sorted(rows.values(), key=lambda r: (r.round_num, r.side, r.steam_id))


def aggregate_players(rows: list[PlayerRoundFeatures]) -> dict[int, dict]:
    """รวมต่อคนทั้งแมตช์ — ค่าที่หน้าเว็บโชว์ในสกอร์บอร์ด"""
    acc: dict[int, dict] = defaultdict(lambda: {
        "rounds": 0, "kills": 0, "deaths": 0, "assists": 0, "headshots": 0, "damage": 0, "kast_rounds": 0,
        "opening_kills": 0, "opening_deaths": 0, "trade_kills": 0, "traded_deaths": 0,
        "clutch_attempts": 0, "clutch_wins": 0, "buys": defaultdict(int), "start_side": None, "first_round": None,
    })
    for r in rows:
        a = acc[r.steam_id]
        a["rounds"] += 1
        for k in ("kills", "deaths", "assists", "headshots", "damage", "trade_kills"):
            a[k] += getattr(r, k)
        a["kast_rounds"] += int(r.kast)
        a["opening_kills"] += int(r.opening_kill)
        a["opening_deaths"] += int(r.opening_death)
        a["traded_deaths"] += int(r.was_traded)
        a["clutch_attempts"] += int(r.clutch_vs > 0)
        a["clutch_wins"] += int(bool(r.clutch_won))
        if r.buy_type:
            a["buys"][r.buy_type] += 1
        if a["first_round"] is None or r.round_num < a["first_round"]:
            a["first_round"], a["start_side"] = r.round_num, r.side
    out = {}
    for sid, a in acc.items():
        n = max(a["rounds"], 1)
        out[sid] = {**a, "buys": dict(a["buys"]),
                    "adr": round(a["damage"] / n, 1),
                    "kast": round(100.0 * a["kast_rounds"] / n, 1),
                    "hs_rate": round(100.0 * a["headshots"] / max(a["kills"], 1), 1)}
        out[sid].pop("first_round")
    return out
