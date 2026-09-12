# -*- coding: utf-8 -*-
"""
backend/db.py — จุดเดียวที่คุยกับ PostgreSQL

ทุกไฟล์ใน backend/ ที่ต้องใช้ฐานข้อมูล import จากที่นี่ จะได้ไม่ต้องเขียน
วิธีต่อ DB ซ้ำกันหลายที่ และเวลาย้าย DB ก็แก้ไฟล์เดียว

    from backend.db import connect, create_pool, DATABASE_URL

    - DATABASE_URL   อ่านจาก .env ที่รากโปรเจกต์ (ค่าดีฟอลต์คือ postgres ในเครื่อง)
    - connect()      เปิด connection เดี่ยว ๆ ใช้กับสคริปต์ที่รันครั้งเดียวจบ เช่น etl_loader.py / auth.py (สร้าง dev user)
    - create_pool()  สร้าง "บ่อ" connection ให้เว็บเซิร์ฟเวอร์หยิบใช้/คืนได้ไม่ต้องต่อใหม่ทุก request
    - apply_schema() รัน views.sql สร้าง view ใหม่ทุกครั้ง (ตารางเป็นของ Alembic: alembic upgrade head)
    - sqlalchemy_url()  URL เดียวกันในรูปที่ SQLAlchemy / Alembic ต้องการ (postgresql+asyncpg://)
    - execute_script()  ให้ migration รัน SQL หลายคำสั่งต่อกันได้
"""
import os
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parent.parent
VIEWS_SQL = Path(__file__).resolve().parent / "views.sql"


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
    """สร้าง/อัปเดต view ตาม views.sql — รันซ้ำกี่ครั้งก็ไม่พัง (ตารางต้องมีก่อน: alembic upgrade head)"""
    await conn.execute(VIEWS_SQL.read_text(encoding="utf-8"))


def redacted_url() -> str:
    """DATABASE_URL แบบซ่อนรหัสผ่าน ไว้พิมพ์ log"""
    if "@" not in DATABASE_URL or "://" not in DATABASE_URL:
        return DATABASE_URL
    scheme, rest = DATABASE_URL.split("://", 1)
    creds, host = rest.rsplit("@", 1)
    user = creds.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host}"


# ---------------------------------------------------------------------------
# SQLAlchemy / Alembic — ใช้ DATABASE_URL ตัวเดียวกัน ต่างกันแค่ scheme
# ---------------------------------------------------------------------------
def sqlalchemy_url(url: str = DATABASE_URL) -> str:
    """แปลง postgresql://... (รูปแบบที่ asyncpg/psql ใช้) เป็น postgresql+asyncpg://... ที่ SQLAlchemy ต้องการ"""
    if url.startswith("postgresql+"):
        return url
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


# ---------------------------------------------------------------------------
# รัน SQL หลายคำสั่งใน migration ของ Alembic
#   driver asyncpg ส่งทุกคำสั่งเป็น prepared statement ซึ่งรับได้ "คำสั่งเดียว" ต่อครั้ง
#   op.execute("A; B; C") จึงพังด้วย "cannot insert multiple commands into a prepared statement"
#   ตัดสคริปต์เป็นคำสั่ง ๆ (บรรทัดที่ลงท้ายด้วย ;) แล้วส่งทีละคำสั่งผ่าน exec_driver_sql
#   ซึ่งส่งข้อความตรงไปที่ driver โดยไม่ผ่าน text() — คอมเมนต์ที่มี ":" จึงไม่ถูกตีความเป็น bind parameter
# ---------------------------------------------------------------------------
def split_statements(sql: str) -> list[str]:
    out, buf = [], []
    for line in sql.splitlines():
        buf.append(line)
        if line.rstrip().endswith(";"):
            stmt = "\n".join(buf).strip()
            buf = []
            if any(ln.strip() and not ln.strip().startswith("--") for ln in stmt.splitlines()):
                out.append(stmt)
    return out


def execute_script(sql: str) -> None:
    from alembic import op  # import ตอนเรียก — เว็บเซิร์ฟเวอร์กับ worker ไม่ต้องโหลด alembic

    bind = op.get_bind()
    for stmt in split_statements(sql):
        bind.exec_driver_sql(stmt)
