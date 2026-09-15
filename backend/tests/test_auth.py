# -*- coding: utf-8 -*-
"""เข้าใช้งาน: JWT ใน httpOnly cookie (Steam + โหมดเยี่ยมชม), dependency require_viewer, สิทธิ์เจ้าของข้อมูล"""
import base64
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.requests import Request

from backend import auth

SECRET = "s" * 40


STEAM_VIEWER = {"type": "steam", "id": 7, "username": "alice", "guest_id": None}


def test_token_roundtrip():
    t = auth.create_token(7, "alice", secret=SECRET)
    assert auth.viewer_from_token(t, secret=SECRET) == STEAM_VIEWER


def test_guest_token_roundtrip():
    """token โหมดเยี่ยมชม: ไม่มี id ไม่มีชื่อ มีแต่รหัส session ที่เดาไม่ได้"""
    gid = auth.new_guest_id()
    t = auth.create_guest_token(guest_id=gid, secret=SECRET)
    assert auth.viewer_from_token(t, secret=SECRET) == {
        "type": "guest", "id": None, "username": None, "guest_id": gid}
    assert gid.startswith("g_") and len(gid) == 26            # g_ + 24 hex — เดาไม่ได้
    assert auth.new_guest_id() != auth.new_guest_id()


def test_guest_token_cannot_claim_to_be_a_steam_account():
    """เปลี่ยน typ เป็น steam เองไม่ได้ เพราะ payload อยู่ในลายเซ็น — แก้แล้วลายเซ็นไม่ตรง"""
    t = auth.create_guest_token(guest_id="g_" + "a" * 24, secret=SECRET)
    head, body, sig = t.split(".")
    forged = json.loads(base64.urlsafe_b64decode(body + "=="))
    forged.update({"typ": "steam", "sub": "1", "name": "admin"})
    forged_body = base64.urlsafe_b64encode(json.dumps(forged).encode()).decode().rstrip("=")
    assert auth.viewer_from_token(f"{head}.{forged_body}.{sig}", secret=SECRET) is None


def test_token_carries_no_privilege_field():
    """ระบบไม่แบ่ง role — token ต้องไม่มีฟิลด์สิทธิ์ให้ใครเอาไปตีความว่าเป็นแอดมิน"""
    import jwt as _jwt
    payload = _jwt.decode(auth.create_token(7, "alice", secret=SECRET), SECRET, algorithms=[auth.JWT_ALG])
    assert "role" not in payload and "is_admin" not in payload


def test_old_token_with_role_still_works_and_grants_nothing():
    """token ที่ออกตอนระบบยังมี role ต้องใช้ต่อได้ ไม่ใช่เด้งออก และ role ในนั้นต้องไม่มีผล"""
    from datetime import UTC, datetime, timedelta

    import jwt as _jwt
    now = datetime.now(UTC)
    legacy = _jwt.encode({"sub": "7", "name": "alice", "role": "admin",
                          "iat": now, "exp": now + timedelta(days=1)}, SECRET, algorithm=auth.JWT_ALG)
    # ไม่มีฟิลด์ typ = token ที่ออกก่อนมีโหมดเยี่ยมชม ต้องถือเป็นผู้ใช้ Steam ตามเดิม ไม่ใช่ guest
    assert auth.viewer_from_token(legacy, secret=SECRET) == STEAM_VIEWER


def test_expired_tampered_wrong_secret_are_rejected():
    old = auth.create_token(7, "alice", secret=SECRET, now=datetime.now(UTC) - timedelta(days=8))
    assert auth.viewer_from_token(old, secret=SECRET) is None
    t = auth.create_token(7, "alice", secret=SECRET)
    head, body, sig = t.split(".")
    forged = json.loads(base64.urlsafe_b64decode(body + "=="))
    forged["sub"] = "1"                                   # แอบเปลี่ยนตัวตนแต่คงลายเซ็นเดิม
    forged_body = base64.urlsafe_b64encode(json.dumps(forged).encode()).decode().rstrip("=")
    assert auth.viewer_from_token(f"{head}.{forged_body}.{sig}", secret=SECRET) is None
    assert auth.viewer_from_token(t, secret="another-secret-" * 3) is None
    assert auth.viewer_from_token("", secret=SECRET) is None
    assert auth.viewer_from_token("not.a.jwt", secret=SECRET) is None


def test_alg_none_and_missing_claims_are_rejected():
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    exp = int((datetime.now(UTC) + timedelta(days=1)).timestamp())
    unsigned = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'sub': '1', 'name': 'x', 'exp': exp})}."
    assert auth.viewer_from_token(unsigned, secret=SECRET) is None
    no_sub = jwt.encode({"name": "x", "exp": exp}, SECRET, algorithm="HS256")
    assert auth.viewer_from_token(no_sub, secret=SECRET) is None
    no_exp = jwt.encode({"sub": "1", "name": "x"}, SECRET, algorithm="HS256")
    assert auth.viewer_from_token(no_exp, secret=SECRET) is None


def test_cookie_is_httponly_lax_and_clearable():
    r = JSONResponse({})
    auth.set_auth_cookie(r, "tok")
    h = r.headers["set-cookie"].lower()
    assert f"{auth.COOKIE_NAME}=tok" in h and "httponly" in h and "samesite=lax" in h and "path=/" in h
    r2 = JSONResponse({})
    auth.clear_auth_cookie(r2)
    assert "max-age=0" in r2.headers["set-cookie"].lower()


def test_cookie_without_remember_me_is_a_session_cookie():
    """ไม่ติ๊ก "จดจำการเข้าสู่ระบบ" = ไม่มี Max-Age/Expires คุกกี้จึงหายเมื่อปิดเบราว์เซอร์ แต่ยัง httpOnly"""
    r = JSONResponse({})
    auth.set_auth_cookie(r, "tok", persistent=False)
    h = r.headers["set-cookie"].lower()
    assert "httponly" in h and "max-age" not in h and "expires" not in h


def _request(cookie: str | None) -> Request:
    headers = [(b"cookie", cookie.encode())] if cookie else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def test_require_viewer_accepts_both_steam_and_guest_cookies():
    from backend import app as appmod
    tok = auth.create_token(3, "bob")
    assert appmod.require_viewer(_request(f"{auth.COOKIE_NAME}={tok}")) == {
        "type": "steam", "id": 3, "username": "bob", "guest_id": None}

    gtok = auth.create_guest_token(guest_id="g_" + "b" * 24)
    assert appmod.require_viewer(_request(f"{auth.COOKIE_NAME}={gtok}")) == {
        "type": "guest", "id": None, "username": None, "guest_id": "g_" + "b" * 24}

    # ไม่มีคุกกี้ / คุกกี้พัง / คุกกี้ชื่ออื่น = ไม่มี session ต้องเป็น 401 ทั้งหมด
    for cookie in (None, f"{auth.COOKIE_NAME}=garbage", f"cs2_session={tok}"):
        with pytest.raises(HTTPException) as e:
            appmod.require_viewer(_request(cookie))
        assert e.value.status_code == 401


def test_auth_routes_are_steam_only():
    """ล็อกอินมีทางเดียวคือ Steam OpenID — ห้ามมี local login / สมัครสมาชิก / dev-login กลับมาอีก"""
    from backend import app as appmod
    routes = {(m, r.path) for r in appmod.app.routes for m in getattr(r, "methods", ()) or ()}
    for expected in [("GET", "/auth/me"), ("POST", "/auth/logout"), ("POST", "/auth/guest"),
                     ("GET", "/auth/steam/login"), ("GET", "/auth/steam/callback")]:
        assert expected in routes
    paths = {p for _, p in routes}
    for forbidden in ("/auth/login", "/auth/register", "/auth/dev-login", "/auth/config", "/auth/local"):
        assert forbidden not in paths


# ---- ล็อกอินด้วย Steam (ตรวจเฉพาะส่วนที่ไม่ต้องต่อเน็ต) ----------------------------------------
def test_steam_login_url_asks_steam_to_return_to_us():
    url = auth.steam_login_url("http://localhost:3000/auth/steam/callback?next=/matches", "http://localhost:3000/")
    assert url.startswith("https://steamcommunity.com/openid/login?")
    q = parse_qs(urlparse(url).query)
    assert q["openid.mode"] == ["checkid_setup"]
    assert q["openid.return_to"] == ["http://localhost:3000/auth/steam/callback?next=/matches"]
    assert q["openid.realm"] == ["http://localhost:3000/"]
    assert q["openid.identity"] == ["http://specs.openid.net/auth/2.0/identifier_select"]


@pytest.mark.parametrize("claimed", [
    None, "", "7656119801234567",
    "https://steamcommunity.com/openid/id/123",                        # สั้นเกิน
    "https://evil.example.com/openid/id/76561198012345678",            # คนละโดเมน
    "https://steamcommunity.com.evil.example/openid/id/76561198012345678",
    "https://steamcommunity.com/openid/id/76561198012345678/../x",
])
def test_bad_claimed_ids_are_rejected(claimed):
    assert auth.steamid_from_claimed_id(claimed) is None


def test_good_claimed_id_gives_the_steamid():
    assert auth.steamid_from_claimed_id("https://steamcommunity.com/openid/id/76561198012345678") == "76561198012345678"


def test_openid_reply_is_only_trusted_when_steam_says_is_valid(monkeypatch):
    """พารามิเตอร์ที่ปลอมมาเองต้องไม่ผ่าน แม้ claimed_id จะถูกรูปแบบ — ต้องรอคำตอบ is_valid:true จาก Steam"""
    good = {"openid.mode": "id_res", "openid.claimed_id": "https://steamcommunity.com/openid/id/76561198012345678",
            "openid.sig": "x", "other": "ignored"}
    sent = {}

    class FakeResponse:
        def __init__(self, text): self.text = text
        def read(self): return self.text.encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=None):
        sent["url"] = req.full_url
        sent["body"] = req.data.decode()
        return FakeResponse(fake_urlopen.answer)

    monkeypatch.setattr(auth.urllib.request, "urlopen", fake_urlopen)
    fake_urlopen.answer = "ns:http://specs.openid.net/auth/2.0\nis_valid:true\n"
    assert auth.verify_steam_openid(dict(good)) == "76561198012345678"
    assert "openid.mode=check_authentication" in sent["body"] and "other" not in sent["body"]
    fake_urlopen.answer = "is_valid:false\n"
    assert auth.verify_steam_openid(dict(good)) is None
    assert auth.verify_steam_openid({**good, "openid.mode": "cancel"}) is None

    def boom(req, timeout=None):
        raise OSError("steam unreachable")

    monkeypatch.setattr(auth.urllib.request, "urlopen", boom)
    assert auth.verify_steam_openid(dict(good)) is None


def test_allowlist_empty_means_everyone(monkeypatch):
    monkeypatch.setattr(auth, "STEAM_ALLOWED_IDS", set())
    assert auth.steam_id_allowed("76561198012345678")
    monkeypatch.setattr(auth, "STEAM_ALLOWED_IDS", {"76561198000000001"})
    assert auth.steam_id_allowed("76561198000000001")
    assert not auth.steam_id_allowed("76561198012345678")


@pytest.mark.parametrize("persona,expected", [
    ("ZywOo", "ZywOo"), ("s1mple.", "s1mple."), ("  dev  ", "dev"),
    ("ลูกทีม", "steam_76561198012345678"),        # ชื่อไทยล้วน -> ไม่เหลือตัวอักษรที่ใช้ได้
    ("a", "steam_76561198012345678"),             # สั้นกว่า 3 ตัว
    ("", "steam_76561198012345678"),
])
def test_username_from_steam_persona(persona, expected):
    assert auth.username_for_steam(persona, "76561198012345678") == expected


def test_steam_persona_without_api_key_does_not_invent_a_name(monkeypatch):
    monkeypatch.setattr(auth, "STEAM_API_KEY", "")
    assert auth.steam_persona("76561198012345678") == {"name": "steam_76561198012345678", "avatar": None}


def _get(headers: list[tuple[bytes, bytes]]) -> Request:
    return Request({"type": "http", "method": "GET", "path": "/auth/steam/login", "query_string": b"",
                    "headers": headers, "scheme": "http", "server": ("api", 8000), "client": ("test", 1)})


def test_public_base_keeps_the_port_the_browser_used():
    """Steam ส่งผู้ใช้กลับมาตาม return_to — พลาดพอร์ตเมื่อไรคือล็อกอินไม่สำเร็จ"""
    from backend import app as appmod
    assert appmod._public_base(_get([(b"host", b"localhost:3000")])) == "http://localhost:3000"
    assert appmod._public_base(_get([(b"host", b"cs2.example.com"), (b"x-forwarded-proto", b"https")])) == "https://cs2.example.com"


def test_public_base_prefers_the_configured_url(monkeypatch):
    from backend import app as appmod
    monkeypatch.setattr(appmod, "PUBLIC_URL", "https://scouting.example.com")
    assert appmod._public_base(_get([(b"host", b"localhost:3000")])) == "https://scouting.example.com"


@pytest.mark.parametrize("given,expected", [
    ("/matches/X.dem/rounds/3", "/matches/X.dem/rounds/3"),
    (None, "/player"), ("", "/player"),            # ไม่ระบุ -> หน้าแรกหลังล็อกอิน = สถิติของฉัน
    ("//evil.example/steal", "/player"),          # open redirect
    ("https://evil.example", "/player"),
    ("/login?next=/matches", "/player"),          # วนกลับหน้า login
])
def test_safe_next_only_allows_paths_inside_this_site(given, expected):
    from backend import app as appmod
    assert appmod._safe_next(given) == expected


# ---- สิทธิ์เจ้าของข้อมูล (แทนที่ระบบ role เดิม) ------------------------------------------------
def test_owner_is_computed_correctly_for_steam_accounts():
    from backend import app as appmod
    owner = {"type": "steam", "id": 7, "username": "alice", "guest_id": None}
    other = {"type": "steam", "id": 8, "username": "bob", "guest_id": None}
    match = {"id": 1, "uploaded_by": 7, "uploader_type": "steam", "uploader_guest": None}
    assert appmod.is_match_owner(match, owner) is True
    assert appmod.is_match_owner(match, other) is False


def test_owner_is_computed_correctly_for_guests():
    """guest เทียบความเป็นเจ้าของด้วย uploader_guest ไม่ใช่ uploaded_by (ซึ่งเป็น NULL เสมอ)"""
    from backend import app as appmod
    me = {"type": "guest", "id": None, "username": None, "guest_id": "g_aaa"}
    someone_else = {"type": "guest", "id": None, "username": None, "guest_id": "g_bbb"}
    match = {"id": 1, "uploaded_by": None, "uploader_type": "guest", "uploader_guest": "g_aaa"}
    assert appmod.is_match_owner(match, me) is True
    assert appmod.is_match_owner(match, someone_else) is False
    # guest ต้องไม่กลายเป็นเจ้าของแมตช์ของผู้ใช้ Steam เพราะ uploaded_by ไม่ใช่ NULL
    assert appmod.is_match_owner({"id": 2, "uploaded_by": 7, "uploader_guest": None}, me) is False


def test_match_without_owner_has_no_owner_and_does_not_error():
    """แมตช์ legacy (uploaded_by = NULL) ต้องคืน False เฉย ๆ ไม่ใช่ error

    NULL เกิดได้สามทาง: แมตช์เก่าก่อน migration 0010, เจ้าของถูกลบบัญชี, และผู้อัปเป็น guest
    สองกรณีแรกคือ "ไม่มีเจ้าของ" — ไม่มีใครเป็นเจ้าของได้
    """
    from backend import app as appmod
    legacy = {"id": 1, "uploaded_by": None, "uploader_type": "legacy", "uploader_guest": None}
    for viewer in ({"type": "steam", "id": 7, "username": "alice", "guest_id": None},
                   {"type": "guest", "id": None, "username": None, "guest_id": "g_aaa"}):
        assert appmod.is_match_owner(legacy, viewer) is False
    # แถวที่ query มาไม่ได้เลือกคอลัมน์พวกนี้เลยก็ต้องไม่ระเบิด
    assert appmod.is_match_owner({"id": 1}, {"type": "steam", "id": 7, "username": "a", "guest_id": None}) is False
    assert appmod.is_match_owner({"id": 1}, {"type": "guest", "id": None, "username": None, "guest_id": "g_a"}) is False


def test_everyone_can_modify_for_now_but_the_rule_lives_in_one_place():
    """ตอนนี้ยังไม่แยกสิทธิ์ — ทั้ง Steam และ guest ทำได้เท่ากัน

    แต่กฎต้องอยู่ใน can_modify_match() ที่เดียว และ is_match_owner() ต้องไม่ถูกลบทิ้ง
    เพื่อให้วันที่จะแยกสิทธิ์จริง แก้ได้ที่ฟังก์ชันเดียวตามที่ตกลงไว้
    """
    import inspect

    from backend import app as appmod
    for viewer in ({"type": "steam", "id": 8, "username": "bob", "guest_id": None},
                   {"type": "guest", "id": None, "username": None, "guest_id": "g_zzz"}):
        assert appmod.can_modify_match({"id": 1, "uploaded_by": 7, "uploader_guest": None}, viewer) is True
    assert callable(appmod.is_match_owner)
    assert "is_match_owner" in inspect.getsource(appmod.can_modify_match)


def test_upload_is_open_to_steam_and_guest_alike():
    """อัปโหลดต้องไม่ผูกกับ role และไม่ผูกกับชนิดผู้ดู — ขอแค่มี session"""
    import inspect

    from backend import app as appmod
    assert not hasattr(appmod, "require_admin")
    assert not hasattr(appmod, "require_login")
    src = inspect.getsource(appmod.api_upload_demo)
    assert "require_viewer" in src and "require_admin" not in src
    # ที่มาของไฟล์ต้องถูกบันทึกตั้งแต่ตอนรับ ไม่ใช่ตอนแกะเสร็จ
    assert "uploader_type" in src and "uploader_guest" in src


def test_every_api_route_goes_through_the_single_gate():
    """ทุก route ใต้ /api และ /auth/me ต้องผ่าน require_viewer ตัวเดียว ไม่มีใครเช็คเอง"""
    import inspect

    from backend import app as appmod
    for route in appmod.app.routes:
        path = getattr(route, "path", "")
        if not (path.startswith("/api/") or path == "/auth/me") or path.startswith("/api/health"):
            continue
        if path in ("/api/docs", "/api/openapi.json"):
            continue
        src = inspect.getsource(route.endpoint)
        assert "require_viewer" in src, f"{path} ไม่ได้ผ่าน require_viewer"
