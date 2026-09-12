# -*- coding: utf-8 -*-
"""
backend/auth.py — ล็อกอินแบบ username/password + JWT ใน httpOnly cookie (เบาที่สุดที่ใช้งานได้)

    hash_password / verify_password      PBKDF2-SHA256 จาก hashlib ของ Python เอง (ไม่ต้องลง lib เพิ่ม) salt สุ่มต่อคน
    create_token / user_from_token       JWT (HS256) อายุ 7 วัน เซ็นด้วย SECRET_KEY จาก .env
    set_auth_cookie / clear_auth_cookie  คุกกี้ httpOnly — JavaScript ในหน้าเว็บอ่าน token ไม่ได้ (ไม่เก็บใน localStorage)

    python -m backend.auth [--reset]     สร้าง dev user (dev / cs2dev1234) — docker compose รันให้ตอน api สตาร์ต
    steam_login_url / verify_steam_openid / steam_persona   ล็อกอินด้วย Steam (OpenID 2.0) — ไม่มีรหัสผ่านในระบบเรา

ยังไม่ทำ (ตั้งใจ): reset password, ยืนยันอีเมล, OAuth, role/permission
"""
import argparse
import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

import asyncpg
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


def set_auth_cookie(response, token: str, *, persistent: bool = True) -> None:
    """persistent=False (ไม่ติ๊ก "จดจำการเข้าสู่ระบบ") = คุกกี้หมดเมื่อปิดเบราว์เซอร์ — ตัว JWT ยังหมดอายุใน 7 วันเหมือนเดิม"""
    response.set_cookie(
        COOKIE_NAME, token,
        max_age=int(TOKEN_TTL.total_seconds()) if persistent else None,
        httponly=True,          # JavaScript อ่านไม่ได้ — สคริปต์แปลกปลอมขโมย token ไม่ได้
        samesite="lax",         # ไม่ส่งไปกับคำขอข้ามเว็บแบบ POST — กัน CSRF พื้นฐาน
        secure=COOKIE_SECURE,
        path="/",
    )


def clear_auth_cookie(response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


# ---------------------------------------------------------------------------
# dev user — รันซ้ำได้ มีอยู่แล้วจะข้าม (ไม่ทับรหัสผ่านที่ถูกเปลี่ยนไปแล้ว)
#   python -m backend.auth            ใช้ DEV_USERNAME / DEV_PASSWORD จาก .env (ค่าเริ่มต้น dev / cs2dev1234)
#   python -m backend.auth --reset    มี user นี้อยู่แล้วก็ตั้งรหัสผ่านกลับเป็นค่าข้างบน
# ---------------------------------------------------------------------------
DEFAULT_USERNAME = "dev"
DEFAULT_PASSWORD = "cs2dev1234"


async def seed(reset: bool = False) -> str:
    username = os.environ.get("DEV_USERNAME") or DEFAULT_USERNAME
    password = os.environ.get("DEV_PASSWORD") or DEFAULT_PASSWORD
    if (err := validate_credentials(username, password)):
        raise SystemExit(f"[dev user] DEV_USERNAME/DEV_PASSWORD ใช้ไม่ได้: {err}")
    conn = await asyncpg.connect(backend.db.DATABASE_URL)
    try:
        row = await conn.fetchrow("SELECT id FROM accounts WHERE lower(username) = lower($1)", username)
        if row and not reset:
            return f"[dev user] มี user '{username}' อยู่แล้ว (id {row['id']}) — ข้าม"
        if row:
            await conn.execute("UPDATE accounts SET password_hash = $2 WHERE id = $1", row["id"], hash_password(password))
            return f"[dev user] ตั้งรหัสผ่านของ '{username}' ใหม่แล้ว"
        new_id = await conn.fetchval(
            "INSERT INTO accounts (username, password_hash) VALUES ($1, $2) RETURNING id", username, hash_password(password))
        return f"[dev user] สร้าง user '{username}' แล้ว (id {new_id})"
    finally:
        await conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="สร้าง user สำหรับ dev")
    ap.add_argument("--reset", action="store_true", help="มีอยู่แล้วก็ตั้งรหัสผ่านใหม่")
    print(asyncio.run(seed(reset=ap.parse_args().reset)), flush=True)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# ล็อกอินด้วย Steam (OpenID 2.0)
#   1) เราพาเบราว์เซอร์ไปที่ steamcommunity.com/openid/login พร้อมบอกว่าเสร็จแล้วส่งกลับมาที่ไหน
#   2) Steam ส่งกลับมาพร้อมพารามิเตอร์ชุดหนึ่ง — ห้ามเชื่อทันที
#   3) เราส่งชุดนั้นกลับไปถาม Steam ว่า "ของคุณจริงไหม" (mode=check_authentication) ผ่านถึงจะยอมรับ
# Steam ไม่ให้ชื่อ/รูปมากับ OpenID — ต้องถาม Steam Web API อีกทีด้วย STEAM_API_KEY (ไม่มีก็ใช้ชื่อสำรอง)
# ---------------------------------------------------------------------------
STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"
STEAM_ID_RE = re.compile(r"^7656119\d{10}$")                       # SteamID64: ขึ้นต้น 7656119 ตามด้วยเลข 10 ตัว
STEAM_CLAIMED_RE = re.compile(r"^https://steamcommunity\.com/openid/id/(7656119\d{10})$")
STEAM_API_KEY = os.environ.get("STEAM_API_KEY", "")               # ไม่มีก็ล็อกอินได้ แค่ไม่ได้ชื่อ/รูปโปรไฟล์
# ว่าง = ใครมี Steam ก็เข้าได้ (ค่าที่ผู้ใช้เลือกไว้) | ใส่ SteamID64 คั่นด้วยจุลภาค = อนุญาตเฉพาะรายชื่อนี้
STEAM_ALLOWED_IDS = {s.strip() for s in os.environ.get("STEAM_ALLOWED_IDS", "").split(",") if s.strip()}
HTTP_TIMEOUT = 8


def steam_login_url(return_to: str, realm: str) -> str:
    """URL ที่พาผู้ใช้ไปล็อกอินที่ Steam — return_to ต้องอยู่ใต้ realm ไม่งั้น Steam ปฏิเสธ"""
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": return_to,
        "openid.realm": realm,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }
    return f"{STEAM_OPENID_URL}?{urllib.parse.urlencode(params)}"


def steamid_from_claimed_id(claimed_id: str | None) -> str | None:
    """แกะ SteamID64 จาก openid.claimed_id — โดเมนต้องเป็นของ Steam เป๊ะ ไม่งั้นคืน None"""
    m = STEAM_CLAIMED_RE.match((claimed_id or "").strip())
    return m.group(1) if m else None


def steam_id_allowed(steamid: str) -> bool:
    """STEAM_ALLOWED_IDS ว่าง = ใครก็เข้าได้ · ถ้าตั้งไว้ = เฉพาะ SteamID64 ในรายการ"""
    return not STEAM_ALLOWED_IDS or steamid in STEAM_ALLOWED_IDS


def verify_steam_openid(params: dict, *, url: str = STEAM_OPENID_URL) -> str | None:
    """ถาม Steam ซ้ำว่าพารามิเตอร์ชุดนี้ออกโดย Steam จริงไหม — ผ่านแล้วคืน SteamID64 ไม่ผ่านคืน None

    ฟังก์ชันนี้เรียกเน็ต (เรียกผ่าน run_in_threadpool จาก route ที่เป็น async)
    """
    steamid = steamid_from_claimed_id(params.get("openid.claimed_id"))
    if not steamid or params.get("openid.mode") != "id_res":
        return None
    check = {k: v for k, v in params.items() if k.startswith("openid.")}
    check["openid.mode"] = "check_authentication"
    body = urllib.parse.urlencode(check).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:      # noqa: S310 — URL คงที่ของ Steam
            answer = r.read().decode("utf-8", "replace")
    except OSError:
        return None
    ok = any(line.strip() == "is_valid:true" for line in answer.splitlines())
    return steamid if ok else None


def steam_persona(steamid: str) -> dict:
    """ชื่อ + รูปจาก Steam Web API — ไม่มีกุญแจหรือเรียกไม่ติด คืนชื่อสำรองที่ไม่ได้แต่งขึ้นเอง"""
    fallback = {"name": f"steam_{steamid}", "avatar": None}
    if not STEAM_API_KEY:
        return fallback
    q = urllib.parse.urlencode({"key": STEAM_API_KEY, "steamids": steamid})
    try:
        with urllib.request.urlopen(
            f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?{q}", timeout=HTTP_TIMEOUT
        ) as r:                                                            # noqa: S310 — URL คงที่ของ Steam
            players = json.loads(r.read()).get("response", {}).get("players", [])
    except (OSError, ValueError):
        return fallback
    if not players:
        return fallback
    p = players[0]
    return {"name": p.get("personaname") or fallback["name"], "avatar": p.get("avatarfull") or None}


def username_for_steam(persona: str, steamid: str) -> str:
    """ชื่อผู้ใช้ในระบบเราจากชื่อ Steam — เหลือเฉพาะตัวอักษรที่ USERNAME_RE ยอมรับ ไม่เหลืออะไรก็ใช้ steam_<id>"""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "", (persona or "").strip())[:32]
    return cleaned if USERNAME_RE.match(cleaned) else f"steam_{steamid}"

