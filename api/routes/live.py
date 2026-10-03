# api/routes/live.py
"""Live Monitoring (INTERFACE.md §4.3).

Baca: USER (router dijaga require_role("USER") di api/main.py); USER s.d.
DATA_ENGINEER hanya melihat scene 30 hari terakhir (plus scene terbaru, yang
toh terlihat publik). Tulis dan log: ADMIN.

Perubahan baris (buat/ubah daerah) berjalan di sesi request ADMIN; siklus,
retensi, dan penghapusan berkas dikerjakan LiveMonitor dengan koneksi
monitor_etl (DATABASE.md §8.1).
"""
from __future__ import annotations
import logging
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from api.schemas import LiveAreaCreateRequest, LiveAreaUpdateRequest
from api.deps import Principal, current_principal, get_db, get_etl_db, require_role
from api.errors import ApiError
from etl.database_client import DatabaseClient, LiveScene
from etl.live_monitor import LiveMonitor

router = APIRouter()
logger = logging.getLogger(__name__)

USER_WINDOW_DAYS = 30
ADMIN = [Depends(require_role("ADMIN"))]


def _monitor(db: DatabaseClient, etl: DatabaseClient | None = None) -> LiveMonitor:
    return LiveMonitor(db, runner_db=etl)


def _cutoff(principal: Principal) -> date | None:
    """Tanggal scene tertua yang boleh dilihat; None = tanpa batas (ADMIN)."""
    if principal.has_role("ADMIN"):
        return None
    return date.today() - timedelta(days=USER_WINDOW_DAYS)


def _latest_scene_date(db: DatabaseClient, area_id: int) -> date | None:
    with db.session() as sess:
        return sess.scalar(select(func.max(LiveScene.scene_date)).where(
            LiveScene.area_id == area_id, LiveScene.deleted_at.is_(None),
            LiveScene.status.in_(("READY", "PARTIAL"))))


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, "Date format must be YYYY-MM-DD")


@router.get("/areas", summary="List Live Areas")
async def list_areas(db: DatabaseClient = Depends(get_db)) -> list[dict]:
    return _monitor(db).list_areas()


@router.post("/areas", status_code=201, summary="Add a Live Area", dependencies=ADMIN)
async def create_area(req: LiveAreaCreateRequest, db: DatabaseClient = Depends(get_db),
                      etl: DatabaseClient = Depends(get_etl_db)) -> dict:
    try:
        return _monitor(db, etl).create_area(req.region_id, req.name, req.retention)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/areas/{area_id}", summary="Live Area details")
async def get_area(area_id: int, db: DatabaseClient = Depends(get_db)) -> dict:
    try:
        return _monitor(db).get_area(area_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))


@router.patch("/areas/{area_id}", summary="Change a Live Area's name/retention/status", dependencies=ADMIN)
async def update_area(area_id: int, req: LiveAreaUpdateRequest,
                      db: DatabaseClient = Depends(get_db),
                      etl: DatabaseClient = Depends(get_etl_db)) -> dict:
    try:
        return _monitor(db, etl).update_area(area_id, retention=req.retention,
                                             name=req.name, enabled=req.enabled)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.delete("/areas/{area_id}", summary="Delete a Live Area (files deleted permanently, logs kept)",
               dependencies=ADMIN)
async def delete_area(area_id: int, db: DatabaseClient = Depends(get_db),
                      etl: DatabaseClient = Depends(get_etl_db)) -> dict:
    import asyncio
    try:
        _monitor(db).get_area(area_id)
        # Menghapus berkas + baris dataset/produk adalah kerja pipeline
        # (monitor_etl), seperti penghapusan dataset (Tahap 2, S1). Bisa lama;
        # jangan blokir event loop.
        return await asyncio.to_thread(LiveMonitor(etl).delete_area, area_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))


@router.post("/areas/{area_id}/check", summary="Run a cycle now", dependencies=ADMIN)
async def run_area_check(area_id: int, db: DatabaseClient = Depends(get_db),
                         etl: DatabaseClient = Depends(get_etl_db)) -> dict:
    try:
        _monitor(db).get_area(area_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    started = LiveMonitor(etl).start_cycle(area_id)
    return {"area_id": area_id, "started": started,
            "message": "Cycle started" if started else "A cycle is already running"}


@router.get("/areas/{area_id}/card", summary="Area card contents (selected scene, dates, forecast)")
async def area_card(area_id: int, date: str | None = Query(None, description="YYYY-MM-DD"),
                    db: DatabaseClient = Depends(get_db),
                    principal: Principal = Depends(current_principal)) -> dict:
    d = _parse_date(date) if date else None
    cutoff = _cutoff(principal)
    if cutoff is not None and d is not None and d < cutoff and d != _latest_scene_date(db, area_id):
        raise ApiError(403, f"Scenes older than {USER_WINDOW_DAYS} days are available to ADMIN only",
                       "SCENE_OUT_OF_RANGE")
    try:
        card = _monitor(db).get_card(area_id, d)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    if cutoff is not None and card["dates"]:
        latest = card["dates"][0]["date"]
        card["dates"] = [x for x in card["dates"] if x["date"] >= cutoff.isoformat() or x["date"] == latest]
    return card


@router.get("/areas/{area_id}/preview/{scene_date}/{key}.png", summary="PNG preview of a single scene")
async def area_preview(area_id: int, scene_date: str, key: str,
                       db: DatabaseClient = Depends(get_db),
                       principal: Principal = Depends(current_principal)):
    from fastapi.responses import FileResponse
    d = _parse_date(scene_date)
    cutoff = _cutoff(principal)
    if cutoff is not None and d < cutoff and d != _latest_scene_date(db, area_id):
        raise ApiError(403, f"Scenes older than {USER_WINDOW_DAYS} days are available to ADMIN only",
                       "SCENE_OUT_OF_RANGE")
    path = _monitor(db).preview_path(area_id, d, key)
    if path is None:
        raise HTTPException(404, "Preview not found")
    # private: gambar hanya untuk pengguna login, jangan disimpan cache bersama.
    return FileResponse(path, media_type="image/png",
                        headers={"Cache-Control": "private, max-age=86400"})


@router.get("/areas/{area_id}/events", summary="Cycle step log", dependencies=ADMIN)
async def area_events(area_id: int, limit: int = Query(100, ge=1, le=1000),
                      db: DatabaseClient = Depends(get_db)) -> list[dict]:
    return _monitor(db).events(area_id, limit)


@router.get("/areas/{area_id}/activity", summary="Latest log: cycle steps + download/processing pipeline",
            dependencies=ADMIN)
async def area_activity(area_id: int, limit: int = Query(5, ge=1, le=200),
                        db: DatabaseClient = Depends(get_db)) -> list[dict]:
    try:
        return _monitor(db).activity(area_id, limit)
    except LookupError as exc:
        raise HTTPException(404, str(exc))


@router.get("/areas/{area_id}/log", summary="Scene log, including deleted scenes", dependencies=ADMIN)
async def area_scene_log(area_id: int, db: DatabaseClient = Depends(get_db)) -> list[dict]:
    return _monitor(db).scene_log(area_id)


@router.post("/areas/{area_id}/scenes/{scene_date}/retry", summary="Retry MODIS/GPM for a single scene",
             dependencies=ADMIN)
async def retry_scene(area_id: int, scene_date: str, db: DatabaseClient = Depends(get_db),
                      etl: DatabaseClient = Depends(get_etl_db)) -> dict:
    d = _parse_date(scene_date)
    try:
        _monitor(db).get_area(area_id)
        started = LiveMonitor(etl).retry_scene(area_id, d)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    return {"area_id": area_id, "scene_date": scene_date, "started": started,
            "message": "Retry started" if started else "A cycle for this area is already running"}
