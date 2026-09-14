"""matches: uploaded_by — ใครเป็นคนอัปโหลดเดโมนี้

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-14

ทำไมต้องมีคอลัมน์นี้
    1. จำกัดจำนวนไฟล์ต่อคนต่อชั่วโมง — ต้องนับจากฐานข้อมูล ไม่ใช่ตัวนับในหน่วยความจำ
       ตัวนับในหน่วยความจำหายทุกครั้งที่เซิร์ฟเวอร์รีสตาร์ต และถ้ารันหลาย replica จะนับแยกกัน
    2. ฐานของ ownership check — แก้/ลบแมตช์ของตัวเองได้เท่านั้น (ฟีเจอร์ในอนาคต)

ON DELETE SET NULL ไม่ใช่ CASCADE
    ลบบัญชีแล้วเดโมต้องไม่หายตามไปด้วย ข้อมูลการแข่งขันเป็นของทีม ไม่ใช่ของคนอัปโหลด
    แมตช์นั้นจะกลายเป็นข้อมูลไม่มีเจ้าของ ซึ่งมีความหมายเดียวกับแมตช์เก่า 56 รายการ

แมตช์เก่า 56 รายการจะมีค่าเป็น NULL
    ถือเป็นข้อมูล legacy ที่ไม่มีเจ้าของ ตามที่ตกลงไว้:
        ทุกคนที่ล็อกอินแล้ว "ดูได้" ตามปกติ
        แต่ "แก้/ลบไม่ได้" จนกว่าจะมีการกำหนดเจ้าของภายหลัง (เผื่อฟีเจอร์ claim)
    โค้ดฝั่ง backend ต้องรองรับ NULL กรณีนี้โดยไม่ error — ดู can_modify_match() ใน backend/app.py

    คอลัมน์จึงตั้งเป็น nullable ตลอดไป ไม่ใช่ nullable ชั่วคราวแล้วค่อยบังคับ NOT NULL ทีหลัง
    เพราะ "ไม่มีเจ้าของ" เป็นสถานะที่ถูกต้องของข้อมูล ไม่ใช่ข้อมูลที่ยังกรอกไม่ครบ

index บน uploaded_by
    การนับโควตาต่อชั่วโมงจะ query ว่า "แมตช์ของคนนี้ที่ imported_at ย้อนหลัง 1 ชั่วโมงมีกี่ไฟล์"
    ทำทุกครั้งที่มีคนอัปโหลด จึงทำ index คู่ (uploaded_by, imported_at) ไว้ให้ตรงกับ query นั้น
"""
from backend.db import execute_script

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("""
        ALTER TABLE matches ADD COLUMN IF NOT EXISTS uploaded_by INTEGER;

        ALTER TABLE matches DROP CONSTRAINT IF EXISTS matches_uploaded_by_fkey;
        ALTER TABLE matches ADD CONSTRAINT matches_uploaded_by_fkey
            FOREIGN KEY (uploaded_by) REFERENCES accounts (id) ON DELETE SET NULL;

        -- ใช้ตอนนับโควตา: WHERE uploaded_by = $1 AND imported_at > now() - interval '1 hour'
        CREATE INDEX IF NOT EXISTS matches_uploaded_by_time_idx
            ON matches (uploaded_by, imported_at);
    """)


def downgrade() -> None:
    execute_script("""
        DROP INDEX IF EXISTS matches_uploaded_by_time_idx;
        ALTER TABLE matches DROP CONSTRAINT IF EXISTS matches_uploaded_by_fkey;
        ALTER TABLE matches DROP COLUMN IF EXISTS uploaded_by;
    """)
