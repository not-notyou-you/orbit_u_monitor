# tests/test_citra_api.py
"""Halaman Citra Satelit (INTERFACE.md §4.3, M56): batas waktu per role lewat
VIEW v_citra_scenes, isi per satelit, perbandingan, dan laporan PDF."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import text

ITEMS = {
    "s1_vv": {"label": "Backscatter VV", "legend": "dB"},
    "s1_vh": {"label": "Backscatter VH", "legend": "dB"},
    "modis_ndvi": {"label": "NDVI", "legend": "indeks"},
    "gpm_rain_24h": {"label": "Hujan 24 jam", "legend": "mm"},
}


@pytest.fixture
def citra_area(db_client):
    """Area dengan scene 5, 100, 400 hari lalu (bergambar) + 50 hari lalu
    (berkas dihapus retensi, angkanya masih ada)."""
    import json
    today = date.today()
    with db_client.session() as sess:
        area = sess.scalar(text("""
            INSERT INTO live_areas (name, bbox_wkt, status)
            VALUES ('citra uji', 'POLYGON((0 0,1 0,1 1,0 1,0 0))', 'ACTIVE') RETURNING area_id"""))
        ids = {}
        for days, status in ((5, "READY"), (50, "DELETED"), (100, "READY"), (400, "READY")):
            ready = status == "READY"
            ids[days] = sess.scalar(text("""
                INSERT INTO live_scenes (area_id, scene_date, status, previews, interpretations, deleted_at)
                VALUES (:a, :d, :s, CAST(:p AS jsonb), CAST(:i AS jsonb), CASE WHEN :ready THEN NULL ELSE now() END)
                RETURNING live_scene_id"""), {
                "a": area, "d": today - timedelta(days=days), "s": status, "ready": ready,
                "p": json.dumps({"items": ITEMS} if ready else {}),
                "i": json.dumps({"s1_vv": {"text": f"Menampilkan VV {days}", "category": "normal"},
                                 "gpm_rain_24h": {"text": "Menampilkan hujan", "category": "normal"}})})
            for band, value in (("VV", -10.0 - days / 100), ("NDVI", 0.5), ("RAIN_24H", 12.0)):
                sess.execute(text("""
                    INSERT INTO live_scene_metrics (live_scene_id, band_id, metric_name, value)
                    SELECT :s, band_id, 'mean', :v FROM spectral_bands WHERE band_code = :b"""),
                    {"s": ids[days], "b": band, "v": value})
    yield area, today, ids
    # Batas 5 Live Area aktif berlaku juga di DB uji bersama: tandai terhapus.
    with db_client.session() as sess:
        sess.execute(text("UPDATE live_areas SET deleted_at = now(), status = 'DELETED' WHERE area_id = :a"), {"a": area})


@pytest.fixture
def fake_png(tmp_path, monkeypatch):
    from PIL import Image

    from etl.live_monitor import LiveMonitor
    path = tmp_path / "tile.png"
    Image.new("RGB", (40, 30), (20, 200, 120)).save(path)
    monkeypatch.setattr(LiveMonitor, "preview_path", lambda self, area_id, d, key, boundaries=False: path)
    return path


def _dates(client, area, source="s1"):
    r = client.get(f"/api/citra/areas/{area}/scenes?source={source}")
    assert r.status_code == 200, r.text
    return r.json()


class TestWindow:
    def test_dates_per_role(self, make_client, citra_area):
        area, today, _ = citra_area
        iso = lambda d: (today - timedelta(days=d)).isoformat()
        anon = _dates(make_client(None), area)
        assert [d["date"] for d in anon["dates"]] == [iso(5)] and anon["window"]["days"] == 30
        user = _dates(make_client("USER"), area)
        assert [d["date"] for d in user["dates"]] == [iso(5), iso(50), iso(100)] and user["window"]["days"] == 365
        for role in ("ANALYST", "DATA_ENGINEER", "ADMIN"):
            body = _dates(make_client(role), area)
            assert len(body["dates"]) == 4 and body["window"]["days"] is None, role
        deleted = next(d for d in user["dates"] if d["date"] == iso(50))
        assert deleted["files_available"] is False and deleted["has_images"] is False

    def test_scene_outside_window_is_not_found(self, make_client, citra_area, fake_png):
        area, today, _ = citra_area
        old = (today - timedelta(days=100)).isoformat()
        anon = make_client(None)
        assert anon.get(f"/api/citra/areas/{area}/scenes/{old}?source=s1").status_code == 404
        assert anon.get(f"/api/citra/areas/{area}/preview/{old}/s1_vv.png").status_code == 404
        assert make_client("USER").get(f"/api/citra/areas/{area}/preview/{old}/s1_vv.png").status_code == 200
        older = (today - timedelta(days=400)).isoformat()
        assert make_client("USER").get(f"/api/citra/areas/{area}/scenes/{older}?source=s1").status_code == 404
        assert make_client("ANALYST").get(f"/api/citra/areas/{area}/scenes/{older}?source=s1").status_code == 200


class TestContent:
    def test_scene_detail_filters_by_satellite(self, make_client, citra_area):
        area, today, _ = citra_area
        d = (today - timedelta(days=5)).isoformat()
        c = make_client(None)
        s1 = c.get(f"/api/citra/areas/{area}/scenes/{d}?source=s1").json()
        assert set(s1["previews"]) == {"s1_vv", "s1_vh"}
        assert set(s1["interpretations"]) == {"s1_vv"}
        assert [m["band_code"] for m in s1["metrics"]] == ["VV"] and s1["metrics"][0]["metric_label"] == "rata-rata"
        gpm = c.get(f"/api/citra/areas/{area}/scenes/{d}?source=gpm").json()
        assert set(gpm["previews"]) == {"gpm_rain_24h"} and gpm["metrics"][0]["band_code"] == "RAIN_24H"
        assert c.get(f"/api/citra/areas/{area}/scenes/{d}?source=landsat").status_code == 422

    def test_deleted_scene_keeps_numbers_without_images(self, make_client, citra_area):
        area, today, _ = citra_area
        d = (today - timedelta(days=50)).isoformat()
        body = make_client("USER").get(f"/api/citra/areas/{area}/scenes/{d}?source=s1").json()
        assert body["files_available"] is False and body["previews"] == {} and body["metrics"]

    def test_summary_and_source_info(self, make_client, citra_area):
        area, today, _ = citra_area
        body = make_client(None).get(f"/api/citra/summary?area_id={area}").json()
        assert body["area"]["area_id"] == area and [s["key"] for s in body["sources"]] == ["s1", "modis", "gpm"]
        s1 = body["sources"][0]
        assert s1["n_dates"] == 1 and s1["latest_date"] == (today - timedelta(days=5)).isoformat()
        assert s1["latest"]["preview"]["url"].endswith("/s1_vh.png") or s1["latest"]["preview"]["url"].endswith("/s1_vv.png")
        info = make_client(None).get("/api/citra/sources/modis").json()
        assert {b["band_code"] for b in info["bands"]} == {"FLOOD", "NDVI", "NDWI"}
        flood = next(b for b in info["bands"] if b["band_code"] == "FLOOD")
        assert [t["label"] for t in flood["thresholds"]] == ["waspada", "tinggi"] and flood["color"].startswith("#")
        assert make_client(None).get("/api/citra/sources/x").status_code == 400


class TestReport:
    def test_pdf_selected_pages_with_comparison(self, make_client, citra_area, fake_png, db_client):
        area, today, _ = citra_area
        d, cmp = (today - timedelta(days=5)).isoformat(), (today - timedelta(days=100)).isoformat()
        r = make_client("USER").get(f"/api/citra/report.pdf?area_id={area}&pages=s1,gpm&date={d}&compare={cmp}")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf" and r.content[:4] == b"%PDF"
        assert "s1-gpm" in r.headers["content-disposition"]
        with db_client.session() as sess:
            row = sess.execute(text("""SELECT detail FROM user_activity_logs WHERE action = 'DOWNLOAD_REPORT'
                                       AND target_type = 'live_scenes' ORDER BY log_id DESC LIMIT 1""")).scalar()
        assert row["pages"] == ["s1", "gpm"]

    def test_pdf_respects_window_and_pages(self, make_client, citra_area, fake_png):
        area, today, _ = citra_area
        old = (today - timedelta(days=100)).isoformat()
        anon = make_client(None)
        assert anon.get(f"/api/citra/report.pdf?area_id={area}&pages=ringkasan").status_code == 200
        # S1 saja: GPM/MODIS bisa punya angka harian (observasi terakhir selalu terlihat).
        assert anon.get(f"/api/citra/report.pdf?area_id={area}&pages=s1&date={old}").status_code == 404
        r = anon.get(f"/api/citra/report.pdf?area_id={area}&pages=s1,landsat")
        assert (r.status_code, r.json()["code"]) == (400, "INVALID_PAGES")


class TestDailyHydromet:
    """GPM/MODIS: hari hasil Job Hidromet/backfill ikut terdeteksi walau tidak
    ada scene Live (perbaikan M56: dulu hanya tanggal scene)."""

    @pytest.fixture
    def daily(self, db_client, synthetic_aoi):
        from etl import hydromet_aggregate as ha
        today = date.today()
        days = {"baru": today - timedelta(days=3), "lama": today - timedelta(days=200), "kuno": today - timedelta(days=600)}
        with db_client.session() as sess:
            for d in days.values():
                ha.upsert_observations(sess, "RAIN_24H", d, {synthetic_aoi["TST001"]: ha.ZonalResult(10.0, 1.0, 1),
                                                             synthetic_aoi["TST003"]: ha.ZonalResult(30.0, 1.0, 1)},
                                       run_type="F")
        return days

    def test_daily_dates_per_role(self, make_client, citra_area, daily):
        area, _, _ = citra_area
        iso = {k: v.isoformat() for k, v in daily.items()}
        def dates(role):
            return {d["date"]: d for d in _dates(make_client(role), area, "gpm")["dates"]}
        anon, user, analyst = dates(None), dates("USER"), dates("ANALYST")
        assert iso["baru"] in anon and iso["lama"] not in anon
        assert iso["lama"] in user and iso["kuno"] not in user
        assert {iso["baru"], iso["lama"], iso["kuno"]} <= set(analyst)
        d = analyst[iso["lama"]]
        assert d["has_scene"] is False and d["has_daily"] is True and d["has_images"] is False
        s1 = {x["date"] for x in _dates(make_client("ANALYST"), area, "s1")["dates"]}
        assert iso["lama"] not in s1                       # S1 tidak punya angka harian

    def test_daily_detail_numbers_and_per_region(self, make_client, citra_area, daily):
        area, _, _ = citra_area
        d = daily["lama"].isoformat()
        body = make_client("USER").get(f"/api/citra/areas/{area}/scenes/{d}?source=gpm").json()
        assert body["has_scene"] is False and body["status"] == "HIDROMET" and body["previews"] == {}
        mean = next(m for m in body["metrics"] if m["band_code"] == "RAIN_24H" and m["metric_name"] == "aoi_mean")
        assert mean["value"] == pytest.approx(20.0) and mean["metric_unit"] == "mm"
        assert len(body["per_region"]) == 2 and all("RAIN_24H" in r["values"] for r in body["per_region"])
        anon = make_client(None).get(f"/api/citra/areas/{area}/scenes/{daily['baru'].isoformat()}?source=gpm").json()
        assert anon["per_region"] is None and anon["metrics"]
        r = make_client("ANALYST").get(f"/api/citra/report.pdf?area_id={area}&pages=gpm&date={d}")
        assert r.status_code == 200 and r.content[:4] == b"%PDF"
