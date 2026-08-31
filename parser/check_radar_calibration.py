#!/usr/bin/env python3
"""
ตรวจว่าค่าปรับเทียบภาพเรดาร์ของแมพหนึ่งถูกต้องไหม

    python parser/check_radar_calibration.py de_dust2
    python parser/check_radar_calibration.py de_dust2 -o /tmp/check.png

วิธีตรวจ: วาดจุดที่มีคนตายจริงทับภาพเรดาร์ โดยระบายสีตาม callout ในเกม
(LongA, BombsiteB, Middle, …) แล้ว **เปิดภาพผลลัพธ์ดูด้วยตา** — ถ้าค่าถูก จุดที่
ติดป้ายว่า LongA จะไปกองอยู่ที่ทางเดิน Long จริง ถ้าค่าผิด จุดจะกระจายมั่วหรือ
หลุดออกนอกกรอบภาพ

ทำไมต้องตรวจด้วยตา ไม่ตรวจด้วยเลข: เราไม่มี "คำตอบที่ถูก" ของตำแหน่ง callout
บนภาพให้เทียบอัตโนมัติ สิ่งที่เรามีคือความรู้ว่าแมพหน้าตาเป็นยังไง ซึ่งอยู่ในหัวคน
สคริปต์นี้จึงทำหน้าที่แค่เอาสองอย่างมาวางซ้อนกันให้ตัดสินง่าย ๆ

สคริปต์รายงานตัวเลขที่ตรวจอัตโนมัติได้ให้ด้วย (จุดที่ตกนอกกรอบภาพ) ซึ่งจับได้
เฉพาะกรณีที่ผิดแบบมโหฬาร — ค่าที่ผิดพอประมาณจะยังตกในกรอบทั้งหมด ตัวเลขนี้จึง
เป็นแค่ด่านแรก ไม่ใช่ข้อสรุป

ค่าปรับเทียบอ่านจาก assets/radars.json ซึ่งเป็นแหล่งความจริงแหล่งเดียว
ของทั้งโปรเจกต์ — เพิ่มแมพใหม่แก้ที่ไฟล์นั้นที่เดียว
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError as exc:  # pragma: no cover
    print(f"ต้องติดตั้ง Pillow ก่อน: pip install -r parser/requirements.txt ({exc})", file=sys.stderr)
    raise SystemExit(1)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

RADARS_PATH = Path("assets/radars.json")
ASSETS_DIR = Path("assets")

# สีของ callout ที่พบบ่อย — ที่เหลือเป็นสีเทา
# ชื่อ callout ซ้ำกันได้ข้ามแมพ (BombsiteA/B มีทุกแมพ) จึงใช้ตารางเดียวรวมทุกแมพได้
PLACE_COLORS = {
    # de_mirage
    "Apartments": (255, 120, 200),
    "Catwalk": (170, 255, 60),
    "Connector": (120, 220, 220),
    "PalaceInterior": (255, 200, 120),
    "Underpass": (140, 140, 255),
    "Jungle": (60, 220, 160),
    "Truck": (230, 140, 255),
    "Stairs": (200, 200, 90),
    # de_dust2
    "LongA": (255, 60, 60),
    "LongDoors": (255, 110, 90),
    "BombsiteA": (255, 140, 0),
    "BombsiteB": (60, 255, 120),
    "Middle": (80, 160, 255),
    "MidDoors": (180, 120, 255),
    "ExtendedA": (255, 230, 60),
    "CTSpawn": (120, 220, 220),
    "UpperTunnel": (255, 120, 200),
    "ShortStairs": (170, 255, 60),
}


def load_deaths(match_dir: Path, map_name: str) -> list[tuple[float, float, str]]:
    out = []
    for path in sorted(match_dir.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("match", {}).get("map_name") != map_name:
            continue
        for ev in doc.get("events", []):
            if ev.get("type") != "kill" or ev.get("victim_x") is None:
                continue
            place = (ev.get("meta") or {}).get("victim_place") or "?"
            out.append((float(ev["victim_x"]), float(ev["victim_y"]), place))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="ตรวจค่าปรับเทียบภาพเรดาร์ด้วยข้อมูลจริง")
    ap.add_argument("map_name")
    ap.add_argument("-i", "--input", default="data/matches")
    ap.add_argument("-o", "--out", default=None, help="ไฟล์ภาพผลลัพธ์ (ดีฟอลต์ <map>_calibration.png)")
    ap.add_argument("--upscale", type=int, default=1, help="ขยายภาพก่อนวาด ใช้ตอนภาพต้นฉบับเล็ก")
    args = ap.parse_args()

    if not RADARS_PATH.exists():
        print(f"ไม่พบ {RADARS_PATH}", file=sys.stderr)
        return 1
    cal = json.loads(RADARS_PATH.read_text(encoding="utf-8")).get(args.map_name)
    if not cal:
        print(f"ยังไม่มีค่าปรับเทียบของ {args.map_name} — เพิ่มใน {RADARS_PATH} ก่อน", file=sys.stderr)
        return 1

    # path ในไฟล์ config เขียนแบบอ้างจากรากของโฟลเดอร์ assets/
    img_path = ASSETS_DIR / cal["image"].lstrip("/")
    if not img_path.exists():
        print(f"ไม่พบภาพเรดาร์ {img_path}", file=sys.stderr)
        return 1

    deaths = load_deaths(Path(args.input), args.map_name)
    if not deaths:
        print(f"ไม่พบข้อมูลการตายของแมพ {args.map_name}", file=sys.stderr)
        return 1

    im = Image.open(img_path).convert("RGB")
    w, h = im.size
    # scale ใน config อ้างกับขนาดภาพที่ระบุไว้ ถ้าไฟล์จริงคนละขนาดต้องปรับตามสัดส่วน
    scale = cal["scale"] * (cal.get("size", w) / w)
    up = max(1, args.upscale)
    im = im.resize((w * up, h * up), Image.NEAREST)
    draw = ImageDraw.Draw(im)

    outside = 0
    places: Counter[str] = Counter()
    for gx, gy, place in deaths:
        px = (gx - cal["pos_x"]) / scale * up
        py = (cal["pos_y"] - gy) / scale * up
        if not (0 <= px < w * up and 0 <= py < h * up):
            outside += 1
        places[place] += 1
        color = PLACE_COLORS.get(place, (190, 190, 190))
        rad = 4 * up if up > 1 else 3
        draw.ellipse([px - rad, py - rad, px + rad, py + rad], fill=color, outline=(0, 0, 0))

    out_path = Path(args.out or f"{args.map_name}_calibration.png")
    im.save(out_path)

    print(f"ภาพ {w}×{h} · scale {scale:.2f} หน่วยเกม/พิกเซล")
    print(f"จุดตาย {len(deaths)} จุด · ตกนอกกรอบภาพ {outside} จุด"
          + ("  ← ค่าปรับเทียบผิดแน่นอน" if outside else "  ✓ ผ่านด่านแรก"))
    print("\ncallout ที่พบ (เทียบสีในภาพ):")
    for place, n in places.most_common(10):
        c = PLACE_COLORS.get(place)
        print(f"  {place:<14} {n:>4} จุด" + (f"  RGB{c}" if c else "  (เทา)"))
    print(f"\n✓ เขียน {out_path} — เปิดดูว่าจุดแต่ละสีตกตรงพื้นที่ที่ควรอยู่ไหม")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
