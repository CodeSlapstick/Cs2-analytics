#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
import_overviews.py — เติมค่าปรับเทียบเรดาร์ของทุกแมพลง assets/radars.json จากไฟล์เกม CS2 โดยตรง

    python research/import_overviews.py                 ดูว่าจะเปลี่ยนอะไรบ้าง (ไม่เขียนไฟล์)
    python research/import_overviews.py --write         เขียน radars.json + คัดลอกภาพเรดาร์ที่ขาด
    python research/import_overviews.py --vpk "D:/.../game/csgo/pak01_dir.vpk"

ทำไมต้องมีสคริปต์นี้
    radars.json เขียนไว้ว่า "อย่าเดาค่าเอง และอย่าหาค่าด้วยการ fit จากข้อมูล"
    ค่าที่ถูกอยู่ในไฟล์ resource/overviews/<map>.txt ของเกม ซึ่งถูกแพ็กไว้ใน pak01_dir.vpk
    สคริปต์นี้อ่านไฟล์นั้นตรง ๆ (ต้องมีเกม CS2 ในเครื่อง + pip install vpk) แล้วลอกค่ามาทั้งชุด
    แพตช์เกมเปลี่ยนแมพเมื่อไร ก็รันใหม่ได้ทันที

สิ่งที่เขียนลงแต่ละแมพ
    pos_x / pos_y / scale   ค่าทางการจากไฟล์เกม (ทับค่าเดิมได้ ถ้าเกมเปลี่ยน)
    image / size / grid     ภาพ /maps/<map>.png ขนาดตามไฟล์จริง กริด 300 หน่วยเท่าแมพอื่น
    sites                   ศูนย์กลางไซต์ A/B — เก็บค่าเดิมไว้ถ้ามี (ค่าเดิมมาจากค่าเฉลี่ยจุดตายจริง ดีกว่า)
                            แมพใหม่ใช้ตำแหน่งไอคอนไซต์ bombA/bombB ในไฟล์เกมเดียวกัน (สัดส่วนของภาพ -> พิกัดเกม)

ภาพเรดาร์มาจาก images/maps/cs2/radars/ (ชุดภาพ 1024px จากเกม) — ตรวจแล้วว่ากรอบภาพตรงกับค่าในไฟล์เกม:
    Mirage จุดตายจริง 7,571 จุดตกบนพื้นที่เดินได้ 99.7% ทั้งภาพเดิมและภาพชุดนี้ · Dust2 100% ทั้งคู่
ภาพที่มีอยู่แล้วใน assets/maps จะถูกแทนเฉพาะเมื่อรูปร่างพื้นที่เดินได้ต่างกันจริง (แมพถูกแก้ในแพตช์)

ข้อจำกัด: แมพสองชั้น (Nuke / Train / Vertigo) ใช้ภาพชั้นบนภาพเดียว — จุดของชั้นล่างวาดทับบนภาพชั้นบน
แมพที่ยังไม่มีเดโมในระบบ ตรวจด้วย check_radar.py ไม่ได้ จนกว่าจะมีคนอัปโหลดเดโมของแมพนั้น
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
RADARS = ROOT / "assets" / "radars.json"
MAPS_DIR = ROOT / "assets" / "maps"
SOURCE_IMAGES = ROOT / "images" / "maps" / "cs2" / "radars"
GRID = 300
# ไฟล์ overview ที่ไม่ใช่แมพแข่ง หรือเป็นรุ่นย่อย/กลางคืน/2v2 ของแมพเดิม
SKIP = re.compile(r"^(ar_|rush_|workshop_)|_(v\d|night|s\d|2v2)$")
VPK_GUESSES = [
    Path(p) / "steamapps/common/Counter-Strike Global Offensive/game/csgo/pak01_dir.vpk"
    for p in ("C:/SteamLibrary", "D:/SteamLibrary", "E:/SteamLibrary",
              "C:/Program Files (x86)/Steam", "C:/Program Files/Steam", "D:/Steam")
]
KV = re.compile(r'"(\w+)"\s+"([^"]*)"')


def parse_overview(text: str) -> dict[str, str]:
    """"key" "value" ทุกคู่ในไฟล์ (ตัดคอมเมนต์ // ทิ้งก่อน) — ไม่ต้องใช้ parser KeyValues เต็มรูป"""
    body = "\n".join(line.split("//", 1)[0] for line in text.splitlines())
    return {k: v for k, v in KV.findall(body)}


def alpha_mask(path: Path, size: int) -> np.ndarray:
    im = Image.open(path).convert("RGBA")
    if im.size != (size, size):
        im = im.resize((size, size))
    return np.asarray(im)[:, :, 3] > 20


def same_shape(a: Path, b: Path) -> float:
    """IoU ของพื้นที่เดินได้สองภาพ — 1.0 = รูปร่างแมพเหมือนกัน (สีต่างกันได้)"""
    ma, mb = alpha_mask(a, 1024), alpha_mask(b, 1024)
    return float((ma & mb).sum() / max(1, (ma | mb).sum()))


def fix_readme(lines: list[str]) -> list[str]:
    """_readme เคยถูกบันทึกผิดเป็นตัวอักษรละรายการ (list("...")) — ต่อกลับเป็นบรรทัดเดียว + ชี้มาที่สคริปต์นี้"""
    out: list[str] = []
    run: list[str] = []
    for x in [*lines, None]:                   # ตัวปิดท้าย ให้ run สุดท้ายถูกเก็บ
        if x is not None and len(x) <= 1:
            run.append(x)
            continue
        if len(run) > 3:                       # สายตัวอักษรที่หลุดมา
            out.append("".join(run).strip(" ·"))
        else:
            out.extend(run)
        run = []
        if x is not None:
            out.append(x)
    note = "เพิ่ม/อัปเดตหลายแมพพร้อมกันจากไฟล์เกม: python research/import_overviews.py --write"
    return out if note in out else [*out, note]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--vpk", type=Path, help="pak01_dir.vpk ของ CS2 (ไม่ใส่ = หาเองจากที่ติดตั้งทั่วไป)")
    ap.add_argument("--write", action="store_true", help="เขียนไฟล์จริง (ไม่ใส่ = แค่แสดงผล)")
    args = ap.parse_args()

    try:
        import vpk  # noqa: PLC0415 — เครื่องมือเสริม ไม่ใช่ของที่ระบบจริงต้องมี
    except ImportError:
        sys.exit("ต้องติดตั้งก่อน: pip install vpk")
    path = args.vpk or next((p for p in VPK_GUESSES if p.exists()), None)
    if not path or not path.exists():
        sys.exit("หา pak01_dir.vpk ของ CS2 ไม่เจอ — ระบุเองด้วย --vpk")
    pak = vpk.open(str(path))

    data = json.loads(RADARS.read_text(encoding="utf-8"))
    readme = data.pop("_readme", [])
    changes: list[str] = []
    for name in sorted(n for n in pak if n.startswith("resource/overviews/") and n.endswith(".txt")):
        m = Path(name).stem
        src = SOURCE_IMAGES / f"{m}.png"
        if SKIP.search(m) or not src.exists():
            continue
        ov = parse_overview(pak[name].read().decode("utf-8", "replace"))
        if not {"pos_x", "pos_y", "scale"} <= ov.keys():
            continue
        size = Image.open(src).size[0]
        pos_x, pos_y, scale = float(ov["pos_x"]), float(ov["pos_y"]), float(ov["scale"])
        old = data.get(m, {})
        entry = {
            "image": f"/maps/{m}.png", "size": size,
            "pos_x": int(pos_x) if pos_x.is_integer() else pos_x,
            "pos_y": int(pos_y) if pos_y.is_integer() else pos_y,
            "scale": scale, "grid": old.get("grid", GRID),
            "source_note": old.get("source_note") or (
                f"ค่าทางการจาก resource/overviews/{m}.txt ของ CS2 (research/import_overviews.py) — "
                "ยังไม่มีเดโมของแมพนี้ในระบบ ตรวจด้วย check_radar.py ได้เมื่อมีคนอัปโหลด"),
        }
        if "sites" in old:
            entry["sites"] = old["sites"]
        elif "bombA_x" in ov and "bombB_x" in ov:
            span = size * scale
            entry["sites"] = {
                s: [round(pos_x + float(ov[f"bomb{s}_x"]) * span), round(pos_y - float(ov[f"bomb{s}_y"]) * span)]
                for s in ("A", "B")
            }
            entry["sites"]["source_note"] = f"ตำแหน่งไอคอนไซต์ bombA/bombB ใน resource/overviews/{m}.txt ของเกม"
        if old and any(old.get(k) != entry[k] for k in ("pos_x", "pos_y", "scale", "size")):
            changes.append(f"{m}: ค่าปรับเทียบเปลี่ยน {old.get('pos_x')},{old.get('pos_y')},{old.get('scale')} -> "
                           f"{entry['pos_x']},{entry['pos_y']},{entry['scale']}")
        elif not old:
            changes.append(f"{m}: เพิ่มใหม่ pos=({entry['pos_x']}, {entry['pos_y']}) scale={entry['scale']}")
        data[m] = entry

        dest = MAPS_DIR / f"{m}.png"
        if not dest.exists():
            changes.append(f"{m}: คัดลอกภาพเรดาร์ใหม่")
            if args.write:
                shutil.copyfile(src, dest)
        else:
            iou = same_shape(src, dest)
            if iou < 0.99:
                changes.append(f"{m}: ภาพเดิมเป็นแมพรุ่นเก่า (รูปร่างตรงกัน {iou:.1%}) -> ใช้ภาพชุดใหม่")
                if args.write:
                    shutil.copyfile(src, dest)

    maps = {k: data[k] for k in sorted(data)}
    out = {"_readme": fix_readme(readme), **maps}
    print("\n".join(changes) or "ไม่มีอะไรเปลี่ยน")
    print(f"\nรวม {len(maps)} แมพใน radars.json")
    if args.write:
        RADARS.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("เขียนแล้ว:", RADARS)
    else:
        print("(ยังไม่เขียน — ใส่ --write เพื่อบันทึก)")


if __name__ == "__main__":
    main()
