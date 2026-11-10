# -*- coding: utf-8 -*-
"""
backend/routes/application.py — ประกอบ FastAPI และ HTTP routes ของเว็บ CS2 Analytics

เปรียบเทียบง่าย ๆ: ไฟล์นี้คือ "พนักงานหลังเคาน์เตอร์"
  - หน้าเว็บ (frontend/) = ลูกค้าที่มายืนหน้าเคาน์เตอร์
  - ไฟล์นี้ = พนักงานที่คอยรับคำสั่ง ไปหยิบของจากคลัง (PostgreSQL) แล้วส่งกลับไปให้

หน้าที่ของไฟล์นี้มี 3 อย่าง (หน้าเว็บทั้งหมดอยู่ที่ frontend/ — React)
  1) ล็อกอินด้วย Steam หรือ guest session (backend/services/auth.py)
  2) จำว่า "ใครล็อกอินอยู่" ด้วย JWT ในคุกกี้ httpOnly (JavaScript อ่านไม่ได้)
  3) ตอบ /api/* — ดึงสถิติจากฐานข้อมูลแล้วส่งเป็น JSON ให้หน้าเว็บเอาไปวาด

ข้อมูลอยู่ใน PostgreSQL (ตาราง: backend/models/ + Alembic, view: backend/models/views.sql, โหลดผ่าน /api/demos หรือ backend/services/etl.py)
ไฟล์นี้ไม่อ่าน csv เองแล้ว — อ่านผ่าน SQL อย่างเดียว จะได้ filter/รวมข้อมูลได้เร็วโดยไม่ต้องโหลดทั้งตารางเข้าแรม

รัน:  python -m uvicorn backend.app:app --reload   (ในเครื่อง — หน้าเว็บ npm run dev ส่งต่อ /api มาที่นี่)
ผู้ใช้ไม่เข้า API ตรง ๆ: เปิดหน้าเว็บ แล้วหน้าเว็บ (หรือ nginx ใน Docker) ส่ง /api /auth /assets มาให้
Swagger: <หน้าเว็บ>/api/docs
"""

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
import mimetypes
import os
import re
import secrets
import sys
import time
import traceback
import urllib.parse
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import asyncpg
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool  # เอางานหนักที่ไม่ใช่ async ไปรันในเธรดแยก ไม่ให้เซิร์ฟเวอร์ค้าง
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from backend.config.database import (  # noqa: F401  (load_dotenv ทำงานตอน import)
    DATABASE_URL,
    apply_schema,
    create_pool,
    redacted_url,
)
from backend.config.settings import ASSETS_DIR, DEMOS_DIR, FRONTEND_URL, GUEST_DEMO_FILE, PUBLIC_URL
from backend.jobs import JSON_DIR, QueueUnavailable, enqueue_parse, job_state, queue_health  # คิวงาน parse (Sprint 2)
from backend.repositories.coach import load_coach_facts
from backend.routes.reports import create_report_router
from backend.services import auth  # ล็อกอิน: Steam OpenID + JWT ใน httpOnly cookie
from backend.services.coach import build_coach_samples, load_coach_model, recommend_round
from backend.services.features import assign_teams, rating2_approx
from backend.services.opening import build_opening_rounds, match_date, select_matches
from backend.services.player_profiles import build_profile, search_players
from backend.services.player_roles import build_match_profiles, compatibility_reason, infer_match, load_role_model
from backend.services.review import (
    HEATMAP_EVENTS,
    build_economy,
    build_round_detail,
    build_round_list,
    build_round_positions,
    deaths_overlay,
    heatmap_points,
    load_grid_model,
    radar_frame,
)
from backend.utilities.logging import log

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
MAX_DEMO_MB = int(os.environ.get("MAX_DEMO_MB", "600"))   # เพดานขนาดไฟล์ที่ยอมรับ กันคนอัปของใหญ่จนดิสก์เต็ม
DEMO_NAME_RE = re.compile(r"^[A-Za-z0-9._()-]{1,120}\.dem$", re.IGNORECASE) # การตั้งชื่อ

DEMO_MAGIC = b"PBDEMS2\x00"

UPLOAD_MAX_PER_HOUR = int(os.environ.get("UPLOAD_MAX_PER_HOUR", "20"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


# ---------------------------------------------------------------------------
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


app = FastAPI(title="CS2 Analytics API", lifespan=lifespan,
              docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")  # URL ที่ขึ้นต้นด้วย /assets ให้ไปหยิบไฟล์จริงใน assets/ (ภาพเรดาร์)

mimetypes.add_type("image/webp", ".webp")


# ---------------------------------------------------------------------------
#
#
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    log(f"[ERROR] {request.method} {request.url.path} -> {type(exc).__name__}: {exc}\n{traceback.format_exc()}")
    return JSONResponse(status_code=500, content={"detail": "เซิร์ฟเวอร์มีข้อผิดพลาดภายใน — ดูรายละเอียดได้ใน log ของเซิร์ฟเวอร์"})


async def db(request: Request) -> asyncpg.Connection:
    """Dependency: ขอ connection จากบ่อหนึ่งเส้นให้ route นี้ใช้ แล้วคืนอัตโนมัติเมื่อจบ"""
    pool: asyncpg.Pool | None = request.app.state.pool
    if pool is None:
        raise HTTPException(503, "ฐานข้อมูลยังไม่พร้อม — เปิดด้วย docker compose up -d db แล้วรีสตาร์ตเซิร์ฟเวอร์")
    async with pool.acquire() as conn:
        yield conn


async def _optional_columns(conn: asyncpg.Connection, table: str, names: tuple[str, ...]) -> set[str]:
    """Read columns on the table resolved by the connection's search path."""
    return {
        row["attname"] for row in await conn.fetch("""
            SELECT attname FROM pg_attribute
            WHERE attrelid = to_regclass($1) AND attname = ANY($2::text[])
              AND attnum > 0 AND NOT attisdropped""", table, list(names))
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def require_viewer(request: Request) -> dict:
    """Dependency: route ไหนใส่อันนี้ = ต้องมี session ก่อน — ประตูบานเดียวของทั้งระบบ

    คืนค่าเหมือน auth.viewer_from_token():
        {"type": "steam", "id": int,  "username": str,  "guest_id": None}
        {"type": "guest", "id": None, "username": None, "guest_id": str}

    ตอนนี้ทั้งสองแบบมีสิทธิ์เท่ากันทุก endpoint ยังไม่แบ่ง role
    ทุก route เรียกตัวนี้ตัวเดียว เวลาจะแยกสิทธิ์จริงจึงแก้ได้ที่นี่กับ can_modify_match()
    ไม่ต้องไปตามแก้ 13 route (ดูตัวอย่างกฎที่จะเขียนได้ในคอมเมนต์ของ can_modify_match)
    """
    viewer = auth.viewer_from_token(request.cookies.get(auth.COOKIE_NAME))
    if not viewer:
        raise HTTPException(401, "ยังไม่ได้เข้าใช้งาน หรือ session หมดอายุ — ล็อกอินด้วย Steam หรือกดเข้าชมที่หน้าแรก")
    return viewer


# ---------------------------------------------------------------------------
#
# ---------------------------------------------------------------------------

#
#
AUTH_MAX_TRIES = int(os.environ.get("AUTH_MAX_TRIES", "20"))     # กี่ครั้งต่อหนึ่งช่วงเวลา
AUTH_WINDOW_SEC = int(os.environ.get("AUTH_WINDOW_SEC", "300"))  # ความยาวช่วงเวลา (วินาที)
_auth_hits: dict[str, tuple[int, float]] = {}                    # ip -> (นับได้กี่ครั้ง, ช่วงเวลานี้เริ่มเมื่อไร)


def _client_ip(request: Request) -> str:
    return (request.client.host if request.client else None) or "unknown"


def rate_limit_auth(request: Request) -> None:
    """Dependency: เกินโควตาแล้วตอบ 429 ทันที โดยไม่ต้องโทรหา Steam หรือแตะฐานข้อมูล"""
    ip = _client_ip(request)
    now = time.monotonic()
    hits, started = _auth_hits.get(ip, (0, now))
    if now - started > AUTH_WINDOW_SEC:       # ช่วงเวลาเก่าหมดอายุ เริ่มนับใหม่
        hits, started = 0, now
    hits += 1
    _auth_hits[ip] = (hits, started)

    if len(_auth_hits) > 1000:
        for k, (_, t) in list(_auth_hits.items()):
            if now - t > AUTH_WINDOW_SEC:
                _auth_hits.pop(k, None)

    if hits > AUTH_MAX_TRIES:
        wait = int(AUTH_WINDOW_SEC - (now - started))
        raise HTTPException(429, f"เรียกเข้าสู่ระบบบ่อยเกินไป — รออีก {wait} วินาทีแล้วลองใหม่")


def _safe_next(next_path: str | None) -> str:
    """กัน open redirect: รับเฉพาะ path ในเว็บเรา (ขึ้นต้น / แต่ไม่ใช่ //) — เหมือน safeNext ฝั่งหน้าเว็บ"""
    p = (next_path or "").strip()
    unsafe_chars = "\\" in p or any(ord(char) < 32 or ord(char) == 127 for char in p)
    return p if not unsafe_chars and p.startswith("/") and not p.startswith("//") and not p.startswith("/login") else "/player"


def _public_base(request: Request) -> str:
    """ที่อยู่ที่เบราว์เซอร์เห็น (ต้องมีพอร์ตด้วย ไม่งั้น Steam ส่งผู้ใช้กลับผิดที่) — nginx ส่ง Host จริงมาให้ทาง $http_host"""
    if PUBLIC_URL:
        return PUBLIC_URL
    host = request.headers.get("host") or request.url.netloc
    scheme = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
    return f"{scheme}://{host}"


def _frontend_base(request: Request) -> str:
    """Frontend origin for browser redirects; the proxy origin is the default."""
    if FRONTEND_URL:
        return FRONTEND_URL
    base = _public_base(request)
    parsed = urllib.parse.urlsplit(base)
    if parsed.hostname in ("localhost", "127.0.0.1") and parsed.port == 8000:
        return f"{parsed.scheme}://{parsed.hostname}:3000"
    return base


def _frontend_redirect(request: Request, path: str) -> RedirectResponse:
    return RedirectResponse(f"{_frontend_base(request)}{path}", status_code=303)


@app.get("/auth/steam/login")
def auth_steam_login(request: Request, next: str = "/player"):
    """พาไปล็อกอินที่ Steam แล้วให้ส่งกลับมาที่ /auth/steam/callback (พก next ไปด้วยใน return_to)"""
    base = _public_base(request)
    return_to = f"{base}/auth/steam/callback?next={urllib.parse.quote(_safe_next(next), safe='/')}"
    return RedirectResponse(auth.steam_login_url(return_to, base + "/"))


@app.get("/auth/steam/callback")
async def auth_steam_callback(request: Request, next: str = "/player",
                              _rl: None = Depends(rate_limit_auth),
                              conn: asyncpg.Connection = Depends(db)):
    """Steam ส่งกลับมาที่นี่ — ตรวจกับ Steam ก่อนเสมอ ผ่านแล้วค่อยสร้าง/หาบัญชีแล้วติดคุกกี้ JWT"""
    params = dict(request.query_params)
    expected_return_to = (f"{_public_base(request)}/auth/steam/callback"
                          f"?next={urllib.parse.quote(_safe_next(next), safe='/')}")
    steamid = await run_in_threadpool(auth.verify_steam_openid, params,
                                     expected_return_to=expected_return_to)
    if not steamid:
        log("[AUTH] Steam ไม่ยืนยันการล็อกอินนี้")
        return _frontend_redirect(request, "/login?err=steam")
    if not auth.steam_id_allowed(steamid):
        log(f"[AUTH] SteamID {steamid} ไม่อยู่ใน STEAM_ALLOWED_IDS")
        return _frontend_redirect(request, "/login?err=steam_denied")

    profile = await run_in_threadpool(auth.steam_persona, steamid)
    row = await conn.fetchrow("SELECT id, username FROM accounts WHERE steam_id = $1", int(steamid))
    if row is None:
        for username in (auth.username_for_steam(profile["name"], steamid), f"steam_{steamid}"):
            try:
                row = await conn.fetchrow("""
                    INSERT INTO accounts (username, steam_id, avatar, last_login)
                    VALUES ($1, $2, $3, now()) RETURNING id, username""",
                    username, int(steamid), profile["avatar"])
                break
            except asyncpg.UniqueViolationError:
                continue
        if row is None:
            return _frontend_redirect(request, "/login?err=steam_account")
        log(f"[AUTH] สร้างบัญชีจาก Steam {steamid} -> {row['username']} (id {row['id']})")
    else:
        await conn.execute("UPDATE accounts SET last_login = now(), avatar = COALESCE($2, avatar) WHERE id = $1",
                           row["id"], profile["avatar"])

    response = _frontend_redirect(request, _safe_next(next))
    auth.set_auth_cookie(response, auth.create_token(row["id"], row["username"]), persistent=True)
    return response


@app.post("/auth/guest")
def auth_guest(request: Request, _: None = Depends(rate_limit_auth)):
    """เข้าชมโดยไม่ล็อกอิน — ออกคุกกี้ session ที่ไม่มีแถวใน accounts

    คุกกี้ระบุว่า session นี้เป็น Guest เพื่อบังคับสิทธิ์อ่านอย่างเดียวและจำกัดให้ดูเดโมตัวอย่าง
    หน้าเว็บถาม /auth/me ที่เดียวได้โดยไม่ต้องเก็บสถานะซ้อนใน localStorage

    ผู้ที่เคยล็อกอิน Steam อยู่แล้วเรียกอันนี้ = ลดสิทธิ์ตัวเอง จึงกันไว้ ให้กดออกจากระบบก่อน
    """
    if auth.viewer_from_token(request.cookies.get(auth.COOKIE_NAME)) is not None:
        raise HTTPException(409, "มี session อยู่แล้ว — กดออกจากระบบก่อนถ้าต้องการเปลี่ยนเป็นโหมดเยี่ยมชม")
    guest_id = auth.new_guest_id()
    response = JSONResponse({"user": {"type": auth.GUEST, "id": None, "username": None, "guest_id": guest_id}})
    auth.set_auth_cookie(response, auth.create_guest_token(guest_id=guest_id), persistent=False)
    log(f"[AUTH] เข้าโหมดเยี่ยมชม {guest_id}")
    return response


@app.get("/auth/me")
async def auth_me(request: Request, viewer: dict = Depends(require_viewer)):
    """หน้าเว็บถามว่า 'ตอนนี้ฉันเข้าใช้งานอยู่ไหม เป็นใคร' — ไม่มี session ตอบ 401

    หน้าเว็บดูฟิลด์ type ตัวเดียวเพื่อรู้ว่าเป็นผู้ใช้ Steam หรือโหมดเยี่ยมชม

    avatar (รูปโปรไฟล์ Steam) อ่านจากฐานข้อมูล แต่ถ้าฐานข้อมูลล่มก็ยังตอบว่าเข้าใช้งานอยู่ได้
    เพราะตัวตนอยู่ใน JWT อยู่แล้ว — ไม่ควรให้ทั้งเว็บเด้งออกเพราะดึงรูปไม่ได้
    """
    avatar = None
    pool = request.app.state.pool
    if viewer["type"] == auth.STEAM and pool is not None:
        try:
            async with pool.acquire() as conn:
                account = await conn.fetchrow("SELECT steam_id, avatar FROM accounts WHERE id = $1", viewer["id"])
                avatar = account["avatar"] if account else None
                if account and not avatar:
                    profile = await run_in_threadpool(auth.steam_persona, str(account["steam_id"]))
                    avatar = profile["avatar"]
                    if avatar:
                        await conn.execute("UPDATE accounts SET avatar = $2 WHERE id = $1", viewer["id"], avatar)
        except Exception as e:                                    # noqa: BLE001 — รูปหายดีกว่า session หลุด
            log(f"[AUTH] ดึง avatar ของ user {viewer['id']} ไม่ได้: {e}")
    return {"user": {**viewer, "avatar": avatar}}


@app.post("/auth/logout")
def auth_logout():
    """ลบคุกกี้ = ออกจากระบบ (JWT เป็น stateless ไม่มีอะไรต้องลบในฐานข้อมูล)"""
    response = JSONResponse({"ok": True})
    auth.clear_auth_cookie(response)
    return response


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
def rows(records) -> list[dict]:
    """asyncpg คืน Record มาให้ แปลงเป็น dict ธรรมดาเพื่อให้ FastAPI ส่งเป็น JSON ได้"""
    return [dict(r) for r in records]


@app.get("/api/health")
async def api_health(request: Request):
    """เช็คว่า DB ต่อได้ไหม มีข้อมูลเท่าไร — ไม่ต้องล็อกอิน ไว้ให้ docker/monitor ถาม

    จำนวนแมตช์/คิลเป็นตัวเลขรวม ไม่มีชื่อคนหรือข้อมูลของแมตช์ใด — หน้า /login เอาไปโชว์
    ก่อนผู้ใช้ล็อกอิน (frontend/src/LoginPage.tsx) จึงตั้งใจให้เรียกได้โดยไม่ต้องมี session
    """
    pool = request.app.state.pool
    if pool is None:
        return JSONResponse({"ok": False, "db": "ยังไม่ได้ต่อ"}, status_code=503)
    try:
        async with pool.acquire() as conn:
            n = await conn.fetchrow(
                "SELECT (SELECT COUNT(*) FROM matches) AS matches, (SELECT COUNT(*) FROM kills) AS kills")
        return {"queue": await run_in_threadpool(queue_health), "ok": True, "db": "ต่อได้", "matches": n["matches"], "kills": n["kills"]}
    except Exception as e:
        log(f"[HEALTH] database check failed: {e}")
        return JSONResponse({"ok": False, "db": "unavailable"}, status_code=503)


async def guest_demo_file(conn: asyncpg.Connection) -> str:
    """Return the single completed upload exposed to guest sessions."""
    if GUEST_DEMO_FILE:
        demo = await conn.fetchval(
            "SELECT demo_file FROM matches WHERE demo_file = $1 AND source = 'upload' AND status = 'done'",
            GUEST_DEMO_FILE,
        )
    else:
        demo = await conn.fetchval("""
            SELECT demo_file FROM matches
            WHERE source = 'upload' AND status = 'done'
            ORDER BY id LIMIT 1
        """)
    if not demo:
        raise HTTPException(503, "ยังไม่มีเดโมตัวอย่างที่พร้อมให้ผู้เยี่ยมชมดู")
    return demo


async def require_match_access(
    conn: asyncpg.Connection,
    viewer: dict,
    *,
    demo_file: str | None = None,
    match_id: int | None = None,
) -> str | None:
    """Restrict guest sessions to the configured single sample demo."""
    if viewer["type"] != auth.GUEST:
        return demo_file
    allowed = await guest_demo_file(conn)
    actual = demo_file
    if match_id is not None:
        actual = await conn.fetchval(
            "SELECT demo_file FROM matches WHERE id = $1 AND source = 'upload'", match_id
        )
    if actual != allowed:
        raise HTTPException(403, "โหมดเยี่ยมชมดูได้เฉพาะเดโมตัวอย่าง")
    return allowed

#เช็คผู้ใช้Steam
def require_steam_viewer(viewer: dict) -> None:
    if viewer["type"] != auth.STEAM:
        raise HTTPException(403, "ฟังก์ชันนี้ต้องล็อกอินด้วย Steam")


@app.get("/api/matches")
async def api_matches(viewer: dict = Depends(require_viewer), conn: asyncpg.Connection = Depends(db)):
    """รายชื่อแมตช์ที่ผู้ใช้อัปโหลด; ชุดฝึกโมเดลไม่ออกผ่านหน้ารายการสาธารณะ"""
    if viewer["type"] == auth.GUEST:
        demo = await guest_demo_file(conn)
        return rows(await conn.fetch(
            "SELECT * FROM match_summary WHERE source = 'upload' AND demo_file = $1", demo
        ))
    return rows(await conn.fetch("SELECT * FROM match_summary WHERE source = 'upload' ORDER BY id"))


@app.delete("/api/matches/{match_id}")
async def api_delete_match(match_id: int, viewer: dict = Depends(require_viewer), conn: asyncpg.Connection = Depends(db)):
    """Delete an uploaded demo and its parsed data after its parser job finishes."""
    moved: list[tuple[Path, Path]] = []
    try:
        async with conn.transaction():
            record = await conn.fetchrow(
                "SELECT id, demo_file, source, status, uploaded_by, uploader_guest FROM matches WHERE id = $1 FOR UPDATE",
                match_id,
            )
            if not record or record["source"] != "upload":
                raise HTTPException(404, "ไม่พบแมตช์นี้")
            match = dict(record)
            if not can_modify_match(match, viewer):
                raise HTTPException(403, "ไม่มีสิทธิ์ลบแมตช์นี้")
            if match["status"] in ("queued", "parsing"):
                raise HTTPException(409, "รอให้แกะเดโมเสร็จก่อนจึงจะลบได้")
            demo_file = match["demo_file"]
            if Path(demo_file).name != demo_file or not DEMO_NAME_RE.fullmatch(demo_file):
                raise HTTPException(409, "ชื่อไฟล์เดโมไม่ถูกต้อง ไม่สามารถลบไฟล์ได้")
            token = secrets.token_hex(8)
            for original in (DEMOS_DIR / demo_file, JSON_DIR / f"{Path(demo_file).stem}.json"):
                if original.exists():
                    tombstone = original.with_name(f".{original.name}.{token}.deleted")
                    original.replace(tombstone)
                    moved.append((original, tombstone))
            await conn.execute("DELETE FROM matches WHERE id = $1", match_id)
    except Exception:
        for original, tombstone in reversed(moved):
            if tombstone.exists() and not original.exists():
                tombstone.replace(original)
        raise

    # Only remove tombstones; a new upload may already reuse the original filename.
    cleanup_failed = []
    for _, path in moved:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            cleanup_failed.append(path.name)
    return {"deleted": True, "cleanup_failed": cleanup_failed}


@app.get("/api/matches/{match_id}")
async def api_match(match_id: int, viewer: dict = Depends(require_viewer), conn: asyncpg.Connection = Depends(db)):
    """แมตช์เดียวแบบละเอียด: สรุป + รายรอบ + สกอร์บอร์ดของนักแข่งในแมตช์นั้น"""
    match = await conn.fetchrow(
        "SELECT * FROM match_summary WHERE id = $1 AND source = 'upload'", match_id)
    if not match:
        raise HTTPException(404, "ไม่พบแมตช์นี้")
    await require_match_access(conn, viewer, match_id=match_id)
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
    feats = await conn.fetch("""
        SELECT pr.steam_id::text AS steam_id,
               COUNT(*) FILTER (WHERE pr.opening_kill)       AS opening_kills,
               COUNT(*) FILTER (WHERE pr.opening_death)      AS opening_deaths,
               COALESCE(SUM(pr.trade_kills), 0)              AS trade_kills,
               COUNT(*) FILTER (WHERE pr.was_traded)         AS traded_deaths,
               COUNT(*) FILTER (WHERE pr.clutch_vs > 0)      AS clutch_attempts,
               COUNT(*) FILTER (WHERE pr.clutch_won)         AS clutch_wins,
               COUNT(*) FILTER (WHERE pr.buy_type = 'full')  AS full_buys,
               COUNT(*) FILTER (WHERE pr.buy_type = 'force') AS force_buys,
               COUNT(*) FILTER (WHERE pr.buy_type = 'eco')   AS eco_buys,
               MAX(pr.features_version)                      AS features_version
        FROM player_rounds pr JOIN rounds r ON r.id = pr.round_id
        WHERE r.match_id = $1
        GROUP BY pr.steam_id""", match_id)
    features = {f["steam_id"]: dict(f) for f in feats if f["features_version"]}
    return {"match": dict(match), "rounds": rows(rounds_), "scoreboard": rows(scoreboard), "features": features}


@app.get("/api/matches/{match_id}/status")
async def api_match_status(match_id: int, viewer: dict = Depends(require_viewer), conn: asyncpg.Connection = Depends(db)):
    """สถานะงานแกะเดโมของแมตช์ — หน้าเว็บ poll ตัวนี้จนกว่าจะ done หรือ error

    status        queued -> parsing -> done | error   (worker เป็นคนขยับ)
    error_message สาเหตุตอน error (ทุก error ใน worker ลงที่นี่)
    job           สถานะฝั่งคิว RQ ถ้าถามได้ (queued/started/finished/failed) ไว้ดูว่า worker หยิบไปหรือยัง
    """
    row = await conn.fetchrow("""
        SELECT id, demo_file, status, error_message, job_id, imported_at, started_at, finished_at
        FROM matches WHERE id = $1 AND source = 'upload';
    """, match_id)
    if not row:
        raise HTTPException(404, "ไม่พบแมตช์นี้")
    await require_match_access(conn, viewer, match_id=match_id)
    d = dict(row)
    d["job"] = await run_in_threadpool(job_state, d["job_id"])
    return d


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
@app.get("/api/players/search")
async def api_player_search(
    q: str = Query(..., min_length=2, max_length=80),
    limit: int = Query(8, ge=1, le=50),
    viewer: dict = Depends(require_viewer),
    conn: asyncpg.Connection = Depends(db),
):
    """ค้นเฉพาะผู้เล่นที่มีรอบอยู่ใน demo ที่ระบบประมวลผลแล้ว."""
    require_steam_viewer(viewer)
    return await search_players(conn, q.strip(), limit)


async def _player_id(conn: asyncpg.Connection, who: str, viewer: dict) -> int:
    """'me' = SteamID ของบัญชีที่ล็อกอินอยู่ · หรือใส่ SteamID64 ตรง ๆ

    โหมดเยี่ยมชมไม่มี "ฉัน" ให้ชี้ (ไม่มีบัญชี ไม่มี steam_id) จึงตอบ 409 ให้หน้าเว็บ
    เอาไปแสดงปุ่มล็อกอิน — แต่ยังเปิดดูสถิติของผู้เล่นคนอื่นด้วย SteamID64 ได้ตามปกติ
    """
    require_steam_viewer(viewer)
    if who == "me":
        row = await conn.fetchrow("""
            SELECT a.steam_id, l.steam_id AS linked_steam_id
            FROM accounts a LEFT JOIN account_player_links l ON l.account_id = a.id
            WHERE a.id = $1
        """, viewer["id"])
        if not row or row["steam_id"] is None:
            raise HTTPException(409, "บัญชีนี้ยังไม่ได้ผูกกับ Steam — ล็อกอินด้วย Steam เพื่อดูสถิติของตัวเอง")
        if row["linked_steam_id"] is not None:
            return int(row["linked_steam_id"])
        has_own_data = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM player_round_facts WHERE steam_id = $1)", row["steam_id"])
        if not has_own_data:
            raise HTTPException(409, "บัญชียังไม่ได้ยืนยันผู้เล่นใน demo — ค้นหา เลือก และยืนยันผู้เล่นของคุณ")
        return int(row["steam_id"])
    if not who.isdigit() or len(who) != 17:
        raise HTTPException(400, "ต้องเป็น SteamID64 (ตัวเลข 17 หลัก) หรือ me")
    return int(who)


@app.post("/api/players/me/link")
async def api_link_my_player(
    request: Request,
    viewer: dict = Depends(require_viewer),
    conn: asyncpg.Connection = Depends(db),
):
    """บันทึกเฉพาะ Steam ID ที่ผู้ใช้เลือกและยืนยันเอง; ไม่เดาจาก nickname."""
    if viewer["type"] == auth.GUEST:
        raise HTTPException(403, "ต้องล็อกอินด้วย Steam ก่อนยืนยันผู้เล่น")
    payload = await request.json()
    steam_id = str(payload.get("steam_id", ""))
    if not steam_id.isdigit() or len(steam_id) != 17:
        raise HTTPException(400, "ต้องเป็น SteamID64 17 หลัก")
    exists = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM player_round_facts WHERE steam_id = $1)", int(steam_id))
    if not exists:
        raise HTTPException(404, "ไม่พบผู้เล่นนี้ใน demo ที่ประมวลผลแล้ว")
    await conn.execute("""
        INSERT INTO account_player_links (account_id, steam_id, confirmed_at)
        VALUES ($1, $2, now())
        ON CONFLICT (account_id) DO UPDATE
        SET steam_id = EXCLUDED.steam_id, confirmed_at = now()
    """, viewer["id"], int(steam_id))
    return {"ok": True, "steam_id": steam_id}


@app.get("/api/players/{who}/profile")
async def api_player_profile(
    who: str,
    recent: int = Query(0, ge=0, le=20),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    map: str | None = Query(None, min_length=1, max_length=80),
    side: str = Query("all", pattern="^(all|ct|t)$"),
    viewer: dict = Depends(require_viewer),
    conn: asyncpg.Connection = Depends(db),
):
    """โปรไฟล์หนึ่งคน โดยทุกการ์ดใช้ match/round filter ชุดเดียวกัน."""
    if recent not in (0, 5, 10, 20):
        raise HTTPException(400, "ช่วงแมตช์ต้องเป็น 0, 5, 10 หรือ 20")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "วันเริ่มต้นต้องไม่อยู่หลังวันสิ้นสุด")
    steam_id = await _player_id(conn, who, viewer)
    profile = await build_profile(conn, steam_id, recent=int(recent), date_from=date_from,
                                  date_to=date_to, map_name=map, side=side)
    if profile is None:
        raise HTTPException(404, "ยังไม่มีข้อมูลของผู้เล่นคนนี้ในเดโมที่โหลดไว้")
    return profile


@app.get("/api/players/{who}/summary")
async def api_player_summary(who: str, viewer: dict = Depends(require_viewer), conn: asyncpg.Connection = Depends(db)):
    """สรุปของผู้เล่นคนเดียว: ภาพรวม + entry แยกฝั่ง + clutch 1v1..1v5 (ทั้งหมดจากเดโมที่โหลดไว้)"""
    steam_id = await _player_id(conn, who, viewer)
    row = await conn.fetchrow("SELECT * FROM player_stats WHERE steam_id = $1", steam_id)
    if row is None or not row["rounds"]:
        raise HTTPException(404, "ยังไม่มีข้อมูลของผู้เล่นคนนี้ในเดโมที่โหลดไว้")
    totals = await conn.fetchrow("""
        SELECT SUM(damage) AS damage, COUNT(*) FILTER (WHERE kast) AS kast_rounds, COUNT(*) AS rounds,
               SUM(kills) AS kills, SUM(deaths) AS deaths, SUM(assists) AS assists
        FROM player_round_facts WHERE steam_id = $1""", steam_id)
    entry = await conn.fetch("""
        SELECT side,
               COUNT(*) FILTER (WHERE opening_kill)  AS kills,
               COUNT(*) FILTER (WHERE opening_death) AS deaths
        FROM player_rounds WHERE steam_id = $1 GROUP BY side""", steam_id)
    clutches = await conn.fetch("""
        SELECT clutch_vs AS vs, COUNT(*) AS attempts, COUNT(*) FILTER (WHERE clutch_won) AS wins
        FROM player_rounds WHERE steam_id = $1 AND clutch_vs > 0 GROUP BY clutch_vs ORDER BY clutch_vs""", steam_id)
    account = await conn.fetchrow("SELECT username, avatar FROM accounts WHERE steam_id = $1", steam_id)
    avatar = account["avatar"] if account else None
    if not avatar:
        avatar = await conn.fetchval("SELECT avatar FROM players WHERE steam_id = $1", steam_id)
    if not avatar:
        profile = await run_in_threadpool(auth.steam_persona, str(steam_id))
        avatar = profile["avatar"]
        if avatar:
            await conn.execute("UPDATE players SET avatar = $2 WHERE steam_id = $1", steam_id, avatar)

    by_side = {r["side"]: {"kills": r["kills"], "deaths": r["deaths"]} for r in entry}
    both = {"kills": sum(v["kills"] for v in by_side.values()), "deaths": sum(v["deaths"] for v in by_side.values())}
    return {
        "player": {"steam_id": str(steam_id), "name": row["name"],
                   "avatar": avatar,
                   "linked_account": account["username"] if account else None},
        "totals": {k: row[k] for k in ("matches", "rounds", "kills", "deaths", "assists", "headshots",
                                       "kd", "hs_rate", "adr", "kast", "win_rate", "survival_rate", "rating")},
        "rating2_approx": rating2_approx(kills=totals["kills"] or 0, deaths=totals["deaths"] or 0,
                                         assists=totals["assists"] or 0, damage=totals["damage"] or 0,
                                         kast_rounds=totals["kast_rounds"], rounds=totals["rounds"]),
        "entry": {"both": both, "t": by_side.get("t", {"kills": 0, "deaths": 0}),
                  "ct": by_side.get("ct", {"kills": 0, "deaths": 0})},
        "clutches": [{"vs": c["vs"], "attempts": c["attempts"], "wins": c["wins"]} for c in clutches],
        "source": {"matches": row["matches"], "label": f"จาก {row['matches']} แมตช์ที่โหลดเข้าระบบ"},
    }


@app.get("/api/players/{who}/matches")
async def api_player_matches(who: str, limit: int = Query(20, ge=1, le=100),
                             viewer: dict = Depends(require_viewer), conn: asyncpg.Connection = Depends(db)):
    """แมตช์ล่าสุดของผู้เล่นคนนี้ พร้อมผลแพ้/ชนะและ rating รายแมตช์"""
    steam_id = await _player_id(conn, who, viewer)
    return rows(await conn.fetch("""
        SELECT match_id, demo_file, map_name, team_a, team_b, imported_at, rounds, rounds_won, result,
               kills, deaths, assists, adr, kast, rating
        FROM player_match_results WHERE steam_id = $1 ORDER BY match_id DESC LIMIT $2""", steam_id, limit))


@app.get("/api/players/{who}/maps")
async def api_player_maps(who: str, viewer: dict = Depends(require_viewer), conn: asyncpg.Connection = Depends(db)):
    """รวมรายแมพ: เล่นกี่แมตช์ ชนะกี่แมตช์ rating/ADR เฉลี่ย"""
    steam_id = await _player_id(conn, who, viewer)
    return rows(await conn.fetch("""
        SELECT map_name, matches, wins, losses, rounds, win_rate, rating, adr
        FROM player_map_stats WHERE steam_id = $1 ORDER BY matches DESC, wins DESC""", steam_id))


@app.get("/api/players/{who}/weapons")
async def api_player_weapons(who: str, limit: int = Query(8, ge=1, le=30),
                             viewer: dict = Depends(require_viewer), conn: asyncpg.Connection = Depends(db)):
    """อาวุธที่ใช้ฆ่าบ่อยที่สุด + %หัวของอาวุธนั้น (นับเฉพาะการดวล)"""
    steam_id = await _player_id(conn, who, viewer)
    return rows(await conn.fetch("""
        SELECT weapon, kills, headshots, hs_rate FROM player_weapon_stats
        WHERE steam_id = $1 ORDER BY kills DESC LIMIT $2""", steam_id, limit))


# ---------------------------------------------------------------------------
#
# ---------------------------------------------------------------------------
# ตรวจหัวไฟล์กับขนาดระหว่างเขียน
def save_upload(file: UploadFile, dest: Path) -> int:
    """เขียนไฟล์ที่อัปโหลดลงดิสก์ทีละก้อน คืนขนาดเป็นไบต์

    อ่านทีละ 1 MB ไม่ใช่ทีเดียวทั้งไฟล์ เพราะเดโมใหญ่หลายร้อยเมกะไบต์
    ถ้าอ่านรวดเดียวจะกินแรมเท่าขนาดไฟล์ อัปพร้อมกันสองคนก็เริ่มเสี่ยงแล้ว

    เขียนลงชื่อ .part ก่อนแล้วค่อยเปลี่ยนชื่อตอนจบ ไฟล์ที่อัปไม่สำเร็จ
    จึงไม่มีทางถูกเข้าใจผิดว่าเป็นเดโมที่สมบูรณ์
    """
    limit = MAX_DEMO_MB * 1024 * 1024
    part = dest.with_suffix(dest.suffix + ".part")
    size = 0
    try:
        with open(part, "wb") as out:
            while chunk := file.file.read(1024 * 1024): # อ่านไฟล์ทีละ 1 MB
                if size == 0 and not chunk.startswith(DEMO_MAGIC): # เช็คหัวไฟล์
                    raise HTTPException(400, "ไฟล์นี้ไม่ใช่เดโมของ CS2 — หัวไฟล์ไม่ใช่ PBDEMS2 "
                                             "(เดโมของ CS:GO รุ่นเก่าใช้กับระบบนี้ไม่ได้)")
                size += len(chunk) # เช็คขนาดไฟล์
                if size > limit:
                    raise HTTPException(413, f"ไฟล์ใหญ่เกิน {MAX_DEMO_MB} MB")
                out.write(chunk)
        if size == 0:
            raise HTTPException(400, "ไฟล์ว่าง")
        try: # ถ้ามีข้อมูลและผ่านทุกเงื่อนไข เปลี่ยนจาก .part เป็นชื่อ dest
            part.replace(dest)      # .replace() = เปลี่ยนชื่อทับของเดิมได้ และเป็น atomic บนดิสก์เดียวกัน
        except PermissionError:     # Windows: ไฟล์ปลายทางถูกเปิดอยู่ (เช่น worker กำลังแกะไฟล์เดิม) — ไม่ใช่ 500
            raise HTTPException(409, "ไฟล์ชื่อนี้กำลังถูกใช้งานอยู่ (อาจกำลังถูกแกะ) — รอให้เสร็จแล้วลองใหม่")
        return size # ส่งขนาดไฟล์เป็นไบต์กลับไปให้ api_upload_demo()
    finally:
        part.unlink(missing_ok=True)   # เหลือ .part ค้างอยู่ = อัปไม่สำเร็จ เก็บกวาดทิ้ง

# ตรวจจำนวนครั้งที่อัปโหลด ว่าผู้ใช้นี้ครบโควตาในหนึ่งชั่วโมงหรือยัง
async def check_upload_quota(conn: asyncpg.Connection, viewer: dict) -> None: # ถ้ายังไม่เกินโควตา ไม่ต้องคืนค่าอะไรให้ api_upload_demo()
    """เกินโควตาต่อชั่วโมงแล้วตอบ 429 — นับจาก matches.imported_at ของคนนั้น

    นับจากฐานข้อมูลไม่ใช่หน่วยความจำ เพราะตัวนับในหน่วยความจำหายทุกครั้งที่รีสตาร์ต
    และการอัปโหลดหนึ่งครั้งกิน CPU ของ worker เป็นนาที จึงต้องนับให้แม่น

    ฟังก์ชันนี้ถูกเรียกหลัง require_steam_viewer เท่านั้น; Guest เป็น read-only และอัปโหลดไม่ได้
    """
    used = await conn.fetchval("""
        SELECT count(*) FROM matches
        WHERE uploaded_by = $1 AND imported_at > now() - interval '1 hour'
    """, viewer["id"]) # ข้อมูลผู้ใช้ที่อัพโหลด
    if used >= UPLOAD_MAX_PER_HOUR: # ใช้งานถี่เกินโควตา
        raise HTTPException(429, f"อัปโหลดครบโควตาแล้ว ({UPLOAD_MAX_PER_HOUR} ไฟล์ต่อชั่วโมง) "
                                 "— รอสักครู่แล้วลองใหม่")

# ผู้ใช้คนนี้ เป็นคนอัปโหลดแมตช์นี้หรือเปล่า?
def is_match_owner(match: dict, viewer: dict) -> bool:
    """ผู้ดูคนนี้เป็นเจ้าของแมตช์นี้จริงไหม — ไม่เกี่ยวกับว่า "ทำได้หรือไม่" (นั่นคือ can_modify_match)

    uploaded_by เป็น NULL ได้สามกรณี และทั้งสามถือว่า "ไม่มีเจ้าของที่เป็นบัญชี Steam":
        1. แมตช์เก่าที่โหลดเข้าระบบก่อนมี migration 0010
        2. แมตช์ที่เจ้าของถูกลบบัญชีไปแล้ว (FK เป็น ON DELETE SET NULL)
        3. แมตช์ที่ผู้อัปโหลดใช้โหมดเยี่ยมชม (เทียบด้วย uploader_guest แทน)
    แยกสามกรณีนี้ออกจากกันได้ที่คอลัมน์ uploader_type (migration 0011)
    """
    if viewer["type"] == auth.GUEST:
        return match.get("uploader_guest") is not None and match["uploader_guest"] == viewer["guest_id"]
    owner = match.get("uploaded_by")
    return owner is not None and owner == viewer["id"]

# ผู้ใช้คนนี้มีสิทธิ์แก้หรือลบแมตช์นี้ไหม?
def can_modify_match(match: dict, viewer: dict) -> bool:
    """Only the Steam account that uploaded a match may replace or delete it."""
    return viewer["type"] == auth.STEAM and is_match_owner(match, viewer)

# โหลดเดโมทับของเดิมได้ไหม?
def require_replace_access(match: dict, viewer: dict) -> None:
    """Validate ownership and parser state before replacing an existing upload."""
    if match["source"] != "upload" or not can_modify_match(match, viewer):
        raise HTTPException(403, "โหลดทับได้เฉพาะเดโมที่บัญชี Steam นี้เป็นผู้อัปโหลด")
    if match["status"] in ("queued", "parsing"):
        raise HTTPException(409, "เดโมกำลังประมวลผลอยู่ จึงยังโหลดทับไม่ได้")


@app.post("/api/demos")
async def api_upload_demo(
    file: UploadFile = File(..., description="ไฟล์ .dem หนึ่งไฟล์"),
    force: str = Form("0"),   #ค่าโหลดทับ                  # "1" = แมตช์นี้เคยโหลดแล้วให้ลบของเดิมทิ้งแล้วโหลดใหม่
    viewer: dict = Depends(require_viewer),
    conn: asyncpg.Connection = Depends(db),
):
    """รับเดโมหนึ่งไฟล์ เก็บลงดิสก์ แล้วส่งงานแกะเข้าคิว — ตอบ 202 ทันที ไม่รอแกะ

    ส่งทีละไฟล์ หน้าเว็บเป็นคนวนส่งเองถ้าผู้ใช้ลากมาหลายไฟล์
    ทำแบบนี้เพื่อให้แต่ละไฟล์มีสถานะของตัวเอง ไฟล์หนึ่งพังก็ไม่ลากไฟล์อื่นล้มไปด้วย
    """
    require_steam_viewer(viewer) #เช็คผู้ใช้steam
    replace = force == "1" #เทียบค่า

    name = Path(file.filename or "").name #ตัด path ให้เหลือแต่ไฟล์ __.dem
    if not DEMO_NAME_RE.match(name): #ตรวจว่าชื่อใช้รูปแบบที่ยอมรับ เช่นลงท้าย .dem
        raise HTTPException(400, "รับเฉพาะไฟล์ .dem และชื่อไฟล์ใช้ได้แค่ตัวอักษร ตัวเลข . _ - ( )")

# SQL ค้นว่าใน matches มี demo_file ชื่อนี้แล้วหรือยัง ถ้ามีแล้วก็จะใส่ข้อมูลในแถวเดิม
    existing = await conn.fetchrow("""
        SELECT id, status, source, uploaded_by, uploader_guest
        FROM matches WHERE demo_file = $1
    """, name)
    # มีชื่อเดิมอยู่ไหม? ผู้ใช้ไม่ได้ขอทับใช่ไหม? และงานเดิมไม่ได้อยู่สถานะ error ใช่ไหม?
    if existing and not replace and existing["status"] != "error":
        raise HTTPException(409, f"แมตช์ {name} มีอยู่ในระบบแล้ว (Match ID: {existing['id']}, สถานะ {existing['status']}) "
                                 "— กด \"โหลดทับของเดิม\" ในรายการอัปโหลดถ้าต้องการโหลดใหม่")
    # ถ้ามีแถวเดิม โค้ดนำข้อมูลแถวนั้นไปตรวจว่าเป็นแมตช์ที่บัญชี Steam นี้อัปโหลดเอง                         
    if existing:
        existing_match = dict(existing)
        require_replace_access(existing_match, viewer)

    await check_upload_quota(conn, viewer) # ตรวจจำนวนครั้งในหนึ่งชั่วโมง ถ้าเกินตอบ 429



    # 1. รับไฟล์ใหม่ไว้แยกจากไฟล์ .dem ที่ใช้อยู่
    DEMOS_DIR.mkdir(parents=True, exist_ok=True) # สร้างโฟลเดอร์นี้ถ้ายังไม่มี
    dem_path = DEMOS_DIR / name # ชื่อ .dem ที่ worker จะเปิดอ่าน
    staged_path = DEMOS_DIR / f".{name}.{secrets.token_hex(8)}.upload"
    size = await run_in_threadpool(save_upload, file, staged_path) # เขียนและตรวจไฟล์ใหม่ และได้ขนาดกลับมา

# จำผู้ส่ง และเตรียมไว้เก็บไฟล์กับข้อมูลแมตช์เดิม หากการโหลดทับต้องย้อนกลับ
    up_type = viewer["type"]
    up_account = viewer["id"]
    up_guest = viewer["guest_id"]
    backup_path: Path | None = None
    previous_match: dict | None = None

    # 2. เลือกแถวแมตช์ แล้วนำไฟล์ใหม่เข้าเช็คในDBว่าเคยมีไหม ถ้าคำสั่งฐานข้อมูลในช่วงนี้ผิดพลาด transaction จะยกเลิกการเปลี่ยนแปลงในฐานข้อมูลช่วงนี้
    try:
        async with conn.transaction():
            # ล็อก แถวที่พบ ไว้ระหว่าง transaction เพื่อไม่ให้คำขออื่นมาแก้แถวนั้นพร้อมกัน
            locked = await conn.fetchrow("""
                SELECT id, status, source, error_message, job_id, started_at, finished_at, imported_at,
                       uploaded_by, uploader_type, uploader_guest
                FROM matches WHERE demo_file = $1 FOR UPDATE
            """, name)

            # มีแถวเดิม: ตรวจสิทธิ์ แล้วใช้ match_id เดิม
            if locked: 
                locked_match = dict(locked)
                # ถ้าผู้ใช้ไม่ได้ขอโหลดทับ และงานเดิมไม่ได้เป็น error ให้หยุดและตอบ 409 ว่าชื่อซ้ำ
                if not replace and locked_match["status"] != "error":
                    raise HTTPException(409, f"แมตช์ {name} มีอยู่ในระบบแล้ว")

                require_replace_access(locked_match, viewer) # ถ้าไม่หยุด โค้ดจะตรวจอีกว่า ผู้ใช้เป็นเจ้าของแมตช์นี้และสถานะเดิมอนุญาตให้ทับไหม
                previous_match = locked_match # จำข้อมูลแถวเดิมไว้ เผื่อส่งงานเข้าคิวไม่สำเร็จแล้วต้องกู้สถานะ
                match_id = locked_match["id"]

                # อัปเดตแถวแมตช์เดิมตาม match_id ตั้งสถานะกลับเป็น queued ล้างข้อมูลของงานรอบก่อน แล้วบันทึกเวลาและผู้ส่งของรอบใหม่ เพื่อเตรียมส่งให้ worker 
                await conn.execute("""
                    UPDATE matches SET status = 'queued', error_message = NULL, job_id = NULL,
                                       started_at = NULL, finished_at = NULL, imported_at = now(),
                                       uploaded_by = $2, uploader_type = $3, uploader_guest = $4
                    WHERE id = $1
                """, match_id, up_account, up_type, up_guest)

            # ไม่มีแถวเดิม: สร้างแมตช์ใหม่และรับ match_id
            else:
                #สร้างแถว match ใหม่
                match_id = await conn.fetchval("""
                    INSERT INTO matches (demo_file, status, uploaded_by, uploader_type, uploader_guest)
                    VALUES ($1, 'queued', $2, $3, $4) RETURNING id
                """, name, up_account, up_type, up_guest)

            # สำรอง .dem เดิมถ้ามี แล้วนำไฟล์ใหม่มาใช้ชื่อนี้  
            if dem_path.exists():
                backup_path = DEMOS_DIR / f".{name}.{secrets.token_hex(8)}.backup"
                dem_path.replace(backup_path)
            staged_path.replace(dem_path)

    # สลับไฟล์หรือบันทึกแถวพัง: พยายามคืนไฟล์เก่า
    except Exception:
        if backup_path and backup_path.exists(): # มีชื่อไฟล์สำรองอยู่ในตัวแปรหรือไม่ และไฟล์สำรองนั้นยังอยู่จริงไหม
            dem_path.unlink(missing_ok=True)
            backup_path.replace(dem_path) # เปลี่ยนชื่อกลับมาเป็น .dem
        raise
    # เก็บกวาดไฟล์ .upload ที่ยังเหลือ
    finally:
        staged_path.unlink(missing_ok=True)

### เมื่อได้ match_id แล้ว API ส่งเลขนี้ไปให้ระบบคิว ###
# 3. ส่ง match_id ให้คิวเพื่อให้ worker ทำงานต่อ
    try:
        job_id = await run_in_threadpool(enqueue_parse, match_id) # เรียก enqueue_parse(match_id) ใน demo_processing.py

    # คิวรับไม่ได้: กู้ของเดิม หรือทำเครื่องหมาย error    
    except QueueUnavailable as e:
        if previous_match: # มีแถวเดิม: พยายามคืนไฟล์และค่าในแถวเดิม
            dem_path.unlink(missing_ok=True)
            if backup_path and backup_path.exists():
                backup_path.replace(dem_path)
            await conn.execute("""
                UPDATE matches SET status = $2, error_message = $3, job_id = $4,
                                   started_at = $5, finished_at = $6, imported_at = $7,
                                   uploaded_by = $8, uploader_type = $9, uploader_guest = $10
                WHERE id = $1
            """, match_id, previous_match["status"], previous_match["error_message"],
                 previous_match["job_id"], previous_match["started_at"], previous_match["finished_at"],
                 previous_match["imported_at"], previous_match["uploaded_by"],
                 previous_match["uploader_type"], previous_match["uploader_guest"])

        # แมตช์ใหม่: เก็บแถว error และลบไฟล์ใหม่
        else:
            await conn.execute("UPDATE matches SET status = 'error', error_message = $2 WHERE id = $1", match_id, str(e))
            dem_path.unlink(missing_ok=True)
        log(f"[UPLOAD] {name}: {e}")
        raise HTTPException(503, f"รับไฟล์แล้วแต่ส่งงานเข้าคิวไม่ได้ — เปิด Redis ด้วย docker compose up -d redis ({e})")

    # คิวรับงานได้ บันทึก job_id
    await conn.execute("UPDATE matches SET job_id = $2 WHERE id = $1;", match_id, job_id)
    # ส่งคิวสำเร็จแล้ว จึงเก็บกวาดไฟล์สำรองที่มี
    if backup_path:
        try:
            backup_path.unlink(missing_ok=True)
        except OSError as e:
            log(f"[UPLOAD] cleanup backup {backup_path.name} failed: {e}")
    log(f"[UPLOAD] {name} ({size / 1024 / 1024:.1f} MB) -> match {match_id} เข้าคิว job {job_id}")

# API ตอบ HTTP 202 ว่ารับไฟล์และส่งงานเข้าคิวแล้ว
    return JSONResponse(status_code=202, content={
        "match_id": match_id,
        "demo_file": name,
        "size_mb": round(size / 1024 / 1024, 1),
        "replaced": bool(existing),
        "status": "queued",
        "job_id": job_id,
        "status_url": f"/api/matches/{match_id}/status",
    })


# ---------------------------------------------------------------------------
#
# ---------------------------------------------------------------------------
async def _review_match(conn: asyncpg.Connection, demo_file: str, viewer: dict) -> dict:
    await require_match_access(conn, viewer, demo_file=demo_file)
    m = await conn.fetchrow("""
        SELECT id, demo_file, map_name, tickrate, team_a, team_b, status
        FROM matches WHERE demo_file = $1 AND source = 'upload'""", demo_file)
    if not m:
        raise HTTPException(404, f"ไม่พบแมตช์ {demo_file}")
    if m["status"] != "done":
        raise HTTPException(409, f"แมตช์ {demo_file} ยังไม่พร้อม (สถานะ {m['status']})")
    return dict(m)


async def _review_roster(conn: asyncpg.Connection, match_id: int) -> list[dict]:
    """ทุกคนในแมตช์ + ทีม + ฝั่งที่เริ่มเกม

    team       ใช้จัดกล่องทีมและแบ่งกลุ่มสี/หมายเลข (review.player_groups)
    start_side ทางถอยของการแบ่งกลุ่มเมื่อเดโมไม่มีชื่อทีม — ไม่เปลี่ยนตลอดแมตช์

    แมตช์ที่โหลดก่อน migration 0004 (team_clan ว่าง) ผูกทีมจาก player_rounds ตอนนี้แทน
    """
    rows = await conn.fetch("""
        SELECT mp.steam_id, p.name, mp.team_clan, mp.start_side FROM match_players mp
        JOIN players p USING (steam_id) WHERE mp.match_id = $1""", match_id)
    roster = [{"steam_id": r["steam_id"], "name": r["name"], "team": r["team_clan"],
               "start_side": r["start_side"]} for r in rows]
    if roster and all(r["team"] for r in roster):
        return roster
    pr = await conn.fetch("""
        SELECT pr.steam_id, r.round_num, pr.side, p.name FROM player_rounds pr
        JOIN rounds r ON r.id = pr.round_id JOIN players p USING (steam_id) WHERE r.match_id = $1""", match_id)
    team_of = assign_teams([dict(x) for x in pr])
    names = {x["steam_id"]: x["name"] for x in pr}
    first = {}
    for x in sorted(pr, key=lambda r: r["round_num"]):
        first.setdefault(x["steam_id"], x["side"])
    return [{"steam_id": sid, "name": names.get(sid), "team": team, "start_side": first.get(sid)}
            for sid, team in team_of.items()]


# ---------------------------------------------------------------------------
ANALYSIS_SCOPES = {
    "reference": "เดโมทีมอาชีพ",
    "upload": "แมตช์ของทีม",
}
DEATH_SIDES = ("all", "ct", "t")


@app.get("/api/analysis/reference-maps")
async def api_analysis_reference_maps(viewer: dict = Depends(require_viewer),
                                      conn: asyncpg.Connection = Depends(db)):
    """Map availability for Analysis without exposing the reference match catalog."""
    if viewer["type"] == auth.GUEST:
        return []
    return [r["map_name"] for r in await conn.fetch("""
        SELECT DISTINCT map_name FROM matches
        WHERE source = 'reference' AND status = 'done' AND map_name IS NOT NULL
        ORDER BY map_name
    """)]


def _parse_int_list(raw: str | None, *, what: str) -> list[int] | None:
    """แปลง '1,2,5' -> [1,2,5] — ใช้กับ rounds และ players (SteamID64 ก็เป็นตัวเลขล้วน)"""
    if not raw:
        return None
    try:
        return [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(400, f"{what} ต้องเป็นตัวเลขคั่นด้วยจุลภาค เช่น 1,2,5") from None


@app.get("/api/analysis/deaths")
async def api_analysis_deaths(
    map: str = Query(..., description="เช่น de_mirage"),
    scope: str = Query("reference", description="reference = ชุดที่โมเดลเทรนจากมัน | upload = แมตช์ที่ผู้ใช้อัปโหลด"),
    side: str = Query("all", description="ฝั่งของ 'คนที่ตาย': all | ct | t"),
    demo: str | None = Query(None, description="เจาะจงแมตช์เดียว (ต้องอยู่ในชุดที่เลือก)"),
    rounds: str | None = Query(None, description="เจาะจงบางรอบ คั่นด้วยจุลภาค เช่น 1,2,5 — ต้องระบุ demo ด้วยเสมอ"),
    players: str | None = Query(None, description="เจาะจงบางคน (SteamID64) คั่นด้วยจุลภาค — กรองที่ 'คนตาย'"),
    viewer: dict = Depends(require_viewer),
    conn: asyncpg.Connection = Depends(db),
):
    """จุดที่ผู้เล่นตาย นับลงกริด 32x32 เดียวกับโมเดล — คืนเป็นสัดส่วนต่อช่อง เทียบข้ามชุดได้"""
    if viewer["type"] == auth.GUEST:
        allowed = await guest_demo_file(conn)
        if scope != "upload" or demo != allowed:
            raise HTTPException(403, "โหมดเยี่ยมชมวิเคราะห์ได้เฉพาะเดโมตัวอย่าง")
    if scope not in ANALYSIS_SCOPES:
        raise HTTPException(400, f"scope ต้องเป็น {' หรือ '.join(ANALYSIS_SCOPES)}")
    if side not in DEATH_SIDES:
        raise HTTPException(400, f"side ต้องเป็น {' หรือ '.join(DEATH_SIDES)}")
    frame = radar_frame(map)
    if frame is None:
        raise HTTPException(404, f"ยังไม่มีภาพเรดาร์ที่ปรับเทียบพิกัดแล้วของแมพ {map}")

    round_nums = _parse_int_list(rounds, what="rounds")
    if round_nums and not demo:
        raise HTTPException(400, "เจาะจงรอบได้เฉพาะตอนเลือกแมตช์เดียว (demo) แล้วเท่านั้น")
    player_ids = _parse_int_list(players, what="players")

    n_matches = await conn.fetchval("""
        SELECT COUNT(*) FROM matches
        WHERE map_name = $1 AND source = $2 AND status = 'done' AND ($3::text IS NULL OR demo_file = $3)
    """, map, scope, demo)
    rows = await conn.fetch("""
        SELECT k.victim_x AS x, k.victim_y AS y, k.victim_place AS place
        FROM kills k
        JOIN rounds r  ON r.id = k.round_id
        JOIN matches m ON m.id = r.match_id
        WHERE m.map_name = $1 AND m.source = $2 AND m.status = 'done'
          AND k.victim_x IS NOT NULL AND k.victim_y IS NOT NULL
          AND ($3 = 'all' OR k.victim_side = $3)
          AND ($4::text IS NULL OR m.demo_file = $4)
          AND ($5::int[] IS NULL OR r.round_num = ANY($5))
          AND ($6::bigint[] IS NULL OR k.victim_id = ANY($6))
    """, map, scope, side, demo, round_nums, player_ids)

    out = await run_in_threadpool(
        deaths_overlay, [r["x"] for r in rows], [r["y"] for r in rows], frame, [r["place"] for r in rows])
    label = f"{demo} (1 แมตช์)" if demo else f"{ANALYSIS_SCOPES[scope]} {n_matches} แมตช์"
    if round_nums:
        label += f" · {len(round_nums)} รอบที่เลือก"
    if player_ids:
        label += f" · {len(player_ids)} คนที่เลือก"
    return {
        **out,
        "map": map,
        "scope": scope,
        "side": side,
        "demo": demo,
        "rounds": round_nums,
        "players": [str(p) for p in player_ids] if player_ids else None,
        "matches": n_matches,
        "label": label,
        "radar": {"image": "/assets" + frame.image, "size": frame.size, "map": frame.map_name},
    }


@app.get("/api/analysis/player-behavior")
async def api_player_behavior(
    demo: str = Query(..., description="Uploaded demo filename"),
    players: str | None = Query(None, description="Optional comma-separated SteamID64 values"),
    viewer: dict = Depends(require_viewer),
    conn: asyncpg.Connection = Depends(db),
):
    """Infer per-match, per-side behaviour from a cached reference-only KMeans artifact."""
    match = await _review_match(conn, demo, viewer)
    model = load_role_model(map_name=match.get("map_name"))
    source = await conn.fetchval("SELECT source FROM matches WHERE id = $1", match["id"])
    reason = compatibility_reason(model, match.get("map_name"), source)
    if reason:
        return {"available": False, "reason": reason, "map": match.get("map_name"),
                "supported_map": model.get("map") if model else None}

    selected = _parse_int_list(players, what="players")
    round_rows = await conn.fetch("""
        SELECT r.round_num, pr.steam_id, p.name, pr.side, pr.assists, pr.opening_kill,
               pr.opening_death, pr.trade_kills, pr.was_traded
        FROM player_rounds pr
        JOIN rounds r ON r.id = pr.round_id
        JOIN players p ON p.steam_id = pr.steam_id
        WHERE r.match_id = $1
        ORDER BY r.round_num, p.name
    """, match["id"])
    kill_rows = await conn.fetch("""
        SELECT r.round_num, r.start_tick, r.bomb_plant_tick, k.tick, k.attacker_id,
               k.victim_id, k.assister_id, k.attacker_side, k.victim_side,
               k.attacker_place, k.victim_place, k.assisted_flash
        FROM kills k JOIN rounds r ON r.id = k.round_id
        WHERE r.match_id = $1 ORDER BY r.round_num, k.tick
    """, match["id"])
    profiles = await run_in_threadpool(build_match_profiles, round_rows, kill_rows, match.get("tickrate") or 128)
    results = await run_in_threadpool(infer_match, profiles, model,
                                      {str(p) for p in selected} if selected is not None else None)
    identities = await conn.fetch("""
        SELECT steam_id::text AS steamid, team_clan
        FROM match_players WHERE match_id = $1
    """, match["id"])
    team_by_player = {row["steamid"]: row["team_clan"] for row in identities}
    own_team = None
    if viewer["type"] == auth.STEAM:
        own_steam_id = await conn.fetchval("""
            SELECT COALESCE(l.steam_id, a.steam_id)::text
            FROM accounts a
            LEFT JOIN account_player_links l ON l.account_id = a.id
            WHERE a.id = $1
        """, viewer["id"])
        own_team = team_by_player.get(own_steam_id)
    for result in results:
        result["team"] = team_by_player.get(result["steamid"])
    teams = sorted({team for team in team_by_player.values() if team})
    return {
        "available": True,
        "demo": demo,
        "map": match.get("map_name"),
        "unit": model.get("unit"),
        "minimum_rounds": model.get("min_rounds_per_profile", 5),
        "players": results,
        "teams": teams,
        "own_team": own_team,
        "source": {
            "kind": "reference_only",
            "matches": model.get("source_matches"),
            "version": model.get("version"),
            "model": model.get("model"),
        },
        "note": model.get("interpretation_note"),
    }


@app.get("/api/coach/{demo_file}")
async def api_coach(demo_file: str, side: str = "t", viewer: dict = Depends(require_viewer),
                    conn: asyncpg.Connection = Depends(db)):
    if side not in ("t", "ct"):
        raise HTTPException(422, "ฝั่งต้องเป็น T หรือ CT")
    match = await _review_match(conn, demo_file, viewer)
    model = load_coach_model(map_name=match["map_name"])
    if not model or model.get("map") != match["map_name"]:
        return {"available": False, "reason": "model_unavailable" if not model else "unsupported_map", "rounds": []}
    data = await load_coach_facts(conn, match["map_name"], match_id=match["id"])
    samples = [s for s in build_coach_samples(data, match["map_name"]) if s["side"] == side]
    return {"available": True, "map": match["map_name"], "side": side,
            "model": {"version": model["version"], "trained_at": model["trained_at"],
                      "reference_matches": len(model["training_match_ids"]),
                      "validation": model["sides"].get(side, {}).get("validation"),
                      "clock_provenance": model["clock_provenance"]},
            "rounds": [recommend_round(s, model, map_name=match["map_name"], exclude_match=match["id"]) for s in samples]}


@app.get("/api/opening-route/catalog")
async def api_opening_catalog(viewer: dict = Depends(require_viewer), conn: asyncpg.Connection = Depends(db)):
    guest_demo = await guest_demo_file(conn) if viewer["type"] == auth.GUEST else None
    records = await conn.fetch("""
        SELECT m.id, m.demo_file, m.map_name, p.steam_id::text AS steamid, p.name
        FROM matches m JOIN match_players mp ON mp.match_id = m.id
        JOIN players p ON p.steam_id = mp.steam_id
        WHERE m.status = 'done' AND ($1::text IS NULL OR m.demo_file = $1) AND (
            EXISTS (SELECT 1 FROM player_positions pp WHERE pp.match_id = m.id AND pp.steam_id = p.steam_id)
            OR EXISTS (SELECT 1 FROM grenades g JOIN rounds r ON r.id = g.round_id
                       WHERE r.match_id = m.id AND g.thrower_id = p.steam_id))
        ORDER BY p.name, m.demo_file
    """, guest_demo)
    return [{**dict(r), "match_date": match_date(r["demo_file"])} for r in records]


@app.get("/api/opening-route")
async def api_opening_route(steamid: str, map: str, side: str = "t", limit: int = 0,
                            viewer: dict = Depends(require_viewer), conn: asyncpg.Connection = Depends(db)):
    if side not in ("t", "ct") or limit not in (0, 5, 10) or not steamid.isdigit() or not 0 < int(steamid) < 2**63:
        raise HTTPException(422, "ตัวกรอง Opening Route ไม่ถูกต้อง")
    sid = int(steamid)
    guest_demo = await guest_demo_file(conn) if viewer["type"] == auth.GUEST else None
    candidates = rows(await conn.fetch("""
        SELECT m.id, m.demo_file, m.map_name, m.tickrate, m.team_a, m.team_b
        FROM matches m JOIN match_players mp ON mp.match_id = m.id
        WHERE m.status = 'done' AND mp.steam_id = $1 AND m.map_name = $2
          AND ($3::text IS NULL OR m.demo_file = $3) AND (
            EXISTS (SELECT 1 FROM player_positions pp WHERE pp.match_id = m.id AND pp.steam_id = $1)
            OR EXISTS (SELECT 1 FROM grenades g JOIN rounds r ON r.id = g.round_id
                       WHERE r.match_id = m.id AND g.thrower_id = $1))
    """, sid, map, guest_demo))
    matches = select_matches(candidates, limit)
    ids = [m["id"] for m in matches]
    rounds_ = rows(await conn.fetch("""
        SELECT r.id, r.match_id, r.round_num, r.start_tick, pr.side,
               (SELECT MIN(k.tick) FROM kills k WHERE k.round_id = r.id AND k.victim_id = $2) AS death_tick
        FROM rounds r JOIN player_rounds pr ON pr.round_id = r.id
        WHERE r.match_id = ANY($1::int[]) AND pr.steam_id = $2 AND pr.side = $3
        ORDER BY r.match_id, r.round_num
    """, ids, sid, side))
    round_ids = [r["id"] for r in rounds_]
    positions = rows(await conn.fetch("""
        SELECT r.id AS round_id, pp.tick, pp.x, pp.y, pp.health
        FROM player_positions pp JOIN rounds r ON r.match_id = pp.match_id AND r.round_num = pp.round_num
        JOIN matches m ON m.id = r.match_id
        WHERE r.id = ANY($1::int[]) AND pp.steam_id = $2
          AND pp.tick BETWEEN r.start_tick AND r.start_tick + 30 * m.tickrate
        ORDER BY r.id, pp.tick
    """, round_ids, sid))
    columns = await _optional_columns(conn, "grenades", ("trajectory",))
    trajectory = "g.trajectory" if "trajectory" in columns else "NULL::jsonb AS trajectory"
    grenades = rows(await conn.fetch(f"""
        SELECT g.round_id, g.tick, g.thrower_id, g.side, g.type, g.throw_x, g.throw_y,
               g.land_x, g.land_y, g.land_tick, g.end_tick, {trajectory}, p.name AS thrower_name
        FROM grenades g LEFT JOIN players p ON p.steam_id = g.thrower_id
        JOIN rounds r ON r.id = g.round_id JOIN matches m ON m.id = r.match_id
        WHERE g.round_id = ANY($1::int[]) AND g.thrower_id = $2
          AND g.tick BETWEEN r.start_tick AND r.start_tick + 30 * m.tickrate
        ORDER BY g.round_id, g.tick, g.id
    """, round_ids, sid))
    result = build_opening_rounds(matches, rounds_, positions, grenades, sid, map)
    return {**result, "matches": len(matches), "undated_matches": sum(match_date(m["demo_file"]) is None for m in candidates),
            "window_seconds": 30, "clock_source": "stored_start_tick_unverified"}


@app.get("/api/review/{demo_file}/rounds")
async def api_review_rounds(demo_file: str, viewer: dict = Depends(require_viewer), conn: asyncpg.Connection = Depends(db)):
    """รายรอบของแมตช์: ใครชนะ จบด้วยอะไร ตายกี่คน คนแรกตายวินาทีที่เท่าไหร่"""
    m = await _review_match(conn, demo_file, viewer)
    rounds_ = await conn.fetch("""
        SELECT round_num, start_tick, winner_side, end_reason FROM rounds WHERE match_id = $1 ORDER BY round_num""", m["id"])
    agg = await conn.fetch("""
        SELECT r.round_num, COUNT(k.id) AS n, MIN(k.tick) AS first_tick
        FROM rounds r LEFT JOIN kills k ON k.round_id = r.id WHERE r.match_id = $1 GROUP BY r.round_num""", m["id"])
    return build_round_list(rows(rounds_), {a["round_num"]: a["first_tick"] for a in agg if a["first_tick"] is not None},
                            {a["round_num"]: a["n"] for a in agg}, m["tickrate"])


@app.get("/api/review/{demo_file}/rounds/{round_num}")
async def api_review_round(demo_file: str, round_num: int, viewer: dict = Depends(require_viewer),
                           conn: asyncpg.Connection = Depends(db)):
    """รอบเดียวแบบละเอียด: ทีม / การตายทุกครั้ง (พิกัด + พิกเซลบนเรดาร์) / บริบทจาก grid_ml1 / สรุปรอบ"""
    m = await _review_match(conn, demo_file, viewer)
    round_columns = await _optional_columns(conn, "rounds", ("end_tick", "defuse_intervals", "bomb_resolved_tick"))
    end_tick = "end_tick" if "end_tick" in round_columns else "NULL::integer AS end_tick"
    defuse_intervals = "defuse_intervals" if "defuse_intervals" in round_columns else "NULL::jsonb AS defuse_intervals"
    bomb_resolved_tick = "bomb_resolved_tick" if "bomb_resolved_tick" in round_columns else "NULL::integer AS bomb_resolved_tick"
    rnd = await conn.fetchrow(f"""
        SELECT id, round_num, start_tick, {end_tick}, {defuse_intervals}, winner_side, end_reason,
               bomb_plant_tick, {bomb_resolved_tick}, bomb_plant_x, bomb_plant_y, bomb_site
        FROM rounds WHERE match_id = $1 AND round_num = $2""", m["id"], round_num)
    if not rnd:
        raise HTTPException(404, f"แมตช์นี้ไม่มีรอบที่ {round_num}")
    roster = await _review_roster(conn, m["id"])
    in_round = await conn.fetch("SELECT steam_id, side, survived FROM player_rounds WHERE round_id = $1", rnd["id"])
    kills = await conn.fetch("""
        SELECT k.*, pa.name AS attacker_name, pv.name AS victim_name, ps.name AS assister_name
        FROM kills k
        LEFT JOIN players pa ON pa.steam_id = k.attacker_id
        LEFT JOIN players pv ON pv.steam_id = k.victim_id
        LEFT JOIN players ps ON ps.steam_id = k.assister_id
        WHERE k.round_id = $1 ORDER BY k.tick, k.id""", rnd["id"])
    grenade_columns = await _optional_columns(conn, "grenades", ("trajectory",))
    trajectory = "g.trajectory" if "trajectory" in grenade_columns else "NULL::jsonb AS trajectory"
    grenades = await conn.fetch(f"""
        SELECT g.tick, g.thrower_id, g.side, g.type, g.throw_x, g.throw_y, g.land_x, g.land_y, g.land_tick, g.end_tick,
               {trajectory},
               p.name AS thrower_name
        FROM grenades g LEFT JOIN players p ON p.steam_id = g.thrower_id
        WHERE g.round_id = $1 ORDER BY g.tick, g.id""", rnd["id"])
    damages = await conn.fetch("""
        SELECT id, tick, attacker_id, victim_id, damage
        FROM damages WHERE round_id = $1 ORDER BY tick, id""", rnd["id"])
    latest_damage_tick = damages[-1]["tick"] if damages else None
    return build_round_detail(match=m, rnd=dict(rnd), roster=roster, in_round=rows(in_round), kills=rows(kills),
                              grenades=rows(grenades), frame=radar_frame(m["map_name"]),
                              model=load_grid_model(map_name=m["map_name"]),
                              damages=rows(damages), latest_damage_tick=latest_damage_tick)


@app.get("/api/review/{demo_file}/rounds/{round_num}/positions")
async def api_review_positions(demo_file: str, round_num: int, viewer: dict = Depends(require_viewer),
                               conn: asyncpg.Connection = Depends(db)):
    """snapshot ตำแหน่งผู้เล่นของรอบนี้ (8 Hz ใหม่ / รองรับ 1 Hz เดิม) โหลดเมื่อเปิดโหมด"""
    m = await _review_match(conn, demo_file, viewer)
    rnd = await conn.fetchrow(
        "SELECT id, round_num, start_tick FROM rounds WHERE match_id = $1 AND round_num = $2", m["id"], round_num)
    if not rnd:
        raise HTTPException(404, f"แมตช์นี้ไม่มีรอบที่ {round_num}")
    equipment = ("active_weapon", "armor", "has_helmet", "has_defuser", "yaw", "flash_remaining", "money", "has_bomb")
    available = await _optional_columns(conn, "player_positions", equipment)
    defaults = {"active_weapon": "NULL::text", "armor": "NULL::integer",
                "has_helmet": "NULL::boolean", "has_defuser": "NULL::boolean", "yaw": "NULL::real",
                "flash_remaining": "NULL::real", "money": "NULL::integer", "has_bomb": "NULL::boolean"}
    equipment_sql = ", ".join(name if name in available else f"{defaults[name]} AS {name}"
                              for name in equipment)
    pos = await conn.fetch(f"""
        SELECT tick, steam_id, side, x, y, health, place, {equipment_sql}
        FROM player_positions
        WHERE match_id = $1 AND round_num = $2 ORDER BY tick, steam_id""", m["id"], round_num)
    return build_round_positions(rows(pos), start_tick=rnd["start_tick"], tickrate=m["tickrate"],
                                 frame=radar_frame(m["map_name"]))


_HEATMAP_SQL = {
    "kills": """
        SELECT k.attacker_x AS x, k.attacker_y AS y FROM kills k JOIN rounds r ON r.id = k.round_id
        WHERE r.match_id = $1 AND k.attacker_id IS NOT NULL
          AND ($2 = 'all' OR k.attacker_side = $2)
          AND ($3::bigint[] IS NULL OR k.attacker_id = ANY($3))
          AND ($4::int[] IS NULL OR r.round_num = ANY($4))""",
    "deaths": """
        SELECT k.victim_x AS x, k.victim_y AS y FROM kills k JOIN rounds r ON r.id = k.round_id
        WHERE r.match_id = $1
          AND ($2 = 'all' OR k.victim_side = $2)
          AND ($3::bigint[] IS NULL OR k.victim_id = ANY($3))
          AND ($4::int[] IS NULL OR r.round_num = ANY($4))""",
    "positions": """
        SELECT x, y FROM player_positions
        WHERE match_id = $1 AND health > 0
          AND ($2 = 'all' OR side = $2)
          AND ($3::bigint[] IS NULL OR steam_id = ANY($3))
          AND ($4::int[] IS NULL OR round_num = ANY($4))""",
    "grenade": """
        SELECT g.land_x AS x, g.land_y AS y FROM grenades g JOIN rounds r ON r.id = g.round_id
        WHERE r.match_id = $1 AND g.type = $5
          AND ($2 = 'all' OR g.side = $2)
          AND ($3::bigint[] IS NULL OR g.thrower_id = ANY($3))
          AND ($4::int[] IS NULL OR r.round_num = ANY($4))""",
}


@app.get("/api/review/{demo_file}/heatmap")
async def api_review_heatmap(
    demo_file: str,
    event: str = Query("kills", description="kills | deaths | positions | smoke | flash | he | molotov"),
    side: str = Query("all", description="ฝั่งของคนที่ทำ event: all | ct | t"),
    players: str | None = Query(None, description="SteamID64 คั่นด้วยจุลภาค — ไม่ระบุ = ทุกคน"),
    rounds: str | None = Query(None, description="เลขรอบคั่นด้วยจุลภาค — ไม่ระบุ = ทุกรอบ"),
    viewer: dict = Depends(require_viewer),
    conn: asyncpg.Connection = Depends(db),
):
    """จุดของ event ที่เลือกในแมตช์เดียว เป็นพิกเซลบนภาพเรดาร์ — หน้าเว็บเอาไปวาด heatmap เอง"""
    if event not in HEATMAP_EVENTS:
        raise HTTPException(400, f"event ต้องเป็น {' | '.join(HEATMAP_EVENTS)}")
    if side not in DEATH_SIDES:
        raise HTTPException(400, f"side ต้องเป็น {' หรือ '.join(DEATH_SIDES)}")
    m = await _review_match(conn, demo_file, viewer)
    frame = radar_frame(m["map_name"])
    if frame is None:
        raise HTTPException(404, f"ยังไม่มีภาพเรดาร์ที่ปรับเทียบพิกัดแล้วของแมพ {m['map_name']}")
    player_ids = _parse_int_list(players, what="players")
    round_nums = _parse_int_list(rounds, what="rounds")

    sql = _HEATMAP_SQL["grenade" if event not in ("kills", "deaths", "positions") else event]
    args = [m["id"], side, player_ids, round_nums] + ([event] if sql is _HEATMAP_SQL["grenade"] else [])
    pts = await conn.fetch(sql, *args)
    roster = await _review_roster(conn, m["id"])
    n_rounds = await conn.fetchval("SELECT COUNT(*) FROM rounds WHERE match_id = $1", m["id"])
    points = heatmap_points([r["x"] for r in pts], [r["y"] for r in pts], frame)
    return {
        "event": event,
        "demo": demo_file,
        "map": m["map_name"],
        "points": points,
        "count": len(points),
        "rounds": n_rounds,
        "roster": [{"steam_id": str(p["steam_id"]), "name": p["name"], "team": p["team"],
                    "start_side": p["start_side"]} for p in sorted(roster, key=lambda p: (p["team"] or "", p["name"]))],
        "radar": {"image": "/assets" + frame.image, "size": frame.size, "map": frame.map_name},
    }


@app.get("/api/review/{demo_file}/economy")
async def api_review_economy(demo_file: str, viewer: dict = Depends(require_viewer), conn: asyncpg.Connection = Depends(db)):
    """เศรษฐกิจรายรอบของสองทีม: มูลค่าอุปกรณ์ตอน freeze จบ + ประเภทการซื้อทั้งทีม + ใครชนะ

    ประเภทการซื้อมาจาก view round_economy (views.sql) ที่เดียว — ที่นี่แค่ผูกฝั่งกับทีมทีละรอบ
    """
    m = await _review_match(conn, demo_file, viewer)
    econ = await conn.fetch("""
        SELECT round_num, winner_side, end_reason, ct_equip, t_equip, ct_buy_type, t_buy_type
        FROM round_economy WHERE match_id = $1 ORDER BY round_num""", m["id"])
    sides = await conn.fetch("""
        SELECT r.round_num, pr.steam_id, pr.side FROM player_rounds pr
        JOIN rounds r ON r.id = pr.round_id WHERE r.match_id = $1""", m["id"])
    roster = await _review_roster(conn, m["id"])
    return {"demo": demo_file, "map": m["map_name"], **build_economy(rows(econ), rows(sides), roster)}


# Report routes are kept in their own module; app.py only supplies the shared auth and DB dependencies.
app.include_router(create_report_router(require_viewer, db, require_match_access))
