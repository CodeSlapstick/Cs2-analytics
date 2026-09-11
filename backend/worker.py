# -*- coding: utf-8 -*-
"""
backend/worker.py — โปรเซสที่หยิบงานจากคิว "parse" มาทำ

    python -m backend.worker            # ฟังคิวไปเรื่อย ๆ จนกด Ctrl+C
    docker compose up -d worker         # แบบเดียวกันแต่ใน container

Windows: RQ Worker ปกติใช้ fork() ซึ่ง Windows ไม่มี จึงสลับไปใช้ SimpleWorker (ทำงานในโปรเซสเดียว)
ให้อัตโนมัติ — พฤติกรรมเหมือนกันสำหรับงานของเรา ต่างแค่ไม่มีโปรเซสลูกคอยกันงานที่ค้าง
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.jobqueue import QUEUE_NAME, REDIS_URL  # noqa: E402  (โหลด .env ผ่าน backend.db ตอน import ใน jobs)


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
