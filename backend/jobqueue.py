# -*- coding: utf-8 -*-
"""
backend/jobqueue.py — ส่งงาน parse เข้าคิว และถามสถานะงาน

    from backend.jobqueue import enqueue_parse, job_state
    job_id = enqueue_parse(match_id)     # เข้าคิว "parse" ให้ worker (python -m backend.worker) หยิบไปทำ
    job_state(job_id)                    # 'queued' / 'started' / 'finished' / 'failed' / None

QUEUE_BACKEND (จาก .env)
    rq      ค่าปกติ — ผ่าน Redis ตาม brief  ต้องมี Redis (docker compose up -d redis) และ worker รันอยู่
    thread  รันงานในโปรเซสของเซิร์ฟเวอร์เองใน thread แยก ไว้ dev/test ในเครื่องโดยไม่ต้องมี Redis
            (พฤติกรรมที่หน้าเว็บเห็นเหมือนกันทุกอย่าง: ตอบ queued ทันที แล้ว status ค่อยขยับ)
"""
import os
import threading
import uuid

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
QUEUE_BACKEND = os.environ.get("QUEUE_BACKEND", "rq").strip().lower()
QUEUE_NAME = "parse"
JOB_TIMEOUT_SEC = 30 * 60      # เดโมใหญ่ ๆ แกะไม่ถึงนาที แต่เผื่อเครื่องช้า/ไฟล์ผิดปกติ
RESULT_TTL_SEC = 24 * 3600


class QueueUnavailable(Exception):
    """ต่อ Redis ไม่ได้ — ผู้เรียกควรตั้งแมตช์เป็น error พร้อมข้อความนี้ ไม่ใช่ปล่อยค้าง queued ตลอดกาล"""


def _redis():
    from redis import Redis
    # timeout สั้น ๆ: ถ้า Redis ล่ม ให้รู้ใน 2 วินาที ไม่ใช่แขวน request ค้างไว้
    return Redis.from_url(REDIS_URL, socket_connect_timeout=2, socket_timeout=5)


def _queue():
    from rq import Queue
    return Queue(QUEUE_NAME, connection=_redis())


def enqueue_parse(match_id: int) -> str:
    """ส่งงานเข้าคิว คืน job_id — โยน QueueUnavailable ถ้า Redis ไม่ตอบ"""
    if QUEUE_BACKEND == "thread":
        from backend.jobs import parse_demo
        job_id = f"thread-{uuid.uuid4().hex[:12]}"
        threading.Thread(target=parse_demo, args=(match_id,), name=job_id, daemon=True).start()
        return job_id

    from redis.exceptions import RedisError
    try:
        job = _queue().enqueue("backend.jobs.parse_demo", match_id,
                               job_timeout=JOB_TIMEOUT_SEC, result_ttl=RESULT_TTL_SEC, failure_ttl=7 * 24 * 3600,
                               description=f"parse match {match_id}")
    except (RedisError, OSError) as e:
        raise QueueUnavailable(f"ส่งงานเข้าคิวไม่ได้ (Redis ที่ {REDIS_URL} ไม่ตอบ): {type(e).__name__}: {e}") from None
    return job.id


def job_state(job_id: str | None) -> str | None:
    """สถานะจากฝั่งคิว (ไม่ใช่ matches.status) — ไว้บอกว่า worker หยิบงานไปหรือยัง"""
    if not job_id or QUEUE_BACKEND == "thread" or job_id.startswith("thread-"):
        return None
    try:
        from rq.job import Job
        return Job.fetch(job_id, connection=_redis()).get_status(refresh=True)
    except Exception:   # noqa: BLE001 — งานหมดอายุ / Redis ล่ม: ไม่ใช่เหตุให้ endpoint สถานะพัง
        return None


def queue_health() -> dict:
    """ไว้ให้ /api/health รายงาน — คิวยาวแค่ไหน มี worker ฟังอยู่กี่ตัว"""
    if QUEUE_BACKEND == "thread":
        return {"backend": "thread", "ok": True}
    try:
        from rq import Worker
        r = _redis()
        q = _queue()
        return {"backend": "rq", "ok": True, "queued": q.count, "workers": Worker.count(connection=r, queue=q)}
    except Exception as e:   # noqa: BLE001
        return {"backend": "rq", "ok": False, "error": f"{type(e).__name__}: {e}"}
