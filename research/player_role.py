# -*- coding: utf-8 -*-
"""Train separate unsupervised player-role models for the T and CT sides.

The unit of analysis is one player in one match on one side.  Only reference
matches are used.  KMeans discovers behavioural clusters independently for
each side; role names are interpretations of cluster centroids, not labels
used during fitting and not claims about a player's permanent role.

Outputs
    output/player_role.json          deployable centroids and model metadata
    output/player_role_profiles.csv  assignments for the reference profiles

Run from the repository root:
    python research/player_role.py
    python research/player_role.py --map de_mirage --min-rounds 6
"""
from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
ALL_KILLS_CSV = ROOT / "data" / "all_kills.csv"
sys.path.insert(0, str(ROOT))

from backend.db import DATABASE_URL  # noqa: E402

SEED = 42
N_CLUSTERS = 5
CSV_N_CLUSTERS = 6
N_BOOTSTRAPS = 40
MIN_ROUNDS = 5

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


# Every query contains the hard boundary m.source = 'reference'.  Uploaded
# matches must never influence this model.
FACTS_SQL = """
SELECT m.demo_file, m.map_name, r.match_id, r.id AS round_id, r.round_num,
       r.start_tick, r.bomb_plant_tick, r.bomb_plant_x, r.bomb_plant_y,
       m.tickrate, pr.steam_id, p.name, pr.side, pr.survived, pr.kills,
       pr.deaths, pr.assists, pr.damage, pr.opening_kill, pr.opening_death,
       pr.trade_kills, pr.was_traded
FROM player_rounds pr
JOIN rounds r ON r.id = pr.round_id
JOIN matches m ON m.id = r.match_id
JOIN players p ON p.steam_id = pr.steam_id
WHERE m.source = 'reference' AND m.status = 'done'
  AND ($1::text IS NULL OR m.map_name = $1)
"""

POSITIONS_SQL = """
SELECT pp.match_id, pp.round_num, pp.tick, pp.steam_id, pp.side,
       pp.x, pp.y, pp.place
FROM player_positions pp
JOIN matches m ON m.id = pp.match_id
WHERE m.source = 'reference' AND m.status = 'done'
  AND ($1::text IS NULL OR m.map_name = $1)
  AND pp.health > 0
"""

GRENADES_SQL = """
SELECT g.round_id, g.thrower_id AS steam_id, g.type, COUNT(*) AS n
FROM grenades g
JOIN rounds r ON r.id = g.round_id
JOIN matches m ON m.id = r.match_id
WHERE m.source = 'reference' AND m.status = 'done'
  AND ($1::text IS NULL OR m.map_name = $1)
  AND g.thrower_id IS NOT NULL
GROUP BY g.round_id, g.thrower_id, g.type
"""

KILLS_SQL = """
SELECT r.match_id, r.round_num, r.start_tick, r.bomb_plant_tick, m.tickrate,
       k.tick, k.attacker_id, k.victim_id, k.attacker_side, k.victim_side
FROM kills k
JOIN rounds r ON r.id = k.round_id
JOIN matches m ON m.id = r.match_id
WHERE m.source = 'reference' AND m.status = 'done'
  AND ($1::text IS NULL OR m.map_name = $1)
  AND k.attacker_id IS NOT NULL AND k.attacker_side <> k.victim_side
"""


T_FEATURES = [
    "opening_attempt_rate", "opening_kill_rate", "opening_death_rate",
    "early_engagement_rate", "trade_kills_per_round", "traded_death_rate",
    "assists_per_round", "utility_per_round", "flash_per_round",
    "smoke_per_round", "damage_per_round", "survival_rate",
    "team_separation", "path_length", "place_diversity",
    "plant_proxy_rate", "postplant_kills_per_plant", "postplant_movement_per_plant",
]

CT_FEATURES = [
    "opening_attempt_rate", "opening_kill_rate", "opening_death_rate",
    "early_engagement_rate", "trade_kills_per_round", "assists_per_round",
    "utility_per_round", "flash_per_round", "smoke_per_round",
    "damage_per_round", "survival_rate", "team_separation", "path_length",
    "early_displacement", "place_diversity", "alive_at_plant_rate",
    "postplant_kills_per_plant", "postplant_movement_per_plant",
]

ROLE_ORDER = {
    "t": ["Entry", "Support", "Lurker", "Trader", "Bomb carrier / Site executor"],
    "ct": ["Site Anchor", "Rotator", "Aggressive Defender", "Utility Support", "Retake Player"],
}

# Positive values mean "characteristically high" and negative values mean
# "characteristically low".  These weights only name discovered centroids;
# they never alter cluster membership.
ROLE_SIGNATURES: dict[str, dict[str, dict[str, float]]] = {
    "t": {
        "Entry": {"opening_attempt_rate": 2, "early_engagement_rate": 1.5, "opening_kill_rate": 1},
        "Support": {"utility_per_round": 1.5, "flash_per_round": 1.5, "smoke_per_round": 1, "assists_per_round": 1},
        "Lurker": {"team_separation": 2, "place_diversity": 0.5, "plant_proxy_rate": -1, "survival_rate": 0.5},
        "Trader": {"trade_kills_per_round": 2, "traded_death_rate": 0.5, "damage_per_round": 0.5},
        "Bomb carrier / Site executor": {"plant_proxy_rate": 2.5, "postplant_movement_per_plant": 0.5, "smoke_per_round": 0.5},
    },
    "ct": {
        "Site Anchor": {"path_length": -1.5, "early_displacement": -1, "place_diversity": -1, "survival_rate": 0.5},
        "Rotator": {"path_length": 1.5, "early_displacement": 1, "place_diversity": 1},
        "Aggressive Defender": {"opening_attempt_rate": 2, "early_engagement_rate": 1.5, "opening_kill_rate": 0.75},
        "Utility Support": {"utility_per_round": 1.5, "flash_per_round": 1.5, "smoke_per_round": 1, "assists_per_round": 1},
        "Retake Player": {"alive_at_plant_rate": 1.5, "postplant_kills_per_plant": 1.5, "postplant_movement_per_plant": 1},
    },
}

# all_kills.csv ใช้หกกลุ่ม: ห้าบทบาทที่ต้องการและหนึ่ง Hybrid / Unresolved
# เพื่อไม่บังคับชื่อเมื่อ kill events ยังไม่แยกบทบาทนั้นชัดเจน
# ไฟล์มีเฉพาะเหตุการณ์ kill จึงใช้ชุดฟีเจอร์ที่พิสูจน์ได้จากไฟล์นี้เท่านั้น
# utility/movement/planter ไม่ถูกเติมค่าปลอม; assist, flash, site และ post-plant เป็น proxy ที่ระบุใน output
CSV_T_FEATURES = [
    "assists_per_round", "flash_assists_per_round", "opening_attempt_rate", "opening_kill_rate",
    "early_engagement_rate",
    "trade_kills_per_round", "traded_death_rate", "postplant_kills_per_round",
    "site_engagement_rate", "avg_kill_time", "place_diversity",
    "place_concentration",
]
CSV_CT_FEATURES = [
    "assists_per_round", "flash_assists_per_round", "opening_attempt_rate",
    "early_engagement_rate", "trade_kills_per_round", "traded_death_rate",
    "postplant_kills_per_round", "site_engagement_rate", "avg_kill_time",
    "place_diversity", "place_concentration",
]

CSV_ROLE_SIGNATURES: dict[str, dict[str, dict[str, float]]] = {
    "t": {
        "Entry": {"opening_attempt_rate": 2, "early_engagement_rate": 1.5, "opening_kill_rate": 1, "avg_kill_time": -0.5},
        "Support": {"assists_per_round": 1.5, "flash_assists_per_round": 2, "kills_per_round": -0.25},
        "Lurker": {"avg_kill_time": 1.5, "survival_rate": 0.75, "site_engagement_rate": -0.75, "opening_attempt_rate": -0.5},
        "Trader": {"trade_kills_per_round": 2, "traded_death_rate": 0.5, "kills_per_round": 0.5},
        "Bomb carrier / Site executor": {"site_engagement_rate": 1.5, "postplant_kills_per_round": 1.5, "place_concentration": 0.5},
    },
    "ct": {
        "Site Anchor": {"place_concentration": 1.5, "site_engagement_rate": 1, "place_diversity": -1},
        "Rotator": {"place_diversity": 1.5, "place_concentration": -1, "site_engagement_rate": 0.5},
        "Aggressive Defender": {"opening_attempt_rate": 2, "early_engagement_rate": 1.5, "opening_kill_rate": 0.75},
        "Utility Support": {"assists_per_round": 1.5, "flash_assists_per_round": 2, "kills_per_round": -0.25},
        "Retake Player": {"postplant_kills_per_round": 2, "avg_kill_time": 0.75, "survival_rate": 0.5},
    },
}


async def load_frames(database_url: str, map_name: str | None) -> dict[str, pd.DataFrame]:
    """Load all training tables from the reference partition only."""
    import asyncpg

    conn = await asyncpg.connect(database_url)
    try:
        result: dict[str, pd.DataFrame] = {}
        for name, query in (
            ("facts", FACTS_SQL), ("positions", POSITIONS_SQL),
            ("grenades", GRENADES_SQL), ("kills", KILLS_SQL),
        ):
            result[name] = pd.DataFrame([dict(row) for row in await conn.fetch(query, map_name)])
        return result
    finally:
        await conn.close()


def _empty_position_features() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "match_id", "round_num", "steam_id", "team_separation", "path_length",
        "early_displacement", "place_diversity", "alive_at_plant",
        "postplant_movement", "plant_proxy",
    ])


def position_features(positions: pd.DataFrame, facts: pd.DataFrame) -> pd.DataFrame:
    """Summarise movement without relying on map-specific hand-labelled zones."""
    if positions.empty:
        return _empty_position_features()

    round_meta = facts[[
        "match_id", "round_num", "start_tick", "bomb_plant_tick",
        "bomb_plant_x", "bomb_plant_y", "tickrate",
    ]].drop_duplicates(["match_id", "round_num"])
    p = positions.merge(round_meta, on=["match_id", "round_num"], how="inner")
    p["tickrate"] = p["tickrate"].fillna(128).clip(lower=1)
    p["time_s"] = (p["tick"] - p["start_tick"]) / p["tickrate"]
    p = p.sort_values(["match_id", "round_num", "steam_id", "tick"])

    keys = ["match_id", "round_num", "steam_id"]
    g = p.groupby(keys, sort=False)
    p["dx"] = g["x"].diff()
    p["dy"] = g["y"].diff()
    p["dt"] = g["tick"].diff() / p["tickrate"]
    p["step"] = np.hypot(p["dx"], p["dy"]).where(p["dt"].between(0, 2.5), 0.0)
    p["postplant"] = p["bomb_plant_tick"].notna() & (p["tick"] >= p["bomb_plant_tick"])

    team_keys = ["match_id", "round_num", "tick", "side"]
    centroid = p.groupby(team_keys)[["x", "y"]].transform("mean")
    p["team_distance"] = np.hypot(p["x"] - centroid["x"], p["y"] - centroid["y"])

    base = g.agg(
        team_separation=("team_distance", "mean"),
        path_length=("step", "sum"),
        place_diversity=("place", "nunique"),
        alive_at_plant=("postplant", "max"),
    ).reset_index()
    post = (p[p["postplant"]].groupby(keys)["step"].sum()
            .rename("postplant_movement").reset_index())

    early = p[p["time_s"].between(0, 30)].copy()
    if early.empty:
        displacement = pd.DataFrame(columns=keys + ["early_displacement"])
    else:
        first = early.groupby(keys, sort=False).first()[["x", "y"]]
        last = early.groupby(keys, sort=False).last()[["x", "y"]]
        displacement = np.hypot(last["x"] - first["x"], last["y"] - first["y"])
        displacement = displacement.rename("early_displacement").reset_index()

    # The schema has the plant location but not the planter id.  The closest
    # living T within two seconds of the plant is an explicit proxy, not a fact.
    near_plant = p[
        (p["side"] == "t") & p["bomb_plant_tick"].notna()
        & ((p["tick"] - p["bomb_plant_tick"]).abs() <= 2 * p["tickrate"])
        & p["bomb_plant_x"].notna() & p["bomb_plant_y"].notna()
    ].copy()
    if near_plant.empty:
        planter = pd.DataFrame(columns=keys + ["plant_proxy"])
    else:
        near_plant["plant_distance"] = np.hypot(
            near_plant["x"] - near_plant["bomb_plant_x"],
            near_plant["y"] - near_plant["bomb_plant_y"],
        )
        nearest_sample = near_plant.loc[near_plant.groupby(keys)["plant_distance"].idxmin()]
        winners = nearest_sample.loc[
            nearest_sample.groupby(["match_id", "round_num"])["plant_distance"].idxmin(), keys
        ].copy()
        winners["plant_proxy"] = 1.0
        planter = winners

    out = base.merge(post, on=keys, how="left").merge(displacement, on=keys, how="left")
    out = out.merge(planter, on=keys, how="left")
    for col in ("postplant_movement", "early_displacement", "plant_proxy"):
        out[col] = out[col].fillna(0.0)
    return out


def combat_features(kills: pd.DataFrame) -> pd.DataFrame:
    """Count early engagements and post-plant kills per player-round."""
    cols = ["match_id", "round_num", "steam_id", "early_engagement", "postplant_kills"]
    if kills.empty:
        return pd.DataFrame(columns=cols)
    k = kills.copy()
    k["tickrate"] = k["tickrate"].fillna(128).clip(lower=1)
    k["time_s"] = (k["tick"] - k["start_tick"]) / k["tickrate"]
    k["is_early"] = k["time_s"].between(0, 25)
    k["is_postplant"] = k["bomb_plant_tick"].notna() & (k["tick"] >= k["bomb_plant_tick"])

    attack = (k.groupby(["match_id", "round_num", "attacker_id"])
              .agg(early_attack=("is_early", "max"), postplant_kills=("is_postplant", "sum"))
              .reset_index().rename(columns={"attacker_id": "steam_id"}))
    victim = (k.groupby(["match_id", "round_num", "victim_id"])["is_early"].max()
              .rename("early_death").reset_index().rename(columns={"victim_id": "steam_id"}))
    out = attack.merge(victim, on=["match_id", "round_num", "steam_id"], how="outer")
    out["early_engagement"] = out[["early_attack", "early_death"]].fillna(False).max(axis=1).astype(float)
    out["postplant_kills"] = out["postplant_kills"].fillna(0.0)
    return out[cols]


def build_profiles(frames: dict[str, pd.DataFrame], min_rounds: int = MIN_ROUNDS) -> pd.DataFrame:
    """Create player-match-side profiles used as independent clustering rows."""
    facts = frames["facts"].copy()
    if facts.empty:
        return pd.DataFrame()

    keys = ["match_id", "round_num", "steam_id"]
    grenade = frames["grenades"].copy()
    if grenade.empty:
        util = pd.DataFrame(columns=["round_id", "steam_id", "utility", "flash", "smoke"])
    else:
        grenade["kind"] = grenade["type"].str.lower()
        util = grenade.pivot_table(
            index=["round_id", "steam_id"], columns="kind", values="n", aggfunc="sum", fill_value=0,
        ).reset_index()
        util["utility"] = util.drop(columns=["round_id", "steam_id"]).sum(axis=1)
        for col in ("flash", "smoke"):
            if col not in util:
                util[col] = 0

    facts = facts.merge(util[["round_id", "steam_id", "utility", "flash", "smoke"]],
                        on=["round_id", "steam_id"], how="left")
    facts = facts.merge(position_features(frames["positions"], facts), on=keys, how="left")
    facts = facts.merge(combat_features(frames["kills"]), on=keys, how="left")
    numeric_fill = [
        "utility", "flash", "smoke", "team_separation", "path_length", "early_displacement",
        "place_diversity", "alive_at_plant", "postplant_movement", "plant_proxy",
        "early_engagement", "postplant_kills",
    ]
    for col in numeric_fill:
        facts[col] = pd.to_numeric(facts[col], errors="coerce").fillna(0.0)
    facts["plant_round"] = facts["bomb_plant_tick"].notna().astype(float)
    facts["opening_attempt"] = facts["opening_kill"].astype(float) + facts["opening_death"].astype(float)

    profile_keys = ["match_id", "demo_file", "map_name", "steam_id", "name", "side"]
    sums = {
        "round_num": "count", "opening_attempt": "sum", "opening_kill": "sum", "opening_death": "sum",
        "early_engagement": "sum", "trade_kills": "sum", "was_traded": "sum", "assists": "sum",
        "utility": "sum", "flash": "sum", "smoke": "sum", "damage": "sum", "survived": "sum",
        "plant_round": "sum", "plant_proxy": "sum", "postplant_kills": "sum",
        "alive_at_plant": "sum", "postplant_movement": "sum",
        "team_separation": "mean", "path_length": "mean",
        "early_displacement": "mean", "place_diversity": "mean",
    }
    out = facts.groupby(profile_keys, dropna=False).agg(sums).reset_index().rename(columns={"round_num": "rounds"})
    r = out["rounds"].clip(lower=1)
    plants = out["plant_round"].clip(lower=1)
    rates = {
        "opening_attempt_rate": ("opening_attempt", r), "opening_kill_rate": ("opening_kill", r),
        "opening_death_rate": ("opening_death", r), "early_engagement_rate": ("early_engagement", r),
        "trade_kills_per_round": ("trade_kills", r), "traded_death_rate": ("was_traded", r),
        "assists_per_round": ("assists", r), "utility_per_round": ("utility", r),
        "flash_per_round": ("flash", r), "smoke_per_round": ("smoke", r),
        "damage_per_round": ("damage", r), "survival_rate": ("survived", r),
        "plant_proxy_rate": ("plant_proxy", plants),
        "alive_at_plant_rate": ("alive_at_plant", plants),
        "postplant_kills_per_plant": ("postplant_kills", plants),
        "postplant_movement_per_plant": ("postplant_movement", plants),
    }
    for target, (source, denom) in rates.items():
        out[target] = out[source] / denom
    return out[out["rounds"] >= min_rounds].reset_index(drop=True)


def load_kills_csv(path: Path, map_name: str | None = None) -> pd.DataFrame:
    """อ่าน all_kills ที่สร้างจาก demos/reference และตรวจ schema ก่อนเทรน"""
    if not path.is_file():
        raise ValueError(f"ไม่พบไฟล์ {path}")
    kills = pd.read_csv(path, low_memory=False)
    required = {
        "demo_file", "map_name", "round_num", "attacker_steamid", "victim_steamid",
        "assister_steamid", "attacker_side", "victim_side", "assister_side",
        "attacker_name", "victim_name", "assister_name", "attacker_team_clan",
        "victim_team_clan", "assister_team_clan", "attacker_place", "victim_place",
        "weapon", "round_time_seconds", "is_live_round_kill", "is_opening_kill",
        "is_opening_death", "is_early_engagement", "is_postplant_kill",
        "is_site_engagement", "is_flash_assisted_kill", "trade_kill_count",
        "victim_was_traded",
    }
    missing = sorted(required - set(kills.columns))
    if missing:
        raise ValueError(
            "all_kills.csv ยังไม่ใช่ schema role-ready; ขาด " + ", ".join(missing)
            + " — รัน python research/demoparser.py ก่อน"
        )
    if map_name:
        kills = kills[kills["map_name"] == map_name].copy()
    if kills.empty:
        raise ValueError(f"all_kills.csv ไม่มีข้อมูลสำหรับ {map_name or 'ทุกแมพ'}")
    return kills


def _mode(series: pd.Series) -> Any:
    values = series.dropna()
    if values.empty:
        return None
    modes = values.mode()
    return modes.iloc[0] if not modes.empty else values.iloc[0]


def _csv_participants(kills: pd.DataFrame) -> pd.DataFrame:
    """แปลง attacker/victim/assister เป็นตารางคนรูปเดียวกัน"""
    parts = []
    for who in ("attacker", "victim", "assister"):
        part = kills[[
            "demo_file", "map_name", "round_num", f"{who}_steamid", f"{who}_name",
            f"{who}_side", f"{who}_team_clan",
        ]].rename(columns={
            f"{who}_steamid": "steam_id", f"{who}_name": "name",
            f"{who}_side": "side", f"{who}_team_clan": "team",
        })
        parts.append(part.dropna(subset=["steam_id", "side", "team"]))
    out = pd.concat(parts, ignore_index=True)
    out["steam_id"] = pd.to_numeric(out["steam_id"], errors="coerce")
    out = out.dropna(subset=["steam_id"])
    out["steam_id"] = out["steam_id"].astype("int64")
    return out[out["side"].isin(["t", "ct"])]


def build_profiles_from_kills(kills: pd.DataFrame, min_rounds: int = MIN_ROUNDS) -> pd.DataFrame:
    """สร้าง player-match-side profiles จาก all_kills.csv โดยไม่ใช้ฐานข้อมูล

    roster ของแมตช์สร้างจาก team_clan ที่ assign_teams กำหนดไว้แล้ว ทำให้รอบที่ผู้เล่น
    ไม่ได้ kill/death/assist ยังถูกนับใน denominator และไม่ทำให้คนเงียบดู active เกินจริง
    """
    participants = _csv_participants(kills)
    if participants.empty:
        return pd.DataFrame()

    conflict = (participants.groupby(["demo_file", "round_num", "team"])["side"]
                .nunique().max())
    if conflict > 1:
        raise ValueError("พบ team_clan เดียวอยู่ทั้ง T และ CT ในรอบเดียวกัน")

    roster = (participants.groupby(["demo_file", "map_name", "steam_id"], as_index=False)
              .agg(name=("name", _mode), team=("team", _mode)))
    team_rounds = (participants[["demo_file", "map_name", "round_num", "team", "side"]]
                   .drop_duplicates())
    base = roster.merge(team_rounds, on=["demo_file", "map_name", "team"], how="inner")
    base["match_id"] = base["demo_file"]
    keys = ["demo_file", "round_num", "steam_id"]

    live = kills[kills["is_live_round_kill"].fillna(False).astype(bool)].copy()
    live["round_time_seconds"] = pd.to_numeric(live["round_time_seconds"], errors="coerce")
    live["trade_kill_count"] = pd.to_numeric(live["trade_kill_count"], errors="coerce").fillna(0)
    live["is_awp"] = live["weapon"].fillna("").str.lower().eq("awp")

    attack = (live.groupby(["demo_file", "round_num", "attacker_steamid"], as_index=False)
              .agg(
                  kills=("is_live_round_kill", "sum"),
                  opening_kills=("is_opening_kill", "sum"),
                  early_attacks=("is_early_engagement", "sum"),
                  postplant_kills=("is_postplant_kill", "sum"),
                  site_attacks=("is_site_engagement", "sum"),
                  trade_kills=("trade_kill_count", "sum"),
                  kill_time_sum=("round_time_seconds", "sum"),
                  awp_kills=("is_awp", "sum"),
              ).rename(columns={"attacker_steamid": "steam_id"}))
    victim = (live.groupby(["demo_file", "round_num", "victim_steamid"], as_index=False)
              .agg(
                  deaths=("is_live_round_kill", "sum"),
                  opening_deaths=("is_opening_death", "sum"),
                  early_deaths=("is_early_engagement", "sum"),
                  postplant_deaths=("is_postplant_kill", "sum"),
                  site_deaths=("is_site_engagement", "sum"),
                  traded_deaths=("victim_was_traded", "sum"),
              ).rename(columns={"victim_steamid": "steam_id"}))
    assisted = live[live["assister_steamid"].notna()].copy()
    assist = (assisted.groupby(["demo_file", "round_num", "assister_steamid"], as_index=False)
              .agg(assists=("is_live_round_kill", "sum"), flash_assists=("is_flash_assisted_kill", "sum"))
              .rename(columns={"assister_steamid": "steam_id"}))

    for frame in (attack, victim, assist):
        if not frame.empty:
            frame["steam_id"] = pd.to_numeric(frame["steam_id"], errors="coerce").astype("int64")
        base = base.merge(frame, on=keys, how="left")

    count_columns = [
        "kills", "opening_kills", "early_attacks", "postplant_kills", "site_attacks",
        "trade_kills", "kill_time_sum", "awp_kills", "deaths", "opening_deaths",
        "early_deaths", "postplant_deaths", "site_deaths", "traded_deaths", "assists",
        "flash_assists",
    ]
    for column in count_columns:
        base[column] = pd.to_numeric(base[column], errors="coerce").fillna(0.0)

    # Callout diversity/concentration is a kill-event proxy for anchor/rotation behaviour.
    attack_places = live[["demo_file", "attacker_steamid", "attacker_side", "attacker_place"]].rename(
        columns={"attacker_steamid": "steam_id", "attacker_side": "side", "attacker_place": "place"})
    victim_places = live[["demo_file", "victim_steamid", "victim_side", "victim_place"]].rename(
        columns={"victim_steamid": "steam_id", "victim_side": "side", "victim_place": "place"})
    places = pd.concat([attack_places, victim_places], ignore_index=True).dropna(subset=["steam_id", "place"])
    places["steam_id"] = pd.to_numeric(places["steam_id"], errors="coerce").astype("int64")
    place_counts = (places.groupby(["demo_file", "steam_id", "side", "place"]).size()
                    .rename("events").reset_index())
    place_profile = (place_counts.groupby(["demo_file", "steam_id", "side"])
                     .agg(place_diversity=("place", "nunique"), place_events=("events", "sum"),
                          top_place_events=("events", "max")).reset_index())
    place_profile["place_concentration"] = place_profile["top_place_events"] / place_profile["place_events"]

    profile_keys = ["match_id", "demo_file", "map_name", "steam_id", "name", "team", "side"]
    sums = {column: "sum" for column in count_columns}
    sums["round_num"] = "count"
    out = base.groupby(profile_keys, as_index=False).agg(sums).rename(columns={"round_num": "rounds"})
    out = out.merge(place_profile[["demo_file", "steam_id", "side", "place_diversity", "place_concentration"]],
                    on=["demo_file", "steam_id", "side"], how="left")
    out[["place_diversity", "place_concentration"]] = out[["place_diversity", "place_concentration"]].fillna(0.0)

    rounds = out["rounds"].clip(lower=1)
    kills_n = out["kills"].clip(lower=1)
    out["kills_per_round"] = out["kills"] / rounds
    out["deaths_per_round"] = out["deaths"] / rounds
    out["assists_per_round"] = out["assists"] / rounds
    out["flash_assists_per_round"] = out["flash_assists"] / rounds
    out["opening_kill_rate"] = out["opening_kills"] / rounds
    out["opening_death_rate"] = out["opening_deaths"] / rounds
    out["opening_attempt_rate"] = (out["opening_kills"] + out["opening_deaths"]) / rounds
    out["early_engagement_rate"] = (out["early_attacks"] + out["early_deaths"]) / rounds
    out["trade_kills_per_round"] = out["trade_kills"] / rounds
    out["traded_death_rate"] = out["traded_deaths"] / rounds
    out["postplant_kills_per_round"] = out["postplant_kills"] / rounds
    out["site_engagement_rate"] = (out["site_attacks"] + out["site_deaths"]) / rounds
    out["avg_kill_time"] = out["kill_time_sum"] / kills_n
    out.loc[out["kills"] == 0, "avg_kill_time"] = np.nan
    out["survival_rate"] = (1 - out["deaths_per_round"]).clip(0, 1)
    out["awp_kill_share"] = out["awp_kills"] / kills_n
    out.loc[out["kills"] == 0, "awp_kill_share"] = 0.0
    return out[out["rounds"] >= min_rounds].reset_index(drop=True)


def assign_role_names(centers_z: np.ndarray, side: str, features: list[str],
                      signatures_by_side: dict[str, dict[str, dict[str, float]]] | None = None,
                      ) -> tuple[list[str], np.ndarray]:
    """Find the globally best one-to-one mapping from centroids to role names."""
    roles = ROLE_ORDER[side]
    signatures = (signatures_by_side or ROLE_SIGNATURES)[side]
    score = np.zeros((len(centers_z), len(roles)))
    for ci, center in enumerate(centers_z):
        for ri, role in enumerate(roles):
            weights = np.array([signatures[role].get(feature, 0.0) for feature in features])
            norm = np.linalg.norm(weights)
            score[ci, ri] = float(center @ weights / norm) if norm else 0.0

    # เลือก centroid คนละตัวให้แต่ละ role แบบ global optimum; centroid ที่เหลือไม่ถูกฝืนตั้งชื่อ
    best_perm: tuple[int, ...] | None = None
    best_total = -math.inf
    for perm in itertools.permutations(range(len(centers_z)), len(roles)):
        total = sum(score[cluster_idx, role_idx] for role_idx, cluster_idx in enumerate(perm))
        if total > best_total:
            best_total, best_perm = total, perm
    assert best_perm is not None
    names = ["Hybrid / Unresolved"] * len(centers_z)
    for role_idx, cluster_idx in enumerate(best_perm):
        names[cluster_idx] = roles[role_idx]
    return names, score


def bootstrap_stability(x: np.ndarray, labels: np.ndarray, seed: int, n_bootstraps: int,
                        n_clusters: int = N_CLUSTERS) -> float:
    """Mean ARI between full-fit labels and bootstrap model predictions."""
    rng = np.random.default_rng(seed)
    scores = []
    for i in range(n_bootstraps):
        sample = rng.integers(0, len(x), size=len(x))
        if len(np.unique(sample)) < n_clusters:
            continue
        model = KMeans(n_clusters=n_clusters, n_init=20, random_state=seed + i + 1).fit(x[sample])
        scores.append(adjusted_rand_score(labels, model.predict(x)))
    return float(np.mean(scores)) if scores else 0.0


def fit_side(profiles: pd.DataFrame, side: str, seed: int = SEED,
             n_bootstraps: int = N_BOOTSTRAPS, features: list[str] | None = None,
             signatures_by_side: dict[str, dict[str, dict[str, float]]] | None = None,
             n_clusters: int = N_CLUSTERS,
             ) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fit and describe one side-specific model."""
    features = features or (T_FEATURES if side == "t" else CT_FEATURES)
    rows = profiles[profiles["side"] == side].copy()
    if len(rows) < n_clusters * 3:
        raise ValueError(f"ฝั่ง {side.upper()} มีเพียง {len(rows)} profiles — ต้องมีอย่างน้อย {n_clusters * 3}")
    x_raw = rows[features].replace([np.inf, -np.inf], np.nan)
    medians = x_raw.median().fillna(0.0)
    x_raw = x_raw.fillna(medians)
    scaler = StandardScaler().fit(x_raw)
    x = scaler.transform(x_raw)
    model = KMeans(n_clusters=n_clusters, n_init=50, random_state=seed).fit(x)
    role_names, role_scores = assign_role_names(model.cluster_centers_, side, features, signatures_by_side)

    rows["cluster"] = model.labels_ + 1
    rows["role"] = [role_names[label] for label in model.labels_]
    distance = model.transform(x)
    rows["role_distance"] = distance[np.arange(len(rows)), model.labels_]

    clusters = []
    for cluster_id, role in enumerate(role_names):
        member = rows[rows["cluster"] == cluster_id + 1]
        top = sorted(zip(features, model.cluster_centers_[cluster_id], strict=True), key=lambda item: -abs(item[1]))[:5]
        role_score = None if role == "Hybrid / Unresolved" else float(
            role_scores[cluster_id, ROLE_ORDER[side].index(role)])
        clusters.append({
            "id": cluster_id + 1,
            "role": role,
            "profiles": int(len(member)),
            "role_name_score": round(role_score, 4) if role_score is not None else None,
            "role_name_status": "unassigned" if role_score is None else ("supported" if role_score >= 0.25 else "weak"),
            "top_signals": [{"feature": feature, "z": round(float(value), 4)} for feature, value in top],
            "center_z": {feature: round(float(value), 6) for feature, value in zip(features, model.cluster_centers_[cluster_id], strict=True)},
            "center_raw": {feature: round(float(value), 6) for feature, value in zip(features, scaler.inverse_transform(model.cluster_centers_[[cluster_id]])[0], strict=True)},
        })

    payload = {
        "side": side,
        "roles": ROLE_ORDER[side],
        "features": features,
        "profiles": int(len(rows)),
        "players": int(rows["steam_id"].nunique()),
        "matches": int(rows["match_id"].nunique()),
        "metrics": {
            "silhouette": round(float(silhouette_score(x, model.labels_)), 6),
            "bootstrap_ari": round(bootstrap_stability(x, model.labels_, seed, n_bootstraps, n_clusters), 6),
            "n_bootstraps": n_bootstraps,
            "n_clusters": n_clusters,
        },
        "preprocess": {
            "median": {f: round(float(medians[f]), 6) for f in features},
            "mean": {f: round(float(v), 6) for f, v in zip(features, scaler.mean_, strict=True)},
            "scale": {f: round(float(v), 6) for f, v in zip(features, scaler.scale_, strict=True)},
        },
        "clusters": clusters,
    }
    return rows, payload


def train(frames: dict[str, pd.DataFrame], map_name: str | None, min_rounds: int,
          n_bootstraps: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    profiles = build_profiles(frames, min_rounds=min_rounds)
    if profiles.empty:
        raise ValueError("ไม่พบ player profiles ที่ผ่านเกณฑ์ขั้นต่ำในชุดอ้างอิง")
    assigned, models = [], {}
    for side in ("t", "ct"):
        side_rows, models[side] = fit_side(profiles, side, n_bootstraps=n_bootstraps)
        assigned.append(side_rows)
    result = pd.concat(assigned, ignore_index=True)
    payload = {
        "model": "separate-side-player-role-kmeans",
        "version": 1,
        "map": map_name or "all",
        "unit": "player-match-side",
        "n_clusters_per_side": N_CLUSTERS,
        "min_rounds_per_profile": min_rounds,
        "training_source": "matches.source='reference' only",
        "interpretation_note": (
            "Role names interpret unsupervised centroids; they are not training labels, "
            "performance grades, or permanent identities. Bomb carrier uses the nearest-T-to-plant proxy."
        ),
        "models": models,
    }
    return result, payload


def train_from_kills_csv(kills: pd.DataFrame, csv_path: Path, map_name: str | None,
                         min_rounds: int, n_bootstraps: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    profiles = build_profiles_from_kills(kills, min_rounds=min_rounds)
    if profiles.empty:
        raise ValueError("ไม่พบ player profiles ที่ผ่านเกณฑ์ขั้นต่ำใน all_kills.csv")
    assigned, models = [], {}
    for side in ("t", "ct"):
        features = CSV_T_FEATURES if side == "t" else CSV_CT_FEATURES
        side_rows, models[side] = fit_side(
            profiles, side, n_bootstraps=n_bootstraps, features=features,
            signatures_by_side=CSV_ROLE_SIGNATURES, n_clusters=CSV_N_CLUSTERS,
        )
        assigned.append(side_rows)
    result = pd.concat(assigned, ignore_index=True)
    payload = {
        "model": "separate-side-player-role-kmeans",
        "version": 2,
        "map": map_name or "all",
        "unit": "player-match-side",
        "n_clusters_per_side": CSV_N_CLUSTERS,
        "min_rounds_per_profile": min_rounds,
        "training_source": str(csv_path),
        "source_matches": int(kills["demo_file"].nunique()),
        "source_kills": int(len(kills)),
        "interpretation_note": (
            "Role names interpret unsupervised centroids; they are not training labels, performance grades, "
            "or permanent identities. CSV-only training has no grenade throws, movement, or planter id. "
            "Support uses assist/flash-assist proxies; anchor/rotator use kill-event callout proxies; "
            "bomb carrier/site executor uses site and post-plant kill-event proxies. A sixth "
            "Hybrid / Unresolved cluster prevents forcing a role name when kill events do not support one."
        ),
        "models": models,
    }
    return result, payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train separate T/CT player-role clusters")
    parser.add_argument("--source", choices=("csv", "database"), default="csv",
                        help="training source (default: csv)")
    parser.add_argument("--csv", type=Path, default=ALL_KILLS_CSV,
                        help=f"role-ready all_kills.csv (default: {ALL_KILLS_CSV})")
    parser.add_argument("--map", dest="map_name", default=None, help="optional map filter, e.g. de_mirage")
    parser.add_argument("--min-rounds", type=int, default=MIN_ROUNDS)
    parser.add_argument("--bootstraps", type=int, default=N_BOOTSTRAPS)
    parser.add_argument("--output-dir", type=Path, default=OUT)
    parser.add_argument("--database-url", default=DATABASE_URL, help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.min_rounds < 1 or args.bootstraps < 0:
        raise SystemExit("--min-rounds ต้องไม่น้อยกว่า 1 และ --bootstraps ต้องไม่ติดลบ")
    try:
        if args.source == "csv":
            kills = load_kills_csv(args.csv, args.map_name)
            profiles, payload = train_from_kills_csv(
                kills, args.csv, args.map_name, args.min_rounds, args.bootstraps)
        else:
            frames = asyncio.run(load_frames(args.database_url, args.map_name))
            profiles, payload = train(frames, args.map_name, args.min_rounds, args.bootstraps)
    except ValueError as exc:
        raise SystemExit(
            f"เทรนไม่ได้: {exc}\n"
            "ถ้าใช้ CSV ให้รัน python research/demoparser.py ก่อน; ถ้าใช้ฐานข้อมูลให้ตรวจว่า "
            "import เดโมด้วย --mark-reference และมี player_rounds อย่างน้อยตาม --min-rounds"
        ) from None
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "player_role.json"
    csv_path = args.output_dir / "player_role_profiles.csv"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    profiles.to_csv(csv_path, index=False, encoding="utf-8-sig")

    scope = args.map_name or "ทุกแมพ"
    print(f"Player role model · {scope} · {args.source} · reference only")
    for side in ("t", "ct"):
        model = payload["models"][side]
        print(f"\n{side.upper()} · {model['profiles']} profiles · silhouette {model['metrics']['silhouette']:.3f} "
              f"· bootstrap ARI {model['metrics']['bootstrap_ari']:.3f}")
        for cluster in model["clusters"]:
            print(f"  {cluster['id']}. {cluster['role']:<30} {cluster['profiles']:>4} profiles")
    print(f"\nบันทึกแล้ว:\n  {json_path}\n  {csv_path}")


if __name__ == "__main__":
    main()
