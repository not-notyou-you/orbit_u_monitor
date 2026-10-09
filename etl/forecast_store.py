# etl/forecast_store.py
"""Forecast tersimpan (M62, PIPELINE.md §14): dihitung saat data baru masuk,
dibaca halaman Forecast tanpa menghitung ulang.

Deret: setiap band per kecamatan (band_catalog.REGION_BANDS) × (rerata AOI +
setiap kecamatan AOI). Setiap band punya **cap data** = max(computed_at)
region_observations band itu dan max(updated_at) live_scenes. refresh()
hanya menghitung deret yang cap tersimpannya berbeda dari cap sekarang, jadi
memanggilnya setelah setiap job murah: band yang tidak berubah dilewati.

Dipanggil di akhir Job Hidromet (harian, Late->Final, backfill), siklus Live
(Sentinel-1), dan job penjadwal ``forecast_refresh`` tiap 6 jam sebagai jaring
pengaman. Satu pekerja sekaligus lewat advisory lock ``forecast``. Riwayat
lebih dari 365 hari dihapus.

Manual:  python -m etl.forecast_store [--force]
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from etl import band_catalog as bc
from etl import band_forecast as bf

logger = logging.getLogger(__name__)

HISTORY_DAYS = 365
BANDS = bc.REGION_BANDS


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _num(v):
    return None if v is None else float(v)


def band_stamp(sess: Session, band: str) -> datetime:
    return sess.scalar(text("""
        SELECT greatest(
            (SELECT max(o.computed_at) FROM region_observations o JOIN spectral_bands b USING (band_id)
             WHERE b.band_code = :b),
            (SELECT max(updated_at) FROM live_scenes),
            'epoch'::timestamptz)"""), {"b": band})


def aoi_points(sess: Session, band: str, end: date) -> list[tuple[date, float | None]]:
    """Seluruh riwayat rerata AOI satu band, sumbernya sama dengan /diagram/latest:
    angka harian per kecamatan, dan rerata scene Live untuk hari tanpa angka harian."""
    vals = {d: _num(v) for d, v in sess.execute(text("""
        SELECT s.scene_date, avg(m.value)
        FROM live_scene_metrics m
        JOIN live_scenes s ON s.live_scene_id = m.live_scene_id
        JOIN live_areas a ON a.area_id = s.area_id AND a.deleted_at IS NULL
        JOIN spectral_bands b ON b.band_id = m.band_id
        WHERE m.metric_name = 'mean' AND b.band_code = :b AND s.scene_date <= :t
          AND s.status IN ('READY', 'PARTIAL', 'DELETED')
        GROUP BY 1"""), {"b": band, "t": end}).all()}
    vals.update({d: _num(v) for d, v in sess.execute(text("""
        SELECT o.obs_date, avg(o.value)
        FROM region_observations o JOIN spectral_bands b USING (band_id)
        JOIN administrative_regions r ON r.region_id = o.region_id AND r.in_aoi
        WHERE b.band_code = :b AND o.obs_date <= :t GROUP BY 1"""), {"b": band, "t": end}).all()})
    return list(vals.items())


def region_points(sess: Session, band: str, ids: list[int], end: date) -> list[tuple[date, float | None]]:
    """Seluruh riwayat satu band untuk satu kecamatan, atau rerata harian beberapa kecamatan."""
    return [(d, _num(v)) for d, v in sess.execute(text("""
        SELECT o.obs_date, avg(o.value) FROM region_observations o JOIN spectral_bands b USING (band_id)
        WHERE b.band_code = :b AND o.region_id = ANY(:r) AND o.obs_date <= :t GROUP BY 1"""),
        {"b": band, "r": ids, "t": end}).all()]


def save(sess: Session, band: str, region_id: int | None, stamp: datetime, end: date,
         fc: dict, duration_ms: int) -> int:
    bt = fc.get("backtest") or {}
    fid = sess.scalar(text("""
        INSERT INTO band_forecasts (band_id, region_id, data_stamp, end_date, history_from, last_obs_date,
                                    n_obs, horizon, model, confidence, backtest_origins, mae, mae_naive,
                                    skill, notes, duration_ms)
        SELECT band_id, :r, :st, :end, :hf, :lo, :n, :h, :m, :c, :o, :mae, :mn, :sk, :notes, :ms
        FROM spectral_bands WHERE band_code = :b
        ON CONFLICT (band_id, (COALESCE(region_id, 0)), data_stamp) DO NOTHING
        RETURNING forecast_id"""),
        {"b": band, "r": region_id, "st": stamp, "end": end, "hf": fc["history_from"], "lo": fc["last_obs_date"],
         "n": fc["n_obs"], "h": fc["horizon"], "m": fc["model"], "c": fc["confidence"],
         "o": bt.get("origins"), "mae": bt.get("mae"), "mn": bt.get("mae_naive"), "sk": bt.get("skill"),
         "notes": "\n".join(fc["notes"]) or None, "ms": duration_ms})
    if fid is None:
        return 0
    if fc["points"]:
        sess.execute(text("""INSERT INTO band_forecast_points (forecast_id, step, target_date, mean, lo, hi)
                             VALUES (:f, :k, :x, :mean, :lo, :hi)"""),
                     [{"f": fid, "k": k, **p} for k, p in enumerate(fc["points"], start=1)])
    if bt.get("mae_by_model"):
        sess.execute(text("INSERT INTO band_forecast_scores (forecast_id, model, mae) VALUES (:f, :m, :v)"),
                     [{"f": fid, "m": m, "v": v} for m, v in bt["mae_by_model"].items()])
    return fid


def latest(sess: Session, band: str, region_id: int | None) -> dict | None:
    """Forecast tersimpan terbaru satu deret, dalam bentuk yang sama dengan
    band_forecast.forecast() (+ data_stamp, computed_at, stored)."""
    row = sess.execute(text("""
        SELECT f.* FROM band_forecasts f JOIN spectral_bands b USING (band_id)
        WHERE b.band_code = :b AND f.region_id IS NOT DISTINCT FROM :r
        ORDER BY f.computed_at DESC, f.forecast_id DESC LIMIT 1"""), {"b": band, "r": region_id}).mappings().first()
    if row is None:
        return None
    fid = row["forecast_id"]
    pts = [{"x": d.isoformat(), "mean": float(m), "lo": float(lo), "hi": float(hi)} for d, m, lo, hi in sess.execute(text(
        "SELECT target_date, mean, lo, hi FROM band_forecast_points WHERE forecast_id = :f ORDER BY step"), {"f": fid})]
    scores = {m: float(v) for m, v in sess.execute(text(
        "SELECT model, mae FROM band_forecast_scores WHERE forecast_id = :f"), {"f": fid})}
    backtest = None if row["backtest_origins"] is None else {
        "origins": row["backtest_origins"], "horizon": row["horizon"], "mae": _num(row["mae"]),
        "mae_naive": _num(row["mae_naive"]), "skill": _num(row["skill"]), "mae_by_model": scores}
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {"band_code": band, "horizon": row["horizon"], "interval": bf.INTERVAL, "n_obs": row["n_obs"],
            "history_from": iso(row["history_from"]), "last_obs_date": iso(row["last_obs_date"]),
            "model": row["model"], "model_label": bf.MODEL_LABELS.get(row["model"]),
            "confidence": row["confidence"], "backtest": backtest, "points": pts,
            "notes": row["notes"].split("\n") if row["notes"] else [],
            "data_stamp": row["data_stamp"], "end_date": row["end_date"], "computed_at": row["computed_at"],
            "stored": True}


def refresh(db, *, force: bool = False, bands: tuple[str, ...] = BANDS, echo=None) -> dict:
    """Hitung ulang deret yang basi (cap data berubah) dan simpan. Tidak
    melempar galat per deret: deret yang gagal dicatat dan dilewati."""
    from etl.advisory_lock import advisory_lock

    summary = {"computed": 0, "skipped": 0, "failed": 0, "locked": False, "seconds": 0.0}
    t0 = time.monotonic()
    with advisory_lock(db, "forecast") as got:
        if not got:
            summary["locked"] = True
            return summary
        end = _today()
        with db.session() as sess:
            regions = list(sess.scalars(text(
                "SELECT region_id FROM administrative_regions WHERE in_aoi AND admin_level = 3 ORDER BY region_id")))
        for band in bands:
            with db.session() as sess:
                stamp = band_stamp(sess, band)
                have = {r: s for r, s in sess.execute(text("""
                    SELECT DISTINCT ON (f.region_id) f.region_id, f.data_stamp
                    FROM band_forecasts f JOIN spectral_bands b USING (band_id) WHERE b.band_code = :b
                    ORDER BY f.region_id, f.computed_at DESC"""), {"b": band}).all()}
            for rid in [None] + regions:
                if not force and have.get(rid) == stamp:
                    summary["skipped"] += 1
                    continue
                try:
                    with db.session() as sess:
                        t = time.monotonic()
                        pts = aoi_points(sess, band, end) if rid is None else region_points(sess, band, [rid], end)
                        fc = bf.forecast(pts, band)
                        save(sess, band, rid, stamp, end, fc, int((time.monotonic() - t) * 1000))
                    summary["computed"] += 1
                except Exception:
                    summary["failed"] += 1
                    logger.exception("[FORECAST] %s region=%s gagal", band, rid)
            if echo:
                echo(f"[FORECAST] {band}: {summary}")
        with db.session() as sess:
            sess.execute(text("DELETE FROM band_forecasts WHERE computed_at < now() - make_interval(days => :d)"),
                         {"d": HISTORY_DAYS})
    summary["seconds"] = round(time.monotonic() - t0, 1)
    logger.info("[FORECAST] %s", summary)
    return summary


def refresh_quietly(db) -> dict | None:
    """Untuk dipanggil di akhir job lain: kegagalan forecast tidak boleh
    menggagalkan job data."""
    if db is None:
        return None
    try:
        return refresh(db)
    except Exception:
        logger.exception("[FORECAST] refresh gagal (tidak fatal)")
        return None


def main(argv: list[str] | None = None) -> int:
    import argparse
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    from etl.database_client import DatabaseClient

    p = argparse.ArgumentParser(description="Compute and store 15-day band forecasts (M62)")
    p.add_argument("--force", action="store_true", help="recompute every series even if its data did not change")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(refresh(DatabaseClient.from_env("etl"), force=args.force, echo=print))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
