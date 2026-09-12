"""accounts: ล็อกอินด้วย Steam (OpenID) ควบคู่กับ username/password เดิม

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-12

บัญชีที่มาจาก Steam ไม่มีรหัสผ่าน (password_hash = NULL) และผูกกับ steam_id (SteamID64) แทน
บัญชีเดิมที่ใช้รหัสผ่านไม่กระทบ — steam_id เป็น NULL และ unique index ยอมให้ NULL ซ้ำกันได้หลายแถว
avatar เก็บ URL รูปโปรไฟล์จาก Steam Web API (ว่างได้ ถ้าไม่ได้ตั้ง STEAM_API_KEY)
ตาราง users เดิมของ Steam login รุ่นแรกยังไม่ลบ ตามกฎห้ามลบของเก่า
"""
from backend.db import execute_script

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("""
        ALTER TABLE accounts ADD COLUMN IF NOT EXISTS steam_id BIGINT;
        ALTER TABLE accounts ADD COLUMN IF NOT EXISTS avatar   TEXT;
        ALTER TABLE accounts ALTER COLUMN password_hash DROP NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS accounts_steam_id_idx ON accounts (steam_id);
    """)


def downgrade() -> None:
    execute_script("""
        DROP INDEX IF EXISTS accounts_steam_id_idx;
        DELETE FROM accounts WHERE password_hash IS NULL;
        ALTER TABLE accounts ALTER COLUMN password_hash SET NOT NULL;
        ALTER TABLE accounts DROP COLUMN IF EXISTS avatar;
        ALTER TABLE accounts DROP COLUMN IF EXISTS steam_id;
    """)
