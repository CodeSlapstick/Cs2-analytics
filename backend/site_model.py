# -*- coding: utf-8 -*-
"""
backend/site_model.py — ใช้โมเดลทายไซต์ที่ research/site_ml.py เทรนไว้

โมเดลเป็น logistic regression หนึ่งชุดต่อหนึ่งวินาที เก็บเป็น JSON (น้ำหนักต่อ callout + intercept)
จึงคำนวณได้ด้วยเลขคณิตธรรมดา ไม่ต้องมี sklearn ตอนรันเซิร์ฟเวอร์ และเปิดไฟล์อ่านน้ำหนักได้เลย

ไฟล์ถูกอ่านครั้งเดียวแล้วเก็บในหน่วยความจำ (อ่านใหม่เฉพาะเมื่อไฟล์ถูกเขียนทับ) — เหมือน grid_ml1.json
ยังไม่เคยรัน research/site_ml.py = ไม่มีไฟล์ = API ตอบว่า available: false ไม่ใช่พัง
"""
import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_JSON = Path(os.environ.get("SITE_MODEL_JSON", ROOT / "output" / "site_model.json"))

_cache: tuple[float, dict] | None = None


def load_site_model(path: Path = SITE_JSON) -> dict | None:
    """โมเดลทั้งก้อนแบบ cache — None ถ้ายังไม่เคยเทรน"""
    global _cache
    try:
        stamp = path.stat().st_mtime
    except OSError:
        _cache = None
        return None
    if _cache and _cache[0] == stamp:
        return _cache[1]
    model = json.loads(path.read_text(encoding="utf-8"))
    _cache = (stamp, model)
    return model


def available_times(model: dict) -> list[int]:
    return sorted(int(t) for t in model.get("models", {}))


def predict_a(model: dict, t: int, counts: dict[str, int]) -> float | None:
    """โอกาสที่บอมบ์จะไปลงไซต์ A ณ วินาทีที่ t — None ถ้าไม่มีโมเดลของวินาทีนั้น

    counts = จำนวน T ที่ยังไม่ตายยืนอยู่แต่ละ callout (callout ที่โมเดลไม่รู้จักถูกมองข้าม
    ไม่ใช่ทำให้พัง — แมพเดียวกันคนละแพตช์อาจมีชื่อจุดใหม่โผล่มา)
    """
    m = model.get("models", {}).get(str(t))
    if not m:
        return None
    z = m["intercept"] + sum(w * counts.get(place, 0) for place, w in m["coef"].items())
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def accuracy_at(model: dict, t: int) -> float | None:
    m = model.get("models", {}).get(str(t))
    return float(m["accuracy"]) if m else None


def read_at(series: list[dict], truth: str | None, confident: float = 0.80) -> int | None:
    """วินาทีแรกที่โมเดล "อ่านออก" = มั่นใจถึงเกณฑ์ และมั่นใจไปทางไซต์ที่เกิดขึ้นจริง

    ไม่มีเฉลย (รอบที่ไม่ได้วางบอมบ์) = ตอบไม่ได้ ไม่ใช่เดาให้
    """
    if truth not in ("A", "B"):
        return None
    for point in series:
        p = point["p_a"] if truth == "A" else 1 - point["p_a"]
        if p >= confident:
            return int(point["t"])
    return None
