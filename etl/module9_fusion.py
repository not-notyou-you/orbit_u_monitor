"""Builds a multi-modal HDF5 feature stack (Sentinel-1 SAR + MODIS flood/NDVI/NDWI
+ GPM rainfall) aligned to a common grid for ML training. This is the FUSION
tier deliverable — the last stage of the pipeline, downstream of GOLD.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import date as date_type, datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Callable, Sequence

import h5py
import numpy as np
import rasterio

from etl import WARP_THREADS
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.warp import reproject
from sqlalchemy import select, update

from etl import folder_manager as fm
from etl import module4_gold_export as m4
from etl.database_client import (
    DatabaseClient,
    DataProduct,
    Dataset,
    FusionProduct,
    JobStatusEnum,
    NasaScene,
    ProductTierEnum,
    SatelliteScene,
)
from etl.constants import (
    GPM_PRODUCT_SHORT_NAME,
    GPM_SOURCE,
    GPM_TILE_ID,
    MODIS_PRODUCT_SHORT_NAME,
    MODIS_SOURCE,
    MODIS_TILE_ID,
)
from etl.lineage_tracker import LineageTracker
from etl.metadata_manager import MetadataManager
from etl.pipeline_logger import PipelineLogger
from etl.processing_plan import GPM as GPM_PLAN_NAME
from etl.processing_plan import MODIS as MODIS_PLAN_NAME
from etl.processing_plan import SENTINEL1 as S1_PLAN_NAME
from etl.fusion_strategies import FILENAME_SUFFIX, SUBFOLDER
from etl.processing_plan import (
    PROCESSED,
    RAW,
    ProcessingPlan,
    SourcePlan,
    load_processing_plan,
)

from etl import tier_names as tn

logger = logging.getLogger(__name__)

MODIS_NODATA_U8 = 255  # uint8 can't hold NaN; 255 marks a missing/nodata pixel
HDF5_CHUNK_MAX = 256

S1_FUSION_BANDS: tuple[str, ...] = ("VV", "VH")


@dataclass(frozen=True)
class _AuxLayer:
    """Satu dataset HDF5 dari sumber aux (MODIS/GPM)."""

    name: str
    file_key: str
    resampling: Resampling
    categorical: bool = False
    band: int = 1


_FLOOD = _AuxLayer("FLOOD", "FLOOD", Resampling.nearest, categorical=True)
_FLOOD_SOURCE = _AuxLayer(
    "FLOOD_SOURCE", "FLOOD", Resampling.nearest, categorical=True, band=2
)

MODIS_FUSION_LAYERS: dict[str, tuple[_AuxLayer, ...]] = {
    RAW: (_FLOOD, _FLOOD_SOURCE),
    PROCESSED: (
        _FLOOD,
        _FLOOD_SOURCE,
        _AuxLayer("NDVI", "NDVI", Resampling.bilinear),
        _AuxLayer("NDVI_AGE_DAYS", "NDVI", Resampling.nearest, band=2),
        _AuxLayer("NDWI", "NDWI", Resampling.bilinear),
        _AuxLayer("NDWI_AGE_DAYS", "NDWI", Resampling.nearest, band=2),
    ),
}

GPM_FUSION_LAYERS: dict[str, tuple[_AuxLayer, ...]] = {
    RAW: (_AuxLayer("rainfall_daily", "24h", Resampling.nearest),),
    PROCESSED: (
        _AuxLayer("rainfall_24h", "24h", Resampling.nearest),
        _AuxLayer("rainfall_72h", "72h", Resampling.nearest),
        _AuxLayer("rainfall_7d", "7d", Resampling.nearest),
    ),
}

_AUX_LAYERS_BY_SOURCE: dict[str, dict[str, tuple[_AuxLayer, ...]]] = {
    MODIS_PLAN_NAME: MODIS_FUSION_LAYERS,
    GPM_PLAN_NAME: GPM_FUSION_LAYERS,
}

GROUP_BY_SOURCE: dict[str, str] = {
    S1_PLAN_NAME: "sentinel1",
    MODIS_PLAN_NAME: "modis",
    GPM_PLAN_NAME: "gpm",
}

FUSION_LAYERS = [
    *(f"sentinel1/{band}" for band in S1_FUSION_BANDS),
    *(f"modis/{layer.name}" for layer in MODIS_FUSION_LAYERS[PROCESSED]),
    *(f"gpm/{layer.name}" for layer in GPM_FUSION_LAYERS[PROCESSED]),
]


def fusion_layers_for(source_levels: dict[str, str]) -> list[str]:
    """Path dataset HDF5 yang akan ditulis untuk {SOURCE: level} ini."""
    out: list[str] = []
    for source, level in source_levels.items():
        group = GROUP_BY_SOURCE.get(source)
        if group is None:
            logger.warning("[M9] sumber tanpa group HDF5, dilewati: %r", source)
            continue
        if source == S1_PLAN_NAME:
            out.extend(f"{group}/{band}" for band in S1_FUSION_BANDS)
        else:
            out.extend(
                f"{group}/{layer.name}"
                for layer in _AUX_LAYERS_BY_SOURCE[source][level]
            )
    return out


def _find_s1_products(
    db: DatabaseClient, dataset_id: int, scene_id: int, tier: str = tn.COG
) -> dict | None:
    """Cari produk Sentinel-1 VV/VH scene `scene_id` di `tier`. None kalau scene-nya sendiri tidak ada."""
    tier_enum = ProductTierEnum[str(tier).upper()]
    with db.session() as sess:
        scene = sess.get(SatelliteScene, scene_id)
        if scene is None:
            return None

        def _band(band: str) -> DataProduct | None:
            return sess.scalar(
                select(DataProduct).where(
                    DataProduct.scene_id == scene.scene_id,
                    DataProduct.dataset_id == dataset_id,
                    DataProduct.product_tier == tier_enum,
                    DataProduct.source == "SENTINEL1",
                    DataProduct.band_name == band,
                    DataProduct.is_latest == True,
                    DataProduct.is_valid == True,
                )
            )

        vv = _band("VV")
        vh = _band("VH")

        return {
            "scene_id": scene.scene_id,
            "region_id": scene.region_id,
            "acquisition_datetime": scene.acquisition_datetime,
            "tier": tier_enum.value,
            "vv_product_id": vv.product_id if vv else None,
            "vv_path": vv.file_path if vv else None,
            "vh_product_id": vh.product_id if vh else None,
            "vh_path": vh.file_path if vh else None,
        }


def _s1_member_paths(
    db: DatabaseClient, dataset_id: int, scene_ids: Sequence[int], tier: str
) -> dict[str, list[str]]:
    """{band: [path raster tiap frame]} untuk frame-frame penyusun mosaik."""
    out: dict[str, list[str]] = {band: [] for band in S1_FUSION_BANDS}
    for member_id in scene_ids:
        found = _find_s1_products(db, dataset_id, member_id, tier=tier)
        if not found:
            continue
        for band in S1_FUSION_BANDS:
            path = found.get(f"{band.lower()}_path")
            if path:
                out[band].append(path)
    return out


def _as_utc(dt: datetime) -> datetime:
    """Normalkan waktu akuisisi ke UTC sebelum diturunkan jadi tanggal."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


AUX_DAY_OFFSETS: tuple[int, ...] = (0, -1)


def _find_aux_daily_file(
    dataset_id: int,
    dataset_name: str,
    source: str,
    filename_fn,
    feature_date: date_type,
    tier: str = "cog",
) -> tuple[Path, date_type] | None:
    """Berkas MODIS/GPM harian untuk tanggal fitur `feature_date`, sebagai
    (path, tanggal berkas), atau None kalau tidak ada di disk.
    """
    for offset in AUX_DAY_OFFSETS:
        candidate = feature_date + timedelta(days=offset)
        tier_dir = fm.get_scene_dir(
            dataset_id, dataset_name, tier.lower(), source,
            candidate.strftime("%Y%m%d"),
        )
        path = tier_dir / filename_fn(candidate)
        if path.exists():
            return path, candidate
    return None


LAYER_UNITS: dict[str, str] = {
    "sentinel1/VV": "linear sigma0 (not dB)",
    "sentinel1/VH": "linear sigma0 (not dB)",
    "modis/FLOOD": "MCDWD class: 0 no water, 1 permanent water, 2 recurrent flood, 3 flood, 255 insufficient data",
    "modis/NDVI": "indeks tanpa satuan [-1, 1]",
    "modis/NDWI": "indeks tanpa satuan [-1, 1]",
    "modis/FLOOD_SOURCE": "origin of FLOOD pixel: 1 2-day composite, 2 1-day CS composite (gap filler), 255 no data",
    "modis/NDVI_AGE_DAYS": "days (age of the NDVI observation relative to the feature date)",
    "modis/NDWI_AGE_DAYS": "days (age of the NDWI observation relative to the feature date)",
    "gpm/rainfall_daily": "mm",
    "gpm/rainfall_24h": "mm",
    "gpm/rainfall_72h": "mm",
    "gpm/rainfall_7d": "mm",
}

_IGNORED_SOURCE_TAGS = {"AREA_OR_POINT"}


def _source_tags(path: Path) -> dict[str, str]:
    """Tag asal-usul berkas sumber (ditulis module7/module8), dengan kunci
    huruf kecil supaya seragam dengan atribut HDF5 lainnya."""
    try:
        with rasterio.open(path) as src:
            tags = src.tags()
    except Exception:  # pragma: no cover - berkas sumber rusak sudah gagal lebih awal
        return {}
    return {
        key.lower(): value for key, value in tags.items()
        if key not in _IGNORED_SOURCE_TAGS
    }


def _hours_after_acquisition(window_end_utc: str | None, acquisition: datetime | None) -> float | None:
    """Berapa jam ujung jendela hujan melewati waktu akuisisi S1."""
    if not window_end_utc or acquisition is None:
        return None
    try:
        end = datetime.fromisoformat(window_end_utc.replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((end - _as_utc(acquisition)).total_seconds() / 3600.0, 2)


class _MissingBand(RuntimeError):
    """Berkas sumber ada, tapi tidak punya band yang diminta lapisan ini."""


def _reproject_to_grid(
    src_path: Path,
    ref_transform,
    ref_crs,
    ref_shape: tuple[int, int],
    resampling: Resampling,
    fill_value: float,
    band: int = 1,
) -> np.ndarray:
    """Reproject band `band` of a raster onto the S1 reference grid, filling
    pixels outside the source extent with `fill_value`."""
    height, width = ref_shape
    dest = np.full((height, width), fill_value, dtype=np.float32)
    with rasterio.open(src_path) as src:
        if band > src.count:
            raise _MissingBand(f"{src_path.name} only has {src.count} band(s), needs band {band}")
        reproject(
            source=rasterio.band(src, band),
            destination=dest,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=ref_transform,
            dst_crs=ref_crs,
            dst_nodata=fill_value,
            resampling=resampling,
            num_threads=WARP_THREADS,
        )
    return dest


def _get_or_create_nasa_scene(
    db: DatabaseClient,
    source: str,
    tile_id: str,
    product_short_name: str,
    acquisition_date: date_type,
    region_id: int,
    file_path: Path,
) -> int:
    with db.session() as sess:
        existing = sess.scalar(
            select(NasaScene.nasa_scene_id).where(
                NasaScene.source == source,
                NasaScene.tile_id == tile_id,
                NasaScene.product_short_name == product_short_name,
                NasaScene.acquisition_date == acquisition_date,
            )
        )
        if existing:
            return existing

        scene = NasaScene(
            source=source,
            tile_id=tile_id,
            product_short_name=product_short_name,
            acquisition_date=acquisition_date,
            region_id=region_id,
            raw_file_path=str(file_path),
            is_available=True,
        )
        sess.add(scene)
        sess.flush()
        return scene.nasa_scene_id


LOW_COVERAGE_FRACTION = 0.05


def _valid_fraction(array: np.ndarray) -> float:
    """Fraksi piksel yang membawa nilai, bukan nodata."""
    if array.dtype == np.uint8:
        return float((array != MODIS_NODATA_U8).mean())
    return float(np.isfinite(array).mean())


class _FusionH5Layers:
    """Penulis stack HDF5: satu lapisan ditulis begitu selesai dihitung."""

    def __init__(self, h5_path: Path, ref_shape: tuple[int, int]) -> None:
        self.path = h5_path
        self.shape = ref_shape
        height, width = ref_shape
        self._chunks = (min(HDF5_CHUNK_MAX, height), min(HDF5_CHUNK_MAX, width))
        h5_path.parent.mkdir(parents=True, exist_ok=True)
        self._partial_path = h5_path.with_name(h5_path.name + ".partial")
        self._file = h5py.File(self._partial_path, "w")
        self.names: list[str] = []

    def add(self, name: str, array: np.ndarray, attrs: dict | None = None) -> None:
        ds = self._file.create_dataset(
            name, data=array, dtype=array.dtype, chunks=self._chunks,
            compression="gzip", shuffle=True,
        )
        ds.attrs["nodata"] = MODIS_NODATA_U8 if array.dtype == np.uint8 else "NaN"
        for key, value in (attrs or {}).items():
            if value is None:
                continue
            ds.attrs[key] = value
        self.names.append(name)

    def finalize(
        self,
        *,
        acquisition_datetime: datetime,
        processing_datetime: datetime,
        aoi_bbox: tuple[float, float, float, float],
        processing_level: str,
        source_levels: dict[str, str],
        fusion_strategy: str | None = None,
        crs: object | None = None,
        transform: object | None = None,
        extra_attrs: dict | None = None,
    ) -> None:
        """Tulis atribut root lalu tutup berkas."""
        height, width = self.shape
        f = self._file
        f.attrs["acquisition_datetime"] = acquisition_datetime.isoformat()
        f.attrs["processing_datetime"] = processing_datetime.isoformat()
        f.attrs["aoi_bbox"] = list(aoi_bbox)
        f.attrs["layers"] = list(self.names)
        f.attrs["height"] = height
        f.attrs["width"] = width
        f.attrs["processing_level"] = processing_level
        f.attrs["sources"] = list(source_levels)
        f.attrs["source_levels"] = [source_levels[k] for k in source_levels]
        if fusion_strategy:
            f.attrs["fusion_strategy"] = fusion_strategy
        for key, value in (extra_attrs or {}).items():
            if value is not None:
                f.attrs[key] = value
        if crs is not None:
            f.attrs["crs"] = str(crs)
            try:
                f.attrs["crs_wkt"] = crs.to_wkt()
            except AttributeError:
                pass
        if transform is not None:
            f.attrs["transform"] = [float(v) for v in tuple(transform)[:6]]
            west, north = transform * (0, 0)
            east, south = transform * (width, height)
            f.attrs["grid_bbox"] = [
                float(west), float(south), float(east), float(north)
            ]
            aoi_west, _, _, aoi_north = aoi_bbox
            res_x, res_y = abs(float(transform.a)), abs(float(transform.e))
            f.attrs["grid_offset_row_col"] = [
                int(round((aoi_north - north) / res_y)),
                int(round((west - aoi_west) / res_x)),
            ]
        f.close()
        os.replace(self._partial_path, self.path)

        logger.info(
            "[M9] Saving fusion H5 to FUSION tier: %s level=%s shape=(%d, %d) "
            "layers=%d %s",
            self.path, processing_level, height, width, len(self.names),
            sorted(self.names),
        )

    def close(self) -> None:
        try:
            self._file.close()
        except Exception:  # pragma: no cover - berkas sudah tertutup
            pass


def _write_fusion_metadata_json(
    json_path: Path,
    fusion_id: int,
    dataset_id: int,
    region_id: int,
    s1_date: date_type,
    s1: dict,
    layer_sources: dict[str, dict],
    days_since_s1: int,
    acquisition_datetime: datetime,
    processing_datetime: datetime,
    aoi_bbox: tuple[float, float, float, float],
    h5_path: Path,
    height: int,
    width: int,
    processing_level: str,
    source_levels: dict[str, str],
    source_tiers: dict[str, str],
    fusion_strategy: str | None,
    temporal_offsets: dict[str, int | None],
    checksum_sha256: str,
) -> None:
    """Tulis sidecar fusion_metadata.json."""
    metadata = {
        "fusion_id": fusion_id,
        "dataset_id": dataset_id,
        "region_id": region_id,
        "feature_date": s1_date.isoformat(),
        "acquisition_datetime": acquisition_datetime.isoformat(),
        "processing_datetime": processing_datetime.isoformat(),
        "aoi_bbox": list(aoi_bbox),
        "shape": {"height": height, "width": width},
        "processing_level": processing_level,
        "source_levels": source_levels,
        "source_tiers": source_tiers,
        "fusion_strategy": fusion_strategy,
        "layers": list(layer_sources),
        "layer_sources": layer_sources,
        "layer_coverage": {
            name: round(source.get("valid_fraction", 0.0), 4)
            for name, source in layer_sources.items()
        },
        "source_scenes": {
            "s1_scene_id": s1["scene_id"],
            **({"s1_mosaic_scene_ids": s1["mosaic_of"]} if s1.get("mosaic_of") else {}),
        },
        "days_since_s1": days_since_s1,
        "temporal_offsets": temporal_offsets,
        "file_name": h5_path.name,
        "file_size_mb": round(h5_path.stat().st_size / (1024 ** 2), 3),
        "checksum_sha256": checksum_sha256,
    }
    with open(json_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)


def _product_exists(db: DatabaseClient, dataset_id: int, file_path: str) -> bool:
    with db.session() as sess:
        return sess.scalar(
            select(DataProduct.product_id).where(
                DataProduct.dataset_id == dataset_id,
                DataProduct.file_path == file_path,
                DataProduct.is_latest == True,
            )
        ) is not None


def _empty_produced() -> dict[str, list[str]]:
    """Wadah {tier: [path]} untuk artefak aux yang ditulis satu pemanggilan."""
    return {tn.ALIGNED: [], tn.INDICES: [], tn.ACCUMULATED: [], tn.COG: []}


def _modis_granule(entry: dict, output_date: date_type) -> tuple[str, date_type]:
    """(product_short_name, acquisition_date) granule asal satu band MODIS."""
    product = str(entry.get("product") or "").split(",")[0].strip()
    short_name = product or MODIS_PRODUCT_SHORT_NAME
    periods = [p for p in (entry.get("periods_used") or []) if p]
    acquisition = date_type.fromisoformat(max(periods)[:10]) if periods else output_date
    return short_name, acquisition


def _aux_plan(db: DatabaseClient, dataset_id: int, source_name: str) -> SourcePlan | None:
    """Konfigurasi satu sumber aux, dibaca dari dataset_source_config."""
    return load_processing_plan(db, dataset_id).get(source_name)


def _register_aux_products(
    db: DatabaseClient,
    *,
    dataset_id: int,
    region_id: int,
    source: str,
    nasa_source: str,
    nasa_tile_id: str,
    nasa_product_short_name: str,
    acquisition_date: date_type,
    band_paths: dict[str, str],
    product_type: str,
    tier: str = tn.INDICES,
    processing_level: str = PROCESSED,
) -> tuple[dict[str, int], dict[str, int]]:
    """Daftarkan band satu source/tanggal sebagai data_products di `tier`."""
    meta = MetadataManager(db)
    lineage = LineageTracker(db)

    product_ids: dict[str, int] = {}
    nasa_ids: dict[str, int] = {}
    for band, path in band_paths.items():
        if not Path(path).exists():
            continue
        nasa_scene_id = meta.insert_nasa_scene(
            source=nasa_source, tile_id=nasa_tile_id,
            product_short_name=nasa_product_short_name,
            acquisition_date=acquisition_date, region_id=region_id, raw_file_path=path,
        )
        nasa_ids[band] = nasa_scene_id
        if _product_exists(db, dataset_id, path):
            continue
        job_id = meta.insert_processing_job(
            None, "DOWNLOAD", nasa_scene_id=nasa_scene_id,
            parameters={"dataset_id": dataset_id, "source": source.upper()},
        )
        meta.start_job(job_id)
        try:
            product_ids[band] = meta.insert_data_product(
                scene_id=None, nasa_scene_id=nasa_scene_id,
                job_id=job_id, dataset_id=dataset_id,
                product_tier=tier, source=fm.db_source(source),
                product_type=product_type, band_name=band,
                file_path=path, file_name=Path(path).name,
                file_size_mb=round(Path(path).stat().st_size / (1024 ** 2), 3),
                data_hash_sha256=lineage.compute_sha256(path),
                processing_level=processing_level,
            )
        except Exception as exc:
            meta.complete_job(
                job_id, status=JobStatusEnum.FAILED,
                error_code=type(exc).__name__, error_message=str(exc)[:2000],
            )
            raise
        meta.complete_job(job_id)

    return product_ids, nasa_ids


def _promote_aux_to_gold(
    db: DatabaseClient,
    *,
    dataset_id: int,
    dataset_name: str,
    source: str,
    date_key: str,
    nasa_scene_ids: dict[str, int],
    silver_paths: dict[str, str],
    silver_product_ids: dict[str, int],
) -> dict[str, str]:
    """Ekspor band rank 2 MODIS/GPM satu tanggal ke COG dan catat produknya
    + lineage-nya. COG menempel pada granule nasa_scenes yang sama dengan
    band asalnya (M30)."""
    meta = MetadataManager(db)
    lineage = LineageTracker(db)

    gold_paths = m4.export_scene_to_gold(
        dataset_id, dataset_name, source, date_key, silver_paths
    )
    if not gold_paths:
        return {}

    for band, path in gold_paths.items():
        if _product_exists(db, dataset_id, path):
            continue
        nasa_scene_id = nasa_scene_ids.get(band)
        if nasa_scene_id is None:
            logger.warning(
                "[M9] COG %s %s tanggal %s dilewati: granule asal tidak terdaftar",
                source, band, date_key,
            )
            continue
        gold_job_id = meta.insert_processing_job(
            None, "GOLD_EXPORT", nasa_scene_id=nasa_scene_id,
            parameters={"dataset_id": dataset_id, "source": source.upper(), "date": date_key},
        )
        meta.start_job(gold_job_id)
        try:
            gold_product_id = meta.insert_data_product(
                scene_id=None, nasa_scene_id=nasa_scene_id,
                job_id=gold_job_id, dataset_id=dataset_id,
                product_tier=tn.COG, source=fm.db_source(source),
                product_type=m4.gold_product_type(source), band_name=band,
                file_path=path, file_name=Path(path).name,
                file_size_mb=round(Path(path).stat().st_size / (1024 ** 2), 3),
                data_hash_sha256=lineage.compute_sha256(path),
                file_format="COG",
                processing_level=PROCESSED,
            )
            if band in silver_product_ids:
                lineage.record_transformation(
                    silver_product_ids[band], gold_product_id, "GOLD_EXPORT", gold_job_id,
                    {"source": source, "date": date_key},
                )
        except Exception as exc:
            meta.complete_job(
                gold_job_id, status=JobStatusEnum.FAILED,
                error_code=type(exc).__name__, error_message=str(exc)[:2000],
            )
            raise
        meta.complete_job(gold_job_id)
    return gold_paths


def ensure_modis_inputs_for_date(
    db: DatabaseClient,
    dataset_id: int,
    dataset_name: str,
    region_id: int,
    aoi_bbox: tuple[float, float, float, float],
    target_date: date_type,
    plog: PipelineLogger | None = None,
    plan: SourcePlan | None = None,
) -> dict[str, list[str]]:
    """Siapkan input MODIS untuk satu tanggal sesuai level yang dikonfigurasi."""
    from etl.module7_modis_download import MODIS_PRODUCT_TYPES, download_modis_scene

    plan = plan or _aux_plan(db, dataset_id, MODIS_PLAN_NAME)
    produced: dict[str, list[str]] = _empty_produced()
    if plan is None:
        logger.info(
            "[M9] MODIS tidak dikonfigurasi untuk dataset=%s, dilewati", dataset_id
        )
        return produced

    target_dt = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)

    try:
        _, modis_meta = download_modis_scene(
            dataset_id, dataset_name, target_dt, target_dt, aoi_bbox, plog=plog,
            processing_levels=plan.levels,
        )
    except Exception:
        logger.exception(
            "[M9] gagal siapkan input MODIS dataset=%s tanggal=%s", dataset_id, target_date
        )
        return produced

    for output in modis_meta["outputs"]:
        output_date = date_type.fromisoformat(output["date"])
        date_key = output_date.strftime("%Y%m%d")
        for band, entry in output["bands"].items():
            short_name, granule_date = _modis_granule(entry, output_date)
            for tier, target in entry["targets"].items():
                path = target["path"]
                product_ids, nasa_ids = _register_aux_products(
                    db, dataset_id=dataset_id, region_id=region_id,
                    source="modis", nasa_source=MODIS_SOURCE, nasa_tile_id=MODIS_TILE_ID,
                    nasa_product_short_name=short_name,
                    acquisition_date=granule_date,
                    band_paths={band: path},
                    product_type=MODIS_PRODUCT_TYPES[band],
                    tier=tier, processing_level=target["processing_level"],
                )
                produced[tier].append(path)
                if tn.rank(tier) != 2:
                    continue
                gold_paths = _promote_aux_to_gold(
                    db, dataset_id=dataset_id, dataset_name=dataset_name, source="modis",
                    date_key=date_key, nasa_scene_ids=nasa_ids,
                    silver_paths={band: path}, silver_product_ids=product_ids,
                )
                produced[tn.COG].extend(gold_paths.values())

    return produced


def ensure_gpm_inputs_for_date(
    db: DatabaseClient,
    dataset_id: int,
    dataset_name: str,
    region_id: int,
    aoi_bbox: tuple[float, float, float, float],
    target_date: date_type,
    plog: PipelineLogger | None = None,
    plan: SourcePlan | None = None,
    windows: tuple[str, ...] | None = None,
    rebuild_non_final: bool = False,
    raise_errors: bool = False,
) -> dict[str, list[str]]:
    """Siapkan input GPM untuk satu tanggal sesuai level yang dikonfigurasi."""
    from etl.module8_gpm_download import (
        GPM_PRODUCT_TYPE,
        band_name as gpm_band_name,
        download_gpm_scene,
    )

    plan = plan or _aux_plan(db, dataset_id, GPM_PLAN_NAME)
    produced: dict[str, list[str]] = _empty_produced()
    if plan is None:
        logger.info(
            "[M9] GPM tidak dikonfigurasi untuk dataset=%s, dilewati", dataset_id
        )
        return produced

    target_dt = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
    date_key = target_date.strftime("%Y%m%d")

    try:
        _, gpm_meta = download_gpm_scene(
            dataset_id, dataset_name, target_dt, aoi_bbox, plog=plog,
            processing_levels=plan.levels, windows=windows,
            rebuild_non_final=rebuild_non_final,
        )
    except Exception:
        if raise_errors:
            raise
        logger.exception(
            "[M9] gagal siapkan input GPM dataset=%s tanggal=%s", dataset_id, target_date
        )
        return produced

    by_tier: dict[str, dict[str, dict[str, str]]] = {}
    for window_name, output in gpm_meta["windows"].items():
        for tier, target in output["targets"].items():
            by_tier.setdefault(tier, {})[gpm_band_name(window_name)] = target

    for tier, bands in by_tier.items():
        band_paths = {band: target["path"] for band, target in bands.items()}
        level = next(iter(bands.values()))["processing_level"]
        product_ids, nasa_ids = _register_aux_products(
            db, dataset_id=dataset_id, region_id=region_id,
            source="gpm", nasa_source=GPM_SOURCE, nasa_tile_id=GPM_TILE_ID,
            nasa_product_short_name=GPM_PRODUCT_SHORT_NAME,
            acquisition_date=target_date,
            band_paths=band_paths, product_type=GPM_PRODUCT_TYPE,
            tier=tier, processing_level=level,
        )
        produced[tier].extend(band_paths.values())
        if tn.rank(tier) != 2:
            continue
        gold_paths = _promote_aux_to_gold(
            db, dataset_id=dataset_id, dataset_name=dataset_name, source="gpm",
            date_key=date_key, nasa_scene_ids=nasa_ids,
            silver_paths=band_paths, silver_product_ids=product_ids,
        )
        produced[tn.COG].extend(gold_paths.values())

    return produced


def ensure_aux_inputs_for_date(
    db: DatabaseClient,
    dataset_id: int,
    dataset_name: str,
    region_id: int,
    aoi_bbox: tuple[float, float, float, float],
    target_date: date_type,
    plog: PipelineLogger | None = None,
    plan: ProcessingPlan | None = None,
) -> dict[str, list[str]]:
    """Siapkan input MODIS + GPM yang dibutuhkan untuk memfusikan scene S1
    tanggal `target_date`: download kalau belum ada di disk, daftarkan sebagai
    data_products, dan (untuk level PROCESSED) ekspor ke COG di tier GOLD.
    """
    plan = plan or load_processing_plan(db, dataset_id)
    produced: dict[str, list[str]] = _empty_produced()
    missing_sources: set[str] = set()

    for source_name, ensure_fn in (
        (MODIS_PLAN_NAME, ensure_modis_inputs_for_date),
        (GPM_PLAN_NAME, ensure_gpm_inputs_for_date),
    ):
        source_plan = plan.get(source_name)
        if source_plan is None:
            logger.info(
                "[M9] %s tidak dikonfigurasi dataset=%s, tidak diunduh",
                source_name, dataset_id,
            )
            continue
        part = ensure_fn(
            db, dataset_id, dataset_name, region_id, aoi_bbox, target_date,
            plog=plog, plan=source_plan,
        )
        if not any(part.values()):
            missing_sources.add(source_name)
        for tier, paths in part.items():
            produced[tier].extend(paths)
    return produced, missing_sources


@dataclass(frozen=True)
class FusionRun:
    """Hasil satu stack fusion — satu berkas HDF5 dan barisnya di database."""

    fusion_id: int
    processing_level: str
    h5_path: Path
    json_path: Path
    layers: tuple[str, ...]
    source_levels: dict[str, str]
    product_id: int
    checksum_sha256: str


def fusion_h5_name(
    date_key: str, processing_level: str, fusion_strategy: str | None = None
) -> str:
    """Nama berkas stack HDF5. Level SELALU ikut di nama, juga saat dataset cuma menghasilkan satu stack."""
    strategy = str(fusion_strategy).strip().upper() if fusion_strategy else None
    suffix = FILENAME_SUFFIX.get(strategy) if strategy else None
    if suffix:
        return f"fusion_{date_key}_{suffix}_{processing_level.lower()}.h5"
    return f"fusion_{date_key}_{processing_level.lower()}.h5"


def fusion_metadata_name(
    date_key: str, processing_level: str, fusion_strategy: str | None = None
) -> str:
    """Sidecar JSON pendamping `fusion_h5_name`: nama yang sama, akhiran `_metadata.json`."""
    stem = fusion_h5_name(date_key, processing_level, fusion_strategy).removesuffix(".h5")
    return f"{stem}_metadata.json"


def _aux_layers_for_run(
    dataset_id: int,
    dataset_name: str,
    source: str,
    level: str,
    feature_date: date_type,
    filename_fn: Callable[[str, str], str],
) -> list[tuple[_AuxLayer, tuple[Path, date_type] | None]]:
    """Pasangkan tiap lapisan aux yang diminta level ini dengan berkasnya di
    disk (None kalau tidak ada untuk D maupun D-1)."""
    tier = "cog" if level == PROCESSED else "aligned"
    out = []
    for layer in _AUX_LAYERS_BY_SOURCE[source][level]:
        hit = _find_aux_daily_file(
            dataset_id, dataset_name, GROUP_BY_SOURCE[source],
            lambda d, k=layer.file_key: filename_fn(k, d.strftime("%Y%m%d")),
            feature_date, tier=tier,
        )
        out.append((layer, hit))
    return out


def _aoi_reference_grid(
    aoi_bbox: tuple[float, float, float, float]
) -> tuple[object, object, tuple[int, int]]:
    """Grid referensi dari AOI saja, untuk tanggal fusi yang tidak punya scene Sentinel-1."""
    from rasterio.transform import from_origin

    from etl.module8_gpm_download import S1_RESOLUTION_DEG

    min_lon, min_lat, max_lon, max_lat = aoi_bbox
    width = max(1, int(np.ceil(round((max_lon - min_lon) / S1_RESOLUTION_DEG, 6))))
    height = max(1, int(np.ceil(round((max_lat - min_lat) / S1_RESOLUTION_DEG, 6))))
    transform = from_origin(min_lon, max_lat, S1_RESOLUTION_DEG, S1_RESOLUTION_DEG)
    return transform, CRS.from_epsg(4326), (height, width)


def _dataset_fusion_grid(
    db: DatabaseClient,
    dataset_id: int,
    tier: str,
    aoi_bbox: tuple[float, float, float, float],
) -> tuple[object, object, tuple[int, int]]:
    """Grid tempat SEMUA stack dataset ini dirakit: kotak AOI penuh, pada
    resolusi raster Sentinel-1 dataset itu.
    """
    from rasterio.transform import from_origin

    from etl.module8_gpm_download import S1_RESOLUTION_DEG

    pinned = _load_pinned_grid(db, dataset_id)
    if pinned is not None:
        return pinned

    reference = _dataset_s1_reference_grid(db, dataset_id, tier)
    if reference is not None:
        ref_transform, ref_crs, _ = reference
        res_x, res_y = abs(float(ref_transform.a)), abs(float(ref_transform.e))
        origin = "s1_raster"
    else:
        ref_crs = CRS.from_epsg(4326)
        res_x = res_y = S1_RESOLUTION_DEG
        origin = "aoi_constant"

    min_lon, min_lat, max_lon, max_lat = aoi_bbox
    width = max(1, int(np.ceil(round((max_lon - min_lon) / res_x, 6))))
    height = max(1, int(np.ceil(round((max_lat - min_lat) / res_y, 6))))
    transform = from_origin(min_lon, max_lat, res_x, res_y)

    _pin_grid(db, dataset_id, transform, ref_crs, (height, width), origin)
    return transform, ref_crs, (height, width)


def _load_pinned_grid(
    db: DatabaseClient, dataset_id: int
) -> tuple[object, object, tuple[int, int]] | None:
    """Grid yang sudah dipaku untuk dataset ini, atau None kalau belum."""
    from rasterio.transform import Affine

    if db is None:
        return None
    with db.session() as sess:
        raw = sess.scalar(
            select(Dataset.fusion_grid).where(Dataset.dataset_id == dataset_id)
        )
    if not raw:
        return None
    try:
        t = [float(v) for v in raw["transform"]]
        shape = (int(raw["height"]), int(raw["width"]))
        crs = CRS.from_string(str(raw["crs"]))
    except (KeyError, TypeError, ValueError):
        logger.warning(
            "[M9] fusion_grid dataset %s tidak terbaca, dipaku ulang", dataset_id
        )
        return None
    return Affine(t[0], t[1], t[2], t[3], t[4], t[5]), crs, shape


def audit_dataset_grids(
    db: DatabaseClient, dataset_id: int, dataset_name: str
) -> dict:
    """Periksa semua stack fusion dataset ini terhadap grid yang dipaku."""
    pinned = _load_pinned_grid(db, dataset_id)
    result: dict = {"pinned": None, "matching": [], "mismatched": []}
    if pinned is None:
        return result
    _transform, _crs, shape = pinned
    result["pinned"] = {"height": shape[0], "width": shape[1]}

    root = fm.get_dataset_root(dataset_id, dataset_name)
    if not root.exists():
        return result

    for path in sorted(root.rglob("*.h5")):
        try:
            with h5py.File(path, "r") as h:
                got = (int(h.attrs["height"]), int(h.attrs["width"]))
        except (OSError, KeyError):
            continue
        entry = {"file": path.name, "height": got[0], "width": got[1]}
        if got == shape:
            result["matching"].append(entry)
        else:
            result["mismatched"].append(entry)
    return result


def audit_dataset_coverage(
    db: DatabaseClient, dataset_id: int, dataset_name: str,
    layer: str = "sentinel1/VV", drop_ratio: float = 0.7,
) -> dict:
    """Periksa apakah ada stack fusion dataset ini yang kehilangan frame S1."""
    result: dict = {"baseline": None, "clean": [], "dropped": [], "recurring_low": []}
    root = fm.get_dataset_root(dataset_id, dataset_name)
    if not root.exists():
        return result

    entries = []
    for path in sorted(root.rglob("*.h5")):
        try:
            with h5py.File(path, "r") as h:
                grp = h
                for part in layer.split("/"):
                    grp = grp[part]
                vf = float(grp.attrs["valid_fraction"])
        except (OSError, KeyError):
            continue
        entries.append({"file": path.name, "valid_fraction": round(vf, 6)})

    if not entries:
        return result

    baseline = max(e["valid_fraction"] for e in entries)
    result["baseline"] = baseline
    threshold = baseline * drop_ratio
    below = [e for e in entries if e["valid_fraction"] < threshold]
    for entry in entries:
        if entry["valid_fraction"] >= threshold:
            result["clean"].append(entry)

    TIER_TOLERANCE = 0.03
    below_sorted = sorted(below, key=lambda e: e["valid_fraction"])
    clusters: list[list[dict]] = []
    for entry in below_sorted:
        if clusters and entry["valid_fraction"] - clusters[-1][-1]["valid_fraction"] <= TIER_TOLERANCE:
            clusters[-1].append(entry)
        else:
            clusters.append([entry])
    for cluster in clusters:
        if len(cluster) >= 2:
            result["recurring_low"].extend(cluster)
        else:
            result["dropped"].extend(cluster)
    return result


def _warn_on_coverage_drop(
    db: DatabaseClient, dataset_id: int, dataset_name: str
) -> None:
    """Teriakkan ke log kalau ada stack dengan cakupan jauh di bawah tanggal lain."""
    try:
        audit = audit_dataset_coverage(db, dataset_id, dataset_name)
    except Exception as exc:
        logger.debug("[M9] audit cakupan dilewati: %s", exc)
        return
    recurring = audit.get("recurring_low") or []
    if recurring:
        logger.info(
            "[M9] dataset %s punya %d stack dengan cakupan sentinel1/VV lebih "
            "rendah tapi BERULANG di dataset ini (baseline valid_fraction=%.4f) "
            "-- kemungkinan besar swath S1 memang cuma menutupi sebagian AOI "
            "pada tanggal-tanggal ini (partial swath asli, bukan bug mosaik): %s",
            dataset_id, len(recurring), audit["baseline"],
            ", ".join(f"{b['file']} ({b['valid_fraction']:.3f})" for b in recurring[:8]),
        )
    bad = audit.get("dropped") or []
    if not bad:
        return
    logger.warning(
        "[M9] dataset %s punya %d stack dengan cakupan sentinel1/VV jauh di "
        "bawah tanggal lain di dataset ini DAN TERISOLASI (tidak ada tanggal "
        "lain dengan valid_fraction serupa) -- baseline valid_fraction=%.4f -- "
        "kemungkinan mosaik kehilangan frame, periksa scene_results_for_date: %s",
        dataset_id, len(bad), audit["baseline"],
        ", ".join(f"{b['file']} ({b['valid_fraction']:.3f})" for b in bad[:5]),
    )


def _warn_on_grid_drift(
    db: DatabaseClient, dataset_id: int, dataset_name: str
) -> None:
    """Teriakkan ke log kalau ada stack yang tidak berhimpit dengan grid dataset."""
    try:
        audit = audit_dataset_grids(db, dataset_id, dataset_name)
    except Exception as exc:
        logger.debug("[M9] audit grid dilewati: %s", exc)
        return
    bad = audit.get("mismatched") or []
    if not bad:
        return
    pinned = audit["pinned"]
    logger.warning(
        "[M9] dataset %s punya %d stack di grid BERBEDA dari grid dataset "
        "(%dx%d) -- deret waktunya tidak bisa ditumpuk sampai dirakit ulang: %s",
        dataset_id, len(bad), pinned["height"], pinned["width"],
        ", ".join(f"{b['file']} ({b['height']}x{b['width']})" for b in bad[:5]),
    )


def _pin_grid(
    db: DatabaseClient,
    dataset_id: int,
    transform: object,
    crs: object,
    shape: tuple[int, int],
    origin: str,
) -> None:
    """Simpan grid dataset supaya jalan berikutnya memakai yang sama persis."""
    if db is None:
        return

    payload = {
        "transform": [
            float(transform.a), float(transform.b), float(transform.c),
            float(transform.d), float(transform.e), float(transform.f),
        ],
        "height": int(shape[0]),
        "width": int(shape[1]),
        "crs": str(crs),
        "origin": origin,
        "pinned_at": datetime.now(timezone.utc).isoformat(),
    }
    with db.session() as sess:
        sess.execute(
            update(Dataset)
            .where(Dataset.dataset_id == dataset_id, Dataset.fusion_grid.is_(None))
            .values(fusion_grid=payload)
        )
        sess.commit()
    logger.info(
        "[M9] grid dataset %s dipaku: %dx%d dari %s",
        dataset_id, shape[0], shape[1], origin,
    )


def _dataset_s1_reference_grid(
    db: DatabaseClient, dataset_id: int, tier: str
) -> tuple[object, object, tuple[int, int]] | None:
    """Grid raster S1 mana pun milik dataset ini di `tier`, atau None."""
    tier_enum = ProductTierEnum[str(tier).upper()]
    with db.session() as sess:
        paths = sess.scalars(
            select(DataProduct.file_path).where(
                DataProduct.dataset_id == dataset_id,
                DataProduct.product_tier == tier_enum,
                DataProduct.source == "SENTINEL1",
                DataProduct.is_latest == True,
                DataProduct.is_valid == True,
            ).order_by(DataProduct.product_id)
        ).all()
    for path in paths:
        if not path or not Path(path).exists():
            continue
        with rasterio.open(path) as ref:
            return ref.transform, ref.crs, (ref.height, ref.width)
    return None


def _build_fusion_stack_for_level(
    db: DatabaseClient,
    *,
    dataset_id: int,
    dataset_name: str,
    s1_date: date_type,
    aoi_bbox: tuple[float, float, float, float],
    scene_id: int | None,
    plan: ProcessingPlan,
    run_level: str,
    fusion_strategy: str | None,
    progress_cb: Callable[[str, int, int], None] | None,
    region_id: int | None = None,
    require_s1: bool = True,
    s1_offset_days: int | None = 0,
    s1_files: dict[str, str] | None = None,
    s1_member_scene_ids: tuple[int, ...] = (),
) -> FusionRun:
    """Bangun SATU stack HDF5 untuk `run_level`. Dipanggil sekali atau dua
    kali per tanggal fusi oleh create_fusion_stack.
    """
    from etl.module7_modis_download import band_filename as modis_band_filename
    from etl.module8_gpm_download import band_filename as gpm_band_filename

    lineage = LineageTracker(db)
    meta = MetadataManager(db)

    source_levels = plan.source_levels_for_run(run_level)
    source_tiers = {
        name: plan.sources[name].tier_for_run(run_level) for name in source_levels
    }
    s1_tier = source_tiers[S1_PLAN_NAME]

    s1 = (
        _find_s1_products(db, dataset_id, scene_id, tier=s1_tier)
        if scene_id is not None else None
    )
    if s1 is not None and s1_files:
        s1 = {
            **s1,
            "vv_path": s1_files.get("VV") or s1["vv_path"],
            "vh_path": s1_files.get("VH") or s1["vh_path"],
            **(
                {"mosaic_of": sorted(members)}
                if len(members := {*s1_member_scene_ids, s1["scene_id"]}) > 1
                else {}
            ),
        }
        if s1.get("mosaic_of"):
            s1["member_paths"] = _s1_member_paths(
                db, dataset_id, s1["mosaic_of"], s1_tier
            )
    if s1 is None or (not s1["vv_path"] and not s1["vh_path"]):
        if require_s1:
            raise RuntimeError(
                f"No S1 {s1_tier} product found for scene_id={scene_id} "
                f"s1_date={s1_date.isoformat()} (run level {run_level})"
            )
        if region_id is None:
            raise RuntimeError(
                "require_s1=False needs a region_id for the fusion_products row "
                "of a day without a Sentinel-1 scene"
            )
        logger.info(
            "[M9] tanggal=%s tanpa scene S1 (strategi=%s): stack ditulis dengan "
            "group sentinel1/ berisi NaN di atas grid AOI",
            s1_date.isoformat(), fusion_strategy,
        )
        s1 = {
            "vv_path": None,
            "vh_path": None,
            "vv_product_id": None,
            "vh_product_id": None,
            "region_id": region_id,
            "scene_id": None,
            "acquisition_datetime": datetime.combine(
                s1_date, datetime.min.time(), tzinfo=timezone.utc
            ),
        }
        s1_offset_days = None

    ref_transform, ref_crs, ref_shape = _dataset_fusion_grid(
        db, dataset_id, s1_tier, aoi_bbox
    )

    expected_layers = fusion_layers_for(source_levels)
    total_layers = len(expected_layers)
    done = 0
    date_key = s1_date.strftime("%Y%m%d")
    subfolder = SUBFOLDER.get(str(fusion_strategy).strip().upper()) if fusion_strategy else None
    out_dir = fm.ensure_fusion_dir(dataset_id, dataset_name, date_key, subfolder)
    h5_path = out_dir / fusion_h5_name(date_key, run_level, fusion_strategy)
    json_path = out_dir / fusion_metadata_name(date_key, run_level, fusion_strategy)
    processing_dt = datetime.now(tz=timezone.utc)
    layers = _FusionH5Layers(h5_path, ref_shape)
    layer_sources: dict[str, dict] = {}
    coverage: dict[str, float] = {}
    found_dates: list[date_type] = []
    offsets: dict[str, int | None] = {MODIS_PLAN_NAME: None, GPM_PLAN_NAME: None}

    def _tick(name: str) -> None:
        nonlocal done
        done += 1
        if progress_cb:
            progress_cb(name, done, total_layers)

    for band, path_key in (("VV", "vv_path"), ("VH", "vh_path")):
        name = f"sentinel1/{band}"
        values = (
            _reproject_to_grid(
                Path(s1[path_key]), ref_transform, ref_crs, ref_shape,
                Resampling.nearest, float("nan"),
            )
            if s1[path_key]
            else np.full(ref_shape, np.nan, dtype="float32")
        )
        coverage[name] = _valid_fraction(values)
        source_paths = s1.get("member_paths", {}).get(band) or (
            [s1[path_key]] if s1[path_key] else []
        )
        layers.add(name, values, attrs={
            "units": LAYER_UNITS.get(name),
            "source_date": s1_date.isoformat() if s1[path_key] else None,
            "acquisition_datetime_utc": (
                _as_utc(s1["acquisition_datetime"]).isoformat()
                if s1[path_key] else None
            ),
            "s1_offset_days": s1_offset_days,
            "source_paths": [str(p) for p in source_paths] or None,
            "valid_fraction": round(coverage[name], 6),
        })
        if s1[path_key] is None:
            logger.warning(
                "[M9] S1 %s missing at %s for scene=%s, filled with NaN",
                band, s1_tier, s1["scene_id"],
            )
        layer_sources[name] = {
            "path": (
                str(source_paths[0]) if len(source_paths) == 1
                else s1[path_key] if not source_paths else None
            ),
            "paths": [str(p) for p in source_paths],
            "date": s1_date.isoformat(),
            "tier": s1_tier,
            "processing_level": source_levels[S1_PLAN_NAME],
            "valid_fraction": coverage[name],
        }
        _tick(name)

    center_dt = s1["acquisition_datetime"]

    for source, filename_fn in (
        (MODIS_PLAN_NAME, modis_band_filename),
        (GPM_PLAN_NAME, gpm_band_filename),
    ):
        if source not in source_levels:
            continue
        group = GROUP_BY_SOURCE[source]
        level = source_levels[source]
        tier = source_tiers[source]
        for layer, hit in _aux_layers_for_run(
            dataset_id, dataset_name, source, level, s1_date, filename_fn
        ):
            name = f"{group}/{layer.name}"
            values = None
            if hit:
                try:
                    values = _reproject_to_grid(
                        hit[0], ref_transform, ref_crs, ref_shape,
                        resampling=layer.resampling, fill_value=np.nan,
                        band=layer.band,
                    )
                except _MissingBand as exc:
                    logger.warning("[M9] %s dilewati: %s", name, exc)
            if values is not None:
                if layer.categorical:
                    values = np.where(
                        np.isnan(values), MODIS_NODATA_U8, values
                    ).astype("uint8")
                coverage[name] = _valid_fraction(values)
                tags = _source_tags(hit[0])
                day_offset = (hit[1] - s1_date).days
                hours_after = (
                    _hours_after_acquisition(
                        tags.get("window_end_utc"), s1["acquisition_datetime"]
                    )
                    if s1.get("vv_path") or s1.get("vh_path") else None
                )
                layers.add(name, values, attrs={
                    **tags,
                    "units": LAYER_UNITS.get(name),
                    "source_date": hit[1].isoformat(),
                    "day_offset": day_offset,
                    "source_path": str(hit[0]),
                    "valid_fraction": round(coverage[name], 6),
                    "hours_after_s1_acquisition": hours_after,
                })
                layer_sources[name] = {
                    "path": str(hit[0]), "date": hit[1].isoformat(),
                    "day_offset": day_offset,
                    "tier": tier, "processing_level": level,
                    "valid_fraction": coverage[name],
                    **({"source_tags": tags} if tags else {}),
                    **(
                        {"hours_after_s1_acquisition": hours_after}
                        if hours_after is not None else {}
                    ),
                }
                found_dates.append(hit[1])
                offset = (hit[1] - s1_date).days
                if offsets[source] is None or abs(offset) < abs(offsets[source]):
                    offsets[source] = offset
            else:
                logger.warning(
                    "[M9] no %s %s %s product for %s or the day before",
                    source, layer.name, tier, s1_date.isoformat(),
                )
                layers.add(name, (
                    np.full(ref_shape, MODIS_NODATA_U8, dtype="uint8")
                    if layer.categorical
                    else np.full(ref_shape, np.nan, dtype="float32")
                ), attrs={"units": LAYER_UNITS.get(name), "valid_fraction": 0.0})
                coverage[name] = 0.0
                layer_sources[name] = {
                    "path": None, "date": None,
                    "tier": tier, "processing_level": level,
                    "valid_fraction": 0.0,
                }
            _tick(name)

    thin = {
        name: round(fraction, 4)
        for name, fraction in sorted(coverage.items())
        if fraction < LOW_COVERAGE_FRACTION
    }
    if thin:
        logger.warning(
            "[M9] %s level=%s: %d dari %d lapisan di bawah %.0f%% piksel valid %s",
            s1_date.isoformat(), run_level, len(thin), len(coverage),
            LOW_COVERAGE_FRACTION * 100, thin,
        )

    layers.finalize(
        acquisition_datetime=center_dt, processing_datetime=processing_dt,
        aoi_bbox=aoi_bbox, processing_level=run_level, source_levels=source_levels,
        fusion_strategy=fusion_strategy, crs=ref_crs, transform=ref_transform,
        extra_attrs={
            "feature_date": s1_date.isoformat(),
            "acquisition_datetime_utc": (
                _as_utc(center_dt).isoformat()
                if s1.get("vv_path") or s1.get("vh_path") else None
            ),
            "s1_offset_days": s1_offset_days,
            "temporal_offset_modis": offsets[MODIS_PLAN_NAME],
            "temporal_offset_gpm": offsets[GPM_PLAN_NAME],
            "aux_day_rule": "the feature date, or the day before; never after",
        },
    )

    def _register_nasa_scene(
        source: str, nasa_source: str, tile_id: str, short_name: str
    ) -> int | None:
        if source not in source_levels:
            return None
        anchors = _AUX_LAYERS_BY_SOURCE[source][source_levels[source]]
        if not anchors:
            return None
        hit = layer_sources.get(f"{GROUP_BY_SOURCE[source]}/{anchors[0].name}", {})
        if not hit.get("date"):
            return None
        return _get_or_create_nasa_scene(
            db, nasa_source, tile_id, short_name,
            date_type.fromisoformat(hit["date"]), s1["region_id"], Path(hit["path"]),
        )

    modis_scene_id = _register_nasa_scene(
        MODIS_PLAN_NAME, MODIS_SOURCE, MODIS_TILE_ID, MODIS_PRODUCT_SHORT_NAME
    )
    gpm_scene_id = _register_nasa_scene(
        GPM_PLAN_NAME, GPM_SOURCE, GPM_TILE_ID, GPM_PRODUCT_SHORT_NAME
    )

    days_since_s1 = max((abs((d - s1_date).days) for d in found_dates), default=0)

    with db.session() as sess:
        existing = sess.scalar(
            select(FusionProduct).where(
                FusionProduct.dataset_id == dataset_id,
                FusionProduct.feature_date == s1_date,
                FusionProduct.processing_level == run_level,
            )
        )
        if existing:
            existing.region_id = s1["region_id"]
            existing.s1_scene_id = s1["scene_id"]
            existing.modis_scene_id = modis_scene_id
            existing.gpm_scene_id = gpm_scene_id
            existing.days_since_s1 = days_since_s1
            existing.feature_stack_path = str(h5_path)
            existing.fusion_strategy = fusion_strategy
            existing.temporal_offset_modis = offsets[MODIS_PLAN_NAME]
            existing.temporal_offset_gpm = offsets[GPM_PLAN_NAME]
            existing.s1_offset_days = s1_offset_days
            sess.flush()
            fusion_id = existing.fusion_id
        else:
            fusion = FusionProduct(
                dataset_id=dataset_id,
                feature_date=s1_date,
                region_id=s1["region_id"],
                s1_scene_id=s1["scene_id"],
                modis_scene_id=modis_scene_id,
                gpm_scene_id=gpm_scene_id,
                days_since_s1=days_since_s1,
                feature_stack_path=str(h5_path),
                fusion_strategy=fusion_strategy,
                processing_level=run_level,
                s1_offset_days=s1_offset_days,
                temporal_offset_modis=offsets[MODIS_PLAN_NAME],
                temporal_offset_gpm=offsets[GPM_PLAN_NAME],
            )
            sess.add(fusion)
            sess.flush()
            fusion_id = fusion.fusion_id

    height, width = ref_shape
    checksum = lineage.compute_sha256(h5_path)
    _write_fusion_metadata_json(
        json_path, fusion_id, dataset_id, s1["region_id"], s1_date, s1,
        layer_sources, days_since_s1,
        center_dt, processing_dt, aoi_bbox, h5_path, height, width,
        processing_level=run_level,
        source_levels=source_levels,
        source_tiers=source_tiers,
        fusion_strategy=fusion_strategy,
        temporal_offsets={
            "modis": offsets[MODIS_PLAN_NAME], "gpm": offsets[GPM_PLAN_NAME],
        },
        checksum_sha256=checksum,
    )

    fusion_job_id = meta.insert_processing_job(
        None, "FUSION",
        parameters={
            "dataset_id": dataset_id, "s1_date": s1_date.isoformat(),
            "processing_level": run_level, "source_levels": source_levels,
        },
    )
    meta.start_job(fusion_job_id)
    try:
        fusion_product_id = meta.insert_data_product(
            scene_id=None, job_id=fusion_job_id, dataset_id=dataset_id,
            product_tier=tn.FUSED, source=fm.FUSION_DB_SOURCE,
            product_type="FUSION_H5",
            band_name=f"FUSION_{run_level}",
            file_path=str(h5_path), file_name=h5_path.name,
            file_size_mb=round(h5_path.stat().st_size / (1024 ** 2), 3),
            data_hash_sha256=checksum,
            file_format="HDF5", rows=height, cols=width,
            processing_level=run_level,
            supersede_same_path=True,
        )
        parent_ids = [
            s1[key] for key in ("vv_product_id", "vh_product_id") if s1.get(key)
        ]
        for member_scene_id in s1_member_scene_ids:
            if member_scene_id == s1["scene_id"]:
                continue
            member = _find_s1_products(db, dataset_id, member_scene_id, tier=s1_tier)
            if not member:
                continue
            parent_ids.extend(
                member[key] for key in ("vv_product_id", "vh_product_id")
                if member.get(key)
            )
        for parent_id in dict.fromkeys(parent_ids):
            lineage.record_transformation(
                parent_id, fusion_product_id, "FUSION", fusion_job_id,
                {"aoi_bbox": list(aoi_bbox), "processing_level": run_level},
            )
    except Exception as exc:
        meta.complete_job(
            fusion_job_id, status=JobStatusEnum.FAILED,
            error_code=type(exc).__name__, error_message=str(exc)[:2000],
        )
        raise
    meta.complete_job(fusion_job_id)

    logger.info(
        "[M9] fusion_id=%d dataset=%s date=%s level=%s sources=%s path=%s hash=%s",
        fusion_id, dataset_id, s1_date.isoformat(), run_level, source_levels,
        h5_path, checksum[:12],
    )

    _warn_on_grid_drift(db, dataset_id, dataset_name)
    _warn_on_coverage_drop(db, dataset_id, dataset_name)

    return FusionRun(
        fusion_id=fusion_id,
        processing_level=run_level,
        h5_path=h5_path,
        json_path=json_path,
        layers=tuple(layer_sources),
        source_levels=source_levels,
        product_id=fusion_product_id,
        checksum_sha256=checksum,
    )


def create_fusion_stack(
    dataset_id: int,
    dataset_name: str,
    s1_date: date_type,
    aoi_bbox: tuple[float, float, float, float],
    scene_id: int,
    db: DatabaseClient | None = None,
    progress_cb: Callable[[str, int, int], None] | None = None,
    plan: ProcessingPlan | None = None,
    fusion_strategy: str | None = None,
    region_id: int | None = None,
    require_s1: bool = True,
    s1_offset_days: int | None = 0,
    s1_files_by_level: dict[str, dict[str, str]] | None = None,
    s1_member_scene_ids: tuple[int, ...] | Sequence[int] | None = None,
) -> list[FusionRun]:
    """Bangun stack fitur HDF5 untuk scene Sentinel-1 `scene_id` (akuisisi
    `s1_date`), mencocokkan produk MODIS/GPM milik tanggal `s1_date` (atau
    sehari sebelumnya, tidak pernah sesudahnya). Ini deliverable tier FUSION.
    """
    owns_db = db is None
    db = db or DatabaseClient.from_env()

    try:
        plan = plan or load_processing_plan(db, dataset_id)
        if not plan.is_configured(S1_PLAN_NAME):
            raise RuntimeError(
                f"FUSION dataset={dataset_id} was requested without SENTINEL1 in "
                "dataset_source_config. Fusion in this pipeline is anchored to the grid "
                "and acquisition date of the S1 scene; without S1 there is no "
                "reference grid or date to pair with "
                "(DOCS/PIPELINE.md)."
            )

        return [
            _build_fusion_stack_for_level(
                db,
                dataset_id=dataset_id,
                dataset_name=dataset_name,
                s1_date=s1_date,
                aoi_bbox=aoi_bbox,
                scene_id=scene_id,
                plan=plan,
                run_level=run_level,
                fusion_strategy=fusion_strategy,
                progress_cb=progress_cb,
                region_id=region_id,
                require_s1=require_s1,
                s1_offset_days=s1_offset_days,
                s1_files=(s1_files_by_level or {}).get(run_level),
                s1_member_scene_ids=tuple(s1_member_scene_ids or ()),
            )
            for run_level in plan.output_levels()
        ]

    finally:
        if owns_db:
            db.dispose()
