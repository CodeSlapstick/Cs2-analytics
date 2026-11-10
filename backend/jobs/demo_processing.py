# -*- coding: utf-8 -*-
"""
backend/jobs/demo_processing.py — ส่งงานแกะเดโมเข้าคิว + ตัวงาน + โปรเซส worker

    enqueue_parse(match_id)   api เรียกตอนอัปโหลด — ส่งงานเข้าคิว "parse" บน Redis คืน job_id
    parse_demo(match_id)      worker ทำ — queued -> parsing -> แกะ + โหลดเข้าฐานข้อมูล -> done | error
    python -m backend.jobs    เปิด worker ฟังคิว (ใน Docker คือ service worker)
"""
import asyncio
import gc
import json
import os
import sys
import threading
import traceback
import uuid
from pathlib import Path

import asyncpg

from backend.config.database import DATABASE_URL
from backend.config.settings import DEMOS_DIR, JSON_DIR
from backend.services.etl import load_match_doc #เชื่อม etl

# ==================================================================================================
#
#     from backend.jobs import enqueue_parse, job_state
#     job_state(job_id)                    # 'queued' / 'started' / 'finished' / 'failed' / None
#
# ==================================================================================================
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
QUEUE_BACKEND = os.environ.get("QUEUE_BACKEND", "rq").strip().lower()
QUEUE_NAME = "parse"
JOB_TIMEOUT_SEC = 30 * 60      # เดโมใหญ่ ๆ แกะไม่ถึงนาที แต่เผื่อเครื่องช้า/ไฟล์ผิดปกติ
RESULT_TTL_SEC = 24 * 3600


class QueueUnavailable(Exception):
    """ต่อ Redis ไม่ได้ — ผู้เรียกควรตั้งแมตช์เป็น error พร้อมข้อความนี้ ไม่ใช่ปล่อยค้าง queued ตลอดกาล"""

# เชื่อมต่อ Redis
def _redis():
    from redis import Redis
    return Redis.from_url(REDIS_URL, socket_connect_timeout=2, socket_timeout=5)


def _queue():
    from rq import Queue
    return Queue(QUEUE_NAME, connection=_redis())

#รับ match_id จาก Api    #job id เลขติดตามงานในคิว
def enqueue_parse(match_id: int) -> str:
    """ส่งงานเข้าคิว คืน job_id — โยน QueueUnavailable ถ้า Redis ไม่ตอบ"""
    if QUEUE_BACKEND == "thread":
        job_id = f"thread-{uuid.uuid4().hex[:12]}"
        threading.Thread(target=parse_demo, args=(match_id,), name=job_id, daemon=True).start()
        return job_id

    from redis.exceptions import RedisError
    try:
        job = _queue().enqueue("backend.jobs.demo_processing.parse_demo", match_id,
                               job_timeout=JOB_TIMEOUT_SEC, result_ttl=RESULT_TTL_SEC, failure_ttl=7 * 24 * 3600,
                               description=f"parse match {match_id}")
    except (RedisError, OSError) as e:
        raise QueueUnavailable(f"ส่งงานเข้าคิวไม่ได้ (Redis ที่ {REDIS_URL} ไม่ตอบ): {type(e).__name__}: {e}") from None
    return job.id

#ถามสถานะงานใน Redis โดยใช้ job_id
def job_state(job_id: str | None) -> str | None:
    """สถานะจากฝั่งคิว (ไม่ใช่ matches.status) — ไว้บอกว่า worker หยิบงานไปหรือยัง"""
    if not job_id or QUEUE_BACKEND == "thread" or job_id.startswith("thread-"):
        return None
    try:
        from rq.job import Job
        return Job.fetch(job_id, connection=_redis()).get_status(refresh=True)
    except Exception:   # noqa: BLE001 — งานหมดอายุ / Redis ล่ม: ไม่ใช่เหตุให้ endpoint สถานะพัง
        return None

# เช็คว่าที่ระบบโหลดค้าง เป็นเพราะไม่มี Worker เปิดอยู่ หรือเพราะ Redis ล่ม
def queue_health() -> dict:
    """ไว้ให้ /api/health รายงาน — คิวยาวแค่ไหน มี worker ฟังอยู่กี่ตัว"""
    if QUEUE_BACKEND == "thread":
        return {"backend": "thread", "ok": True}
    try:
        from rq import Worker
        r = _redis()
        q = _queue()
        return {"backend": "rq", "ok": True, "queued": q.count, "workers": Worker.count(connection=r, queue=q)}
    except Exception as e:   # noqa: BLE001   # ถ้า Redis ดับ ลืมเปิด Docker หรือการเชื่อมต่อหลุด
        return {"backend": "rq", "ok": False, "error": f"{type(e).__name__}: {e}"}


# ==================================================================================================
#
#
#
# ==================================================================================================
ERROR_MAX_CHARS = 2000  #จำกัดความยาวข้อความ error ที่จะเขียนลง


class JobError(Exception):
    """ความผิดพลาดที่คาดไว้ (ไฟล์หาย / แกะไม่ได้) — ข้อความอ่านรู้เรื่อง เก็บลง error_message ได้ตรง ๆ"""

# รับ path  #เชื่อม parser.py
def _parse_file(path: Path) -> dict: 
    """เรียก parser แล้วห่อ "ทุกอย่าง" ที่ผิดพลาดเป็น JobError — รวม PanicException จาก Rust (BaseException)"""
    try:
        #เชื่อม parser
        from backend.services.parser import parse_demo as parse_file  #เปลี่ยนชื่อ
    except ImportError as e:
        raise JobError(f"worker นี้ยังไม่มี library สำหรับแกะเดโม ({e.name}) — pip install -r requirements.txt") from None
    err: str | None = None
    try:
        return parse_file(path)
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:   
        err = f"แกะเดโมไม่สำเร็จ: {type(e).__name__}: {e}" # ถ้าแกะไม่ได้แจ้งข้อความผิดพลาดให้ worker นำไปรายงานต่อ
    gc.collect()
    raise JobError(err)

# คุยกับ db เปิด connection → ส่ง SQL → ปิด connection
async def _db(sql: str, *args):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        return await conn.fetchrow(sql, *args)
    finally:
        await conn.close()

# ส่งข้อมูล doc กับ match_id ไปให้ ETL บันทึก
async def _load(doc: dict, match_id: int) -> int:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        return await load_match_doc(conn, doc, match_id=match_id)
    finally:
        await conn.close()

# นำ id ไปค้นหา ไฟล์ demo ในโฟลเดอร์
def parse_demo(match_id: int) -> dict:
    """entry point ของ RQ: backend.jobs.demo_processing.parse_demo(match_id)"""
    row = asyncio.run(_db("SELECT id, demo_file FROM matches WHERE id = $1;", match_id)) # Worker หาไฟล์จาก match_id
    if row is None:
        raise JobError(f"ไม่พบแมตช์ id={match_id} ในฐานข้อมูล")
    demo_file = row["demo_file"]

    # Worker เปลี่ยนสถานะแถวเป็น parsing   # และหาที่อยู่ของไฟล์
    asyncio.run(_db("""
        UPDATE matches SET status = 'parsing', error_message = NULL, started_at = now(), finished_at = NULL
        WHERE id = $1;
    """, match_id))
    try:
        dem_path = DEMOS_DIR / demo_file #เชื่อมต่อหาว่ามีไฟล์จริงไหม
        if not dem_path.is_file():
            raise JobError(f"ไม่พบไฟล์เดโม {dem_path} — ไฟล์อาจถูกลบ หรือ worker ไม่ได้ mount โฟลเดอร์ demos/")

       # ส่งงานให้ parser ทำงานต่อ
        doc = _parse_file(dem_path) # แกะไฟล์ ได้ผลกลับมาเป็น doc
        doc.setdefault("match", {})["demo_file"] = demo_file
       
       # แปลง doc เป็นข้อความ JSON แล้วเขียนลง output/json/<ชื่อไฟล์>.json เพื่อเก็บผลที่แกะได้ไว้บนดิสก์
        JSON_DIR.mkdir(parents=True, exist_ok=True)   # เก็บผล parse ไว้ตรวจย้อนหลัง / โหลดซ้ำโดยไม่ต้องแกะใหม่
        (JSON_DIR / (dem_path.stem + ".json")).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

        
        asyncio.run(_load(doc, match_id)) # ให้ ETL บันทึกข้อมูลลง DB
        asyncio.run(_db("UPDATE matches SET status = 'done', finished_at = now() WHERE id = $1;", match_id))
        return {"match_id": match_id, "demo_file": demo_file, **doc.get("counts", {})}

    # ถ้ามีการหยุดโปรแกรม
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:   # noqa: BLE001 — ทุกความผิดพลาดต้องลงเอยที่ status=error ตามข้อกำหนด
        msg = str(e) if isinstance(e, JobError) else f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        asyncio.run(_db("""
            UPDATE matches SET status = 'error', error_message = $2, finished_at = now() WHERE id = $1;
        """, match_id, msg[:ERROR_MAX_CHARS]))
        raise   # ให้ RQ บันทึกว่างานล้มด้วย (ดูได้จาก rq info / failed registry)


# ==================================================================================================
#
#
# ==================================================================================================

# เฝ้างาน
def main() -> None:
    from redis import Redis
    from rq import Queue, SimpleWorker, Worker

    for s in (sys.stdout, sys.stderr):     # ให้คอนโซล Windows พิมพ์ไทยได้
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    conn = Redis.from_url(REDIS_URL)
    queue = Queue(QUEUE_NAME, connection=conn)
    worker_cls = SimpleWorker if os.name == "nt" else Worker
    print(f"[worker] ฟังคิว '{QUEUE_NAME}' ที่ {REDIS_URL} ({worker_cls.__name__})")
    worker_cls([queue], connection=conn).work(with_scheduler=False)


if __name__ == "__main__":
    main()
