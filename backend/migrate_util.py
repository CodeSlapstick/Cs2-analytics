# -*- coding: utf-8 -*-
"""
backend/migrate_util.py — รัน SQL หลายคำสั่งใน migration ของ Alembic

    from backend.migrate_util import execute_script
    def upgrade(): execute_script(SQL)

ทำไมต้องมี
    driver asyncpg ส่งทุกคำสั่งเป็น prepared statement ซึ่งรับได้ "คำสั่งเดียว" ต่อครั้ง
    op.execute("A; B; C") จึงพังด้วย "cannot insert multiple commands into a prepared statement"
    ฟังก์ชันนี้ตัดสคริปต์เป็นคำสั่ง ๆ (บรรทัดที่ลงท้ายด้วย ;) แล้วส่งทีละคำสั่งผ่าน exec_driver_sql
    ซึ่งส่งข้อความตรงไปที่ driver โดยไม่ผ่าน text() — คอมเมนต์ที่มี ":" จึงไม่ถูกตีความเป็น bind parameter
"""
from alembic import op


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
    bind = op.get_bind()
    for stmt in split_statements(sql):
        bind.exec_driver_sql(stmt)
