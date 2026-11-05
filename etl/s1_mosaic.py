"""Mosaik frame Sentinel-1 yang jatuh di tanggal yang sama."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.merge import merge

logger = logging.getLogger(__name__)

MODULE = "S1_MOSAIC"


def _coverage(path: str) -> float:
    """Fraksi piksel valid sebuah raster, 0.0 kalau tidak terbaca."""
    try:
        with rasterio.open(path) as src:
            out_h = min(src.height, 512)
            out_w = min(src.width, 512)
            data = src.read(1, out_shape=(1, out_h, out_w))
            if src.nodata is None or np.isnan(src.nodata):
                valid = np.isfinite(data)
            else:
                valid = np.isfinite(data) & (data != src.nodata)
            return float(valid.mean())
    except Exception:
        logger.exception("[%s] gagal membaca cakupan %s", MODULE, path)
        return 0.0


def mosaic_frames(
    frames: list[dict[str, str]], out_dir: Path, *, date_key: str, level: str
) -> dict[str, str]:
    """Satukan `frames` ({band: path} per scene) jadi satu {band: path}."""
    by_band: dict[str, list[str]] = {}
    for frame in frames:
        for band, path in (frame or {}).items():
            if not path:
                continue
            if not Path(path).exists():
                logger.warning(
                    "[%s] %s %s: berkas %s band %s tidak ada, frame dilewati",
                    MODULE, date_key, level, path, band,
                )
                continue
            by_band.setdefault(band, []).append(path)

    out: dict[str, str] = {}
    for band, paths in by_band.items():
        if len(paths) == 1:
            out[band] = paths[0]
            continue
        ordered = sorted(paths, key=_coverage, reverse=True)
        ordered = _drop_foreign_crs(ordered, date_key=date_key, level=level, band=band)
        if len(ordered) == 1:
            out[band] = ordered[0]
            continue
        out_path = out_dir / f"{date_key}_{level}_{band}_mosaic.tif"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            out[band] = str(
                _merge_to(ordered, out_path, date_key=date_key, level=level, band=band)
            )
        except Exception:
            logger.exception(
                "[%s] %s %s band %s: mosaik gagal, memakai frame dengan cakupan "
                "terbesar (%s)", MODULE, date_key, level, band, ordered[0],
            )
            out[band] = ordered[0]

    return out


def _merge_to(
    ordered: list[str], out_path: Path, *, date_key: str, level: str, band: str
) -> Path:
    with rasterio.open(ordered[0]) as first:
        profile = first.profile.copy()

    profile.update(driver="GTiff", nodata=float("nan"), count=1, compress="deflate")
    merge(
        sources=ordered,
        nodata=float("nan"),
        method="first",
        use_highest_res=True,
        resampling=Resampling.nearest,
        mem_limit=8192,
        dst_path=str(out_path),
        dst_kwds={k: profile[k] for k in ("driver", "compress", "nodata") if k in profile},
    )
    with rasterio.open(out_path) as dst:
        logger.info(
            "[%s] %s %s band %s: %d frame -> %dx%d (%.1f%% valid)",
            MODULE, date_key, level, band, len(ordered), dst.height, dst.width,
            _coverage(str(out_path)) * 100,
        )
    return out_path


def _crs_of(path: str):
    with rasterio.open(path) as src:
        return src.crs


def _drop_foreign_crs(
    ordered: list[str], *, date_key: str, level: str, band: str
) -> list[str]:
    """Sisakan frame yang CRS-nya sama dengan frame pertama (cakupan
    terbesar). `ordered` harus sudah urut cakupan menurun."""
    keep_crs = _crs_of(ordered[0])
    kept = [p for p in ordered if _crs_of(p) == keep_crs]
    dropped = [p for p in ordered if p not in kept]
    if dropped:
        logger.warning(
            "[%s] %s %s band %s: %d frame dibuang karena CRS-nya bukan %s: %s",
            MODULE, date_key, level, band, len(dropped), keep_crs, dropped,
        )
    return kept
