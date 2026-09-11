# -*- coding: utf-8 -*-
"""
backend/auth.py — ล็อกอินแบบ username/password + JWT ใน httpOnly cookie (เบาที่สุดที่ใช้งานได้)

    hash_password / verify_password      PBKDF2-SHA256 จาก hashlib ของ Python เอง (ไม่ต้องลง lib เพิ่ม) salt สุ่มต่อคน
    create_token / user_from_token       JWT (HS256) อายุ 7 วัน เซ็นด้วย SECRET_KEY จาก .env
    set_auth_cookie / clear_auth_cookie  คุกกี้ httpOnly — JavaScript ในหน้าเว็บอ่าน token ไม่ได้ (ไม่เก็บใน localStorage)

ยังไม่ทำ (ตั้งใจ): reset password, ยืนยันอีเมล, OAuth, role/permission
"""
import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import UTC, datetime, timedelta

import jwt

import backend.db  # noqa: F401  โหลด .env เข้า environment ก่อนอ่าน SECRET_KEY / COOKIE_SECURE

COOKIE_NAME = "cs2_token"
JWT_ALG = "HS256"
TOKEN_TTL = timedelta(days=7)
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"   # 1 = ส่งคุกกี้เฉพาะ HTTPS (เปิดเมื่อ deploy จริง)

PBKDF2_ITERATIONS = 390_000            # ค่าแนะนำของ OWASP สำหรับ PBKDF2-SHA256 (ช้าพอให้เดารหัสยาก ~0.3 วินาทีต่อครั้ง)
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
PASSWORD_MIN = 8
PASSWORD_MAX = 256

_secret: str | None = None


def secret_key() -> str:
    """กุญแจเซ็น JWT — ไม่ตั้ง SECRET_KEY ไว้ = สุ่มใหม่ทุกครั้งที่เซิร์ฟเวอร์สตาร์ต (ทุกคนต้องล็อกอินใหม่)"""
    global _secret
    if _secret is None:
        _secret = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    return _secret


# ---------------------------------------------------------------------------
# รหัสผ่าน
# ---------------------------------------------------------------------------
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    """คืน 'pbkdf2_sha256$รอบ$salt$hash' — เก็บจำนวนรอบไว้ในตัว จะเพิ่มรอบทีหลังได้โดยรหัสเก่ายังใช้ได้"""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str | None) -> bool:
    """เทียบรหัสผ่านกับ hash ที่เก็บไว้ — รูปแบบผิด/ข้อมูลเสียทุกแบบตอบ False ไม่โยน error"""
    try:
        algo, iterations, salt, digest = str(stored).split("$")
        if algo != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _unb64(salt), int(iterations))
        return hmac.compare_digest(calc, _unb64(digest))       # เทียบแบบเวลาคงที่ กันเดาทีละตัวจากเวลาตอบ
    except (ValueError, TypeError):
        return False


_dummy_hash: str | None = None


def burn_time_like_verify(password: str) -> None:
    """ตอนหา username ไม่เจอ ให้เสียเวลาเท่ากับตรวจรหัสจริง — เวลาตอบจะได้ไม่บอกว่าชื่อนี้มีอยู่ในระบบไหม"""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password(secrets.token_hex(8))
    verify_password(password, _dummy_hash)


def validate_credentials(username: str | None, password: str | None) -> str | None:
    """คืนข้อความ error ภาษาไทย หรือ None ถ้าใช้ได้"""
    if not USERNAME_RE.match(username or ""):
        return "ชื่อผู้ใช้ต้องยาว 3-32 ตัว ใช้ได้เฉพาะ a-z A-Z 0-9 _ . -"
    if len(password or "") < PASSWORD_MIN:
        return f"รหัสผ่านต้องยาวอย่างน้อย {PASSWORD_MIN} ตัว"
    if len(password) > PASSWORD_MAX:
        return "รหัสผ่านยาวเกินไป"
    return None


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def create_token(user_id: int, username: str, *, secret: str | None = None,
                 ttl: timedelta = TOKEN_TTL, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    payload = {"sub": str(user_id), "name": username, "iat": now, "exp": now + ttl}
    return jwt.encode(payload, secret or secret_key(), algorithm=JWT_ALG)


def user_from_token(token: str | None, *, secret: str | None = None) -> dict | None:
    """แกะ token จากคุกกี้ — หมดอายุ / ถูกแก้ / เซ็นด้วยกุญแจอื่น / ไม่ใช่ HS256 -> None (= ยังไม่ล็อกอิน)"""
    if not token:
        return None
    try:
        p = jwt.decode(token, secret or secret_key(), algorithms=[JWT_ALG], options={"require": ["exp", "sub"]})
        return {"id": int(p["sub"]), "username": str(p.get("name", ""))}
    except (jwt.InvalidTokenError, TypeError, ValueError):
        return None


def set_auth_cookie(response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME, token,
        max_age=int(TOKEN_TTL.total_seconds()),
        httponly=True,          # JavaScript อ่านไม่ได้ — สคริปต์แปลกปลอมขโมย token ไม่ได้
        samesite="lax",         # ไม่ส่งไปกับคำขอข้ามเว็บแบบ POST — กัน CSRF พื้นฐาน
        secure=COOKIE_SECURE,
        path="/",
    )


def clear_auth_cookie(response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
