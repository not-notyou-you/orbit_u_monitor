# tests/test_hydromet_aggregate.py
"""Zonal statistics berbobot luas irisan (PIPELINE.md §3.3) dengan raster sintetis.

Setiap jawaban dihitung dengan tangan dari geometri SYNTH_KECAMATAN di
conftest (grid 0.1 derajat, origin 106.0/-6.5), bukan dari kode yang diuji.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest
from shapely.geometry import box
from sqlalchemy import text

from etl import hydromet_aggregate as ha
from tests.conftest import SYNTH_KECAMATAN, write_synthetic_raster

ND = -9999.9


def _regions():
    return [{"region_id": i, "geom": box(*b)} for i, b in enumerate(SYNTH_KECAMATAN.values(), start=1)]


def _grid(fill=0.0):
    return np.full((4, 4), fill, dtype="float32")


@pytest.fixture(autouse=True)
def _fresh_cache():
    ha.clear_cache()
    yield
    ha.clear_cache()


class TestMean:
    def test_partial_cells_weighted_by_overlap(self, tmp_path):
        # TST001: 1/4 sel (0,0) + 3/4 sel (0,1), lintang pusat irisan sama
        # (-6.55) -> rerata = (A + 3B) / 4.
        g = _grid()
        g[0, 0], g[0, 1] = 10.0, 30.0
        res = ha.aggregate_raster(write_synthetic_raster(tmp_path / "r.tif", g), _regions(), "MEAN")
        assert res[1].value == pytest.approx((10 + 3 * 30) / 4, abs=1e-9)
        assert res[1].valid_fraction == 1.0
        # Sel (0,2) hanya bersinggungan di tepi x=106.2 -> tidak ikut.
        assert res[1].n_cells == 2

    def test_exact_cell_ignores_edge_touching_neighbours(self, tmp_path):
        g = _grid(999.0)
        g[1, 2] = 42.0
        res = ha.aggregate_raster(write_synthetic_raster(tmp_path / "r.tif", g), _regions(), "MEAN")
        assert res[2].value == pytest.approx(42.0, abs=1e-9)
        assert res[2].n_cells == 1

    def test_cos_latitude_weighting_across_rows(self, tmp_path):
        # TST003: seperempat dari sel (1,0),(1,1) [pusat irisan lat -6.675]
        # dan (2,0),(2,1) [lat -6.725]. Luas irisan sama (0.05 x 0.05).
        g = _grid()
        g[1, 0], g[1, 1], g[2, 0], g[2, 1] = 10.0, 20.0, 30.0, 40.0
        res = ha.aggregate_raster(write_synthetic_raster(tmp_path / "r.tif", g), _regions(), "MEAN")
        cu, cl = math.cos(math.radians(-6.675)), math.cos(math.radians(-6.725))
        expected = (cu * (10 + 20) + cl * (30 + 40)) / (2 * cu + 2 * cl)
        assert res[3].value == pytest.approx(expected, abs=1e-9)
        # Bobot lintang memang berpengaruh (beda dari rerata polos 25).
        assert res[3].value != pytest.approx(25.0, abs=1e-6)


class TestValidFraction:
    def test_nodata_cell_lowers_valid_fraction(self, tmp_path):
        g = _grid()
        g[0, 0], g[0, 1] = 8.0, ND
        res = ha.aggregate_raster(write_synthetic_raster(tmp_path / "r.tif", g), _regions(), "MEAN")
        assert res[1].valid_fraction == pytest.approx(0.25, abs=1e-4)
        assert res[1].value == pytest.approx(8.0, abs=1e-9)

    def test_below_min_valid_fraction_gives_null(self, tmp_path):
        g = _grid()
        g[1, 0], g[1, 1], g[2, 0], g[2, 1] = ND, ND, ND, 5.0   # 1 dari 4 seperempat (bobot ~0.2497)
        path = write_synthetic_raster(tmp_path / "r.tif", g)
        res = ha.aggregate_raster(path, _regions(), "MEAN", min_valid_fraction=0.3)
        assert res[3].value is None
        cu, cl = math.cos(math.radians(-6.675)), math.cos(math.radians(-6.725))
        assert res[3].valid_fraction == pytest.approx(round(cl / (2 * cu + 2 * cl), 4), abs=1e-4)

    def test_all_nodata(self, tmp_path):
        res = ha.aggregate_raster(write_synthetic_raster(tmp_path / "r.tif", _grid(ND)), _regions(), "MEAN")
        assert all(r.value is None and r.valid_fraction == 0.0 for r in res.values())

    def test_nan_counts_as_invalid(self, tmp_path):
        g = _grid()
        g[0, 0], g[0, 1] = np.nan, 12.0
        res = ha.aggregate_raster(write_synthetic_raster(tmp_path / "r.tif", g, nodata=None), _regions(), "MEAN")
        assert res[1].valid_fraction == pytest.approx(0.75, abs=1e-4)
        assert res[1].value == pytest.approx(12.0, abs=1e-9)


class TestFraction:
    def test_flood_classes_2_and_3_over_valid_cells(self, tmp_path):
        # TST003 menyentuh 4 sel dengan bobot nyaris sama; kelas
        # (1,0)=3 air banjir, (1,1)=1 bukan, (2,0)=255 nodata, (2,1)=2 air.
        g = np.zeros((4, 4), dtype="uint8")
        g[1, 0], g[1, 1], g[2, 0], g[2, 1] = 3, 1, 255, 2
        path = write_synthetic_raster(tmp_path / "f.tif", g, nodata=255, dtype="uint8")
        res = ha.aggregate_raster(path, _regions(), "FRACTION")
        cu, cl = math.cos(math.radians(-6.675)), math.cos(math.radians(-6.725))
        assert res[3].value == pytest.approx((cu + cl) / (2 * cu + cl) * 100, abs=1e-6)
        assert res[3].valid_fraction == pytest.approx(round((2 * cu + cl) / (2 * cu + 2 * cl), 4), abs=1e-4)


class TestWorstRun:
    @pytest.mark.parametrize("runs,expected", [(["F"], "F"), (["F", "L"], "L"), (["L", "E", "F"], "E"),
                                               ([], None), (["X"], None)])
    def test_worst(self, runs, expected):
        assert ha.worst_run(runs) == expected


class TestUpsertFinalBeatsLate:
    """ON CONFLICT hanya menimpa bila run baru tidak lebih buruk (F > L > E)
    atau nilai lama NULL; NULL tidak pernah menimpa nilai."""

    D = date(2024, 2, 1)

    def _value(self, db_client, region_id):
        with db_client.session() as sess:
            return sess.execute(text("""
                SELECT o.value, o.run_type FROM region_observations o
                JOIN spectral_bands b USING (band_id)
                WHERE o.region_id = :r AND b.band_code = 'RAIN_24H' AND o.obs_date = :d"""),
                {"r": region_id, "d": self.D}).one()

    def _put(self, db_client, region_id, value, run, vf=1.0):
        with db_client.session() as sess:
            return ha.upsert_observations(sess, "RAIN_24H", self.D, {region_id: ha.ZonalResult(value, vf, 1)},
                                          run_type=run)

    def test_sequence(self, db_client, synthetic_aoi):
        rid = synthetic_aoi["TST002"]
        assert self._put(db_client, rid, 10.0, "L") == 1
        assert self._put(db_client, rid, 20.0, "E") == 0          # lebih buruk: ditolak
        assert tuple(self._value(db_client, rid)) == (pytest.approx(10.0), "L")
        assert self._put(db_client, rid, 11.0, "L") == 1          # run sama: dihitung ulang
        assert self._put(db_client, rid, 30.0, "F") == 1          # Final menggantikan Late
        assert self._put(db_client, rid, 40.0, "L") == 0
        assert self._put(db_client, rid, None, "F", vf=0.0) == 0  # NULL tidak menimpa nilai
        assert tuple(self._value(db_client, rid)) == (pytest.approx(30.0), "F")

    def test_null_is_replaced_by_any_run(self, db_client, synthetic_aoi):
        rid = synthetic_aoi["TST001"]
        assert self._put(db_client, rid, None, "F", vf=0.05) == 1
        assert self._put(db_client, rid, 7.5, "E") == 1
        assert tuple(self._value(db_client, rid)) == (pytest.approx(7.5), "E")

    def test_range_trigger_rejects_impossible_value(self, db_client, synthetic_aoi):
        with pytest.raises(Exception, match="out of range"):
            self._put(db_client, synthetic_aoi["TST003"], 5000.0, "F")


class TestRegionsFromShapefile:
    def test_lebak_cod_ab_has_28_kecamatan(self):
        from etl import regions as rg
        adm3 = rg.DEFAULT_COD_AB_DIR / "idn_admin3.shp"
        if not adm3.exists():
            pytest.skip("COD-AB shapefile not present in data/external/cod-ab-idn")
        feats = rg.read_cod_ab(adm3, 3)
        names = {f.name for f in feats}
        assert len(feats) == 28
        assert {"Bayah", "Panggarangan", "Cihara", "Malingping"} <= names
        assert all(f.pcode.startswith("ID3602") and f.parent_pcode == "ID3602" for f in feats)
