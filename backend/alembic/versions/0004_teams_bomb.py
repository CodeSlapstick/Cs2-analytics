"""match_players.team_clan + rounds bomb plant position (for Round Review)

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-11

team_clan   ชื่อทีมที่คงที่ทั้งแมตช์ (clan tag ในเดโม หรือ Team A/B) — ผูกด้วย backend/features.py
bomb_plant  ตำแหน่งที่วางบอมบ์ในรอบนั้น (จาก event bomb_planted) ไว้วางไอคอนบนแผนที่หน้า Round Review
แมตช์ที่โหลดก่อน migration นี้มีค่าว่าง — API คำนวณทีมเองจาก player_rounds ได้ ส่วนตำแหน่งบอมบ์ต้องโหลดใหม่
"""
from backend.db import execute_script

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("""
        ALTER TABLE match_players ADD COLUMN IF NOT EXISTS team_clan TEXT;
        ALTER TABLE rounds ADD COLUMN IF NOT EXISTS bomb_plant_x REAL;
        ALTER TABLE rounds ADD COLUMN IF NOT EXISTS bomb_plant_y REAL;
        ALTER TABLE rounds ADD COLUMN IF NOT EXISTS bomb_site    TEXT;
    """)


def downgrade() -> None:
    execute_script("""
        ALTER TABLE rounds DROP COLUMN IF EXISTS bomb_site;
        ALTER TABLE rounds DROP COLUMN IF EXISTS bomb_plant_y;
        ALTER TABLE rounds DROP COLUMN IF EXISTS bomb_plant_x;
        ALTER TABLE match_players DROP COLUMN IF EXISTS team_clan;
    """)
