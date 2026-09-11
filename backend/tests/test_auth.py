# -*- coding: utf-8 -*-
"""ล็อกอิน: hash รหัสผ่าน, JWT ใน httpOnly cookie, dependency require_login และ route ที่เปิดไว้"""
import base64
import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.requests import Request

from backend import auth

FAST = 1_000          # รอบน้อย ๆ ไว้ทดสอบตรรกะ (ความแข็งแรงของ hash ทดสอบแยกข้างล่าง)
SECRET = "s" * 40


def test_hash_verifies_and_salts_differ():
    h1 = auth.hash_password("correct horse", iterations=FAST)
    h2 = auth.hash_password("correct horse", iterations=FAST)
    assert h1 != h2 and h1.startswith("pbkdf2_sha256$1000$")
    assert auth.verify_password("correct horse", h1)
    assert not auth.verify_password("correct horsE", h1)


def test_default_hash_is_strong():
    h = auth.hash_password("password123")
    assert int(h.split("$")[1]) >= 300_000
    assert auth.verify_password("password123", h)


@pytest.mark.parametrize("stored", ["", "plain", "md5$1$a$b", "pbkdf2_sha256$x$a$b", "pbkdf2_sha256$1000$@@$@@", None])
def test_verify_rejects_garbage_without_raising(stored):
    assert auth.verify_password("pw", stored) is False


def test_token_roundtrip():
    t = auth.create_token(7, "alice", secret=SECRET)
    assert auth.user_from_token(t, secret=SECRET) == {"id": 7, "username": "alice"}


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


@pytest.mark.parametrize("username,password,ok", [
    ("dev", "cs2dev1234", True), ("a.b-c_d", "12345678", True),
    ("ab", "12345678", False), ("x" * 33, "12345678", False), ("bad name", "12345678", False),
    ("ไทย", "12345678", False), ("dev", "short", False), ("dev", "x" * 300, False), (None, None, False),
])
def test_validate_credentials(username, password, ok):
    assert (auth.validate_credentials(username, password) is None) is ok


def test_cookie_is_httponly_lax_and_clearable():
    r = JSONResponse({})
    auth.set_auth_cookie(r, "tok")
    h = r.headers["set-cookie"].lower()
    assert f"{auth.COOKIE_NAME}=tok" in h and "httponly" in h and "samesite=lax" in h and "path=/" in h
    r2 = JSONResponse({})
    auth.clear_auth_cookie(r2)
    assert "max-age=0" in r2.headers["set-cookie"].lower()


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


def test_auth_routes_are_jwt_only():
    from backend import app as appmod
    routes = {(m, r.path) for r in appmod.app.routes for m in getattr(r, "methods", ()) or ()}
    for expected in [("POST", "/auth/register"), ("POST", "/auth/login"), ("GET", "/auth/me"), ("POST", "/auth/logout")]:
        assert expected in routes
    paths = {p for _, p in routes}
    assert not any(p.startswith("/auth/steam") or p == "/auth/dev-login" for p in paths)
