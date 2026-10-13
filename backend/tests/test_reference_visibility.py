import asyncio

import pytest
from fastapi import HTTPException

from backend.app import _review_match, api_analysis_reference_maps, api_match, api_match_status, api_matches


class RecordingConnection:
    def __init__(self, rows=None):
        self.sql: list[str] = []
        self.rows = rows or []

    async def fetch(self, sql, *args):
        self.sql.append(sql)
        return self.rows

    async def fetchrow(self, sql, *args):
        self.sql.append(sql)
        return None


def assert_upload_only(sql: str) -> None:
    assert "source = 'upload'" in sql


def test_match_catalog_does_not_expose_reference_matches():
    conn = RecordingConnection()
    assert asyncio.run(api_matches({}, conn)) == []
    assert_upload_only(conn.sql[-1])


def test_analysis_exposes_only_reference_map_names():
    conn = RecordingConnection([{"map_name": "de_ancient"}, {"map_name": "de_mirage"}])
    assert asyncio.run(api_analysis_reference_maps({}, conn)) == ["de_ancient", "de_mirage"]
    assert "source = 'reference'" in conn.sql[-1]
    assert "demo_file" not in conn.sql[-1]


@pytest.mark.parametrize("endpoint", [api_match, api_match_status])
def test_match_id_endpoints_do_not_expose_reference_matches(endpoint):
    conn = RecordingConnection()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(endpoint(123, {}, conn))
    assert exc.value.status_code == 404
    assert_upload_only(conn.sql[-1])


def test_review_endpoints_do_not_open_reference_demo_files():
    conn = RecordingConnection()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_review_match(conn, "pro-reference.dem"))
    assert exc.value.status_code == 404
    assert_upload_only(conn.sql[-1])
