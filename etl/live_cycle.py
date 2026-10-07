# etl/live_cycle.py
"""Siklus otomatis satu Daerah Live (LIVE_MONITORING.md 3.3).

    1. cek scene Sentinel-1 baru (discover_scenes)
    2. unduh + proses S1/MODIS/GPM lewat run_dataset_job (pipeline biasa)
    3. per scene: metrik -> 8 preview -> peta perubahan air (preview ke-9,
       PIPELINE §4.1) -> kalimat kondisi
    4. hitung ulang forecast
    5. retensi: hapus scene paling lama yang melebihi batas
    6. semua langkah dicatat ke live_events

Backfill awal adalah siklus yang sama: selama scene tersimpan < retensi,
discovery melihat mundur cukup jauh untuk mengisi kekurangannya.

Kegagalan satu sumber tidak menggagalkan scene: MODIS/GPM yang berkasnya tidak
ada ditandai FAILED di source_status, scene tetap PARTIAL (tampil), dan tiap
siklus berikutnya mencoba ulang sumber itu (retry_failed_sources).
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from shapely import wkt as shapely_wkt
from sqlalchemy import select

from etl import download_guard as dg
from etl import folder_manager as fm
from etl.database_client import Dataset, DatasetJob, LiveArea, LiveScene
from etl.job_lock import LOCK_DIRNAME as JOB_LOCK_DIRNAME
from etl.job_lock import JobLock
from etl.live_monitor import (
    _CYCLE_LOCK,
    BACKFILL_MARGIN_DAYS,
    MAX_LOOKBACK_DAYS,
    S1_REVISIT_DAYS,
    LiveMonitor,
    _jsonable,
    _LiveFiles,
)

logger = logging.getLogger(__name__)

# Scene yang S1-nya gagal diproses dicoba ulang sampai sekian kali (siklus
# berbeda), lalu dibiarkan FAILED -- tetap di log, tidak tampil di kartu.
MAX_S1_ATTEMPTS = 3
# Jendela discovery minimum di siklus rutin: menangkap scene yang terbit
# terlambat di katalog Copernicus.
ROUTINE_LOOKBACK_DAYS = 10
# Peta perubahan air dihitung di grid preview yang diperhalus WC_REFINE kali:
# luas km2 dari piksel 768-an terlalu kasar, sedangkan PNG-nya tetap harus
# seukuran preview lain. 3 menjaga kehalusannya setara MAX_SIDE lama (2048).
WC_REFINE = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def run_cycle(mon: LiveMonitor, area_id: int) -> dict:
    """Satu siklus, terkunci dua lapis: _CYCLE_LOCK menyerialkan daerah DI
    DALAM proses ini; JobLock mencegah dua PROSES (mis. uvicorn --reload lama
    yang belum benar-benar berhenti + proses baru, lihat etl/job_lock.py)
    menjalankan siklus daerah yang sama bersamaan dan berebut menulis berkas
    scene yang sama. Tanpa ini, restart yang tumpang tindih bisa membuat dua
    proses mengunduh S1/MODIS/GPM ke folder yang sama sekaligus."""
    lock_dir = fm.DATA_ROOT.parent / JOB_LOCK_DIRNAME
    lock = JobLock.acquire_key(f"live-area-{area_id}", lock_dir)
    if lock is None:
        logger.info("[LIVE] area=%d sedang dikerjakan proses lain, dilewati", area_id)
        return {"skipped": "locked_by_other_process"}
    try:
        key, prev_status = _queue_key(mon, area_id)
        if _CYCLE_LOCK.busy():
            _set_area(mon, area_id, status="WAITING", status_message="Waiting its turn")
        # Seluruh siklus (termasuk retry MODIS/GPM di luar run_dataset_job)
        # mengalah ke unduhan Dataset Saya di slot koneksi download_guard.
        with _CYCLE_LOCK.hold(key), dg.low_priority():
            started = time.time()
            try:
                _recover_interrupted_ingest(mon, area_id)
                return _run_cycle_locked(mon, area_id)
            finally:
                _report_auth_failures(mon, area_id, started)
                # Jalur keluar awal (daerah nonaktif/terhapus) tidak menulis
                # status; jangan biarkan kartu tertahan "Menunggu giliran".
                _restore_if_waiting(mon, area_id, prev_status)
    finally:
        lock.release()


def retry_scene_locked(mon: LiveMonitor, area_id: int, scene_date: date) -> None:
    """Coba ulang MODIS/GPM satu scene (tombol di kartu), antre di gerbang
    siklus yang sama. Kunci -inf: ini aksi pengguna yang sedang ditunggu."""
    with _CYCLE_LOCK.hold(float("-inf")), dg.low_priority():
        started = time.time()
        retry_failed_sources(mon, area_id, only=scene_date)
        reinterpret_all(mon, area_id)
        refresh_forecast(mon, area_id)
        _report_auth_failures(mon, area_id, started)


def _queue_key(mon: LiveMonitor, area_id: int) -> tuple[float, str | None]:
    """(kunci antrean FIFO, status sekarang). Daerah yang paling lama tidak
    dicek dilayani lebih dulu; yang belum pernah dicek paling depan."""
    with mon._db.session() as sess:
        a = sess.get(LiveArea, area_id)
        if a is None:
            return 0.0, None
        ts = a.last_checked_at.timestamp() if a.last_checked_at else 0.0
        return ts, a.status


def _restore_if_waiting(mon: LiveMonitor, area_id: int, prev_status: str | None) -> None:
    with mon._db.session() as sess:
        a = sess.get(LiveArea, area_id)
        if a is not None and a.status == "WAITING":
            a.status = prev_status if prev_status and prev_status != "WAITING" else "ACTIVE"
            a.status_message = None
            a.updated_at = _now()


def _report_auth_failures(mon: LiveMonitor, area_id: int, since: float) -> None:
    """401/403 NASA selama siklus ini. ensure_*_inputs_for_date menelan
    exception per sumber, jadi tanpa ini token kedaluwarsa cuma terlihat
    sebagai MODIS/GPM FAILED tanpa alasan di kartu."""
    for source, msg in dg.auth_failures_since(since).items():
        mon.log(area_id, "AUTH", "FAILED", msg, source=source)


def _set_area(mon: LiveMonitor, area_id: int, **fields) -> None:
    with mon._db.session() as sess:
        a = sess.get(LiveArea, area_id)
        if a is not None:
            for k, v in fields.items():
                setattr(a, k, v)
            a.updated_at = _now()


def _recover_interrupted_ingest(mon: LiveMonitor, area_id: int) -> None:
    """Pulihkan ingest yang terputus (proses mati/restart di tengah _ingest).

    Dipanggil sambil memegang JobLock daerah + _CYCLE_LOCK, jadi tidak ada
    ingest daerah ini yang sedang berjalan: setiap scene yang masih PROCESSING
    pasti yatim. Tanpa ini scene itu macet selamanya -- _discover_new_dates
    menganggap PROCESSING sudah "dikenal" sehingga tidak diunduh ulang, dan
    tidak pernah difinalisasi sehingga tidak tampil. Dijadikan FAILED dengan
    attempts +1 supaya ikut jalur coba-ulang MAX_S1_ATTEMPTS yang sudah ada.
    Job LIVE_INGEST-nya yang tertinggal DOWNLOADING/PROCESSING ditutup FAILED.
    """
    from etl.module5_orchestrator import LIVE_JOB_TYPE

    active = ("QUEUED", "PREPARING", "DOWNLOADING", "PROCESSING")
    with mon._db.session() as sess:
        a = sess.get(LiveArea, area_id)
        if a is None:
            return
        stuck = sess.scalars(select(LiveScene).where(
            LiveScene.area_id == area_id, LiveScene.status == "PROCESSING",
            LiveScene.deleted_at.is_(None))).all()
        stuck_dates = []
        for r in stuck:
            src = dict(r.source_status or {})
            s1 = dict(src.get("sentinel1") or {})
            s1["attempts"] = int(s1.get("attempts") or 0) + 1
            s1["status"] = "FAILED"
            s1["reason"] = "Ingest interrupted (process stopped)"
            src["sentinel1"] = s1
            r.source_status = src
            r.status = "FAILED"
            r.updated_at = _now()
            stuck_dates.append(r.scene_date)
        jobs = []
        if a.dataset_id is not None:
            jobs = sess.scalars(select(DatasetJob).where(
                DatasetJob.dataset_id == a.dataset_id,
                DatasetJob.job_type == LIVE_JOB_TYPE,
                DatasetJob.status.in_(active))).all()
        for j in jobs:
            j.status = "FAILED"
            j.completed_at = _now()
        job_ids = [j.job_id for j in jobs]
    for d in sorted(stuck_dates):
        mon.log(area_id, "RECOVER", "WARNING",
                f"Scene {d} was interrupted mid-ingest and will be retried", scene_date=d)
    if job_ids:
        logger.warning("[LIVE] area=%d job LIVE_INGEST yatim ditutup FAILED: %s", area_id, job_ids)
        mon.log(area_id, "RECOVER", "WARNING",
                f"Interrupted ingest job(s) closed: {', '.join(map(str, job_ids))}", job_ids=job_ids)


def _run_cycle_locked(mon: LiveMonitor, area_id: int) -> dict:
    with mon._db.session() as sess:
        a = sess.get(LiveArea, area_id)
        if a is None or a.deleted_at is not None:
            return {"skipped": "deleted"}
        if not a.enabled:
            mon.log(area_id, "CYCLE", "SKIPPED", "Area is disabled, cycle skipped")
            return {"skipped": "disabled"}
        retention, bbox_wkt, dataset_id = a.retention, a.bbox_wkt, a.dataset_id
        prev_status = a.status
        rows = sess.scalars(select(LiveScene).where(LiveScene.area_id == area_id)).all()
        scenes = {r.scene_date: (r.status, r.source_status or {}) for r in rows}
        dataset = sess.get(Dataset, dataset_id) if dataset_id else None
        if dataset is None:
            a.status, a.status_message = "ERROR", "The area's dataset is missing"
            return {"error": "dataset_missing"}
        dataset_name = dataset.name

    kept = sorted((d for d, (st, _) in scenes.items() if st in ("READY", "PARTIAL")), reverse=True)
    filling = len(kept) < retention
    _set_area(mon, area_id, status="BACKFILLING" if filling else "RUNNING",
              status_message="Backfilling initial scenes" if filling else "Checking for new scenes")
    mon.log(area_id, "CYCLE", "STARTED",
            f"Cycle started ({len(kept)}/{retention} scenes stored)")

    try:
        new_dates = _discover_new_dates(mon, area_id, bbox_wkt, retention, kept, scenes)
        processed: list[date] = []
        if new_dates:
            processed = _ingest(mon, area_id, dataset_id, new_dates)
        # Sumber yang gagal di scene lama dicoba ulang tiap siklus.
        retry_failed_sources(mon, area_id, skip=set(processed))
        reinterpret_all(mon, area_id)
        mon.enforce_retention(area_id)
        refresh_forecast(mon, area_id)
        _update_dataset_size(mon, dataset_id, dataset_name)
    except Exception as exc:
        logger.exception("[LIVE] siklus area=%d gagal", area_id)
        mon.log(area_id, "CYCLE", "FAILED", f"Cycle failed: {exc}",
                result={"level": "error", "text": f"Cycle failed: {str(exc)[:300]}"})
        _set_area(mon, area_id, status="ERROR", status_message=str(exc)[:500],
                  last_checked_at=_now())
        return {"error": str(exc)}

    with mon._db.session() as sess:
        n = len(sess.scalars(select(LiveScene).where(
            LiveScene.area_id == area_id, LiveScene.deleted_at.is_(None),
            LiveScene.status.in_(("READY", "PARTIAL")))).all())
    msg = (f"{n}/{retention} scenes stored"
           + ("" if n >= retention else " — not enough Sentinel-1 scenes available yet"))
    _set_area(mon, area_id, status="ACTIVE", status_message=msg, last_checked_at=_now())
    mon.log(area_id, "CYCLE", "COMPLETED",
            f"Cycle completed: {len(processed)} new scene(s), {msg}",
            new_scenes=[d.isoformat() for d in processed], previous_status=prev_status,
            result=_cycle_result(mon, area_id, new_dates, n, retention))
    return {"new_scenes": [d.isoformat() for d in processed], "stored": n}


_SOURCE_NAMES = {"sentinel1": "Sentinel-1", "modis": "MODIS", "gpm": "GPM"}


def _cycle_result(mon: LiveMonitor, area_id: int, targets: list[date],
                  stored: int, retention: int) -> dict:
    """Ringkasan hasil siklus untuk kartu: {level: ok|warn, text}.
    Dibedakan lengkap / sebagian (sumber mana yang gagal) / gagal, supaya
    siklus yang tidak mulus tidak terlihat sama dengan yang mulus."""
    from etl import download_guard as dg

    full, partial, failed, incomplete = 0, [], 0, 0
    if targets:
        with mon._db.session() as sess:
            rows = sess.scalars(select(LiveScene).where(
                LiveScene.area_id == area_id, LiveScene.scene_date.in_(targets))).all()
            for r in rows:
                if r.status == "READY":
                    full += 1
                elif r.status == "PARTIAL":
                    bad = [_SOURCE_NAMES.get(k, k) for k, v in (r.source_status or {}).items()
                           if isinstance(v, dict) and v.get("status") == "FAILED"]
                    partial.append(", ".join(bad) or "source")
                elif r.status == "FAILED":
                    failed += 1
                elif r.status == "INCOMPLETE":
                    incomplete += 1
    parts = []
    if not targets:
        parts.append(f"no new scenes ({stored}/{retention} stored)")
    else:
        parts.append(f"{len(targets)} new scene(s)")
        detail = []
        if full:
            detail.append(f"{full} complete")
        if partial:
            srcs = sorted(set(", ".join(partial).split(", ")))
            detail.append(f"{len(partial)} partial ({'/'.join(srcs)} failed)")
        if failed:
            detail.append(f"{failed} failed Sentinel-1")
        if incomplete:
            detail.append(f"{incomplete} rejected (Sentinel-1 does not cover the AOI)")
        if detail:
            parts[-1] += " — " + ", ".join(detail)
    auth = dg.active_auth_failures()
    if auth:
        parts.append("NASA token rejected")
    level = "warn" if (partial or failed or incomplete or auth) else "ok"
    return {"level": level, "text": "Done: " + "; ".join(parts)}


# ---------------------------------------------------------------------------
# 1. discovery
# ---------------------------------------------------------------------------

def _discover_new_dates(mon, area_id, bbox_wkt, retention, kept, scenes) -> list[date]:
    from etl import aoi_coverage as aoi_cov
    from etl.module1_download import discover_scenes
    from etl.module5_orchestrator import _drop_dates_barely_covering_aoi, _scene_date

    today = _now().date()
    if len(kept) < retention:
        lookback = min(MAX_LOOKBACK_DAYS, retention * S1_REVISIT_DAYS + BACKFILL_MARGIN_DAYS)
        date_from = today - timedelta(days=lookback)
    else:
        date_from = min(kept[0] - timedelta(days=1), today - timedelta(days=ROUTINE_LOOKBACK_DAYS))
    date_to = _now() + timedelta(days=1)

    try:
        found = discover_scenes(
            bbox_wkt=bbox_wkt,
            date_from=datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc),
            date_to=date_to, max_results=200,
        )
    except Exception as exc:
        mon.log(area_id, "DISCOVER", "FAILED", f"Failed to check for Sentinel-1 scenes: {exc}")
        raise
    # LAPIS 1 gerbang kelengkapan AOI (etl/aoi_coverage.py): buang tanggal yang
    # footprint-nya saja sudah tidak menutup AOI, SEBELUM diunduh. Ambangnya
    # live.min_aoi_coverage, bukan MIN_S1_AOI_COVERAGE milik orchestrator --
    # yang itu penjaga pemborosan unduhan arsip (5%), terlalu longgar untuk
    # menjamin kelengkapan. Footprint bersifat optimis, jadi lapis 2 di
    # finalize_scene masih mengukur ulang dari pikselnya.
    with mon._db.session() as sess:
        min_cov = aoi_cov.min_coverage(sess)
    found = _drop_dates_barely_covering_aoi(found, bbox_wkt, job_id=0,
                                            min_fraction=min_cov)
    dates = sorted({d for s in found if (d := _scene_date(s))}, reverse=True)

    def known(d: date) -> bool:
        if d not in scenes:
            return False
        st, src = scenes[d]
        if st == "FAILED":
            return int((src.get("sentinel1") or {}).get("attempts") or 0) >= MAX_S1_ATTEMPTS
        return True  # READY/PARTIAL/PROCESSING/DELETED

    candidates = [d for d in dates if not known(d)]
    # Hanya yang akan masuk `retensi` terbaru; scene yang lebih tua dari yang
    # sudah tersimpan akan langsung terhapus lagi, jadi tidak diunduh.
    top = sorted(set(kept) | set(candidates), reverse=True)[:retention]
    targets = sorted(d for d in top if d in candidates)
    mon.log(area_id, "DISCOVER", "OK",
            f"{len(dates)} S1 date(s) found since {date_from}, {len(targets)} newly processed",
            found=[d.isoformat() for d in dates], targets=[d.isoformat() for d in targets])
    return targets


# ---------------------------------------------------------------------------
# 2-3. ingest + finalisasi scene
# ---------------------------------------------------------------------------

def _ingest(mon: LiveMonitor, area_id: int, dataset_id: int, dates: list[date]) -> list[date]:
    from etl.module5_orchestrator import LIVE_JOB_TYPE, run_dataset_job

    with mon._db.session() as sess:
        for d in dates:
            row = sess.scalar(select(LiveScene).where(
                LiveScene.area_id == area_id, LiveScene.scene_date == d))
            if row is None:
                row = LiveScene(area_id=area_id, dataset_id=dataset_id, scene_date=d,
                                source_status={}, interpretations={},
                                area_status={}, previews={}, deleted_files=[])
                sess.add(row)
            row.status = "PROCESSING"
            row.updated_at = _now()
        ds = sess.get(Dataset, dataset_id)
        ds.date_start = min(ds.date_start, dates[0])
        ds.date_end = max(ds.date_end, dates[-1])
        job = DatasetJob(dataset_id=dataset_id, job_type=LIVE_JOB_TYPE, status="QUEUED",
                         date_range_start=dates[0], date_range_end=dates[-1])
        sess.add(job)
        sess.flush()
        job_id = job.job_id

    mon.log(area_id, "INGEST", "STARTED",
            f"Downloading & processing {len(dates)} scene(s) ({dates[0]} to {dates[-1]}), job {job_id}",
            job_id=job_id)
    try:
        run_dataset_job(mon._db, job_id)
    except Exception as exc:
        # Scene yang sebagian berkasnya sudah jadi tetap difinalisasi di bawah.
        mon.log(area_id, "INGEST", "FAILED", f"Job {job_id} berhenti: {exc}", job_id=job_id)
    with mon._db.session() as sess:
        job = sess.get(DatasetJob, job_id)
        job_status = job.status if job else "?"
    mon.log(area_id, "INGEST", "OK" if job_status == "COMPLETED" else "WARNING",
            f"Job {job_id} finished with status {job_status}", job_id=job_id)

    done = []
    for d in dates:
        if finalize_scene(mon, area_id, d) in ("READY", "PARTIAL"):
            done.append(d)
    return done


def finalize_scene(mon: LiveMonitor, area_id: int, scene_date: date) -> str:
    """Metrik + status sumber + preview untuk satu scene. Kalimat kondisi
    ditulis reinterpret_all (butuh scene sebelumnya)."""
    from etl import aoi_coverage as aoi_cov
    from etl import live_metrics as lmx

    info = _area_files(mon, area_id)
    if info is None:
        return "FAILED"
    files = info
    inputs = lmx.scene_inputs(files.root, scene_date)
    metrics = lmx.compute_metrics(inputs, scene_date)
    status = lmx.source_status(inputs, metrics)

    with mon._db.session() as sess:
        row = sess.scalar(select(LiveScene).where(
            LiveScene.area_id == area_id, LiveScene.scene_date == scene_date))
        prev_attempts = int(((row.source_status or {}).get("sentinel1") or {}).get("attempts") or 0) if row else 0
        area = sess.get(LiveArea, area_id)
        bbox_wkt = area.bbox_wkt if area else None
        min_cov = aoi_cov.min_coverage(sess)

    # LAPIS 2 gerbang kelengkapan AOI: diukur dari piksel, bukan footprint.
    # Dicatat juga saat lolos -- angkanya yang membuat scene lama bisa diaudit
    # ulang tanpa membaca rasternya lagi (scripts/repair_incomplete_scenes.py).
    coverage = aoi_cov.scene_coverage(inputs.get("s1"), bbox_wkt) if bbox_wkt else None
    if coverage is not None:
        status["sentinel1"]["aoi_coverage"] = round(coverage, 4)
        status["sentinel1"]["aoi_coverage_min"] = min_cov

    if status["sentinel1"]["status"] == "OK" and coverage is not None and coverage < min_cov:
        # Bukan FAILED: FAILED memicu unduh ulang sampai MAX_S1_ATTEMPTS,
        # padahal mengulang tidak akan menambah cakupan -- pada tanggal itu
        # satelitnya memang tidak melewati sisa AOI. Baris ini tetap disimpan
        # sebagai catatan supaya tanggalnya tidak ditemukan ulang tiap siklus.
        status["sentinel1"]["status"] = "INCOMPLETE"
        scene_status = "INCOMPLETE"
        previews = {}
        mon.log(area_id, "SCENE", "WARNING",
                f"Scene {scene_date} rejected: Sentinel-1 covers only "
                f"{coverage * 100:.1f}% of the AOI (minimum {min_cov * 100:.0f}%)",
                scene_date=scene_date, source_status=status)
    elif status["sentinel1"]["status"] != "OK":
        status["sentinel1"]["attempts"] = prev_attempts + 1
        scene_status = "FAILED"
        previews = {}
        mon.log(area_id, "SCENE", "FAILED",
                f"Scene {scene_date}: Sentinel-1 could not be processed "
                f"(attempt {prev_attempts + 1}/{MAX_S1_ATTEMPTS})", scene_date=scene_date)
    else:
        previews = {}
        try:
            from etl.admin_overlay import load_regions
            from etl.live_preview import render_scene_previews
            previews = render_scene_previews(files, scene_date, inputs,
                                             load_regions(mon._db), bbox_wkt=bbox_wkt)
        except Exception as exc:
            logger.exception("[LIVE] preview %s gagal", scene_date)
            mon.log(area_id, "PREVIEW", "FAILED", f"Preview for {scene_date} failed: {exc}",
                    scene_date=scene_date)
        failed = [k for k in ("modis", "gpm") if status[k]["status"] == "FAILED"]
        scene_status = "PARTIAL" if failed else "READY"
        mon.log(area_id, "SCENE", "OK" if not failed else "WARNING",
                f"Scene {scene_date} {scene_status}: "
                + ", ".join(f"{k}={v['status']}" for k, v in status.items()),
                scene_date=scene_date, source_status=status,
                previews=len(previews.get("items", {})) if previews else 0)

    with mon._db.session() as sess:
        row = sess.scalar(select(LiveScene).where(
            LiveScene.area_id == area_id, LiveScene.scene_date == scene_date))
        if row is not None:
            row.status = scene_status
            # M31: angka ke live_scene_metrics, deskriptor teks ke
            # source_status[sumber].meta (K6).
            meta = lmx.save_scene_metrics(sess, row.live_scene_id, scene_date, _jsonable(metrics))
            for src, entries in meta.items():
                status.setdefault(src, {})["meta"] = entries
            row.source_status = _jsonable(status)
            row.previews = _jsonable(previews)
            row.s1_product_ids = [
                next(iter(f.values())).name.rsplit("_", 3)[0] for f in inputs["s1"]
            ]
            row.updated_at = _now()
    if scene_status == "INCOMPLETE":
        # Berkasnya tidak berguna untuk apa pun -- dihapus sekarang, bukan
        # menunggu retensi: enforce_retention hanya menghitung READY/PARTIAL,
        # jadi scene ini tidak akan pernah tersapu dan COG-nya menumpuk.
        mon.delete_scene(area_id, scene_date,
                         reason=f"AOI coverage {coverage * 100:.1f}% below "
                                f"{min_cov * 100:.0f}%")
        with mon._db.session() as sess:
            row = sess.scalar(select(LiveScene).where(
                LiveScene.area_id == area_id, LiveScene.scene_date == scene_date))
            if row is not None:
                # delete_scene menyetel DELETED; alasan sebenarnya disimpan di
                # status supaya terbedakan dari scene yang kena retensi.
                row.status = "INCOMPLETE"
                row.source_status = _jsonable(status)
    if scene_status in ("READY", "PARTIAL"):
        try:
            water_change_stage(mon, area_id, scene_date, files, inputs)
        except Exception as exc:
            # Tahap opsional (processing_stages.is_mandatory = false).
            logger.exception("[LIVE] perubahan air %s gagal", scene_date)
            mon.log(area_id, "WATER_CHANGE", "FAILED", f"Water change map for {scene_date} failed: {exc}",
                    scene_date=scene_date)
    return scene_status


def _drop_water_change(mon: LiveMonitor, area_id: int, scene_date: date,
                       files: _LiveFiles) -> None:
    """Buang PNG + entri preview peta perubahan air satu scene.

    Dipakai saat scene tidak lagi punya pembanding. Metrik di
    live_scene_water_change dibiarkan: tabel itu log, dan baris lamanya tetap
    benar untuk tanggal pembanding yang dicatatnya."""
    from etl import water_change as wcm

    pdir = files.preview_dir(scene_date)
    for name in (f"{wcm.PREVIEW_KEY}.png", f"{wcm.PREVIEW_KEY}_adm.png"):
        try:
            (pdir / name).unlink(missing_ok=True)
        except OSError:
            logger.warning("[LIVE] gagal menghapus %s", pdir / name)
    with mon._db.session() as sess:
        row = sess.scalar(select(LiveScene).where(
            LiveScene.area_id == area_id, LiveScene.scene_date == scene_date))
        if row is None:
            return
        previews = dict(row.previews or {})
        items = dict(previews.get("items") or {})
        if items.pop(wcm.PREVIEW_KEY, None) is not None:
            previews["items"] = items
            row.previews = previews


def _scene_vh(files: _LiveFiles, frames: list, scratch_key: str):
    """Path VH satu scene (mosaik sementara bila >1 frame) + direktori
    sementara yang harus dihapus pemanggil (atau None)."""
    frames = [{b: str(p) for b, p in f.items()} for f in frames or []]
    if not frames:
        return None, None
    if len(frames) == 1:
        vh = frames[0].get("VH")
        return (Path(vh) if vh else None), None
    from etl.s1_mosaic import mosaic_frames
    scratch = files.root / "_work" / f"wc_{scratch_key}"
    scratch.mkdir(parents=True, exist_ok=True)
    s1 = mosaic_frames(frames, scratch, date_key=scratch_key, level="PROCESSED")
    return (Path(s1["VH"]) if "VH" in s1 else None), scratch


def water_change_stage(mon: LiveMonitor, area_id: int, scene_date: date, files: _LiveFiles,
                       inputs: dict) -> dict | None:
    """Peta & metrik perubahan air terhadap scene tersimpan sebelumnya yang
    COG VH-nya masih ada (PIPELINE §4.1). Scene pertama -> tidak ada baris."""
    import shutil

    from etl import live_metrics as lmx
    from etl import water_change as wcm
    from etl.live_preview import LIVE_MAX_SIDE as LIVE_PREVIEW_MAX_SIDE
    from etl.settings import get_setting

    with mon._db.session() as sess:
        cur = sess.scalar(select(LiveScene).where(
            LiveScene.area_id == area_id, LiveScene.scene_date == scene_date))
        prevs = sess.scalars(select(LiveScene).where(
            LiveScene.area_id == area_id, LiveScene.scene_date < scene_date,
            LiveScene.deleted_at.is_(None), LiveScene.status.in_(("READY", "PARTIAL")))
            .order_by(LiveScene.scene_date.desc())).all()
        threshold = float(get_setting(sess, "water.vh_threshold_db"))
        area = sess.get(LiveArea, area_id)
        bbox_wkt = area.bbox_wkt if area else None
        cur_id, cur_products = cur.live_scene_id, list(cur.s1_product_ids or [])
        candidates = [(p.live_scene_id, p.scene_date, list(p.s1_product_ids or [])) for p in prevs]
    prev = next(((sid, d, prods, fr) for sid, d, prods in candidates
                 if (fr := lmx.s1_frames(files.root, d))), None)
    if prev is None:
        # Sisa render terdahulu harus ikut pergi. Tanpa ini, scene yang
        # pembandingnya baru saja hilang (kena retensi, atau ditolak gerbang
        # AOI) menyimpan PNG lama selamanya: bingkainya ketinggalan zaman dan
        # isinya membandingkan dengan tanggal yang rasternya sudah tidak ada.
        _drop_water_change(mon, area_id, scene_date, files)
        mon.log(area_id, "WATER_CHANGE", "SKIPPED", f"Scene {scene_date}: no comparison scene yet",
                scene_date=scene_date)
        return None
    prev_id, prev_date, prev_products, prev_frames = prev
    dk = scene_date.strftime("%Y%m%d")
    cur_vh, s1 = _scene_vh(files, inputs.get("s1"), dk)
    prev_vh, s2 = _scene_vh(files, prev_frames, prev_date.strftime("%Y%m%d") + "_ref")
    try:
        if cur_vh is None or prev_vh is None:
            mon.log(area_id, "WATER_CHANGE", "SKIPPED", f"Scene {scene_date}: VH band missing",
                    scene_date=scene_date)
            return None
        # Satu bingkai dengan tujuh preview lain: grid AOI yang sama, cuma
        # WC_REFINE kali lebih halus supaya luas km2 tidak dihitung dari
        # piksel 768-an. Penurunannya kembali ke ukuran preview jadi bulat.
        grid = out_shape = None
        if bbox_wkt:
            from etl import aoi_coverage as aoi_cov
            import rasterio
            with rasterio.open(cur_vh) as src:
                scene_crs = src.crs
            base = aoi_cov.preview_grid(bbox_wkt, scene_crs, LIVE_PREVIEW_MAX_SIDE)
            grid = aoi_cov.refine(base, WC_REFINE)
            out_shape = (base.height, base.width)
        wc = wcm.compute(cur_vh, prev_vh, threshold, grid=grid)
        with mon._db.session() as sess:
            orbits = wcm.orbit_metadata(sess, cur_products + prev_products)
        same = wcm.same_orbit(cur_products, prev_products, orbits)
        from etl.admin_overlay import load_regions
        legend = wcm.render_png(wc, files.preview_dir(scene_date) / f"{wcm.PREVIEW_KEY}.png",
                                orbit_differs=same is False, regions=load_regions(mon._db),
                                out_shape=out_shape)
        # "file_adm" milik item preview, bukan legenda yang dikirim ke UI.
        file_adm = legend.pop("file_adm", None)
    finally:
        for d in (s1, s2):
            if d is not None:
                shutil.rmtree(d, ignore_errors=True)
    with mon._db.session() as sess:
        wcm.save_metrics(sess, cur_id, prev_id, wc.metrics, same, source_date=prev_date)
        row = sess.get(LiveScene, cur_id)
        previews = dict(row.previews or {})
        items = dict(previews.get("items") or {})
        items[wcm.PREVIEW_KEY] = {"file": f"{wcm.PREVIEW_KEY}.png", "label": "Perubahan air Sentinel-1",
                                  "legend": legend, "ref_date": prev_date.isoformat(),
                                  "file_adm": file_adm}
        previews["items"] = items
        row.previews = _jsonable(previews)
    mon.log(area_id, "WATER_CHANGE", "OK",
            f"Scene {scene_date} vs {prev_date}: new {wc.metrics['new_km2']} km², "
            f"receded {wc.metrics['receded_km2']} km²" + ("" if same is not False else " (different orbit)"),
            scene_date=scene_date)
    return wc.metrics


def retry_failed_sources(mon: LiveMonitor, area_id: int, skip: set[date] | None = None,
                         only: date | None = None) -> list[date]:
    """Unduh ulang MODIS/GPM yang FAILED di scene tersimpan, lalu finalisasi
    ulang scene-nya."""
    from etl.module9_fusion import ensure_gpm_inputs_for_date, ensure_modis_inputs_for_date
    from etl.pipeline_logger import PipelineLogger

    with mon._db.session() as sess:
        a = sess.get(LiveArea, area_id)
        rows = sess.scalars(select(LiveScene).where(
            LiveScene.area_id == area_id, LiveScene.deleted_at.is_(None),
            LiveScene.status.in_(("PARTIAL",) if only is None else ("PARTIAL", "READY")))).all()
        todo = [(r.scene_date, r.source_status or {}) for r in rows
                if (only is None or r.scene_date == only) and r.scene_date not in (skip or set())]
        dataset = sess.get(Dataset, a.dataset_id) if a and a.dataset_id else None
        if dataset is None:
            return []
        ds_id, ds_name, region_id, bbox = dataset.dataset_id, dataset.name, dataset.region_id, dataset.bbox_wkt

    bbox_tuple = shapely_wkt.loads(bbox).bounds
    plog = PipelineLogger(mon._db)
    dg.set_context(ds_id)  # jeda retry MODIS/GPM tampil di bar daerah ini
    redone = []
    for d, st in todo:
        for src, fn in (("modis", ensure_modis_inputs_for_date), ("gpm", ensure_gpm_inputs_for_date)):
            if (st.get(src) or {}).get("status") != "FAILED" and only is None:
                continue
            try:
                fn(mon._db, ds_id, ds_name, region_id, bbox_tuple, d, plog=plog)
                mon.log(area_id, "RETRY", "OK", f"{src.upper()} {d} retried", scene_date=d)
            except Exception as exc:
                mon.log(area_id, "RETRY", "FAILED", f"{src.upper()} {d} failed again: {exc}",
                        scene_date=d)
        finalize_scene(mon, area_id, d)
        redone.append(d)
    return redone


def reinterpret_all(mon: LiveMonitor, area_id: int) -> None:
    """Tulis ulang kalimat kondisi semua scene tersimpan, urut tanggal, dengan
    scene tersimpan sebelumnya sebagai pembanding."""
    from etl import water_change as wcm
    from etl.live_interpret import area_status, interpret_scene, sync_bmkg_thresholds
    from etl.live_metrics import load_scene_metrics

    with mon._db.session() as sess:
        sync_bmkg_thresholds(sess)
        rows = sess.scalars(select(LiveScene).where(
            LiveScene.area_id == area_id, LiveScene.deleted_at.is_(None),
            LiveScene.status.in_(("READY", "PARTIAL"))).order_by(LiveScene.scene_date)).all()
        metrics = load_scene_metrics(sess, rows)
        changes = wcm.load_metrics(sess, [r.live_scene_id for r in rows])
        prev = None
        for r in rows:
            current = metrics[r.live_scene_id]
            interp = interpret_scene(current, prev, r.source_status or {})
            if r.live_scene_id in changes or (r.previews or {}).get("items", {}).get(wcm.PREVIEW_KEY):
                interp[wcm.PREVIEW_KEY] = wcm.sentence(changes.get(r.live_scene_id))
            r.interpretations = _jsonable(interp)
            r.area_status = _jsonable(area_status(interp))
            prev = current


# ---------------------------------------------------------------------------
# 4. forecast
# ---------------------------------------------------------------------------

def refresh_forecast(mon: LiveMonitor, area_id: int) -> None:
    from etl.live_forecast import build_area_forecast
    from etl.live_metrics import load_scene_metrics

    with mon._db.session() as sess:
        rows = sess.scalars(select(LiveScene).where(
            LiveScene.area_id == area_id, LiveScene.deleted_at.is_(None),
            LiveScene.status.in_(("READY", "PARTIAL"))).order_by(LiveScene.scene_date)).all()
        metrics = load_scene_metrics(sess, rows)
        series = [(r.scene_date, metrics[r.live_scene_id]) for r in rows]
    fc = build_area_forecast(series)
    _set_area(mon, area_id, forecast=_jsonable(fc), forecast_updated_at=_now())
    mon.log(area_id, "FORECAST", "OK",
            f"Forecast computed from {len(series)} scene(s), {fc.get('steps', 0)} step(s)")


# ---------------------------------------------------------------------------
# util
# ---------------------------------------------------------------------------

def _area_files(mon: LiveMonitor, area_id: int) -> _LiveFiles | None:
    with mon._db.session() as sess:
        a = sess.get(LiveArea, area_id)
        info = mon._dataset_info(a.dataset_id if a else None)
    return _LiveFiles(*info) if info else None


def _update_dataset_size(mon: LiveMonitor, dataset_id: int, dataset_name: str) -> None:
    root = fm.get_dataset_root(dataset_id, dataset_name)
    size = sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) if root.is_dir() else 0
    with mon._db.session() as sess:
        d = sess.get(Dataset, dataset_id)
        if d is not None:
            d.total_size_bytes = size
