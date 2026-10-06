"""Coach feature/model owner. Observational tactic candidates, never causal advice.

Opening pattern discovery uses recorded 5/15/25s spatial summaries and 0-30s
Utility. Recommendation input uses ONLY pre-round equipment/phase. No target
round result, movement or Utility enters the recommendation input.
"""
import json
import math
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from backend.features import buy_type

MODEL_PATH = Path(__file__).resolve().parent.parent / "output" / "coach_model.json"
VERSION = "coach-opening-patterns-v1"
CONTEXT_FEATURES = ["mean_equip", "spread_equip", "full_share", "force_share", "eco_share", "pistol"]
AREAS = ["a", "mid", "b", "other"]
UTILITY = ["flash", "smoke", "molotov", "he", "decoy"]
OPENING_FEATURES = [f"{area}_{time}" for time in (5, 15, 25) for area in AREAS] + UTILITY
AREA_PLACES = {
    "a": {"TRamp", "PalaceInterior", "PalaceAlley", "BombsiteA", "Stairs", "Jungle", "Scaffolding"},
    "mid": {"TopofMid", "Middle", "Underpass", "Connector", "Catwalk", "SnipersNest", "Ladder"},
    "b": {"Apartments", "BackAlley", "BombsiteB", "Shop", "Truck", "House"},
}


def round_context(players: list[dict], number: int) -> list[float] | None:
    if len(players) != 5 or any(p.get("equip_value") is None for p in players):
        return None
    equipment = [float(p["equip_value"]) for p in players]
    if any(not math.isfinite(v) or v < 0 for v in equipment):
        return None
    mean = sum(equipment) / 5
    types = [buy_type(p["equip_value"], number) for p in players]
    return [mean / 10000, math.sqrt(sum((v - mean) ** 2 for v in equipment) / 5) / 10000,
            types.count("full") / 5, types.count("force") / 5, types.count("eco") / 5,
            float(types[0] == "pistol")]


def build_coach_samples(data: dict) -> list[dict]:
    groups, positions, utility = defaultdict(list), defaultdict(list), defaultdict(dict)
    for fact in data["facts"]:
        if fact.get("side") in ("t", "ct"):
            groups[(fact["round_id"], fact["side"])].append(fact)
    for point in data["positions"]:
        positions[(point["round_id"], point["side"])].append(point)
    for event in data["utility"]:
        utility[(event["round_id"], event["side"])][event["type"]] = event["n"]
    samples = []
    for key, players in groups.items():
        row = players[0]
        context = round_context(players, row["round_num"])
        opening = []
        start, rate = row.get("start_tick"), row.get("tickrate")
        complete = context is not None and start is not None and rate is not None and rate > 0
        points = positions[key]
        for time in (5, 15, 25):
            ticks = {p["tick"] for p in points}
            tick = min(ticks, key=lambda t: abs(t - (start + time * rate))) if complete and ticks else None
            snap = [p for p in points if p["tick"] == tick and p.get("place")]
            # No synthetic snapshots: requires >=3 observed living players and
            # an actual sample within 0.6s of the requested time (legacy 1Hz).
            if tick is None or abs(tick - (start + time * rate)) / rate > .6 or len(snap) < 3:
                complete = False
                break
            counts = dict.fromkeys(AREAS, 0)
            for point in snap:
                area = next((name for name, places in AREA_PLACES.items() if point["place"] in places), "other")
                counts[area] += 1
            opening.extend(counts[a] / len(snap) for a in AREAS)
        if complete:
            opening.extend(min(utility[key].get(kind, 0), 15) / 15 for kind in UTILITY)
        samples.append({"match_id": row["match_id"], "demo_file": row["demo_file"],
                        "round_num": row["round_num"], "side": key[1], "source": row["source"],
                        "won": row.get("winner_side") == key[1] if row.get("winner_side") in ("t", "ct") else None,
                        "context": context, "opening": opening if complete else None})
    return samples


def load_coach_model(path: Path = MODEL_PATH) -> dict | None:
    try:
        return _read_coach_model(str(path), path.stat().st_mtime_ns)
    except OSError:
        return None


@lru_cache(maxsize=2)
def _read_coach_model(path: str, stamp: int) -> dict | None:
    try:
        model = json.loads(Path(path).read_text(encoding="utf-8"))
        return model if model.get("version") == VERSION else None
    except (OSError, ValueError, TypeError):
        return None


def nearest_pattern(opening: list[float], spec: dict) -> int:
    z = [(x - mean) / scale for x, mean, scale in zip(opening, spec["mean"], spec["scale"], strict=True)]
    return min(range(len(spec["centers"])), key=lambda i: sum((a - b) ** 2 for a, b in zip(z, spec["centers"][i], strict=True)))


def tree_distribution(context: list[float], tree: dict) -> list[float]:
    node = 0
    while tree["left"][node] != -1:
        node = tree["left"][node] if context[tree["feature"][node]] <= tree["threshold"][node] else tree["right"][node]
    weights = tree["values"][node]
    total = sum(weights)
    return [v / total if total else 0 for v in weights]


def recommend_round(sample: dict, model: dict | None, *, map_name: str, exclude_match: int | None = None) -> dict:
    base = {"round_num": sample["round_num"], "side": sample["side"], "options": []}
    if not model or model.get("map") != map_name or sample["side"] not in model.get("sides", {}):
        return {**base, "available": False, "reason": "model_unavailable"}
    if sample["context"] is None:
        return {**base, "available": False, "reason": "missing_economy"}
    spec = model["sides"][sample["side"]]
    if exclude_match in model["training_match_ids"]:
        return {**base, "available": False, "reason": "training_match"}
    distributions = [tree_distribution(sample["context"], tree) for tree in spec["trees"]]
    scores = [sum(d[i] for d in distributions) / len(distributions) for i in range(len(spec["classes"]))]
    options = []
    for cls, score in sorted(zip(spec["classes"], scores, strict=True), key=lambda p: -p[1])[:3]:
        pattern = spec["patterns"][str(cls)]
        if pattern["rounds"] < 20 or pattern["matches"] < 3:
            continue
        candidates = [r for r in pattern["evidence"] if r["match_id"] != exclude_match]
        candidates.sort(key=lambda r: sum((a - b) ** 2 for a, b in zip(sample["context"], r["context"], strict=True)))
        options.append({"id": cls, "name": pattern["name"], "match_share": round(score, 4),
                        "rounds": pattern["rounds"], "matches": pattern["matches"],
                        "profile": pattern["profile"], "evidence": [{k: r[k] for k in ("demo_file", "round_num", "side")} for r in candidates[:3]]})
    observed = nearest_pattern(sample["opening"], spec) if sample["opening"] is not None else None
    return {**base, "available": bool(options), "reason": None if options else "insufficient_support",
            "experimental": not spec["validation"]["beats_baseline"],
            "observed_pattern": observed, "options": options}
