# -*- coding: utf-8 -*-
"""
backend/app.py — "หลังบ้าน" (backend) ของเว็บ CS2 Analytics

เปรียบเทียบง่าย ๆ: ไฟล์นี้คือ "พนักงานหลังเคาน์เตอร์"
  - หน้าเว็บ (frontend/) = ลูกค้าที่มายืนหน้าเคาน์เตอร์
  - ไฟล์นี้ = พนักงานที่คอยรับคำสั่ง ไปหยิบของจากคลัง (PostgreSQL) แล้วส่งกลับไปให้

หน้าที่ของไฟล์นี้มี 4 อย่าง
  1) ส่งหน้าเว็บ (ไฟล์ .html ใน frontend/pages/) ให้เบราว์เซอร์
  2) พาผู้ใช้ไปล็อกอินที่ Steam แล้วรับผลกลับมา
  3) จำว่า "ใครล็อกอินอยู่" ด้วยคุกกี้ (cookie = บัตรคิวที่ติดตัวลูกค้าไว้)
  4) ตอบ /api/* — ดึงสถิติจากฐานข้อมูลแล้วส่งเป็น JSON ให้หน้าเว็บเอาไปวาด

ข้อมูลอยู่ใน PostgreSQL (โครงอยู่ที่ backend/schema.sql โหลดด้วย backend/load_kills.py)
ไฟล์นี้ไม่อ่าน csv เองแล้ว — อ่านผ่าน SQL อย่างเดียว จะได้ filter/รวมข้อมูลได้เร็วโดยไม่ต้องโหลดทั้งตารางเข้าแรม

รัน:  python -m uvicorn backend.app:app --reload
เปิด: http://localhost:8000
"""

# ---------------------------------------------------------------------------
# ส่วนที่ 0 — ขนเครื่องมือเข้ามาใช้
# ---------------------------------------------------------------------------
import json
import mimetypes
import os
import re
import secrets
import sys
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import httpx                   # httpx = โทรศัพท์ ใช้ "โทร" ไปถามเว็บอื่น (ที่นี่คือเซิร์ฟเวอร์ Steam)
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, URLSafeSerializer   # เครื่อง "เซ็นชื่อ" ข้อมูลในคุกกี้ กันคนปลอมแปลง

from backend.db import DATABASE_URL, apply_schema, create_pool, redacted_url  # noqa: F401  (load_dotenv ทำงานตอน import)

# ---------------------------------------------------------------------------
# ส่วนที่ 1 — ค่าตั้งต้น (CONFIG) อยากแก้อะไรแก้ตรงนี้ที่เดียว
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent   # โฟลเดอร์โปรเจกต์
FRONTEND = ROOT / "frontend"                    # โฟลเดอร์ของหน้าเว็บทั้งหมด
PAGES_DIR = FRONTEND / "pages"                  # หน้า .html ที่ไฟล์นี้เสิร์ฟให้เบราว์เซอร์
STATIC_DIR = FRONTEND / "static"                # ไฟล์นิ่ง ๆ (.css .js รูป)
ASSETS_DIR = ROOT / "assets"                    # ภาพเรดาร์ของแต่ละแมพ + ค่าปรับเทียบพิกัด (radars.json)

# คอนโซลของ Windows ดีฟอลต์เป็น cp1252 ซึ่งพิมพ์ภาษาไทยไม่ได้ ถ้าไม่ตั้งบรรทัดนี้
# print() ที่มีข้อความไทยจะโยน UnicodeEncodeError ออกมากลางคัน ทำให้ทั้ง request พัง
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def log(msg: str) -> None:
    """พิมพ์ log โดยไม่มีทางทำให้โปรแกรมพังเพราะ encoding ของคอนโซล"""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


# ค่าจาก .env ที่รากโปรเจกต์ (backend/db.py โหลดเข้า environment ให้แล้วตอน import)
STEAM_API_KEY = os.environ.get("STEAM_API_KEY", "")             # กุญแจ Steam ขอฟรีที่ steamcommunity.com/dev/apikey ("" = ยังไม่มี)
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")  # ที่อยู่เว็บเรา ใช้บอก Steam ว่า "ล็อกอินเสร็จให้ส่งกลับมาที่นี่"
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)  # กุญแจเซ็นคุกกี้ ถ้าไม่ตั้งไว้ = สุ่มใหม่ทุกครั้งที่รัน (ล็อกอินจะหลุดตอนรีสตาร์ต)
ALLOW_DEV_LOGIN = os.environ.get("ALLOW_DEV_LOGIN", "1") == "1"     # "โหมดทดสอบ" ให้พิมพ์เลข Steam เข้าเองได้ โดยไม่ต้องมีกุญแจ API

COOKIE_NAME = "cs2_session"        # ชื่อคุกกี้ (บัตรคิว) ที่เราจะติดให้ผู้ใช้
COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # อายุคุกกี้ 1 สัปดาห์

STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"  # ประตูล็อกอินของ Steam (มาตรฐานชื่อ OpenID 2.0)
STEAM_ID_RE = re.compile(r"^7656119\d{10}$")                  # แบบแผนของ SteamID64: ขึ้นต้น 7656119 แล้วตามด้วยเลข 10 ตัว
SIDE_RE = re.compile(r"^(ct|t)$")

signer = URLSafeSerializer(SECRET_KEY, salt="cs2-session")    # "ตราประทับ" ไว้เซ็นและตรวจคุกกี้ด้วยกุญแจลับ


# ---------------------------------------------------------------------------
# ส่วนที่ 2 — เปิด/ปิดฐานข้อมูลพร้อมเซิร์ฟเวอร์
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """สิ่งที่ทำตอนเซิร์ฟเวอร์เริ่ม (ก่อน yield) และตอนปิด (หลัง yield)"""
    app.state.pool = None
    try:
        app.state.pool = await create_pool()
        async with app.state.pool.acquire() as conn:
            await apply_schema(conn)          # สร้างตารางถ้ายังไม่มี รันซ้ำได้
        log(f"[DB] ต่อ {redacted_url()} สำเร็จ")
    except Exception as e:                    # DB ล่ม/ยังไม่เปิด -> เว็บยังเปิดได้ แต่ /api/* จะตอบ 503
        log(f"[DB] ต่อ {redacted_url()} ไม่ได้: {e}")
        log("[DB] เปิด DB ด้วย: docker compose up -d db")
    yield
    if app.state.pool:
        await app.state.pool.close()


app = FastAPI(title="CS2 Analytics API", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")  # URL ที่ขึ้นต้นด้วย /static ให้ไปหยิบไฟล์จริงใน frontend/static/
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")  # URL ที่ขึ้นต้นด้วย /assets ให้ไปหยิบไฟล์จริงใน assets/ (ภาพเรดาร์)

# Windows บางเครื่องไม่รู้จักนามสกุล .webp ทำให้ส่งไฟล์ออกไปเป็น application/octet-stream
# บอกชนิดไฟล์ให้ถูกต้องไว้ก่อน เบราว์เซอร์จะได้รู้แน่ ๆ ว่านี่คือรูปภาพ
mimetypes.add_type("image/webp", ".webp")


@app.middleware("http")
async def no_stale_static(request: Request, call_next):
    """บังคับให้เบราว์เซอร์ถามเซิร์ฟเวอร์ก่อนใช้ไฟล์ .css/.js/.html ที่แคชไว้

    ทำไมต้องมี
        FastAPI ส่ง etag กับ last-modified มาให้อยู่แล้ว แต่ "ไม่ส่ง" cache-control
        พอไม่มี cache-control เบราว์เซอร์จะใช้ heuristic caching คือเดาอายุไฟล์เอง
        จาก last-modified แล้วหยิบของในแคชมาใช้เลยโดยไม่ถามเซิร์ฟเวอร์ซ้ำ
        ผลคือแก้ style.css แล้วรีเฟรชธรรมดาไม่เห็นการเปลี่ยนแปลง ต้อง Ctrl+Shift+R ทุกครั้ง
        และอาการจะโผล่เฉพาะเครื่องที่เคยเปิดเว็บก่อนแก้ไฟล์ — เครื่องใหม่ดูปกติ หาสาเหตุยากมาก

    no-cache ไม่ได้แปลว่า "ห้ามแคช"
        แปลว่า "แคชได้ แต่ต้องถามก่อนใช้" ถ้าไฟล์ไม่เปลี่ยน etag จะตรงกัน
        เซิร์ฟเวอร์ตอบ 304 Not Modified ตัวเปล่า ๆ ไม่ได้ส่งไฟล์ซ้ำ จึงแทบไม่เปลืองอะไร

    รูปกับฟอนต์ไม่ต้องยุ่ง — พวกนั้นเปลี่ยนน้อย ปล่อยให้แคชยาว ๆ ได้เลย

    ดูจาก content-type ไม่ใช่จากนามสกุลใน URL
        เพราะหน้าเว็บของเราเป็น /overview /players /map ไม่มี .html ต่อท้ายสักอัน
        ถ้าไล่เช็คนามสกุลจะหลุดทุกหน้าพอดี แต่ content-type บอกตรง ๆ ว่าไฟล์นี้คืออะไร
    """
    response = await call_next(request)
    ctype = response.headers.get("content-type", "")
    if ctype.startswith(("text/html", "text/css", "text/javascript", "application/javascript")):
        response.headers["Cache-Control"] = "no-cache"
    return response


async def db(request: Request) -> asyncpg.Connection:
    """Dependency: ขอ connection จากบ่อหนึ่งเส้นให้ route นี้ใช้ แล้วคืนอัตโนมัติเมื่อจบ"""
    pool: asyncpg.Pool | None = request.app.state.pool
    if pool is None:
        raise HTTPException(503, "ฐานข้อมูลยังไม่พร้อม — เปิดด้วย docker compose up -d db แล้วรีสตาร์ตเซิร์ฟเวอร์")
    async with pool.acquire() as conn:
        yield conn


# ---------------------------------------------------------------------------
# ส่วนที่ 3 — เรื่องคุกกี้ "ใครล็อกอินอยู่"
# ---------------------------------------------------------------------------
def make_session_cookie(response, user: dict) -> None:
    """เอาข้อมูลผู้ใช้ใส่ซอง เซ็นชื่อกำกับ แล้วแปะเป็นคุกกี้ติดตัวเบราว์เซอร์"""
    token = signer.dumps(user)          # แปลง dict เป็นข้อความ + เซ็นชื่อต่อท้าย (ถ้ามีคนแอบแก้ข้างใน ลายเซ็นจะไม่ตรง)
    response.set_cookie(
        COOKIE_NAME, token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,                  # JavaScript อ่านคุกกี้นี้ไม่ได้ (กันสคริปต์แปลกปลอมขโมย)
        samesite="lax",                 # ส่งคุกกี้เฉพาะตอนอยู่เว็บเรา กันเว็บอื่นยืมใช้
    )


def read_session(request: Request) -> dict | None:
    """แกะคุกกี้ออกมาดูว่าเป็นใคร — ถ้าไม่มีหรือถูกปลอม จะคืน None (แปลว่า "ยังไม่ล็อกอิน")"""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        return signer.loads(token)             # ตรวจลายเซ็นก่อน ถ้าผ่านค่อยแปลงกลับเป็น dict
    except BadSignature:                       # ลายเซ็นไม่ตรง = มีคนแก้คุกกี้ -> ถือว่าไม่ล็อกอิน
        return None


def require_login(request: Request) -> dict:
    """Dependency: route ไหนใส่อันนี้ = ต้องล็อกอินก่อน ไม่งั้นตอบ 401 ทันที"""
    user = read_session(request)
    if not user:
        raise HTTPException(401, "ยังไม่ได้ล็อกอิน")
    return user


# ---------------------------------------------------------------------------
# ส่วนที่ 4 — ส่งหน้าเว็บ
# ---------------------------------------------------------------------------
@app.get("/")
def page_login():
    """หน้าแรก = หน้าล็อกอิน"""
    return FileResponse(PAGES_DIR / "login.html")


# แต่ละหน้าเป็นไฟล์ .html ของตัวเองใน frontend/pages/ (1 หน้า = 1 ไฟล์ html + 1 ไฟล์ js)
# ตัว JS ในแต่ละหน้าจะเช็คเองว่าล็อกอินแล้วหรือยัง ถ้ายังจะเด้งกลับมาหน้า /

@app.get("/overview")
def page_overview():
    """ภาพรวม — การ์ดตัวเลขสรุป + กราฟ + แมตช์ล่าสุด"""
    return FileResponse(PAGES_DIR / "overview.html")


@app.get("/matches")
def page_matches():
    """แมตช์ — ตารางแมตช์ + รายรอบ + สกอร์บอร์ด"""
    return FileResponse(PAGES_DIR / "matches.html")


@app.get("/players")
def page_players():
    """นักแข่ง — อันดับ + รายละเอียดรายคน"""
    return FileResponse(PAGES_DIR / "players.html")


@app.get("/map")
def page_map():
    """แผนที่ — heatmap จุดที่คนตาย"""
    return FileResponse(PAGES_DIR / "map.html")


@app.get("/tactical")
def page_tactical():
    """แท็คติก — การดวลแรกของรอบ / จังหวะปะทะ / ผลของการปักระเบิด"""
    return FileResponse(PAGES_DIR / "tactical.html")


@app.get("/ml")
def page_ml():
    """โมเดล ML — โอกาสชนะรอบ + โมเดลกริด"""
    return FileResponse(PAGES_DIR / "ml.html")


@app.get("/main")
def page_main():
    """ที่อยู่เดิมสมัยยังเป็นหน้าเดียว — ส่งต่อไปหน้าภาพรวม ลิงก์เก่าจะได้ไม่พัง"""
    return RedirectResponse("/overview")


# ---------------------------------------------------------------------------
# ส่วนที่ 5 — ล็อกอิน / ออกจากระบบ
# ---------------------------------------------------------------------------
@app.get("/auth/steam/login")
def steam_login():
    """พาผู้ใช้ไปหน้าล็อกอินของ Steam (OpenID 2.0) พร้อมบอกว่าเสร็จแล้วให้ส่งกลับมาที่ /auth/steam/callback"""
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": f"{BASE_URL}/auth/steam/callback",
        "openid.realm": BASE_URL,
        "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
    }
    return RedirectResponse(f"{STEAM_OPENID_URL}?{urllib.parse.urlencode(params)}")


@app.get("/auth/steam/callback")
async def steam_callback(request: Request, conn: asyncpg.Connection = Depends(db)):
    """Steam ส่งผู้ใช้กลับมาที่นี่ — ต้องถาม Steam ซ้ำอีกรอบว่า "ข้อมูลชุดนี้มาจากคุณจริงไหม" กันคนปลอม URL"""
    params = dict(request.query_params)
    params["openid.mode"] = "check_authentication"      # เปลี่ยนโหมดเป็น "ขอตรวจสอบ" แล้วส่งกลับไปให้ Steam ทั้งชุด
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(STEAM_OPENID_URL, data=params)
    if "is_valid:true" not in r.text:
        return JSONResponse({"error": "Steam ไม่ยืนยันการล็อกอินนี้"}, status_code=401)

    claimed = params.get("openid.claimed_id", "")       # หน้าตา https://steamcommunity.com/openid/id/7656119...
    steamid = claimed.rsplit("/", 1)[-1]
    if not STEAM_ID_RE.match(steamid):
        return JSONResponse({"error": "SteamID ที่ได้กลับมาผิดรูปแบบ"}, status_code=400)

    profile = await fetch_steam_profile(steamid)
    user = {"steamid": steamid, **profile, "mode": "steam"}
    await save_user(conn, user)

    response = RedirectResponse("/overview", status_code=303)
    make_session_cookie(response, user)
    return response


@app.post("/auth/dev-login")
async def dev_login(request: Request, conn: asyncpg.Connection = Depends(db)):
    """โหมดทดสอบ: พิมพ์เลข Steam64 เข้าเองได้เลย ไม่ต้องมีกุญแจ API (ไว้ตอนพัฒนา/ตอนนำเสนอ)"""
    if not ALLOW_DEV_LOGIN:
        return JSONResponse({"error": "dev login ถูกปิดอยู่"}, status_code=403)

    body = await request.json()
    steamid = str(body.get("steamid", "")).strip()
    if not STEAM_ID_RE.match(steamid):              # ตรวจรูปแบบก่อนเสมอ อย่าเชื่อสิ่งที่ผู้ใช้พิมพ์
        return JSONResponse({"error": "SteamID64 ต้องเป็นตัวเลข 17 หลักขึ้นต้นด้วย 7656119"}, status_code=400)

    profile = await fetch_steam_profile(steamid)
    user = {"steamid": steamid, **profile, "mode": "dev"}   # mode="dev" ไว้ให้หน้าเว็บโชว์ป้าย "โหมดทดสอบ"
    await save_user(conn, user)

    response = JSONResponse({"ok": True, "user": user})
    make_session_cookie(response, user)
    return response


@app.post("/auth/logout")
def logout():
    """ลบคุกกี้ = ออกจากระบบ"""
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME)
    return response


async def save_user(conn: asyncpg.Connection, user: dict) -> None:
    """จดว่าใครล็อกอินเข้ามาลงตาราง users — เคยมีแล้วก็อัปเดตชื่อ/รูป/เวลาล่าสุด"""
    await conn.execute(
        """
        INSERT INTO users (steamid, name, avatar, profile_url, mode, last_login)
        VALUES ($1, $2, $3, $4, $5, CURRENT_TIMESTAMP)
        ON CONFLICT (steamid) DO UPDATE
        SET name = EXCLUDED.name, avatar = EXCLUDED.avatar, profile_url = EXCLUDED.profile_url,
            mode = EXCLUDED.mode, last_login = CURRENT_TIMESTAMP
        """,
        str(user.get("steamid", "")), str(user.get("name", "")), str(user.get("avatar", "")),
        str(user.get("profile_url", "")), str(user.get("mode", "dev")),
    )
    log(f"[DB] บันทึกผู้ใช้ {user.get('steamid')} ({user.get('mode')})")


async def fetch_steam_profile(steamid: str) -> dict:
    """ขอชื่อ/รูปโปรไฟล์จาก Steam Web API — ถ้าไม่มีกุญแจหรือโทรไม่ติด ใช้ค่าสำรองแทน"""
    fallback = {
        "name": f"ผู้เล่น {steamid[-4:]}",
        "avatar": "",
        "profile_url": f"https://steamcommunity.com/profiles/{steamid}",
    }
    if not STEAM_API_KEY:
        return fallback
    url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(url, params={"key": STEAM_API_KEY, "steamids": steamid})
        p = r.json()["response"]["players"][0]
        return {"name": p.get("personaname", fallback["name"]),
                "avatar": p.get("avatarfull", ""),
                "profile_url": p.get("profileurl", fallback["profile_url"])}
    except Exception:
        return fallback


# ---------------------------------------------------------------------------
# ส่วนที่ 6 — API สำหรับหน้าเว็บ (ตอบ JSON) — ทุกอันดึงจาก PostgreSQL
# ---------------------------------------------------------------------------
def rows(records) -> list[dict]:
    """asyncpg คืน Record มาให้ แปลงเป็น dict ธรรมดาเพื่อให้ FastAPI ส่งเป็น JSON ได้"""
    return [dict(r) for r in records]


@app.get("/api/health")
async def api_health(request: Request):
    """เช็คว่า DB ต่อได้ไหม มีข้อมูลเท่าไร — ไม่ต้องล็อกอิน ไว้ให้ docker/monitor ถาม"""
    pool = request.app.state.pool
    if pool is None:
        return JSONResponse({"ok": False, "db": "ยังไม่ได้ต่อ"}, status_code=503)
    try:
        async with pool.acquire() as conn:
            n = await conn.fetchrow(
                "SELECT (SELECT COUNT(*) FROM matches) AS matches, (SELECT COUNT(*) FROM kills) AS kills")
        return {"ok": True, "db": "ต่อได้", "matches": n["matches"], "kills": n["kills"]}
    except Exception as e:
        return JSONResponse({"ok": False, "db": str(e)}, status_code=503)


@app.get("/api/me")
def api_me(user: dict = Depends(require_login)):
    """หน้าเว็บถามว่า 'ตอนนี้ฉันล็อกอินอยู่ไหม เป็นใคร'"""
    return {"user": user}


@app.get("/api/config")
def api_config():
    """บอกหน้าเว็บว่าเซิร์ฟเวอร์ตั้งค่าไว้ยังไง (เช่น ต้องซ่อนกล่องโหมดทดสอบไหม)"""
    return {"allow_dev_login": ALLOW_DEV_LOGIN, "has_steam_key": bool(STEAM_API_KEY)}


@app.get("/api/stats")
async def api_stats(
    map_name: str | None = Query(None, alias="map", pattern=r"^de_[a-z0-9_]+$"),
    _: dict = Depends(require_login),
    conn: asyncpg.Connection = Depends(db),
):
    """สรุปภาพรวมให้หน้าหลัก — ใส่ ?map=de_mirage เพื่อดูเฉพาะแมพ (ไม่ใส่ = ทุกแมพ)

    รูปแบบคำตอบคงเดิมกับตอนที่ยังอ่านจาก csv หน้าเว็บจึงไม่ต้องแก้อะไร
    """
    where = "WHERE m.map_name = $1" if map_name else ""
    args = [map_name] if map_name else []
    base = f"FROM kills k JOIN rounds r ON r.id = k.round_id JOIN matches m ON m.id = r.match_id {where}"

    totals = await conn.fetchrow(f"""
        SELECT COUNT(*)                                          AS total_kills,
               COUNT(*) FILTER (WHERE k.headshot)                AS headshots,
               COUNT(*) FILTER (WHERE k.attacker_side = 'ct')    AS ct_kills,
               COUNT(*) FILTER (WHERE k.attacker_side = 't')     AS t_kills,
               ROUND(AVG(r.round_num)::numeric, 1)               AS avg_round,
               COUNT(DISTINCT m.id)                              AS matches,
               COUNT(DISTINCT r.id)                              AS rounds
        {base}""", *args)
    top_weapons = await conn.fetch(f"""
        SELECT k.weapon AS name, COUNT(*) AS count {base}
        GROUP BY k.weapon ORDER BY count DESC LIMIT 8""", *args)
    top_places = await conn.fetch(f"""
        SELECT k.victim_place AS name, COUNT(*) AS count {base}
        {"AND" if where else "WHERE"} k.victim_place IS NOT NULL
        GROUP BY k.victim_place ORDER BY count DESC LIMIT 8""", *args)

    # KPI ระดับรอบ/คน สำหรับการ์ดบนหน้า Dashboard — มาจาก view player_round_facts (ต้องมี player_rounds)
    # avg_* = ค่าเฉลี่ยต่อคนต่อรอบทั้งชุดข้อมูล ไว้เป็นเส้นอ้างอิงเวลาเทียบนักแข่งคนเดียว
    kpi = await conn.fetchrow(f"""
        SELECT COUNT(DISTINCT f.round_id) FILTER (WHERE r.winner_side = 'ct')                         AS ct_rounds_won,
               COUNT(DISTINCT f.round_id)                                                            AS rounds_with_facts,
               ROUND(AVG(f.damage)::numeric, 1)                                                      AS avg_adr,
               ROUND(100.0 * COUNT(*) FILTER (WHERE f.kast) / GREATEST(COUNT(*), 1), 1)              AS avg_kast
        FROM player_round_facts f JOIN rounds r ON r.id = f.round_id JOIN matches m ON m.id = r.match_id
        {where}""", *args)
    avg_rating = await conn.fetchval("SELECT ROUND(AVG(rating)::numeric, 2) FROM player_stats WHERE rounds >= 20")

    total = totals["total_kills"]
    return {
        "map": map_name,
        "matches": totals["matches"],
        "rounds": totals["rounds"],
        "total_kills": total,
        "headshots": totals["headshots"],
        "headshot_rate": round(totals["headshots"] / total * 100, 1) if total else 0.0,
        "avg_round": float(totals["avg_round"] or 0),
        "ct_kills": totals["ct_kills"],
        "t_kills": totals["t_kills"],
        "top_weapons": rows(top_weapons),
        "top_places": rows(top_places),
        # ใหม่ — เป็น 0/None ถ้ายังไม่ได้โหลด player_rounds (JSON schema_version < 3)
        "ct_round_win_rate": round(100 * kpi["ct_rounds_won"] / kpi["rounds_with_facts"], 1) if kpi["rounds_with_facts"] else None,
        "avg_adr": float(kpi["avg_adr"]) if kpi["avg_adr"] is not None else None,
        "avg_kast": float(kpi["avg_kast"]) if kpi["avg_kast"] is not None else None,
        "avg_rating": float(avg_rating) if avg_rating is not None else None,
    }


@app.get("/api/matches")
async def api_matches(_: dict = Depends(require_login), conn: asyncpg.Connection = Depends(db)):
    """รายชื่อแมตช์ทั้งหมดพร้อมสรุป (จาก view match_summary)"""
    return rows(await conn.fetch("SELECT * FROM match_summary ORDER BY id"))


@app.get("/api/matches/{match_id}")
async def api_match(match_id: int, _: dict = Depends(require_login), conn: asyncpg.Connection = Depends(db)):
    """แมตช์เดียวแบบละเอียด: สรุป + รายรอบ + สกอร์บอร์ดของนักแข่งในแมตช์นั้น"""
    match = await conn.fetchrow("SELECT * FROM match_summary WHERE id = $1", match_id)
    if not match:
        raise HTTPException(404, "ไม่พบแมตช์นี้")
    # รายรอบ + เศรษฐกิจ (มูลค่าอุปกรณ์ทั้งทีมตอน freeze จบ และ buy type) จาก view round_economy
    # LEFT JOIN เพื่อให้แมตช์ที่โหลดจาก JSON รุ่นเก่า (ไม่มี player_rounds) ยังตอบได้ แค่ช่องเศรษฐกิจว่าง
    rounds_ = await conn.fetch("""
        SELECT r.round_num, r.winner_side, r.end_reason,
               r.bomb_plant_tick IS NOT NULL AS bomb_planted,
               COUNT(k.id) AS kills,
               e.ct_equip, e.t_equip, e.ct_buy_type, e.t_buy_type
        FROM rounds r
        LEFT JOIN kills k ON k.round_id = r.id
        LEFT JOIN round_economy e ON e.round_id = r.id
        WHERE r.match_id = $1
        GROUP BY r.id, e.ct_equip, e.t_equip, e.ct_buy_type, e.t_buy_type
        ORDER BY r.round_num""", match_id)
    # สกอร์บอร์ดจาก view match_scoreboard — มี ADR / KAST / rating / ฝั่งที่เริ่ม (= ทีม) มาให้ครบ
    scoreboard = await conn.fetch("""
        SELECT steam_id::text AS steam_id, name, start_side, rounds,
               kills, deaths, assists, headshots, hs_rate, adr, kast, rating
        FROM match_scoreboard WHERE match_id = $1
        ORDER BY rating DESC, kills DESC""", match_id)
    if not scoreboard:                        # แมตช์รุ่นเก่าที่ไม่มี player_rounds — ถอยไปนับจาก kills ตรง ๆ
        scoreboard = await conn.fetch("""
            WITH mk AS (SELECT k.* FROM kills k JOIN rounds r ON r.id = k.round_id WHERE r.match_id = $1),
                 ids AS (SELECT attacker_id AS steam_id FROM mk WHERE attacker_id IS NOT NULL
                         UNION SELECT victim_id FROM mk)
            SELECT p.steam_id::text AS steam_id, p.name,
                   (SELECT COUNT(*) FROM mk WHERE attacker_id = p.steam_id)              AS kills,
                   (SELECT COUNT(*) FROM mk WHERE victim_id   = p.steam_id)              AS deaths,
                   (SELECT COUNT(*) FROM mk WHERE assister_id = p.steam_id)              AS assists,
                   (SELECT COUNT(*) FROM mk WHERE attacker_id = p.steam_id AND headshot) AS headshots
            FROM ids JOIN players p USING (steam_id)
            ORDER BY kills DESC, deaths ASC""", match_id)
    return {"match": dict(match), "rounds": rows(rounds_), "scoreboard": rows(scoreboard)}


@app.get("/api/players")
async def api_players(
    limit: int = Query(20, ge=1, le=200),
    min_matches: int = Query(1, ge=1),
    _: dict = Depends(require_login),
    conn: asyncpg.Connection = Depends(db),
):
    """นักแข่งเรียงตามคิล (จาก view player_stats) — ?min_matches=3 กรองคนที่เล่นน้อยออก"""
    recs = await conn.fetch("""
        SELECT steam_id::text AS steam_id, name, matches, rounds, kills, deaths, assists, headshots, kd, hs_rate,
               adr, kast, rating, win_rate, opening_rate, trade_rate, util_per_round
        FROM player_stats WHERE matches >= $1
        ORDER BY kills DESC LIMIT $2""", min_matches, limit)
    return rows(recs)


@app.get("/api/players/{steam_id}")
async def api_player(steam_id: int, _: dict = Depends(require_login), conn: asyncpg.Connection = Depends(db)):
    """นักแข่งคนเดียว: สถิติรวม + เรดาร์ 6 แกน + ปืนที่ใช้ + จุดที่ฆ่า/ตายบ่อย"""
    p = await conn.fetchrow("""
        SELECT steam_id::text AS steam_id, name, matches, rounds, kills, deaths, assists, headshots, kd, hs_rate,
               adr, kast, rating, win_rate, survival_rate, opening_kills, opening_deaths, opening_rate,
               trade_kills, trade_rate, traded_rate, util_per_round, clutch_attempts, clutch_wins
        FROM player_stats WHERE steam_id = $1""", steam_id)
    if not p:
        raise HTTPException(404, "ไม่พบนักแข่งคนนี้")
    # เรดาร์ 6 แกน = เปอร์เซ็นไทล์เทียบนักแข่งคนอื่นที่เล่น >= 20 รอบ (0 = ต่ำสุดในกลุ่ม, 100 = สูงสุด)
    #   AIM = ยิงหัว%  ENTRY = เปิดรอบ%  TRD = เทรดคิล/รอบ  UTIL = ระเบิด/รอบ  CLUTCH = ชนะ clutch%  SURV = รอด%
    #   ใช้เปอร์เซ็นไทล์แทนค่าดิบ เพราะแต่ละแกนหน่วยคนละอย่าง ค่าดิบวางบนเรดาร์เดียวกันไม่ได้
    #   clutch ต้องมีอย่างน้อย 3 ครั้งถึงนับ ไม่งั้นคนที่ชนะ 1/1 จะได้ 100% ทันที
    radar = await conn.fetchrow("""
        WITH pool AS (SELECT * FROM player_stats WHERE rounds >= 20),
        ranked AS (
            SELECT steam_id,
                   percent_rank() OVER (ORDER BY hs_rate)        AS aim,
                   percent_rank() OVER (ORDER BY opening_rate)   AS entry,
                   percent_rank() OVER (ORDER BY trade_rate)     AS trade,
                   percent_rank() OVER (ORDER BY util_per_round) AS util,
                   percent_rank() OVER (ORDER BY CASE WHEN clutch_attempts >= 3
                                                     THEN clutch_wins::numeric / clutch_attempts ELSE 0 END) AS clutch,
                   percent_rank() OVER (ORDER BY survival_rate)  AS surv,
                   COUNT(*) OVER ()                              AS pool_size
            FROM pool)
        SELECT * FROM ranked WHERE steam_id = $1""", steam_id)
    weapons = await conn.fetch("""
        SELECT weapon AS name, COUNT(*) AS count FROM kills
        WHERE attacker_id = $1 GROUP BY weapon ORDER BY count DESC LIMIT 8""", steam_id)
    kill_places = await conn.fetch("""
        SELECT attacker_place AS name, COUNT(*) AS count FROM kills
        WHERE attacker_id = $1 AND attacker_place IS NOT NULL
        GROUP BY attacker_place ORDER BY count DESC LIMIT 8""", steam_id)
    death_places = await conn.fetch("""
        SELECT victim_place AS name, COUNT(*) AS count FROM kills
        WHERE victim_id = $1 AND victim_place IS NOT NULL
        GROUP BY victim_place ORDER BY count DESC LIMIT 8""", steam_id)
    return {"player": dict(p),
            # เรดาร์เป็น 0-100 ต่อแกน; None ถ้าคนนี้เล่นไม่ถึง 20 รอบ (ยังไม่อยู่ในกลุ่มเทียบ)
            "radar": ({k: round(float(radar[k]) * 100) for k in ("aim", "entry", "trade", "util", "clutch", "surv")}
                      | {"pool_size": radar["pool_size"], "min_rounds": 20}) if radar else None,
            "weapons": rows(weapons),
            "kill_places": rows(kill_places), "death_places": rows(death_places)}


@app.get("/api/heatmap")
async def api_heatmap(
    map_name: str = Query(..., alias="map", pattern=r"^de_[a-z0-9_]+$"),
    side: str | None = Query(None, pattern=r"^(ct|t)$"),
    _: dict = Depends(require_login),
    conn: asyncpg.Connection = Depends(db),
):
    """พิกัดที่คนตายบนแมพหนึ่ง สำหรับวาด heatmap — ?side=ct เอาเฉพาะคนตายฝั่ง CT

    พิกัดเป็นระบบของเกม หน้าเว็บต้องแปลงด้วย assets/radars.json (pos_x, pos_y, scale) ก่อนวาด
    """
    recs = await conn.fetch("""
        SELECT k.victim_x AS x, k.victim_y AS y, k.victim_side AS side,
               k.weapon, k.headshot, k.victim_place AS place
        FROM kills k JOIN rounds r ON r.id = k.round_id JOIN matches m ON m.id = r.match_id
        WHERE m.map_name = $1 AND k.victim_x IS NOT NULL
          AND ($2::text IS NULL OR k.victim_side = $2)""", map_name, side)
    return {"map": map_name, "side": side, "count": len(recs), "points": rows(recs)}


@app.get("/api/radar")
def api_radar(
    map_name: str = Query(..., alias="map", pattern=r"^de_[a-z0-9_]+$"),
    _: dict = Depends(require_login),
):
    """ค่าปรับเทียบภาพเรดาร์ของแมพ — ไว้ให้หน้าเว็บแปลงพิกัดในเกมเป็นพิกเซลบนภาพ

    ค่าทั้งหมดอ่านจาก assets/radars.json ซึ่งเป็นแหล่งความจริงแหล่งเดียวของทั้งระบบ
    (สคริปต์ฝั่ง Python ก็อ่านไฟล์เดียวกันนี้ ตัวเลขสองฝั่งจึงไม่มีทางเพี้ยนจากกัน)

    สูตรแปลงพิกัด — หน้าเว็บเอาไปใช้ตรง ๆ ได้เลย
        pixel_x = (game_x - pos_x) / scale
        pixel_y = (pos_y - game_y) / scale      <- แกน y กลับด้าน เพราะในเกม y เพิ่มขึ้นด้านบน
                                                   แต่บนภาพ y เพิ่มลงด้านล่าง
    """
    data = json.loads((ASSETS_DIR / "radars.json").read_text(encoding="utf-8"))
    cal = data.get(map_name)
    if not cal:
        raise HTTPException(404, f"ยังไม่มีค่าปรับเทียบเรดาร์ของ {map_name} ใน assets/radars.json")

    return {
        "map": map_name,
        "image": "/assets" + cal["image"],   # cal["image"] เก็บเป็น "/maps/de_mirage.webp" -> เติม /assets ข้างหน้าให้เป็น URL จริง
        "size": cal["size"],                 # ภาพเป็นจัตุรัส ด้านละกี่พิกเซล
        "pos_x": cal["pos_x"],               # พิกัดเกมของมุมบนซ้ายของภาพ
        "pos_y": cal["pos_y"],
        "scale": cal["scale"],               # 1 พิกเซล = กี่หน่วยเกม
    }


# ===========================================================================
# ส่วนที่ 6 — วิเคราะห์แท็คติก (Tactical Analysis)
#
# ทุกตัวเลขในนี้คำนวณสด ๆ จากฐานข้อมูล ไม่มีค่าที่พิมพ์ทิ้งไว้เอง
# แนวคิดหลักคือ "การดวลแรกของรอบ" (opening duel) = คิลแรกสุดของรอบนั้น
# เพราะใครชนะการดวลแรก มักลากยาวไปชนะทั้งรอบ
# ===========================================================================

# SQL ก้อนนี้ถูกเอาไปแปะหน้าคำถามทุกข้อในหน้านี้ จึงเขียนไว้ที่เดียว
# DISTINCT ON (k.round_id) + ORDER BY k.round_id, k.tick
#   = "ของแต่ละรอบ เอาแถวเดียว คือแถวที่ tick น้อยที่สุด" -> ได้คิลแรกของรอบ
FIRST_KILL_CTE = """
WITH fk AS (
    SELECT DISTINCT ON (k.round_id)
           k.round_id,
           k.attacker_side,
           k.attacker_place,
           k.victim_place,
           k.tick,
           r.start_tick,
           r.winner_side,
           r.end_reason,
           r.bomb_plant_tick,
           m.tickrate
    FROM kills k
    JOIN rounds  r ON r.id = k.round_id
    JOIN matches m ON m.id = r.match_id
    WHERE m.map_name = $1
    ORDER BY k.round_id, k.tick
)
"""


@app.get("/api/tactical")
async def api_tactical(
    map_name: str = Query(..., alias="map", pattern=r"^de_[a-z0-9_]+$"),
    side: str = Query("t", pattern=r"^(ct|t)$"),        # มองจากมุมของฝั่งไหน
    _: dict = Depends(require_login),
    conn: asyncpg.Connection = Depends(db),
):
    """สรุปแท็คติกของแมพหนึ่ง มองจากมุมฝั่งที่เลือก (ct หรือ t)

    ตอบกลับ 5 ก้อน
      summary  ภาพรวม: กี่รอบ ชนะกี่รอบ ปักระเบิดกี่รอบ เวลาปะทะแรกเฉลี่ย
      opening  การดวลแรกของรอบ แยกตามตำแหน่งที่ยืน
      timing   ปะทะแรกเกิดตอนวินาทีที่เท่าไร แล้วรอบนั้นชนะไหม
      endings  รอบจบด้วยสาเหตุอะไรบ้าง
      bomb     ปักระเบิดแล้วชนะบ่อยกว่าไม่ปักไหม
    """
    # ---- 1) ภาพรวม -------------------------------------------------------
    summary = await conn.fetchrow(f"""
        {FIRST_KILL_CTE}
        SELECT COUNT(*)                                              AS rounds,
               COUNT(*) FILTER (WHERE winner_side = $2)              AS wins,
               COUNT(*) FILTER (WHERE bomb_plant_tick IS NOT NULL)   AS planted,
               ROUND(AVG((tick - start_tick)::numeric / tickrate), 1) AS avg_first_contact
        FROM fk
        WHERE start_tick IS NOT NULL""", map_name, side)
    # (tick - start_tick) / tickrate = จำนวน tick ตั้งแต่เริ่มรอบ หารด้วย tick ต่อวินาที = วินาที
    # FILTER (WHERE ...) = "นับเฉพาะแถวที่เข้าเงื่อนไข" เขียนสั้นกว่าใช้ CASE WHEN

    if not summary or not summary["rounds"]:
        raise HTTPException(404, f"ไม่มีข้อมูลรอบของแมพ {map_name}")

    # ---- 2) การดวลแรก แยกตามตำแหน่ง --------------------------------------
    # ถ้าฝั่งเราเป็นคนยิง -> ตำแหน่งของเราคือ attacker_place
    # ถ้าฝั่งเราเป็นคนโดนยิง -> ตำแหน่งของเราคือ victim_place
    opening = await conn.fetch(f"""
        {FIRST_KILL_CTE}
        SELECT COALESCE(CASE WHEN attacker_side = $2 THEN attacker_place
                             ELSE victim_place END, '(ไม่ทราบ)')     AS place,
               COUNT(*)                                              AS duels,
               COUNT(*) FILTER (WHERE attacker_side = $2)            AS won,
               COUNT(*) FILTER (WHERE winner_side  = $2)             AS round_wins
        FROM fk
        GROUP BY 1
        HAVING COUNT(*) >= 5
        ORDER BY duels DESC
        LIMIT 8""", map_name, side)
    # COALESCE(ก, ข) = ถ้า ก เป็น NULL ให้ใช้ ข แทน
    # HAVING COUNT(*) >= 5 = ตัดตำแหน่งที่เจอไม่ถึง 5 ครั้งทิ้ง เพราะเปอร์เซ็นต์จากข้อมูล 1-2 ครั้งเชื่อไม่ได้

    # ---- 3) ปะทะแรกเกิดตอนวินาทีที่เท่าไร ---------------------------------
    timing = await conn.fetch(f"""
        {FIRST_KILL_CTE}
        SELECT CASE WHEN sec < 20 THEN '0-20 วิ'
                    WHEN sec < 40 THEN '20-40 วิ'
                    WHEN sec < 60 THEN '40-60 วิ'
                    ELSE '60 วิ ขึ้นไป' END                          AS bucket,
               COUNT(*)                                              AS rounds,
               COUNT(*) FILTER (WHERE winner_side = $2)              AS wins
        FROM (SELECT (tick - start_tick)::numeric / tickrate AS sec, winner_side
              FROM fk WHERE start_tick IS NOT NULL) q
        GROUP BY 1
        ORDER BY MIN(sec)""", map_name, side)
    # ORDER BY MIN(sec) = เรียงกลุ่มตามวินาทีที่น้อยที่สุดในกลุ่มนั้น (ไม่งั้นจะเรียงตามตัวอักษรไทยมั่ว)

    # ---- 4) รอบจบด้วยอะไร -------------------------------------------------
    endings = await conn.fetch("""
        SELECT COALESCE(r.end_reason, '(ไม่ทราบ)')      AS reason,
               COUNT(*)                                 AS rounds,
               COUNT(*) FILTER (WHERE r.winner_side = $2) AS wins
        FROM rounds r JOIN matches m ON m.id = r.match_id
        WHERE m.map_name = $1
        GROUP BY 1 ORDER BY rounds DESC""", map_name, side)

    # ---- 5) ปักระเบิดแล้วต่างกันไหม ---------------------------------------
    bomb = await conn.fetch("""
        SELECT CASE WHEN r.bomb_plant_tick IS NOT NULL THEN 'ปักระเบิดแล้ว'
                    ELSE 'ไม่ได้ปัก' END                 AS state,
               COUNT(*)                                 AS rounds,
               COUNT(*) FILTER (WHERE r.winner_side = $2) AS wins
        FROM rounds r JOIN matches m ON m.id = r.match_id
        WHERE m.map_name = $1
        GROUP BY 1 ORDER BY rounds DESC""", map_name, side)

    return {
        "map": map_name,
        "side": side,
        "summary": {
            "rounds": summary["rounds"],
            "wins": summary["wins"],
            "planted": summary["planted"],
            "avg_first_contact": float(summary["avg_first_contact"] or 0),
        },
        "opening": rows(opening),
        "timing": rows(timing),
        "endings": rows(endings),
        "bomb": rows(bomb),
    }


# ===========================================================================
# ส่วนที่ 7 — ผลจากโมเดล ML
#
# เราไม่เทรนโมเดลในเซิร์ฟเวอร์นี้ (ช้าและกินแรม) สคริปต์ใน pipeline/ เทรนเสร็จ
# แล้วเขียนคำตอบทั้งหมดลงไฟล์ json ไว้ให้ เซิร์ฟเวอร์แค่หยิบไฟล์นั้นส่งต่อ
#     python pipeline/round_win.py   ->  output/round_win.json
#     python pipeline/grid_ml.py     ->  output/grid_ml.json
# ===========================================================================

def read_output_json(filename: str, how_to_make: str) -> dict:
    """อ่านไฟล์ json ในโฟลเดอร์ output/ — ถ้ายังไม่มี บอกวิธีสร้างไปเลย"""
    f = ROOT / "output" / filename
    if not f.exists():
        raise HTTPException(404, f"ยังไม่มีไฟล์ output/{filename} — สร้างด้วย: {how_to_make}")
    return json.loads(f.read_text(encoding="utf-8"))   # loads = แปลงข้อความ json ให้เป็น dict


@app.get("/api/ml/round-win")
def api_ml_round_win(_: dict = Depends(require_login)):
    """โมเดลโอกาสชนะรอบ — ตารางเปิดค่า P(CT ชนะ) ของทุกสถานะที่เป็นไปได้

    คีย์ในตารางหน้าตาแบบ "3v2|0|20-40s" = CT เหลือ 3, T เหลือ 2, ยังไม่ปักระเบิด, วินาทีที่ 20-40
    """
    return read_output_json("round_win.json", "python pipeline/round_win.py")


@app.get("/api/ml/grid")
def api_ml_grid(_: dict = Depends(require_login)):
    """โมเดลกริด — แบ่งแมพเป็นช่อง ๆ แล้วทายว่าการดวลในช่องนั้นฝั่งไหนได้เปรียบ

    ตัดฟิลด์หนัก ๆ ออกก่อนส่ง (ภาพ mask กับจุดตายดิบ 7 พันจุด) เพราะหน้าเว็บไม่ได้ใช้
    เหลือแต่คะแนนโมเดลกับค่ารายช่อง ไฟล์จะได้เล็กลงจาก 160 KB เหลือ ~40 KB
    """
    d = read_output_json("grid_ml.json", "python pipeline/grid_ml.py")
    for heavy in ("play_mask", "kills"):
        d.pop(heavy, None)          # .pop(คีย์, None) = ลบคีย์นี้ทิ้ง ถ้าไม่มีก็ไม่ต้องพัง
    d["cells"] = sorted(d["cells"], key=lambda c: -c["kills"])[:40]
    # sorted(..., key=lambda c: -c["kills"]) = เรียงจากช่องที่มีคนตายเยอะสุดไปน้อยสุด (ติดลบ = กลับด้าน)
    # [:40] = เอาแค่ 40 ช่องแรก พอสำหรับโชว์ตาราง
    return d
