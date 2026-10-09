# etl/hydromet_job.py
"""Job Hidromet Harian (PIPELINE.md §3): GPM + MODIS AOI -> region_observations -> alert_events.

Satu tanggal = satu hari UTC = satu baris ``dataset_jobs`` (``HYDROMET_DAILY``)
pada dataset sistem ``HYDROMET_AOI``. Urutan tahap:

    1  GPM_DOWNLOAD + ACCUMULATE_RAIN   COG 24h/72h/7d/30d   (fallback F -> L -> E)
    2  HYDROMET_AGGREGATE (GPM)         RAIN_* per kecamatan
    3  ALERT_CHECK                      alert_events
    4  MODIS + HYDROMET_AGGREGATE        FLOOD/NDVI/NDWI per kecamatan (tidak fatal)

GPM lebih dulu karena alert hanya bergantung pada GPM. Bila granule hari itu
belum terbit di run mana pun, tanggalnya ``WAITING_UPSTREAM`` dan dicoba lagi
pada jadwal berikutnya sampai ``app_settings.hydromet.waiting_max_days``,
setelah itu ``FAILED`` (§8).

Resume: tanggal dengan job ``COMPLETED`` dilewati (``pending_dates``), jadi
backfill yang dibunuh di tengah cukup dijalankan ulang. Semua penulisan DB
idempoten (upsert / ON CONFLICT), dan COG yang sudah ada dipakai ulang oleh
module8/module7.

Pengambil input (``Fetchers``) bisa diganti: tes memakai raster sintetis
tanpa jaringan.
"""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import text

from etl import alert_engine, hydromet_aggregate as ha, regions as rg
from etl.settings import get_setting

logger = logging.getLogger(__name__)

JOB_TYPE = "HYDROMET_DAILY"
GPM_BANDS = {"24h": "RAIN_24H", "72h": "RAIN_72H", "7d": "RAIN_7D", "30d": "RAIN_30D"}
MODIS_BANDS = ("FLOOD", "NDVI", "NDWI")
# Late -> Final: Final IMERG terbit ±3,5 bulan setelah hari H, jadi tanggal
# 4–5 bulan terakhir yang masih L/E diperiksa (PIPELINE §3.4).
FINAL_REFRESH_DAYS = 153
# Granule mentah dataset sistem disimpan 45 hari (PIPELINE §9): jendela GPM
# 30 hari + lookback komposit MOD09A1 32 hari (+ periode 8 hari) masih muat.
GRANULE_RETENTION_DAYS = 45


@dataclass
class Layer:
    """Satu COG siap diagregasi."""
    band_code: str
    path: Path
    run_type: str | None = None
    product_id: int | None = None


@dataclass
class DayResult:
    obs_date: date
    status: str                      # COMPLETED | WAITING_UPSTREAM | FAILED | SKIPPED
    job_id: int | None = None
    gpm_run: str | None = None
    observations: int = 0
    alerts: list[int] = field(default_factory=list)
    modis_bands: list[str] = field(default_factory=list)
    message: str = ""


class UpstreamNotReady(Exception):
    """Granule GPM hari itu belum terbit di run mana pun."""


@dataclass
class Context:
    db: object
    dataset_id: int
    dataset_name: str
    region_id: int
    bbox: tuple[float, float, float, float]


# Pengambil default (jaringan, module8/module7 lewat module9) ------------------

def _product_id(db, path: str | Path) -> int | None:
    with db.session() as sess:
        return sess.scalar(text("""
            SELECT product_id FROM data_products WHERE file_path = :p AND is_latest
            ORDER BY product_id DESC LIMIT 1"""), {"p": str(path)})


def default_gpm_fetch(ctx: Context, obs_date: date, rebuild_non_final: bool) -> list[Layer]:
    from etl import module8_gpm_download as m8
    from etl.module9_fusion import ensure_gpm_inputs_for_date

    try:
        produced = ensure_gpm_inputs_for_date(
            ctx.db, ctx.dataset_id, ctx.dataset_name, ctx.region_id, ctx.bbox, obs_date,
            windows=m8.HYDROMET_WINDOWS, rebuild_non_final=rebuild_non_final, raise_errors=True,
        )
    except m8.GranuleNotPublished as exc:
        raise UpstreamNotReady(str(exc)) from exc
    dk = obs_date.strftime("%Y%m%d")
    by_name = {}
    for tier, paths in produced.items():
        for p in paths:
            by_name.setdefault(Path(p).name, {})[tier] = Path(p)
    layers = []
    for window, band in GPM_BANDS.items():
        copies = by_name.get(m8.band_filename(window, dk))
        if not copies:
            continue
        path = copies.get("COG") or next(iter(copies.values()))
        runs = m8.file_runs(path) or next((m8.file_runs(p) for p in copies.values() if m8.file_runs(p)), [])
        layers.append(Layer(band, path, ha.worst_run(runs), _product_id(ctx.db, path)))
    return layers


def default_modis_fetch(ctx: Context, obs_date: date) -> list[Layer]:
    from etl import module7_modis_download as m7
    from etl.module9_fusion import ensure_modis_inputs_for_date

    produced = ensure_modis_inputs_for_date(
        ctx.db, ctx.dataset_id, ctx.dataset_name, ctx.region_id, ctx.bbox, obs_date)
    dk = obs_date.strftime("%Y%m%d")
    all_paths = [Path(p) for paths in produced.values() for p in paths]
    layers = []
    for band in MODIS_BANDS:
        name = m7.band_filename(band, dk)
        matches = [p for p in all_paths if p.name == name]
        if not matches:
            continue
        cog = next((p for p in matches if "cog" in {part.lower() for part in p.parts}), matches[0])
        layers.append(Layer(band, cog, None, _product_id(ctx.db, cog)))
    return layers


@dataclass
class Fetchers:
    gpm: Callable[[Context, date, bool], list[Layer]] = default_gpm_fetch
    modis: Callable[[Context, date], list[Layer]] | None = default_modis_fetch


# Utilitas ---------------------------------------------------------------------

def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def target_date() -> date:
    """Tanggal operasi harian: kemarin (UTC), karena IMERG Late hari H baru
    tersedia ±14 jam setelah hari H berakhir."""
    return utc_today() - timedelta(days=1)


def context(db) -> Context:
    with db.session() as sess:
        ds = rg.hydromet_dataset(sess)
    if ds is None:
        raise RuntimeError("system dataset HYDROMET_AOI not found; run scripts/load_regions.py --aoi ... first")
    return Context(db, ds["dataset_id"], ds["name"], ds["region_id"], ds["bbox"])


def _job_row(db, ctx: Context, obs_date: date) -> int:
    """Baris dataset_jobs tanggal ini: dipakai ulang bila belum COMPLETED
    (percobaan berikutnya untuk WAITING_UPSTREAM/FAILED/terputus)."""
    with db.session() as sess:
        job_id = sess.scalar(text("""
            SELECT job_id FROM dataset_jobs
            WHERE dataset_id = :d AND job_type = :t AND date_range_start = :day
            ORDER BY job_id DESC LIMIT 1"""), {"d": ctx.dataset_id, "t": JOB_TYPE, "day": obs_date})
        if job_id is None:
            return sess.scalar(text("""
                INSERT INTO dataset_jobs (dataset_id, job_type, status, date_range_start, date_range_end,
                                          total_scenes, started_at)
                VALUES (:d, :t, 'PROCESSING', :day, :day, 1, now()) RETURNING job_id"""),
                {"d": ctx.dataset_id, "t": JOB_TYPE, "day": obs_date})
        sess.execute(text("""
            UPDATE dataset_jobs SET status = 'PROCESSING', started_at = now(), completed_at = NULL,
                   resume_count = resume_count + 1, resumed_at = now()
            WHERE job_id = :j"""), {"j": job_id})
        return job_id


def _finish_job(db, job_id: int, status: str, processed: int = 0, failed: int = 0) -> None:
    with db.session() as sess:
        sess.execute(text("""
            UPDATE dataset_jobs SET status = :s, processed_count = :p, failed_count = :f,
                   completed_at = CASE WHEN :s IN ('COMPLETED', 'FAILED') THEN now() END
            WHERE job_id = :j"""), {"s": status, "p": processed, "f": failed, "j": job_id})


def _stage_job(db, stage: str, status: str, parameters: dict, error: str | None = None) -> None:
    """Catat satu tahap di processing_jobs (tanpa jangkar, seperti FUSION)."""
    with db.session() as sess:
        sess.execute(text("""
            INSERT INTO processing_jobs (stage_id, status, started_at, completed_at, worker_hostname,
                                         error_code, error_message, parameters_json)
            SELECT stage_id, CAST(:st AS job_status_enum), now(), now(), :host,
                   CASE WHEN :err IS NULL THEN NULL ELSE :st END, :err, CAST(:params AS jsonb)
            FROM processing_stages WHERE stage_name = :stage"""),
            {"st": status, "host": socket.gethostname(), "err": error, "stage": stage,
             "params": _json(parameters)})


def _json(obj) -> str:
    import json
    return json.dumps(obj, default=str)


def _record_gpm_run(db, obs_date: date, run: str | None) -> None:
    """nasa_scenes.run_type granule GPM tanggal itu (dipakai v_kelengkapan_data)."""
    if run is None:
        return
    from etl.constants import GPM_SOURCE
    with db.session() as sess:
        sess.execute(text("""
            UPDATE nasa_scenes SET run_type = :r
            WHERE source = :s AND acquisition_date = :d AND run_type IS DISTINCT FROM :r"""),
            {"r": run, "s": GPM_SOURCE, "d": obs_date})


def prune_granule_cache(ctx: "Context", obs_date: date, keep_days: int = GRANULE_RETENTION_DAYS) -> dict:
    """Hapus granule GPM/MODIS mentah di _granule_cache yang tanggalnya lebih
    tua dari ``obs_date - keep_days``. Produk turunan (COG) tidak disentuh;
    granule yang dihapus bisa diunduh ulang dari URL resminya."""
    from etl import folder_manager as fm
    from etl.live_monitor import _granule_date

    cutoff = obs_date - timedelta(days=keep_days)
    removed, freed = 0, 0
    for source in ("gpm", "modis"):
        cache = fm.get_granule_cache_dir(ctx.dataset_id, ctx.dataset_name, source)
        if not cache.is_dir():
            continue
        for p in cache.iterdir():
            d = _granule_date(p.name) if p.is_file() else None
            if d is not None and d < cutoff:
                try:
                    size = p.stat().st_size
                    p.unlink()
                    removed += 1
                    freed += size
                except OSError:
                    logger.warning("[HYDROMET] gagal menghapus granule lama %s", p)
    if removed:
        logger.info("[HYDROMET] cache granule < %s: %d berkas dihapus (%.0f MB)", cutoff, removed, freed / 2 ** 20)
    return {"removed": removed, "freed_bytes": freed}


# Inti -------------------------------------------------------------------------

def run_day(db, obs_date: date, *, rebuild_non_final: bool = False,
            fetchers: Fetchers | None = None, ctx: Context | None = None) -> DayResult:
    """Kerjakan satu tanggal UTC. Tidak pernah melempar untuk kegagalan
    sumber: statusnya dikembalikan dan dicatat di dataset_jobs."""
    fetchers = fetchers or Fetchers()
    ctx = ctx or context(db)
    with db.session() as sess:
        regions = rg.aoi_regions(sess)
        min_vf = float(get_setting(sess, "hydromet.min_valid_fraction"))
        max_wait = int(get_setting(sess, "hydromet.waiting_max_days"))
    if not regions:
        raise RuntimeError("no kecamatan is in_aoi")
    ha.clear_cache()
    job_id = _job_row(db, ctx, obs_date)
    result = DayResult(obs_date, "FAILED", job_id=job_id)

    # 1–2: GPM ---------------------------------------------------------------
    try:
        gpm_layers = fetchers.gpm(ctx, obs_date, rebuild_non_final)
    except UpstreamNotReady as exc:
        late = (utc_today() - obs_date).days > max_wait
        result.status = "FAILED" if late else "WAITING_UPSTREAM"
        result.message = str(exc)
        _stage_job(db, "DOWNLOAD", result.status, {"source": "GPM", "date": obs_date, "job_id": job_id},
                   error=str(exc)[:2000])
        _finish_job(db, job_id, result.status, failed=1)
        logger.warning("[HYDROMET] %s %s: %s", obs_date, result.status, exc)
        return result
    except Exception as exc:
        logger.exception("[HYDROMET] %s: GPM gagal", obs_date)
        result.message = f"GPM: {exc}"
        _stage_job(db, "DOWNLOAD", "FAILED", {"source": "GPM", "date": obs_date, "job_id": job_id},
                   error=str(exc)[:2000])
        _finish_job(db, job_id, "FAILED", failed=1)
        return result
    if not gpm_layers:
        result.message = "GPM produced no rainfall layer"
        _finish_job(db, job_id, "FAILED", failed=1)
        return result

    gpm_run = next((l.run_type for l in gpm_layers if l.band_code == "RAIN_24H"), None)
    result.gpm_run = gpm_run
    with db.session() as sess:
        for layer in gpm_layers:
            res = ha.aggregate_raster(layer.path, regions, "MEAN", min_vf)
            result.observations += ha.upsert_observations(
                sess, layer.band_code, obs_date, res, run_type=layer.run_type,
                product_id=layer.product_id, job_id=job_id)
    _record_gpm_run(db, obs_date, gpm_run)
    _stage_job(db, "HYDROMET_AGGREGATE", "SUCCESS",
               {**ha.job_parameters(gpm_run, len(regions), min_vf), "source": "GPM", "date": obs_date,
                "bands": [l.band_code for l in gpm_layers], "job_id": job_id})

    # 3: alert ---------------------------------------------------------------
    with db.session() as sess:
        result.alerts = alert_engine.check_alerts(sess, obs_date)
    _stage_job(db, "ALERT_CHECK", "SUCCESS", {"date": obs_date, "new_alerts": len(result.alerts),
                                               "job_id": job_id})

    # 4: MODIS (tidak fatal, PIPELINE §1) --------------------------------------
    modis_failed = 0
    if fetchers.modis is not None:
        try:
            modis_layers = fetchers.modis(ctx, obs_date)
            with db.session() as sess:
                bands = ha.band_ids(sess)
                for layer in modis_layers:
                    res = ha.aggregate_raster(layer.path, regions, bands[layer.band_code][1], min_vf)
                    result.observations += ha.upsert_observations(
                        sess, layer.band_code, obs_date, res, product_id=layer.product_id, job_id=job_id)
                    result.modis_bands.append(layer.band_code)
            _stage_job(db, "HYDROMET_AGGREGATE", "SUCCESS",
                       {**ha.job_parameters(None, len(regions), min_vf), "source": "MODIS",
                        "date": obs_date, "bands": result.modis_bands, "job_id": job_id})
        except Exception as exc:
            modis_failed = 1
            logger.exception("[HYDROMET] %s: MODIS gagal (tidak fatal)", obs_date)
            _stage_job(db, "HYDROMET_AGGREGATE", "FAILED", {"source": "MODIS", "date": obs_date,
                                                             "job_id": job_id}, error=str(exc)[:2000])

    try:
        prune_granule_cache(ctx, obs_date)
    except Exception:
        logger.exception("[HYDROMET] pembersihan cache granule gagal (tidak fatal)")

    result.status = "COMPLETED"
    result.message = (f"{result.observations} observations, {len(result.alerts)} new alerts, GPM run {gpm_run}"
                      + ("" if not modis_failed else ", MODIS failed"))
    _finish_job(db, job_id, "COMPLETED", processed=result.observations, failed=modis_failed)
    logger.info("[HYDROMET] %s COMPLETED: %s", obs_date, result.message)
    return result


def pending_dates(db, date_from: date, date_to: date) -> list[date]:
    """Tanggal di [date_from, date_to] yang belum COMPLETED (urut naik)."""
    ctx = context(db)
    with db.session() as sess:
        done = set(sess.scalars(text("""
            SELECT date_range_start FROM dataset_jobs
            WHERE dataset_id = :d AND job_type = :t AND status = 'COMPLETED'
              AND date_range_start BETWEEN :a AND :b"""),
            {"d": ctx.dataset_id, "t": JOB_TYPE, "a": date_from, "b": date_to}).all())
    days = (date_to - date_from).days + 1
    return [d for d in (date_from + timedelta(days=i) for i in range(days)) if d not in done]


def modis_missing_dates(db, date_from: date, date_to: date) -> list[date]:
    """Tanggal di [date_from, date_to] tanpa satu pun observasi MODIS (FLOOD,
    NDVI, NDWI), termasuk yang Job Hidromet-nya sudah COMPLETED karena GPM
    selesai tetapi MODIS gagal/terlewat. Dipakai backfill MODIS halaman Data
    (M56): ``pending_dates`` saja akan melewati tanggal-tanggal itu."""
    with db.session() as sess:
        have = set(sess.scalars(text("""
            SELECT DISTINCT o.obs_date FROM region_observations o JOIN spectral_bands b USING (band_id)
            JOIN satellite_sources s USING (source_id)
            WHERE s.source_code = 'MODIS' AND o.obs_date BETWEEN :a AND :b"""),
            {"a": date_from, "b": date_to}).all())
    days = (date_to - date_from).days + 1
    return [d for d in (date_from + timedelta(days=i) for i in range(days)) if d not in have]


def waiting_dates(db) -> list[date]:
    """Tanggal WAITING_UPSTREAM yang masih boleh dicoba lagi."""
    ctx = context(db)
    with db.session() as sess:
        return list(sess.scalars(text("""
            SELECT date_range_start FROM dataset_jobs
            WHERE dataset_id = :d AND job_type = :t AND status = 'WAITING_UPSTREAM'
            ORDER BY date_range_start"""), {"d": ctx.dataset_id, "t": JOB_TYPE}).all())


def run_daily(db, fetchers: Fetchers | None = None) -> list[DayResult]:
    """Job harian 02:00 WIB: tanggal yang masih WAITING_UPSTREAM, lalu kemarin
    (UTC), lalu buang raster yang keluar dari jendela raster (M58)."""
    from etl.raster_retention import prune_main_rasters

    targets = sorted(set(waiting_dates(db)) | {target_date()})
    ctx = context(db)
    results = [run_day(db, d, fetchers=fetchers, ctx=ctx) for d in targets]
    try:
        prune_main_rasters(db)
    except Exception:
        logger.exception("[HYDROMET] pembersihan raster > jendela gagal (tidak fatal)")
    return results


def non_final_dates(db, days: int = FINAL_REFRESH_DAYS) -> list[date]:
    """Tanggal (dalam ``days`` hari terakhir) yang RAIN_24H-nya belum Final."""
    with db.session() as sess:
        return list(sess.scalars(text("""
            SELECT DISTINCT o.obs_date FROM region_observations o
            JOIN spectral_bands b ON b.band_id = o.band_id AND b.band_code = 'RAIN_24H'
            WHERE o.obs_date >= current_date - CAST(:n AS int)
              AND (o.run_type IS NULL OR o.run_type <> 'F')
            ORDER BY o.obs_date"""), {"n": days}).all())


def final_published(ctx: Context, obs_date: date) -> bool:
    """True bila IMERG Final hari itu sudah ada di GES DISC (listing bulanan,
    di-cache module8) -- supaya Late tidak diunduh ulang sia-sia."""
    from etl import folder_manager as fm
    from etl import module8_gpm_download as m8

    raw_dir = fm.get_granule_cache_dir(ctx.dataset_id, ctx.dataset_name, "gpm")
    when = datetime(obs_date.year, obs_date.month, obs_date.day, tzinfo=timezone.utc)
    try:
        return m8._resolve_daily_granule(when, "F", raw_dir) is not None
    except Exception:
        logger.exception("[HYDROMET] gagal memeriksa Final %s", obs_date)
        return False


def refresh_late_to_final(db, fetchers: Fetchers | None = None,
                          is_final_published: Callable[[Context, date], bool] | None = None) -> list[DayResult]:
    """Job mingguan Minggu 04:00 WIB (§3.4): proses ulang tanggal non-Final
    yang Final-nya sudah terbit. Alert lama tidak disentuh."""
    ctx = context(db)
    check = is_final_published or final_published
    out = []
    for d in non_final_dates(db):
        if check(ctx, d):
            out.append(run_day(db, d, rebuild_non_final=True, fetchers=fetchers, ctx=ctx))
    return out


def backfill(db, date_from: date, date_to: date, *, modis: bool = True, fetchers: Fetchers | None = None,
             dry_run: bool = False, max_consecutive_failures: int = 5, echo=print,
             pending_fn=None) -> dict:
    """Backfill berurutan dan resume-aware di bawah advisory lock ``hydromet``
    (scripts/backfill_hydromet.py, POST /admin/ingest). Mengembalikan ringkasan.

    Berhenti lebih awal setelah `max_consecutive_failures` hari FAILED berurutan
    (0 = jangan pernah berhenti). Gangguan jaringan panjang membuat setiap hari
    gagal di tahap download, dan menyapu ratusan tanggal dalam keadaan itu hanya
    membuang waktu tanpa menghasilkan satu baris pun -- backfill 2026-10-05
    menggagalkan hari demi hari selama outage ISP sampai dihentikan manual.
    Tanggal yang belum COMPLETED tidak hilang: jalankan ulang perintah yang sama
    setelah jaringan pulih. WAITING_UPSTREAM tidak dihitung sebagai kegagalan --
    itu granule yang memang belum dipublikasikan, bukan tanda jaringan rusak."""
    import time

    from etl.advisory_lock import advisory_lock

    summary = {"COMPLETED": 0, "WAITING_UPSTREAM": 0, "FAILED": 0, "skipped_done": 0, "locked": False}
    with advisory_lock(db, "hydromet") as got:
        if not got:
            summary["locked"] = True
            echo("[SKIP] another worker holds the 'hydromet' lock (scheduler or another backfill)")
            return summary
        # pending_fn: tanggal yang dikerjakan; default yang belum COMPLETED.
        # Backfill MODIS memakai modis_missing_dates.
        pending = (pending_fn or pending_dates)(db, date_from, date_to)
        total = (date_to - date_from).days + 1
        summary["skipped_done"] = total - len(pending)
        echo(f"[INFO] {total} days in range, {summary['skipped_done']} already done, {len(pending)} to do")
        if dry_run:
            for d in pending:
                echo(f"  {d}")
            return summary
        if fetchers is None:
            fetchers = Fetchers() if modis else Fetchers(modis=None)
        ctx = context(db)
        consecutive_failed = 0
        for i, d in enumerate(pending, 1):
            t0 = time.monotonic()
            res = run_day(db, d, fetchers=fetchers, ctx=ctx)
            summary[res.status] = summary.get(res.status, 0) + 1
            echo(f"[{i}/{len(pending)}] {d} {res.status} ({time.monotonic() - t0:.0f}s) {res.message}")
            if res.status == "FAILED":
                consecutive_failed += 1
            else:
                consecutive_failed = 0
            if max_consecutive_failures and consecutive_failed >= max_consecutive_failures:
                summary["aborted_after"] = str(d)
                remaining = len(pending) - i
                echo(f"[ABORT] {consecutive_failed} hari FAILED berurutan "
                     f"(terakhir {d}); {remaining} tanggal belum dikerjakan. "
                     "Biasanya jaringan/kredensial, bukan data. Perbaiki lalu "
                     "jalankan ulang perintah yang sama -- tanggal COMPLETED dilewati.")
                logger.error("[HYDROMET] backfill dihentikan: %d FAILED berurutan, "
                             "sisa %d tanggal", consecutive_failed, remaining)
                break
    if not summary["locked"] and not dry_run and summary["COMPLETED"]:
        from etl import forecast_store
        forecast_store.refresh_quietly(db)
    return summary
