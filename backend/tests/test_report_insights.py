from backend.report_insights import build_insights, confidence


def raw_report(rounds=24):
    return {"match": {"demo_file": "team.dem"}, "players": [{"rounds": rounds, "opening_deaths": 5, "deaths": 14, "traded_deaths": 5}],
            "rounds": [{"round_num": 4, "deaths_count": 5, "first_death_t": 38.0}], "hotspots": [{"place": "Mid", "deaths": 6}]}


def test_insights_separate_possible_causes_from_observation():
    insights = build_insights(raw_report())
    assert insights[0].observation.startswith("พบ 6 deaths")
    assert insights[0].possible_causes
    assert "อาจ" in insights[0].possible_causes[0]
    assert insights[0].evidence[0].viewer_url.endswith("/rounds/4")


def test_confidence_uses_sample_size():
    assert confidence(5) == "low"
    assert confidence(10) == "medium"
    assert confidence(20) == "high"
