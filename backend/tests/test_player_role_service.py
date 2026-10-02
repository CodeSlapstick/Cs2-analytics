import json

from backend.player_role_service import (
    assign_profile,
    build_match_profiles,
    compatibility_reason,
    infer_match,
    load_role_model,
)


def artifact():
    side = {
        "features": ["assists_per_round", "avg_kill_time"],
        "preprocess": {
            "median": {"assists_per_round": 0.25, "avg_kill_time": 20.0},
            "mean": {"assists_per_round": 0.5, "avg_kill_time": 30.0},
            "scale": {"assists_per_round": 0.5, "avg_kill_time": 10.0},
        },
        "clusters": [
            {"id": 0, "role": "Support", "role_name_status": "supported",
             "center_z": {"assists_per_round": 1.0, "avg_kill_time": -1.0}},
            {"id": 1, "role": "Lurker", "role_name_status": "supported",
             "center_z": {"assists_per_round": -1.0, "avg_kill_time": 1.0}},
        ],
    }
    return {"unit": "player-match-side", "map": "de_mirage", "min_rounds_per_profile": 2,
            "models": {"t": side, "ct": side}}


def test_missing_artifact_and_compatibility(tmp_path):
    load_role_model.cache_clear()
    assert load_role_model(str(tmp_path / "missing.json")) is None
    assert compatibility_reason(None, "de_mirage", "upload") == "model_unavailable"
    assert compatibility_reason(artifact(), "de_nuke", "upload") == "unsupported_map"
    assert compatibility_reason(artifact(), "de_mirage", "reference") == "uploaded_matches_only"
    assert compatibility_reason(artifact(), "de_mirage", "upload") is None


def test_artifact_feature_order_median_scale_and_margin():
    result = assign_profile({"assists_per_round": 1.0, "avg_kill_time": None}, "t", artifact())
    # avg_kill_time is median-imputed to z=-1; this lands exactly on Support.
    assert result["role"] == "Support"
    assert result["distance"] == 0
    assert result["margin"] > 0
    assert result["signals"][0]["feature"] in {"assists_per_round", "avg_kill_time"}


def test_profiles_are_separate_by_side_and_use_real_event_facts():
    rounds = [
        {"round_num": 1, "steam_id": 1, "name": "ผู้เล่น一", "side": "t", "assists": 1,
         "opening_kill": True, "opening_death": False, "trade_kills": 1, "was_traded": False},
        {"round_num": 2, "steam_id": 1, "name": "ผู้เล่น一", "side": "ct", "assists": 0,
         "opening_kill": False, "opening_death": True, "trade_kills": 0, "was_traded": True},
        {"round_num": 1, "steam_id": 2, "name": "B", "side": "ct", "assists": 0,
         "opening_kill": False, "opening_death": True, "trade_kills": 0, "was_traded": False},
        {"round_num": 2, "steam_id": 2, "name": "B", "side": "t", "assists": 0,
         "opening_kill": True, "opening_death": False, "trade_kills": 0, "was_traded": False},
    ]
    kills = [{"round_num": 1, "start_tick": 100, "bomb_plant_tick": 200, "tick": 220,
              "attacker_id": 1, "victim_id": 2, "assister_id": None, "attacker_side": "t",
              "victim_side": "ct", "attacker_place": "BombsiteA", "victim_place": "A Ramp",
              "assisted_flash": False}]
    profiles = build_match_profiles(rounds, kills, 64)
    p1 = [p for p in profiles if p["steamid"] == "1"]
    assert {p["side"] for p in p1} == {"t", "ct"}
    t = next(p for p in p1 if p["side"] == "t")
    assert t["rounds"] == 1 and t["postplant_kills_per_round"] == 1
    assert t["site_engagement_rate"] == 1 and t["avg_kill_time"] == 1.875


def test_minimum_rounds_and_player_filter():
    profiles = [{"steamid": "1", "name": "A", "side": "t", "rounds": 1},
                {"steamid": "2", "name": "B", "side": "ct", "rounds": 1}]
    result = infer_match(profiles, artifact(), {"1"})
    assert len(result) == 1
    assert result[0] == {"steamid": "1", "name": "A", "side": "t", "rounds": 1,
                         "available": False, "reason": "insufficient_rounds", "minimum_rounds": 2}


def test_loader_accepts_cached_inference_artifact(tmp_path):
    path = tmp_path / "role.json"
    path.write_text(json.dumps(artifact()), encoding="utf-8")
    load_role_model.cache_clear()
    assert load_role_model(str(path))["map"] == "de_mirage"
