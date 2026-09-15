# -*- coding: utf-8 -*-
"""0012 — แยก "ชุดอ้างอิงที่ใช้เทรนโมเดล" ออกจาก "แมตช์ที่ผู้ใช้อัปโหลด"

matches.source  'reference' = เดโมชุดตั้งต้นที่ grid_ml1 เทรนจากมัน (อยู่ใน demos/reference/)
                'upload'    = เดโมที่ผู้ใช้อัปโหลดเข้ามาเอง (อยู่ใน demos/uploads/) — ห้ามเข้าชุดเทรน

ค่าตั้งต้นเป็น 'upload' เพราะเป็นทางที่ปลอดภัยกว่า: แมตช์ที่ไม่มีใครยืนยันว่าเป็นชุดอ้างอิง
ต้องไม่ถูกนับเป็นชุดเทรนโดยอัตโนมัติ  แถวเก่าที่เป็นชุดอ้างอิงจริงทำเครื่องหมายด้วย
    python -m backend.etl_loader --mark-reference
"""
from backend.db import execute_script

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("""
        ALTER TABLE matches ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'upload';
        ALTER TABLE matches DROP CONSTRAINT IF EXISTS matches_source_check;
        ALTER TABLE matches ADD CONSTRAINT matches_source_check CHECK (source IN ('reference', 'upload'));
        CREATE INDEX IF NOT EXISTS matches_source_idx ON matches (source);
    """)


def downgrade() -> None:
    execute_script("""
        DROP INDEX IF EXISTS matches_source_idx;
        ALTER TABLE matches DROP CONSTRAINT IF EXISTS matches_source_check;
        ALTER TABLE matches DROP COLUMN IF EXISTS source;
    """)
