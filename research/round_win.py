#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
โมเดล "โอกาสชนะรอบ" — จากสถานะกลางรอบ ทายว่าฝั่ง CT จะชนะรอบนั้นไหม

    python research/round_win.py

ต่างจาก grid_ml.py ยังไง
    grid_ml.py ถามว่า "การดวลครั้งนี้ คนยิงเป็นฝั่งไหน" — คำถามระดับกระสุนนัดเดียว
    ไฟล์นี้ถามว่า "จากสถานะตรงนี้ ใครจะชนะรอบ" — คำถามระดับรอบ

    ฟีเจอร์ชุดเดียวกัน (คนเหลือกี่ต่อกี่ / ระเบิดลงหรือยัง / นาทีที่เท่าไร)
    ให้ผลต่างกันคนละโลก: กับคำถามแรกได้ AUC ~0.55 (เกือบเดาสุ่ม)
    กับคำถามนี้ได้ ~0.82 เพราะความได้เปรียบเป็นเรื่องของรอบ ไม่ใช่ของกระสุน

ผลลัพธ์
    output/round_win.json — ตารางเปิดค่า P(CT ชนะรอบ) ของทุกสถานะที่เป็นไปได้
    ตัวโมเดลใช้ฟีเจอร์หมวดหมู่ล้วน คำทำนายจึงยุบเป็นตารางเปิดค่าได้หมด
    หน้าเว็บเลยไม่ต้องมีโมเดลอยู่ในตัว แค่เปิดตารางดู
"""
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "all_kills.csv"
OUT = ROOT / "output" / "round_win.json"

MAP = "de_mirage"
N_SPLITS = 5
C_PENALTY = 1.0

# แหล่งข้อมูล: auto = ลอง PostgreSQL ก่อน (เดโมที่อัปโหลดผ่านเว็บอยู่ที่นั่น) ต่อไม่ได้ค่อยถอยไป csv
#   python research/round_win.py --source=db     บังคับ DB
#   python research/round_win.py --source=csv    บังคับ csv (Docker ที่ไม่มี DB)
SOURCE = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--source=")), "auto")
sys.path.insert(0, str(ROOT))                   # ให้ import research.datasource ได้เมื่อรันเป็นสคริปต์
from research.datasource import load_kills  # noqa: E402

# ช่วงเวลาในรอบ — ต้นรอบยังตั้งหลักกันอยู่ ท้ายรอบคือบีบเวลา คนละสถานการณ์กัน
TIME_EDGES = [-1, 20, 40, 1e9]
TIME_NAMES = ["0-20s", "20-40s", "40s+"]

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def add_state(df: pd.DataFrame) -> pd.DataFrame:
    """เติมสถานะ 'ก่อน' การตายแต่ละครั้ง: ใครเหลือกี่คน ระเบิดลงยัง วินาทีที่เท่าไร"""
    df = df.sort_values(["demo_file", "round_num", "tick"], kind="stable")
    g = df.groupby(["demo_file", "round_num"], sort=False)

    # shift(1) คือหัวใจ — ต้องเป็นจำนวนคนตาย "ก่อนแถวนี้" ไม่ใช่รวมแถวนี้
    # ถ้ารวมแถวนี้ด้วย เท่ากับรู้ผลของเหตุการณ์ที่กำลังจะทายอยู่แล้ว
    dead_ct = g["victim_side"].transform(lambda s: (s == "ct").cumsum().shift(1).fillna(0))
    dead_t = g["victim_side"].transform(lambda s: (s == "t").cumsum().shift(1).fillna(0))
    df["alive_ct"] = 5 - dead_ct
    df["alive_t"] = 5 - dead_t
    df["t_round"] = (df["tick"] - df["round_start_tick"]) / df["tickrate"].fillna(128)
    df["planted"] = (df["bomb_plant_tick"].notna() & (df["tick"] >= df["bomb_plant_tick"])).astype(int)
    return df


def features(alive_ct, alive_t, planted, t_round) -> pd.DataFrame:
    """ฟีเจอร์หมวดหมู่ล้วน — ตั้งใจให้ยุบเป็นตารางเปิดค่าได้ตอนท้าย

    ใช้คู่ (CT เหลือ, T เหลือ) ไม่ใช่ผลต่าง เพราะ 5v5 กับ 2v2 ผลต่างเท่ากันคือ 0
    แต่โอกาสชนะไม่เท่ากัน (0.52 กับ 0.38) — ผลต่างอย่างเดียวทิ้งข้อมูลนั้นไป
    """
    pair = alive_ct.astype(int).astype(str) + "v" + alive_t.astype(int).astype(str)
    tcat = pd.cut(t_round, TIME_EDGES, labels=TIME_NAMES)
    return pd.concat([
        pd.get_dummies(pair, prefix="p"),
        pd.get_dummies(tcat, prefix="t"),
        pd.Series(planted, name="planted", index=pair.index),
    ], axis=1)


def main() -> None:
    df = load_kills(MAP, source=SOURCE)
    source_desc = df.attrs.get("source", SOURCE)
    if df.empty:
        sys.exit(f"ไม่มีคิลของแมพ {MAP} ใน {source_desc}")
    if "round_winner" not in df.columns:
        sys.exit("ข้อมูลไม่มีคอลัมน์ round_winner — csv รุ่นเก่า รัน python research/demoparser.py --force ก่อน")
    print(f"แหล่งข้อมูล: {source_desc}")

    df = add_state(df)
    n_before = len(df)

    # ตัดแถวที่นับคนเหลือได้นอกช่วง 1-5
    # เกิดจากบางรอบที่ขอบเขตรอบเพี้ยนจนมีคนตายเกิน 10 คน สถานะแบบนั้นเป็นไปไม่ได้จริง
    # เก็บไว้จะกลายเป็นถังข้อมูลปลอมที่โมเดลเรียนไปด้วย
    ok = df["alive_ct"].between(1, 5) & df["alive_t"].between(1, 5)
    df = df[ok & df["round_winner"].notna()].copy()

    y = (df["round_winner"] == "ct").astype(int).to_numpy()
    groups = df["demo_file"].to_numpy()
    X = features(df["alive_ct"], df["alive_t"], df["planted"], df["t_round"])
    Xv = X.to_numpy(dtype=float)

    print(f"{n_before:,} แถว -> ใช้ได้ {len(df):,} จุดตัดสินใจ "
          f"| {df['demo_file'].nunique()} แมตช์ | {df.groupby(['demo_file', 'round_num']).ngroups:,} รอบ")
    print(f"  ตัดออก {n_before - len(df):,} แถวที่นับคนเหลือได้นอกช่วง 1-5 (ขอบรอบเพี้ยน)")

    # วัดผลแบบเดียวกับ grid_ml.py — GroupKFold แบ่งตามแมตช์
    # รอบจากแมตช์เดียวกันมีทีมเดียวกันเล่น ถ้าหลุดไปอยู่ทั้งสองฝั่งคะแนนจะสวยเกินจริง
    splits = list(GroupKFold(n_splits=N_SPLITS).split(Xv, y, groups))
    pred = np.zeros(len(df))
    base = np.zeros(len(df))
    for tr, te in splits:
        base[te] = y[tr].mean()
        m = LogisticRegression(C=C_PENALTY, max_iter=3000).fit(Xv[tr], y[tr])
        pred[te] = m.predict_proba(Xv[te])[:, 1]

    bb, bg = brier_score_loss(y, base), brier_score_loss(y, pred)
    print(f"\nวัดผลด้วย GroupKFold {N_SPLITS} กอง แบ่งตามแมตช์ | CT ชนะรอบรวม {y.mean():.3f}")
    print(f"  baseline (ไม่ดูอะไรเลย)  Brier {bb:.4f}")
    print(f"  สถานะกลางรอบ            Brier {bg:.4f}  AUC {roc_auc_score(y, pred):.3f}  "
          f"{(1 - bg / bb) * 100:+.1f}%  ({Xv.shape[1]} ฟีเจอร์)")

    # --- เทรนใหม่ด้วยข้อมูลทั้งหมด แล้วยุบเป็นตารางเปิดค่า ---
    # ตัวนี้เห็นเฉลยครบแล้ว เอาไปวัดผลไม่ได้ ใช้แค่ทำตารางให้หน้าเว็บเปิดดู
    final = LogisticRegression(C=C_PENALTY, max_iter=3000).fit(Xv, y)

    combos = [(ct, t, pl, tn)
              for ct in range(1, 6) for t in range(1, 6)
              for pl in (0, 1) for tn in TIME_NAMES]
    grid = pd.DataFrame(combos, columns=["alive_ct", "alive_t", "planted", "tcat"])
    Xg = features(grid["alive_ct"], grid["alive_t"], grid["planted"],
                  pd.Series([{"0-20s": 10, "20-40s": 30, "40s+": 50}[c] for c in grid["tcat"]]))
    Xg = Xg.reindex(columns=X.columns, fill_value=0)      # เรียงคอลัมน์ให้ตรงกับตอนเทรน
    grid["wp"] = final.predict_proba(Xg.to_numpy(dtype=float))[:, 1]

    table = {f"{r.alive_ct}v{r.alive_t}|{r.planted}|{r.tcat}": round(r.wp, 4)
             for r in grid.itertuples()}

    # นับจำนวนตัวอย่างจริงของแต่ละสถานะไว้ด้วย จะได้รู้ว่าค่าไหนมาจากข้อมูลน้อย
    seen = (df.assign(tcat=pd.cut(df["t_round"], TIME_EDGES, labels=TIME_NAMES))
              .groupby(["alive_ct", "alive_t", "planted", "tcat"], observed=True)
              .size())
    support = {f"{int(k[0])}v{int(k[1])}|{int(k[2])}|{k[3]}": int(v) for k, v in seen.items()}

    payload = {
        "map": MAP,
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),   # หน้าเว็บใช้บอกว่าผลเก่าแค่ไหน
        "source": source_desc,                                                     # เทรนจาก DB หรือ csv
        "time_edges": TIME_EDGES[1:-1],
        "time_names": TIME_NAMES,
        "metrics": {
            "rows": int(len(df)),
            "rounds": int(df.groupby(["demo_file", "round_num"]).ngroups),
            "matches": int(df["demo_file"].nunique()),
            "ct_win_overall": float(y.mean()),
            "brier_base": float(bb),
            "brier": float(bg),
            "auc": float(roc_auc_score(y, pred)),
            "gain_pct": float((1 - bg / bb) * 100),
        },
        "table": table,
        "support": support,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    print("\nโอกาสที่ CT ชนะรอบ (ยังไม่ปักระเบิด ช่วง 20-40 วินาที)")
    show = grid[(grid.planted == 0) & (grid.tcat == "20-40s")]
    print(show.pivot(index="alive_ct", columns="alive_t", values="wp")
              .to_string(float_format=lambda v: f"{v:.2f}"))
    print("แถว = CT เหลือ, คอลัมน์ = T เหลือ")
    print(f"\nเซฟที่ {OUT}")


if __name__ == "__main__":
    main()
