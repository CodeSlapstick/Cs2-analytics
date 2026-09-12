"""matches: parse status columns (queued/parsing/done/error), nullable map_name/tickrate

สถานะงาน parse + error_message และให้ map_name/tickrate ว่างได้จนกว่าจะแกะเสร็จ

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-11

แถว matches ถูกสร้างตั้งแต่ตอนอัปโหลด ก่อนที่ใครจะรู้ว่าแมพอะไร tickrate เท่าไร
สองคอลัมน์นั้นจึงต้องว่างได้ แล้ว worker ค่อยเติมตอนแกะเสร็จ
แถวเก่าจาก Sprint 1 ที่มีข้อมูลครบอยู่แล้ว ให้ถือว่า done ทั้งหมด (DEFAULT ตอนเพิ่มคอลัมน์)
แถวใหม่หลังจากนี้เริ่มที่ queued
"""
from backend.db import execute_script

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("""
        ALTER TABLE matches ALTER COLUMN map_name DROP NOT NULL;
        ALTER TABLE matches ALTER COLUMN tickrate DROP NOT NULL;

        ALTER TABLE matches ADD COLUMN IF NOT EXISTS status        TEXT NOT NULL DEFAULT 'done';
        ALTER TABLE matches ALTER COLUMN status SET DEFAULT 'queued';
        ALTER TABLE matches ADD COLUMN IF NOT EXISTS error_message TEXT;
        ALTER TABLE matches ADD COLUMN IF NOT EXISTS job_id        TEXT;
        ALTER TABLE matches ADD COLUMN IF NOT EXISTS started_at    TIMESTAMPTZ;
        ALTER TABLE matches ADD COLUMN IF NOT EXISTS finished_at   TIMESTAMPTZ;

        ALTER TABLE matches DROP CONSTRAINT IF EXISTS matches_status_check;
        ALTER TABLE matches ADD CONSTRAINT matches_status_check
            CHECK (status IN ('queued', 'parsing', 'done', 'error'));
        CREATE INDEX IF NOT EXISTS matches_status_idx ON matches (status);
    """)


def downgrade() -> None:
    execute_script("""
        -- view อ้างคอลัมน์ที่จะลบอยู่ ต้องทิ้ง view ก่อน (app.py สร้างใหม่จาก views.sql ตอนสตาร์ตอยู่แล้ว)
        DROP VIEW IF EXISTS match_summary CASCADE;
        DROP INDEX IF EXISTS matches_status_idx;
        ALTER TABLE matches DROP CONSTRAINT IF EXISTS matches_status_check;
        ALTER TABLE matches DROP COLUMN IF EXISTS finished_at;
        ALTER TABLE matches DROP COLUMN IF EXISTS started_at;
        ALTER TABLE matches DROP COLUMN IF EXISTS job_id;
        ALTER TABLE matches DROP COLUMN IF EXISTS error_message;
        ALTER TABLE matches DROP COLUMN IF EXISTS status;
        -- แถวที่ยังไม่มีแมพ (queued/error) ใส่ค่ากันชนก่อนบังคับ NOT NULL กลับ
        UPDATE matches SET map_name = 'unknown' WHERE map_name IS NULL;
        UPDATE matches SET tickrate = 0 WHERE tickrate IS NULL;
        ALTER TABLE matches ALTER COLUMN map_name SET NOT NULL;
        ALTER TABLE matches ALTER COLUMN tickrate SET NOT NULL;
    """)
