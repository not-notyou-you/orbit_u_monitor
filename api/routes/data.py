# api/routes/data.py
"""Halaman Data (INTERFACE.md §4.6, M56): DATA_ENGINEER dan ADMIN.

    GET   /data/summary                          keadaan data per satelit
    GET   /data/{source}/items                   daftar scene/granule (termasuk yang dinonaktifkan)
    PATCH /data/{source}/items/{id}              {is_valid, reason}: nonaktifkan/pulihkan (soft delete, M23/M24)
    POST  /data/{source}/items/{id}/reprocess    proses ulang
    POST  /data/{source}/backfill                {date_from, date_to}
    GET   /data/{source}/backfill                proses berjalan + riwayat per tanggal
    GET   /data/backfill/runs/{run_id}           progres + baris log (polling)
    GET   /data/eda                              EDA per satelit dan rentang tanggal

``source`` = s1 | modis | gpm. Backfill GPM/MODIS = Job Hidromet di thread
latar (``etl.backfill_runs``, log terlihat langsung). Backfill Sentinel-1 =
dataset Katalog khusus S1 atas AOI; progres dan lognya adalah progres dan log
dataset itu (``/api/datasets/{id}/status|logs``). Tidak ada "tambah scene
manual" (M24): data hanya masuk lewat API resmi.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.activity import log_activity, request_meta
from api.deps import Principal, current_principal, get_db, get_etl_db, get_session
from api.errors import ApiError
from api.routes import admin_monitor as am
from etl import backfill_runs as br
from etl import band_catalog as bc
from etl import eda
from etl import regions as rg

router = APIRouter()

SOURCES = {"s1": "S1", "modis": "MODIS", "gpm": "GPM"}
MAX_BACKFILL_DAYS = 366
MAX_EDA_DAYS = 3660


def _src(source: str) -> str:
    code = SOURCES.get(source.lower())
    if code is None:
        raise ApiError(400, "source must be s1, modis or gpm", "INVALID_SOURCE")
    return code


class BackfillRequest(BaseModel):
    date_from: date
    date_to: date

    @model_validator(mode="after")
    def _range(self):
        if self.date_from > self.date_to or (self.date_to - self.date_from).days + 1 > MAX_BACKFILL_DAYS:
            raise ValueError(f"date_from must be before date_to, at most {MAX_BACKFILL_DAYS} days")
        return self


# --- backfill di luar halaman ini --------------------------------------------------
#
# Job Hidromet juga dijalankan scripts/backfill_hydromet.py, scheduler harian,
# atau worker API lain. Semuanya memegang advisory lock "hydromet" (M22), jadi
# kunci itu -- bukan daftar jalan di memori proses ini -- yang menentukan
# apakah backfill sedang berjalan. pg_locks bisa dibaca semua role.

_HYDROMET_LOCKED = text("""
    SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND granted
                   AND database = (SELECT oid FROM pg_database WHERE datname = current_database())
                   AND objid = (hashtext('orbit-u:hydromet')::bigint & 4294967295)::oid)""")


def hydromet_activity(sess: Session) -> dict:
    """{locked, external, current_date, current_started_at, done_last_hour, last_completed_date}."""
    locked = bool(sess.scalar(_HYDROMET_LOCKED))
    hyd = rg.hydromet_dataset(sess)
    out = {"locked": locked, "external": locked and not (br.running("gpm") or br.running("modis")),
           "current_date": None, "current_started_at": None, "done_last_hour": 0, "last_completed_date": None}
    if hyd is None:
        return out
    row = sess.execute(text("""
        SELECT (SELECT date_range_start FROM dataset_jobs WHERE dataset_id = :d AND job_type = 'HYDROMET_DAILY'
                  AND status = 'PROCESSING' ORDER BY started_at DESC NULLS LAST LIMIT 1) AS cur,
               (SELECT max(started_at) FROM dataset_jobs WHERE dataset_id = :d AND job_type = 'HYDROMET_DAILY'
                  AND status = 'PROCESSING') AS cur_at,
               (SELECT count(*) FROM dataset_jobs WHERE dataset_id = :d AND job_type = 'HYDROMET_DAILY'
                  AND status = 'COMPLETED' AND completed_at > now() - interval '1 hour') AS done,
               (SELECT date_range_start FROM dataset_jobs WHERE dataset_id = :d AND job_type = 'HYDROMET_DAILY'
                  AND status = 'COMPLETED' ORDER BY completed_at DESC NULLS LAST LIMIT 1) AS last_done"""),
        {"d": hyd["dataset_id"]}).mappings().one()
    if locked:
        out.update(current_date=row["cur"], current_started_at=row["cur_at"])
    out.update(done_last_hour=row["done"], last_completed_date=row["last_done"])
    return out


# --- ringkasan ----------------------------------------------------------------------

@router.get("/summary", summary="Data status per satellite: counts, coverage, running backfills")
def summary(sess: Session = Depends(get_session)) -> dict:
    s1 = sess.execute(text("""
        SELECT count(*) AS n_total, count(*) FILTER (WHERE is_valid) AS n_valid,
               count(*) FILTER (WHERE NOT is_valid) AS n_invalid,
               min(acquisition_datetime)::date AS first_date, max(acquisition_datetime)::date AS last_date,
               max(created_at) AS last_ingested_at,
               count(DISTINCT (acquisition_datetime AT TIME ZONE 'UTC')::date) AS n_days
        FROM satellite_scenes""")).mappings().one()
    nasa = {r["source"]: r for r in sess.execute(text("""
        SELECT source, count(*) AS n_total, count(*) FILTER (WHERE is_valid) AS n_valid,
               count(*) FILTER (WHERE NOT is_valid) AS n_invalid,
               min(acquisition_date) AS first_date, max(acquisition_date) AS last_date,
               max(created_at) AS last_ingested_at, count(DISTINCT acquisition_date) AS n_days
        FROM nasa_scenes GROUP BY source""")).mappings().all()}
    obs = {r["source_code"]: r for r in sess.execute(text("""
        SELECT s.source_code, count(DISTINCT o.obs_date) AS obs_days, max(o.obs_date) AS last_obs_date
        FROM region_observations o JOIN spectral_bands b USING (band_id) JOIN satellite_sources s USING (source_id)
        GROUP BY s.source_code""")).mappings().all()}
    activity = hydromet_activity(sess)
    items = []
    for key, code in SOURCES.items():
        base = dict(s1) if code == "S1" else dict(nasa.get(code) or {"n_total": 0, "n_valid": 0, "n_invalid": 0,
                                                                     "first_date": None, "last_date": None,
                                                                     "last_ingested_at": None, "n_days": 0})
        o = obs.get({"S1": "SENTINEL1"}.get(code, code)) or {}
        items.append({"key": key, "label": bc.SOURCES[key]["label"], **base,
                      "obs_days": o.get("obs_days", 0), "last_obs_date": o.get("last_obs_date"),
                      "backfill_running": br.running(key) or (key != "s1" and activity["external"])})
    datasets = sess.execute(text("""
        SELECT count(*) FILTER (WHERE deleted_at IS NULL AND NOT is_system) AS n_datasets,
               count(*) FILTER (WHERE status IN ('QUEUED','PREPARING','DOWNLOADING','PROCESSING','CLEANUP')) AS n_active
        FROM datasets""")).mappings().one()
    return {"sources": items, "datasets": dict(datasets), "hydromet": activity,
            "recent_runs": [r.as_dict() for r in br.runs()[:10]]}


# --- daftar & ubah ------------------------------------------------------------------

@router.get("/{source}/items", summary="Scenes (S1) or granules (MODIS/GPM), including deactivated ones")
def items(source: str, sess: Session = Depends(get_session),
          date_from: date | None = None, date_to: date | None = None,
          status: str = Query("all", pattern="^(all|valid|invalid)$"),
          q: str | None = Query(None, max_length=100, description="Product identifier / product name contains"),
          limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)) -> dict:
    code = _src(source)
    where, params = ["true"], {}
    if code == "S1":
        day = "(s.acquisition_datetime AT TIME ZONE 'UTC')::date"
        name_col = "s.product_identifier"
    else:
        day = "s.acquisition_date"
        name_col = "s.product_short_name"
        where.append("s.source = :src")
        params["src"] = code
    if date_from:
        where.append(f"{day} >= :a")
        params["a"] = date_from
    if date_to:
        where.append(f"{day} <= :b")
        params["b"] = date_to
    if status != "all":
        where.append("s.is_valid" if status == "valid" else "NOT s.is_valid")
    if q:
        where.append(f"{name_col} ILIKE :q")
        params["q"] = f"%{q}%"
    cond = " AND ".join(where)
    if code == "S1":
        sql = f"""
            SELECT s.scene_id AS id, s.product_identifier AS name, s.acquisition_datetime,
                   {day} AS acquisition_date, s.orbit_direction::text AS orbit_direction, s.relative_orbit,
                   s.raw_file_size_mb, s.is_available, s.is_valid, s.invalid_reason, s.invalidated_at,
                   (SELECT count(*) FROM data_products p WHERE p.scene_id = s.scene_id) AS n_products,
                   NULL AS run_type, NULL AS tile_id
            FROM satellite_scenes s WHERE {cond}"""
        table = "satellite_scenes s"
    else:
        sql = f"""
            SELECT s.nasa_scene_id AS id, s.product_short_name AS name, NULL::timestamptz AS acquisition_datetime,
                   s.acquisition_date, NULL AS orbit_direction, NULL::smallint AS relative_orbit,
                   NULL::numeric AS raw_file_size_mb, s.is_available, s.is_valid, s.invalid_reason, s.invalidated_at,
                   (SELECT count(*) FROM data_products p WHERE p.nasa_scene_id = s.nasa_scene_id) AS n_products,
                   s.run_type, s.tile_id
            FROM nasa_scenes s WHERE {cond}"""
        table = "nasa_scenes s"
    total = sess.scalar(text(f"SELECT count(*) FROM {table} WHERE {cond}"), params)
    rows = sess.execute(text(sql + " ORDER BY acquisition_date DESC, id DESC LIMIT :limit OFFSET :offset"),
                        {**params, "limit": limit, "offset": offset}).mappings().all()
    return {"source": source.lower(), "items": [{**r, "raw_file_size_mb": None if r["raw_file_size_mb"] is None
                                                 else float(r["raw_file_size_mb"])} for r in rows],
            "total": total, "limit": limit, "offset": offset}


@router.patch("/{source}/items/{item_id}", summary="Deactivate (soft delete, reason required) or restore an item")
def update_item(source: str, item_id: int, req: am.SceneValidityUpdate, request: Request,
                sess: Session = Depends(get_session), principal: Principal = Depends(current_principal)) -> dict:
    code = _src(source)
    out = am.set_scene_validity(code, item_id, req, sess, principal)
    log_activity(sess, "SCENE_UPDATE", user_id=principal.user_id, target_type=am._SCENE_TABLES[code][0],
                 target_id=item_id, detail={"source": code, "is_valid": req.is_valid, "reason": req.reason},
                 **request_meta(request))
    return out


@router.post("/{source}/items/{item_id}/reprocess", status_code=202, summary="Reprocess one scene or granule")
def reprocess_item(source: str, item_id: int, sess: Session = Depends(get_session), etl=Depends(get_etl_db)) -> dict:
    return am.reprocess_scene(_src(source), item_id, sess, etl)


# --- backfill -----------------------------------------------------------------------

@router.post("/{source}/backfill", status_code=202, summary="Backfill a date range for one satellite")
def start_backfill(source: str, req: BackfillRequest, request: Request, sess: Session = Depends(get_session),
                   db=Depends(get_db), etl=Depends(get_etl_db),
                   principal: Principal = Depends(current_principal)) -> dict:
    code = _src(source)
    key = source.lower()
    hyd = rg.hydromet_dataset(sess)
    if hyd is None:
        raise ApiError(409, "System dataset HYDROMET_AOI is missing; set the AOI first", "HYDROMET_NOT_READY")
    meta = request_meta(request)
    if code == "S1":
        from etl.dataset_manager import DatasetManager
        try:
            result = DatasetManager(db, runner_db=etl).create_dataset(
                created_by=principal.user_id, region_id=hyd["region_id"], date_start=req.date_from,
                date_end=req.date_to, name=f"Backfill Sentinel-1 {req.date_from} s.d. {req.date_to}",
                sources={"sentinel1": {"processing": ["PROCESSED"]}}, generate_preview=True,
                description="Dibuat dari halaman Data > Sentinel-1 (backfill).")
        except (ValueError, RuntimeError) as exc:
            raise ApiError(400, str(exc), "BAD_REQUEST")
        log_activity(sess, "BACKFILL_START", user_id=principal.user_id, target_type="datasets",
                     target_id=result.get("dataset_id"), detail={"source": code, "date_from": str(req.date_from),
                                                                   "date_to": str(req.date_to)}, **meta)
        return {"accepted": True, "source": key, "kind": "DATASET", "dataset_id": result.get("dataset_id"),
                "dataset": result}
    if br.running("gpm") or br.running("modis") or sess.scalar(_HYDROMET_LOCKED):
        # Kunci dipegang skrip/scheduler/worker lain: jalan baru akan langsung
        # SKIPPED, jadi tolak di sini dengan pesan yang jelas.
        raise ApiError(409, "A Hydromet backfill (GPM/MODIS) is already running", "BACKFILL_RUNNING")
    from etl import hydromet_job as hj

    def work(echo):
        if code == "GPM":
            return hj.backfill(etl, req.date_from, req.date_to, modis=False, echo=echo)
        return hj.backfill(etl, req.date_from, req.date_to, modis=True, echo=echo,
                           pending_fn=hj.modis_missing_dates)

    run = br.start(key, req.date_from, req.date_to, principal.user_id, work)
    log_activity(sess, "BACKFILL_START", user_id=principal.user_id, target_type="dataset_jobs", target_id=None,
                 detail={"source": code, "run_id": run.run_id, "date_from": str(req.date_from),
                         "date_to": str(req.date_to)}, **meta)
    return {"accepted": True, "source": key, "kind": "HYDROMET", "run": run.as_dict()}


@router.get("/{source}/backfill", summary="Running/recent backfills and the per-day job history")
def backfill_status(source: str, sess: Session = Depends(get_session),
                    days: int = Query(60, ge=1, le=366)) -> dict:
    code = _src(source)
    key = source.lower()
    out = {"source": key, "runs": [r.as_dict() for r in br.runs(key)]}
    if code == "S1":
        out["datasets"] = [dict(r) for r in sess.execute(text("""
            SELECT d.dataset_id, d.name, d.status, d.date_start, d.date_end, d.total_scenes,
                   d.completed_scenes, d.failed_scenes, d.created_at
            FROM datasets d WHERE d.name LIKE 'Backfill Sentinel-1 %' AND d.deleted_at IS NULL
            ORDER BY d.created_at DESC LIMIT 20""")).mappings().all()]
        return out
    hyd = rg.hydromet_dataset(sess)
    if hyd is None:
        out["days"] = []
        return out
    activity = hydromet_activity(sess)
    out["hydromet"] = activity
    band_filter = "s.source_code = 'MODIS'" if code == "MODIS" else "s.source_code = 'GPM'"
    rows = [dict(r) for r in sess.execute(text(f"""
        SELECT j.date_range_start AS date, j.status, j.processed_count, j.failed_count, j.started_at, j.completed_at,
               (SELECT count(*) FROM region_observations o JOIN spectral_bands b USING (band_id)
                JOIN satellite_sources s USING (source_id)
                WHERE o.obs_date = j.date_range_start AND {band_filter}) AS n_observations
        FROM dataset_jobs j
        WHERE j.dataset_id = :d AND j.job_type = 'HYDROMET_DAILY'
          AND j.job_id = (SELECT max(j2.job_id) FROM dataset_jobs j2 WHERE j2.dataset_id = j.dataset_id
                           AND j2.job_type = j.job_type AND j2.date_range_start = j.date_range_start)
        ORDER BY j.date_range_start DESC LIMIT :n"""), {"d": hyd["dataset_id"], "n": days}).mappings().all()]
    # PROCESSING yang bukan tanggal yang sedang dikerjakan = jalan yang
    # terputus (proses mati/dihentikan). Tanggal itu dikerjakan ulang oleh
    # backfill berikutnya (pending_dates hanya melewati COMPLETED).
    for r in rows:
        r["stale"] = r["status"] == "PROCESSING" and not (
            activity["locked"] and r["date"] == activity["current_date"])
    out["days"] = rows
    out["stale_dates"] = [str(d) for d in sess.scalars(text("""
        SELECT date_range_start FROM dataset_jobs j WHERE dataset_id = :d AND job_type = 'HYDROMET_DAILY'
          AND status = 'PROCESSING' AND date_range_start IS DISTINCT FROM :cur
          AND job_id = (SELECT max(job_id) FROM dataset_jobs j2 WHERE j2.dataset_id = j.dataset_id
                        AND j2.job_type = j.job_type AND j2.date_range_start = j.date_range_start)
        ORDER BY 1"""), {"d": hyd["dataset_id"], "cur": activity["current_date"] if activity["locked"] else None}).all()]
    return out


@router.get("/backfill/runs/{run_id}", summary="Progress and log lines of one backfill run")
def backfill_run(run_id: int, since: int = Query(0, ge=0, description="Return lines after this index")) -> dict:
    run = br.get(run_id)
    if run is None:
        raise ApiError(404, f"Backfill run {run_id} not found (runs are kept until the server restarts)",
                       "NOT_FOUND")
    return run.as_dict(with_lines=True, since=since)


# --- EDA ----------------------------------------------------------------------------

@router.get("/eda", summary="Exploratory data analysis for one satellite and date range")
def eda_view(sess: Session = Depends(get_session), source: str = Query(..., pattern="^(s1|modis|gpm)$"),
             date_from: date = Query(...), date_to: date = Query(...)) -> dict:
    if date_from > date_to or (date_to - date_from).days > MAX_EDA_DAYS:
        raise ApiError(400, f"date_from must be before date_to, at most {MAX_EDA_DAYS} days", "INVALID_DATE_RANGE")
    n_days = (date_to - date_from).days + 1
    src_code = bc.SOURCES[source]["source_code"]
    out = {"source": source, "date_from": date_from, "date_to": date_to, "n_days": n_days}
    if source == "s1":
        return {**out, **_eda_s1(sess, date_from, date_to)}

    regions = sess.execute(text("SELECT count(*) FROM administrative_regions WHERE in_aoi")).scalar() or 0
    rows = sess.execute(text("""
        SELECT o.obs_date, o.region_id, b.band_code, o.value, o.valid_fraction, o.run_type
        FROM region_observations o JOIN spectral_bands b USING (band_id) JOIN satellite_sources s USING (source_id)
        WHERE s.source_code = :c AND o.obs_date BETWEEN :f AND :t"""),
        {"c": src_code, "f": date_from, "t": date_to}).all()
    bands = [r["band_code"] for r in sess.execute(text("""
        SELECT b.band_code FROM spectral_bands b JOIN satellite_sources s USING (source_id)
        WHERE s.source_code = :c AND b.band_code = ANY(:allowed) ORDER BY b.band_id"""),
        {"c": src_code, "allowed": list(bc.REGION_BANDS)}).mappings().all()]
    by_band = defaultdict(list)
    table: dict[tuple, dict] = defaultdict(dict)
    vf = []
    runs = defaultdict(int)
    for d, rid, band, v, valid_fraction, run_type in rows:
        val = None if v is None else float(v)
        by_band[band].append(val)
        table[(d, rid)][band] = val
        vf.append(float(valid_fraction))
        if run_type:
            runs[run_type] += 1
    expected = n_days * regions
    return {**out, "unit_of_analysis": "kecamatan × hari", "n_regions": regions, "n_rows": len(rows),
            "variables": [{"band_code": b, "unit": None, "color": bc.color(b), **eda.describe(by_band[b], expected)}
                          for b in bands],
            "correlation": eda.correlation(table, bands),
            "completeness": eda.daily_completeness([(d, band, v) for d, _r, band, v, _vf, _rt in rows],
                                                   bands, date_from, date_to, regions),
            "valid_fraction": eda.describe(vf),
            "run_types": dict(runs)}


def _eda_s1(sess: Session, date_from: date, date_to: date) -> dict:
    """S1: tidak dihitung per kecamatan. Unit analisis = scene × band dari
    quality_metrics (statistik raster), ditambah metadata akuisisi."""
    q = sess.execute(text("""
        SELECT (s.acquisition_datetime AT TIME ZONE 'UTC')::date AS d, s.scene_id, m.band_name,
               m.backscatter_mean_db, m.backscatter_std_db, m.nodata_percent, m.speckle_index, m.quality_score
        FROM quality_metrics m JOIN satellite_scenes s USING (scene_id)
        WHERE (s.acquisition_datetime AT TIME ZONE 'UTC')::date BETWEEN :f AND :t"""),
        {"f": date_from, "t": date_to}).all()
    scenes = sess.execute(text("""
        SELECT orbit_direction::text AS orbit_direction, relative_orbit, incidence_angle_near, incidence_angle_far,
               raw_file_size_mb, is_valid, (acquisition_datetime AT TIME ZONE 'UTC')::date AS d
        FROM satellite_scenes
        WHERE (acquisition_datetime AT TIME ZONE 'UTC')::date BETWEEN :f AND :t"""),
        {"f": date_from, "t": date_to}).mappings().all()
    variables = {}
    table: dict[tuple, dict] = defaultdict(dict)
    for d, sid, band, mean, std, nodata, speckle, score in q:
        for name, v in ((f"{band}_mean_db", mean), (f"{band}_std_db", std), (f"{band}_nodata_pct", nodata),
                        (f"{band}_speckle", speckle), (f"{band}_quality", score)):
            val = None if v is None else float(v)
            variables.setdefault(name, []).append(val)
            table[(sid,)][name] = val
    names = sorted(variables)
    orbit = defaultdict(int)
    for s in scenes:
        orbit[f"{s['orbit_direction']} {s['relative_orbit'] or '?'}"] += 1
    acq_days = sorted({s["d"] for s in scenes})
    gaps = [(b - a).days for a, b in zip(acq_days, acq_days[1:])]
    return {"unit_of_analysis": "scene × band (quality_metrics)", "n_rows": len(q), "n_scenes": len(scenes),
            "n_invalid": sum(1 for s in scenes if not s["is_valid"]),
            "variables": [{"band_code": n, "unit": None, "color": bc.color(n.split("_")[0]), **eda.describe(variables[n])}
                          for n in names],
            "correlation": eda.correlation(table, names),
            "orbits": dict(orbit),
            "revisit_gap_days": eda.describe([float(g) for g in gaps]),
            "file_size_mb": eda.describe([None if s["raw_file_size_mb"] is None else float(s["raw_file_size_mb"])
                                          for s in scenes]),
            "acquisition_dates": [d.isoformat() for d in acq_days]}
