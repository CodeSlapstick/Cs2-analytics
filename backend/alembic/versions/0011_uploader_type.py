"""matches: uploader_type — เดโมนี้มาจากผู้ใช้ Steam, โหมดเยี่ยมชม หรือของเก่า

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-15

ทำไมต้องมีคอลัมน์นี้ (ไม่ใช้ uploaded_by IS NULL แทน)
    หลังเปิดโหมดเยี่ยมชม จะมีแมตช์ที่ uploaded_by เป็น NULL อยู่สามแบบที่คนละความหมาย:
        แมตช์เก่า 56 รายการ   ไม่มีใครเป็นเจ้าของ (โหลดก่อนมีระบบบัญชี)
        guest อัปโหลด         มีคนอัป แต่คนนั้นไม่มีบัญชี Steam
        บัญชี Steam ถูกลบ      เคยมีเจ้าของ แต่ ON DELETE SET NULL ล้างไปแล้ว
    ถ้าไม่แยก uploader_type ไว้ วันที่เอาข้อมูลไปเทรน ML จะกรอง "เฉพาะของผู้ใช้ Steam" ไม่ได้
    เพราะ NULL สามแบบนี้หน้าตาเหมือนกันหมด

uploader_guest คืออะไร
    รหัสของ session โหมดเยี่ยมชม (สุ่มตอนกดเข้าชม เก็บในคุกกี้ ไม่มีแถวใน accounts)
    ใช้สองอย่าง: บอกว่าไฟล์ชุดนี้มาจากคนเดียวกัน และนับโควตาอัปโหลดต่อชั่วโมง
    ถ้าไม่มีคอลัมน์นี้ guest จะอัปได้ไม่จำกัด เพราะ WHERE uploaded_by = $1 ไม่เคยแมตช์กับ NULL

ทำไม NOT NULL และไม่ตั้ง DEFAULT
    ทั้งโปรเจกต์มีที่เดียวที่ INSERT ลง matches (POST /api/demos)
    ไม่มี default = ถ้าวันหน้าเพิ่มทางเข้าใหม่แล้วลืมระบุที่มา คำสั่งจะพังทันที
    ดีกว่าให้มันผ่านไปแล้วติดป้ายที่มาผิด เพราะข้อมูลนี้จะถูกใช้เทรนโมเดล

ทำไม CHECK ไม่บังคับว่า 'steam' ต้องมี uploaded_by
    เพราะ ON DELETE SET NULL (migration 0010) จะล้าง uploaded_by เป็น NULL ตอนลบบัญชี
    ถ้าใส่เงื่อนไขนั้นไว้ การลบบัญชีจะพังทั้งคำสั่ง — ตั้งใจให้ uploader_type ยังจำได้ว่า
    "เดโมนี้มาจากผู้ใช้ Steam" แม้จะไม่รู้แล้วว่าคนไหน
"""
from backend.db import execute_script

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("""
        ALTER TABLE matches ADD COLUMN IF NOT EXISTS uploader_type TEXT;
        ALTER TABLE matches ADD COLUMN IF NOT EXISTS uploader_guest TEXT;

        -- 1) ติดป้ายแถวที่มีอยู่ก่อน migration นี้
        --    มี uploaded_by = มาจากผู้ใช้ Steam (จาก 0010 เป็นต้นมามีทางนี้ทางเดียว)
        --    ไม่มี            = ของเก่าที่โหลดก่อนมีระบบบัญชี
        UPDATE matches SET uploader_type = CASE
            WHEN uploaded_by IS NOT NULL THEN 'steam' ELSE 'legacy' END
        WHERE uploader_type IS NULL;

        -- 2) จากนี้ทุกแถวต้องบอกที่มาได้เสมอ
        ALTER TABLE matches ALTER COLUMN uploader_type SET NOT NULL;
        ALTER TABLE matches DROP CONSTRAINT IF EXISTS matches_uploader_type_check;
        ALTER TABLE matches ADD CONSTRAINT matches_uploader_type_check
            CHECK (uploader_type IN ('legacy', 'steam', 'guest'));

        -- 3) uploader_guest มีได้เฉพาะแถวของโหมดเยี่ยมชม
        ALTER TABLE matches DROP CONSTRAINT IF EXISTS matches_uploader_guest_check;
        ALTER TABLE matches ADD CONSTRAINT matches_uploader_guest_check
            CHECK (uploader_guest IS NULL OR uploader_type = 'guest');

        -- ใช้ตอนนับโควตาของ guest: WHERE uploader_guest = $1 AND imported_at > now() - interval '1 hour'
        CREATE INDEX IF NOT EXISTS matches_uploader_guest_time_idx
            ON matches (uploader_guest, imported_at);
    """)


def downgrade() -> None:
    execute_script("""
        DROP INDEX IF EXISTS matches_uploader_guest_time_idx;
        ALTER TABLE matches DROP CONSTRAINT IF EXISTS matches_uploader_guest_check;
        ALTER TABLE matches DROP CONSTRAINT IF EXISTS matches_uploader_type_check;
        ALTER TABLE matches DROP COLUMN IF EXISTS uploader_guest;
        ALTER TABLE matches DROP COLUMN IF EXISTS uploader_type;
    """)
