# tests/test_monitor_api.py
"""Endpoint Tahap 3 (INTERFACE.md §4.2, §4.4–4.6, §4.9) + impor CSV kejadian + scheduler."""

from __future__ import annotations

import threading
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from etl import alert_engine, hydromet_aggregate as ha


def _today():
    return datetime.now(timezone.utc).date()


@pytest.fixture(scope="module")
def recent_obs(db_client, synthetic_aoi):
    """RAIN_24H/72H/7D/30D lengkap untuk 3 kecamatan pada 'kemarin' + alert."""
    d = _today() - timedelta(days=1)
    with db_client.session() as sess:
        for band, mult in (("RAIN_24H", 1), ("RAIN_72H", 2), ("RAIN_7D", 3), ("RAIN_30D", 4)):
            ha.upsert_observations(sess, band, d, {synthetic_aoi[p]: ha.ZonalResult(v * mult, 1.0, 1)
                                                   for p, v in (("TST001", 12.0), ("TST002", 120.0), ("TST003", 0.0))},
                                   run_type="L")
        alert_engine.check_alerts(sess, d)
    return d


class TestHydromet:
    def test_today(self, make_client, recent_obs, synthetic_aoi):
        r = make_client("USER").get("/api/hydromet/today")
        assert r.status_code == 200
        body = r.json()
        assert body["obs_date"] == recent_obs.isoformat()
        assert body["window_wib"].startswith(f"{recent_obs.isoformat()}T07:00+07:00/")
        bayah = next(x for x in body["regions"] if x["pcode"] == "TST002")
        assert bayah["rain_24h_mm"] == 120.0 and bayah["rain_30d_mm"] == 480.0
        assert bayah["bmkg_category"] == "SANGAT_LEBAT" and bayah["gpm_run"] == "L"
        assert bayah["active_alert"]["severity"] == "WARNING"       # severity tertinggi hari itu
        assert next(x for x in body["regions"] if x["pcode"] == "TST003")["active_alert"] is None

    def test_user_limited_to_30_days(self, make_client, recent_obs):
        old = (_today() - timedelta(days=200)).isoformat()
        r = make_client("USER").get(f"/api/hydromet/observations?date_from={old}")
        assert r.status_code == 403 and r.json()["code"] == "DATE_OUT_OF_RANGE"
        assert make_client("ANALYST").get(f"/api/hydromet/observations?date_from={old}").status_code == 200
        r = make_client("USER").get("/api/hydromet/observations?band=RAIN_24H")
        assert r.status_code == 200 and r.json()["total"] >= 3
        assert make_client("USER").get("/api/hydromet/trend?days=90").status_code == 403

    def test_trend_shape(self, make_client, recent_obs):
        body = make_client("USER").get("/api/hydromet/trend?band=RAIN_24H&days=7").json()
        assert len(body["dates"]) == 7 and body["dates"][-1] == recent_obs.isoformat()
        assert all(len(s["values"]) == 7 for s in body["series"])

    def test_csv_export_is_logged(self, make_client, recent_obs, db_client):
        r = make_client("ANALYST").get("/api/hydromet/observations.csv?band=RAIN_24H")
        assert r.status_code == 200 and r.text.splitlines()[0].startswith("obs_date_utc,region_id")
        assert make_client("USER").get("/api/hydromet/observations.csv").status_code == 403
        with db_client.session() as sess:
            assert sess.scalar(text("SELECT count(*) FROM user_activity_logs WHERE action = 'EXPORT_CSV'")) >= 1

    def test_kecamatan_geojson(self, make_client, synthetic_aoi):
        fc = make_client("USER").get("/api/regions").json()
        assert fc["type"] == "FeatureCollection"
        props = {f["properties"]["pcode"] for f in fc["features"]}
        assert {"TST001", "TST002", "TST003"} <= props
        assert all(f["geometry"]["type"] in ("Polygon", "MultiPolygon") for f in fc["features"])


class TestAlerts:
    def test_list_and_acknowledge(self, make_client, recent_obs, role_users):
        items = make_client("USER").get("/api/alerts?status=active&severity=WARNING").json()["items"]
        target = next(a for a in items if a["pcode"] == "TST002" and a["observation_date"] == recent_obs.isoformat())
        assert make_client("USER").post(f"/api/alerts/{target['alert_id']}/acknowledge", json={}).status_code == 403
        r = make_client("ANALYST").post(f"/api/alerts/{target['alert_id']}/acknowledge", json={"note": "dicek lapangan"})
        assert r.status_code == 200 and r.json()["acknowledged_by"] == role_users["ANALYST"]
        assert r.json()["ack_note"] == "dicek lapangan"
        again = make_client("ANALYST").post(f"/api/alerts/{target['alert_id']}/acknowledge", json={})
        assert again.status_code == 409 and again.json()["code"] == "ALERT_ALREADY_ACKED"
        assert make_client("ANALYST").post("/api/alerts/999999/acknowledge", json={}).status_code == 404

    def test_evaluation(self, make_client):
        body = make_client("ANALYST").get("/api/alerts/evaluation").json()
        assert set(body) >= {"hit", "miss", "false_alarm", "pod", "far"}
        assert make_client("USER").get("/api/alerts/evaluation").status_code == 403

    def test_rules_crud_without_delete(self, make_client):
        admin = make_client("ADMIN")
        assert len(make_client("USER").get("/api/alert-rules").json()["items"]) >= 4
        body = {"rule_code": "TEST_API_RULE", "disaster_type_code": "LONGSOR", "band_code": "RAIN_72H",
                "threshold_value": 150, "severity": "WARNING", "reference_source": "uji API"}
        assert make_client("ANALYST").post("/api/alert-rules", json=body).status_code == 403
        r = admin.post("/api/alert-rules", json=body)
        assert r.status_code == 201, r.text
        rule_id = r.json()["rule_id"]
        assert admin.post("/api/alert-rules", json=body).status_code == 409
        r = admin.put(f"/api/alert-rules/{rule_id}", json={"is_active": False})
        assert r.status_code == 200 and r.json()["is_active"] is False
        bad = admin.put(f"/api/alert-rules/{rule_id}", json={"is_active": True, "threshold_value": None})
        assert bad.status_code == 400 and bad.json()["code"] == "THRESHOLD_REQUIRED"
        assert admin.delete(f"/api/alert-rules/{rule_id}").status_code == 405


class TestDisasters:
    def test_crud_soft_delete_and_rain(self, make_client, recent_obs, synthetic_aoi, db_client):
        analyst = make_client("ANALYST")
        body = {"disaster_type_code": "BANJIR", "region_id": synthetic_aoi["TST002"], "village_name": "Desa Uji",
                "location": {"lat": -6.65, "lon": 106.25}, "event_date": recent_obs.isoformat(),
                "description": "Luapan sungai merendam permukiman uji.", "info_source": "GMLS", "is_verified": True}
        assert make_client("USER").post("/api/disasters", json=body).status_code == 403
        assert make_client("DATA_ENGINEER").get("/api/disasters").status_code == 403
        r = analyst.post("/api/disasters", json=body)
        assert r.status_code == 201, r.text
        ev = r.json()
        assert ev["location"] == {"lat": -6.65, "lon": 106.25} and ev["is_verified"] is True
        detail = analyst.get(f"/api/disasters/{ev['event_id']}").json()
        assert detail["rain"][0] == {"day": "H-0", "rain_24h_mm": 120.0, "rain_72h_mm": 240.0, "rain_7d_mm": 360.0}
        assert detail["rain"][1]["rain_24h_mm"] is None
        r = analyst.put(f"/api/disasters/{ev['event_id']}", json={"impact_summary": "± 10 rumah"})
        assert r.status_code == 200 and r.json()["impact_summary"] == "± 10 rumah"
        bad = analyst.put(f"/api/disasters/{ev['event_id']}",
                          json={"event_end_date": (recent_obs - timedelta(days=5)).isoformat()})
        assert bad.status_code == 400
        assert analyst.delete(f"/api/disasters/{ev['event_id']}").status_code == 200
        assert analyst.get(f"/api/disasters/{ev['event_id']}").status_code == 404
        with db_client.session() as sess:     # soft delete: baris masih ada
            assert sess.scalar(text("SELECT deleted_at IS NOT NULL FROM disaster_events WHERE event_id = :e"),
                               {"e": ev["event_id"]})

    def test_validation(self, make_client, synthetic_aoi):
        analyst = make_client("ANALYST")
        base = {"disaster_type_code": "BANJIR", "region_id": synthetic_aoi["TST001"], "event_date": "2024-01-01",
                "description": "terlalu", "info_source": "GMLS"}
        assert analyst.post("/api/disasters", json=base).status_code == 422          # deskripsi < 10
        base["description"] = "Deskripsi yang cukup panjang."
        r = analyst.post("/api/disasters", json={**base, "disaster_type_code": "TSUNAMI"})
        assert r.status_code == 400 and r.json()["code"] == "INVALID_DISASTER"

    def test_types(self, make_client):
        assert {"BANJIR", "LONGSOR"} <= {t["type_code"] for t in make_client("USER").get("/api/disaster-types").json()["items"]}
        admin = make_client("ADMIN")
        r = admin.post("/api/disaster-types", json={"type_code": "CUACA_EKSTREM", "type_name": "Cuaca ekstrem"})
        assert r.status_code == 201
        assert admin.put(f"/api/disaster-types/{r.json()['disaster_type_id']}", json={"is_active": False}).json()["is_active"] is False
        assert make_client("ANALYST").post("/api/disaster-types", json={"type_code": "XX_YY", "type_name": "x"}).status_code == 403


class TestAdminRegions:
    def test_patch_in_aoi_rebuilds_roi(self, make_client, synthetic_aoi, db_client):
        admin = make_client("ADMIN")
        rid = synthetic_aoi["TST003"]

        def bbox():
            with db_client.session() as sess:
                return sess.scalar(text("SELECT ST_AsText(bbox) FROM regions_of_interest WHERE is_monitor_aoi"))
        before = bbox()
        r = admin.patch(f"/api/admin/regions/{rid}", json={"in_aoi": False})
        assert r.status_code == 200 and r.json()["in_aoi"] is False
        assert bbox() != before
        admin.patch(f"/api/admin/regions/{rid}", json={"in_aoi": True})
        assert bbox() == before
        lvl2 = synthetic_aoi["TST00"]
        assert admin.patch(f"/api/admin/regions/{lvl2}", json={"in_aoi": True}).json()["code"] == "NOT_KECAMATAN"
        assert make_client("ANALYST").patch(f"/api/admin/regions/{rid}", json={"in_aoi": False}).status_code == 403

    def test_union_roi(self, make_client, synthetic_aoi):
        r = make_client("ADMIN").post("/api/admin/rois", json={
            "region_ids": [synthetic_aoi["TST001"], synthetic_aoi["TST002"]], "name": "Gabungan uji",
            "region_code": "TST_UNION"})
        assert r.status_code == 201, r.text
        assert r.json()["bbox"] == pytest.approx([106.075, -6.7, 106.3, -6.5], abs=1e-9)
        bad = make_client("ADMIN").post("/api/admin/rois", json={"region_ids": [synthetic_aoi["TST00"]], "name": "x1"})
        assert bad.status_code == 400

    def test_ingest_validation(self, make_client):
        admin = make_client("ADMIN")
        assert admin.post("/api/admin/ingest", json={"job": "HYDROMET"}).status_code == 422
        assert admin.post("/api/admin/ingest", json={"job": "LIVE", "area_id": 999999}).status_code == 404


class TestPublicLive:
    @pytest.fixture()
    def area(self, db_client, tmp_path):
        """Live Area dengan dua scene; PNG hanya pada folder scene terbaru."""
        from etl import folder_manager as fm
        with db_client.session() as sess:
            ds = sess.scalar(text("""INSERT INTO datasets (name, bbox, bbox_wkt, date_start, date_end, dataset_kind, status)
                VALUES ('live_publik_uji', ST_GeomFromText('POLYGON((106 -7,106.5 -7,106.5 -6.5,106 -6.5,106 -7))', 4326),
                        'POLYGON((106 -7,106.5 -7,106.5 -6.5,106 -6.5,106 -7))', current_date, current_date,
                        'LIVE_AREA', 'DRAFT') RETURNING dataset_id"""))
            area = sess.scalar(text("""INSERT INTO live_areas (dataset_id, name, bbox_wkt, status)
                VALUES (:d, 'Area Publik Uji', 'POLYGON((106 -7,106.5 -7,106.5 -6.5,106 -6.5,106 -7))', 'ACTIVE')
                RETURNING area_id"""), {"d": ds})
            for d in (date(2024, 1, 10), date(2024, 1, 22)):
                sess.execute(text("""INSERT INTO live_scenes (area_id, dataset_id, scene_date, status, previews, interpretations)
                    VALUES (:a, :ds, :d, 'READY', CAST(:p AS jsonb), '{}')"""),
                    {"a": area, "ds": ds, "d": d, "p": '{"items": {"s1_vh": {"file": "s1_vh.png", "label": "VH"}}}'})
        from etl.live_monitor import _LiveFiles
        files = _LiveFiles(ds, "live_publik_uji", "LIVE_AREA")
        p = files.preview_dir(date(2024, 1, 22)) / "s1_vh.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        yield area
        with db_client.session() as sess:
            sess.execute(text("DELETE FROM live_scenes WHERE area_id = :a"), {"a": area})
            sess.execute(text("DELETE FROM live_areas WHERE area_id = :a"), {"a": area})
            sess.execute(text("DELETE FROM datasets WHERE dataset_id = :d"), {"d": ds})

    def test_latest_only(self, make_client, area):
        anon = make_client(None)
        body = anon.get("/api/public/live").json()
        item = next(i for i in body["items"] if i["area_id"] == area)
        assert item["scene_date"] == "2024-01-22" and "forecast" not in item and "dates" not in item
        url = item["previews"]["s1_vh"]["url"]
        assert anon.get(url).status_code == 200
        r = anon.get(url + "?date=2024-01-10")
        assert r.status_code == 403 and r.json()["code"] == "SCENE_NOT_PUBLIC"
        assert anon.get(f"/api/public/live/{area}/preview/modis_ndvi.png").status_code == 404


class TestImportDisasters:
    def test_csv_import_all_or_nothing(self, app_db_client, synthetic_aoi, tmp_path, db_client):
        from scripts.import_disasters import run
        good = tmp_path / "ok.csv"
        good.write_text("tanggal,jenis,kecamatan,desa,lat,lon,keterangan,sumber,terverifikasi\n"
                        "2024-02-01,BANJIR,TST001,Desa A,-6.55,106.1,Banjir uji impor CSV pertama,GMLS,ya\n"
                        "2024-02-02,LONGSOR,Kecamatan 2,,,,Longsor uji impor CSV kedua,BPBD_LEBAK,\n", encoding="utf-8")
        s = run(app_db_client, good, "t_analyst")
        assert (s["inserted"], s["duplicates"], s["errors"]) == (2, 0, [])
        assert run(app_db_client, good, "t_analyst")["duplicates"] == 2         # impor ulang aman
        bad = tmp_path / "bad.csv"
        bad.write_text("tanggal,jenis,kecamatan,keterangan,sumber\n"
                       "2024-02-03,BANJIR,TST002,Baris yang benar sekali,GMLS\n"
                       "2024-02-04,BANJIR,TIDAKADA,Kecamatan tidak dikenal,GMLS\n", encoding="utf-8")
        s = run(app_db_client, bad, "t_analyst")
        assert s["inserted"] == 0 and len(s["errors"]) == 1 and "line 3" in s["errors"][0]
        with db_client.session() as sess:
            assert sess.scalar(text("SELECT count(*) FROM disaster_events WHERE event_date = '2024-02-03'")) == 0
            recorded = sess.scalar(text("""SELECT count(*) FROM audit_log WHERE table_name = 'disaster_events'
                                           AND operation = 'I' AND app_user_id IS NOT NULL"""))
        assert recorded >= 2
        with pytest.raises(ValueError, match="ANALYST or ADMIN"):
            run(app_db_client, good, "t_user")


class TestSchedulerLock:
    def test_second_worker_is_skipped_locked(self, etl_db_client, db_client):
        from etl import scheduler
        from etl.advisory_lock import advisory_lock, is_locked

        holding, release = threading.Event(), threading.Event()

        def hold():
            with advisory_lock(etl_db_client, "report") as got:
                assert got
                holding.set()
                release.wait(10)

        t = threading.Thread(target=hold)
        t.start()
        assert holding.wait(10)
        try:
            assert is_locked(etl_db_client, "report")
            ran = []
            out = scheduler.run_locked(etl_db_client, "report_TEST", "report", lambda: ran.append(1))
            assert out["status"] == "SKIPPED_LOCKED" and ran == []
        finally:
            release.set()
            t.join()
        assert scheduler.run_locked(etl_db_client, "report_TEST", "report", lambda: "ok") == {"status": "OK", "result": "ok"}
        with db_client.session() as sess:
            row = sess.execute(text("""SELECT j.status::text, j.parameters_json->>'lock' FROM processing_jobs j
                JOIN processing_stages s USING (stage_id) WHERE s.stage_name = 'ORCHESTRATE'
                AND j.parameters_json->>'scheduler_job' = 'report_TEST' ORDER BY job_id DESC LIMIT 1""")).one()
        assert tuple(row) == ("SKIPPED_LOCKED", "report")

    def test_jobs_cover_pipeline_section_7(self):
        from etl.scheduler import JOBS
        cron = {j.job_id: j.cron for j in JOBS}
        assert cron["hydromet_daily"] == {"hour": 2, "minute": 0}
        assert cron["hydromet_final"]["day_of_week"] == "sun" and cron["hydromet_final"]["hour"] == 4
        assert cron["live_cycle"]["hour"] == "1,7,13,19"
        assert cron["report_HYDROMET_WEEKLY"] == {"day_of_week": "mon", "hour": 3, "minute": 0}
        assert cron["report_DATAHEALTH_WEEKLY"]["minute"] == 15
        assert cron["report_HYDROMET_MONTHLY"] == {"day": 1, "hour": 3, "minute": 30}
        assert cron["report_DATAHEALTH_MONTHLY"]["minute"] == 45
        assert {j.lock for j in JOBS} == {"hydromet", "live", "report"}

    def test_report_waits_for_hydromet_then_notes(self, etl_db_client, monkeypatch, tmp_path):
        from etl import report_periodic, scheduler
        from etl.advisory_lock import advisory_lock
        monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
        seen = {}
        monkeypatch.setattr(report_periodic, "generate_report",
                            lambda db, code, period, notes=None: seen.update(code=code, notes=notes) or
                            type("R", (), {"status": "READY"})())
        with advisory_lock(etl_db_client, "hydromet"):
            done = {}
            t = threading.Thread(target=lambda: done.update(r=scheduler.job_report(etl_db_client, "HYDROMET_WEEKLY",
                                                                                   wait_minutes=0.01)))
            t.start()
            t.join(30)
        assert done["r"]["status"] == "OK" and seen["notes"] == [scheduler.INCOMPLETE_NOTE]


class TestAdminOperations:
    def test_scene_soft_delete_and_reprocess(self, make_client, db_client, synthetic_aoi, monkeypatch):
        from api.routes import admin_monitor
        with db_client.session() as sess:
            nid = sess.scalar(text("""INSERT INTO nasa_scenes (source, tile_id, product_short_name, acquisition_date,
                                       region_id) VALUES ('GPM', 'GLOBAL', 'GPM_3IMERGDF', '2024-07-01', :r)
                                       RETURNING nasa_scene_id"""), {"r": synthetic_aoi["roi_id"]})
        admin = make_client("ADMIN")
        r = admin.patch(f"/api/admin/scenes/GPM/{nid}", json={"is_valid": False})
        assert r.status_code == 400 and r.json()["code"] == "REASON_REQUIRED"
        r = admin.patch(f"/api/admin/scenes/GPM/{nid}", json={"is_valid": False, "reason": "granule rusak"})
        assert r.status_code == 200 and r.json()["is_valid"] is False and r.json()["invalid_reason"] == "granule rusak"
        assert admin.patch(f"/api/admin/scenes/MODIS/{nid}", json={"is_valid": True}).status_code == 404
        assert admin.patch(f"/api/admin/scenes/GPM/{nid}", json={"is_valid": True}).json()["is_valid"] is True
        calls = []
        monkeypatch.setattr(admin_monitor, "_reprocess_hydromet", lambda etl, day: calls.append(day))
        r = admin.post(f"/api/admin/scenes/GPM/{nid}/reprocess")
        assert r.status_code == 202 and r.json()["date"] == "2024-07-01"
        assert admin.post("/api/admin/scenes/XX/1/reprocess").json()["code"] == "INVALID_SOURCE"
        with db_client.session() as sess:
            sess.execute(text("DELETE FROM nasa_scenes WHERE nasa_scene_id = :i"), {"i": nid})

    def test_thresholds_and_settings(self, make_client, db_client):
        admin = make_client("ADMIN")
        items = admin.get("/api/admin/quality-thresholds").json()["items"]
        vf = next(i for i in items if i["band_code"] == "RAIN_24H" and i["metric_name"] == "valid_fraction")
        r = admin.put("/api/admin/quality-thresholds", json=[{"threshold_id": vf["threshold_id"], "fail_below": 0.9}])
        assert r.status_code == 400 and r.json()["code"] == "INVALID_THRESHOLD"     # fail > warn
        r = admin.put("/api/admin/quality-thresholds", json=[{"threshold_id": vf["threshold_id"], "warn_below": 0.6}])
        assert r.status_code == 200
        admin.put("/api/admin/quality-thresholds", json=[{"threshold_id": vf["threshold_id"], "warn_below": 0.5}])
        keys = {i["setting_key"] for i in admin.get("/api/admin/settings").json()["items"]}
        assert {"live.retention_default", "hydromet.waiting_max_days"} <= keys
        bad = admin.put("/api/admin/settings", json={"settings": {"live.retention_max": 99}})
        assert bad.status_code == 400 and bad.json()["code"] == "INVALID_SETTING"
        assert admin.put("/api/admin/settings", json={"settings": {"nope": 1}}).status_code == 404
        ok = admin.put("/api/admin/settings", json={"settings": {"hydromet.waiting_max_days": 4}})
        assert ok.status_code == 200
        admin.put("/api/admin/settings", json={"settings": {"hydromet.waiting_max_days": 3}})
        assert admin.put("/api/admin/settings", json={"settings": {"live.retention_default": 70}}).status_code == 400

    def test_status_and_archive(self, make_client, recent_obs):
        admin = make_client("ADMIN")
        st = admin.get("/api/admin/pipeline/status").json()
        assert {"latest_jobs", "hydromet", "live_areas", "reports", "credentials", "scheduler"} <= set(st)
        assert isinstance(st["credentials"]["nasa_earthdata_token"], bool)
        stats = admin.get("/api/admin/archive/stats").json()
        assert stats["rows"]["region_observations"] > 0
        v = admin.post("/api/admin/archive/verify", json={"limit": 5}).json()
        assert v["checked"] == v["ok"] + len(v["missing"]) + len(v["mismatch"])
