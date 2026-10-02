# -*- coding: utf-8 -*-
"""Unit tests for the player-role research pipeline (no database required)."""
from pathlib import Path

import numpy as np
import pandas as pd

from research.player_role import (
    FACTS_SQL,
    GRENADES_SQL,
    KILLS_SQL,
    POSITIONS_SQL,
    ROLE_ORDER,
    assign_role_names,
    build_profiles,
    build_profiles_from_kills,
    load_kills_csv,
)

ROOT = Path(__file__).resolve().parent.parent.parent


def test_every_role_training_query_is_reference_only():
    for query in (FACTS_SQL, POSITIONS_SQL, GRENADES_SQL, KILLS_SQL):
        assert "m.source = 'reference'" in query


def test_role_names_are_unique_for_each_side():
    rng = np.random.default_rng(7)
    for side, features in (
        ("t", [
            "opening_attempt_rate", "early_engagement_rate", "opening_kill_rate",
            "utility_per_round", "flash_per_round", "smoke_per_round", "assists_per_round",
            "team_separation", "place_diversity", "plant_proxy_rate", "survival_rate",
            "trade_kills_per_round", "traded_death_rate", "damage_per_round",
            "postplant_movement_per_plant",
        ]),
        ("ct", [
            "path_length", "early_displacement", "place_diversity", "survival_rate",
            "opening_attempt_rate", "early_engagement_rate", "opening_kill_rate",
            "utility_per_round", "flash_per_round", "smoke_per_round", "assists_per_round",
            "alive_at_plant_rate", "postplant_kills_per_plant", "postplant_movement_per_plant",
        ]),
    ):
        names, _ = assign_role_names(rng.normal(size=(5, len(features))), side, features)
        assert sorted(names) == sorted(ROLE_ORDER[side])


def test_profiles_keep_sides_separate_and_apply_minimum_rounds():
    facts = pd.DataFrame([
        {
            "demo_file": "ref.dem", "map_name": "de_mirage", "match_id": 1, "round_id": round_no,
            "round_num": round_no, "start_tick": 0, "bomb_plant_tick": None,
            "bomb_plant_x": None, "bomb_plant_y": None, "tickrate": 64,
            "steam_id": 10, "name": "p", "side": side, "survived": True,
            "kills": 0, "deaths": 0, "assists": 0, "damage": 0,
            "opening_kill": False, "opening_death": False, "trade_kills": 0, "was_traded": False,
        }
        for side, count in (("t", 5), ("ct", 3)) for round_no in range(1, count + 1)
    ])
    frames = {
        "facts": facts,
        "positions": pd.DataFrame(),
        "grenades": pd.DataFrame(),
        "kills": pd.DataFrame(),
    }
    profiles = build_profiles(frames, min_rounds=4)
    assert profiles["side"].tolist() == ["t"]
    assert profiles.iloc[0]["rounds"] == 5
    assert profiles.iloc[0]["opening_attempt_rate"] == 0


def test_reference_all_kills_builds_separate_player_match_side_profiles():
    kills = load_kills_csv(ROOT / "data" / "all_kills.csv", "de_mirage")
    profiles = build_profiles_from_kills(kills, min_rounds=5)
    assert len(profiles) == 940
    assert profiles.groupby("side").size().to_dict() == {"ct": 470, "t": 470}
    assert not profiles.duplicated(["demo_file", "steam_id", "side"]).any()
    assert profiles["rounds"].min() >= 5
