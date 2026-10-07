# tests/test_aoi_coverage_gate.py
"""
Gerbang kelengkapan AOI (etl/aoi_coverage.py) — penjaga agar scene yang
Sentinel-1-nya cuma menutup sepotong AOI tidak pernah masuk Daerah Live.

Kenapa gerbang ini ada: sebagian orbit S1 hanya menyerempet tepi AOI. Scene
tanggal itu menghasilkan preview terpotong DAN metrik yang dihitung dari
wilayah berbeda dengan tanggal lain, sehingga grafik antar tanggal diam-diam
membandingkan dua daerah yang tidak sama. Pada AOI GMLS bedanya tajam: orbit
yang menyerempet ~30%, yang melintas penuh ~99-100%.

Tiga hal yang dijaga:

1. `scene_coverage` menghitung GABUNGAN frame, bukan per frame. Satu lintasan
   bisa terbelah jadi dua frame yang sendiri-sendiri sebagian tapi bersama
   menutup penuh — frame seperti itu tidak boleh ditolak.

2. Nol pada sigma0 linear dibaca sebagai di luar swath, bukan sebagai data.
   Kalau tidak, raster yang separuhnya nol akan dilaporkan 100% dan gerbangnya
   jadi hiasan.

3. `preview_grid` memberi grid yang SAMA untuk footprint S1 yang berbeda-beda.
   Itu seluruh gunanya: sebelum ini grid diturunkan dari footprint, jadi
   ukuran PNG berganti tiap tanggal dan citranya tidak bisa ditumpuk.

GeoTIFF-nya sintetis di tmp_path; tidak ada database atau dataset asli yang
disentuh.
"""

from __future__ import annotations

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from etl import aoi_coverage as ac

# AOI persegi 1x1 derajat, sengaja sederhana supaya porsi yang diharapkan bisa
# dihitung di kepala (separuh = 0.5).
AOI = "POLYGON ((100 -7, 100 -6, 101 -6, 101 -7, 100 -7))"
RES = 0.01


def _tif(path, array, west=100.0, north=-6.0, res=RES, crs="EPSG:4326"):
    path.parent.mkdir(parents=True, exist_ok=True)
    array = np.asarray(array, dtype="float32")
    with rasterio.open(path, "w", driver="GTiff", height=array.shape[0],
                       width=array.shape[1], count=1, dtype="float32",
                       crs=crs, transform=from_origin(west, north, res, res),
                       nodata=np.nan) as dst:
        dst.write(array, 1)
    return path


class TestSceneCoverage:
    def test_full_scene_covers_the_whole_aoi(self, tmp_path):
        arr = np.full((100, 100), 0.05, dtype="float32")
        frames = [{"VH": _tif(tmp_path / "full_VH.tif", arr)}]
        assert ac.scene_coverage(frames, AOI) == pytest.approx(1.0, abs=0.01)

    def test_half_scene_is_reported_as_half(self, tmp_path):
        """Raster yang hanya menutup separuh barat AOI."""
        arr = np.full((100, 50), 0.05, dtype="float32")
        frames = [{"VH": _tif(tmp_path / "half_VH.tif", arr)}]
        assert ac.scene_coverage(frames, AOI) == pytest.approx(0.5, abs=0.02)

    def test_two_partial_frames_are_counted_together(self, tmp_path):
        """Dua frame satu lintasan: masing-masing separuh, bersama penuh.

        Ini kasus yang membuat keputusan harus per TANGGAL, bukan per frame —
        memutuskan per frame akan membuang lintasan yang sebenarnya lengkap."""
        west = np.full((100, 50), 0.05, dtype="float32")
        east = np.full((100, 50), 0.05, dtype="float32")
        frames = [
            {"VH": _tif(tmp_path / "w_VH.tif", west, west=100.0)},
            {"VH": _tif(tmp_path / "e_VH.tif", east, west=100.5)},
        ]
        assert ac.scene_coverage(frames, AOI) == pytest.approx(1.0, abs=0.02)

    def test_linear_zeros_are_outside_the_swath_not_data(self, tmp_path):
        """sigma0 linear: nol = di luar swath.

        Raster di sini menutup AOI secara geometris tapi separuhnya nol, jadi
        cakupan sebenarnya 50% — bukan 100%."""
        arr = np.full((100, 100), 0.05, dtype="float32")
        arr[:, 50:] = 0.0
        frames = [{"VH": _tif(tmp_path / "zeros_VH.tif", arr)}]
        assert ac.scene_coverage(frames, AOI) == pytest.approx(0.5, abs=0.02)

    def test_nodata_does_not_count_as_coverage(self, tmp_path):
        arr = np.full((100, 100), 0.05, dtype="float32")
        arr[:, 50:] = np.nan
        frames = [{"VH": _tif(tmp_path / "nan_VH.tif", arr)}]
        assert ac.scene_coverage(frames, AOI) == pytest.approx(0.5, abs=0.02)

    def test_no_frames_gives_none_not_zero(self):
        """None, bukan 0.0: tanpa bukti pemanggil tidak boleh menyimpulkan
        scene-nya terpotong dan menghapus berkasnya."""
        assert ac.scene_coverage([], AOI) is None
        assert ac.scene_coverage(None, AOI) is None


class TestPreviewGrid:
    def test_grid_is_identical_whatever_the_scene_footprint(self):
        """Inti perubahannya: bingkai ditentukan AOI, bukan footprint S1."""
        grids = [ac.preview_grid(AOI, "EPSG:4326", 768) for _ in range(3)]
        first = grids[0]
        for g in grids[1:]:
            assert (g.width, g.height) == (first.width, first.height)
            assert tuple(g.transform)[:6] == tuple(first.transform)[:6]

    def test_grid_covers_the_entire_aoi(self):
        g = ac.preview_grid(AOI, "EPSG:4326", 768)
        west, north = g.transform * (0, 0)
        east, south = g.transform * (g.width, g.height)
        assert west <= 100.0 and east >= 101.0
        assert north >= -6.0 and south <= -7.0

    def test_longest_side_is_about_max_side(self):
        g = ac.preview_grid(AOI, "EPSG:4326", 768)
        # Boleh lebih satu piksel: tepinya di-snap ke kelipatan resolusi supaya
        # grid tidak bergeser antar tanggal, dan menutup AOI utuh menang atas
        # angka yang bulat.
        assert 768 <= max(g.width, g.height) <= 769

    def test_refine_divides_exactly_so_the_png_matches_the_preview(self):
        """Grid halus peta perubahan air harus turun PERSIS ke ukuran preview.

        Kalau tidak, s1_water_change jadi satu-satunya tile yang selisih satu
        piksel dan tidak setumpuk dengan tujuh lainnya."""
        base = ac.preview_grid(AOI, "EPSG:4326", 768)
        fine = ac.refine(base, 3)
        assert (fine.width, fine.height) == (base.width * 3, base.height * 3)
        assert fine.transform.c == base.transform.c
        assert fine.transform.f == base.transform.f
        assert fine.transform.a == pytest.approx(base.transform.a / 3)
