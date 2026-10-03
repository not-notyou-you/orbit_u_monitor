# api/routes/live.py
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from api.schemas import LiveAreaCreateRequest, LiveAreaUpdateRequest
from api.deps import get_db
from etl.database_client import DatabaseClient
from etl.live_monitor import LiveMonitor

router = APIRouter()
logger = logging.getLogger(__name__)


def _monitor(db: DatabaseClient) -> LiveMonitor:
    return LiveMonitor(db)


@router.get("/areas", summary="List Live Areas")
async def list_areas(db: DatabaseClient = Depends(get_db)) -> list[dict]:
    return _monitor(db).list_areas()


@router.post("/areas", status_code=201, summary="Add a Live Area")
async def create_area(req: LiveAreaCreateRequest, db: DatabaseClient = Depends(get_db)) -> dict:
    try:
        return _monitor(db).create_area(req.region_id, req.name, req.retention)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/areas/{area_id}", summary="Live Area details")
async def get_area(area_id: int, db: DatabaseClient = Depends(get_db)) -> dict:
    try:
        return _monitor(db).get_area(area_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))


@router.patch("/areas/{area_id}", summary="Change a Live Area's name/retention/status")
async def update_area(area_id: int, req: LiveAreaUpdateRequest,
                      db: DatabaseClient = Depends(get_db)) -> dict:
    try:
        return _monitor(db).update_area(area_id, retention=req.retention,
                                        name=req.name, enabled=req.enabled)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.delete("/areas/{area_id}", summary="Delete a Live Area (files deleted permanently, logs kept)")
async def delete_area(area_id: int, db: DatabaseClient = Depends(get_db)) -> dict:
    import asyncio
    try:
        # Menghapus berkas bisa lama; jangan blokir event loop.
        return await asyncio.to_thread(_monitor(db).delete_area, area_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))


@router.post("/areas/{area_id}/check", summary="Run a cycle now")
async def run_area_check(area_id: int, db: DatabaseClient = Depends(get_db)) -> dict:
    mon = _monitor(db)
    try:
        mon.get_area(area_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    started = mon.start_cycle(area_id)
    return {"area_id": area_id, "started": started,
            "message": "Cycle started" if started else "A cycle is already running"}


@router.get("/areas/{area_id}/card", summary="Area card contents (selected scene, dates, forecast)")
async def area_card(area_id: int, date: str | None = Query(None, description="YYYY-MM-DD"),
                    db: DatabaseClient = Depends(get_db)) -> dict:
    from datetime import date as date_cls
    try:
        d = date_cls.fromisoformat(date) if date else None
    except ValueError:
        raise HTTPException(400, "Date format must be YYYY-MM-DD")
    try:
        return _monitor(db).get_card(area_id, d)
    except LookupError as exc:
        raise HTTPException(404, str(exc))


@router.get("/areas/{area_id}/preview/{scene_date}/{key}.png", summary="PNG preview of a single scene")
async def area_preview(area_id: int, scene_date: str, key: str,
                       db: DatabaseClient = Depends(get_db)):
    from datetime import date as date_cls
    from fastapi.responses import FileResponse
    try:
        d = date_cls.fromisoformat(scene_date)
    except ValueError:
        raise HTTPException(400, "Date format must be YYYY-MM-DD")
    path = _monitor(db).preview_path(area_id, d, key)
    if path is None:
        raise HTTPException(404, "Preview not found")
    return FileResponse(path, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})


@router.get("/areas/{area_id}/events", summary="Cycle step log")
async def area_events(area_id: int, limit: int = Query(100, ge=1, le=1000),
                      db: DatabaseClient = Depends(get_db)) -> list[dict]:
    return _monitor(db).events(area_id, limit)


@router.get("/areas/{area_id}/activity", summary="Latest log: cycle steps + download/processing pipeline")
async def area_activity(area_id: int, limit: int = Query(5, ge=1, le=200),
                        db: DatabaseClient = Depends(get_db)) -> list[dict]:
    try:
        return _monitor(db).activity(area_id, limit)
    except LookupError as exc:
        raise HTTPException(404, str(exc))


@router.get("/areas/{area_id}/log", summary="Scene log, including deleted scenes")
async def area_scene_log(area_id: int, db: DatabaseClient = Depends(get_db)) -> list[dict]:
    return _monitor(db).scene_log(area_id)


@router.post("/areas/{area_id}/scenes/{scene_date}/retry", summary="Retry MODIS/GPM for a single scene")
async def retry_scene(area_id: int, scene_date: str, db: DatabaseClient = Depends(get_db)) -> dict:
    from datetime import date as date_cls
    try:
        d = date_cls.fromisoformat(scene_date)
        started = _monitor(db).retry_scene(area_id, d)
    except ValueError:
        raise HTTPException(400, "Date format must be YYYY-MM-DD")
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    return {"area_id": area_id, "scene_date": scene_date, "started": started,
            "message": "Retry started" if started else "A cycle for this area is already running"}
