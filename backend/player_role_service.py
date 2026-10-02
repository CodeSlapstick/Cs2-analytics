"""Cached inference for the research player-role artifact. Never trains in a request."""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

MODEL_PATH = Path(__file__).resolve().parent.parent / "output" / "player_role.json"


def compatibility_reason(model: dict[str, Any] | None, map_name: str | None, source: str) -> str | None:
    if model is None:
        return "model_unavailable"
    if source != "upload":
        return "uploaded_matches_only"
    if model.get("map") != map_name:
        return "unsupported_map"
    return None


@lru_cache(maxsize=4)
def load_role_model(path: str = str(MODEL_PATH)) -> dict[str, Any] | None:
    try:
        model = json.loads(Path(path).read_text(encoding="utf-8"))
        if model.get("unit") != "player-match-side" or not isinstance(model.get("models"), dict):
            return None
        return model
    except (OSError, ValueError, TypeError):
        return None


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def assign_profile(profile: dict[str, Any], side: str, model: dict[str, Any]) -> dict[str, Any]:
    spec = model["models"][side]
    features = spec["features"]
    prep = spec["preprocess"]
    values: dict[str, float] = {}
    z: dict[str, float] = {}
    for feature in features:
        value = _finite(profile.get(feature))
        if value is None:
            value = float(prep["median"][feature])
        values[feature] = value
        scale = float(prep["scale"][feature]) or 1.0
        z[feature] = (value - float(prep["mean"][feature])) / scale

    ranked: list[tuple[float, dict[str, Any]]] = []
    for cluster in spec["clusters"]:
        distance = math.sqrt(sum((z[f] - float(cluster["center_z"][f])) ** 2 for f in features))
        ranked.append((distance, cluster))
    ranked.sort(key=lambda item: (item[0], int(item[1]["id"])))
    distance, cluster = ranked[0]
    margin = ranked[1][0] - distance if len(ranked) > 1 else 0.0
    role = cluster.get("role") if cluster.get("role_name_status") == "supported" else "Hybrid / Unresolved"
    signals = sorted(features, key=lambda f: (-abs(z[f]), f))[:3]
    return {
        "role": role or "Hybrid / Unresolved",
        "cluster": cluster["id"],
        "distance": round(distance, 4),
        "margin": round(margin, 4),
        "signals": [{"feature": f, "direction": "higher" if z[f] >= 0 else "lower",
                     "z": round(z[f], 3), "value": round(values[f], 4)} for f in signals],
    }


def build_match_profiles(round_rows: Iterable[Any], kill_rows: Iterable[Any], tickrate: float) -> list[dict[str, Any]]:
    """Build the same kill-event proxy features used by research/player_role.py."""
    stats: dict[tuple[int, str], dict[str, Any]] = {}
    side_at: dict[tuple[int, int], str] = {}
    for raw in round_rows:
        row = dict(raw)
        key = (int(row["steam_id"]), row["side"])
        side_at[(int(row["round_num"]), int(row["steam_id"]))] = row["side"]
        s = stats.setdefault(key, {"steamid": str(row["steam_id"]), "name": row["name"], "side": row["side"],
                                   "rounds": 0, "assists": 0, "opening_attempts": 0, "opening_kills": 0,
                                   "trade_kills": 0, "traded_deaths": 0, "flash_assists": 0,
                                   "early": 0, "postplant": 0, "site": 0, "kill_time_sum": 0.0,
                                   "kills": 0, "places": Counter()})
        s["rounds"] += 1
        s["assists"] += int(row.get("assists") or 0)
        s["opening_attempts"] += int(bool(row.get("opening_kill"))) + int(bool(row.get("opening_death")))
        s["opening_kills"] += int(bool(row.get("opening_kill")))
        s["trade_kills"] += int(row.get("trade_kills") or 0)
        s["traded_deaths"] += int(bool(row.get("was_traded")))

    rate = max(float(tickrate or 128), 1.0)
    for raw in kill_rows:
        row = dict(raw)
        attacker, victim = row.get("attacker_id"), row.get("victim_id")
        a_side, v_side = row.get("attacker_side"), row.get("victim_side")
        start, tick = row.get("start_tick"), row.get("tick")
        if attacker is None or a_side not in ("ct", "t") or v_side not in ("ct", "t") or a_side == v_side:
            continue
        if start is None or tick is None or tick < start:
            continue
        akey, vkey = (int(attacker), a_side), (int(victim), v_side)
        if akey not in stats or vkey not in stats:
            continue
        elapsed = (tick - start) / rate
        stats[akey]["kills"] += 1
        stats[akey]["kill_time_sum"] += elapsed
        if elapsed <= 25:
            stats[akey]["early"] += 1
            stats[vkey]["early"] += 1
        if row.get("bomb_plant_tick") is not None and tick >= row["bomb_plant_tick"]:
            stats[akey]["postplant"] += 1
        site = str(row.get("attacker_place") or "").startswith("Bombsite") or str(row.get("victim_place") or "").startswith("Bombsite")
        if site:
            stats[akey]["site"] += 1
            stats[vkey]["site"] += 1
        for key, place in ((akey, row.get("attacker_place")), (vkey, row.get("victim_place"))):
            if place:
                stats[key]["places"][str(place)] += 1
        assister = row.get("assister_id")
        if assister is not None and row.get("assisted_flash"):
            as_side = side_at.get((int(row["round_num"]), int(assister)))
            if as_side and (int(assister), as_side) in stats:
                stats[(int(assister), as_side)]["flash_assists"] += 1

    profiles = []
    for s in stats.values():
        rounds = max(s["rounds"], 1)
        places: Counter = s.pop("places")
        events = sum(places.values())
        profiles.append({**s,
            "assists_per_round": s["assists"] / rounds,
            "flash_assists_per_round": s["flash_assists"] / rounds,
            "opening_attempt_rate": s["opening_attempts"] / rounds,
            "opening_kill_rate": s["opening_kills"] / rounds,
            "early_engagement_rate": s["early"] / rounds,
            "trade_kills_per_round": s["trade_kills"] / rounds,
            "traded_death_rate": s["traded_deaths"] / rounds,
            "postplant_kills_per_round": s["postplant"] / rounds,
            "site_engagement_rate": s["site"] / rounds,
            "avg_kill_time": s["kill_time_sum"] / s["kills"] if s["kills"] else None,
            "place_diversity": len(places),
            "place_concentration": max(places.values()) / events if events else 0.0,
        })
    return sorted(profiles, key=lambda p: (p["name"].casefold(), p["side"]))


def infer_match(profiles: list[dict[str, Any]], model: dict[str, Any], players: set[str] | None = None) -> list[dict[str, Any]]:
    minimum = int(model.get("min_rounds_per_profile", 5))
    out = []
    for profile in profiles:
        if players is not None and profile["steamid"] not in players:
            continue
        base = {"steamid": profile["steamid"], "name": profile["name"], "side": profile["side"], "rounds": profile["rounds"]}
        if profile["rounds"] < minimum:
            out.append({**base, "available": False, "reason": "insufficient_rounds", "minimum_rounds": minimum})
        else:
            out.append({**base, "available": True, **assign_profile(profile, profile["side"], model)})
    return out
