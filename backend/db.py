# -*- coding: utf-8 -*-
"""
backend/db.py — จุดเดียวที่คุยกับ PostgreSQL

ทุกไฟล์ใน backend/ ที่ต้องใช้ฐานข้อมูล import จากที่นี่ จะได้ไม่ต้องเขียน
วิธีต่อ DB ซ้ำกันหลายที่ และเวลาย้าย DB ก็แก้ไฟล์เดียว

    from backend.db import connect, create_pool, DATABASE_URL

    - DATABASE_URL   อ่านจาก .env ที่รากโปรเจกต์ (ค่าดีฟอลต์คือ postgres ในเครื่อง)
    - connect()      เปิด connection เดี่ยว ๆ ใช้กับสคริปต์ที่รันครั้งเดียวจบ เช่น load_kills.py
    - create_pool()  สร้าง "บ่อ" connection ให้เว็บเซิร์ฟเวอร์หยิบใช้/คืนได้ไม่ต้องต่อใหม่ทุก request
    - apply_schema() รัน schema.sql (ปลอดภัย รันซ้ำได้ เพราะทุกคำสั่งเป็น IF NOT EXISTS)
"""
import os
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_SQL = Path(__file__).resolve().parent / "schema.sql"


def load_dotenv(path: Path) -> None:
    """อ่านไฟล์ .env แบบง่าย ๆ (KEY=VALUE บรรทัดละคู่) ใส่เข้า environment ถ้ายังไม่มีค่านั้น"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/cs2_analytics",
)


async def connect() -> asyncpg.Connection:
    """connection เดี่ยว — สำหรับสคริปต์ที่รันจบในครั้งเดียว อย่าลืม await conn.close()"""
    return await asyncpg.connect(DATABASE_URL)


async def create_pool(min_size: int = 1, max_size: int = 5) -> asyncpg.Pool:
    """บ่อ connection สำหรับเว็บเซิร์ฟเวอร์ — เปิดครั้งเดียวตอน start แล้วใช้ร่วมกันทุก request"""
    return await asyncpg.create_pool(DATABASE_URL, min_size=min_size, max_size=max_size)


async def apply_schema(conn: asyncpg.Connection) -> None:
    """สร้างตาราง/view ตาม schema.sql ถ้ายังไม่มี — รันซ้ำกี่ครั้งก็ไม่พัง"""
    await conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))


def redacted_url() -> str:
    """DATABASE_URL แบบซ่อนรหัสผ่าน ไว้พิมพ์ log"""
    if "@" not in DATABASE_URL or "://" not in DATABASE_URL:
        return DATABASE_URL
    scheme, rest = DATABASE_URL.split("://", 1)
    creds, host = rest.rsplit("@", 1)
    user = creds.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host}"
