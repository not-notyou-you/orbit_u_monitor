# etl/region_crop.py
"""Tile preview Live yang dipotong ke SATU kecamatan (Pantau Lokasi, M63).

PNG preview Live menutupi seluruh Live Area. Beranda menampilkan citra untuk
kecamatan yang dipantau saja, jadi dari PNG itu dibuat salinan:

* piksel di luar poligon kecamatan dibuat transparan (alpha 0; lubang
  poligon ikut transparan);
* gambar dipotong ke kotak pembatas kecamatan + sedikit tepi.

Georeferensi PNG dibaca dari ``live_scenes.previews.grid`` (empat sudut
WGS84 + CRS raster, etl/live_preview.py ``grid_dict``), bukan dari bbox
area: extent grid milik SCENE itu (lihat module10 ``grid_corners_wgs84``).
Affine dibangun ulang dari sudut kiri-atas, kanan-atas, dan kiri-bawah yang
diproyeksikan ke CRS raster; proyeksi titik poligon sama dengan
etl/admin_overlay.py, jadi potongan sejajar piksel dengan garis wilayah.

Hasilnya di-cache di ``data/_lokasi_cache`` (di luar folder preview dataset,
supaya galeri dan laporan yang membaca ``*.png`` di sana tidak ikut
memungutnya). Cache dianggap basi bila PNG asal lebih baru.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PAD_PX = 6


def cache_dir() -> Path:
    # Dibaca saat dipanggil: tests/conftest.py mengalihkan DATA_ROOT ke
    # direktori sementara.
    from etl import folder_manager as fm
    return fm.DATA_ROOT.parent / "_lokasi_cache"


def _polygons(geojson: dict):
    """[[cincin luar, lubang...], ...] dari Polygon/MultiPolygon GeoJSON."""
    t, coords = geojson.get("type"), geojson.get("coordinates") or []
    return coords if t == "MultiPolygon" else [coords] if t == "Polygon" else []


def _transform(grid: dict, size: tuple[int, int]):
    """Affine piksel PNG -> CRS raster dari empat sudut WGS84 grid."""
    from affine import Affine
    from etl.admin_overlay import _project

    (tl, tr, _br, bl) = grid["corners_wgs84"]
    xs, ys = _project([tl[0], tr[0], bl[0]], [tl[1], tr[1], bl[1]], grid.get("crs"))
    w, h = size
    return Affine((xs[1] - xs[0]) / w, (xs[2] - xs[0]) / h, xs[0],
                  (ys[1] - ys[0]) / w, (ys[2] - ys[0]) / h, ys[0])


def crop(src: Path, grid: dict, geojson: dict, out: Path) -> Path | None:
    """Tulis `out` = `src` dipotong ke poligon `geojson`. None bila poligon
    tidak jatuh di dalam gambar atau georeferensinya tidak lengkap."""
    from PIL import Image, ImageChops, ImageDraw
    from etl.admin_overlay import _project

    if not grid or len(grid.get("corners_wgs84") or []) != 4:
        return None
    polys = _polygons(geojson)
    if not polys:
        return None
    with Image.open(src) as im:
        img = im.convert("RGBA")
    w, h = img.size
    ia, ib, ic, id_, ie, if_ = (~_transform(grid, (w, h)))[:6]

    lons = [float(p[0]) for poly in polys for ring in poly for p in ring]
    lats = [float(p[1]) for poly in polys for ring in poly for p in ring]
    xs, ys = _project(lons, lats, grid.get("crs"))
    mask = Image.new("L", (w, h), 0)
    pen = ImageDraw.Draw(mask)
    at = 0
    for poly in polys:
        for i, ring in enumerate(poly):
            pts = [(ia * xs[j] + ib * ys[j] + ic, id_ * xs[j] + ie * ys[j] + if_)
                   for j in range(at, at + len(ring))]
            at += len(ring)
            if len(pts) >= 3:
                pen.polygon(pts, fill=255 if i == 0 else 0)
    box = mask.getbbox()
    if box is None:
        return None
    img.putalpha(ImageChops.multiply(img.getchannel("A"), mask))
    box = (max(0, box[0] - PAD_PX), max(0, box[1] - PAD_PX), min(w, box[2] + PAD_PX), min(h, box[3] + PAD_PX))
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.png")
    img.crop(box).save(tmp, optimize=False)
    tmp.replace(out)
    return out


def cached_crop(src: Path, grid: dict, geojson: dict, area_id: int, scene_date, key: str,
                region_id: int) -> Path | None:
    """Potongan dari cache, dibuat bila belum ada atau PNG asal lebih baru."""
    out = cache_dir() / str(area_id) / str(scene_date) / f"{key}_r{region_id}.png"
    try:
        if out.is_file() and out.stat().st_mtime >= Path(src).stat().st_mtime:
            return out
        return crop(Path(src), grid, geojson, out)
    except Exception as exc:
        logger.warning("[LOKASI] potongan %s kecamatan %s gagal: %s", key, region_id, exc)
        return None
