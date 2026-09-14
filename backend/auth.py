# -*- coding: utf-8 -*-
"""
backend/auth.py — ล็อกอินด้วย Steam (OpenID 2.0) + JWT ใน httpOnly cookie

    create_token / user_from_token       JWT (HS256) อายุ 7 วัน เซ็นด้วย SECRET_KEY จาก .env
    set_auth_cookie / clear_auth_cookie  คุกกี้ httpOnly — JavaScript ในหน้าเว็บอ่าน token ไม่ได้ (ไม่เก็บใน localStorage)

    python -m backend.auth [--reset]     สร้าง dev user (dev / cs2dev1234) — docker compose รันให้ตอน api สตาร์ต
    steam_login_url / verify_steam_openid / steam_persona   ล็อกอินด้วย Steam (OpenID 2.0) — ไม่มีรหัสผ่านในระบบเรา

ระบบนี้รองรับเฉพาะบัญชี Steam เท่านั้น (CS2 เล่นผ่าน Steam) จึงไม่มีรหัสผ่าน ไม่มีหน้าสมัคร
และไม่แบ่ง role — ล็อกอินแล้วทุกคนมีสิทธิ์เท่ากัน
"""
import json
import os
import re
import secrets
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

import jwt

import backend.db  # noqa: F401  โหลด .env เข้า environment ก่อนอ่าน SECRET_KEY / COOKIE_SECURE

COOKIE_NAME = "cs2_token"
JWT_ALG = "HS256"
TOKEN_TTL = timedelta(days=7)
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"   # 1 = ส่งคุกกี้เฉพาะ HTTPS (เปิดเมื่อ deploy จริง)


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


_dummy_hash: str | None = None


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def create_token(user_id: int, username: str, *, secret: str | None = None,
                 ttl: timedelta = TOKEN_TTL, now: datetime | None = None) -> str:
    """สร้าง JWT ของผู้ใช้ที่ล็อกอินผ่าน Steam แล้ว

    ไม่มีฟิลด์สิทธิ์ใน payload เพราะระบบไม่แบ่ง role — ล็อกอินแล้วทำได้เท่ากันหมด
    สิทธิ์ที่ยังแยกอยู่คือ "เจ้าของข้อมูล" ซึ่งเทียบจาก id ในฐานข้อมูล ไม่ใช่จาก token
    """
    now = now or datetime.now(UTC)
    payload = {"sub": str(user_id), "name": username, "iat": now, "exp": now + ttl}
    return jwt.encode(payload, secret or secret_key(), algorithm=JWT_ALG)


def user_from_token(token: str | None, *, secret: str | None = None) -> dict | None:
    """แกะ token จากคุกกี้ — หมดอายุ / ถูกแก้ / เซ็นด้วยกุญแจอื่น / ไม่ใช่ HS256 -> None (= ยังไม่ล็อกอิน)"""
    if not token:
        return None
    try:
        p = jwt.decode(token, secret or secret_key(), algorithms=[JWT_ALG], options={"require": ["exp", "sub"]})
        # token เก่าที่ยังมีฟิลด์ role ติดมา ถูกมองข้ามไปเฉย ๆ ไม่ต้องบังคับให้ล็อกอินใหม่
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
# ชื่อผู้ใช้ที่ยอมรับ — ใช้ตรวจชื่อที่สร้างจากชื่อโปรไฟล์ Steam ก่อนเอาไปเก็บ (ดู username_for_steam)
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
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

