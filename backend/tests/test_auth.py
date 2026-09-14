# -*- coding: utf-8 -*-
"""ล็อกอิน: hash รหัสผ่าน, JWT ใน httpOnly cookie, dependency require_login และ route ที่เปิดไว้"""
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

FAST = 1_000          # รอบน้อย ๆ ไว้ทดสอบตรรกะ (ความแข็งแรงของ hash ทดสอบแยกข้างล่าง)
SECRET = "s" * 40


def test_token_roundtrip():
    t = auth.create_token(7, "alice", secret=SECRET)
    assert auth.user_from_token(t, secret=SECRET) == {"id": 7, "username": "alice"}


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
    assert auth.user_from_token(legacy, secret=SECRET) == {"id": 7, "username": "alice"}


def test_expired_tampered_wrong_secret_are_rejected():
    old = auth.create_token(7, "alice", secret=SECRET, now=datetime.now(UTC) - timedelta(days=8))
    assert auth.user_from_token(old, secret=SECRET) is None
    t = auth.create_token(7, "alice", secret=SECRET)
    head, body, sig = t.split(".")
    forged = json.loads(base64.urlsafe_b64decode(body + "=="))
    forged["sub"] = "1"                                   # แอบเปลี่ยนตัวตนแต่คงลายเซ็นเดิม
    forged_body = base64.urlsafe_b64encode(json.dumps(forged).encode()).decode().rstrip("=")
    assert auth.user_from_token(f"{head}.{forged_body}.{sig}", secret=SECRET) is None
    assert auth.user_from_token(t, secret="another-secret-" * 3) is None
    assert auth.user_from_token("", secret=SECRET) is None
    assert auth.user_from_token("not.a.jwt", secret=SECRET) is None


def test_alg_none_and_missing_claims_are_rejected():
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    exp = int((datetime.now(UTC) + timedelta(days=1)).timestamp())
    unsigned = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'sub': '1', 'name': 'x', 'exp': exp})}."
    assert auth.user_from_token(unsigned, secret=SECRET) is None
    no_sub = jwt.encode({"name": "x", "exp": exp}, SECRET, algorithm="HS256")
    assert auth.user_from_token(no_sub, secret=SECRET) is None
    no_exp = jwt.encode({"sub": "1", "name": "x"}, SECRET, algorithm="HS256")
    assert auth.user_from_token(no_exp, secret=SECRET) is None


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


def test_require_login_uses_the_cookie():
    from backend import app as appmod
    tok = auth.create_token(3, "bob")
    assert appmod.require_login(_request(f"{auth.COOKIE_NAME}={tok}")) == {"id": 3, "username": "bob"}
    for cookie in (None, f"{auth.COOKIE_NAME}=garbage", f"cs2_session={tok}"):
        with pytest.raises(HTTPException) as e:
            appmod.require_login(_request(cookie))
        assert e.value.status_code == 401


def test_auth_routes_are_steam_only():
    """ล็อกอินมีทางเดียวคือ Steam OpenID — ห้ามมี local login / สมัครสมาชิก / dev-login กลับมาอีก"""
    from backend import app as appmod
    routes = {(m, r.path) for r in appmod.app.routes for m in getattr(r, "methods", ()) or ()}
    for expected in [("GET", "/auth/me"), ("POST", "/auth/logout"),
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
    (None, "/matches"), ("", "/matches"),
    ("//evil.example/steal", "/matches"),          # open redirect
    ("https://evil.example", "/matches"),
    ("/login?next=/matches", "/matches"),          # วนกลับหน้า login
])
def test_safe_next_only_allows_paths_inside_this_site(given, expected):
    from backend import app as appmod
    assert appmod._safe_next(given) == expected


# ---- สิทธิ์เจ้าของข้อมูล (แทนที่ระบบ role เดิม) ------------------------------------------------
def test_owner_can_modify_but_others_cannot():
    from backend import app as appmod
    owner = {"id": 7, "username": "alice"}
    other = {"id": 8, "username": "bob"}
    match = {"id": 1, "uploaded_by": 7}
    assert appmod.can_modify_match(match, owner) is True
    assert appmod.can_modify_match(match, other) is False


def test_match_without_owner_is_readable_but_not_modifiable():
    """แมตช์ legacy (uploaded_by = NULL) ต้องคืน False เฉย ๆ ไม่ใช่ error

    NULL เกิดได้สองทาง: แมตช์เก่าก่อน migration 0010 และแมตช์ที่เจ้าของถูกลบบัญชี
    ทั้งสองกรณีคือ "ไม่มีเจ้าของ" — ใครก็แก้ไม่ได้จนกว่าจะมีฟีเจอร์กำหนดเจ้าของ
    """
    from backend import app as appmod
    for user in ({"id": 7, "username": "alice"}, {"id": 8, "username": "bob"}):
        assert appmod.can_modify_match({"id": 1, "uploaded_by": None}, user) is False
    # ไม่มีคีย์ uploaded_by เลย (แถวที่ query มาไม่ได้เลือกคอลัมน์นั้น) ก็ต้องไม่ระเบิด
    assert appmod.can_modify_match({"id": 1}, {"id": 7, "username": "alice"}) is False


def test_upload_is_open_to_every_logged_in_user():
    """อัปโหลดต้องไม่ผูกกับ role อีกแล้ว — ขอแค่ล็อกอิน และต้องไม่มี require_admin หลงเหลือ"""
    import inspect

    from backend import app as appmod
    assert not hasattr(appmod, "require_admin")
    src = inspect.getsource(appmod.api_upload_demo)
    assert "require_login" in src and "require_admin" not in src
