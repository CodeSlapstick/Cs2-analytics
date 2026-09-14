"""accounts: เหลือ Steam อย่างเดียว + ยกเลิก role

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-14

หลักการของระบบ: CS2 เล่นผ่าน Steam ผู้ใช้จริงทุกคนจึงมี steam_id เสมอ
โครงตารางควรบังคับข้อนี้ ไม่ใช่ปล่อยให้โค้ดคอยเช็คเอง

migration นี้ทำสามอย่าง เรียงลำดับตามที่ต้องทำจริง:

    1. ลบบัญชีทดสอบที่ไม่มี steam_id
       dev + kayasu1234 — ตรวจแล้วว่าไม่มี foreign key หรือคอลัมน์ใดในฐานข้อมูล
       อ้างถึง accounts.id เลย (pg_constraint คืน 0 แถว) เดโมทั้ง 56 แมตช์
       ไม่ผูกกับบัญชีใคร ลบแล้วจึงไม่มีข้อมูลอื่นหายตาม

    2. บังคับ steam_id NOT NULL + UNIQUE
       ต้องทำหลังขั้นที่ 1 เพราะถ้ายังมีแถวที่ steam_id เป็น NULL อยู่
       คำสั่ง SET NOT NULL จะล้มทั้ง migration
       (UNIQUE index มีมาแล้วตั้งแต่ 0007 — ที่เพิ่มคือ NOT NULL)

    3. ลบ password_hash และ role
       password_hash  ไม่มีการล็อกอินด้วยรหัสผ่านอีกแล้ว
       role           ยกเลิกการแบ่งสิทธิ์ ผู้ใช้ที่ล็อกอินแล้วมีสิทธิ์เท่ากันหมด

ไม่ลบคอลัมน์ username — บัญชี Steam ก็ใช้ (ตั้งจากชื่อ Steam หรือ steam_<SteamID64>)
และหน้าเว็บแสดงค่านี้บนแถบบน (frontend/src/main.tsx) คนละเรื่องกับ local auth

downgrade คืนคอลัมน์ให้ แต่คืนบัญชีทดสอบที่ลบไปไม่ได้ — ข้อมูลที่ลบแล้วก็คือลบแล้ว
"""
from backend.db import execute_script

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("""
        -- 1) บัญชีทดสอบที่ไม่มี Steam — ไม่ใช่ผู้ใช้จริงของระบบ
        DELETE FROM accounts WHERE steam_id IS NULL;

        -- 2) จากนี้ทุกบัญชีต้องมาจาก Steam เท่านั้น
        ALTER TABLE accounts ALTER COLUMN steam_id SET NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS accounts_steam_id_idx ON accounts (steam_id);

        -- 3) เลิกใช้รหัสผ่าน และเลิกแบ่งสิทธิ์
        ALTER TABLE accounts DROP CONSTRAINT IF EXISTS accounts_role_check;
        ALTER TABLE accounts DROP COLUMN IF EXISTS role;
        ALTER TABLE accounts DROP COLUMN IF EXISTS password_hash;
    """)


def downgrade() -> None:
    # คืนโครงคอลัมน์ได้ แต่บัญชีที่ถูกลบในขั้นที่ 1 คืนไม่ได้
    execute_script("""
        ALTER TABLE accounts ADD COLUMN IF NOT EXISTS password_hash TEXT;
        ALTER TABLE accounts ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'member';
        ALTER TABLE accounts ADD CONSTRAINT accounts_role_check CHECK (role IN ('member', 'admin'));
        ALTER TABLE accounts ALTER COLUMN steam_id DROP NOT NULL;
    """)
