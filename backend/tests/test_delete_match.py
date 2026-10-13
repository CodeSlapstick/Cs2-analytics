import asyncio
from contextlib import asynccontextmanager

import pytest
from fastapi import HTTPException

from backend import app as appmod


class DeleteConnection:
    def __init__(self, record):
        self.record = record
        self.deleted = False

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetchrow(self, sql, match_id):
        assert "FOR UPDATE" in sql
        return self.record

    async def execute(self, sql, match_id):
        assert sql == "DELETE FROM matches WHERE id = $1"
        self.deleted = True


def record(*, source="upload", status="done", demo_file="sample.dem"):
    return {"id": 1, "source": source, "status": status, "demo_file": demo_file,
            "uploaded_by": None, "uploader_guest": None}


def test_delete_match_removes_upload_record_and_files(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    parsed = tmp_path / "json"
    uploads.mkdir()
    parsed.mkdir()
    demo = uploads / "sample.dem"
    json_file = parsed / "sample.json"
    demo.write_bytes(b"demo")
    json_file.write_text("{}")
    monkeypatch.setattr(appmod, "DEMOS_DIR", uploads)
    monkeypatch.setattr(appmod, "JSON_DIR", parsed)
    conn = DeleteConnection(record())

    result = asyncio.run(appmod.api_delete_match(1, {}, conn))

    assert result == {"deleted": True, "cleanup_failed": []}
    assert conn.deleted
    assert not demo.exists()
    assert not json_file.exists()


@pytest.mark.parametrize("item,expected", [
    (None, 404),
    (record(source="reference"), 404),
    (record(status="queued"), 409),
    (record(status="parsing"), 409),
    (record(demo_file="../sample.dem"), 409),
])
def test_delete_match_rejects_unsafe_or_active_records(item, expected):
    conn = DeleteConnection(item)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(appmod.api_delete_match(1, {}, conn))
    assert exc.value.status_code == expected
    assert not conn.deleted
