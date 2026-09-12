"""grenades: where each grenade was thrown from, where it landed, and when its smoke / fire ended

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-12

หน้ารอบวาดระเบิดบนแผนที่พร้อมชื่อคนขว้าง จึงต้องรู้ตำแหน่ง (เดิมตารางนี้มีแค่ใคร ขว้างอะไร tick ไหน)
    throw_x / throw_y   ตำแหน่งคนขว้าง ณ ตอนขว้าง (event weapon_fire)
    land_x / land_y     จุดที่ระเบิดตก/แตก (smokegrenade_detonate / flashbang_detonate / hegrenade_detonate / inferno_startburn)
    land_tick           tick ที่ตก
    end_tick            tick ที่ควัน/ไฟหมด (smokegrenade_expired / inferno_expire) — แฟลชกับ HE = land_tick
แถวเก่าเป็น NULL ทั้งหมดจนกว่าจะแกะเดโมใหม่ (อัปโหลดทับ หรือส่งงาน parse ซ้ำ)
"""
from backend.db import execute_script

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("""
        ALTER TABLE grenades ADD COLUMN IF NOT EXISTS throw_x   REAL;
        ALTER TABLE grenades ADD COLUMN IF NOT EXISTS throw_y   REAL;
        ALTER TABLE grenades ADD COLUMN IF NOT EXISTS land_x    REAL;
        ALTER TABLE grenades ADD COLUMN IF NOT EXISTS land_y    REAL;
        ALTER TABLE grenades ADD COLUMN IF NOT EXISTS land_tick INTEGER;
        ALTER TABLE grenades ADD COLUMN IF NOT EXISTS end_tick  INTEGER;
    """)


def downgrade() -> None:
    execute_script("""
        ALTER TABLE grenades DROP COLUMN IF EXISTS end_tick;
        ALTER TABLE grenades DROP COLUMN IF EXISTS land_tick;
        ALTER TABLE grenades DROP COLUMN IF EXISTS land_y;
        ALTER TABLE grenades DROP COLUMN IF EXISTS land_x;
        ALTER TABLE grenades DROP COLUMN IF EXISTS throw_y;
        ALTER TABLE grenades DROP COLUMN IF EXISTS throw_x;
    """)
