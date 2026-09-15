"""accounts: role — แยกสิทธิ์ "อ่านอย่างเดียว" ออกจาก "แก้ข้อมูลของระบบได้"

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-13

ก่อนหน้านี้ทุกคนที่ล็อกอินได้สิทธิ์เท่ากันหมด — ใครก็อัปโหลดเดโมและสั่งโหลดทับแมตช์เดิมได้
ซึ่งเป็นการเขียนทับข้อมูลของทั้งทีม

role มีสองค่าเท่านั้น ตั้งใจให้น้อยที่สุดเท่าที่อธิบายได้:
    member  (ค่าเริ่มต้น)  อ่านข้อมูลได้ทุกอย่าง แต่เปลี่ยนแปลงข้อมูลไม่ได้
    admin                  อัปโหลด/โหลดทับเดโมได้ด้วย

ทำไมไม่แยกเป็น โค้ช / นักวิเคราะห์ / ผู้เล่น ตั้งแต่ตอนนี้
    สามบทบาทนั้นต่างกันที่ "เห็นข้อมูลของใครได้บ้าง" ซึ่งต้องออกแบบร่วมกับเจ้าของงานก่อน
    การเดาแล้วใส่ลงไปจะกลายเป็นกฎที่ไม่มีใครยืนยันได้ว่าถูก
    ตอนนี้จึงแยกเฉพาะเส้นที่ชัดเจน: ใครเปลี่ยนข้อมูลของระบบได้

บัญชีที่มีอยู่แล้วทั้งหมดถูกตั้งเป็น admin เพื่อไม่ให้ระบบที่ใช้งานอยู่สะดุด
(ถ้าตั้งเป็น member หมด จะไม่เหลือใครอัปโหลดเดโมได้เลย)
"""
from backend.db import execute_script

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("""
        ALTER TABLE accounts ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'member';

        -- บัญชีที่มีอยู่ก่อน migration นี้ = คนที่ใช้ระบบอยู่จริง ให้เป็น admin ต่อไป
        -- เงื่อนไข created_at กันไม่ให้บัญชีที่สมัครหลังจากนี้ได้ admin ไปด้วย
        UPDATE accounts SET role = 'admin' WHERE created_at <= now();

        ALTER TABLE accounts DROP CONSTRAINT IF EXISTS accounts_role_check;
        ALTER TABLE accounts ADD CONSTRAINT accounts_role_check CHECK (role IN ('member', 'admin'));
    """)


def downgrade() -> None:
    execute_script("""
        ALTER TABLE accounts DROP CONSTRAINT IF EXISTS accounts_role_check;
        ALTER TABLE accounts DROP COLUMN IF EXISTS role;
    """)
