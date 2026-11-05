"""Tier GOLD: ekspor produk SILVER per-source jadi Cloud-Optimized GeoTIFF analysis-ready."""

from __future__ import annotations

import logging
from pathlib import Path

import rasterio
from rasterio.shutil import copy as rio_copy

from etl import folder_manager as fm

logger = logging.getLogger(__name__)

MODULE = "MODULE4_GOLD_EXPORT"

COG_PROFILE = {
    "driver": "COG",
    "compress": "DEFLATE",
    "predictor": "YES",
    "blocksize": 512,
    "overview_resampling": "average",
    "bigtiff": "IF_SAFER",
}

GOLD_PRODUCT_TYPES: dict[str, str] = {
    "sentinel1": "S1_COG",
    "modis": "MODIS_COG",
    "gpm": "GPM_COG",
}


def _overview_resampling_for(src: rasterio.DatasetReader) -> str:
    """Overview 'average' benar untuk data kontinu (backscatter, curah hujan,
    NDVI). Untuk raster kategorikal — flood mask MODIS yang uint8 dengan
    255 = nodata — merata-ratakan kelas akan mengarang kelas baru yang tidak
    ada di data asli, jadi pakai nearest."""
    if src.dtypes[0] in ("uint8", "int8") or src.count == 0:
        return "nearest"
    return "average"


def export_cog(src_path: str | Path, out_path: str | Path) -> Path:
    """Tulis ulang satu GeoTIFF jadi COG. Idempotent: file yang sudah ada
    ditimpa, karena COG-nya turunan penuh dari input dan aman dibangun ulang."""
    src_path = Path(src_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    profile = dict(COG_PROFILE)
    with rasterio.open(src_path) as src:
        profile["overview_resampling"] = _overview_resampling_for(src)
        if min(src.height, src.width) < profile["blocksize"]:
            profile["blocksize"] = 128

    rio_copy(str(src_path), str(out_path), **profile)
    logger.info(
        "[M4] COG %s -> %s (%.2f MB)",
        src_path.name, out_path.name, out_path.stat().st_size / (1024 ** 2),
    )
    return out_path


def export_scene_to_gold(
    dataset_id: int,
    dataset_name: str,
    source: str,
    scene_key: str,
    silver_files: dict[str, str | Path],
) -> dict[str, str]:
    """Ekspor semua band SILVER satu scene ke tier GOLD sebagai COG."""
    gold_dir = fm.ensure_scene_dir(dataset_id, dataset_name, "cog", source, scene_key)
    exported: dict[str, str] = {}

    for band, silver_path in silver_files.items():
        silver_path = Path(silver_path)
        if not silver_path.exists():
            logger.warning(
                "[M4] SILVER %s/%s band=%s tidak ada di disk, lewati: %s",
                source, scene_key, band, silver_path,
            )
            continue
        out_path = gold_dir / silver_path.name
        try:
            export_cog(silver_path, out_path)
        except Exception:
            logger.exception(
                "[M4] gagal ekspor GOLD %s/%s band=%s dari %s",
                source, scene_key, band, silver_path,
            )
            continue
        exported[band] = str(out_path)

    logger.info(
        "[M4] GOLD %s scene=%s: %d/%d band diekspor",
        source, scene_key, len(exported), len(silver_files),
    )
    return exported


def gold_product_type(source: str) -> str:
    return GOLD_PRODUCT_TYPES[fm.normalize_source(source)]


def run(
    dataset_id: int,
    dataset_name: str,
    source: str,
    scene_key: str,
    silver_files: dict[str, str | Path],
) -> dict[str, str]:
    """Alias konsisten dengan module2/module3 yang juga mengekspos `run`."""
    return export_scene_to_gold(dataset_id, dataset_name, source, scene_key, silver_files)
