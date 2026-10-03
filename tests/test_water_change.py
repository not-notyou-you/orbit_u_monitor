# tests/test_water_change.py
"""Peta perubahan air S1 (PIPELINE.md §4.1, M19) dengan VH sintetis yang jawabannya pasti."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest
from PIL import Image
from sqlalchemy import text

from etl import water_change as wc
from tests.conftest import write_synthetic_raster

# Grid 4x4 sel 0.01 derajat di sekitar Bayah.
GRID = {"x0": 106.20, "y0": -6.90, "res": 0.01, "shape": (4, 4)}
WATER, LAND = 10 ** (-25 / 10), 10 ** (-12 / 10)     # sigma0 linear: -25 dB (air), -12 dB (darat)


def _vh(tmp_path, name, layout):
    """layout: string 4x4 per baris, W=air, L=darat, .=NoData (0 = di luar swath)."""
    arr = np.array([[{"W": WATER, "L": LAND, ".": 0.0}[c] for c in row] for row in layout], dtype="float32")
    return write_synthetic_raster(tmp_path / f"{name}.tif", arr, nodata=0.0, grid=GRID)


PREV = ["WWLL",
        "WWLL",
        "LLLL",
        "LL.."]
CUR = ["WWWL",
       "LWLL",
       "LLLW",
       "LLL."]
# Hasil per sel: baris 0 W->W, W->W, L->W(baru), L->L
#               baris 1 W->L(surut), W->W, L, L
#               baris 2 L, L, L, L->W(baru)
#               baris 3 L, L, NoData(prev), NoData


def _cell_area(row: int) -> float:
    top = -6.90 - row * 0.01
    bottom = top - 0.01
    return wc.EARTH_RADIUS_KM ** 2 * math.radians(0.01) * abs(math.sin(math.radians(top)) - math.sin(math.radians(bottom)))


class TestClassify:
    def test_classes_and_areas(self, tmp_path):
        res = wc.compute(_vh(tmp_path, "cur", CUR), _vh(tmp_path, "prev", PREV), threshold_db=-20.0, edge_buffer_m=0)
        expected = np.array([[2, 2, 3, 1],
                             [4, 2, 1, 1],
                             [1, 1, 1, 3],
                             [1, 1, 0, 0]], dtype="uint8")
        np.testing.assert_array_equal(res.classes, expected)
        assert res.metrics["new_km2"] == pytest.approx(round(_cell_area(0) + _cell_area(2), 4), abs=1e-4)
        assert res.metrics["receded_km2"] == pytest.approx(round(_cell_area(1), 4), abs=1e-4)
        assert res.metrics["persistent_km2"] == pytest.approx(round(2 * _cell_area(0) + _cell_area(1), 4), abs=1e-4)
        assert res.metrics["valid_fraction"] == pytest.approx(14 / 16, abs=1e-4)

    def test_threshold_is_respected(self, tmp_path):
        # Dengan ambang -30 dB tidak ada piksel air sama sekali.
        res = wc.compute(_vh(tmp_path, "cur", CUR), _vh(tmp_path, "prev", PREV), threshold_db=-30.0, edge_buffer_m=0)
        assert res.metrics["new_km2"] == res.metrics["receded_km2"] == res.metrics["persistent_km2"] == 0.0

    def test_downsampling_averages_in_linear_space(self, tmp_path):
        # 2x2 piksel: dua -25 dB dan dua -12 dB. Rerata linear ≈ -14.8 dB (darat),
        # sedangkan rerata dB (-18.5) juga di atas -20 -> pakai ambang -16 untuk
        # membedakan: linear -> darat, dB -> air.
        lay = ["WL", "WL"]
        g = {"x0": 106.2, "y0": -6.9, "res": 0.01, "shape": (2, 2)}
        arr = np.array([[{"W": WATER, "L": LAND}[c] for c in r] for r in lay], dtype="float32")
        p1 = write_synthetic_raster(tmp_path / "a.tif", arr, nodata=0.0, grid=g)
        p2 = write_synthetic_raster(tmp_path / "b.tif", arr, nodata=0.0, grid=g)
        res = wc.compute(p1, p2, threshold_db=-16.0, max_side=1, edge_buffer_m=0)
        expected_db = 10 * math.log10((WATER + LAND) / 2)
        assert res.vh_db[0, 0] == pytest.approx(expected_db, abs=1e-3)
        assert res.classes[0, 0] == wc.LAND

    def test_db_input_is_detected(self, tmp_path):
        arr = np.array([[-25, -12], [-12, -12]], dtype="float32")
        g = {"x0": 106.2, "y0": -6.9, "res": 0.01, "shape": (2, 2)}
        p = write_synthetic_raster(tmp_path / "db.tif", arr, nodata=None, grid=g)
        res = wc.compute(p, p, edge_buffer_m=0)
        assert res.classes[0, 0] == wc.PERSISTENT and res.classes[1, 1] == wc.LAND


class TestOrbit:
    @pytest.mark.parametrize("pid,expected", [
        ("S1A_IW_GRDH_1SDV_20240110T224512_20240110T224537_052036_064A8B_1A2B", (52036 - 73) % 175 + 1),
        ("S1B_IW_GRDH_1SDV_20210110T224512_20210110T224537_025000_02F9AA_ABCD", (25000 - 27) % 175 + 1),
        ("S1C_IW_GRDH_1SDV_20250110T224512_20250110T224537_001000_000001_ABCD", (1000 - 172) % 175 + 1),
        # S1C setelah rekonfigurasi 24-06-2026: tanpa metadata -> tidak ditebak.
        ("S1C_IW_GRDH_1SDV_20260801T224512_20260801T224537_009000_000001_ABCD", None),
        ("S1D_IW_GRDH_1SDV_20260110T224512_20260110T224537_003000_000001_ABCD", (3000 - 42) % 175 + 1),
        # Nilai nyata CDSE (relativeOrbitNumber) untuk produk Live Lebak Selatan, 27-09-2026.
        ("S1D_IW_GRDH_1SDV_20260927T112236_20260927T112305_004762_008EC4_A3A7.SAFE", 171),
        ("garbage", None), (None, None)])
    def test_relative_orbit(self, pid, expected):
        assert wc.relative_orbit(pid) == expected

    def test_same_orbit(self):
        a = "S1A_IW_GRDH_1SDV_20240110T224512_20240110T224537_052036_064A8B_1A2B"
        b = "S1A_IW_GRDH_1SDV_20240122T224512_20240122T224537_052211_064F00_1A2B"   # +175 orbit = sama
        c = "S1A_IW_GRDH_1SDV_20240115T110000_20240115T110025_052110_064C00_1A2B"
        assert wc.same_orbit([a], [b]) is True
        assert wc.same_orbit([a], [c]) is False
        assert wc.same_orbit([a], ["unknown"]) is None

    def test_metadata_wins_over_formula(self):
        late = "S1C_IW_GRDH_1SDV_20260801T224512_20260801T224537_009000_000001_ABCD"
        assert wc.relative_orbit(late, {late + "_COG": 98}) == 98
        a = "S1A_IW_GRDH_1SDV_20240110T224512_20240110T224537_052036_064A8B_1A2B"
        assert wc.relative_orbit(a, {a: 5}) == 5            # metadata katalog didahulukan
        assert wc.same_orbit([late], [late], {late: 98}) is True


class TestPngAndMetrics:
    def test_png_colors_and_orbit_label(self, tmp_path):
        res = wc.compute(_vh(tmp_path, "cur", CUR), _vh(tmp_path, "prev", PREV), edge_buffer_m=0)
        out = tmp_path / "live" / "s1_water_change.png"
        legend = wc.render_png(res, out, orbit_differs=True, max_side=400)
        img = np.asarray(Image.open(out).convert("RGB"))
        assert img.shape[:2] == (400, 400)
        # Sel (2,3) air baru -> merah; sel (1,0) air surut -> hijau (tengah sel, jauh dari label).
        assert tuple(img[250, 350]) == (0xE0, 0x45, 0x45)
        assert tuple(img[150, 50]) == (0x2F, 0xA3, 0x6B)
        assert legend["warning"] == wc.ORBIT_WARNING
        assert not list(out.parent.glob("*.tmp"))          # atomic_path tidak meninggalkan sisa

    def test_metrics_rows(self, db_client, tmp_path):
        with db_client.session() as sess:
            ids = []
            for d in (date(2024, 1, 10), date(2024, 1, 22)):
                ids.append(sess.scalar(text("""INSERT INTO live_scenes (area_id, scene_date, status)
                                               VALUES (987654, :d, 'READY') RETURNING live_scene_id"""), {"d": d}))
            wc.save_metrics(sess, ids[1], ids[0], {"new_km2": 1.5, "receded_km2": 0.25, "persistent_km2": 3.0,
                                                   "valid_km2": 50.0}, same=False, source_date=date(2024, 1, 10))
            wc.save_metrics(sess, ids[1], ids[0], {"new_km2": 1.5, "receded_km2": 0.25, "persistent_km2": 3.0,
                                                   "valid_km2": 50.0}, same=False, source_date=date(2024, 1, 10))
            got = wc.load_metrics(sess, ids)
            sess.execute(text("DELETE FROM live_scenes WHERE area_id = 987654"))
        m = got[ids[1]]
        assert (m["new_km2"], m["receded_km2"], m["same_orbit"], m["ref_live_scene_id"]) == (1.5, 0.25, 0.0, ids[0])
        assert ids[0] not in got
        s = wc.sentence(m)
        assert s["text"].startswith("Menampilkan perubahan air radar (VH) dalam kondisi")
        assert "orbit berbeda" in s["text"]
        assert s["category"] == "alert"       # (1.5 - 0.25) / 50 = 2.5 poin persen >= 2
        assert wc.sentence(None)["category"] == "unavailable"


class TestRunsAsMonitorEtl:
    """Siklus Live berjalan sebagai monitor_etl: menulis ulang metrik scene
    (hapus + sisip) harus diizinkan GRANT (T3-27, ditemukan uji nyata)."""

    def test_rewrite_metrics_as_etl(self, etl_db_client, db_client):
        from etl import live_metrics as lmx
        with db_client.session() as sess:
            ids = [sess.scalar(text("""INSERT INTO live_scenes (area_id, scene_date, status)
                                       VALUES (987655, :d, 'READY') RETURNING live_scene_id"""), {"d": d})
                   for d in (date(2024, 2, 1), date(2024, 2, 13))]
        metrics = {"sentinel1": {"vv_mean_db": -11.5, "vh_mean_db": -18.2, "vh_water_pct": 7.5}, "modis": {}, "gpm": {}}
        try:
            for _ in range(2):          # kedua kali = menulis ulang (DELETE + INSERT)
                with etl_db_client.session() as sess:
                    lmx.save_scene_metrics(sess, ids[1], date(2024, 2, 13), metrics)
                    wc.save_metrics(sess, ids[1], ids[0], {"new_km2": 1.0, "receded_km2": 0.5,
                                                           "persistent_km2": 2.0, "valid_km2": 40.0},
                                    same=True, source_date=date(2024, 2, 1))
            with etl_db_client.session() as sess:
                got = wc.load_metrics(sess, ids)
                n = sess.scalar(text("SELECT count(*) FROM live_scene_metrics WHERE live_scene_id = :s"), {"s": ids[1]})
            assert got[ids[1]]["new_km2"] == 1.0 and got[ids[1]]["same_orbit"] == 1.0
            assert n == len(lmx.metric_rows(metrics, date(2024, 2, 13))[0]) + 5
        finally:
            with db_client.session() as sess:
                sess.execute(text("DELETE FROM live_scenes WHERE area_id = 987655"))


class TestOrbitMetadataTruncatedIds:
    def test_truncated_live_ids_resolve_through_satellite_scenes(self, db_client, sample_region):
        """live_scenes.s1_product_ids menyimpan nama terpotong ('…T112236_20');
        orbit tetap ditemukan lewat nama lengkap di satellite_scenes."""
        full = {"S1D_IW_GRDH_1SDV_20260927T112236_20260927T112305_004762_008EC4_A3A7.SAFE": None,
                "S1D_IW_GRDH_1SDV_20260922T111440_20260922T111505_004689_008C3D_9D0D.SAFE": 98}
        with db_client.session() as sess:
            for pid, rel in full.items():
                sess.execute(text("""INSERT INTO satellite_scenes (product_identifier, acquisition_datetime, bbox,
                                         region_id, relative_orbit)
                                     VALUES (:p, now(), ST_GeomFromText('POLYGON((106 -7,106.1 -7,106.1 -6.9,106 -6.9,106 -7))', 4326),
                                             :r, :rel) ON CONFLICT (product_identifier) DO NOTHING"""),
                             {"p": pid, "r": sample_region, "rel": rel})
            cur, prev = ["S1D_IW_GRDH_1SDV_20260927T112236_20"], ["S1D_IW_GRDH_1SDV_20260922T111440_20"]
            meta = wc.orbit_metadata(sess, cur + prev)
            sess.execute(text("DELETE FROM satellite_scenes WHERE product_identifier = ANY(:p)"), {"p": list(full)})
        assert sorted(meta.values()) == [98, 171]          # 171 dari rumus S1D, 98 dari metadata
        assert wc.same_orbit(cur, prev, meta) is False


class TestSwathEdge:
    def test_pixels_next_to_nodata_are_dropped_but_frame_is_not(self):
        from rasterio.transform import from_origin
        from rasterio.crs import CRS
        db = np.full((20, 20), -12.0)
        db[:, 15:] = np.nan                       # swath berakhir di kolom 15
        tf = from_origin(106.0, -6.9, 0.001, 0.001)   # ±110 m per piksel
        out = wc.mask_swath_edges(db, tf, CRS.from_epsg(4326), buffer_m=300)   # 3 piksel
        assert np.isnan(out[:, 12:15]).all() and np.isfinite(out[:, 11]).all()
        assert np.isfinite(out[0, 0]) and np.isfinite(out[19, 5])      # bingkai crop tidak terkikis
        assert wc.mask_swath_edges(db, tf, CRS.from_epsg(4326), buffer_m=0) is db
