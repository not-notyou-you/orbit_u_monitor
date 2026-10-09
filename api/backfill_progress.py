# api/backfill_progress.py
"""Progres backfill Sentinel-1 dataset utama untuk halaman Proses berjalan (M58).

Semua angka dibaca dari basis data, jadi sama saja apakah backfill dijalankan
dari halaman Data, penjadwal, atau scripts/backfill_s1.py di proses lain:

* rencana siklus      live_events DISCOVER terakhir (details.targets)
* tanggal selesai     live_scenes target yang sudah bukan PROCESSING sejak siklus mulai
* frame (produk S1)   scene_job_state job LIVE_INGEST sejak siklus mulai
* posisi sekarang     processing_logs terbaru dataset Live ("Downloading: x / y MB")
* perkiraan selesai   rata-rata detik per frame yang sudah selesai x sisa frame;
                      sebelum ada frame selesai, dari kecepatan unduh terakhir.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

DEFAULT_FRAMES_PER_DATE = 1.7     # rata-rata AOI GMLS (151 produk / 90 tanggal)
DEFAULT_FRAME_MB = 1800
_DL = re.compile(r"Downloading:\s*(\d+)\s*/\s*(\d+)\s*MB")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def s1_progress(sess, area_id: int, dataset_id: int) -> dict | None:
    cycle = sess.execute(text("""
        SELECT created_at FROM live_events WHERE area_id = :a AND step = 'CYCLE' AND status = 'STARTED'
        ORDER BY event_id DESC LIMIT 1"""), {"a": area_id}).scalar()
    if cycle is None:
        return None
    disc = sess.execute(text("""
        SELECT details FROM live_events WHERE area_id = :a AND step = 'DISCOVER' AND created_at >= :c
        ORDER BY event_id DESC LIMIT 1"""), {"a": area_id, "c": cycle}).scalar()
    finished = sess.execute(text("""
        SELECT created_at FROM live_events WHERE area_id = :a AND step = 'CYCLE'
          AND status IN ('COMPLETED', 'FAILED') AND created_at >= :c
        ORDER BY event_id DESC LIMIT 1"""), {"a": area_id, "c": cycle}).scalar()
    targets = sorted((disc or {}).get("targets") or [], reverse=True)

    scenes = {str(r.scene_date): r for r in sess.execute(text("""
        SELECT scene_date, status, updated_at FROM live_scenes
        WHERE area_id = :a AND scene_date = ANY(CAST(:t AS date[]))"""), {"a": area_id, "t": targets}).all()}
    done = [d for d in targets if d in scenes and scenes[d].status != "PROCESSING" and scenes[d].updated_at >= cycle]
    ok = [d for d in done if scenes[d].status in ("READY", "PARTIAL")]
    current_dates = [d for d in targets if d in scenes and scenes[d].status == "PROCESSING"]

    frames = sess.execute(text("""
        SELECT f.product_identifier, f.stage_status, f.current_stage, f.started_at, f.completed_at, j.job_id
        FROM scene_job_state f JOIN dataset_jobs j ON j.job_id = f.job_id
        WHERE j.dataset_id = :d AND j.job_type = 'LIVE_INGEST' AND j.created_at >= :c"""),
        {"d": dataset_id, "c": cycle}).mappings().all()
    frames_done = [f for f in frames if f["stage_status"] in ("COMPLETED", "SKIPPED", "FAILED")]
    pending_job_frames = len(frames) - len(frames_done)
    dates_in_jobs = {f["product_identifier"][17:25] for f in frames}
    fpd = (len(frames) / len(dates_in_jobs)) if dates_in_jobs else DEFAULT_FRAMES_PER_DATE
    untouched_dates = [d for d in targets if d.replace("-", "") not in dates_in_jobs]
    frames_total = len(frames) + round(len(untouched_dates) * fpd)
    frames_left = max(0, frames_total - len(frames_done))

    cur = sess.execute(text("""
        SELECT scene_id, module, stage, status, message, details, created_at FROM processing_logs
        WHERE dataset_id = :d AND created_at >= :c ORDER BY log_id DESC LIMIT 1"""),
        {"d": dataset_id, "c": cycle}).mappings().first()
    current = None
    speed = None
    if cur:
        pid = cur["scene_id"] or ""
        current = {"product": pid.replace(".SAFE", ""), "date": f"{pid[17:21]}-{pid[21:23]}-{pid[23:25]}" if len(pid) > 25 else None,
                   "stage": cur["stage"], "message": cur["message"], "at": cur["created_at"],
                   "percent": (cur["details"] or {}).get("progress_percent")}
        # Kecepatan unduh dari dua titik progres frame yang sama (15 menit terakhir).
        pts = sess.execute(text("""
            SELECT message, created_at FROM processing_logs
            WHERE dataset_id = :d AND scene_id = :s AND stage = 'DOWNLOAD' AND message LIKE 'Downloading:%'
              AND created_at >= now() - interval '15 minutes' ORDER BY log_id"""),
            {"d": dataset_id, "s": cur["scene_id"]}).all()
        mb = [(int(m.group(1)), t) for msg, t in pts if (m := _DL.search(msg or ""))]
        if len(mb) >= 2 and mb[-1][1] > mb[0][1]:
            speed = (mb[-1][0] - mb[0][0]) / ((mb[-1][1] - mb[0][1]).total_seconds() / 60)

    # Perkiraan: per frame selesai bila sudah ada, kalau belum dari kecepatan unduh.
    elapsed = ((finished or _now()) - cycle).total_seconds()
    sec_per_frame = elapsed / len(frames_done) if frames_done else (
        DEFAULT_FRAME_MB / speed * 60 if speed and speed > 0 else None)
    running = finished is None
    eta = None
    if running and sec_per_frame and frames_left:
        eta = _now() + timedelta(seconds=sec_per_frame * frames_left)

    recent = sess.execute(text("""
        SELECT created_at AS at, 'LIVE' AS src, step AS stage, status, message, scene_date::text AS date
        FROM live_events WHERE area_id = :a AND created_at >= :c
        UNION ALL
        SELECT created_at, 'PIPELINE', stage, status, message, NULL FROM processing_logs
        WHERE dataset_id = :d AND created_at >= :c AND message NOT LIKE 'Downloading:%'
        ORDER BY 1 DESC LIMIT 25"""), {"a": area_id, "d": dataset_id, "c": cycle}).mappings().all()

    return {
        "running": running, "cycle_started_at": cycle, "cycle_finished_at": finished,
        "dates_total": len(targets), "dates_done": len(done), "dates_ok": len(ok),
        "dates_failed": len(done) - len(ok), "current_dates": current_dates,
        "first_date": targets[-1] if targets else None, "last_date": targets[0] if targets else None,
        "frames_total": frames_total, "frames_done": len(frames_done), "frames_left": frames_left,
        "frames_in_batch": pending_job_frames,
        "percent": round(len(frames_done) / frames_total * 100, 1) if frames_total else (100.0 if not running else 0.0),
        "current": current, "download_mb_per_min": round(speed, 1) if speed else None,
        "minutes_per_frame": round(sec_per_frame / 60, 1) if sec_per_frame else None,
        "eta": eta, "eta_basis": "frames" if frames_done else ("download_speed" if speed else None),
        "recent": [dict(r) for r in recent],
    }
