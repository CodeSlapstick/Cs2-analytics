#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ยัดข้อมูลกับภาพเรดาร์เข้าไปในเทมเพลตใน frontend/ แล้วได้หน้าเว็บไฟล์เดียว

    python frontend/build.py                 # ทุกหน้า -> output/*.html
    python frontend/build.py map             # เฉพาะหน้าแผนที่รวม
    python frontend/build.py rounds          # เฉพาะหน้ารีวิวรายรอบ
    python frontend/build.py --body-only     # ไม่ครอบ <html><head> (เอาไปวางเป็น artifact)

ต้องมีข้อมูลก่อน
    map     <- python pipeline/grid_ml.py       สร้าง output/grid_ml.json
    rounds  <- python pipeline/round_review.py  สร้าง output/round_review.json

ทำไมต้องยัดรวมเป็นไฟล์เดียว
    ถ้าให้หน้าเว็บ fetch json เอง เบราว์เซอร์จะบล็อกด้วย CORS ตอนเปิดแบบ file://
    หน้าจะว่างเปล่าโดยไม่ขึ้น error ให้เห็น ต้องตั้งเว็บเซิร์ฟเวอร์ถึงจะดูได้
    ยัดรวมไปเลยจึงส่งไฟล์เดียวให้ใครเปิดที่ไหนก็ได้ แลกกับไฟล์ใหญ่ขึ้นราว 100 KB
"""
import argparse
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
OUT = ROOT / "output"

# ชื่อหน้า -> (เทมเพลต, ไฟล์ข้อมูล, ชื่อไฟล์ผลลัพธ์)
PAGES = {
    "map": ("template.html", "grid_ml.json", "index"),
    "rounds": ("rounds.template.html", "round_review.json", "rounds"),
}

# โครงเอกสารสำหรับไฟล์ที่เปิดเองในเครื่อง
# (ตอนเอาไปวางเป็น artifact ไม่ต้องมี เพราะฝั่งนั้นครอบให้อยู่แล้ว)
SKELETON_HEAD = """<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { color-scheme: light dark; }
  body { margin: 0; }
  img { max-width: 100%; }
</style>
"""
SKELETON_TAIL = "\n</html>\n"

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def build(page: str, body_only: bool, out_path: Path | None) -> None:
    tpl_name, data_name, stem = PAGES[page]
    tpl = FRONTEND / tpl_name
    data = OUT / data_name

    if not data.exists():
        sys.exit(f"ไม่พบ {data} — ดูหัวไฟล์นี้ว่าต้องรันสคริปต์ไหนก่อน")

    payload = json.loads(data.read_text(encoding="utf-8"))

    # ภาพเรดาร์: path ใน json เขียนเป็น /maps/... ซึ่งอ้างจากโฟลเดอร์ assets
    img_path = ROOT / "assets" / payload["radar"]["image"].lstrip("/")
    if not img_path.exists():
        sys.exit(f"ไม่พบภาพเรดาร์ {img_path}")
    radar_uri = "data:image/webp;base64," + base64.b64encode(img_path.read_bytes()).decode()

    # separators แบบไม่มีช่องว่าง ประหยัดไปได้หลายสิบ KB
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # กัน "</script>" ที่อาจโผล่มาในชื่อผู้เล่นหรือ callout ไปปิดแท็กก่อนเวลา
    blob = blob.replace("</", "<\\/")

    html = tpl.read_text(encoding="utf-8")
    for token, value in (("__PAYLOAD__", blob), ("__RADAR__", radar_uri)):
        if token not in html:
            sys.exit(f"ไม่เจอที่ว่าง {token} ใน {tpl.name}")
        html = html.replace(token, value)

    if not body_only:
        html = SKELETON_HEAD + html + SKELETON_TAIL

    out = out_path or (OUT / (stem + ("-artifact.html" if body_only else ".html")))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"เซฟแล้ว {out}  ({out.stat().st_size / 1024:.0f} KB)")


def main() -> None:
    ap = argparse.ArgumentParser(description="สร้างหน้าเว็บไฟล์เดียวจากเทมเพลต + ข้อมูล")
    ap.add_argument("page", nargs="?", choices=sorted(PAGES), help="ไม่ใส่ = ทำทุกหน้า")
    ap.add_argument("--body-only", action="store_true",
                    help="ไม่ต้องครอบ <html><head> (ใช้ตอนเอาไปวางเป็น artifact)")
    ap.add_argument("--out", type=Path, help="ชื่อไฟล์ผลลัพธ์ (ใช้ได้เมื่อระบุหน้าเดียว)")
    args = ap.parse_args()

    if args.out and not args.page:
        sys.exit("--out ใช้ได้ตอนระบุหน้าเดียวเท่านั้น")

    for page in ([args.page] if args.page else sorted(PAGES)):
        build(page, args.body_only, args.out)


if __name__ == "__main__":
    main()
