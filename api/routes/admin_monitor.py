# api/routes/admin_monitor.py
"""Administrasi wilayah dan ingest manual (INTERFACE.md §4.9, bagian Tahap 3).

Dijaga ``require_role("ADMIN")`` di api/main.py (prefix /api/admin).

    GET   /admin/regions          kecamatan Lebak + status in_aoi
    PATCH /admin/regions/{id}     {in_aoi} -> ROI AOI + dataset HYDROMET_AOI dibangun ulang
    POST  /admin/rois             ROI gabungan dari daftar region_id kecamatan
    POST  /admin/ingest           {job: HYDROMET|LIVE, date_from, date_to, area_id?} -> 202
"""

from __future__ import annotations

import logging
import threading
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Literal

from api.deps import get_etl_db, get_session
from api.errors import ApiError
from api.schemas_monitor import RegionAoiUpdate, UnionRoiCreate
from etl import regions as rg

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_INGEST_DAYS = 366


def _region_rows(sess: Session, where: str = "true", params: dict | None = None) -> list[dict]:
    rows = sess.execute(text(f"""
        SELECT region_id, pcode, region_name, admin_level, parent_region_id, in_aoi, area_km2, source_dataset
        FROM administrative_regions WHERE {where} ORDER BY admin_level, region_name"""), params or {}).mappings().all()
    return [{**r, "area_km2": None if r["area_km2"] is None else float(r["area_km2"])} for r in rows]


@router.get("/regions", summary="List Lebak kecamatan with their AOI flag")
def list_admin_regions(sess: Session = Depends(get_session)) -> dict:
    items = _region_rows(sess)
    return {"items": items, "total": len(items), "aoi_count": sum(1 for r in items if r["in_aoi"])}


@router.patch("/regions/{region_id}", summary="Include/exclude a kecamatan from the GMLS AOI")
def update_region(region_id: int, req: RegionAoiUpdate, sess: Session = Depends(get_session)) -> dict:
    rows = _region_rows(sess, "region_id = :r", {"r": region_id})
    if not rows:
        raise ApiError(404, f"Region {region_id} not found", "NOT_FOUND")
    if rows[0]["admin_level"] != 3:
        raise ApiError(400, "Only kecamatan (admin level 3) can be part of the AOI", "NOT_KECAMATAN")
    if req.in_aoi is False:
        remaining = sess.scalar(text("SELECT count(*) FROM administrative_regions WHERE in_aoi AND region_id <> :r"),
                                {"r": region_id})
        if remaining == 0:
            raise ApiError(409, "The AOI must keep at least one kecamatan", "AOI_EMPTY")
    sess.execute(text("UPDATE administrative_regions SET in_aoi = :a WHERE region_id = :r"),
                 {"a": req.in_aoi, "r": region_id})
    roi_id = rg.rebuild_monitor_aoi(sess)
    return {**_region_rows(sess, "region_id = :r", {"r": region_id})[0], "aoi_roi_id": roi_id}


@router.post("/rois", status_code=201, summary="Create an ROI from a list of kecamatan")
def create_roi(req: UnionRoiCreate, sess: Session = Depends(get_session)) -> dict:
    try:
        roi_id = rg.create_union_roi(sess, req.region_ids, req.name, req.region_code)
    except ValueError as exc:
        raise ApiError(400, str(exc), "INVALID_ROI")
    row = sess.execute(text("""
        SELECT region_id, region_code, name, description, area_km2,
               ST_XMin(bbox) AS x0, ST_YMin(bbox) AS y0, ST_XMax(bbox) AS x1, ST_YMax(bbox) AS y1
        FROM regions_of_interest WHERE region_id = :r"""), {"r": roi_id}).mappings().one()
    return {"region_id": row["region_id"], "region_code": row["region_code"], "name": row["name"],
            "description": row["description"], "area_km2": float(row["area_km2"]),
            "bbox": [float(row[k]) for k in ("x0", "y0", "x1", "y1")]}


class IngestRequest(BaseModel):
    job: Literal["HYDROMET", "LIVE"]
    date_from: date | None = None
    date_to: date | None = None
    area_id: int | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.job == "HYDROMET":
            if not self.date_from or not self.date_to:
                raise ValueError("HYDROMET needs date_from and date_to")
            if self.date_to < self.date_from:
                raise ValueError("date_to must not be before date_from")
            if (self.date_to - self.date_from).days + 1 > MAX_INGEST_DAYS:
                raise ValueError(f"at most {MAX_INGEST_DAYS} days per request")
        if self.job == "LIVE" and self.area_id is None:
            raise ValueError("LIVE needs area_id")
        return self


def _hydromet_thread(etl, date_from: date, date_to: date) -> None:
    from etl.hydromet_job import backfill
    try:
        backfill(etl, date_from, date_to, echo=lambda m: logger.info("[INGEST] %s", m))
    except Exception:
        logger.exception("[INGEST] hydromet %s..%s gagal", date_from, date_to)


@router.post("/ingest", status_code=202, summary="Run Hydromet for a date range, or a Live cycle now")
def ingest(req: IngestRequest, sess: Session = Depends(get_session), etl=Depends(get_etl_db)) -> dict:
    if req.job == "LIVE":
        from etl.live_monitor import LiveMonitor
        if not sess.scalar(text("SELECT 1 FROM live_areas WHERE area_id = :a AND deleted_at IS NULL"),
                           {"a": req.area_id}):
            raise ApiError(404, f"Live Area {req.area_id} not found", "NOT_FOUND")
        started = LiveMonitor(etl).start_cycle(req.area_id)
        return {"accepted": True, "job": "LIVE", "area_id": req.area_id, "started": started}
    if rg.hydromet_dataset(sess) is None:
        raise ApiError(409, "System dataset HYDROMET_AOI is missing; set the AOI first", "HYDROMET_NOT_READY")
    threading.Thread(target=_hydromet_thread, args=(etl, req.date_from, req.date_to),
                     name=f"ingest-hydromet-{req.date_from}", daemon=True).start()
    return {"accepted": True, "job": "HYDROMET", "date_from": req.date_from, "date_to": req.date_to,
            "note": "runs in the background under the 'hydromet' advisory lock; skipped if another worker holds it"}
