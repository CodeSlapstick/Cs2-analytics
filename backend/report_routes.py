# -*- coding: utf-8 -*-
"""FastAPI routes for reports. Validation and transport only."""
from collections.abc import Callable

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from backend.report_export import build_text_report
from backend.report_repository import ReportNotFoundError, ReportRepository
from backend.report_schemas import ReportResponse
from backend.report_service import ReportService


def create_report_router(require_viewer: Callable, db: Callable) -> APIRouter:
    router = APIRouter(prefix="/api/reports", tags=["reports"])

    @router.get("/coach/{match_id}", response_model=ReportResponse)
    async def coach_report(match_id: int, side: str = Query("all", pattern="^(all|t|ct)$"),
                           _: dict = Depends(require_viewer), conn: asyncpg.Connection = Depends(db)):
        return await _call(lambda: ReportService(ReportRepository(conn)).coach_report(match_id, side))

    @router.get("/player/{match_id}/{steam_id}", response_model=ReportResponse)
    async def player_report(match_id: int, steam_id: str, side: str = Query("all", pattern="^(all|t|ct)$"),
                            _: dict = Depends(require_viewer), conn: asyncpg.Connection = Depends(db)):
        if not steam_id.isdigit():
            raise HTTPException(422, "steam_id ต้องเป็นตัวเลข")
        return await _call(lambda: ReportService(ReportRepository(conn)).player_report(match_id, steam_id, side))

    @router.get("/{match_id}/text")
    async def report_text(match_id: int, report_type: str = Query("coach", pattern="^(coach|player)$"),
                          steam_id: str | None = None, side: str = Query("all", pattern="^(all|t|ct)$"),
                          _: dict = Depends(require_viewer), conn: asyncpg.Connection = Depends(db)):
        service = ReportService(ReportRepository(conn))
        if report_type == "player" and not (steam_id and steam_id.isdigit()):
            raise HTTPException(422, "Player report ต้องระบุ steam_id")
        report = await _call(lambda: service.player_report(match_id, steam_id, side) if report_type == "player" else service.coach_report(match_id, side))
        name = f"{report.header.map_name or 'match'}-{report_type}-report.txt"
        return Response(build_text_report(report), media_type="text/plain; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    return router


async def _call(factory):
    try:
        return await factory()
    except ReportNotFoundError as exc:
        what = "ผู้เล่น" if str(exc) == "player" else "แมตช์"
        raise HTTPException(404, f"ไม่พบ{what}ที่พร้อมสร้างรายงาน") from None
