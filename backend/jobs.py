# -*- coding: utf-8 -*-
"""
backend/jobs.py — งานเดียวของ worker: parse_demo(match_id)

    เดโมถูกอัปโหลดไว้ที่ demos/<demo_file> และแถว matches ถูกสร้างไว้แล้ว (status=queued)
    งานนี้: queued -> parsing -> (แกะ + โหลดเข้าฐานข้อมูล) -> done   หรือ   -> error พร้อมข้อความ

กฎสองข้อจาก brief
    idempotent   รันซ้ำ match เดิมได้ไม่เกิดข้อมูลซ้ำ — etl_loader ลบลูก ๆ ของแมตช์ก่อนใส่ใหม่ทุกครั้ง
    ทุก error    ต้องลงเอยที่ matches.status = 'error' + error_message เสมอ รวมถึง panic จาก Rust ใน demoparser2
                 ซึ่งเป็น BaseException ไม่ใช่ Exception (except Exception ธรรมดาดักไม่ได้)

ฟังก์ชันเป็น sync เพราะ RQ เรียกแบบ sync — ส่วนที่คุยกับฐานข้อมูล (asyncpg) ห่อด้วย asyncio.run
"""
import asyncio
import gc
import json
import os
import sys
import traceback
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.db import DATABASE_URL  # noqa: E402
from backend.etl_loader import load_match_doc  # noqa: E402

DEMOS_DIR = Path(os.environ.get("DEMOS_DIR", ROOT / "demos"))
JSON_DIR = Path(os.environ.get("JSON_DIR", ROOT / "output" / "json"))
ERROR_MAX_CHARS = 2000


class JobError(Exception):
    """ความผิดพลาดที่คาดไว้ (ไฟล์หาย / แกะไม่ได้) — ข้อความอ่านรู้เรื่อง เก็บลง error_message ได้ตรง ๆ"""


def _parse_file(path: Path) -> dict:
    """เรียก parser แล้วห่อ "ทุกอย่าง" ที่ผิดพลาดเป็น JobError — รวม PanicException จาก Rust (BaseException)"""
    try:
        from backend.parser.service import parse_demo as parse_file
    except ImportError as e:
        raise JobError(f"worker นี้ยังไม่มี library สำหรับแกะเดโม ({e.name}) — pip install -r requirements.txt") from None
    err: str | None = None
    try:
        return parse_file(path)
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:   # ตั้งใจดักกว้าง ดูคำอธิบายบนหัวไฟล์
        err = f"แกะเดโมไม่สำเร็จ: {type(e).__name__}: {e}"
    # ต้อง raise "นอก" except: ตราบใดที่ยังอยู่ใน except ตัว exception จะอ้าง frame ของ parser
    # ซึ่งถือไฟล์ .dem เปิดอยู่ — บน Windows ไฟล์ที่พังจะถูกล็อกจนอัปโหลดทับไม่ได้ (PermissionError)
    # ออกจาก except แล้ว Python ปล่อย exception เอง เก็บกวาดอีกทีให้ชัวร์ แล้วค่อยรายงาน
    gc.collect()
    raise JobError(err)


async def _db(sql: str, *args):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        return await conn.fetchrow(sql, *args)
    finally:
        await conn.close()


async def _load(doc: dict, match_id: int) -> int:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        return await load_match_doc(conn, doc, match_id=match_id)
    finally:
        await conn.close()


def parse_demo(match_id: int) -> dict:
    """entry point ของ RQ: backend.jobs.parse_demo(match_id)"""
    row = asyncio.run(_db("SELECT id, demo_file FROM matches WHERE id = $1;", match_id))
    if row is None:
        raise JobError(f"ไม่พบแมตช์ id={match_id} ในฐานข้อมูล")
    demo_file = row["demo_file"]

    asyncio.run(_db("""
        UPDATE matches SET status = 'parsing', error_message = NULL, started_at = now(), finished_at = NULL
        WHERE id = $1;
    """, match_id))
    try:
        dem_path = DEMOS_DIR / demo_file
        if not dem_path.is_file():
            raise JobError(f"ไม่พบไฟล์เดโม {dem_path} — ไฟล์อาจถูกลบ หรือ worker ไม่ได้ mount โฟลเดอร์ demos/")

        doc = _parse_file(dem_path)
        doc.setdefault("match", {})["demo_file"] = demo_file

        JSON_DIR.mkdir(parents=True, exist_ok=True)   # เก็บผล parse ไว้ตรวจย้อนหลัง / โหลดซ้ำโดยไม่ต้องแกะใหม่
        (JSON_DIR / (dem_path.stem + ".json")).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

        asyncio.run(_load(doc, match_id))
        asyncio.run(_db("UPDATE matches SET status = 'done', finished_at = now() WHERE id = $1;", match_id))
        return {"match_id": match_id, "demo_file": demo_file, **doc.get("counts", {})}

    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:   # noqa: BLE001 — ทุกความผิดพลาดต้องลงเอยที่ status=error ตามข้อกำหนด
        msg = str(e) if isinstance(e, JobError) else f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        asyncio.run(_db("""
            UPDATE matches SET status = 'error', error_message = $2, finished_at = now() WHERE id = $1;
        """, match_id, msg[:ERROR_MAX_CHARS]))
        raise   # ให้ RQ บันทึกว่างานล้มด้วย (ดูได้จาก rq info / failed registry)
