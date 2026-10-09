# etl/s1_observations.py
"""Sentinel-1 per kecamatan -> ``region_observations`` (M58).

Dataset utama memegang SATU deret waktu per sumber: GPM/MODIS harian ditulis
Job Hidromet (etl/hydromet_job.py), Sentinel-1 ditulis di sini setiap kali
scene Live selesai difinalisasi (etl/live_cycle.finalize_scene), termasuk
selama backfill. Dengan begitu grafik, statistik, dan laporan membaca
satu tabel untuk ketiga satelit.

Band yang ditulis (spectral_bands, sumber SENTINEL1):

    VV, VH      rata-rata backscatter (dB) per kecamatan
    WATER_PCT   persen luas dengan VH < ``water.vh_threshold_db`` (-20 dB)

Raster S1 (~10 m) diturunkan dulu ke grid AOI ``GRID_DEG`` (~100 m) dengan
rata-rata di ranah linear, semua frame tanggal itu digabung ke grid yang sama.
Zonal-nya memakai fungsi yang sama dengan GPM/MODIS (bobot luas irisan,
``hydromet.min_valid_fraction``), jadi angkanya bisa disandingkan.
"""

from __future__ import annotations

import logging
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject
from sqlalchemy import text

from etl import hydromet_aggregate as ha
from etl import regions as rg
from etl.settings import get_setting

logger = logging.getLogger(__name__)

# ~100 m di ekuator: cukup halus untuk kecamatan (puluhan km²), dan grid AOI
# GMLS jadi ±740 x 610 sel -- ringan untuk bobot irisan per kecamatan.
GRID_DEG = 0.0009
WATER_CLASS = ha.FLOOD_WATER_CLASSES[0]
NODATA_CLASS = ha.FLOOD_NODATA


def _aoi_grid(bbox: tuple[float, float, float, float]):
    x0, y0, x1, y1 = bbox
    width = int(np.ceil((x1 - x0) / GRID_DEG))
    height = int(np.ceil((y1 - y0) / GRID_DEG))
    return from_origin(x0, y1, GRID_DEG, GRID_DEG), (height, width)


def _to_grid(path: Path, transform, shape) -> np.ndarray:
    """Satu COG S1 (sigma0 linear atau dB) -> grid AOI, LINEAR, NaN = kosong."""
    out = np.full(shape, np.nan, dtype=np.float32)
    with rasterio.open(path) as src:
        data = src.read(1).astype(np.float32)
        nodata = src.nodata
        valid = np.isfinite(data)
        if nodata is not None and np.isfinite(nodata):
            valid &= data != nodata
        finite = data[valid]
        is_db = finite.size > 0 and float(np.median(finite)) < 0
        if is_db:
            data = np.where(valid, 10.0 ** (data / 10.0), np.nan)
        else:
            # 0 = di luar swath pada GOLD linear.
            data = np.where(valid & (data > 0), data, np.nan)
        reproject(source=data, destination=out, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=transform, dst_crs="EPSG:4326", src_nodata=np.nan, dst_nodata=np.nan,
                  resampling=Resampling.average)
    return out


def mosaic(paths: list[Path], transform, shape) -> np.ndarray:
    """Semua frame di grid AOI, dirata-rata di ranah linear lalu ke dB;
    sel yang tidak tertutup frame mana pun = NaN."""
    stack = [_to_grid(p, transform, shape) for p in paths]
    if not stack:
        return np.full(shape, np.nan, dtype=np.float32)
    with warnings.catch_warnings(), np.errstate(divide="ignore", invalid="ignore"):
        warnings.simplefilter("ignore", category=RuntimeWarning)  # sel kosong di semua frame
        lin = np.nanmean(np.stack(stack), axis=0)
        return np.where(lin > 0, 10.0 * np.log10(lin), np.nan).astype(np.float32)


def _product_id(sess, path: Path) -> int | None:
    return sess.scalar(text("""
        SELECT product_id FROM data_products WHERE file_name = :n AND is_valid
        ORDER BY product_id DESC LIMIT 1"""), {"n": path.name})


def record_scene(db, scene_date: date, frames: list[dict[str, Path]],
                 job_id: int | None = None) -> int:
    """Tulis VV/VH/WATER_PCT per kecamatan untuk satu tanggal S1.

    ``frames`` = keluaran ``live_metrics.s1_frames`` ([{VV: path, VH: path}]).
    Mengembalikan jumlah baris yang ditulis. Idempoten (upsert)."""
    if not frames:
        return 0
    with db.session() as sess:
        ds = rg.hydromet_dataset(sess)
        regions = rg.aoi_regions(sess)
        min_vf = float(get_setting(sess, "hydromet.min_valid_fraction"))
        thr = float(get_setting(sess, "water.vh_threshold_db"))
    if ds is None or not regions:
        logger.warning("[S1OBS] dataset utama/kecamatan AOI belum ada, %s dilewati", scene_date)
        return 0
    transform, shape = _aoi_grid(ds["bbox"])
    from shapely import from_wkb
    for r in regions:
        r["geom"] = from_wkb(r["wkb"])

    layers: dict[str, np.ndarray] = {}
    for band in ("VV", "VH"):
        paths = [f[band] for f in frames if band in f]
        if paths:
            layers[band] = mosaic(paths, transform, shape)
    if not layers:
        return 0

    written = 0
    with db.session() as sess:
        for band, arr in layers.items():
            valid = np.isfinite(arr)
            res = {r["region_id"]: ha.zonal(arr, valid, transform, r["geom"], "MEAN", min_vf,
                                            region_key=("s1", r["region_id"])) for r in regions}
            pid = _product_id(sess, next(f[band] for f in frames if band in f))
            written += ha.upsert_observations(sess, band, scene_date, res, product_id=pid, job_id=job_id)
        if "VH" in layers:
            vh = layers["VH"]
            classes = np.where(np.isfinite(vh), np.where(vh < thr, WATER_CLASS, 0), NODATA_CLASS)
            valid = classes != NODATA_CLASS
            res = {r["region_id"]: ha.zonal(classes, valid, transform, r["geom"], "FRACTION", min_vf,
                                            region_key=("s1", r["region_id"])) for r in regions}
            pid = _product_id(sess, next(f["VH"] for f in frames if "VH" in f))
            written += ha.upsert_observations(sess, "WATER_PCT", scene_date, res, product_id=pid,
                                              job_id=job_id)
    logger.info("[S1OBS] %s: %d baris (%d frame)", scene_date, written, len(frames))
    return written
