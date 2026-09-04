#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
train_round_win.py — เทรนโมเดล "โอกาสชนะรอบ"

    python pipeline/train_round_win.py

โจทย์
    หลังคิลแต่ละครั้ง เรารู้สถานะของรอบ: CT เหลือกี่คน / T เหลือกี่คน /
    ระเบิดลงหรือยัง / ผ่านไปกี่วินาที  →  ถามโมเดลว่า "ฝั่ง CT จะชนะรอบนี้ไหม"
    เฉลยอยู่ในคอลัมน์ round_winner ของ csv อยู่แล้ว

กฎข้อเดียว
    ฟีเจอร์ต้องเป็นสิ่งที่รู้ "ณ ตอนนั้น" เท่านั้น ห้ามใช้ของที่รู้หลังรอบจบ
    (เช่น round_end_reason) ไม่งั้นคะแนนสวยแต่โกง
"""
import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "all_kills.csv"
OUT = ROOT / "output" / "round_win_model.joblib"

FEATURES = ["alive_ct", "alive_t", "planted", "time_sec"]

for _s in (sys.stdout, sys.stderr):     # ให้คอนโซล Windows พิมพ์ไทยได้
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


# ---------------------------------------------------------------------------
# 1) โหลด csv — หนึ่งแถว = หนึ่งคิล
# ---------------------------------------------------------------------------
df = pd.read_csv(CSV)
df = df.sort_values(["demo_file", "round_num", "tick"], kind="stable")
print(f"โหลด {len(df):,} คิล จาก {df['demo_file'].nunique()} แมตช์")


# ---------------------------------------------------------------------------
# 2) สร้างฟีเจอร์ = สถานะของรอบ "หลัง" คิลแถวนี้เกิดขึ้น
# ---------------------------------------------------------------------------
# นับว่าในรอบนี้ ตายไปแล้วกี่คนของแต่ละฝั่ง (นับรวมแถวนี้ด้วย)
each_round = df.groupby(["demo_file", "round_num"])
dead_ct = each_round["victim_side"].transform(lambda s: (s == "ct").cumsum())
dead_t = each_round["victim_side"].transform(lambda s: (s == "t").cumsum())

df["alive_ct"] = (5 - dead_ct).clip(lower=0)
df["alive_t"] = (5 - dead_t).clip(lower=0)

# ระเบิดลงแล้วหรือยัง ณ tick ของคิลนี้ (bomb_plant_tick ว่าง = รอบนี้ไม่ได้วาง)
df["planted"] = (df["bomb_plant_tick"].notna() & (df["tick"] >= df["bomb_plant_tick"])).astype(int)

# ผ่านไปกี่วินาทีตั้งแต่รอบเริ่ม
df["time_sec"] = (df["tick"] - df["round_start_tick"]) / df["tickrate"]

# เฉลย: 1 = CT ชนะรอบ, 0 = T ชนะรอบ
df["y"] = (df["round_winner"] == "ct").astype(int)

X = df[FEATURES]
y = df["y"]
groups = df["demo_file"]        # ใช้แบ่ง train/test ตามแมตช์


# ---------------------------------------------------------------------------
# 3) วัดผลแบบไม่โกง — แบ่งตามแมตช์ ไม่ใช่สุ่มรายแถว
# ---------------------------------------------------------------------------
# คิลในรอบเดียวกันมีเฉลยเดียวกันหมด ถ้าสุ่มรายแถว แถวจากรอบเดียวกันจะไปอยู่
# ทั้ง train และ test → โมเดลจำเฉลยได้ → คะแนนสวยเกินจริง
pred = pd.Series(0.0, index=df.index)
for train_idx, test_idx in GroupKFold(n_splits=5).split(X, y, groups):
    model = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200)
    model.fit(X.iloc[train_idx], y.iloc[train_idx])
    pred.iloc[test_idx] = model.predict_proba(X.iloc[test_idx])[:, 1]

print(f"\nผลวัดแบบ 5-fold แบ่งตามแมตช์")
print(f"  AUC   {roc_auc_score(y, pred):.3f}   (0.5 = เดาสุ่ม, 1.0 = ทายถูกหมด)")
print(f"  Brier {brier_score_loss(y, pred):.4f} (ยิ่งต่ำยิ่งดี, เดาค่าเฉลี่ยได้ {brier_score_loss(y, [y.mean()] * len(y)):.4f})")


# ---------------------------------------------------------------------------
# 4) เทรนจริงด้วยข้อมูลทั้งหมด แล้วเซฟ
# ---------------------------------------------------------------------------
model = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200)
model.fit(X, y)

OUT.parent.mkdir(exist_ok=True)
joblib.dump(model, OUT)
print(f"\nเซฟโมเดลแล้ว: {OUT}")


# ---------------------------------------------------------------------------
# 5) ลองถามโมเดลดูสักหน่อย
# ---------------------------------------------------------------------------
examples = pd.DataFrame([
    # alive_ct, alive_t, planted, time_sec
    [5, 5, 0, 10],     # ต้นรอบ เท่ากัน
    [5, 3, 0, 40],     # CT ได้เปรียบ 5v3
    [3, 5, 0, 40],     # T ได้เปรียบ 3v5
    [2, 2, 1, 80],     # 2v2 ระเบิดลงแล้ว
    [1, 1, 1, 100],    # 1v1 ระเบิดลงแล้ว
], columns=FEATURES)

examples["P(CT ชนะ)"] = model.predict_proba(examples)[:, 1].round(2)
print("\nตัวอย่างคำทำนาย")
print(examples.to_string(index=False))
