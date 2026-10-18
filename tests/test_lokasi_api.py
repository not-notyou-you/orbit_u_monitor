# tests/test_lokasi_api.py
"""Pantau Lokasi di Beranda (M63, INTERFACE.md §2 halaman 1, §4.2).

* Pengunjung membaca angka per kecamatan lewat v_public_lokasi_obs dengan batas
  waktu 30 hari, tetapi dua observasi terakhir tiap band selalu terlihat
  (pembanding kalimat kondisi); USER melihat 365 hari.
* Kalimat kondisi menyebut apa yang tidak normal, termasuk alert hujan 7 hari.
* Citra dipotong ke kecamatan: di luar poligon transparan, dipotong ke bbox.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from etl import alert_engine, hydromet_aggregate as ha


def _today():
    return datetime.now(timezone.utc).date()


@pytest.fixture(scope="module")
def lokasi_obs(db_client, synthetic_aoi):
    """Hujan lebat TST002 lima hari lalu (+ alert), NDVI lama TST003 untuk uji batas waktu.

    Lima hari: masih di jendela alert 7 hari, tetapi bukan H-0..H-2 kejadian
    uji di tests/test_monitor_api.py (yang mengharapkan hari-hari itu kosong)."""
    d = _today() - timedelta(days=5)
    with db_client.session() as sess:
        # Sama dengan nilai tests/test_monitor_api.py::recent_obs (kemarin),
        # jadi urutan modul tidak mengubah angka hujan "terbaru".
        for band, mult in (("RAIN_24H", 1), ("RAIN_72H", 2), ("RAIN_7D", 3)):
            ha.upsert_observations(sess, band, d, {synthetic_aoi[p]: ha.ZonalResult(v * mult, 1.0, 1)
                                                   for p, v in (("TST001", 12.0), ("TST002", 120.0), ("TST003", 0.0))},
                                   run_type="L")
        alert_engine.check_alerts(sess, d)
        for days, v in ((200, 0.60), (190, 0.70), (180, 0.80)):
            ha.upsert_observations(sess, "NDVI", _today() - timedelta(days=days),
                                   {synthetic_aoi["TST003"]: ha.ZonalResult(v, 0.9, 1)})
    return d


class TestLokasiApi:
    def test_list_is_public_with_status_and_alert(self, make_client, lokasi_obs, synthetic_aoi):
        body = make_client(None).get("/api/public/lokasi").json()
        by = {i["pcode"]: i for i in body["items"]}
        assert {"TST001", "TST002", "TST003"} <= set(by)
        assert by["TST002"]["status"]["level"] >= 1 and by["TST002"]["alert"] == "WARNING"
        assert by["TST002"]["abnormal"] >= 1
        # TST001 (12 mm) tidak pernah melewati ambang BMKG di modul mana pun.
        assert by["TST001"]["alert"] is None

    def test_detail_explains_what_is_abnormal(self, make_client, lokasi_obs, synthetic_aoi):
        r = make_client(None).get(f"/api/public/lokasi/{synthetic_aoi['TST002']}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"]["label"] in ("Waspada", "Tinggi")
        keys = {a["key"] for a in d["abnormal"]}
        assert {"gpm_rain_24h", "gpm_rain_72h", "alert"} <= keys
        alert = next(a for a in d["abnormal"] if a["key"] == "alert")
        assert "120" in alert["because"] and "100" in alert["because"]
        rain = next(s for s in d["stats"] if s["band_code"] == "RAIN_24H")
        assert rain["value"] == 120.0 and rain["unit"]
        assert [s["band_code"] for s in d["stats"]][:3] == ["VV", "VH", "WATER_PCT"]
        assert d["dates"]["gpm"] is not None

    def test_public_window_keeps_two_latest(self, make_client, lokasi_obs, synthetic_aoi, db_client):
        """NDVI 180/190/200 hari lalu: pengunjung melihat dua terakhir saja
        (pembanding), USER melihat ketiganya (365 hari)."""
        rid = synthetic_aoi["TST003"]
        counts = {}
        for role in ("monitor_public", "monitor_user"):
            with db_client.session() as sess:
                sess.execute(text(f"SET LOCAL ROLE {role}"))
                counts[role] = sess.scalar(text(
                    "SELECT count(*) FROM v_public_lokasi_obs WHERE region_id = :r AND band_code = 'NDVI'"), {"r": rid})
        assert counts == {"monitor_public": 2, "monitor_user": 3}
        ndvi = next(s for s in make_client(None).get(f"/api/public/lokasi/{rid}").json()["stats"]
                    if s["band_code"] == "NDVI")
        assert ndvi["value"] == 0.8 and ndvi["prev_value"] == 0.7

    def test_public_cannot_read_alert_handling(self, db_client, lokasi_obs):
        with db_client.session() as sess:
            sess.execute(text("SET LOCAL ROLE monitor_public"))
            cols = set(sess.execute(text("SELECT * FROM v_public_lokasi_alert LIMIT 0")).keys())
        assert "acknowledged_by" not in cols and "acknowledged_at" not in cols

    def test_trend_shape_and_unknown_region(self, make_client, lokasi_obs, synthetic_aoi):
        anon = make_client(None)
        body = anon.get(f"/api/public/lokasi/{synthetic_aoi['TST002']}/trend").json()
        assert len(body["dates"]) == 30 and [g["key"] for g in body["groups"]] == ["s1", "modis", "gpm"]
        rain = next(b for g in body["groups"] for b in g["bands"] if b["band_code"] == "RAIN_24H")
        assert rain["values"][body["dates"].index(lokasi_obs.isoformat())] == 120.0
        assert anon.get("/api/public/lokasi/999999").status_code == 404
        assert anon.get(f"/api/public/lokasi/{synthetic_aoi['TST002']}/trend?days=365").status_code == 422


class TestCroppedPreview:
    @pytest.fixture()
    def area(self, db_client, synthetic_aoi):
        """Live Area 106..106.5 × -7..-6.5 dengan PNG merah 500×500 ber-grid EPSG:4326."""
        from PIL import Image

        from etl.live_monitor import _LiveFiles
        wkt = "POLYGON((106 -7,106.5 -7,106.5 -6.5,106 -6.5,106 -7))"
        d = date(2024, 2, 1)
        with db_client.session() as sess:
            ds = sess.scalar(text("""INSERT INTO datasets (name, bbox, bbox_wkt, date_start, date_end, dataset_kind, status)
                VALUES ('live_lokasi_uji', ST_GeomFromText(:w, 4326), :w, current_date, current_date, 'LIVE_AREA', 'DRAFT')
                RETURNING dataset_id"""), {"w": wkt})
            area = sess.scalar(text("""INSERT INTO live_areas (dataset_id, name, bbox_wkt, status)
                VALUES (:d, 'Area Lokasi Uji', :w, 'ACTIVE') RETURNING area_id"""), {"d": ds, "w": wkt})
            previews = ('{"grid": {"width": 500, "height": 500, "crs": "EPSG:4326", '
                        '"corners_wgs84": [[106,-6.5],[106.5,-6.5],[106.5,-7],[106,-7]]}, '
                        '"items": {"s1_vh": {"file": "s1_vh.png", "label": "VH"}}}')
            sess.execute(text("""INSERT INTO live_scenes (area_id, dataset_id, scene_date, status, previews, interpretations)
                VALUES (:a, :ds, :d, 'READY', CAST(:p AS jsonb), '{}')"""), {"a": area, "ds": ds, "d": d, "p": previews})
        p = _LiveFiles(ds, "live_lokasi_uji", "LIVE_AREA").preview_dir(d) / "s1_vh.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (500, 500), (255, 0, 0)).save(p)
        yield area
        with db_client.session() as sess:
            sess.execute(text("DELETE FROM live_scenes WHERE area_id = :a"), {"a": area})
            sess.execute(text("DELETE FROM live_areas WHERE area_id = :a"), {"a": area})
            sess.execute(text("DELETE FROM datasets WHERE dataset_id = :d"), {"d": ds})

    def test_crop_is_transparent_outside_kecamatan(self, make_client, area, synthetic_aoi):
        import io

        from PIL import Image
        anon = make_client(None)
        rid = synthetic_aoi["TST002"]          # box 106.2..106.3 × -6.7..-6.6 = 100×100 px
        d = anon.get(f"/api/public/lokasi/{rid}").json()
        assert d["imagery"]["area_id"] == area and d["imagery"]["cropped"] is True
        url = d["imagery"]["previews"]["s1_vh"]["url"]
        assert url == f"/api/public/lokasi/{rid}/preview/s1_vh.png"
        r = anon.get(url)
        assert r.status_code == 200 and r.headers["content-type"] == "image/png"
        img = Image.open(io.BytesIO(r.content))
        assert img.mode == "RGBA" and 100 <= img.width <= 114 and 100 <= img.height <= 114
        assert img.getpixel((img.width // 2, img.height // 2)) == (255, 0, 0, 255)
        assert img.getpixel((1, 1))[3] == 0                          # tepi padding di luar poligon
        assert anon.get(f"/api/public/lokasi/{rid}/preview/modis_ndvi.png").status_code == 404


class TestLokasiInterpret:
    def test_any_abnormal_item_raises_status(self):
        """Hujan 7 hari di atas ambang tidak dibaca status gabungan Live, tetapi
        Beranda menjelaskannya sebagai "tidak normal", jadi statusnya ikut naik."""
        from etl.lokasi_interpret import interpret_region
        latest = {"RAIN_24H": {"value": 2.0}, "RAIN_72H": {"value": 10.0}, "RAIN_7D": {"value": 90.0}}
        res = interpret_region(latest, {}, {}, [])
        assert res["status"]["label"] == "Waspada"
        assert [a["key"] for a in res["abnormal"]] == ["gpm_rain_7d"]
        assert "curah hujan 7 hari" in res["status"]["text"]

    def test_normal_and_unavailable(self):
        from etl.lokasi_interpret import interpret_region
        res = interpret_region({"RAIN_72H": {"value": 3.0}}, {}, {}, [])
        assert res["status"]["level"] == 0 and res["abnormal"] == []
        assert res["items"]["modis_flood"]["category"] == "unavailable"
        empty = interpret_region({}, {}, {}, [])
        assert empty["status"]["level"] == -1

    def test_critical_alert_means_tinggi(self):
        from etl.lokasi_interpret import interpret_region
        alerts = [{"severity": "CRITICAL", "observation_date": date(2026, 1, 2), "observed_value": 160.0,
                   "threshold_value": 150.0}]
        res = interpret_region({"RAIN_72H": {"value": 3.0}}, {}, {}, alerts)
        assert res["status"]["level"] == 2 and res["abnormal"][-1]["key"] == "alert"

    def test_alert_date_is_latest_alert_not_worst(self):
        """Kunci anti-duplikat email (M64) = tanggal alert TERBARU: alert
        PERINGATAN baru tetap memicu email walau alert KRITIS lama masih dalam
        jendela 7 hari; status tetap mengikuti yang terparah."""
        from etl.lokasi_interpret import interpret_region
        alerts = [{"severity": "CRITICAL", "observation_date": date(2026, 1, 1), "observed_value": 160.0,
                   "threshold_value": 150.0, "band_code": "RAIN_24H"},
                  {"severity": "WARNING", "observation_date": date(2026, 1, 3), "observed_value": 110.0,
                   "threshold_value": 100.0, "band_code": "RAIN_24H"}]
        res = interpret_region({"RAIN_72H": {"value": 3.0}}, {}, {}, alerts)
        al = next(a for a in res["abnormal"] if a["key"] == "alert")
        assert al["date"] == date(2026, 1, 3) and al["level"] == 2 and res["status"]["level"] == 2

    def test_ndwi_above_water_threshold(self):
        from etl.lokasi_interpret import interpret_region
        res = interpret_region({"NDWI": {"value": 0.1}}, {}, {"NDWI": {"p02": -0.8, "p98": -0.6}}, [])
        assert res["items"]["modis_ndwi"]["category"] == "flood-indicated"
        res = interpret_region({"NDWI": {"value": -0.5}}, {}, {"NDWI": {"p02": -0.8, "p98": -0.6}}, [])
        assert res["items"]["modis_ndwi"]["category"] == "alert"


def test_region_crop_keeps_holes_transparent(tmp_path):
    from PIL import Image

    from etl.region_crop import crop
    src = tmp_path / "a.png"
    Image.new("RGB", (100, 100), (0, 0, 255)).save(src)
    grid = {"crs": "EPSG:4326", "corners_wgs84": [[0, 1], [1, 1], [1, 0], [0, 0]]}
    outer = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9], [0.1, 0.1]]
    hole = [[0.4, 0.4], [0.6, 0.4], [0.6, 0.6], [0.4, 0.6], [0.4, 0.4]]
    out = crop(src, grid, {"type": "Polygon", "coordinates": [outer, hole]}, tmp_path / "o.png")
    img = Image.open(out)
    assert img.getpixel((img.width // 2, img.height // 2))[3] == 0        # lubang
    assert img.getpixel((12, 12))[3] == 255                              # cincin luar
    assert crop(src, grid, {"type": "Polygon", "coordinates": [[[5, 5], [6, 5], [6, 6], [5, 5]]]},
                tmp_path / "x.png") is None                              # di luar gambar


def test_region_crop_projected_grid(tmp_path):
    """Grid preview ber-CRS UTM (sudut WGS84 tidak sejajar sumbu): poligon yang
    dibangun dari kotak UTM yang diketahui harus jatuh tepat di piksel itu."""
    from affine import Affine
    from PIL import Image
    from rasterio.warp import transform as warp

    from etl.region_crop import crop
    crs = "EPSG:32748"
    t = Affine(100.0, 0, 600000.0, 0, -100.0, 9260000.0)          # 100 m/piksel, 200×200 piksel
    w = h = 200
    xy = [t * (c, r) for c, r in ((0, 0), (w, 0), (w, h), (0, h))]
    lon, lat = warp(crs, "EPSG:4326", [p[0] for p in xy], [p[1] for p in xy])
    grid = {"crs": crs, "corners_wgs84": [[a, b] for a, b in zip(lon, lat)]}
    # Kotak piksel 50..150 (kolom) × 40..120 (baris), dibuat di UTM lalu ke WGS84.
    box = [t * (c, r) for c, r in ((50, 40), (150, 40), (150, 120), (50, 120), (50, 40))]
    blon, blat = warp(crs, "EPSG:4326", [p[0] for p in box], [p[1] for p in box])
    src = tmp_path / "u.png"
    Image.new("RGB", (w, h), (0, 200, 0)).save(src)
    out = crop(src, grid, {"type": "Polygon", "coordinates": [[[a, b] for a, b in zip(blon, blat)]]},
               tmp_path / "o.png")
    img = Image.open(out)
    pad = 6
    assert abs(img.width - (100 + 2 * pad)) <= 2 and abs(img.height - (80 + 2 * pad)) <= 2
    assert img.getpixel((img.width // 2, img.height // 2))[3] == 255
    assert img.getpixel((1, 1))[3] == 0
