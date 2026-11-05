"""Gerbang kelengkapan AOI untuk Daerah Live: berapa persen AOI yang benar-benar
punya piksel Sentinel-1 valid, dan grid preview tetap seluas AOI.
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

SAMPLE_SIDE = 384

READ_MAX_SIDE = 1024


def min_coverage(sess) -> float:
    """Ambang cakupan AOI dari app_settings."""
    from etl.settings import get_setting

    return float(get_setting(sess, SETTING_KEY))


def _sample_points(bbox_wkt: str, side: int = SAMPLE_SIDE):
    """(lon, lat) titik cuplikan DI DALAM poligon AOI."""
    from shapely import wkt as shapely_wkt
    from shapely.geometry import Point

    aoi = shapely_wkt.loads(bbox_wkt)
    if aoi.is_empty or aoi.area <= 0:
        return None, None
    west, south, east, north = aoi.bounds
    lon, lat = np.meshgrid(np.linspace(west, east, side),
                           np.linspace(south, north, side))
    lon, lat = lon.ravel(), lat.ravel()
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
    valid = data[~masked] if (~masked).any() else np.array([])
    if valid.size and np.median(valid) > 0:
        good &= data[r, c] > 0
    out[inside] = good
    return out


def scene_coverage(frames, bbox_wkt: str, band: str = "VH") -> float | None:
    """Porsi AOI (0..1) yang tertutup piksel valid GABUNGAN semua frame."""
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


def preview_grid(bbox_wkt: str, crs, max_side: int):
    """Grid PNG yang menutup AOI, SAMA untuk setiap tanggal."""
    from etl.module10_generate_preview import _PreviewGrid
    from shapely import wkt as shapely_wkt

    aoi = shapely_wkt.loads(bbox_wkt)
    west, south, east, north = aoi.bounds
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
    """Grid yang sama dengan `grid` tapi `factor` kali lebih halus."""
    from etl.module10_generate_preview import _PreviewGrid

    t = grid.transform
    return _PreviewGrid(
        Affine(t.a / factor, 0.0, t.c, 0.0, t.e / factor, t.f),
        grid.crs, grid.width * factor, grid.height * factor,
    )
