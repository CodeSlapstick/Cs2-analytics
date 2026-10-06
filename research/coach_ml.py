"""Train opening-pattern discovery + winning-reference imitation policy.

python research/coach_ml.py --map de_mirage
No causal optimal-tactic claim. Reference only; match-disjoint validation.
"""
import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import numpy as np
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.coach import CONTEXT_FEATURES, OPENING_FEATURES, VERSION, build_coach_samples  # noqa: E402
from backend.coach_data import load_coach_facts  # noqa: E402
from backend.db import DATABASE_URL  # noqa: E402

SEED = 42


def fit_policy(samples, clusters=4):
    x = np.array([r["opening"] for r in samples], dtype=float)
    scaler = StandardScaler().fit(x)
    km = KMeans(n_clusters=clusters, n_init=20, random_state=SEED).fit(scaler.transform(x))
    labels = km.labels_
    winning = np.array([r["won"] is True for r in samples])
    contexts = np.array([r["context"] for r in samples], dtype=float)
    policy = RandomForestClassifier(n_estimators=64, max_depth=5, min_samples_leaf=15,
                                    random_state=SEED, n_jobs=1).fit(contexts[winning], labels[winning])
    return scaler, km, policy, labels


def train_side(samples):
    if len(samples) < 120 or len({r["match_id"] for r in samples}) < 8:
        return None
    groups = np.array([r["match_id"] for r in samples])
    train_idx, test_idx = next(GroupShuffleSplit(n_splits=1, test_size=.25, random_state=SEED).split(samples, groups=groups))
    train = [samples[i] for i in train_idx]
    test = [samples[i] for i in test_idx if samples[i]["won"]]
    scaler, km, policy, _ = fit_policy(train)
    truth = km.predict(scaler.transform([r["opening"] for r in test]))
    context = [r["context"] for r in test]
    pred = policy.predict(context)
    train_winning_labels = km.predict(scaler.transform([r["opening"] for r in train if r["won"]]))
    baseline_class = int(np.bincount(train_winning_labels).argmax())
    accuracy = float(accuracy_score(truth, pred))
    baseline = float(np.mean(truth == baseline_class))
    validation = {"target": "pattern_used_in_winning_reference_round", "method": "match_disjoint_holdout",
                  "train_matches": sorted(set(int(groups[i]) for i in train_idx)),
                  "test_matches": sorted(set(int(groups[i]) for i in test_idx)),
                  "test_winning_rounds": len(test), "accuracy": accuracy, "baseline": baseline,
                  "beats_baseline": accuracy > baseline}
    scaler, km, policy, labels = fit_policy(samples)
    patterns = {}
    for cls in range(4):
        members = [r for r, label in zip(samples, labels, strict=True) if label == cls and r["won"]]
        profile = np.mean([r["opening"] for r, label in zip(samples, labels, strict=True) if label == cls], axis=0)
        areas = dict(zip(("A", "Mid", "B", "Other"), profile[4:8], strict=True))
        lead = max(areas, key=areas.get)
        if lead == "Other" or areas[lead] < .45:
            name = "Default spread" if samples[0]["side"] == "t" else "Balanced hold"
        else:
            name = f"{lead} pressure" if samples[0]["side"] == "t" else f"{lead}-weighted defense"
        patterns[str(cls)] = {"name": f"{name} · P{cls + 1}", "rounds": len(members),
                              "matches": len({r["match_id"] for r in members}),
                              "profile": {k: round(float(v), 4) for k, v in zip(OPENING_FEATURES, profile, strict=True)},
                              "evidence": [{k: r[k] for k in ("match_id", "demo_file", "round_num", "side", "context")} for r in members]}
    trees = []
    for estimator in policy.estimators_:
        tree = estimator.tree_
        trees.append({"left": tree.children_left.tolist(), "right": tree.children_right.tolist(),
                      "feature": tree.feature.tolist(), "threshold": tree.threshold.tolist(),
                      "values": tree.value[:, 0, :].tolist()})
    return {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(), "centers": km.cluster_centers_.tolist(),
            "classes": [int(c) for c in policy.classes_], "trees": trees, "patterns": patterns,
            "validation": validation, "training_rounds": len(samples)}


async def main(args):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        data = await load_coach_facts(conn, args.map, reference_only=True)
    finally:
        await conn.close()
    if any(r["source"] != "reference" for r in data["facts"]):
        raise ValueError("Uploaded matches must never enter Coach training")
    samples = [r for r in build_coach_samples(data) if r["opening"] is not None and r["won"] is not None]
    sides = {s: train_side([r for r in samples if r["side"] == s]) for s in ("t", "ct")}
    sides = {s: model for s, model in sides.items() if model is not None}
    if not sides:
        raise ValueError("Insufficient reference data: need 120 complete team-rounds across 8 matches per side")
    model = {"version": VERSION, "map": args.map, "trained_at": datetime.now(UTC).isoformat(),
             "source": "reference_only", "context_features": CONTEXT_FEATURES, "opening_features": OPENING_FEATURES,
             "training_match_ids": sorted({r["match_id"] for r in samples}), "sides": sides,
             "clock_provenance": "stored_start_tick_unverified"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(model, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps({"artifact": str(args.output), "reference_matches": len(model["training_match_ids"]),
                      "sides": {s: {"rounds": m["training_rounds"], **m["validation"]} for s, m in sides.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", default="de_mirage", choices=["de_mirage"])
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "coach_model.json")
    asyncio.run(main(parser.parse_args()))
