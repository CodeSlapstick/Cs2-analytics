# -*- coding: utf-8 -*-
"""
backend/database.py — SQLAlchemy async engine (ชั้นใหม่ของ Sprint 2)

    from backend.database import engine, SessionLocal, sqlalchemy_url

ทำไมมีสองทางเข้าฐานข้อมูล
    backend/db.py       = asyncpg ตรง ๆ  ใช้โดย query เดิม 15 ตัวใน app.py กับ etl_loader (ทำงานดีอยู่แล้ว ไม่แตะ)
    backend/database.py = SQLAlchemy      ใช้โดย models.py / Alembic / โค้ดใหม่ที่เขียนใน Sprint 2 เป็นต้นไป
    ทั้งคู่อ่าน DATABASE_URL ตัวเดียวกันจาก .env — ต่างกันแค่ scheme ที่ SQLAlchemy ต้องการ (postgresql+asyncpg://)
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db import DATABASE_URL  # โหลด .env ให้ตอน import


def sqlalchemy_url(url: str = DATABASE_URL) -> str:
    """แปลง postgresql://... (รูปแบบที่ asyncpg/psql ใช้) เป็น postgresql+asyncpg://... ที่ SQLAlchemy ต้องการ"""
    if url.startswith("postgresql+"):
        return url
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


# pool_pre_ping = ตรวจ connection ก่อนใช้ กันเจอ connection ที่ตายไปแล้วหลัง DB รีสตาร์ต
engine = create_async_engine(sqlalchemy_url(), pool_size=5, max_overflow=5, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
