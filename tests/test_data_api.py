# tests/test_data_api.py
"""Halaman Data, log per halaman, dan laporan rentang bebas (M56)."""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from etl import hydromet_aggregate as ha


def _today():
    return datetime.now(timezone.utc).date()


@pytest.fixture
def granules(db_client, synthetic_aoi):
    """Dua granule GPM dan satu MODIS milik ROI AOI."""
    d = _today() - timedelta(days=30)
    ids = {}
    with db_client.session() as sess:
        for key, src, short, day in (("gpm1", "GPM", "GPM_3IMERGDL", d), ("gpm2", "GPM", "GPM_3IMERGDL", d - timedelta(days=1)),
                                     ("modis", "MODIS", "MOD09A1", d)):
            ids[key] = sess.scalar(text("""
                INSERT INTO nasa_scenes (source, tile_id, product_short_name, acquisition_date, region_id, run_type)
                VALUES (:s, :t, :p, :d, :r, CASE WHEN :s = 'GPM' THEN 'L' END)
                ON CONFLICT (source, tile_id, product_short_name, acquisition_date) DO UPDATE SET is_valid = true,
                    invalid_reason = NULL, invalidated_at = NULL, invalidated_by = NULL
                RETURNING nasa_scene_id"""), {"s": src, "t": f"T{time.time_ns() % 10**6}", "p": short, "d": day,
                                              "r": synthetic_aoi["roi_id"]})
    return ids


class TestItems:
    def test_summary(self, make_client, granules):
        body = make_client("DATA_ENGINEER").get("/api/data/summary").json()
        by = {s["key"]: s for s in body["sources"]}
        assert set(by) == {"s1", "modis", "gpm"} and by["gpm"]["n_total"] >= 2 and by["modis"]["n_total"] >= 1
        assert "recent_runs" in body and "datasets" in body

    def test_list_and_soft_delete_restore(self, make_client, granules, db_client):
        de = make_client("DATA_ENGINEER")
        items = de.get("/api/data/gpm/items?limit=500").json()
        assert granules["gpm1"] in {i["id"] for i in items["items"]}
        assert all(i["run_type"] in ("L", "F", "E", None) for i in items["items"])
        r = de.patch(f"/api/data/gpm/items/{granules['gpm1']}", json={"is_valid": False})
        assert (r.status_code, r.json()["code"]) == (400, "REASON_REQUIRED")
        r = de.patch(f"/api/data/gpm/items/{granules['gpm1']}", json={"is_valid": False, "reason": "granule rusak"})
        assert r.status_code == 200 and r.json()["is_valid"] is False
        invalid = de.get("/api/data/gpm/items?status=invalid&limit=500").json()["items"]
        assert granules["gpm1"] in {i["id"] for i in invalid}
        assert de.patch(f"/api/data/gpm/items/{granules['gpm1']}", json={"is_valid": True}).json()["is_valid"] is True
        # Granule MODIS tidak bisa diubah lewat jalur GPM.
        assert de.patch(f"/api/data/gpm/items/{granules['modis']}", json={"is_valid": True}).status_code == 404
        with db_client.session() as sess:
            n = sess.scalar(text("""SELECT count(*) FROM user_activity_logs WHERE action = 'SCENE_UPDATE'
                                    AND target_id = :i"""), {"i": granules["gpm1"]})
        assert n == 3 or n >= 2
        assert de.get("/api/data/landsat/items").json()["code"] == "INVALID_SOURCE"

    def test_analyst_cannot_touch_data(self, make_client, granules):
        r = make_client("ANALYST").patch(f"/api/data/gpm/items/{granules['gpm2']}",
                                         json={"is_valid": False, "reason": "x"})
        assert (r.status_code, r.json()["code"]) == (403, "ROLE_FORBIDDEN")


class TestBackfill:
    @pytest.fixture(autouse=True)
    def _clean_runs(self):
        from etl import backfill_runs as br
        br.reset()
        yield
        for _ in range(100):
            if not br.running():
                break
            time.sleep(0.05)
        br.reset()

    def test_gpm_backfill_logs_are_visible(self, make_client, synthetic_aoi, monkeypatch, db_client):
        from etl import hydromet_job as hj
        calls = {}

        def fake_backfill(db, a, b, *, modis=True, echo=print, pending_fn=None, **kw):
            calls.update(modis=modis, pending_fn=pending_fn)
            echo("[INFO] 2 days in range, 0 already done, 2 to do")
            echo(f"[1/2] {a} COMPLETED (1s) ok")
            echo(f"[2/2] {b} COMPLETED (1s) ok")
            return {"COMPLETED": 2, "FAILED": 0, "locked": False}

        monkeypatch.setattr(hj, "backfill", fake_backfill)
        de = make_client("DATA_ENGINEER")
        a, b = (_today() - timedelta(days=12)).isoformat(), (_today() - timedelta(days=11)).isoformat()
        r = de.post("/api/data/gpm/backfill", json={"date_from": a, "date_to": b})
        assert r.status_code == 202, r.text
        run_id = r.json()["run"]["run_id"]
        for _ in range(100):
            run = de.get(f"/api/data/backfill/runs/{run_id}").json()
            if run["status"] != "RUNNING":
                break
            time.sleep(0.05)
        assert run["status"] == "COMPLETED" and (run["done"], run["total"]) == (2, 2)
        assert any("[2/2]" in line for line in run["lines"]) and run["lines"][-1].endswith("[END] COMPLETED")
        assert calls == {"modis": False, "pending_fn": None}
        tail = de.get(f"/api/data/backfill/runs/{run_id}?since={run['n_lines'] - 1}").json()["lines"]
        assert len(tail) == 1
        status = de.get("/api/data/gpm/backfill").json()
        assert status["runs"][0]["run_id"] == run_id and "days" in status
        with db_client.session() as sess:
            assert sess.scalar(text("SELECT count(*) FROM v_log_data WHERE action = 'BACKFILL_START'")) >= 1

    def test_modis_backfill_uses_missing_dates(self, make_client, synthetic_aoi, monkeypatch):
        from etl import hydromet_job as hj
        seen = {}
        monkeypatch.setattr(hj, "backfill", lambda db, a, b, **kw: seen.update(kw) or {"COMPLETED": 0, "locked": False})
        de = make_client("DATA_ENGINEER")
        d = (_today() - timedelta(days=12)).isoformat()
        assert de.post("/api/data/modis/backfill", json={"date_from": d, "date_to": d}).status_code == 202
        for _ in range(100):
            if seen:
                break
            time.sleep(0.05)
        assert seen["modis"] is True and seen["pending_fn"] is hj.modis_missing_dates

    def test_range_limit_and_conflict(self, make_client, synthetic_aoi, monkeypatch):
        from etl import backfill_runs as br
        from etl import hydromet_job as hj
        de = make_client("DATA_ENGINEER")
        r = de.post("/api/data/gpm/backfill", json={"date_from": "2024-01-01", "date_to": "2025-06-01"})
        assert r.status_code == 422
        gate = {"go": False}

        def slow(db, a, b, **kw):
            while not gate["go"]:
                time.sleep(0.02)
            return {"COMPLETED": 1, "locked": False}
        monkeypatch.setattr(hj, "backfill", slow)
        d = (_today() - timedelta(days=12)).isoformat()
        assert de.post("/api/data/gpm/backfill", json={"date_from": d, "date_to": d}).status_code == 202
        r = de.post("/api/data/modis/backfill", json={"date_from": d, "date_to": d})
        assert (r.status_code, r.json()["code"]) == (409, "BACKFILL_RUNNING")
        gate["go"] = True

    def test_s1_backfill_creates_dataset(self, make_client, synthetic_aoi, monkeypatch):
        from etl.dataset_manager import DatasetManager
        monkeypatch.setattr(DatasetManager, "_spawn_job_runner", lambda self, job_id: None)
        de = make_client("DATA_ENGINEER")
        a, b = (_today() - timedelta(days=40)).isoformat(), (_today() - timedelta(days=30)).isoformat()
        r = de.post("/api/data/s1/backfill", json={"date_from": a, "date_to": b})
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["kind"] == "DATASET" and body["dataset_id"]
        listed = de.get("/api/data/s1/backfill").json()["datasets"]
        assert body["dataset_id"] in {d["dataset_id"] for d in listed}

    def test_modis_missing_dates(self, db_client, synthetic_aoi):
        from etl import hydromet_job as hj
        base = _today() - timedelta(days=200)
        with db_client.session() as sess:
            ha.upsert_observations(sess, "NDVI", base, {synthetic_aoi["TST001"]: ha.ZonalResult(0.5, 1.0, 1)})
        missing = hj.modis_missing_dates(db_client, base - timedelta(days=1), base + timedelta(days=1))
        assert missing == [base - timedelta(days=1), base + timedelta(days=1)]


class TestEda:
    def test_gpm_eda(self, make_client, synthetic_aoi, db_client):
        base = _today() - timedelta(days=300)
        with db_client.session() as sess:
            for i in range(5):
                d = base + timedelta(days=i)
                ha.upsert_observations(sess, "RAIN_24H", d, {synthetic_aoi["TST001"]: ha.ZonalResult(10.0 * i, 1.0, 1),
                                                             synthetic_aoi["TST002"]: ha.ZonalResult(5.0 * i, 0.8, 1)},
                                       run_type="F")
                ha.upsert_observations(sess, "RAIN_72H", d, {synthetic_aoi["TST001"]: ha.ZonalResult(30.0 * i, 1.0, 1)},
                                       run_type="F")
        body = make_client("DATA_ENGINEER").get(
            f"/api/data/eda?source=gpm&date_from={base}&date_to={base + timedelta(days=4)}").json()
        assert body["n_days"] == 5 and body["n_regions"] == 3
        rain = next(v for v in body["variables"] if v["band_code"] == "RAIN_24H")
        assert rain["n"] == 10 and rain["expected"] == 15 and rain["missing_pct"] == pytest.approx(33.33, abs=0.01)
        assert rain["max"] == 40.0 and rain["histogram"]
        corr = body["correlation"]
        i, j = corr["variables"].index("RAIN_24H"), corr["variables"].index("RAIN_72H")
        assert corr["matrix"][i][j]["r"] == pytest.approx(1.0) and corr["matrix"][i][j]["n"] == 5
        assert len(body["completeness"]) == 5 and body["run_types"]["F"] >= 15

    def test_s1_eda_and_validation(self, make_client):
        de = make_client("DATA_ENGINEER")
        body = de.get(f"/api/data/eda?source=s1&date_from={_today() - timedelta(days=30)}&date_to={_today()}").json()
        assert body["unit_of_analysis"].startswith("scene") and "orbits" in body
        r = de.get(f"/api/data/eda?source=gpm&date_from={_today()}&date_to={_today() - timedelta(days=3)}")
        assert (r.status_code, r.json()["code"]) == (400, "INVALID_DATE_RANGE")
        assert make_client("ANALYST").get(f"/api/data/eda?source=gpm&date_from={_today()}&date_to={_today()}").status_code == 403


def test_eda_describe_and_correlation():
    from etl import eda
    d = eda.describe([1.0, 2.0, 3.0, 4.0, 100.0, None], expected=8)
    assert d["n"] == 5 and d["n_null"] == 1 and d["missing"] == 3 and d["outliers"] == 1
    assert eda.describe([None])["mean"] is None
    c = eda.correlation({(1,): {"a": 1, "b": 2}, (2,): {"a": 2, "b": 4}, (3,): {"a": 3, "b": 6}, (4,): {"a": 4}},
                        ["a", "b"])
    assert c["matrix"][0][1] == {"r": 1.0, "n": 3}


class TestLogs:
    def test_role_scoped_logs(self, make_client, synthetic_aoi, db_client):
        analyst = make_client("ANALYST")
        r = analyst.post("/api/disasters", json={
            "disaster_type_code": "BANJIR", "region_id": synthetic_aoi["TST003"], "event_date": "2025-02-01",
            "info_source": "GMLS", "description": "Kejadian untuk uji log halaman."})
        assert r.status_code == 201
        ev = r.json()["event_id"]
        items = analyst.get("/api/logs/kejadian?limit=500").json()["items"]
        assert any(i["target_type"] == "disaster_events" and i["target_id"] == str(ev) and i["action"] == "INSERT"
                   for i in items)
        assert make_client("DATA_ENGINEER").get("/api/logs/kejadian").status_code == 403
        assert analyst.get("/api/logs/data").status_code == 403
        de_items = make_client("DATA_ENGINEER").get("/api/logs/data?limit=500").json()["items"]
        assert all(i["target_type"] != "disaster_events" for i in de_items)
        admin = make_client("ADMIN")
        assert admin.get("/api/logs/data").status_code == 200 and admin.get("/api/logs/kejadian").status_code == 200
        r = analyst.get("/api/logs/kejadian?date_from=2025-02-02&date_to=2025-02-01")
        assert r.json()["code"] == "INVALID_DATE_RANGE"

    def test_admin_login_log_includes_registration(self, make_client):
        from api.routes.auth import register_rate_limiter
        from tests.conftest import TEST_PASSWORD
        register_rate_limiter.reset()
        name = f"logreg_{time.time_ns() % 10**7}"
        assert make_client(None).post("/api/auth/register", json={
            "email": f"{name}@example.org", "username": name, "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD}).status_code == 201
        items = make_client("ADMIN").get("/api/admin/logs/login?limit=200").json()["items"]
        assert any(i["action"] == "REGISTER" and i["username"] == name for i in items)


class TestCustomReport:
    def test_audience_and_pdf(self, make_client, synthetic_aoi):
        a, b = (_today() - timedelta(days=20)).isoformat(), (_today() - timedelta(days=10)).isoformat()
        r = make_client("ANALYST").get(f"/api/reports/custom.pdf?kind=HYDROMET&date_from={a}&date_to={b}")
        assert r.status_code == 200, r.text
        assert r.content[:4] == b"%PDF" and "HYDROMET_" in r.headers["content-disposition"]
        r = make_client("ANALYST").get(f"/api/reports/custom.pdf?kind=DATAHEALTH&date_from={a}&date_to={b}")
        assert (r.status_code, r.json()["code"]) == (403, "REPORT_AUDIENCE")
        r = make_client("DATA_ENGINEER").get(f"/api/reports/custom.pdf?kind=DATAHEALTH&date_from={a}&date_to={b}")
        assert r.status_code == 200, r.text
        r = make_client("USER").get(f"/api/reports/custom.pdf?kind=HYDROMET&date_from={a}&date_to={b}")
        assert r.json()["code"] == "REPORT_AUDIENCE"
        r = make_client("ADMIN").get(f"/api/reports/custom.pdf?kind=HYDROMET&date_from=2024-01-01&date_to=2025-06-01")
        assert r.json()["code"] == "INVALID_DATE_RANGE"


class TestExternalBackfill:
    """Backfill yang berjalan di proses lain (skrip/scheduler) memegang kunci
    advisory "hydromet"; halaman Data harus mendeteksinya dari kunci itu."""

    def test_lock_held_elsewhere_is_detected(self, make_client, synthetic_aoi, db_client):
        from etl import backfill_runs as br
        from etl.advisory_lock import advisory_lock
        br.reset()
        de = make_client("DATA_ENGINEER")
        assert de.get("/api/data/gpm/backfill").json()["hydromet"]["locked"] is False
        with advisory_lock(db_client, "hydromet") as got:
            assert got
            body = de.get("/api/data/gpm/backfill").json()
            assert body["hydromet"]["locked"] is True and body["hydromet"]["external"] is True
            summ = {s["key"]: s["backfill_running"] for s in de.get("/api/data/summary").json()["sources"]}
            assert summ == {"s1": False, "modis": True, "gpm": True}
            d = (_today() - timedelta(days=12)).isoformat()
            r = de.post("/api/data/gpm/backfill", json={"date_from": d, "date_to": d})
            assert (r.status_code, r.json()["code"]) == (409, "BACKFILL_RUNNING")
        assert de.get("/api/data/gpm/backfill").json()["hydromet"]["locked"] is False

    def test_interrupted_processing_day_is_stale(self, make_client, synthetic_aoi, db_client):
        day = _today() - timedelta(days=700)
        with db_client.session() as sess:
            sess.execute(text("""INSERT INTO dataset_jobs (dataset_id, job_type, status, date_range_start, date_range_end, started_at)
                                 VALUES (:d, 'HYDROMET_DAILY', 'PROCESSING', :x, :x, now() - interval '2 days')"""),
                         {"d": synthetic_aoi["dataset_id"], "x": day})
        body = make_client("DATA_ENGINEER").get("/api/data/gpm/backfill?days=366").json()
        assert day.isoformat() in body["stale_dates"]
