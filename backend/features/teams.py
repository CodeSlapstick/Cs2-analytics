# -*- coding: utf-8 -*-
"""
backend/features/teams.py — ผูกผู้เล่นกับ "ทีม" ให้คงที่ทั้งแมตช์ (ไม่ใช่ side ที่สลับกันทุกครึ่ง)

    from backend.features.teams import assign_teams
    team_of = assign_teams(rows)     # rows: {steam_id, round_num, side, clan} หลายแถว -> {steam_id: ชื่อทีม}

หลักการ
    คนที่อยู่ side เดียวกันในรอบเดียวกัน = ทีมเดียวกัน, คนละ side ในรอบเดียวกัน = คนละทีม
    ไล่เชื่อมแบบนี้ทุกรอบจะได้สองกลุ่มเสมอ โดยไม่ต้องรู้ว่าสลับฝั่งรอบไหน (MR12, overtime)
    และคนที่ลงแทนกลางแมตช์ก็ถูกผูกเข้าทีมที่ถูกเอง เพราะเขาเล่นร่วมรอบกับเพื่อนร่วมทีม

ชื่อทีม
    clan tag ที่พบบ่อยที่สุดในกลุ่ม (เดโมแข่งจาก HLTV มีทุกไฟล์ — ตรวจแล้ว 50/50 ไฟล์)
    ไม่มี clan (MM / pug) -> "Team A" = กลุ่มที่อยู่ CT ในรอบแรกที่เห็น, "Team B" = อีกกลุ่ม
    (ยึด side ของครึ่งแรกตาม brief — รอบแรกที่มีข้อมูลคือรอบในครึ่งแรกเสมอ ถ้าเดโมไม่ขาดตอน)
"""
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping

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
