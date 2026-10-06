from backend.opening_routes import build_opening_rounds, match_date, select_matches


def test_dates_are_real_and_missing_dates_are_not_recent():
    matches = [{"id": i, "demo_file": name} for i, name in enumerate(
        ["2026-01-01_A.dem", "unknown.dem", "2026-09-01_B.dem", "2026-02-30_invalid.dem"])]
    assert match_date("2026-02-30.dem") is None
    assert [m["id"] for m in select_matches(matches, 5)] == [2, 0]
    assert len(select_matches(matches, 0)) == 4


def derive(*, positions=(), grenades=(), start=100, death=None, rate=64):
    return build_opening_rounds(
        [{"id": 1, "demo_file": "real.dem", "tickrate": rate}],
        [{"id": 5, "match_id": 1, "round_num": 1, "start_tick": start, "side": "ct", "death_tick": death}],
        list(positions), list(grenades), 123, "de_mirage")["rounds"][0]


def point(tick, x=100):
    return {"round_id": 5, "tick": tick, "x": x, "y": 100, "health": 100}


def test_live_start_window_death_and_gaps():
    result = derive(positions=[point(t) for t in [92, 100, 108, 116, 300, 308, 2020, 2028]])
    assert result["segments"][0][0]["t"] == 0
    assert result["side"] == "ct"
    assert len(result["segments"]) == 3
    assert result["segments"][-1][-1]["t"] == 30
    assert derive(positions=[point(100), point(108), point(116)], death=116)["segments"][0][-1]["t"] == .125


def test_invalid_positions_and_missing_clock_are_not_zero_coordinates():
    result = derive(positions=[point(100), point(108, None), point(116)])
    assert len(result["segments"]) == 2
    for missing in [derive(start=None), derive(rate=None), derive(rate=0)]:
        assert missing["segments"] == []
        assert missing["utility"] is None
        assert missing["clock_available"] is False


def test_utility_without_positions_and_unknown_endpoints():
    grenade = {"round_id": 5, "tick": 100, "type": "smoke", "thrower_id": 123,
               "side": "ct", "throw_x": None, "throw_y": None, "land_x": None, "land_y": None}
    result = derive(grenades=[grenade, {**grenade, "tick": 2020}, {**grenade, "tick": 2021}])
    assert len(result["utility"]) == 2
    assert result["utility"][0]["t_throw"] == 0
    assert result["utility"][0]["t_end"] is None
    assert result["utility"][0]["throw_px"] is None
    assert result["segments"] == []


def test_real_fixture_preserves_recorded_side_and_utility(sample_doc):
    source = sample_doc["rounds"][0]
    roster = next(p for p in sample_doc["player_rounds"] if p["round_num"] == source["round_num"])
    rnd = {**source, "id": 5, "match_id": 1, "side": roster["side"], "death_tick": None}
    utility = [{**g, "round_id": 5} for g in sample_doc.get("grenades", [])
               if g["round_num"] == source["round_num"] and g.get("thrower_id") == roster["steam_id"]]
    positions = [{**p, "round_id": 5} for p in sample_doc["positions"]
                 if p["round_num"] == source["round_num"] and p["steam_id"] == roster["steam_id"]]
    result = build_opening_rounds([{**sample_doc["match"], "id": 1}], [rnd], positions, utility,
                                  roster["steam_id"], sample_doc["match"]["map_name"])["rounds"][0]
    assert result["side"] == roster["side"]
    assert result["segments"][0][0]["t"] == 0
    assert all(0 <= p["t"] <= 30 for segment in result["segments"] for p in segment)
    assert all(0 <= g["t_throw"] <= 30 for g in result["utility"])
