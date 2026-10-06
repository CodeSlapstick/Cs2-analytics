import numpy as np
from sklearn.ensemble import RandomForestClassifier

from backend.coach import build_coach_samples, recommend_round, round_context, tree_distribution
from backend.coach_data import load_coach_facts


def test_pre_round_context_has_no_outcome_or_future_input():
    players = [{"equip_value": 4200, "winner_side": "t", "future_place": "BombsiteA"} for _ in range(5)]
    context = round_context(players, 2)
    assert context == [.42, 0, 1, 0, 0, 0]
    for row in players:
        row.update(winner_side="ct", future_place="BombsiteB")
    assert round_context(players, 2) == context
    assert round_context(players[:4], 2) is None
    assert round_context([{"equip_value": None}] * 5, 2) is None


def test_portable_forest_inference_matches_sklearn():
    x = np.array([[0], [.2], [.4], [.6], [.8], [1]])
    y = [0, 0, 0, 1, 1, 1]
    clf = RandomForestClassifier(n_estimators=3, max_depth=2, random_state=42).fit(x, y)
    for value in [.1, .5, .9]:
        results = []
        for estimator in clf.estimators_:
            tree = estimator.tree_
            results.append(tree_distribution([value], {
                "left": tree.children_left, "right": tree.children_right, "feature": tree.feature,
                "threshold": tree.threshold, "values": tree.value[:, 0, :]}))
        np.testing.assert_allclose(np.mean(results, axis=0), clf.predict_proba([[value]])[0])


def test_no_model_or_training_match_never_returns_recommendations():
    sample = {"round_num": 1, "side": "t", "context": [0] * 6, "opening": None}
    assert recommend_round(sample, None, map_name="de_mirage")["available"] is False
    model = {"map": "de_mirage", "training_match_ids": [1], "sides": {"t": {}}}
    assert recommend_round(sample, model, map_name="de_mirage", exclude_match=1)["reason"] == "training_match"
    assert recommend_round({**sample, "context": None}, model, map_name="de_mirage")["reason"] == "missing_economy"


def test_real_fixture_opening_requires_real_snapshots(sample_doc):
    facts = []
    rounds = {r["round_num"]: r for r in sample_doc["rounds"]}
    for player in sample_doc["player_rounds"]:
        rnd = rounds[player["round_num"]]
        facts.append({**rnd, **player, "round_id": rnd["round_num"], "match_id": 1,
                      "demo_file": sample_doc["match"]["demo_file"], "source": "upload",
                      "tickrate": sample_doc["match"]["tickrate"]})
    data = {"facts": facts, "positions": [{**p, "round_id": p["round_num"]} for p in sample_doc["positions"]], "utility": []}
    assert any(s["opening"] is not None for s in build_coach_samples(data))
    assert all(s["opening"] is None for s in build_coach_samples({**data, "positions": []}))


def test_training_sql_has_explicit_reference_boundary():
    import asyncio

    class Conn:
        def __init__(self):
            self.sql = []

        async def fetch(self, sql, *args):
            self.sql.append(sql)
            return []

    conn = Conn()
    asyncio.run(load_coach_facts(conn, "de_mirage", reference_only=True))
    assert len(conn.sql) == 3
    assert all("m.source = 'reference'" in sql for sql in conn.sql)
