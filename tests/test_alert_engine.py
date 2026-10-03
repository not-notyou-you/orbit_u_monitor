# tests/test_alert_engine.py
"""alert_rules x region_observations -> alert_events (PIPELINE.md §3.5) dan Job Hidromet per tanggal (§3)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import text

from etl import alert_engine, hydromet_aggregate as ha, hydromet_job as hj
from tests.conftest import write_synthetic_raster


def _obs(db_client, region_id, band, d, value, run="L"):
    with db_client.session() as sess:
        ha.upsert_observations(sess, band, d, {region_id: ha.ZonalResult(value, 1.0, 1)}, run_type=run)


def _alerts(db_client, d):
    with db_client.session() as sess:
        return sess.execute(text("""
            SELECT ar.pcode, ru.rule_code, a.severity, a.observed_value, a.threshold_value
            FROM alert_events a JOIN alert_rules ru USING (rule_id)
            JOIN administrative_regions ar ON ar.region_id = a.region_id
            WHERE a.observation_date = :d ORDER BY ar.pcode, a.threshold_value"""), {"d": d}).all()


class TestCheckAlerts:
    def test_bmkg_levels_fire_cumulatively(self, db_client, synthetic_aoi):
        d = date(2024, 3, 1)
        _obs(db_client, synthetic_aoi["TST001"], "RAIN_24H", d, 49.99)   # di bawah 50: tidak ada
        _obs(db_client, synthetic_aoi["TST002"], "RAIN_24H", d, 100.0)   # >= 50 dan >= 100
        _obs(db_client, synthetic_aoi["TST003"], "RAIN_24H", d, 151.0)   # ketiganya
        with db_client.session() as sess:
            created = alert_engine.check_alerts(sess, d)
        rows = _alerts(db_client, d)
        assert len(created) == 5
        assert [(r.pcode, r.severity) for r in rows] == [
            ("TST002", "INFO"), ("TST002", "WARNING"),
            ("TST003", "INFO"), ("TST003", "WARNING"), ("TST003", "CRITICAL")]
        # Nilai dan ambang disalin ke baris alert (catatan historis).
        assert float(rows[1].observed_value) == 100.0 and float(rows[1].threshold_value) == 100.0

    def test_idempotent_and_frozen_after_revision(self, db_client, synthetic_aoi):
        d = date(2024, 3, 2)
        rid = synthetic_aoi["TST002"]
        _obs(db_client, rid, "RAIN_24H", d, 60.0, "L")
        with db_client.session() as sess:
            assert len(alert_engine.check_alerts(sess, d)) == 1
            assert alert_engine.check_alerts(sess, d) == []          # ON CONFLICT DO NOTHING
        _obs(db_client, rid, "RAIN_24H", d, 20.0, "F")              # Final di bawah ambang
        with db_client.session() as sess:
            assert alert_engine.check_alerts(sess, d) == []
        rows = _alerts(db_client, d)
        assert len(rows) == 1 and float(rows[0].observed_value) == 60.0   # alert tidak dihapus/diubah

    def test_null_values_and_inactive_rules_do_not_fire(self, db_client, synthetic_aoi):
        d = date(2024, 3, 3)
        with db_client.session() as sess:
            ha.upsert_observations(sess, "RAIN_24H", d, {synthetic_aoi["TST001"]: ha.ZonalResult(None, 0.05, 1)})
        _obs(db_client, synthetic_aoi["TST002"], "RAIN_72H", d, 999.0)   # LANDSLIDE_RAIN72 nonaktif
        with db_client.session() as sess:
            assert alert_engine.check_alerts(sess, d) == []

    def test_region_outside_aoi_is_ignored(self, db_client, synthetic_aoi):
        d = date(2024, 3, 4)
        rid = synthetic_aoi["TST003"]
        _obs(db_client, rid, "RAIN_24H", d, 70.0)
        with db_client.session() as sess:
            sess.execute(text("UPDATE administrative_regions SET in_aoi = false WHERE region_id = :r"), {"r": rid})
            try:
                assert alert_engine.check_alerts(sess, d) == []
            finally:
                sess.execute(text("UPDATE administrative_regions SET in_aoi = true WHERE region_id = :r"), {"r": rid})

    def test_new_rule_less_than_comparator(self, db_client, synthetic_aoi):
        """Aturan baru (mis. kekeringan RAIN_30D < 20 mm) bekerja tanpa ubah kode."""
        d = date(2024, 3, 5)
        with db_client.session() as sess:
            sess.execute(text("""
                INSERT INTO alert_rules (rule_code, disaster_type_id, band_id, comparator, threshold_value,
                                         severity, reference_source)
                SELECT 'TEST_DROUGHT_30D', d.disaster_type_id, b.band_id, '<', 20, 'INFO', 'uji'
                FROM disaster_types d, spectral_bands b
                WHERE d.type_code = 'KEKERINGAN' AND b.band_code = 'RAIN_30D'"""))
        try:
            _obs(db_client, synthetic_aoi["TST001"], "RAIN_30D", d, 5.0)
            _obs(db_client, synthetic_aoi["TST002"], "RAIN_30D", d, 25.0)
            with db_client.session() as sess:
                assert len(alert_engine.check_alerts(sess, d)) == 1
            assert [r.pcode for r in _alerts(db_client, d)] == ["TST001"]
        finally:
            with db_client.session() as sess:
                sess.execute(text("DELETE FROM alert_events WHERE rule_id IN "
                                  "(SELECT rule_id FROM alert_rules WHERE rule_code = 'TEST_DROUGHT_30D')"))
                sess.execute(text("DELETE FROM alert_rules WHERE rule_code = 'TEST_DROUGHT_30D'"))

    def test_bmkg_thresholds_for_live(self, db_client):
        with db_client.session() as sess:
            assert alert_engine.bmkg_rain24_thresholds(sess) == [(50.0, "INFO"), (100.0, "WARNING"),
                                                                 (150.0, "CRITICAL")]


# --- Job Hidromet dengan pengambil tiruan --------------------------------------

def _fake_gpm(tmp_path: Path, values_24h: float, run: str = "L", calls: list | None = None):
    def fetch(ctx, d, rebuild):
        if calls is not None:
            calls.append((d, rebuild))
        layers = []
        for window, band in hj.GPM_BANDS.items():
            mult = {"24h": 1, "72h": 2, "7d": 3, "30d": 4}[window]
            p = write_synthetic_raster(tmp_path / f"{d:%Y%m%d}_{run}" / f"gpm_rain_{window}.tif",
                                       np.full((4, 4), values_24h * mult, dtype="float32"),
                                       tags={"IMERG_RUNS": run})
            layers.append(hj.Layer(band, p, run, None))
        return layers
    return fetch


def _fake_modis(tmp_path: Path):
    def fetch(ctx, d):
        flood = np.full((4, 4), 3, dtype="uint8")
        ndvi = np.full((4, 4), 0.6, dtype="float32")
        return [hj.Layer("FLOOD", write_synthetic_raster(tmp_path / f"m{d:%Y%m%d}" / "flood.tif", flood,
                                                         nodata=255, dtype="uint8")),
                hj.Layer("NDVI", write_synthetic_raster(tmp_path / f"m{d:%Y%m%d}" / "ndvi.tif", ndvi,
                                                        nodata=None))]
    return fetch


def _job_status(db_client, dataset_id, d):
    with db_client.session() as sess:
        return sess.scalar(text("""SELECT status FROM dataset_jobs WHERE dataset_id = :ds
            AND job_type = 'HYDROMET_DAILY' AND date_range_start = :d ORDER BY job_id DESC LIMIT 1"""),
            {"ds": dataset_id, "d": d})


class TestRunDay:
    def test_completed_day_writes_observations_and_alerts(self, db_client, synthetic_aoi, tmp_path):
        d = date(2024, 4, 1)
        res = hj.run_day(db_client, d, fetchers=hj.Fetchers(_fake_gpm(tmp_path, 60.0), _fake_modis(tmp_path)))
        assert res.status == "COMPLETED", res.message
        assert res.gpm_run == "L"
        assert res.observations == 3 * 4 + 3 * 2          # 3 kecamatan x (4 GPM + 2 MODIS)
        assert len(res.alerts) == 3                       # 60 mm >= 50 di 3 kecamatan
        assert res.modis_bands == ["FLOOD", "NDVI"]
        assert _job_status(db_client, synthetic_aoi["dataset_id"], d) == "COMPLETED"
        with db_client.session() as sess:
            vals = dict(sess.execute(text("""SELECT b.band_code, avg(o.value) FROM region_observations o
                JOIN spectral_bands b USING (band_id) WHERE o.obs_date = :d GROUP BY b.band_code"""), {"d": d}).all())
            stages = sess.scalars(text("""SELECT s.stage_name FROM processing_jobs j JOIN processing_stages s
                USING (stage_id) WHERE j.parameters_json->>'job_id' = :j ORDER BY j.job_id"""),
                {"j": str(res.job_id)}).all()
        assert float(vals["RAIN_24H"]) == pytest.approx(60.0)
        assert float(vals["RAIN_30D"]) == pytest.approx(240.0)
        assert float(vals["FLOOD"]) == pytest.approx(100.0)
        assert float(vals["NDVI"]) == pytest.approx(0.6, abs=1e-4)
        assert stages == ["HYDROMET_AGGREGATE", "ALERT_CHECK", "HYDROMET_AGGREGATE"]

    def test_waiting_upstream_then_failed_after_max_days(self, db_client, synthetic_aoi, monkeypatch):
        def not_ready(ctx, d, rebuild):
            raise hj.UpstreamNotReady("no IMERG product (F/L/E)")
        recent = hj.utc_today() - timedelta(days=1)
        res = hj.run_day(db_client, recent, fetchers=hj.Fetchers(not_ready, None))
        assert res.status == "WAITING_UPSTREAM"
        assert recent in hj.waiting_dates(db_client)
        old = hj.utc_today() - timedelta(days=10)
        assert hj.run_day(db_client, old, fetchers=hj.Fetchers(not_ready, None)).status == "FAILED"
        assert _job_status(db_client, synthetic_aoi["dataset_id"], old) == "FAILED"
        # Percobaan berikutnya memakai baris dataset_jobs yang sama.
        with db_client.session() as sess:
            n = sess.scalar(text("SELECT count(*) FROM dataset_jobs WHERE job_type = 'HYDROMET_DAILY' "
                                 "AND date_range_start = :d"), {"d": recent})
        hj.run_day(db_client, recent, fetchers=hj.Fetchers(not_ready, None))
        with db_client.session() as sess:
            assert sess.scalar(text("SELECT count(*) FROM dataset_jobs WHERE job_type = 'HYDROMET_DAILY' "
                                    "AND date_range_start = :d"), {"d": recent}) == n

    def test_modis_failure_is_not_fatal(self, db_client, synthetic_aoi, tmp_path):
        def broken(ctx, d):
            raise RuntimeError("LAADS 503")
        res = hj.run_day(db_client, date(2024, 4, 2), fetchers=hj.Fetchers(_fake_gpm(tmp_path, 5.0), broken))
        assert res.status == "COMPLETED" and "MODIS failed" in res.message

    def test_pending_dates_resume(self, db_client, synthetic_aoi, tmp_path):
        a, b = date(2024, 5, 1), date(2024, 5, 4)
        hj.run_day(db_client, date(2024, 5, 2), fetchers=hj.Fetchers(_fake_gpm(tmp_path, 1.0), None))
        assert hj.pending_dates(db_client, a, b) == [date(2024, 5, 1), date(2024, 5, 3), date(2024, 5, 4)]

    def test_late_to_final_refresh(self, db_client, synthetic_aoi, tmp_path):
        d = hj.utc_today() - timedelta(days=100)
        hj.run_day(db_client, d, fetchers=hj.Fetchers(_fake_gpm(tmp_path, 70.0, "L"), None))
        calls: list = []
        out = hj.refresh_late_to_final(
            db_client, fetchers=hj.Fetchers(_fake_gpm(tmp_path, 10.0, "F", calls), None),
            is_final_published=lambda ctx, day: day == d)
        assert [r.obs_date for r in out] == [d] and calls == [(d, True)]
        with db_client.session() as sess:
            row = sess.execute(text("""SELECT o.value, o.run_type FROM region_observations o
                JOIN spectral_bands b USING (band_id) WHERE b.band_code = 'RAIN_24H' AND o.obs_date = :d
                AND o.region_id = :r"""), {"d": d, "r": synthetic_aoi["TST001"]}).one()
            n_alerts = sess.scalar(text("SELECT count(*) FROM alert_events WHERE observation_date = :d"), {"d": d})
        assert float(row.value) == pytest.approx(10.0) and row.run_type == "F"
        assert n_alerts == 3                        # alert Late (70 mm) tetap ada
        assert d not in hj.non_final_dates(db_client)

    def test_runs_as_monitor_etl(self, etl_db_client, synthetic_aoi, tmp_path):
        """Scheduler/backfill terkoneksi sebagai monitor_etl (DATABASE §8.1):
        GRANT-nya harus cukup untuk seluruh tahap."""
        res = hj.run_day(etl_db_client, date(2024, 4, 3),
                         fetchers=hj.Fetchers(_fake_gpm(tmp_path, 120.0), _fake_modis(tmp_path)))
        assert res.status == "COMPLETED", res.message
        assert len(res.alerts) == 6
