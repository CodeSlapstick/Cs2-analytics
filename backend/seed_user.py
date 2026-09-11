# -*- coding: utf-8 -*-
"""
backend/seed_user.py — สร้าง user สำหรับ dev (รันซ้ำได้)

    python -m backend.seed_user            # ใช้ DEV_USERNAME / DEV_PASSWORD จาก .env (ค่าเริ่มต้น dev / cs2dev1234)
    python -m backend.seed_user --reset    # มี user นี้อยู่แล้วก็ตั้งรหัสผ่านกลับเป็นค่าข้างบน

docker compose รันให้เองทุกครั้งที่ api สตาร์ต (หลัง alembic upgrade head)
ถ้ามี user อยู่แล้วจะข้าม — ไม่ทับรหัสผ่านที่ถูกเปลี่ยนไปแล้ว
"""
import argparse
import asyncio
import os

import asyncpg

from backend.auth import hash_password, validate_credentials
from backend.db import DATABASE_URL

DEFAULT_USERNAME = "dev"
DEFAULT_PASSWORD = "cs2dev1234"


async def seed(reset: bool = False) -> str:
    username = os.environ.get("DEV_USERNAME") or DEFAULT_USERNAME
    password = os.environ.get("DEV_PASSWORD") or DEFAULT_PASSWORD
    if (err := validate_credentials(username, password)):
        raise SystemExit(f"[seed_user] DEV_USERNAME/DEV_PASSWORD ใช้ไม่ได้: {err}")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow("SELECT id FROM accounts WHERE lower(username) = lower($1)", username)
        if row and not reset:
            return f"[seed_user] มี user '{username}' อยู่แล้ว (id {row['id']}) — ข้าม"
        if row:
            await conn.execute("UPDATE accounts SET password_hash = $2 WHERE id = $1", row["id"], hash_password(password))
            return f"[seed_user] ตั้งรหัสผ่านของ '{username}' ใหม่แล้ว"
        new_id = await conn.fetchval(
            "INSERT INTO accounts (username, password_hash) VALUES ($1, $2) RETURNING id", username, hash_password(password))
        return f"[seed_user] สร้าง user '{username}' แล้ว (id {new_id})"
    finally:
        await conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="สร้าง user สำหรับ dev")
    ap.add_argument("--reset", action="store_true", help="มีอยู่แล้วก็ตั้งรหัสผ่านใหม่")
    print(asyncio.run(seed(reset=ap.parse_args().reset)), flush=True)


if __name__ == "__main__":
    main()
