# -*- coding: utf-8 -*-
"""กันไม่ให้ "เดโมที่ผู้ใช้อัปโหลด" หลุดเข้า "ชุดข้อมูลที่ใช้เทรนโมเดล"

เคยเป็นแบบนี้มาก่อน: ทั้งสองอย่างใช้โฟลเดอร์ demos/ ร่วมกัน และ research/demoparser.py
อ่าน demos/*.dem ทั้งหมด  แปลว่าวันไหนมีคนรัน demoparser เพื่ออัปเดตชุดข้อมูล
แมตช์ของผู้ใช้จะถูกรวมเข้า data/all_kills.csv เงียบ ๆ แล้ว grid_ml1 ก็เทรนจากมันต่อ
ไม่มี error ไม่มีคำเตือน — เทสต์ชุดนี้คือสิ่งเดียวที่จะส่งเสียงถ้ามีใครเผลอรวมกลับมาอีก
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


def _const_in_source(path: Path, name: str) -> str:
    """อ่านค่าคงที่จากซอร์สโดยไม่ import (research/demoparser.py ลาก awpy กับ polars มาด้วย)"""
    m = re.search(rf"^{name}\s*=\s*(.+)$", path.read_text(encoding="utf-8"), re.MULTILINE)
    assert m, f"ไม่พบ {name} ใน {path.name}"
    return m.group(1).strip()


def test_upload_folder_and_training_folder_are_not_the_same():
    """โฟลเดอร์ที่ระบบเขียนไฟล์อัปโหลดลงไป ต้องไม่ใช่โฟลเดอร์ที่ demoparser อ่านไปทำชุดเทรน"""
    from backend import app as appmod

    upload = appmod.DEMOS_DIR.resolve()
    training_expr = _const_in_source(ROOT / "research" / "demoparser.py", "DEMO_DIR")
    assert '"reference"' in training_expr, (
        f"research/demoparser.py อ่านจาก {training_expr} — ต้องชี้ที่ demos/reference/ เท่านั้น")
    training = (ROOT / "demos" / "reference").resolve()

    assert upload != training
    assert training not in upload.parents, "โฟลเดอร์อัปโหลดอยู่ข้างในโฟลเดอร์ชุดเทรน — เดโมผู้ใช้จะถูกกวาดเข้าชุดเทรน"
    assert upload not in training.parents, "โฟลเดอร์ชุดเทรนอยู่ข้างในโฟลเดอร์อัปโหลด"


def test_api_writes_where_the_worker_reads():
    """ถ้าสองที่นี้ไม่ตรงกัน worker จะหาไฟล์ที่เพิ่งอัปโหลดไม่เจอ (แยกโฟลเดอร์แล้วต้องแยกให้ครบทั้งคู่)"""
    from backend import app as appmod
    from backend import jobs

    assert appmod.DEMOS_DIR.resolve() == jobs.DEMOS_DIR.resolve()


def test_new_matches_default_to_upload_not_reference():
    """ค่าตั้งต้นของ matches.source ต้องเป็น 'upload' — แมตช์ที่ไม่มีใครยืนยันห้ามถูกนับเป็นชุดเทรนเอง"""
    from backend.models import Match

    col = Match.__table__.c.source
    assert col.nullable is False
    assert "upload" in str(col.server_default.arg)


def test_every_upload_records_where_it_came_from():
    """โหมดเยี่ยมชมอัปโหลดได้ แต่ทุกไฟล์ต้องติดป้ายที่มา — ไม่งั้นคัด "ของใครเข้าชุดเทรน" ไม่ได้

    uploader_type บังคับ NOT NULL และไม่มีค่าตั้งต้น: ถ้าวันหน้ามีทางเข้าใหม่แล้วลืมระบุที่มา
    คำสั่ง INSERT จะพังทันที ดีกว่าปล่อยให้แถวนั้นติดป้ายผิดแล้วไหลเข้าชุดเทรน
    """
    from backend.models import Match

    col = Match.__table__.c.uploader_type
    assert col.nullable is False
    assert col.server_default is None, "uploader_type ห้ามมีค่าตั้งต้น — ที่มาต้องถูกระบุตอน INSERT เสมอ"
    # และไม่ว่าใครอัป แถวใหม่ก็ยังเป็น source='upload' (เทสต์ข้างบน) จึงไม่เข้าชุดเทรนอยู่ดี


@pytest.mark.skipif(not (ROOT / "data" / "all_kills.csv").is_file(), reason="ไม่มี data/all_kills.csv ในเครื่องนี้")
def test_training_csv_holds_only_reference_demos():
    """ทุกแมตช์ใน all_kills.csv ต้องมีไฟล์อยู่ใน demos/reference/ — ถ้ามีชื่อแปลกปลอมแปลว่าเคยปนกันไปแล้ว"""
    import csv

    ref_dir = ROOT / "demos" / "reference"
    if not ref_dir.is_dir():
        pytest.skip("ยังไม่มี demos/reference/ ในเครื่องนี้ (เดโมไม่ได้อยู่ใน git)")
    with open(ROOT / "data" / "all_kills.csv", encoding="utf-8", newline="") as f:
        in_csv = {row["demo_file"] for row in csv.DictReader(f) if row.get("demo_file")}
    on_disk = {p.name for p in ref_dir.glob("*.dem")}
    stray = sorted(in_csv - on_disk)
    assert not stray, f"ชุดเทรนมีแมตช์ที่ไม่ได้อยู่ใน demos/reference/: {stray[:5]}"
