"""Opening Route derivation owner. Pure functions; SQL stays in app.py.

Coordinates and utility projection reuse review.py. No guessed match dates,
freeze ticks, projectile paths, or effect durations are supplied here.
"""
import math
import re
from collections import defaultdict
from datetime import date
from statistics import median

from backend.review import build_grenade_rows, radar_frame, world_to_pixel

WINDOW_SECONDS = 30


def match_date(demo_file: str) -> str | None:
    """Only an explicit ISO calendar date in a filename is available today."""
    found = re.search(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)", demo_file)
    if found:
        try:
            return date.fromisoformat(found[1]).isoformat()
        except ValueError:
            pass
    return None


def select_matches(matches: list[dict], limit: int) -> list[dict]:
    # Undated matches cannot truthfully be called the latest. All includes them,
    # ordered after known dates; filename is only a deterministic tie-breaker.
    dated = [m for m in matches if match_date(m["demo_file"]) is not None]
    pool = dated if limit else matches
    ordered = sorted(pool, key=lambda m: (match_date(m["demo_file"]) or "", m["demo_file"]), reverse=True)
    return ordered[:limit] if limit else ordered


def build_opening_rounds(matches, rounds, positions, grenades, steam_id, map_name):
    frame = radar_frame(map_name)
    match_by_id = {m["id"]: m for m in matches}
    pos_by_round, utility_by_round = defaultdict(list), defaultdict(list)
    for point in positions:
        pos_by_round[point["round_id"]].append(point)
    for utility in grenades:
        utility_by_round[utility["round_id"]].append(utility)
    output = []
    for rnd in rounds:
        match = match_by_id[rnd["match_id"]]
        start, rate = rnd.get("start_tick"), match.get("tickrate")
        clock_available = start is not None and rate is not None and rate > 0
        death = rnd.get("death_tick")
        samples = []
        break_before = False
        if clock_available and frame:
            for point in sorted(pos_by_round[rnd["id"]], key=lambda p: p["tick"]):
                tick = point["tick"]
                if not start <= tick <= start + WINDOW_SECONDS * rate:
                    continue
                if death is not None and tick >= death:
                    break
                if point.get("health") is not None and point["health"] <= 0:
                    break
                x, y = point.get("x"), point.get("y")
                if x is None or y is None or not math.isfinite(x) or not math.isfinite(y):
                    break_before = True
                    continue
                px = world_to_pixel(x, y, frame)
                sample = {"t": (tick - start) / rate, "px": list(px), "break_before": break_before}
                if not samples or sample["t"] > samples[-1]["t"]:
                    samples.append(sample)
                    break_before = False
        gaps = [b["t"] - a["t"] for a, b in zip(samples, samples[1:])]
        # 8 Hz: <=0.1875s; legacy 1 Hz: <=1.5s. Never bridge a
        # multi-second outage, even if a sparse recording has a larger median.
        max_gap = min(1.5, median(gaps) * 1.5) if gaps else 0.1875
        segments = []
        for sample in samples:
            if not segments or sample["break_before"] or sample["t"] - segments[-1][-1]["t"] > max_gap:
                segments.append([])
            segments[-1].append({"t": sample["t"], "px": sample["px"]})

        def person(sid, name, side):
            return {"steamid": str(sid), "name": name or str(sid), "side": side,
                    "color": None, "slot": None}

        events = []
        if clock_available:
            raw = [g for g in utility_by_round[rnd["id"]]
                   if start <= g["tick"] <= start + WINDOW_SECONDS * rate]
            events = build_grenade_rows(raw, person, start=start, tickrate=rate, frame=frame)
        output.append({
            "key": f'{match["id"]}:{rnd["round_num"]}',
            "demo_file": match["demo_file"], "match_name": " vs ".join(
                n for n in (match.get("team_a"), match.get("team_b")) if n) or match["demo_file"],
            "match_date": match_date(match["demo_file"]), "round_num": rnd["round_num"],
            "side": rnd["side"], "clock_available": clock_available,
            "segments": segments, "max_gap": max_gap,
            "death_t": (death - start) / rate if clock_available and death is not None else None,
            "utility": events if clock_available else None,
        })
    return {"radar": {"image": "/assets" + frame.image, "size": frame.size, "map": frame.map_name}
            if frame else None, "rounds": output}
