# tests/test_reports.py
"""Laporan periodik (PIPELINE.md §6): isi PDF (pypdf), registrasi, SUPERSEDED, FAILED, endpoint /reports."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pypdf import PdfReader
from sqlalchemy import text

from etl import alert_engine, hydromet_aggregate as ha
from etl import report_periodic as rp

WEEK = date(2024, 6, 3)          # Senin
EMPTY_WEEK = date(2019, 1, 7)    # Senin, tanpa data apa pun


@pytest.fixture(autouse=True)
def _reports_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    yield tmp_path / "reports"


def _pdf_text(path: Path) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)


@pytest.fixture(scope="module")
def week_data(db_client, synthetic_aoi, role_users):
    """Hujan 24h/72h tiap hari minggu WEEK + satu kejadian banjir terverifikasi."""
    vals = {synthetic_aoi["TST001"]: 10.0, synthetic_aoi["TST002"]: 60.0, synthetic_aoi["TST003"]: 0.0}
    with db_client.session() as sess:
        for i in range(7):
            d = WEEK + timedelta(days=i)
            ha.upsert_observations(sess, "RAIN_24H", d, {r: ha.ZonalResult(v, 1.0, 1) for r, v in vals.items()},
                                   run_type="L")
            ha.upsert_observations(sess, "RAIN_72H", d, {r: ha.ZonalResult(v * 3, 1.0, 1) for r, v in vals.items()},
                                   run_type="L")
            alert_engine.check_alerts(sess, d)
        sess.execute(text("""
            INSERT INTO disaster_events (disaster_type_id, region_id, event_date, description, info_source,
                                         is_verified, recorded_by)
            SELECT disaster_type_id, :r, :d, 'Banjir uji di kecamatan sintetis', 'GMLS', true, :u
            FROM disaster_types WHERE type_code = 'BANJIR'"""),
            {"r": synthetic_aoi["TST002"], "d": WEEK + timedelta(days=2), "u": role_users["ANALYST"]})
    return vals


class TestPeriods:
    def test_weekly_and_monthly(self):
        assert rp.period_for("HYDROMET_WEEKLY", WEEK) == (WEEK, date(2024, 6, 9))
        assert rp.period_for("DATAHEALTH_MONTHLY", date(2024, 2, 1)) == (date(2024, 2, 1), date(2024, 2, 29))
        with pytest.raises(ValueError):
            rp.period_for("HYDROMET_WEEKLY", date(2024, 6, 4))
        with pytest.raises(ValueError):
            rp.period_for("HYDROMET_MONTHLY", date(2024, 6, 2))

    def test_previous_period_in_wib(self):
        # Senin 2024-06-10 02:00 WIB = Minggu 19:00 UTC: minggu lalu tetap 3–9 Juni.
        now = datetime(2024, 6, 9, 19, 0, tzinfo=timezone.utc)
        assert rp.previous_period("HYDROMET_WEEKLY", now) == WEEK
        assert rp.previous_period("HYDROMET_MONTHLY", now) == date(2024, 5, 1)

    def test_number_format(self):
        assert rp.num(None) == "—" and rp.num(1234.5, 1, "mm") == "1.234,5 mm" and rp.pct(1, 0) == "—"


class TestHydrometReport:
    def test_content_matches_data(self, etl_db_client, week_data):
        res = rp.generate_report(etl_db_client, "HYDROMET_WEEKLY", WEEK)
        assert res.status == "READY", res.error
        body = _pdf_text(res.path)
        for i, title in enumerate(["Ringkasan eksekutif", "Hujan per kecamatan", "Grafik hujan", "Alert",
                                   "Kejadian bencana", "Evaluasi alert", "Vegetasi dan genangan",
                                   "Ringkasan Live", "Catatan keterbatasan"], start=1):
            assert f"{i}. {title}" in body
        assert "7 dari 7 hari" in body
        # Total AOI = rerata (70, 420, 0) = 163,3 mm; 7 hari lebat (60 mm di TST002).
        assert "163,3 mm" in body
        assert re.search(r"Hari lebat \(≥ 50 mm di ≥ 1\s+kecamatan\)\s+7\s", body)
        assert re.search(r"Jumlah alert\s+7\s", body)          # 7 hari x INFO 50 mm di TST002
        assert "FLOOD_RAIN24_HEAVY" in re.sub(r"\s", "", body)   # sel tabel membungkus baris
        assert "BANJIR" in body
        assert "Hanya dimuat di laporan bulanan" in body
        assert res.path.name == "HYDROMET_WEEKLY_2024-06-03.pdf"
        assert res.path.parent.name == "2024"

    def test_empty_period_has_no_invented_numbers(self, etl_db_client, synthetic_aoi):
        res = rp.generate_report(etl_db_client, "HYDROMET_WEEKLY", EMPTY_WEEK)
        assert res.status == "READY", res.error
        body = _pdf_text(res.path)
        assert "0 dari 7 hari" in body
        assert re.search(r"Total hujan AOI\s*—", body)
        assert "Tidak ada alert pada periode ini." in body
        assert "Grafik tidak dibuat" in body

    def test_monthly_includes_evaluation(self, etl_db_client, week_data):
        res = rp.generate_report(etl_db_client, "HYDROMET_MONTHLY", date(2024, 6, 1))
        body = _pdf_text(res.path)
        assert "Probability of detection" in body and "Hit" in body

    def test_regenerate_supersedes_and_keeps_file(self, etl_db_client, db_client, week_data):
        first = rp.generate_report(etl_db_client, "HYDROMET_WEEKLY", WEEK)
        second = rp.generate_report(etl_db_client, "HYDROMET_WEEKLY", WEEK)
        assert first.path.exists() and second.path.exists() and first.path != second.path
        with db_client.session() as sess:
            rows = dict(sess.execute(text("SELECT report_id, status FROM generated_reports WHERE report_id IN (:a, :b)"),
                                     {"a": first.report_id, "b": second.report_id}).all())
            ready = sess.scalar(text("""SELECT count(*) FROM generated_reports g JOIN report_types t USING (report_type_id)
                                        WHERE t.report_code = 'HYDROMET_WEEKLY' AND period_start = :s AND status = 'READY'"""),
                                {"s": WEEK})
            digest = sess.scalar(text("SELECT checksum_sha256 FROM generated_reports WHERE report_id = :r"),
                                 {"r": second.report_id})
        assert rows == {first.report_id: "SUPERSEDED", second.report_id: "READY"} and ready == 1
        assert digest == rp._sha256(second.path)

    def test_failure_is_recorded(self, etl_db_client, db_client, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("template rusak")
        monkeypatch.setattr(rp, "builder_for", lambda code: boom)
        res = rp.generate_report(etl_db_client, "HYDROMET_WEEKLY", date(2020, 1, 6))
        assert res.status == "FAILED" and res.path is None
        with db_client.session() as sess:
            row = sess.execute(text("SELECT status, error_message, file_size_bytes FROM generated_reports "
                                    "WHERE report_id = :r"), {"r": res.report_id}).one()
        assert row.status == "FAILED" and "template rusak" in row.error_message and row.file_size_bytes == 0


class TestDataHealthReport:
    def test_sections_and_runs_as_etl(self, etl_db_client, week_data):
        res = rp.generate_report(etl_db_client, "DATAHEALTH_WEEKLY", WEEK)
        assert res.status == "READY", res.error
        body = _pdf_text(res.path)
        for i, title in enumerate(["Skor kesehatan", "Kelengkapan per sumber", "Kualitas", "Pipeline", "Lineage",
                                   "Fusion", "Penyimpanan", "Unduhan"], start=1):
            assert f"{i}. {title}" in body
        assert "Tanpa nama pengguna" in body


class TestReportsApi:
    @pytest.fixture()
    def two_reports(self, etl_db_client, week_data):
        h = rp.generate_report(etl_db_client, "HYDROMET_WEEKLY", WEEK)
        d = rp.generate_report(etl_db_client, "DATAHEALTH_WEEKLY", WEEK)
        return h, d

    def test_audience_filtering(self, make_client, two_reports):
        h, d = two_reports
        codes = lambda c: {i["report_code"] for i in c.get("/api/reports?year=2024").json()["items"]}
        analyst, engineer = codes(make_client("ANALYST")), codes(make_client("DATA_ENGINEER"))
        assert "HYDROMET_WEEKLY" in analyst and analyst <= {"HYDROMET_WEEKLY", "HYDROMET_MONTHLY"}
        assert "DATAHEALTH_WEEKLY" in engineer and engineer <= {"DATAHEALTH_WEEKLY", "DATAHEALTH_MONTHLY"}
        assert "DATAHEALTH_WEEKLY" in codes(make_client("ADMIN")) and "HYDROMET_WEEKLY" in codes(make_client("ADMIN"))
        r = make_client("USER").get("/api/reports")
        assert r.status_code == 403 and r.json()["code"] == "REPORT_AUDIENCE"

    def test_download_and_hidden_404(self, make_client, two_reports, db_client):
        h, d = two_reports
        analyst = make_client("ANALYST")
        r = analyst.get(f"/api/reports/{h.report_id}/download")
        assert r.status_code == 200 and r.content[:4] == b"%PDF"
        assert analyst.get(f"/api/reports/{d.report_id}/download").status_code == 404   # bukan audiensnya
        with db_client.session() as sess:
            assert sess.scalar(text("""SELECT count(*) FROM user_activity_logs WHERE action = 'DOWNLOAD_REPORT'
                                       AND target_id = :r"""), {"r": h.report_id}) >= 1

    def test_regenerate_admin_only(self, make_client):
        body = {"report_code": "HYDROMET_WEEKLY", "period_start": "2024-06-04"}
        assert make_client("ANALYST").post("/api/reports/regenerate", json=body).status_code == 403
        r = make_client("ADMIN").post("/api/reports/regenerate", json=body)
        assert r.status_code == 400 and r.json()["code"] == "INVALID_PERIOD"
