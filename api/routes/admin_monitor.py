# api/routes/admin_monitor.py
"""Administrasi wilayah dan ingest manual (INTERFACE.md §4.9, bagian Tahap 3).

Dijaga ``require_role("ADMIN")`` di api/main.py (prefix /api/admin).

    GET   /admin/regions          kecamatan Lebak + status in_aoi
    PATCH /admin/regions/{id}     {in_aoi} -> ROI AOI + dataset HYDROMET_AOI dibangun ulang
    POST  /admin/rois             ROI gabungan dari daftar region_id kecamatan
    POST  /admin/ingest           {job: HYDROMET|LIVE, date_from, date_to, area_id?} -> 202
    PATCH /admin/scenes/{source}/{id}            {is_valid, reason} (soft delete)
    POST  /admin/scenes/{source}/{id}/reprocess  -> 202
    GET/PUT /admin/quality-thresholds, /admin/settings
    GET   /admin/pipeline/status, /admin/archive/stats; POST /admin/archive/verify
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import date
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, model_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import current_principal, get_etl_db, get_session
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


# --- scene: soft delete & proses ulang (§4.9) ----------------------------------------

_SCENE_TABLES = {"S1": ("satellite_scenes", "scene_id"), "MODIS": ("nasa_scenes", "nasa_scene_id"),
                 "GPM": ("nasa_scenes", "nasa_scene_id")}


class SceneValidityUpdate(BaseModel):
    is_valid: bool
    reason: str | None = None


def _scene_row(sess: Session, source: str, scene_id: int) -> dict:
    if source not in _SCENE_TABLES:
        raise ApiError(400, "source must be S1, MODIS or GPM", "INVALID_SOURCE")
    table, pk = _SCENE_TABLES[source]
    extra = "" if source == "S1" else " AND source = :src"
    date_expr = "(acquisition_datetime AT TIME ZONE 'UTC')::date" if source == "S1" else "acquisition_date"
    row = sess.execute(text(f"""SELECT {pk} AS id, is_valid, invalid_reason, invalidated_at, invalidated_by,
                                       {date_expr} AS acquisition_date
                                FROM {table} WHERE {pk} = :i{extra}"""),
                       {"i": scene_id, "src": source}).mappings().first()
    if row is None:
        raise ApiError(404, f"{source} scene {scene_id} not found", "NOT_FOUND")
    return dict(row)


@router.patch("/scenes/{source}/{scene_id}", summary="Mark a scene/granule valid or invalid (soft delete)")
def set_scene_validity(source: str, scene_id: int, req: SceneValidityUpdate, sess: Session = Depends(get_session),
                       principal=Depends(current_principal)) -> dict:
    source = source.upper()
    _scene_row(sess, source, scene_id)
    table, pk = _SCENE_TABLES[source]
    if not req.is_valid and not (req.reason or "").strip():
        raise ApiError(400, "A reason is required when marking a scene invalid", "REASON_REQUIRED")
    if req.is_valid:
        sess.execute(text(f"""UPDATE {table} SET is_valid = true, invalid_reason = NULL, invalidated_at = NULL,
                                                invalidated_by = NULL WHERE {pk} = :i"""), {"i": scene_id})
    else:
        sess.execute(text(f"""UPDATE {table} SET is_valid = false, invalid_reason = :r, invalidated_at = now(),
                                                invalidated_by = :u WHERE {pk} = :i"""),
                     {"i": scene_id, "r": req.reason.strip(), "u": principal.user_id})
    return {"source": source, **_scene_row(sess, source, scene_id)}


def _reprocess_hydromet(etl, day: date) -> None:
    from etl import hydromet_job as hj
    from etl.advisory_lock import advisory_lock
    with advisory_lock(etl, "hydromet", wait_seconds=600) as got:
        if not got:
            logger.warning("[ADMIN] proses ulang hidromet %s dilewati: kunci hydromet sibuk", day)
            return
        try:
            hj.run_day(etl, day, rebuild_non_final=True)
        except Exception:
            logger.exception("[ADMIN] proses ulang hidromet %s gagal", day)


@router.post("/scenes/{source}/{scene_id}/reprocess", status_code=202, summary="Reprocess a scene/granule")
def reprocess_scene(source: str, scene_id: int, sess: Session = Depends(get_session), etl=Depends(get_etl_db)) -> dict:
    """GPM/MODIS: Job Hidromet tanggal granule itu dijalankan ulang (zonal +
    alert; COG non-Final dibangun ulang). S1: scene Live tanggal itu dicoba
    ulang; scene dataset Katalog diproses ulang dengan menjalankan ulang
    dataset-nya (409 NOT_REPROCESSABLE)."""
    source = source.upper()
    row = _scene_row(sess, source, scene_id)
    day = row["acquisition_date"]
    if source in ("GPM", "MODIS"):
        if rg.hydromet_dataset(sess) is None:
            raise ApiError(409, "System dataset HYDROMET_AOI is missing; set the AOI first", "HYDROMET_NOT_READY")
        threading.Thread(target=_reprocess_hydromet, args=(etl, day), name=f"reprocess-{source}-{day}",
                         daemon=True).start()
        return {"accepted": True, "source": source, "date": day, "job": "HYDROMET"}
    area_ids = sess.scalars(text("""SELECT DISTINCT s.area_id FROM live_scenes s JOIN live_areas a USING (area_id)
                                    WHERE s.scene_date = :d AND s.deleted_at IS NULL AND a.deleted_at IS NULL"""),
                            {"d": day}).all()
    if not area_ids:
        raise ApiError(409, "This Sentinel-1 scene is not part of a Live Area; rerun its dataset instead",
                       "NOT_REPROCESSABLE")
    from etl.live_monitor import LiveMonitor
    started = [a for a in area_ids if LiveMonitor(etl).retry_scene(a, day)]
    return {"accepted": True, "source": source, "date": day, "job": "LIVE", "areas": list(area_ids),
            "started": started}


# --- ambang kualitas & pengaturan ----------------------------------------------------

class ThresholdUpdate(BaseModel):
    threshold_id: int
    warn_below: float | None = None
    fail_below: float | None = None
    warn_above: float | None = None
    fail_above: float | None = None
    reference: str | None = None
    is_active: bool | None = None


_LIMIT_COLS = ("warn_below", "fail_below", "warn_above", "fail_above")


@router.get("/quality-thresholds", summary="Quality-control thresholds per band")
def list_thresholds(sess: Session = Depends(get_session)) -> dict:
    rows = sess.execute(text("""SELECT q.threshold_id, b.band_code, q.metric_name, q.warn_below, q.fail_below,
                                       q.warn_above, q.fail_above, q.reference, q.is_active
                                FROM quality_thresholds q JOIN spectral_bands b USING (band_id)
                                ORDER BY b.band_code, q.metric_name""")).mappings().all()
    items = [{k: (float(v) if k in _LIMIT_COLS and v is not None else v) for k, v in r.items()} for r in rows]
    return {"items": items, "total": len(items)}


@router.put("/quality-thresholds", summary="Update quality-control thresholds")
def update_thresholds(req: list[ThresholdUpdate], sess: Session = Depends(get_session)) -> dict:
    for t in req:
        fields = t.model_dump(exclude_unset=True)
        fields.pop("threshold_id")
        if not fields:
            continue
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        try:
            with sess.begin_nested():
                hit = sess.execute(text(f"UPDATE quality_thresholds SET {sets} WHERE threshold_id = :i RETURNING 1"),
                                   {**fields, "i": t.threshold_id}).first()
        except IntegrityError:
            raise ApiError(400, f"Threshold {t.threshold_id}: fail limit must lie beyond the warn limit",
                           "INVALID_THRESHOLD")
        if hit is None:
            raise ApiError(404, f"Threshold {t.threshold_id} not found", "NOT_FOUND")
    return list_thresholds(sess)


# Validasi per kunci: (tipe, min, max); untuk teks min/max = panjang.
_SETTING_RULES = {
    "live.max_areas": (int, 1, 20), "live.retention_max": (int, 1, 60), "live.retention_default": (int, 1, 60),
    "water.vh_threshold_db": (float, -40, -5), "dataset.max_days": (int, 1, 3660),
    "hydromet.min_valid_fraction": (float, 0, 1), "hydromet.waiting_max_days": (int, 0, 30),
    "report.wait_hydromet_minutes": (float, 0, 240), "live.default_area_name": (str, 1, 100),
    "report.timezone": (str, 1, 50),
}


class SettingsUpdate(BaseModel):
    settings: dict[str, Any]


@router.get("/settings", summary="Application settings (app_settings)")
def list_settings(sess: Session = Depends(get_session)) -> dict:
    rows = sess.execute(text("""SELECT setting_key, setting_value, description, updated_by, updated_at
                                FROM app_settings ORDER BY setting_key""")).mappings().all()
    return {"items": [dict(r) for r in rows], "total": len(rows)}


@router.put("/settings", summary="Change application settings (existing keys only)")
def update_settings(req: SettingsUpdate, sess: Session = Depends(get_session),
                    principal=Depends(current_principal)) -> dict:
    for key, value in req.settings.items():
        rule = _SETTING_RULES.get(key)
        if rule:
            typ, lo, hi = rule
            try:
                value = typ(value)
            except (TypeError, ValueError):
                raise ApiError(400, f"{key} must be {typ.__name__}", "INVALID_SETTING")
            size = len(value) if typ is str else value
            if not lo <= size <= hi:
                raise ApiError(400, f"{key} must be between {lo} and {hi}", "INVALID_SETTING")
        hit = sess.execute(text("""UPDATE app_settings SET setting_value = CAST(:v AS jsonb), updated_by = :u,
                                          updated_at = now() WHERE setting_key = :k RETURNING 1"""),
                           {"v": json.dumps(value), "u": principal.user_id, "k": key}).first()
        if hit is None:
            raise ApiError(404, f"Unknown setting {key}", "NOT_FOUND")
    out = list_settings(sess)
    vals = {r["setting_key"]: r["setting_value"] for r in out["items"]}
    if int(vals.get("live.retention_default", 6)) > int(vals.get("live.retention_max", 60)):
        raise ApiError(400, "live.retention_default must not exceed live.retention_max", "INVALID_SETTING")
    return out


# --- status pipeline & arsip ----------------------------------------------------------

@router.get("/pipeline/status", summary="Latest job per kind, credentials, queue, schedule")
def pipeline_status(sess: Session = Depends(get_session)) -> dict:
    jobs = sess.execute(text("""
        SELECT DISTINCT ON (kind) kind, job_id, status, date_range_start, started_at, completed_at FROM (
            SELECT CASE WHEN d.is_system THEN 'HYDROMET' WHEN d.dataset_kind = 'LIVE_AREA' THEN 'LIVE'
                        ELSE 'DATASET' END AS kind, j.*
            FROM dataset_jobs j JOIN datasets d USING (dataset_id)) q
        ORDER BY kind, job_id DESC""")).mappings().all()
    hydromet = sess.execute(text("""
        SELECT max(date_range_start) FILTER (WHERE status = 'COMPLETED') AS last_completed,
               count(*) FILTER (WHERE status = 'WAITING_UPSTREAM') AS waiting,
               count(*) FILTER (WHERE status = 'FAILED') AS failed
        FROM dataset_jobs WHERE job_type = 'HYDROMET_DAILY'""")).mappings().one()
    last_obs = sess.scalar(text("SELECT max(obs_date) FROM region_observations"))
    reports = sess.execute(text("""SELECT DISTINCT ON (t.report_code) t.report_code, g.status, g.period_start,
                                          g.generated_at FROM generated_reports g JOIN report_types t USING (report_type_id)
                                   ORDER BY t.report_code, g.generated_at DESC""")).mappings().all()
    skipped = sess.execute(text("""SELECT parameters_json->>'scheduler_job' AS job, max(queued_at) AS last_at, count(*) AS n
                                   FROM processing_jobs WHERE status = 'SKIPPED_LOCKED'
                                     AND queued_at > now() - interval '7 days' GROUP BY 1""")).mappings().all()
    queue = sess.scalar(text("SELECT count(*) FROM dataset_jobs WHERE status = 'QUEUED'"))
    live = sess.execute(text("""SELECT area_id, name, status, status_message, last_checked_at FROM live_areas
                                WHERE deleted_at IS NULL ORDER BY area_id""")).mappings().all()
    schedule = []
    try:
        from api import main as api_main
        if api_main._scheduler is not None:
            schedule = api_main._scheduler.jobs()
    except Exception:
        logger.exception("[ADMIN] gagal membaca jadwal scheduler")
    return {
        "latest_jobs": [dict(j) for j in jobs],
        "hydromet": {**dict(hydromet), "last_observation_date": last_obs},
        "live_areas": [dict(a) for a in live],
        "reports": [dict(r) for r in reports],
        "skipped_locked_7d": [dict(s) for s in skipped],
        "queue": {"dataset_jobs_queued": queue},
        # Hanya ada/tidaknya kredensial; nilainya tidak pernah dikirim.
        "credentials": {"nasa_earthdata_token": bool(os.getenv("NASA_EARTHDATA_TOKEN")),
                        "copernicus": any(os.getenv(k) for k in ("COPERNICUS_USERNAME", "COPERNICUS_USER",
                                                                 "CDSE_USERNAME"))},
        "scheduler": schedule,
    }


@router.get("/archive/stats", summary="Archive size per source/tier and row counts")
def archive_stats(sess: Session = Depends(get_session)) -> dict:
    products = sess.execute(text("""SELECT source, product_tier::text AS tier, count(*) AS n,
                                           round(sum(file_size_mb)::numeric, 1) AS mb,
                                           count(*) FILTER (WHERE NOT is_valid) AS invalid
                                    FROM data_products WHERE is_latest GROUP BY 1, 2 ORDER BY 1, 2""")).mappings().all()
    counts = {t: sess.scalar(text(f"SELECT count(*) FROM {t}")) for t in
              ("region_observations", "alert_events", "disaster_events", "live_scenes", "satellite_scenes",
               "nasa_scenes", "generated_reports", "data_lineage")}
    span = sess.execute(text("SELECT min(obs_date) AS first, max(obs_date) AS last FROM region_observations")).mappings().one()
    return {"products": [{**p, "mb": float(p["mb"] or 0)} for p in products], "rows": counts,
            "hydromet_span": dict(span)}


class ArchiveVerifyRequest(BaseModel):
    limit: int = 50
    source: Literal["SENTINEL1", "MODIS", "GPM", "FUSION"] | None = None


@router.post("/archive/verify", summary="Verify SHA-256 of a random sample of archived products")
def archive_verify(req: ArchiveVerifyRequest, sess: Session = Depends(get_session)) -> dict:
    limit = max(1, min(req.limit, 500))
    rows = sess.execute(text(f"""SELECT product_id, source, file_path, data_hash_sha256 FROM data_products
                                 WHERE is_latest {'AND source = :s' if req.source else ''}
                                 ORDER BY random() LIMIT :n"""), {"s": req.source, "n": limit}).mappings().all()
    ok, missing, mismatch = 0, [], []
    for r in rows:
        p = Path(r["file_path"])
        if not p.is_file():
            missing.append(r["product_id"])
            continue
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() == r["data_hash_sha256"]:
            ok += 1
        else:
            mismatch.append(r["product_id"])
    return {"checked": len(rows), "ok": ok, "missing": missing, "mismatch": mismatch}
