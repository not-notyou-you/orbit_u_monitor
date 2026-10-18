# etl/scheduler.py
"""Scheduler tunggal Orbit-U: The Monitor (PIPELINE.md §7, M22). Menggantikan live_scheduler.

| Job                       | Cron (Asia/Jakarta)          | Kunci advisory |
|---------------------------|------------------------------|----------------|
| Hidromet harian           | 02:00 setiap hari            | hydromet       |
| Pembaruan Late -> Final   | Minggu 04:00                 | hydromet       |
| Siklus Live               | 01:00, 07:00, 13:00, 19:00   | live           |
| Laporan mingguan          | Senin 03:00 / 03:15          | report         |
| Laporan bulanan           | tanggal 1, 03:30 / 03:45     | report         |
| Forecast tersimpan (M62)  | 00:30, 06:30, 12:30, 18:30   | forecast       |

Setiap job memegang ``pg_try_advisory_lock`` selama berjalan. Gagal ->
worker lain sedang menjalankannya -> job dilewati dan dicatat sebagai baris
``processing_jobs`` berstatus ``SKIPPED_LOCKED`` (tahap ORCHESTRATE). Job
laporan lebih dulu menunggu kunci ``hydromet`` maksimal
``app_settings.report.wait_hydromet_minutes`` (60) lalu tetap jalan dengan
catatan "data hari terakhir belum lengkap" (§6.1).

Forecast tersimpan juga dihitung di akhir job hidromet dan setiap siklus Live
(etl/forecast_store.py); job ``forecast_refresh`` hanya jaring pengaman, dan
murah karena deret yang datanya tidak berubah dilewati.

Backup ``pg_dump`` 01:30 di luar APScheduler (cron OS).
"""

from __future__ import annotations

import json
import logging
import os
import socket
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import text

from etl.advisory_lock import advisory_lock
from etl.database_client import DatabaseClient

logger = logging.getLogger(__name__)

TIMEZONE = "Asia/Jakarta"
INCOMPLETE_NOTE = "Catatan: data hari terakhir belum lengkap (job hidromet masih berjalan saat laporan dibuat)."


@dataclass(frozen=True)
class JobSpec:
    job_id: str
    name: str
    lock: str
    cron: dict


JOBS = (
    JobSpec("hydromet_daily", "Hidromet harian", "hydromet", {"hour": 2, "minute": 0}),
    JobSpec("hydromet_final", "Pembaruan Late -> Final", "hydromet", {"day_of_week": "sun", "hour": 4, "minute": 0}),
    JobSpec("live_cycle", "Siklus Live", "live", {"hour": "1,7,13,19", "minute": 0}),
    JobSpec("report_HYDROMET_WEEKLY", "Laporan Hidromet mingguan", "report", {"day_of_week": "mon", "hour": 3, "minute": 0}),
    JobSpec("report_DATAHEALTH_WEEKLY", "Laporan Kesehatan Data mingguan", "report",
            {"day_of_week": "mon", "hour": 3, "minute": 15}),
    JobSpec("report_HYDROMET_MONTHLY", "Laporan Hidromet bulanan", "report", {"day": 1, "hour": 3, "minute": 30}),
    JobSpec("report_DATAHEALTH_MONTHLY", "Laporan Kesehatan Data bulanan", "report", {"day": 1, "hour": 3, "minute": 45}),
    JobSpec("forecast_refresh", "Forecast tersimpan", "forecast", {"hour": "0,6,12,18", "minute": 30}),
)


def record_skip(db, spec_id: str, lock: str) -> None:
    """Baris processing_jobs SKIPPED_LOCKED (tahap ORCHESTRATE, tanpa jangkar)."""
    try:
        with db.session() as sess:
            sess.execute(text("""
                INSERT INTO processing_jobs (stage_id, status, started_at, completed_at, worker_hostname,
                                             error_code, error_message, parameters_json)
                SELECT stage_id, 'SKIPPED_LOCKED', now(), now(), :host, 'SKIPPED_LOCKED',
                       :msg, CAST(:params AS jsonb)
                FROM processing_stages WHERE stage_name = 'ORCHESTRATE'"""),
                {"host": socket.gethostname(), "msg": f"advisory lock '{lock}' held by another worker",
                 "params": json.dumps({"scheduler_job": spec_id, "lock": lock})})
    except Exception:
        logger.exception("[SCHED] gagal mencatat SKIPPED_LOCKED %s", spec_id)


def run_locked(db, spec_id: str, lock: str, fn: Callable[[], object]) -> dict:
    """Jalankan ``fn`` di bawah advisory lock ``lock``; dilewati bila terkunci."""
    with advisory_lock(db, lock) as got:
        if not got:
            logger.warning("[SCHED] %s dilewati: kunci %s dipegang worker lain", spec_id, lock)
            record_skip(db, spec_id, lock)
            return {"status": "SKIPPED_LOCKED"}
        try:
            return {"status": "OK", "result": fn()}
        except Exception as exc:
            logger.exception("[SCHED] %s gagal", spec_id)
            return {"status": "FAILED", "error": str(exc)}


# --- isi job -------------------------------------------------------------------------

def job_hydromet_daily(db) -> dict:
    from etl import forecast_store as fs
    from etl import hydromet_job as hj
    from etl import notify
    out = run_locked(db, "hydromet_daily", "hydromet",
                     lambda: [(str(r.obs_date), r.status) for r in hj.run_daily(db)])
    fs.refresh_quietly(db)
    # M64: peringatan email setelah angka dan alert hari ini tersimpan.
    # Backfill/proses ulang tidak lewat sini, jadi tanggal lampau tidak memicu email.
    notify.run_quietly(db, "hydromet_daily")
    return out


def job_hydromet_final(db) -> dict:
    from etl import forecast_store as fs
    from etl import hydromet_job as hj
    out = run_locked(db, "hydromet_final", "hydromet",
                     lambda: [(str(r.obs_date), r.status) for r in hj.refresh_late_to_final(db)])
    fs.refresh_quietly(db)
    return out


def job_forecast(db) -> dict:
    """refresh() memegang kunci 'forecast' sendiri, jadi tidak lewat run_locked."""
    from etl import forecast_store as fs
    try:
        res = fs.refresh(db)
    except Exception as exc:
        logger.exception("[SCHED] forecast_refresh gagal")
        return {"status": "FAILED", "error": str(exc)}
    if res["locked"]:
        record_skip(db, "forecast_refresh", "forecast")
        return {"status": "SKIPPED_LOCKED"}
    return {"status": "OK", "result": res}


def job_live(db) -> dict:
    """Siklus setiap Live Area aktif, berurutan, selama kunci 'live' dipegang."""
    def _run():
        from etl.live_monitor import LiveMonitor
        mon = LiveMonitor(db)
        areas = sorted(mon.list_areas(), key=lambda a: (
            a["last_checked_at"] is not None,
            a["last_checked_at"].timestamp() if a["last_checked_at"] else 0.0))
        done = []
        for area in areas:
            if not area["enabled"]:
                continue
            try:
                mon.run_cycle(area["area_id"])
                done.append(area["area_id"])
            except Exception:
                logger.exception("[SCHED] siklus Live area=%s gagal", area["area_id"])
        return done
    from etl import notify
    out = run_locked(db, "live_cycle", "live", _run)
    # M64: lintasan Sentinel-1 baru (VV/VH/% air per kecamatan) bisa memicu email.
    notify.run_quietly(db, "live_cycle")
    return out


def job_report(db, code: str, wait_minutes: float | None = None) -> dict:
    from etl.report_periodic import generate_report, previous_period
    from etl.settings import read_setting

    if wait_minutes is None:
        wait_minutes = float(read_setting(db, "report.wait_hydromet_minutes"))
    notes: list[str] = []
    # Tunggu job hidromet 02:00 selesai (kunci dilepas), maksimal wait_minutes.
    with advisory_lock(db, "hydromet", wait_seconds=wait_minutes * 60) as got:
        if not got:
            notes.append(INCOMPLETE_NOTE)
    period = previous_period(code)
    return run_locked(db, f"report_{code}", "report",
                      lambda: generate_report(db, code, period, notes=notes).status)


def runner_for(spec: JobSpec, db) -> Callable[[], dict]:
    if spec.job_id == "hydromet_daily":
        return lambda: job_hydromet_daily(db)
    if spec.job_id == "hydromet_final":
        return lambda: job_hydromet_final(db)
    if spec.job_id == "live_cycle":
        return lambda: job_live(db)
    if spec.job_id == "forecast_refresh":
        return lambda: job_forecast(db)
    code = spec.job_id.removeprefix("report_")
    return lambda: job_report(db, code)


class Scheduler:
    """APScheduler di proses API (koneksi monitor_etl)."""

    def __init__(self, db: DatabaseClient) -> None:
        self._db = db
        self._scheduler = None

    def start(self) -> None:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        self._scheduler = BackgroundScheduler(timezone=TIMEZONE, job_defaults={"coalesce": True, "max_instances": 1})
        for spec in JOBS:
            self._scheduler.add_job(func=runner_for(spec, self._db), trigger=CronTrigger(**spec.cron),
                                    id=spec.job_id, name=spec.name, replace_existing=True,
                                    misfire_grace_time=3600)
        self._scheduler.start()
        logger.info("[SCHED] dimulai: %s", ", ".join(s.job_id for s in JOBS))
        self._recover_live_areas()

    def jobs(self) -> list[dict]:
        if not self._scheduler:
            return []
        return [{"id": j.id, "name": j.name, "next_run": j.next_run_time} for j in self._scheduler.get_jobs()]

    def _recover_live_areas(self) -> None:
        """Area yang siklusnya terputus restart (BACKFILLING/RUNNING/WAITING)
        dilanjutkan, termasuk Live Area default baru dari load_regions.py."""
        if os.getenv("AUTO_RESUME_JOBS", "true").lower() not in ("1", "true", "yes"):
            return
        try:
            from etl.live_monitor import LiveMonitor
            mon = LiveMonitor(self._db)
            for area in mon.list_areas():
                if area["enabled"] and area["status"] in ("BACKFILLING", "RUNNING", "WAITING"):
                    logger.warning("[SCHED] Live area=%d terputus (%s), dilanjutkan", area["area_id"], area["status"])
                    mon.start_cycle(area["area_id"])
        except Exception:
            logger.exception("[SCHED] gagal memulihkan Live Area")

    def shutdown(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            logger.info("[SCHED] dihentikan")
