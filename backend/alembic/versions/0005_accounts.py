"""accounts: username/password login (JWT) replacing Steam / dev-login

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-11

บัญชีสำหรับล็อกอินหน้าเว็บ — รหัสผ่านเก็บเป็น PBKDF2 hash (backend/auth.py) ไม่เคยเก็บตัวจริง
username ไม่สนตัวพิมพ์เล็กใหญ่ (unique index บน lower(username))
ตาราง users เดิมของ Steam login ไม่ลบ — เก็บไว้ตามกฎห้ามลบของเก่า แต่ไม่มีโค้ดไหนเขียนลงแล้ว
"""
from backend.db import execute_script

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_script("""
        CREATE TABLE IF NOT EXISTS accounts (
            id            SERIAL PRIMARY KEY,
            username      TEXT        NOT NULL,
            password_hash TEXT        NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_login    TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX IF NOT EXISTS accounts_username_lower_idx ON accounts (lower(username));
    """)


def downgrade() -> None:
    execute_script("""
        DROP TABLE IF EXISTS accounts;
    """)
