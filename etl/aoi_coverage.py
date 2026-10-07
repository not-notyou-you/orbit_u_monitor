# etl/aoi_coverage.py
"""Gerbang kelengkapan AOI untuk Daerah Live: berapa persen AOI yang benar-benar
punya piksel Sentinel-1 valid, dan grid preview tetap seluas AOI.

KENAPA ADA MODUL INI
Sentinel-1 melintas dalam swath. Sebagian orbit hanya menyerempet tepi AOI,
jadi tanggalnya menghasilkan scene yang isinya cuma sepotong AOI -- preview
terpotong, metrik dihitung dari wilayah yang berbeda dengan tanggal lain, dan
grafik antar tanggal membandingkan dua daerah yang tidak sama. Scene seperti
itu tidak bisa "dilengkapi": pada tanggal itu satelitnya memang tidak pernah
melewati sisa AOI. Satu-satunya perlakuan yang benar adalah menolaknya.

DUA LAPIS, DUA ALAT UKUR YANG BEDA
1. Pra-unduh -- `module5_orchestrator._drop_dates_barely_covering_aoi` memakai
   footprint dari katalog CDSE. Murah (tidak perlu berkas) tapi OPTIMIS:
   footprint adalah batas luar produk, sedangkan di dalamnya masih ada NoData
   (frame 20260910T111439: footprint utuh, isinya 56% kosong).
2. Pasca-ingest -- `scene_coverage()` di sini, dihitung dari raster yang sudah
   diunduh. Inilah ukuran yang mengikat: ia melihat piksel, bukan metadata.

Keduanya memakai ambang yang sama (`live.min_aoi_coverage`). Lapis 1 menghemat
kuota; lapis 2 yang memberi jaminan.

SATUAN LUAS
Porsi dihitung dengan mencuplik AOI pada kisi lon/lat seragam, sama seperti
`module1_download.aoi_coverage` yang membandingkan luas dalam derajat: AOI Live
selebar <1 derajat di dekat ekuator, jadi distorsi derajat->meter di dalamnya
dapat diabaikan. Yang dibandingkan selalu dua angka dari konvensi yang sama.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.warp import transform as warp_transform

logger = logging.getLogger(__name__)

SETTING_KEY = "live.min_aoi_coverage"

# Sisi kisi cuplikan. 384x384 (~147 rb titik) sudah memberi porsi dengan galat
# jauh di bawah 1% untuk AOI sebesar ini, sementara bedanya scene lengkap (99%)
# dan terpotong (30%) puluhan persen -- presisi lebih tinggi tidak mengubah
# keputusan apa pun, hanya memperlambat tiap siklus.
SAMPLE_SIDE = 384

# Sisi terpanjang pembacaan raster saat mencuplik. Cakupan adalah sifat
# GEOMETRIS (ada data / tidak), bukan radiometrik, jadi membaca level piramida
# yang kasar sudah cukup -- dan menjaga raster 7000x6000 tidak masuk memori.
READ_MAX_SIDE = 1024


def min_coverage(sess) -> float:
    """Ambang cakupan AOI dari app_settings."""
    from etl.settings import get_setting

    return float(get_setting(sess, SETTING_KEY))


# ---------------------------------------------------------------------------
# Cuplikan AOI
# ---------------------------------------------------------------------------

def _sample_points(bbox_wkt: str, side: int = SAMPLE_SIDE):
    """(lon, lat) titik cuplikan DI DALAM poligon AOI.

    AOI Live selalu bbox, tapi poligonnya diuji betulan supaya modul ini tetap
    benar kalau suatu saat AOI berbentuk lain."""
    from shapely import wkt as shapely_wkt
    from shapely.geometry import Point

    aoi = shapely_wkt.loads(bbox_wkt)
    if aoi.is_empty or aoi.area <= 0:
        return None, None
    west, south, east, north = aoi.bounds
    lon, lat = np.meshgrid(np.linspace(west, east, side),
                           np.linspace(south, north, side))
    lon, lat = lon.ravel(), lat.ravel()
    # Untuk bbox (kasus nyata) semua titik di dalam; uji ini baru berarti kalau
    # AOI non-persegi, dan harganya sekali per scene.
    if aoi.equals(aoi.envelope):
        return lon, lat
    inside = np.fromiter((aoi.covers(Point(x, y)) for x, y in zip(lon, lat)),
                         bool, lon.size)
    return lon[inside], lat[inside]


def _valid_at(path: Path, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Mask boolean: titik mana yang jatuh pada piksel valid raster `path`."""
    with rasterio.open(path) as src:
        scale = min(1.0, READ_MAX_SIDE / max(src.width, src.height))
        out_h = max(1, int(src.height * scale))
        out_w = max(1, int(src.width * scale))
        arr = src.read(1, out_shape=(out_h, out_w), masked=True)
        tf = src.transform * Affine.scale(src.width / out_w, src.height / out_h)
        xs, ys = warp_transform("EPSG:4326", src.crs, list(lon), list(lat))

    rows, cols = rasterio.transform.rowcol(tf, xs, ys)
    rows, cols = np.asarray(rows), np.asarray(cols)
    inside = (rows >= 0) & (rows < out_h) & (cols >= 0) & (cols < out_w)

    data = np.asarray(arr.data, dtype=np.float64)
    masked = np.ma.getmaskarray(arr)
    out = np.zeros(lon.size, dtype=bool)
    if not inside.any():
        return out

    r, c = rows[inside], cols[inside]
    good = ~masked[r, c] & np.isfinite(data[r, c])
    # sigma0 linear: nol BUKAN nilai sah, itu penanda di luar swath (lihat
    # live_preview._read_s1_db). Data yang sudah dB bermedian negatif dan nol
    # di sana sah, jadi uji ini hanya dipakai kalau rasternya linear.
    valid = data[~masked] if (~masked).any() else np.array([])
    if valid.size and np.median(valid) > 0:
        good &= data[r, c] > 0
    out[inside] = good
    return out


def scene_coverage(frames, bbox_wkt: str, band: str = "VH") -> float | None:
    """Porsi AOI (0..1) yang tertutup piksel valid GABUNGAN semua frame.

    `frames` = keluaran live_metrics.s1_frames(): [{VV: path, VH: path}].
    Gabungan, bukan per frame: satu pass bisa terbelah jadi dua frame yang
    sendiri-sendiri cuma sebagian tapi bersama menutup penuh -- persis alasan
    `_drop_dates_barely_covering_aoi` memutuskan per tanggal.

    None kalau tidak ada frame yang bisa dibaca: tanpa bukti, pemanggil tidak
    boleh menyimpulkan apa pun (lihat pemakaiannya di live_cycle)."""
    paths = [f[band] for f in (frames or []) if band in f]
    if not paths:
        return None

    lon, lat = _sample_points(bbox_wkt)
    if lon is None or lon.size == 0:
        return None

    covered = np.zeros(lon.size, dtype=bool)
    read_any = False
    for p in paths:
        try:
            covered |= _valid_at(Path(p), lon, lat)
            read_any = True
        except Exception:
            logger.exception("[AOI] gagal membaca %s untuk cakupan AOI", p)
    return float(covered.mean()) if read_any else None


# ---------------------------------------------------------------------------
# Grid preview seluas AOI
# ---------------------------------------------------------------------------

def preview_grid(bbox_wkt: str, crs, max_side: int):
    """Grid PNG yang menutup AOI, SAMA untuk setiap tanggal.

    Sebelumnya grid preview diturunkan dari footprint Sentinel-1, jadi extent
    dan ukuran PNG berubah tiap tanggal (768x633, 768x632, 438x768). Di layar
    monitoring yang orangnya bolak-balik antar tanggal, citranya jadi bergeser
    dan tidak bisa ditumpuk. Dengan AOI sebagai kanvas, keempat sudut dan
    ukurannya identik selamanya; bagian tanpa data jadi transparan di bingkai
    yang tetap, dan "terpotong" terbaca sebagai kekosongan, bukan sebagai
    gambar berbentuk lain.

    `crs` diambil dari raster scene, bukan dipilih di sini: COG PROCESSED
    Daerah Live ber-CRS EPSG:4326, dan menyamakannya dengan sumber menjaga
    `grid_corners_wgs84` di module10 berlaku apa adanya. Konsekuensinya piksel
    persegi dalam DERAJAT, bukan meter -- sama seperti perilaku lama yang
    memakai transform raster langsung, jadi bukan perubahan; di lintang AOI
    Live (<10 derajat) regangannya di bawah 1%.

    Tepinya di-snap ke kelipatan resolusi: tanpa itu, beda pembulatan sepersen
    piksel antar tanggal cukup untuk menggeser grid satu piksel. Lebarnya
    karena itu bisa satu piksel lebih dari `max_side` (769, bukan 768) --
    menutup AOI utuh lebih penting daripada angka yang bulat.
    """
    from etl.module10_generate_preview import _PreviewGrid
    from shapely import wkt as shapely_wkt

    aoi = shapely_wkt.loads(bbox_wkt)
    west, south, east, north = aoi.bounds
    # Tepi AOI dirapatkan sebelum diproyeksikan: garis lurus di lon/lat bukan
    # garis lurus di UTM, jadi mengambil 4 sudut saja bisa memotong tepinya
    # beberapa ratus meter (alasan yang sama dengan grid_corners_wgs84).
    n = 32
    lons = np.concatenate([np.linspace(west, east, n), np.linspace(west, east, n),
                           np.full(n, west), np.full(n, east)])
    lats = np.concatenate([np.full(n, south), np.full(n, north),
                           np.linspace(south, north, n), np.linspace(south, north, n)])
    xs, ys = warp_transform("EPSG:4326", crs, list(lons), list(lats))
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)

    res = max(x1 - x0, y1 - y0) / max_side
    x0 = math.floor(x0 / res) * res
    y1 = math.ceil(y1 / res) * res
    width = max(1, math.ceil((x1 - x0) / res))
    height = max(1, math.ceil((y1 - y0) / res))
    return _PreviewGrid(Affine(res, 0.0, x0, 0.0, -res, y1), crs, width, height)


def refine(grid, factor: int):
    """Grid yang sama dengan `grid` tapi `factor` kali lebih halus.

    Dipakai peta perubahan air: metriknya (luas km2) dihitung di grid halus,
    PNG-nya harus satu bingkai dengan preview lain. Karena grid halus ini
    turunan BULAT dari grid preview -- titik asal sama, resolusi dibagi rata --
    menurunkannya kembali `factor` kali menghasilkan ukuran preview PERSIS,
    bukan selisih satu piksel hasil pembulatan dua grid yang dihitung sendiri-
    sendiri.
    """
    from etl.module10_generate_preview import _PreviewGrid

    t = grid.transform
    return _PreviewGrid(
        Affine(t.a / factor, 0.0, t.c, 0.0, t.e / factor, t.f),
        grid.crs, grid.width * factor, grid.height * factor,
    )
