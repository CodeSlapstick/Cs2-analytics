#!/usr/bin/env python3
"""
Map analytics — แบ่งแมพเป็น "โซนการปะทะ" ด้วย unsupervised learning

    python parser/map_zones.py de_dust2 -i backend/data/matches -o backend/data/zones
    python parser/map_zones.py de_dust2 --summary      # ดูผลเฉย ๆ ไม่เขียนไฟล์
    python parser/map_zones.py de_dust2 --k 8          # บังคับจำนวนโซน (ปกติเลือกให้เอง)

ทำไมต้องใช้ ML: การแบ่งโซนแบบเดิมคือ "ตีกริดสี่เหลี่ยมทับแมพ" ซึ่งไม่รู้จักแมพ
เส้นกริดจึงผ่ากลางจุดที่คนปะทะกันจริงบ่อย ๆ ทำให้จุดปะทะจุดเดียวถูกหั่นไปอยู่คนละช่อง
ตัวเลขที่ได้ก็เลยแปลไม่ออก วิธีนี้ปล่อยให้ **ข้อมูลบอกเองว่าโซนอยู่ตรงไหน** โดยจับกลุ่ม
พิกัดที่คนตายจริงในไฟล์ .dem แล้วให้ขอบเขตโซนวิ่งตามการเล่นจริง

หลักการเดียวกับที่ใช้ทั้งโปรเจกต์: **ไฟล์นี้ออกแบบโซนอย่างเดียว ไม่คำนวณสถิติ**
การให้คะแนนโซน (ฝั่งไหนได้เปรียบตรงไหน) ไปคิดที่ backend/src/services/mapZones.js
ที่เดียว เหมือนที่ parse_demo.py ไม่คิด KPI แต่ปล่อยให้ derive.js คิด

ผลลัพธ์คือ "โมเดล" ที่ fit แล้ว เก็บเป็น backend/data/zones/<map>.json — บอกไว้ด้วยว่า
fit จากกี่แมตช์ กี่จุด และได้คะแนนเท่าไร เพื่อให้ย้อนตรวจได้ว่าโซนชุดนี้มาจากข้อมูลชุดไหน
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

try:
    import numpy as np
    from sklearn.cluster import DBSCAN, KMeans
    from sklearn.metrics import silhouette_score
except ImportError as exc:  # pragma: no cover
    print(f"ต้องติดตั้ง dependency ก่อน: pip install -r parser/requirements.txt ({exc})", file=sys.stderr)
    raise SystemExit(1)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

SCHEMA_VERSION = 1

# ช่วงจำนวนโซนที่ยอมให้เลือก — ต่ำกว่า 4 หยาบไปจนโค้ชเอาไปใช้ไม่ได้
# สูงกว่า 14 ก็ละเอียดจนแต่ละโซนมีข้อมูลน้อยเกินกว่าจะเชื่อสถิติ
K_MIN, K_MAX = 4, 14

# โซนที่มีจุดน้อยกว่านี้ถือว่าเป็นเศษ ไม่ควรเอาไปแสดงเป็นโซนจริง
MIN_POINTS_PER_ZONE = 15

RANDOM_STATE = 42  # ตรึงไว้ให้ผลซ้ำได้ ไม่งั้นรันสองครั้งได้โซนคนละชุด


# ---------------------------------------------------------------------------
# อ่านข้อมูล
# ---------------------------------------------------------------------------
def load_deaths(match_dir: Path, map_name: str) -> tuple[list[dict], list[str]]:
    """
    ดึง "จุดที่มีคนตาย" จากไฟล์ normalized JSON ทุกไฟล์ของแมพนี้

    ใช้พิกัดคนตาย (victim) ไม่ใช่พิกัดคนยิง เพราะโซนที่เราอยากได้คือ
    "พื้นที่ที่อันตราย" ส่วนพิกัดคนยิงเก็บไว้ด้วยเพื่อทำลูกศรทิศทางการปะทะทีหลัง
    """
    deaths: list[dict] = []
    sources: list[str] = []
    for path in sorted(match_dir.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  ! ข้าม {path.name}: {exc}", file=sys.stderr)
            continue
        if doc.get("match", {}).get("map_name") != map_name:
            continue

        sources.append(doc["match"]["external_id"])
        for ev in doc.get("events", []):
            if ev.get("type") != "kill":
                continue
            if ev.get("victim_x") is None or ev.get("victim_y") is None:
                continue
            meta = ev.get("meta") or {}
            # เก็บแค่พิกัดกับ callout — ที่เหลือ (ใครฆ่าใคร ฝั่งไหน) ไม่ได้ใช้ตอนแบ่งโซน
            # และฝั่ง Node ดึงจากฐานข้อมูลได้อยู่แล้วตอนคิดคะแนน
            deaths.append(
                {
                    "x": float(ev["victim_x"]),
                    "y": float(ev["victim_y"]),
                    "place": meta.get("victim_place"),
                }
            )
    return deaths, sources


# ---------------------------------------------------------------------------
# เลือกจำนวนโซน
# ---------------------------------------------------------------------------
def choose_k(xy: np.ndarray, k_min: int = K_MIN, k_max: int = K_MAX) -> tuple[int, list[dict]]:
    """
    เลือกจำนวนโซนด้วย silhouette score

    silhouette ตอบคำถามว่า "จุดแต่ละจุดอยู่ใกล้พวกเดียวกันมากกว่าพวกอื่นแค่ไหน"
    ค่าอยู่ระหว่าง -1 ถึง 1 ยิ่งสูงยิ่งแบ่งกลุ่มได้ชัด เลือก k ที่ได้คะแนนสูงสุด

    ไม่ใช้ elbow method เพราะจุดหักของกราฟ inertia ต้องใช้ตาคนอ่าน ตัดสินใจอัตโนมัติไม่ได้
    silhouette ให้ตัวเลขเดียวเทียบกันตรง ๆ ได้ และรายงานให้ดูย้อนหลังได้ด้วยว่าแต่ละ k ได้เท่าไร

    เงื่อนไขเพิ่ม: รับเฉพาะ k ที่ทำให้ **ทุกโซนมีจุดอย่างน้อย MIN_POINTS_PER_ZONE**
    เพราะ silhouette สนใจแค่รูปทรงของกลุ่ม ไม่สนว่ากลุ่มนั้นมีข้อมูลพอจะคิดสถิติไหม
    ปล่อยไว้จะได้ k สูง ๆ ที่สวยบนกระดาษแต่มีโซนละ 3 คิล ซึ่งเอาไปสรุปอะไรไม่ได้
    """
    k_max = min(k_max, len(xy) - 1)
    scores = []
    for k in range(k_min, k_max + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE)
        labels = km.fit_predict(xy)
        if len(set(labels)) < 2:
            continue
        smallest = int(np.bincount(labels, minlength=k).min())
        scores.append(
            {
                "k": k,
                "silhouette": round(float(silhouette_score(xy, labels)), 4),
                "inertia": round(float(km.inertia_), 1),
                "smallest_zone": smallest,
                "usable": smallest >= MIN_POINTS_PER_ZONE,
            }
        )
    usable = [s for s in scores if s["usable"]]
    if not usable:
        raise SystemExit(
            f"ไม่มีจำนวนโซนไหนเลยที่ทุกโซนมีจุดถึง {MIN_POINTS_PER_ZONE} — ข้อมูลยังน้อยเกินไป"
        )
    best = max(usable, key=lambda s: s["silhouette"])
    return best["k"], scores


def grid_baseline(xy: np.ndarray, n_zones: int) -> float:
    """
    baseline สำหรับเทียบ: ตีกริดสี่เหลี่ยมทับแมพให้ได้จำนวนช่องใกล้เคียงกับจำนวนโซนของ KMeans
    แล้ววัด silhouette ด้วยไม้บรรทัดอันเดียวกัน

    มีไว้ตอบคำถามว่า "จะใช้ ML ทำไม ตีกริดเอาก็ได้" — ถ้าตัวเลขไม่ชนะกริด ก็ควรใช้กริด
    """
    side = max(2, int(round(np.sqrt(n_zones))))
    xs, ys = xy[:, 0], xy[:, 1]
    # +1e-9 กันกรณีจุดอยู่ขอบขวาสุดพอดีแล้วหลุดออกนอกช่องสุดท้าย
    cx = np.floor((xs - xs.min()) / (np.ptp(xs) + 1e-9) * side).clip(0, side - 1)
    cy = np.floor((ys - ys.min()) / (np.ptp(ys) + 1e-9) * side).clip(0, side - 1)
    labels = (cy * side + cx).astype(int)
    if len(set(labels)) < 2:
        return float("nan")
    return round(float(silhouette_score(xy, labels)), 4)


# ---------------------------------------------------------------------------
# สร้างโซน
# ---------------------------------------------------------------------------
def name_zone(places: list[str | None], fallback: str) -> str:
    """
    ตั้งชื่อโซนจาก callout ในเกมที่พบบ่อยที่สุดในกลุ่มนั้น

    ตัวจับกลุ่มไม่รู้จักชื่อสถานที่ — มันเห็นแค่ตัวเลขพิกัด ชื่อจึงเป็นแค่ "ป้ายกำกับ"
    ที่ติดทีหลังให้โค้ชอ่านออก ไม่ได้เอาไปใช้ตอนแบ่งกลุ่ม (ถ้าเอาไปใช้ก็ไม่ใช่ unsupervised แล้ว)
    """
    known = [p for p in places if p]
    if not known:
        return fallback
    top, count = Counter(known).most_common(1)[0]
    share = count / len(known)
    # ถ้า callout ยอดนิยมกินไม่ถึงครึ่ง แปลว่าโซนนี้คร่อมหลายพื้นที่ บอกไว้ตรง ๆ ดีกว่าตั้งชื่อมั่ว
    return top if share >= 0.5 else f"{top} +"


def hotspots(points: np.ndarray, eps: float = 220.0, min_samples: int = 6) -> list[dict]:
    """
    หา "จุดตายซ้ำ ๆ" ด้วย DBSCAN

    ใช้คนละตัวกับที่แบ่งโซนเพราะตอบคนละคำถาม: KMeans บังคับให้ทุกจุดสังกัดโซนใดโซนหนึ่ง
    (เหมาะกับการแบ่งพื้นที่ให้ครบทั้งแมพ) ส่วน DBSCAN ทิ้งจุดที่กระจัดกระจายเป็น noise ได้
    จึงเหลือเฉพาะจุดที่คนตายซ้ำจริง ๆ — เป็นตำแหน่งที่โค้ชเอาไปสั่งลูกทีมได้เลย

    eps 220 หน่วยเกม ≈ 4 เมตร คือระยะที่ยังนับว่า "ตายที่เดียวกัน" ในเกม
    """
    if len(points) < min_samples:
        return []
    db = DBSCAN(eps=eps, min_samples=min_samples).fit(points)
    out = []
    for label in sorted(set(db.labels_)):
        if label == -1:  # noise — จุดที่ไม่ได้เกาะกลุ่มกับใคร
            continue
        member = points[db.labels_ == label]
        out.append(
            {
                "x": round(float(member[:, 0].mean()), 1),
                "y": round(float(member[:, 1].mean()), 1),
                "deaths": int(len(member)),
                "radius": round(float(np.percentile(np.linalg.norm(member - member.mean(axis=0), axis=1), 80)), 1),
            }
        )
    return sorted(out, key=lambda h: -h["deaths"])


def build_zones(deaths: list[dict], k: int | None) -> dict:
    xy = np.array([[d["x"], d["y"]] for d in deaths], dtype=float)

    if k is None:
        k, k_scores = choose_k(xy)
        chosen_by = "silhouette"
    else:
        k_scores = []
        chosen_by = "ผู้ใช้กำหนดเอง"

    km = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE)
    labels = km.fit_predict(xy)
    silhouette = round(float(silhouette_score(xy, labels)), 4) if len(set(labels)) > 1 else None

    zones = []
    for idx in range(k):
        member_mask = labels == idx
        member = xy[member_mask]
        if len(member) < MIN_POINTS_PER_ZONE:
            continue
        places = [deaths[i]["place"] for i in np.flatnonzero(member_mask)]
        centroid = km.cluster_centers_[idx]
        zones.append(
            {
                "zone_id": int(idx),
                "name": name_zone(places, f"โซน {idx + 1}"),
                "centroid": [round(float(centroid[0]), 1), round(float(centroid[1]), 1)],
                "deaths": int(len(member)),
                # กรอบสี่เหลี่ยมของจุดในโซน ใช้วาดขอบเขตคร่าว ๆ บนหน้าเว็บ
                "bbox": [
                    round(float(member[:, 0].min()), 1), round(float(member[:, 1].min()), 1),
                    round(float(member[:, 0].max()), 1), round(float(member[:, 1].max()), 1),
                ],
                # รัศมีที่ครอบจุดในโซนไว้ 80% ใช้วาดวงกลมแทนกรอบเมื่ออยากได้รูปนุ่มกว่า
                "radius": round(float(np.percentile(np.linalg.norm(member - centroid, axis=1), 80)), 1),
                "hotspots": hotspots(member),
            }
        )

    dropped = k - len(zones)
    return {
        "zones": sorted(zones, key=lambda z: -z["deaths"]),
        "model": {
            "algorithm": "KMeans",
            "k": k,
            "k_chosen_by": chosen_by,
            "silhouette": silhouette,
            "grid_baseline_silhouette": grid_baseline(xy, k),
            "k_search": k_scores,
            "zones_dropped_too_small": dropped,
            "min_points_per_zone": MIN_POINTS_PER_ZONE,
            "random_state": RANDOM_STATE,
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="แบ่งแมพเป็นโซนการปะทะด้วย unsupervised learning")
    ap.add_argument("map_name", help="ชื่อแมพ เช่น de_dust2")
    ap.add_argument("-i", "--input", default="backend/data/matches", help="โฟลเดอร์ normalized JSON")
    ap.add_argument("-o", "--out", default="backend/data/zones", help="โฟลเดอร์ปลายทางของไฟล์โซน")
    ap.add_argument("--k", type=int, default=None, help="บังคับจำนวนโซน (ปกติเลือกด้วย silhouette)")
    ap.add_argument("--summary", action="store_true", help="แสดงผลอย่างเดียว ไม่เขียนไฟล์")
    args = ap.parse_args()

    match_dir = Path(args.input)
    if not match_dir.is_dir():
        print(f"ไม่พบโฟลเดอร์ {match_dir}", file=sys.stderr)
        return 1

    print(f"[zones] {args.map_name} — อ่านจาก {match_dir}")
    deaths, sources = load_deaths(match_dir, args.map_name)
    if not deaths:
        print(f"ไม่พบข้อมูลการตายของแมพ {args.map_name} — โหลด .dem ของแมพนี้เข้ามาก่อน", file=sys.stderr)
        return 1
    if len(deaths) < K_MIN * MIN_POINTS_PER_ZONE:
        print(
            f"มีจุดตายแค่ {len(deaths)} จุด น้อยเกินกว่าจะแบ่ง {K_MIN} โซนได้อย่างมีความหมาย "
            f"(ต้องการอย่างน้อย {K_MIN * MIN_POINTS_PER_ZONE}) — โหลดแมตช์เพิ่มก่อน",
            file=sys.stderr,
        )
        return 1

    result = build_zones(deaths, args.k)
    model = result["model"]

    doc = {
        "schema_version": SCHEMA_VERSION,
        "map_name": args.map_name,
        "fitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fit_from": {"matches": len(sources), "deaths": len(deaths), "external_ids": sources},
        "model": model,
        "zones": result["zones"],
    }

    print(f"  แมตช์  : {len(sources)} แมตช์, จุดตาย {len(deaths)} จุด")
    print(f"  โซน    : {len(result['zones'])} โซน (k={model['k']}, เลือกโดย {model['k_chosen_by']})")
    print(f"  คุณภาพ : silhouette {model['silhouette']} vs กริดตายตัว {model['grid_baseline_silhouette']}")
    if model["zones_dropped_too_small"]:
        print(f"  ตัดทิ้ง : {model['zones_dropped_too_small']} โซนที่มีจุดน้อยกว่า {MIN_POINTS_PER_ZONE}")
    print()
    print("  โซน                    จุดตาย  hotspot  ศูนย์กลาง")
    for z in result["zones"]:
        print(f"  {z['name']:<22} {z['deaths']:>6}  {len(z['hotspots']):>7}  ({z['centroid'][0]:.0f}, {z['centroid'][1]:.0f})")

    if args.summary:
        return 0

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.map_name}.json"
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ เขียน {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
