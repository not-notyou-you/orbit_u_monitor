# tests/test_live_preview_geo.py
"""
Georeferensi grid preview Live — yang dipakai halaman Relief 3D untuk
menempatkan PNG di atas DEM.

Yang dijaga di sini ada dua, dan keduanya pernah jadi jebakan:

1. `module10.grid_corners_wgs84` mengembalikan EMPAT sudut, bukan bbox. Grid
   preview hidup di CRS proyeksi scene (UTM), jadi persegi di sana bukan
   persegi di lon/lat. Kalau helper ini diam-diam "diluruskan" jadi bbox,
   citra akan tergeser terhadap batas kecamatan di peta — gejala yang sulit
   dilacak karena gambarnya tetap tampil.

2. `render_scene_previews` menyertakan sudut-sudut itu di hasilnya, satu entri
   per scene. Tanpa itu kartu Live tidak punya georeferensi sama sekali dan
   Relief 3D jatuh ke bbox daerah.

GeoTIFF-nya sintetis dan ditulis ke tmp_path; tidak ada database maupun data
dataset asli yang disentuh.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
import rasterio
from affine import Affine
from rasterio.crs import CRS
from rasterio.transform import from_origin

from etl import live_preview as lp
from etl import module10_generate_preview as m10

SCENE_DATE = date(2026, 7, 12)
# UTM 48S, pas untuk AOI Lebak/Banten — sengaja BUKAN EPSG:4326, karena justru
# proyeksinya yang membuat keempat sudut berbeda dari bbox.
UTM48S = "EPSG:32748"


def _write_utm_tif(path, array, transform):
    path.parent.mkdir(parents=True, exist_ok=True)
    array = array.astype("float32")
    with rasterio.open(
        path, "w", driver="GTiff",
        height=array.shape[0], width=array.shape[1], count=1,
        dtype="float32", crs=UTM48S, transform=transform, nodata=np.nan,
    ) as dst:
        dst.write(array, 1)
    return path


class _FakeFiles:
    """Pengganti live_monitor._LiveFiles: cuma dua atribut yang dipakai
    render_scene_previews (root untuk scratch, preview_dir untuk keluaran).
    Konstruktor aslinya menuntut dataset LIVE_AREA di database."""

    def __init__(self, root):
        self.root = root

    def preview_dir(self, scene_date):
        return self.root / "live" / scene_date.strftime("%Y%m%d")


def test_grid_corners_are_four_skewed_corners_not_a_bbox():
    grid = m10._PreviewGrid(
        Affine(20.0, 0, 600000.0, 0, -20.0, 9300000.0),
        CRS.from_string(UTM48S), 768, 500,
    )
    corners = m10.grid_corners_wgs84(grid)

    assert len(corners) == 4
    tl, tr, br, bl = corners
    # Urutan kiri-atas -> kanan-atas -> kanan-bawah -> kiri-bawah, seperti
    # `coordinates` image source MapLibre.
    assert tl[0] < tr[0] and bl[0] < br[0]      # kiri benar-benar di barat
    assert tl[1] > bl[1] and tr[1] > br[1]      # atas benar-benar di utara
    # AOI uji ada di Banten/Jawa Barat bagian selatan.
    assert all(105 < lon < 108 for lon, _ in corners)
    assert all(-7.5 < lat < -6 for _, lat in corners)
    # Inti helper ini: tepi atas TIDAK sejajar garis lintang. Kalau suatu saat
    # ini jadi nol, seseorang telah menggantinya dengan bbox.
    assert tl[1] != tr[1]


def test_render_scene_previews_records_grid_georeferencing(tmp_path):
    files = _FakeFiles(tmp_path / "dataset")
    transform = from_origin(600000.0, 9300000.0, 20.0, 20.0)
    # sigma0 linear positif: _read_s1_db mengubahnya ke dB sendiri.
    array = np.linspace(0.01, 0.6, 64 * 48, dtype="float32").reshape(48, 64)
    s1_dir = tmp_path / "s1"
    inputs = {
        "s1": [{
            "VV": _write_utm_tif(s1_dir / "vv.tif", array, transform),
            "VH": _write_utm_tif(s1_dir / "vh.tif", array * 0.5, transform),
        }],
    }

    # regions=[] (bukan None) supaya admin_overlay tidak mencoba memuat batas
    # kecamatan dari database: varian bergaris tidak diuji di sini.
    out = lp.render_scene_previews(files, SCENE_DATE, inputs, regions=[])

    assert set(out["items"]) >= {"s1_vv", "s1_vh"}, out["skipped"]
    grid = out["grid"]
    assert grid is not None
    assert grid["crs"].endswith("32748")
    corners = grid["corners_wgs84"]
    assert len(corners) == 4
    assert all(len(c) == 2 for c in corners)

    # Sudut harus cocok dengan grid PNG yang benar-benar dirender — bukan
    # dengan extent GeoTIFF sumbernya. Keduanya berbeda: _preview_shape
    # memperbesar raster kecil dengan faktor bulat (64x48 -> 768 px) dan
    # transform-nya diskalakan ikut.
    expected = m10.grid_corners_wgs84(
        m10._preview_grid(inputs["s1"][0]["VH"], lp.LIVE_MAX_SIDE)
    )
    assert corners == expected
    assert (grid["width"], grid["height"]) == (768, 576)


def test_grid_is_none_when_sentinel1_is_missing(tmp_path):
    """Tanpa S1 tidak ada PNG sama sekali, jadi tidak ada grid yang bisa
    dilaporkan. Konsumennya harus melihat None, bukan sudut-sudut basi."""
    files = _FakeFiles(tmp_path / "dataset")
    out = lp.render_scene_previews(files, SCENE_DATE, {"s1": []}, regions=[])
    assert out["items"] == {}
    assert out.get("grid") is None


# ---------------------------------------------------------------------------
# Backfill georeferensi scene lama (scripts/backfill_preview_grid.py)
# ---------------------------------------------------------------------------

def _s1_inputs(tmp_path, transform, shape=(48, 64)):
    array = np.linspace(0.01, 0.6, shape[0] * shape[1], dtype="float32").reshape(shape)
    d = tmp_path / "s1"
    return {"s1": [{
        "VV": _write_utm_tif(d / "vv.tif", array, transform),
        "VH": _write_utm_tif(d / "vh.tif", array * 0.5, transform),
    }]}


def test_backfill_grid_matches_what_the_renderer_produced(tmp_path):
    """Inti backfill: grid yang dihitung ULANG tanpa me-render harus identik
    dengan yang ditulis perender. Kalau tidak, menambal scene lama akan
    menggeser citranya terhadap PNG yang sudah ada di disk."""
    files = _FakeFiles(tmp_path / "dataset")
    transform = from_origin(600000.0, 9300000.0, 20.0, 20.0)
    inputs = _s1_inputs(tmp_path, transform)

    rendered = lp.render_scene_previews(files, SCENE_DATE, inputs, regions=[])
    grid, why = lp.scene_grid(files, SCENE_DATE, inputs)

    assert why is None and grid is not None
    assert lp.grid_dict(grid) == rendered["grid"]


def test_scene_grid_reports_why_instead_of_raising(tmp_path):
    """Scene yang rasternya sudah dibersihkan retensi harus dilaporkan sebagai
    alasan, bukan melempar: backfill memproses banyak scene dalam satu jalan."""
    files = _FakeFiles(tmp_path / "dataset")
    grid, why = lp.scene_grid(files, SCENE_DATE, {"s1": []})
    assert grid is None and why

    # VH hilang (hanya VV): grid preview Live selalu diambil dari VH.
    array = np.full((8, 8), 0.2, dtype="float32")
    only_vv = {"s1": [{"VV": _write_utm_tif(tmp_path / "s1" / "vv.tif", array,
                                            from_origin(600000.0, 9300000.0, 20.0, 20.0))}]}
    grid, why = lp.scene_grid(files, SCENE_DATE, only_vv)
    assert grid is None and "VH" in why


def test_backfill_size_guard_rejects_a_mismatched_png(tmp_path):
    """Penjaga ukuran: PNG yang dirender dari susunan raster lain tidak boleh
    ditambal grid baru -- citra akan tergeser tanpa gejala yang kelihatan."""
    from scripts.backfill_preview_grid import _existing_png, _png_size

    files = _FakeFiles(tmp_path / "dataset")
    transform = from_origin(600000.0, 9300000.0, 20.0, 20.0)
    inputs = _s1_inputs(tmp_path, transform)
    rendered = lp.render_scene_previews(files, SCENE_DATE, inputs, regions=[])
    items = rendered["items"]

    png = _existing_png(files, SCENE_DATE, items)
    assert png is not None
    grid, _ = lp.scene_grid(files, SCENE_DATE, inputs)
    # Jalur normal: ukuran PNG sama dengan grid, jadi aman ditulis.
    assert _png_size(png) == (grid.width, grid.height)

    # Raster sumber berganti ukuran (mis. jumlah frame berubah) -> grid baru
    # tidak lagi cocok dengan PNG yang ada, dan itulah yang harus terdeteksi.
    other = _s1_inputs(tmp_path / "lain", transform, shape=(32, 32))
    grid2, _ = lp.scene_grid(files, SCENE_DATE, other)
    assert _png_size(png) != (grid2.width, grid2.height)


def test_backfill_skips_scene_without_png_on_disk(tmp_path):
    """Manifest menyebut berkas, disknya tidak punya -> tidak ada pembanding
    ukuran, jadi scene itu dilewati, bukan ditulis percaya-percaya."""
    from scripts.backfill_preview_grid import _existing_png

    files = _FakeFiles(tmp_path / "dataset")
    assert _existing_png(files, SCENE_DATE, {"s1_vh": {"file": "s1_vh.png"}}) is None
