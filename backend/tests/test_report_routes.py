from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.report_routes import create_report_router


def viewer():
    return {"type": "guest"}


async def empty_db():
    yield None


def test_report_route_validates_side_and_player_id():
    app = FastAPI()
    app.include_router(create_report_router(viewer, empty_db))
    client = TestClient(app)
    assert client.get("/api/reports/coach/1?side=wrong").status_code == 422
    assert client.get("/api/reports/player/1/not-a-steam-id").status_code == 422
    assert client.get("/api/reports/1/text?report_type=player").status_code == 422


def test_report_route_keeps_shared_auth_dependency():
    def denied():
        raise HTTPException(401, "login required")
    app = FastAPI()
    app.include_router(create_report_router(denied, empty_db))
    assert TestClient(app).get("/api/reports/coach/1").status_code == 401
