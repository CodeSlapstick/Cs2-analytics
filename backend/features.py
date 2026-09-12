# -*- coding: utf-8 -*-
"""
backend/features.py — ฟีเจอร์ของผู้เล่น: นิยาม + ผูกทีม + ตัวคำนวณ (แหล่งเดียว ห้ามนิยามซ้ำที่อื่น)

    from backend.features import compute_features, aggregate_players, assign_teams

    opening_kill  คิลแรกของรอบหลัง freeze-time จบ
                  นับเฉพาะ "การดวล" (มีคนยิง และคนละฝั่ง) — ตายจาก C4 / ตกที่สูง / ทีมคิล ไม่ใช่การเปิดรอบ
    trade         คนที่ฆ่าเหยื่อ ตายภายใน TRADE_WINDOW_SEC วินาที ด้วยมือเพื่อนของเหยื่อ
                  (เพื่อน = อยู่ฝั่งเดียวกับเหยื่อในรอบนั้น)
    buy_type      มูลค่าอุปกรณ์ "ต่อคน" ตอน freeze-time จบ
                  Full >= BUY_FULL_MIN | Force ระหว่าง BUY_FORCE_MIN ถึง BUY_FULL_MIN | Eco < BUY_FORCE_MIN
                  Pistol = รอบใน PISTOL_ROUNDS เสมอ ไม่ว่าเงินเท่าไร
    clutch        เหลือคนเดียวฝั่งตัวเอง เจอศัตรู >= 1 และรอบยังไม่จบ
                  clutch_vs = จำนวนศัตรูที่ยังอยู่ ณ วินาทีที่เหลือคนเดียว, won = ฝั่งนั้นชนะรอบ
                  1v1 นับเป็น clutch ของทั้งสองฝั่ง
    ADR           ดาเมจที่ทำใส่ศัตรูรวม / จำนวนรอบที่เล่น
    KAST          % ของรอบที่ผู้เล่นทำได้อย่างน้อยหนึ่งอย่าง: Kill, Assist, Survived, Traded

ตัวเลขทุกตัวเป็นค่าตาม brief ของ Sprint 2 — ถ้าเปลี่ยน ให้ขยับ FEATURES_VERSION ด้วย
จะได้รู้ว่าแถวไหนในฐานข้อมูลคำนวณด้วยนิยามรุ่นเก่า (ต้อง backfill ใหม่)
"""
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field

# ==================================================================================================
# นิยาม (ตัวเลขทุกตัวตาม brief)
# ==================================================================================================
FEATURES_VERSION = 1

TRADE_WINDOW_SEC = 5          # ฆ่าคืนภายในกี่วินาทีถึงนับเป็น trade

BUY_FULL_MIN = 4000           # >= นี้ = full buy   (ต่อคน หน่วยเป็นดอลลาร์ในเกม)
BUY_FORCE_MIN = 2000          # >= นี้แต่ < BUY_FULL_MIN = force buy, ต่ำกว่านี้ = eco
PISTOL_ROUNDS = (1, 13)       # รอบปืนสั้น (MR12: ครึ่งละ 12 รอบ จึงเป็นรอบ 1 กับ 13)

BUY_TYPES = ("pistol", "full", "force", "eco")
SIDES = ("ct", "t")


def buy_type(equip_value: int | None, round_num: int) -> str | None:
    """จัดประเภทการซื้อของผู้เล่นหนึ่งคนในหนึ่งรอบ — None ถ้าไม่รู้มูลค่าอุปกรณ์ (เดโมไม่มีข้อมูล)"""
    if round_num in PISTOL_ROUNDS:
        return "pistol"
    if equip_value is None:
        return None
    if equip_value >= BUY_FULL_MIN:
        return "full"
    if equip_value >= BUY_FORCE_MIN:
        return "force"
    return "eco"


def trade_window_ticks(tickrate: int) -> int:
    """หน้าต่าง trade แปลงเป็น tick ของเดโมนั้น (64 หรือ 128 tick/วินาที)"""
    return TRADE_WINDOW_SEC * int(tickrate)


def is_duel(kill: dict) -> bool:
    """การดวลจริง = มีคนยิง และคนละฝั่งกับคนตาย (ตัด C4 / ตกที่สูง / ทีมคิล)"""
    return bool(kill.get("attacker_id")) and kill.get("attacker_side") in SIDES \
        and kill.get("victim_side") in SIDES and kill["attacker_side"] != kill["victim_side"]


def other_side(side: str) -> str:
    return "t" if side == "ct" else "ct"


# ==================================================================================================
# ผูกผู้เล่นกับทีมให้คงที่ทั้งแมตช์
# backend/features.py — ผูกผู้เล่นกับ "ทีม" ให้คงที่ทั้งแมตช์ (ไม่ใช่ side ที่สลับกันทุกครึ่ง)
#
#     from backend.features import assign_teams
#     team_of = assign_teams(rows)     # rows: {steam_id, round_num, side, clan} หลายแถว -> {steam_id: ชื่อทีม}
#
# หลักการ
#     คนที่อยู่ side เดียวกันในรอบเดียวกัน = ทีมเดียวกัน, คนละ side ในรอบเดียวกัน = คนละทีม
#     ไล่เชื่อมแบบนี้ทุกรอบจะได้สองกลุ่มเสมอ โดยไม่ต้องรู้ว่าสลับฝั่งรอบไหน (MR12, overtime)
#     และคนที่ลงแทนกลางแมตช์ก็ถูกผูกเข้าทีมที่ถูกเอง เพราะเขาเล่นร่วมรอบกับเพื่อนร่วมทีม
#
# ชื่อทีม
#     clan tag ที่พบบ่อยที่สุดในกลุ่ม (เดโมแข่งจาก HLTV มีทุกไฟล์ — ตรวจแล้ว 50/50 ไฟล์)
#     ไม่มี clan (MM / pug) -> "Team A" = กลุ่มที่อยู่ CT ในรอบแรกที่เห็น, "Team B" = อีกกลุ่ม
#     (ยึด side ของครึ่งแรกตาม brief — รอบแรกที่มีข้อมูลคือรอบในครึ่งแรกเสมอ ถ้าเดโมไม่ขาดตอน)
# ==================================================================================================
FALLBACK_NAMES = ("Team A", "Team B")     # [0] = เริ่มเกมฝั่ง CT, [1] = เริ่มเกมฝั่ง T


def _clean(clan) -> str | None:
    if clan is None:
        return None
    s = str(clan).strip()
    return s or None


def assign_teams(rows: Iterable[Mapping]) -> dict[int, str]:
    """คืน {steam_id: ชื่อทีม} — ทุกคนที่โผล่ใน rows ได้ทีมเสมอ"""
    side_at: dict[tuple[int, int], str] = {}              # (steam_id, round) -> side
    clans: dict[int, Counter] = defaultdict(Counter)
    for r in rows:
        sid = r.get("steam_id")
        side = r.get("side")
        if sid is None or side not in ("ct", "t"):
            continue
        sid = int(sid)
        side_at.setdefault((sid, int(r["round_num"])), side)
        if (c := _clean(r.get("clan"))):
            clans[sid][c] += 1
    if not side_at:
        return {}

    # ---- 1) แบ่งสองกลุ่มด้วยการระบายสองสี: เพื่อนร่วมรอบฝั่งเดียวกัน = สีเดียวกัน, คนละฝั่ง = สีตรงข้าม
    by_round: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for (sid, rnd), side in side_at.items():
        by_round[rnd].append((sid, side))
    neighbours: dict[int, list[tuple[int, int]]] = defaultdict(list)   # sid -> [(อีกคน, 0 ทีมเดียวกัน / 1 คนละทีม)]
    for members in by_round.values():
        for i, (a, sa) in enumerate(members):
            for b, sb in members[i + 1:]:
                w = 0 if sa == sb else 1
                neighbours[a].append((b, w))
                neighbours[b].append((a, w))

    first_round = min(by_round)
    anchor = min(sid for sid, side in by_round[first_round] if side == "ct") \
        if any(side == "ct" for _, side in by_round[first_round]) else by_round[first_round][0][0]
    colour: dict[int, int] = {}
    everyone = sorted({sid for sid, _ in side_at})
    # เริ่มจากคนที่อยู่ CT ในรอบแรก ให้เป็นกลุ่ม 0 — กลุ่มแยกขาด (ไม่มีรอบร่วมกันเลย) ค่อยเริ่มใหม่ทีหลัง
    for start in [anchor, *everyone]:
        if start in colour:
            continue
        rnd0 = min(r for (s, r) in side_at if s == start)
        colour[start] = 0 if side_at[(start, rnd0)] == "ct" else 1
        stack = [start]
        while stack:
            a = stack.pop()
            for b, w in neighbours[a]:
                if b not in colour:
                    colour[b] = colour[a] ^ w
                    stack.append(b)

    # ---- 2) ตั้งชื่อกลุ่ม: clan ที่พบบ่อยสุด ถ้าไม่มีหรือชื่อชนกันใช้ Team A / B
    names: list[str | None] = [None, None]
    for g in (0, 1):
        total = Counter()
        for sid, c in colour.items():
            if c == g:
                total.update(clans.get(sid, Counter()))
        if total:
            names[g] = total.most_common(1)[0][0]
    if names[0] is None or names[1] is None or names[0] == names[1]:
        names = list(FALLBACK_NAMES)
    return {sid: names[c] for sid, c in colour.items()}


# ==================================================================================================
# คำนวณฟีเจอร์ต่อคนต่อรอบ + รวมต่อคน
# backend/features.py — คำนวณฟีเจอร์จากผลของ parser (dict ที่ backend/parser.py คืนมา)
#
#     from backend.features import compute_features, aggregate_players
#     rows = compute_features(doc)              # หนึ่งแถวต่อคนต่อรอบ (PlayerRoundFeatures)
#     per_player = aggregate_players(rows)      # รวมต่อคน: ADR / KAST / opening / trade / clutch
#
# ทุกฟังก์ชันเป็น pure function บน dict/list — ไม่แตะฐานข้อมูล จึงทดสอบได้ด้วย pytest ล้วน ๆ
# นิยามทุกตัวมาจาก backend/features.py ไฟล์นี้แค่ "ทำตาม" ไม่ตั้งเกณฑ์เอง
# ==================================================================================================
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


# ---------------------------------------------------------------------------
# HLTV Rating 2.0 — "ประมาณการ" เท่านั้น
#   HLTV ไม่เปิดสูตรจริงของ 2.0 (1.0 เปิด และอยู่ใน views.sql แล้ว)
#   ชุดสัมประสิทธิ์ข้างล่างคือสูตรถดถอยที่ชุมชนหามาจากการ fit กับค่าที่ HLTV แสดง
#   ใช้ได้ในความหมาย "ใกล้เคียง" — ห้ามเรียกว่า Rating 2.0 ของ HLTV ในหน้าเว็บ ต้องเขียนว่าเป็นค่าประมาณ
#   ตัวแปร: KPR/DPR/APR = kill/death/assist ต่อรอบ · KAST เป็น % · ADR = ดาเมจต่อรอบ
# ---------------------------------------------------------------------------
RATING2 = {"kast": 0.0073, "kpr": 0.3591, "dpr": -0.5329, "impact": 0.2372, "adr": 0.0032, "const": 0.1587}
IMPACT = {"kpr": 2.13, "apr": 0.42, "const": -0.41}


def impact_rating(kills, assists, rounds) -> float:
    """Impact — ส่วนประกอบหนึ่งของ Rating 2.0 (สูตรประมาณการเช่นกัน)

    ตัวเลขที่มาจาก SQL เป็น Decimal — แปลงเป็น float ก่อนเสมอ (float * Decimal โยน TypeError)
    """
    kills, assists, rounds = float(kills), float(assists), float(rounds)
    if rounds <= 0:
        return 0.0
    return IMPACT["kpr"] * (kills / rounds) + IMPACT["apr"] * (assists / rounds) + IMPACT["const"]


def rating2_approx(*, kills, deaths, assists, damage, kast_rounds, rounds) -> float:
    """ค่าประมาณของ HLTV Rating 2.0 — 0 รอบ = 0.0 (ไม่เดาค่าให้) · รับ Decimal จาก SQL ได้"""
    kills, deaths, assists = float(kills), float(deaths), float(assists)
    damage, kast_rounds, rounds = float(damage), float(kast_rounds), float(rounds)
    if rounds <= 0:
        return 0.0
    kast = 100.0 * kast_rounds / rounds
    return round(
        RATING2["kast"] * kast
        + RATING2["kpr"] * (kills / rounds)
        + RATING2["dpr"] * (deaths / rounds)
        + RATING2["impact"] * impact_rating(kills, assists, rounds)
        + RATING2["adr"] * (damage / rounds)
        + RATING2["const"],
        2,
    )

