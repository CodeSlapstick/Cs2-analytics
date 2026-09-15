#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Site ML (supervised) — ทายว่าฝั่ง T จะเอาบอมบ์ไปลงไซต์ไหน จากตำแหน่งที่ยืนกันอยู่

    python research/site_ml.py

ต่างจาก grid_ml1.py ตรงไหน
    grid_ml1.py เป็น unsupervised: ไม่มีเฉลย ถามว่า "การปะทะจัดกลุ่มตัวเองอย่างไร"
    ไฟล์นี้เป็น supervised: มีเฉลยจริง (บอมบ์ลง A หรือ B) วัดได้ตรง ๆ ว่าทายถูกกี่ %

คำถาม
    ณ วินาทีที่ t ของรอบ ถ้าดูแค่ว่า T ที่ยังไม่ตายยืนอยู่ callout ไหนบ้าง
    เดาได้ไหมว่าอีกสักพักบอมบ์จะไปลงไซต์ไหน — และเดาได้เร็วแค่ไหนก่อนบอมบ์ลงจริง

ทำไมคำถามนี้มีประโยชน์กับทีม
    ถ้าโมเดลอ่านออกตั้งแต่วินาทีต้น ๆ แปลว่าคู่แข่งที่ดูเทปก็อ่านออกเหมือนกัน
    "อ่านออกวินาทีที่เท่าไร" จึงเป็นตัวชี้วัดว่าการเข้าของทีมนั้นปกปิดทิศทางได้ดีแค่ไหน

กฎที่ห้ามพลาด
    เทรนจาก source='reference' เท่านั้น — เดโมที่ผู้ใช้อัปโหลดห้ามเข้าชุดเทรนเด็ดขาด
    (ดู backend/tests/test_data_separation.py · เหตุผลอยู่ใน README หัวข้อ "กันข้อมูลของผู้ใช้ไม่ให้ปนเข้าชุดเทรน")

กันข้อมูลรั่ว
    ใช้เฉพาะรอบที่บอมบ์ลง "หลัง" วินาทีที่ t และไม่แตะข้อมูลหลังบอมบ์ลงเลย
    แบ่ง train/test ด้วย GroupKFold ตาม "แมตช์" ไม่ใช่ตามรอบ — รอบจากแมตช์เดียวกันไม่เป็นอิสระต่อกัน

ผลลัพธ์
    output/site_model.json — น้ำหนักของ logistic regression หนึ่งชุดต่อหนึ่งวินาที
    เลือก logistic regression เพราะเขียนลง JSON ได้ทั้งตัว หน้าเว็บ/API จึงใช้โมเดลได้โดยไม่ต้องมี sklearn
    และดูน้ำหนักแล้วอธิบายได้เลยว่าโมเดลใช้ callout ไหนตัดสิน
"""
import asyncio
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, cross_val_predict, cross_val_score
from sklearn.preprocessing import StandardScaler

# ===========================================================================
# CONFIG — ปรับตรงนี้ที่เดียว
# ===========================================================================
MAP = "de_mirage"
TIMES = range(5, 41)      # วินาทีที่ทำนาย (หนึ่งโมเดลต่อหนึ่งวินาที)
MIN_ROUNDS = 60           # วินาทีไหนเหลือรอบน้อยกว่านี้ ไม่เทรน (ท้ายรอบข้อมูลบางลงเรื่อย ๆ)
C_REG = 0.5               # ยิ่งน้อยยิ่งกันโมเดลจำข้อมูล — 24 ฟีเจอร์ต่อ ~500 รอบต้องคุมไว้
N_SPLITS = 5
SEED = 0

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
sys.path.insert(0, str(ROOT))
from backend.db import DATABASE_URL  # noqa: E402  ใช้ค่าเดียวกับทั้งระบบ

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


# ===========================================================================
# STEP 1 — ดึงข้อมูล (เฉพาะชุดอ้างอิง)
# ===========================================================================
ROUNDS_SQL = """
    SELECT m.demo_file, r.match_id, r.round_num, r.start_tick, m.tickrate,
           r.bomb_plant_tick, r.bomb_site
    FROM rounds r JOIN matches m ON m.id = r.match_id
    WHERE m.source = 'reference' AND m.map_name = $1
      AND r.bomb_site IS NOT NULL AND r.start_tick IS NOT NULL AND r.bomb_plant_tick IS NOT NULL
"""
POS_SQL = """
    SELECT p.match_id, p.round_num, p.tick, p.place
    FROM player_positions p JOIN matches m ON m.id = p.match_id
    WHERE m.source = 'reference' AND m.map_name = $1 AND p.side = 't'
      AND p.place IS NOT NULL AND p.health > 0
"""


async def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    import asyncpg
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rounds = pd.DataFrame([dict(r) for r in await conn.fetch(ROUNDS_SQL, MAP)])
        pos = pd.DataFrame([dict(r) for r in await conn.fetch(POS_SQL, MAP)])
    finally:
        await conn.close()
    return rounds, pos


rounds, pos = asyncio.run(load())
if rounds.empty:
    sys.exit(f"ไม่มีรอบที่วางบอมบ์ของแมพ {MAP} ในชุดอ้างอิง — โหลดเดโมเข้าระบบแล้วรัน "
             "`python -m backend.etl_loader --mark-reference` กับ `--fix-bomb-sites` ก่อน")

rate = rounds["tickrate"].fillna(128)
rounds["plant_t"] = (rounds["bomb_plant_tick"] - rounds["start_tick"]) / rate
rounds = rounds[rounds["plant_t"].between(0, 200)]

pos = pos.merge(rounds[["match_id", "round_num", "start_tick", "tickrate", "bomb_site", "demo_file", "plant_t"]],
                on=["match_id", "round_num"], how="inner")
pos["t"] = ((pos["tick"] - pos["start_tick"]) / pos["tickrate"].fillna(128)).round().astype(int)
PLACES = sorted(pos["place"].unique())

share_a = (rounds["bomb_site"] == "A").mean()
print(f"{MAP} · ชุดอ้างอิง {rounds['demo_file'].nunique()} แมตช์ · รอบที่วางบอมบ์ {len(rounds)} รอบ "
      f"(A {int(share_a * len(rounds))} · B {len(rounds) - int(share_a * len(rounds))})")
print(f"ทายไซต์ที่มาบ่อยสุดทุกครั้งถูก {max(share_a, 1 - share_a):.1%} — โมเดลต้องชนะเลขนี้ถึงจะมีประโยชน์")
print(f"callout ที่ T เคยยืน {len(PLACES)} จุด · บอมบ์ลงเฉลี่ยวินาทีที่ {rounds['plant_t'].mean():.0f}\n")


def snapshot(rows: pd.DataFrame) -> pd.DataFrame:
    """หนึ่งรอบ = หนึ่งแถว · หนึ่งคอลัมน์ = จำนวน T ที่ยังไม่ตายยืนอยู่ callout นั้น"""
    return (rows.pivot_table(index=["match_id", "round_num"], columns="place", values="tick",
                             aggfunc="count", fill_value=0)
            .reindex(columns=PLACES, fill_value=0))


# ===========================================================================
# STEP 2 — เทรนทีละวินาที แล้ววัดผลแบบแบ่งตามแมตช์
# ===========================================================================
print(f"{'วินาที':>7} {'รอบ':>5} {'ทายมั่ว':>8} {'โมเดล':>8} {'ดีขึ้น':>8}")
models, scan = {}, []
for t in TIMES:
    snap = pos[(pos["t"] == t) & (pos["plant_t"] > t)]
    if snap.empty:
        continue
    X = snapshot(snap)
    meta = X.index.to_frame(index=False).merge(
        rounds[["match_id", "round_num", "bomb_site", "demo_file"]], on=["match_id", "round_num"])
    y = (meta["bomb_site"] == "A").astype(int).to_numpy()
    groups = meta["demo_file"].to_numpy()
    if len(y) < MIN_ROUNDS or len(np.unique(y)) < 2 or len(np.unique(groups)) < N_SPLITS:
        continue

    Xv = X.to_numpy(float)
    cv = GroupKFold(n_splits=N_SPLITS)
    base = cross_val_score(DummyClassifier(strategy="most_frequent"), Xv, y, cv=cv, groups=groups).mean()
    # สเกลเองแล้วพับกลับเข้าน้ำหนัก เพื่อให้ JSON ใช้กับ "จำนวนคนดิบ" ได้ตรง ๆ ไม่ต้องส่ง scaler ไปด้วย
    sc = StandardScaler().fit(Xv)
    acc = cross_val_score(LogisticRegression(max_iter=2000, C=C_REG, random_state=SEED),
                          sc.transform(Xv), y, cv=cv, groups=groups).mean()
    clf = LogisticRegression(max_iter=2000, C=C_REG, random_state=SEED).fit(sc.transform(Xv), y)
    coef = clf.coef_[0] / sc.scale_
    intercept = float(clf.intercept_[0] - (clf.coef_[0] * sc.mean_ / sc.scale_).sum())

    models[t] = {"intercept": intercept, "coef": {p: float(c) for p, c in zip(PLACES, coef, strict=True)},
                 "rounds": int(len(y)), "accuracy": float(acc), "baseline": float(base)}
    scan.append({"t": t, "rounds": len(y), "baseline": base, "accuracy": acc})
    print(f"{t:>6}s {len(y):>5} {base:>8.1%} {acc:>8.1%} {acc - base:>+8.1%}")

if not models:
    sys.exit("ไม่มีวินาทีไหนที่ข้อมูลพอจะเทรน")

scan = pd.DataFrame(scan)
best = scan.loc[scan["accuracy"].idxmax()]
print(f"\nแม่นสุดที่วินาทีที่ {int(best['t'])}: {best['accuracy']:.1%} (ทายมั่ว {best['baseline']:.1%})")

# ===========================================================================
# STEP 3 — ทีมอาชีพ "อ่านออกวินาทีที่เท่าไร" ไว้เป็นเส้นเทียบ
# ===========================================================================
# ต้องใช้คำทำนายแบบ out-of-fold เท่านั้น: ทำนายรอบไหนก็ใช้โมเดลที่ไม่เคยเห็นแมตช์นั้น
# ถ้าใช้โมเดลที่เทรนรวมรอบนั้นไปด้วย ตัวเลขจะสวยเกินจริง แล้วเส้นเทียบก็โกหก
READ_AT = 0.80          # มั่นใจถึงเท่านี้ และมั่นใจถูกทาง = "อ่านออก"
oof: dict[tuple[int, int], dict[int, float]] = {}
for t in models:
    snap = pos[(pos["t"] == t) & (pos["plant_t"] > t)]
    X = snapshot(snap)
    meta = X.index.to_frame(index=False).merge(
        rounds[["match_id", "round_num", "bomb_site", "demo_file"]], on=["match_id", "round_num"])
    y = (meta["bomb_site"] == "A").astype(int).to_numpy()
    groups = meta["demo_file"].to_numpy()
    Xs = StandardScaler().fit_transform(X.to_numpy(float))
    proba = cross_val_predict(LogisticRegression(max_iter=2000, C=C_REG, random_state=SEED),
                              Xs, y, cv=GroupKFold(n_splits=N_SPLITS), groups=groups, method="predict_proba")[:, 1]
    for (mid, rn), p in zip(X.index, proba, strict=True):
        oof.setdefault((mid, rn), {})[t] = float(p)

truth_of = rounds.set_index(["match_id", "round_num"])["bomb_site"].to_dict()
read_rows = []
for key, by_t in oof.items():
    truth = truth_of.get(key)
    if truth not in ("A", "B"):
        continue
    first = next((t for t in sorted(by_t) if (by_t[t] if truth == "A" else 1 - by_t[t]) >= READ_AT), None)
    read_rows.append({"read_at": first})
read = pd.DataFrame(read_rows)
seen = read["read_at"].dropna()
readability = {
    "threshold": READ_AT,
    "rounds": int(len(read)),
    "read_share": float(seen.size / len(read)) if len(read) else 0.0,
    "avg_read_at": float(seen.mean()) if seen.size else None,
    "median_read_at": float(seen.median()) if seen.size else None,
}
print(f"\nทีมอาชีพ (วัดแบบ out-of-fold): โมเดลอ่านออก {readability['read_share']:.0%} ของรอบ "
      f"· เฉลี่ยวินาทีที่ {readability['avg_read_at']:.1f}")

# ===========================================================================
# STEP 4 — โมเดลใช้ callout ไหนตัดสิน (คำถามที่อาจารย์ถามแน่ ๆ)
# ===========================================================================
mid = min(models, key=lambda t: abs(t - 15))
w = pd.Series(models[mid]["coef"]).sort_values()
print(f"\nน้ำหนักที่วินาทีที่ {mid} — บวก = ชี้ไป A · ลบ = ชี้ไป B (ต่อ T หนึ่งคนที่ยืนตรงนั้น)")
for place, v in pd.concat([w.head(4), w.tail(4)]).items():
    print(f"  {place:<20} {v:+.2f}  {'-> B' if v < 0 else '-> A'}")

# ===========================================================================
# STEP 5 — เซฟให้ API ใช้
# ===========================================================================
OUT.mkdir(exist_ok=True)
payload = {
    "map": MAP,
    "target": "bomb_site",
    "classes": {"1": "A", "0": "B"},
    "places": PLACES,
    "source": {"matches": int(rounds["demo_file"].nunique()), "rounds": int(len(rounds)),
               "label": f"เดโมทีมอาชีพ {rounds['demo_file'].nunique()} แมตช์ ({len(rounds)} รอบที่วางบอมบ์บน {MAP})"},
    "note": "ทำนายเฉพาะรอบที่ T ได้วางบอมบ์ · เทรนจากชุดอ้างอิงเท่านั้น ไม่เคยเห็นแมตช์ที่ผู้ใช้อัปโหลด",
    "metrics": {"best_t": int(best["t"]), "best_accuracy": float(best["accuracy"]),
                "baseline": float(scan["baseline"].mean()),
                "readability": readability,
                "scan": scan.to_dict("records")},
    "models": {str(t): m for t, m in sorted(models.items())},
}
(OUT / "site_model.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
scan.to_csv(OUT / "site_ml_scan.csv", index=False, encoding="utf-8-sig")
print(f"\nเซฟแล้ว:\n  {OUT / 'site_model.json'}\n  {OUT / 'site_ml_scan.csv'}")
