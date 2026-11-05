"""Orchestrator dataset: menyusun DAG pemrosesan dari konfigurasi per-satelit."""
from __future__ import annotations
import json
import logging
import os
import re
import shutil
import threading
import time
import traceback
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import rasterio
from shapely import wkt as shapely_wkt
from etl.database_client import Dataset, DatabaseClient, DatasetJob, LiveScene
from etl.dataset_manager import (
    DatasetManager,
    compute_skip_stages,
    compute_tiers_to_delete,
    get_cancel_event,
    get_pause_event,
)
from etl import download_guard as dg
from etl import folder_manager as fm
from etl.lineage_tracker import LineageTracker
from etl.metadata_manager import MetadataManager
from etl.fusion_strategies import DEFAULT_S1_MATCH_TOLERANCE_DAYS, FusionPlan, plan_fusion
from etl.module1_download import (
    MIN_S1_AOI_COVERAGE,
    aoi_coverage,
    discover_scenes,
    download_scene,
)
from etl.module1b_calibrate import run as calibrate_run
from etl.module2_crop import run as crop_run
from etl.module3_lee_filter import run as lee_run
from etl.module4_gold_export import export_scene_to_gold, gold_product_type
from etl.module6_analytics import (
    classify_quality,
    compute_band_metrics,
    load_quality_thresholds,
    threshold_for,
)
from etl.module9_fusion import (
    create_fusion_stack,
    ensure_aux_inputs_for_date,
    fusion_layers_for,
)
from etl.module10_generate_preview import (
    generate_previews,
    tier_for_level as preview_tier_for_level,
)
from etl.processing_plan import (
    PROCESSED,
    RAW,
    ProcessingPlan,
    SourcePlan,
    load_processing_plan,
)
from etl.processing_plan import SENTINEL1 as S1_SOURCE_NAME
from etl.s1_mosaic import mosaic_frames
from etl.pipeline_logger import (
    PipelineLogger,
    adopt_dataset_log_scope,
    dataset_log_file,
)

from etl import tier_names as tn

logger = logging.getLogger(__name__)

_MAX_CONCURRENT_SCENE_PIPELINES = int(os.getenv("PIPELINE_MAX_CONCURRENT_SCENES", "2"))
_pipeline_semaphore = dg.PrioritySemaphore(_MAX_CONCURRENT_SCENE_PIPELINES)

LIVE_JOB_TYPE = "LIVE_INGEST"


@dataclass
class _JobContext:
    db: DatabaseClient
    dsmgr: DatasetManager
    meta: MetadataManager
    lineage: LineageTracker
    plog: PipelineLogger
    job_id: int
    dataset_id: int
    dataset_name: str
    region_id: int
    bbox_wkt: str
    bbox_tuple: tuple[float, float, float, float]
    required_tiers: list[str]
    skip_stages: set[str]
    base_dir: Path
    plan: ProcessingPlan
    fusion_strategy: str | None
    fusion_plan: FusionPlan | None
    preview_options: list[str] | None
    pause_event: threading.Event
    cancel_event: threading.Event
    expected_pids_by_date: dict[str, set[str]] = field(default_factory=dict)
    failed_scene_keys: set[str] = field(default_factory=set)
    _failed_scene_keys_lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def s1_plan(self) -> SourcePlan:
        """Konfigurasi Sentinel-1. Hanya dipanggil dari jalur yang sudah
        memastikan S1 dikonfigurasi (_process_scene dan pemanggilnya)."""
        plan = self.plan.get(S1_SOURCE_NAME)
        if plan is None:  # pragma: no cover - dijaga run_dataset_job
            raise RuntimeError("the Sentinel-1 path was called without an S1 configuration")
        return plan
    log_path: Path | None = None
    low_priority: bool = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _bbox_tuple_from_wkt(wkt_str: str) -> tuple[float, float, float, float]:
    return shapely_wkt.loads(wkt_str).bounds


def _file_size_mb(path: str) -> float:
    return round(Path(path).stat().st_size / (1024 ** 2), 3)


def _raster_dims(path: str) -> tuple[int | None, int | None]:
    try:
        with rasterio.open(path) as src:
            return src.height, src.width
    except Exception:
        return None, None


def _dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _write_dataset_metadata(
    dsmgr: DatasetManager, dataset_id: int, total_size_bytes: int | None = None
) -> None:
    """Delegasi ke DatasetManager.write_metadata_file — definisinya pindah ke
    sana supaya create_dataset() bisa menulis metadata.json sejak dataset
    dibuat, bukan cuma orchestrator setelah job selesai."""
    try:
        dsmgr.write_metadata_file(dataset_id, total_size_bytes=total_size_bytes)
    except OSError:
        logger.warning("[ORCH] gagal tulis metadata.json dataset_id=%d", dataset_id, exc_info=True)


def _run_s1_chain(
    jc: _JobContext, scene_meta: dict, dl_result
) -> tuple[int, list[str], dict[str, list[str]], dict[str, dict[str, str]]]:
    """Cabang Sentinel-1 untuk satu scene: DOWNLOAD -> CALIBRATE -> CROP, lalu
    (hanya untuk level PROCESSED) LEE_FILTER -> QUALITY_ANALYTICS -> GOLD_EXPORT.
    """
    pid = scene_meta["product_identifier"]
    acq_date = dl_result.acquisition_datetime
    produced_tiers: list[str] = []
    produced_files: dict[str, list[str]] = {}

    scene_id = jc.meta.insert_satellite_scene(
        product_identifier=dl_result.product_identifier,
        acquisition_datetime=dl_result.acquisition_datetime,
        region_id=jc.region_id,
        bbox_wkt=jc.bbox_wkt,
        orbit_direction=dl_result.orbit_direction,
        orbit_number=dl_result.orbit_number,
        relative_orbit=dl_result.relative_orbit,
        cloud_cover_percent=dl_result.cloud_cover,
        raw_file_path=dl_result.zip_path or None,
        raw_file_size_mb=dl_result.file_size_mb,
        download_url=dl_result.download_url,
        checksum_md5=dl_result.checksum_md5,
    )
    jc.dsmgr.upsert_scene_job_state(
        jc.job_id, pid, scene_id=scene_id, current_stage="DOWNLOAD", stage_status="COMPLETED"
    )

    dl_job_id = jc.meta.insert_processing_job(scene_id, "DOWNLOAD", parameters={"dataset_id": jc.dataset_id})
    jc.meta.start_job(dl_job_id)
    s1_plan = jc.s1_plan
    raw_level = s1_plan.level_for_tier("RAW")
    bronze_level = s1_plan.level_for_tier(tn.ALIGNED)
    raw_vv_id = jc.meta.insert_data_product(
        scene_id=scene_id, job_id=dl_job_id, dataset_id=jc.dataset_id,
        product_tier="RAW", source="SENTINEL1", product_type="RAW_EXTRACTED_TIFF", band_name="VV",
        file_path=dl_result.vv_tif_path, file_name=Path(dl_result.vv_tif_path).name,
        file_size_mb=_file_size_mb(dl_result.vv_tif_path),
        data_hash_sha256=jc.lineage.compute_sha256(dl_result.vv_tif_path),
        processing_level=raw_level,
    )
    raw_vh_id = jc.meta.insert_data_product(
        scene_id=scene_id, job_id=dl_job_id, dataset_id=jc.dataset_id,
        product_tier="RAW", source="SENTINEL1", product_type="RAW_EXTRACTED_TIFF", band_name="VH",
        file_path=dl_result.vh_tif_path, file_name=Path(dl_result.vh_tif_path).name,
        file_size_mb=_file_size_mb(dl_result.vh_tif_path),
        data_hash_sha256=jc.lineage.compute_sha256(dl_result.vh_tif_path),
        processing_level=raw_level,
    )
    jc.meta.complete_job(dl_job_id, output_size_mb=dl_result.file_size_mb)
    produced_tiers.append("RAW")
    produced_files["RAW"] = [dl_result.vv_tif_path, dl_result.vh_tif_path]
    if dl_result.zip_path:
        produced_files["RAW"].append(dl_result.zip_path)

    if "CROP" in jc.skip_stages:
        return scene_id, produced_tiers, produced_files, {}
    jc.pause_event.wait()
    if jc.cancel_event.is_set():
        return scene_id, produced_tiers, produced_files, {}

    jc.dsmgr.upsert_scene_job_state(jc.job_id, pid, current_stage="CROP", stage_status="RUNNING")
    crop_job_id = jc.meta.insert_processing_job(
        scene_id, "CROP", parameters={"bbox": list(jc.bbox_tuple), "dataset_id": jc.dataset_id}
    )
    jc.meta.start_job(crop_job_id)

    calib_dir = fm.get_scratch_dir(jc.dataset_id, jc.dataset_name, pid)
    with jc.plog.stage(
        jc.dataset_id, pid, module="MODULE1B_CALIBRATE", stage="CALIBRATE",
        message="Applying radiometric calibration",
        input_vv=dl_result.vv_tif_path, input_vh=dl_result.vh_tif_path,
    ) as st:
        calib_dir.mkdir(parents=True, exist_ok=True)
        calib_vv, calib_vh = calibrate_run(dl_result.zip_path, dl_result.vv_tif_path, dl_result.vh_tif_path, str(calib_dir))
        st.output(output_vv=calib_vv, output_vh=calib_vh)

    bronze_dir = fm.get_scene_dir(jc.dataset_id, jc.dataset_name, "aligned", "sentinel1", pid)
    with jc.plog.stage(
        jc.dataset_id, pid, module="MODULE2_CROP", stage="CROP",
        message="Cropping to region boundaries", bbox=list(jc.bbox_tuple),
    ) as st:
        bronze_dir.mkdir(parents=True, exist_ok=True)
        crop_vv, crop_vh = crop_run(calib_vv, calib_vh, str(bronze_dir), bbox=jc.bbox_tuple)
        st.output(
            output_vv=crop_vv, output_vh=crop_vh,
            file_size_mb=round(_file_size_mb(crop_vv) + _file_size_mb(crop_vh), 3),
        )

    shutil.rmtree(calib_dir, ignore_errors=True)

    vv_rows, vv_cols = _raster_dims(crop_vv)
    bronze_vv_id = jc.meta.insert_data_product(
        scene_id=scene_id, job_id=crop_job_id, dataset_id=jc.dataset_id,
        product_tier=tn.ALIGNED, source="SENTINEL1", product_type="CROPPED_TIFF", band_name="VV",
        file_path=crop_vv, file_name=Path(crop_vv).name,
        file_size_mb=_file_size_mb(crop_vv), data_hash_sha256=jc.lineage.compute_sha256(crop_vv),
        rows=vv_rows, cols=vv_cols, processing_level=bronze_level,
    )
    vh_rows, vh_cols = _raster_dims(crop_vh)
    bronze_vh_id = jc.meta.insert_data_product(
        scene_id=scene_id, job_id=crop_job_id, dataset_id=jc.dataset_id,
        product_tier=tn.ALIGNED, source="SENTINEL1", product_type="CROPPED_TIFF", band_name="VH",
        file_path=crop_vh, file_name=Path(crop_vh).name,
        file_size_mb=_file_size_mb(crop_vh), data_hash_sha256=jc.lineage.compute_sha256(crop_vh),
        rows=vh_rows, cols=vh_cols, processing_level=bronze_level,
    )
    jc.lineage.record_transformation(raw_vv_id, bronze_vv_id, "CROP", crop_job_id, {"bbox": list(jc.bbox_tuple)})
    jc.lineage.record_transformation(raw_vh_id, bronze_vh_id, "CROP", crop_job_id, {"bbox": list(jc.bbox_tuple)})
    jc.meta.complete_job(crop_job_id, cpu_usage_percent=st.cpu_peak_percent, memory_usage_mb=st.memory_peak_mb)
    produced_tiers.append(tn.ALIGNED)
    produced_files[tn.ALIGNED] = [crop_vv, crop_vh]
    s1_files_by_level: dict[str, dict[str, str]] = {RAW: {"VV": crop_vv, "VH": crop_vh}}
    jc.dsmgr.upsert_scene_job_state(jc.job_id, pid, current_stage="CROP", stage_status="COMPLETED")

    if "LEE_FILTER" in jc.skip_stages:
        if s1_plan.raw_only:
            logger.info(
                "[ORCH] pid=%s berhenti di BRONZE: SENTINEL1 dikonfigurasi RAW-only", pid
            )
        return scene_id, produced_tiers, produced_files, s1_files_by_level
    jc.pause_event.wait()
    if jc.cancel_event.is_set():
        return scene_id, produced_tiers, produced_files, s1_files_by_level

    jc.dsmgr.upsert_scene_job_state(jc.job_id, pid, current_stage="LEE_FILTER", stage_status="RUNNING")
    lee_job_id = jc.meta.insert_processing_job(scene_id, "LEE_FILTER", parameters={"window_size": 7, "looks": 1})
    jc.meta.start_job(lee_job_id)

    silver_dir = fm.get_scene_dir(jc.dataset_id, jc.dataset_name, "despeckled", "sentinel1", pid)
    with jc.plog.stage(
        jc.dataset_id, pid, module="MODULE3_LEE_FILTER", stage="LEE_FILTER",
        message="Applying Lee filter to reduce speckle", window_size=7, looks=1,
    ) as st:
        silver_dir.mkdir(parents=True, exist_ok=True)
        lee_vv, lee_vh = lee_run(crop_vv, crop_vh, str(silver_dir), window_size=7, looks=1)
        st.output(
            output_vv=lee_vv, output_vh=lee_vh,
            file_size_mb=round(_file_size_mb(lee_vv) + _file_size_mb(lee_vh), 3),
        )

    silver_vv_id = jc.meta.insert_data_product(
        scene_id=scene_id, job_id=lee_job_id, dataset_id=jc.dataset_id,
        product_tier=tn.DESPECKLED, source="SENTINEL1", product_type="LEE_FILTERED", band_name="VV",
        file_path=lee_vv, file_name=Path(lee_vv).name,
        file_size_mb=_file_size_mb(lee_vv), data_hash_sha256=jc.lineage.compute_sha256(lee_vv),
        processing_level=PROCESSED,
    )
    silver_vh_id = jc.meta.insert_data_product(
        scene_id=scene_id, job_id=lee_job_id, dataset_id=jc.dataset_id,
        product_tier=tn.DESPECKLED, source="SENTINEL1", product_type="LEE_FILTERED", band_name="VH",
        file_path=lee_vh, file_name=Path(lee_vh).name,
        file_size_mb=_file_size_mb(lee_vh), data_hash_sha256=jc.lineage.compute_sha256(lee_vh),
        processing_level=PROCESSED,
    )
    jc.lineage.record_transformation(bronze_vv_id, silver_vv_id, "LEE_FILTER", lee_job_id, {"window_size": 7, "looks": 1})
    jc.lineage.record_transformation(bronze_vh_id, silver_vh_id, "LEE_FILTER", lee_job_id, {"window_size": 7, "looks": 1})
    jc.meta.complete_job(lee_job_id, cpu_usage_percent=st.cpu_peak_percent, memory_usage_mb=st.memory_peak_mb)
    produced_tiers.append(tn.DESPECKLED)
    produced_files[tn.DESPECKLED] = [lee_vv, lee_vh]
    jc.dsmgr.upsert_scene_job_state(jc.job_id, pid, current_stage="LEE_FILTER", stage_status="COMPLETED")

    if "QUALITY_ANALYTICS" in jc.skip_stages:
        return scene_id, produced_tiers, produced_files, s1_files_by_level
    jc.pause_event.wait()
    if jc.cancel_event.is_set():
        return scene_id, produced_tiers, produced_files, s1_files_by_level

    jc.dsmgr.upsert_scene_job_state(jc.job_id, pid, current_stage="QUALITY_ANALYTICS", stage_status="RUNNING")
    qa_job_id = jc.meta.insert_processing_job(scene_id, "QUALITY_ANALYTICS", parameters={})
    jc.meta.start_job(qa_job_id)

    with jc.plog.stage(
        jc.dataset_id, pid, module="MODULE6_ANALYTICS", stage="QUALITY_ANALYTICS",
        message="Running quality assurance checks",
    ) as st:
        band_metrics: dict[str, dict] = {}
        thresholds = load_quality_thresholds(jc.db)
        for band, path, product_id in (("VV", lee_vv, silver_vv_id), ("VH", lee_vh, silver_vh_id)):
            thr = threshold_for(thresholds, band)
            m = compute_band_metrics(path, band, min_quality_score=thr.fail_below)
            m.quality_flag = classify_quality(m.quality_score, thr)
            band_metrics[band] = asdict(m)
            jc.meta.insert_quality_metrics(
                scene_id=scene_id, product_id=product_id, band_name=band,
                total_pixels=m.total_pixels, valid_pixels=m.valid_pixels, nodata_pixels=m.nodata_pixels,
                quality_score=m.quality_score, backscatter_mean_db=m.backscatter_mean_db,
                backscatter_std_db=m.backscatter_std_db, backscatter_min_db=m.backscatter_min_db,
                backscatter_max_db=m.backscatter_max_db, radiometric_consistency=m.radiometric_consistency,
                speckle_index=m.speckle_index, quality_flag=m.quality_flag,
            )
        jc.meta.complete_job(qa_job_id)

        qa_path = silver_dir / "metadata_qa.json"
        with open(qa_path, "w") as f:
            json.dump(
                {
                    "scene_id": scene_id,
                    "product_identifier": pid,
                    "acquisition_date": acq_date.isoformat() if hasattr(acq_date, "isoformat") else str(acq_date),
                    "bands": band_metrics,
                },
                f, indent=2, default=str,
            )

        avg_quality_score = round(sum(m["quality_score"] for m in band_metrics.values()) / len(band_metrics), 2) if band_metrics else None
        st.output(quality_score=avg_quality_score, bands=band_metrics)

    jc.dsmgr.upsert_scene_job_state(jc.job_id, pid, current_stage="QUALITY_ANALYTICS", stage_status="COMPLETED")

    if "GOLD_EXPORT" in jc.skip_stages:
        return scene_id, produced_tiers, produced_files, s1_files_by_level
    jc.pause_event.wait()
    if jc.cancel_event.is_set():
        return scene_id, produced_tiers, produced_files, s1_files_by_level

    jc.dsmgr.upsert_scene_job_state(jc.job_id, pid, current_stage="GOLD_EXPORT", stage_status="RUNNING")
    gold_job_id = jc.meta.insert_processing_job(
        scene_id, "GOLD_EXPORT",
        parameters={"dataset_id": jc.dataset_id, "source": "SENTINEL1"},
    )
    jc.meta.start_job(gold_job_id)

    with jc.plog.stage(
        jc.dataset_id, pid, module="MODULE4_GOLD_EXPORT", stage="GOLD_EXPORT",
        message="Exporting Sentinel-1 bands to analysis-ready COG",
    ) as st:
        gold_files = export_scene_to_gold(
            jc.dataset_id, jc.dataset_name, "sentinel1", pid,
            {"VV": lee_vv, "VH": lee_vh},
        )
        st.output(
            output_vv=gold_files.get("VV"), output_vh=gold_files.get("VH"),
            file_size_mb=round(
                sum(_file_size_mb(f) for f in gold_files.values() if Path(f).exists()), 3
            ),
        )

    gold_product_ids: dict[str, int] = {}
    for band, silver_product_id in (("VV", silver_vv_id), ("VH", silver_vh_id)):
        gold_path = gold_files.get(band)
        if not gold_path:
            continue
        g_rows, g_cols = _raster_dims(gold_path)
        gold_product_ids[band] = jc.meta.insert_data_product(
            scene_id=scene_id, job_id=gold_job_id, dataset_id=jc.dataset_id,
            product_tier=tn.COG, source="SENTINEL1",
            product_type=gold_product_type("sentinel1"), band_name=band,
            file_path=gold_path, file_name=Path(gold_path).name,
            file_size_mb=_file_size_mb(gold_path),
            data_hash_sha256=jc.lineage.compute_sha256(gold_path),
            file_format="COG", rows=g_rows, cols=g_cols,
            processing_level=PROCESSED,
        )
        jc.lineage.record_transformation(
            silver_product_id, gold_product_ids[band], "GOLD_EXPORT", gold_job_id,
            {"source": "sentinel1"},
        )
    jc.meta.complete_job(
        gold_job_id, cpu_usage_percent=st.cpu_peak_percent, memory_usage_mb=st.memory_peak_mb
    )
    produced_tiers.append(tn.COG)
    produced_files[tn.COG] = list(gold_files.values())
    s1_files_by_level[PROCESSED] = dict(gold_files)
    jc.dsmgr.upsert_scene_job_state(jc.job_id, pid, current_stage="GOLD_EXPORT", stage_status="COMPLETED")

    return scene_id, produced_tiers, produced_files, s1_files_by_level


@dataclass
class _SceneResult:
    """Hasil satu scene sampai SEBELUM PREVIEW/FUSION."""

    pid: str
    scene_id: int
    acquisition_date: date
    produced_tiers: list[str]
    produced_files: dict[str, list[str]]
    s1_files_by_level: dict[str, dict[str, str]]
    duration_seconds: float = 0.0


def _process_scene(jc: _JobContext, scene_meta: dict, dl_result) -> _SceneResult:
    """Pipeline satu scene Sentinel-1 sampai input aux tanggalnya siap."""
    pid = scene_meta["product_identifier"]
    acq_date = dl_result.acquisition_datetime

    scene_id, produced_tiers, produced_files, s1_files_by_level = _run_s1_chain(
        jc, scene_meta, dl_result
    )
    s1_date = acq_date.date()

    def _result() -> _SceneResult:
        return _SceneResult(
            pid=pid, scene_id=scene_id, acquisition_date=s1_date,
            produced_tiers=produced_tiers, produced_files=produced_files,
            s1_files_by_level=s1_files_by_level,
        )

    if jc.cancel_event.is_set():
        return _result()
    jc.pause_event.wait()
    if jc.cancel_event.is_set():
        return _result()

    aux_produced, _ = ensure_aux_inputs_for_date(
        jc.db, jc.dataset_id, jc.dataset_name, jc.region_id, jc.bbox_tuple, s1_date,
        plog=jc.plog, plan=jc.plan,
    )
    for aux_tier, aux_paths in aux_produced.items():
        produced_files.setdefault(aux_tier, []).extend(aux_paths)
        if aux_paths and aux_tier not in produced_tiers:
            produced_tiers.append(aux_tier)

    return _result()


def _mosaic_s1_by_level(
    jc: _JobContext, date_key: str, members: list[_SceneResult]
) -> dict[str, dict[str, str]]:
    """{level: {band: path}} untuk satu tanggal, gabungan SEMUA frame-nya."""
    scratch = fm.get_scratch_dir(jc.dataset_id, jc.dataset_name, date_key)
    mosaics: dict[str, dict[str, str]] = {}
    for level in jc.plan.output_levels():
        frames = [m.s1_files_by_level.get(level, {}) for m in members]
        frames = [f for f in frames if f]
        if not frames:
            continue
        files = mosaic_frames(frames, scratch, date_key=date_key, level=level)
        if files:
            mosaics[level] = files
    return mosaics


def _run_preview_for_date(
    jc: _JobContext, date_key: str, s1_date: date, members: list[_SceneResult],
    primary: _SceneResult, mosaics: dict[str, dict[str, str]],
) -> list[str]:
    """PREVIEW satu tanggal. Mengembalikan daftar berkas yang ditulis."""
    for member in members:
        jc.dsmgr.upsert_scene_job_state(
            jc.job_id, member.pid, current_stage="PREVIEW", stage_status="RUNNING"
        )
    preview_files: list[str] = []
    try:
        for level in jc.plan.output_levels():
            with jc.plog.stage(
                jc.dataset_id, primary.pid, module="MODULE10_PREVIEW", stage="PREVIEW",
                message=f"Rendering PNG preview level {level} from tier "
                        f"{preview_tier_for_level(level).upper()}",
                acquisition_date=date_key, processing_level=level,
                s1_frames=len(members),
            ) as st:
                preview_result = generate_previews(
                    jc.dataset_id, jc.dataset_name, s1_date,
                    s1_scene_key=primary.pid,
                    s1_files=mosaics.get(level),
                    processing_level=level,
                    options=jc.preview_options,
                )
                st.output(
                    output_dir=str(fm.get_preview_level_dir(
                        jc.dataset_id, jc.dataset_name, date_key, level
                    )),
                    grayscale_count=preview_result["counts"]["grayscale"],
                    colored_count=preview_result["counts"]["colored"],
                    composite_count=preview_result["counts"]["composite"],
                    skipped_count=preview_result["counts"]["skipped"],
                    file_size_mb=preview_result["total_size_mb"],
                )
            preview_files.extend(preview_result["files"])
        for member in members:
            jc.dsmgr.upsert_scene_job_state(
                jc.job_id, member.pid, current_stage="PREVIEW", stage_status="COMPLETED"
            )
    except Exception:
        logger.exception(
            "[ORCH] PREVIEW gagal tanggal=%s pid=%s, lanjut ke FUSION",
            date_key, primary.pid,
        )
    return preview_files


def _run_fusion_for_date(
    jc: _JobContext, s1_date: date, members: list[_SceneResult],
    primary: _SceneResult, mosaics: dict[str, dict[str, str]],
) -> list[str]:
    """FUSION satu tanggal. Mengembalikan daftar berkas HDF5+JSON yang ditulis
    (kosong kalau fusi memang dilewati dataset ini)."""
    if "FUSION" in jc.skip_stages or not jc.plan.fusion_eligible(jc.fusion_strategy):
        logger.info(
            "[ORCH] pid=%s FUSION dilewati: sumber=%d strategi=%r skipped=%s",
            primary.pid, jc.plan.source_count, jc.fusion_strategy,
            "FUSION" in jc.skip_stages,
        )
        return []

    for member in members:
        jc.dsmgr.upsert_scene_job_state(
            jc.job_id, member.pid, current_stage="FUSION", stage_status="RUNNING"
        )

    planned_layers = sorted({
        layer
        for level in jc.plan.output_levels()
        for layer in fusion_layers_for(jc.plan.source_levels_for_run(level))
    })

    with jc.plog.stage(
        jc.dataset_id, primary.pid, module="MODULE9_FUSION", stage="FUSION",
        message="Fusing multi-modal data into H5", layers=planned_layers,
        processing_levels=list(jc.plan.output_levels()),
        s1_frames=len(members),
    ) as st:
        def _fusion_progress(layer_name: str, done: int, total: int) -> None:
            jc.plog.log_event(
                jc.dataset_id, primary.pid, "MODULE9_FUSION", "FUSION", "RUNNING",
                f"Fusing layer {layer_name} ({done}/{total})",
                {"progress_percent": round(done / total * 100, 1), "layer": layer_name},
            )

        runs = create_fusion_stack(
            jc.dataset_id, jc.dataset_name, s1_date, jc.bbox_tuple, primary.scene_id,
            db=jc.db, progress_cb=_fusion_progress,
            plan=jc.plan, fusion_strategy=jc.fusion_strategy,
            region_id=jc.region_id,
            s1_files_by_level=mosaics,
            s1_member_scene_ids=tuple(m.scene_id for m in members),
        )
        st.output(
            output_paths=[str(run.h5_path) for run in runs],
            processing_levels=[run.processing_level for run in runs],
            file_size_mb=round(
                sum(_file_size_mb(str(run.h5_path)) for run in runs
                    if run.h5_path.exists()), 3,
            ),
        )

    for member in members:
        jc.dsmgr.upsert_scene_job_state(
            jc.job_id, member.pid, current_stage="FUSION", stage_status="COMPLETED"
        )
    return [str(path) for run in runs for path in (run.h5_path, run.json_path)]


def _finalize_date(jc: _JobContext, members: list[_SceneResult]) -> None:
    """PREVIEW + FUSION untuk satu tanggal, sekali, di atas seluruh frame-nya."""
    if not members:
        return
    members = sorted(members, key=lambda m: m.pid)
    primary = members[0]
    s1_date = primary.acquisition_date
    date_key = s1_date.strftime("%Y%m%d")

    if jc.cancel_event.is_set():
        return
    jc.pause_event.wait()
    if jc.cancel_event.is_set():
        return

    if len(members) > 1:
        logger.info(
            "[ORCH] tanggal=%s: %d frame Sentinel-1 disatukan sebelum PREVIEW/FUSION (%s)",
            date_key, len(members), ", ".join(m.pid for m in members),
        )

    mosaics = _mosaic_s1_by_level(jc, date_key, members)

    if "PREVIEW" not in jc.skip_stages:
        preview_files = _run_preview_for_date(
            jc, date_key, s1_date, members, primary, mosaics
        )
        if preview_files:
            primary.produced_files["PREVIEW"] = preview_files

    if jc.cancel_event.is_set():
        return
    jc.pause_event.wait()
    if jc.cancel_event.is_set():
        return

    fused_files = _run_fusion_for_date(jc, s1_date, members, primary, mosaics)
    if fused_files:
        primary.produced_files[tn.FUSED] = fused_files
        if tn.FUSED not in primary.produced_tiers:
            primary.produced_tiers.append(tn.FUSED)


def _fuse_days_without_s1(
    jc: _JobContext, s1_dates: set[date], scenes: list[dict] | None = None
) -> int:
    """Rakit HDF5 untuk tanggal fusi yang tidak punya scene Sentinel-1."""
    plan = jc.fusion_plan
    if plan is None or plan.requires_s1:
        return 0

    pending = [d for d in plan.fusion_dates if d not in s1_dates]
    if not pending:
        return 0

    logger.info(
        "[ORCH] job_id=%d strategi=%s: merakit %d tanggal fusi tanpa scene S1",
        jc.job_id, plan.strategy, len(pending),
    )

    pid_by_date: dict[date, str] = {}
    for meta_row in scenes or []:
        d = _scene_date(meta_row)
        if d is not None:
            pid_by_date.setdefault(d, meta_row["product_identifier"])

    written = 0
    for day in pending:
        jc.pause_event.wait()
        if jc.cancel_event.is_set():
            break
        date_key = day.strftime("%Y%m%d")
        anchor = plan.anchor(day)
        anchor_pid = pid_by_date.get(anchor) if anchor else None
        anchor_scene = (
            jc.meta.get_scene_by_pid(anchor_pid) if anchor_pid else None
        )
        try:
            runs = create_fusion_stack(
                jc.dataset_id, jc.dataset_name, day, jc.bbox_tuple,
                anchor_scene["scene_id"] if anchor_scene else None,
                db=jc.db, plan=jc.plan, fusion_strategy=jc.fusion_strategy,
                region_id=jc.region_id, require_s1=False,
                s1_offset_days=plan.offset_days(day) if anchor_scene else None,
            )
            written += 1
            jc.plog.log_event(
                jc.dataset_id, date_key, "MODULE9_FUSION", "FUSION", "COMPLETED",
                f"Fusi {date_key} tanpa scene S1: {len(runs)} stack",
                {"date": day.isoformat(), "s1_offset_days": plan.offset_days(day),
                 "output_paths": [str(r.h5_path) for r in runs]},
            )
        except Exception as exc:
            logger.exception(
                "[ORCH] fusi tanpa-S1 gagal tanggal=%s job_id=%d", day, jc.job_id
            )
            _record_worker_failure(jc, date_key, "FUSION", exc)
            jc.meta.fail_open_jobs(exc)
            jc.dsmgr.increment_job_counters(jc.job_id, failed=1)

    return written


_FUSION_ONLY_DISPOSABLE: tuple[str, ...] = (
    "raw", "aligned", "despeckled", "indices", "accumulated", "cog",
    "bronze", "silver", "gold",
)


def _sweep_scratch(jc: _JobContext) -> int:
    """Buang _work/ di akhir job -- KECUALI folder scene yang gagal run ini."""
    scratch_root = jc.base_dir / fm.SCRATCH_DIRNAME
    if not scratch_root.is_dir():
        return 0

    with jc._failed_scene_keys_lock:
        protected_slugs = {fm.scratch_slug(key) for key in jc.failed_scene_keys}

    long_root = fm.long_path(scratch_root)
    deleted = 0
    kept_dirs: list[str] = []
    for entry in long_root.iterdir():
        if entry.name in protected_slugs:
            kept_dirs.append(entry.name)
            continue
        entry_files = [entry] if entry.is_file() else [p for p in entry.rglob("*") if p.is_file()]
        try:
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        except OSError as exc:
            logger.error("[ORCH] gagal menyapu %s: %s", entry, exc)
            continue
        deleted += len(entry_files)

    if not kept_dirs:
        try:
            long_root.rmdir()
        except OSError as exc:
            logger.error("[ORCH] gagal membuang %s: %s", scratch_root, exc)

    if deleted:
        logger.info(
            "[ORCH] job_id=%d _work/ disapu: %d berkas antara dihapus", jc.job_id, deleted,
        )
    if kept_dirs:
        logger.info(
            "[ORCH] job_id=%d _work/: %d folder scene gagal dipertahankan untuk resume: %s",
            jc.job_id, len(kept_dirs), sorted(kept_dirs),
        )
    return deleted


def _apply_fusion_output_only(jc: _JobContext, fusion_written: bool) -> int:
    """Hapus artefak per-satelit setelah stack fusi selesai ditulis."""
    if not fusion_written:
        logger.warning(
            "[ORCH] job_id=%d fusion_output_only diminta tapi tidak ada stack "
            "fusi yang berhasil ditulis — artefak per-satelit DIPERTAHANKAN",
            jc.job_id,
        )
        return 0

    deleted = 0
    for tier in _FUSION_ONLY_DISPOSABLE:
        for tier_dir in fm.tier_dirs_under(jc.base_dir, tier):
            for path in sorted(tier_dir.rglob("*"), reverse=True):
                try:
                    if path.is_file():
                        path.unlink()
                        deleted += 1
                    elif path.is_dir():
                        path.rmdir()
                except OSError as exc:
                    logger.error("[ORCH] gagal hapus %s: %s", path, exc)
            try:
                tier_dir.rmdir()
            except OSError:
                pass

    logger.info(
        "[ORCH] job_id=%d fusion_output_only: %d berkas per-satelit dihapus",
        jc.job_id, deleted,
    )
    return deleted


def _cleanup_scene_tiers(
    jc: _JobContext,
    pid: str,
    scene_id: int,
    produced_tiers: list[str],
    produced_files: dict[str, list[str]],
) -> None:
    tiers_to_delete = compute_tiers_to_delete(produced_tiers, jc.required_tiers)
    if not tiers_to_delete:
        return
    for tier in tiers_to_delete:
        scene_dirs: set[Path] = set()
        deleted_paths: list[str] = []
        for file_path in produced_files.get(tier, []):
            p = Path(file_path)
            scene_dirs.add(p.parent)
            if p.exists():
                try:
                    p.unlink()
                    deleted_paths.append(file_path)
                except OSError as exc:
                    logger.error("[ORCH] gagal hapus %s: %s", p, exc)
            else:
                deleted_paths.append(file_path)
        for d in scene_dirs:
            try:
                d.rmdir()
            except OSError:
                pass  # masih ada file scene lain di tanggal yang sama
        jc.meta.mark_products_invalid(scene_id=scene_id, dataset_id=jc.dataset_id, tier=tier)
        jc.meta.mark_products_invalid_by_paths(jc.dataset_id, deleted_paths)
    logger.info("[ORCH] cleanup pid=%s tiers dihapus=%s", pid, sorted(tiers_to_delete))


def _record_worker_failure(
    jc: _JobContext, pid: str, stage: str, exc: BaseException
) -> None:
    """Persist a worker-level failure to processing_logs."""
    with jc._failed_scene_keys_lock:
        jc.failed_scene_keys.add(pid)
    try:
        jc.plog.log_event(
            jc.dataset_id, pid, "ORCHESTRATOR", stage, "FAILED",
            f"{stage} failed: {exc}",
            {
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback": traceback.format_exc()[-4000:],
            },
        )
    except Exception:
        logger.exception("[ORCH] gagal mencatat kegagalan pid=%s stage=%s", pid, stage)


class _JobCancelled(Exception):
    """Raised from a progress callback to abort work already in flight."""


S1_PARALLEL_DOWNLOADS = max(1, min(4, int(os.getenv("S1_PARALLEL_DOWNLOADS", "3"))))


def _download_worker(jc: _JobContext, scenes: list[dict], download_queue: Queue) -> None:
    if jc.log_path:
        adopt_dataset_log_scope(jc.log_path)
    stop = threading.Event()  # cancel: scene yang belum mulai tidak diambil

    def _pool_init() -> None:
        dg.set_low_priority(jc.low_priority)
        dg.set_context(jc.dataset_id)
        if jc.log_path:
            adopt_dataset_log_scope(jc.log_path)

    def _task(scene_meta: dict) -> None:
        if stop.is_set():
            return
        try:
            if not _download_one(jc, scene_meta, download_queue):
                stop.set()
        except Exception:
            logger.exception(
                "[ORCH] download worker error pid=%s job_id=%d",
                scene_meta.get("product_identifier"), jc.job_id,
            )

    with ThreadPoolExecutor(
        max_workers=1 if jc.low_priority else S1_PARALLEL_DOWNLOADS,
        thread_name_prefix="_download_worker",
        initializer=_pool_init,
    ) as pool:
        for _ in pool.map(_task, scenes):
            pass
    download_queue.put(None)


def _download_one(jc: _JobContext, scene_meta: dict, download_queue: Queue) -> bool:
    """Unduh satu scene dan antrekan hasilnya. False = job dibatalkan, jangan
    mulai scene lain."""
    jc.pause_event.wait()
    if jc.cancel_event.is_set():
        return False
    pid = scene_meta["product_identifier"]
    state = jc.dsmgr.get_scene_job_state(jc.job_id, pid)
    if state and DatasetManager.scene_is_done(state.get("current_stage"), state.get("stage_status")):
        return True
    try:
        jc.dsmgr.upsert_scene_job_state(
            jc.job_id, pid, current_stage="DOWNLOAD", stage_status="RUNNING", started_at=_now()
        )
        raw_dir = fm.ensure_scene_dir(
            jc.dataset_id, jc.dataset_name, "raw", "sentinel1", pid
        )

        def _download_progress(pct: float, detail: str) -> None:
            if jc.cancel_event.is_set():
                raise _JobCancelled(f"job_id={jc.job_id} dibatalkan")
            jc.plog.log_event(
                jc.dataset_id, pid, "MODULE1_DOWNLOAD", "DOWNLOAD", "RUNNING",
                f"Downloading: {detail}", {"progress_percent": round(pct, 1)},
            )

        with jc.plog.stage(
            jc.dataset_id, pid, module="MODULE1_DOWNLOAD", stage="DOWNLOAD",
            message="Downloading scene from ESA server",
            expected_size_mb=scene_meta.get("size_mb"),
        ) as st:
            result = download_scene(
                scene_meta, output_dir=str(raw_dir), keep_raw=True, progress_cb=_download_progress,
                reuse_root=fm.DATA_ROOT, cancel_event=jc.cancel_event,
            )
            st.output(
                output_vv=result.vv_tif_path, output_vh=result.vh_tif_path,
                file_size_mb=result.file_size_mb, checksum_md5=result.checksum_md5,
                message="Scene downloaded successfully",
            )
        jc.dsmgr.increment_job_counters(jc.job_id, downloaded=1)
        download_queue.put((scene_meta, result))
    except _JobCancelled:
        logger.info("[ORCH] download dibatalkan pid=%s job_id=%d", pid, jc.job_id)
        return False
    except Exception as exc:
        if jc.cancel_event.is_set():
            logger.info("[ORCH] download dibatalkan pid=%s job_id=%d", pid, jc.job_id)
            return False
        logger.exception("[ORCH] download gagal pid=%s job_id=%d", pid, jc.job_id)
        _record_worker_failure(jc, pid, "DOWNLOAD", exc)
        jc.dsmgr.upsert_scene_job_state(
            jc.job_id, pid, stage_status="FAILED", last_error=str(exc)[:2000], completed_at=_now()
        )
        jc.dsmgr.increment_job_counters(jc.job_id, failed=1)
    return True


_RECONCILE_LOG = "ORCH"

_BANDS = ("VV", "VH")


def _s1_cogs_by_pid(dataset_id: int, dataset_name: str) -> dict[str, dict[str, str]]:
    """Petakan {product_identifier_prefix: {band: path}} dari raster di disk."""
    from etl import folder_manager as fm

    root = fm.get_dataset_root(dataset_id, dataset_name)
    proc = root / "sentinel-1" / "PROCESSED"
    out: dict[str, dict[str, str]] = defaultdict(dict)
    if not proc.is_dir():
        return out
    for path in sorted(proc.glob("*.tif")):
        for band in _BANDS:
            if f"_{band}_" in path.name:
                stem = path.name.split("_calibrated_")[0]
                out[stem][band] = str(path)
                break
    return out


def _s1_raw_crops_by_pid(dataset_id: int, dataset_name: str) -> dict[str, dict[str, str]]:
    """Petakan {product_identifier_prefix: {band: path}} raster S1 tier RAW
    (crop sebelum Lee filter) di disk -- sumber `fusion_<tanggal>_hybrid_raw.h5`.
    """
    from etl import folder_manager as fm

    root = fm.get_dataset_root(dataset_id, dataset_name)
    raw_dir = root / "sentinel-1" / "RAW"
    out: dict[str, dict[str, str]] = defaultdict(dict)
    if not raw_dir.is_dir():
        return out
    for path in sorted(raw_dir.glob("*.tif")):
        for band in _BANDS:
            if f"_{band}_" in path.name:
                stem = path.name.split("_calibrated_")[0]
                out[stem][band] = str(path)
                break
    return out


def _match_cogs(pid: str, cogs: dict[str, dict[str, str]]) -> dict[str, str]:
    for stem, bands in cogs.items():
        if pid.startswith(stem):
            return bands
    return {}


def scene_results_for_date(db, job_id: int, jc, date_key: str) -> list:
    """`_SceneResult` tiap frame S1 tanggal itu, dirakit dari disk + database."""
    from sqlalchemy import select

    from etl.database_client import SceneJobState

    cogs = _s1_cogs_by_pid(jc.dataset_id, jc.dataset_name)
    raw_crops = _s1_raw_crops_by_pid(jc.dataset_id, jc.dataset_name)

    with db.session() as sess:
        rows = sess.execute(
            select(
                SceneJobState.product_identifier,
                SceneJobState.scene_id,
                SceneJobState.job_id,
            )
            .join(DatasetJob, DatasetJob.job_id == SceneJobState.job_id)
            .where(DatasetJob.dataset_id == jc.dataset_id)
        ).all()

    by_pid: dict[str, tuple[int, int]] = {}
    for pid, scene_id, row_job_id in rows:
        if date_key not in pid:
            continue
        if pid not in by_pid or row_job_id == job_id:
            by_pid[pid] = (scene_id, row_job_id)

    out = []
    matched_stems: set[str] = set()
    for pid, (scene_id, _row_job_id) in by_pid.items():
        bands = _match_cogs(pid, cogs)
        if not bands:
            logger.warning(
                "[%s] %s: raster PROCESSED tidak ditemukan, frame dilewati",
                _RECONCILE_LOG, pid,
            )
            continue
        for stem in cogs:
            if pid.startswith(stem):
                matched_stems.add(stem)
                break
        s1_files_by_level = {"PROCESSED": bands}
        raw_bands = _match_cogs(pid, raw_crops)
        if raw_bands:
            s1_files_by_level["RAW"] = raw_bands
        out.append(
            _SceneResult(
                pid=pid,
                scene_id=scene_id,
                acquisition_date=date(
                    int(date_key[:4]), int(date_key[4:6]), int(date_key[6:8])
                ),
                produced_tiers=[],
                produced_files={},
                s1_files_by_level=s1_files_by_level,
            )
        )

    for stem in cogs:
        if date_key not in stem or stem in matched_stems:
            continue
        logger.warning(
            "[%s] tanggal %s: COG %s ada di disk tapi tidak ada baris "
            "SceneJobState yang cocok di job manapun -- frame ini TIDAK "
            "ikut mosaik, hasil fusion tanggal ini kemungkinan terpotong",
            _RECONCILE_LOG, date_key, stem,
        )

    return sorted(out, key=lambda m: m.pid)


def _reconcile_date_members(
    jc: _JobContext, date_key: str, members: list[_SceneResult]
) -> list[_SceneResult]:
    """Gabungkan `members` (yang lewat antrean RUN INI) dengan frame tanggal
    ini yang sudah selesai diproses di run/resume SEBELUMNYA tapi tidak
    pernah masuk `pending` run ini.
    """
    try:
        on_disk = scene_results_for_date(jc.db, jc.job_id, jc, date_key)
    except Exception:
        logger.exception(
            "[ORCH] rekonsiliasi anggota tanggal=%s job_id=%d gagal, "
            "pakai antrean run ini apa adanya",
            date_key, jc.job_id,
        )
        return members

    by_pid = {m.pid: m for m in members}
    tambahan = [extra for extra in on_disk if extra.pid not in by_pid]
    if tambahan:
        logger.warning(
            "[ORCH] tanggal=%s job_id=%d: %d frame dari run sebelumnya "
            "digabung kembali sebelum finalize (%s) -- tanpa ini stack akan "
            "menimpa dirinya sendiri jadi cuma satu frame",
            date_key, jc.job_id, len(tambahan),
            ", ".join(sorted(e.pid for e in tambahan)),
        )
    for extra in tambahan:
        by_pid[extra.pid] = extra
    return sorted(by_pid.values(), key=lambda m: m.pid)


def _flush_date(
    jc: _JobContext, date_key: str, members: list[_SceneResult], cleanup_queue: Queue
) -> None:
    """Selesaikan satu tanggal: PREVIEW + FUSION sekali, lalu antre cleanup."""
    finalize_members = _reconcile_date_members(jc, date_key, members)
    try:
        _finalize_date(jc, finalize_members)
    except Exception as exc:
        logger.exception(
            "[ORCH] finalisasi tanggal=%s gagal job_id=%d", date_key, jc.job_id
        )
        _record_worker_failure(jc, date_key, "SCENE_PIPELINE", exc)
        jc.meta.fail_open_jobs(exc)
        jc.dsmgr.increment_job_counters(jc.job_id, failed=1)

    for member in sorted(members, key=lambda m: m.pid):
        storage_breakdown = {
            tier: round(sum(_file_size_mb(p) for p in paths if Path(p).exists()), 3)
            for tier, paths in member.produced_files.items()
        }
        jc.plog.log_event(
            jc.dataset_id, member.pid, "ORCHESTRATOR", "SCENE_PIPELINE", "COMPLETED",
            f"Scene processed successfully (tiers: {', '.join(member.produced_tiers)})",
            {
                "duration_seconds": round(member.duration_seconds, 3),
                "produced_tiers": member.produced_tiers,
                "storage_breakdown_mb": storage_breakdown,
                "total_size_mb": round(sum(storage_breakdown.values()), 3),
            },
        )
        cleanup_queue.put(
            (member.pid, member.scene_id, member.produced_tiers, member.produced_files)
        )


def _pipeline_worker(jc: _JobContext, download_queue: Queue, cleanup_queue: Queue) -> None:
    dg.set_low_priority(jc.low_priority)
    dg.set_context(jc.dataset_id)
    if jc.log_path:
        adopt_dataset_log_scope(jc.log_path)
    pending: dict[str, list[_SceneResult]] = {}
    while True:
        item = download_queue.get()
        if item is None:
            break
        jc.pause_event.wait()
        if jc.cancel_event.is_set():
            break
        scene_meta, dl_result = item
        pid = scene_meta["product_identifier"]
        _pipeline_semaphore.acquire(low=jc.low_priority)
        t0 = time.monotonic()
        try:
            result = _process_scene(jc, scene_meta, dl_result)
            result.duration_seconds = time.monotonic() - t0
            jc.dsmgr.increment_job_counters(jc.job_id, processed=1)
            date_key = result.acquisition_date.strftime("%Y%m%d")
            pending.setdefault(date_key, []).append(result)
        except Exception as exc:
            logger.exception("[ORCH] pipeline gagal pid=%s job_id=%d", pid, jc.job_id)
            _record_worker_failure(jc, pid, "SCENE_PIPELINE", exc)
            jc.meta.fail_open_jobs(exc)
            jc.dsmgr.upsert_scene_job_state(
                jc.job_id, pid, stage_status="FAILED", last_error=str(exc)[:2000], completed_at=_now()
            )
            jc.dsmgr.increment_job_counters(jc.job_id, failed=1)
        finally:
            _pipeline_semaphore.release()

        for ready in [
            d for d, members in pending.items()
            if jc.expected_pids_by_date.get(d)
            and {m.pid for m in members} >= jc.expected_pids_by_date[d]
        ]:
            _flush_date(jc, ready, pending.pop(ready), cleanup_queue)

    if jc.cancel_event.is_set():
        if pending:
            logger.info(
                "[ORCH] job_id=%d dibatalkan: %d tanggal tidak difinalisasi",
                jc.job_id, len(pending),
            )
    else:
        for date_key in sorted(pending):
            members = pending[date_key]
            expected = jc.expected_pids_by_date.get(date_key)
            got = {m.pid for m in members}
            if expected and got < expected:
                logger.warning(
                    "[ORCH] job_id=%d tanggal=%s: %d/%d frame di antrean run "
                    "ini (hilang dari run ini: %s) -- mencoba rekonsiliasi "
                    "dari disk sebelum finalize",
                    jc.job_id, date_key, len(got), len(expected),
                    sorted(expected - got),
                )
            _flush_date(jc, date_key, members, cleanup_queue)
    cleanup_queue.put(None)


def _cleanup_worker(jc: _JobContext, cleanup_queue: Queue) -> None:
    if jc.log_path:
        adopt_dataset_log_scope(jc.log_path)
    while True:
        item = cleanup_queue.get()
        if item is None:
            break
        pid, scene_id, produced_tiers, produced_files = item
        try:
            _cleanup_scene_tiers(jc, pid, scene_id, produced_tiers, produced_files)
            jc.dsmgr.upsert_scene_job_state(
                jc.job_id, pid, current_stage="CLEANUP", stage_status="COMPLETED", completed_at=_now()
            )
            jc.dsmgr.increment_job_counters(jc.job_id, cleaned=1)
        except Exception as exc:
            logger.exception("[ORCH] cleanup gagal pid=%s job_id=%d", pid, jc.job_id)
            _record_worker_failure(jc, pid, "CLEANUP", exc)


def _keep_live_target_dates(db, job_id: int, dataset_id: int, scenes: list[dict]) -> list[dict]:
    """Job LIVE_INGEST hanya untuk tanggal yang dipilih siklus Live (baris
    live_scenes PROCESSING), bukan setiap scene di rentang [awal, akhir].
    """
    with db.session() as sess:
        job = sess.get(DatasetJob, job_id)
        if job is None or job.job_type != LIVE_JOB_TYPE:
            return scenes
        wanted = {r.scene_date for r in sess.query(LiveScene.scene_date).filter(
            LiveScene.dataset_id == dataset_id, LiveScene.status == "PROCESSING")}
        ds = sess.get(Dataset, dataset_id)
        root = fm.get_dataset_root(dataset_id, ds.name) if ds else None
    kept = [s for s in scenes if _scene_date(s) in wanted] if wanted else list(scenes)
    if len(kept) != len(scenes):
        logger.info("[ORCH] job_id=%d Live: %d -> %d scene (hanya tanggal target %s)",
                    job_id, len(scenes), len(kept), sorted(d.isoformat() for d in wanted))
    done_dir = root / fm.SOURCE_DIR_NAMES["sentinel1"] / "PROCESSED" if root else None
    if done_dir is not None and done_dir.is_dir():
        names = {p.name for p in done_dir.glob("*_lee.tif")}

        def has_cogs(pid: str) -> bool:
            stem = pid[:35]   # S1X_IW_GRDH_1SDV_YYYYMMDDTHHMMSS_20 = prefix nama COG
            return all(any(n.startswith(stem) and n.endswith(f"_{b}_lee.tif") for n in names)
                       for b in ("VV", "VH"))
        before = len(kept)
        kept = [s for s in kept if not has_cogs(s["product_identifier"])]
        if len(kept) != before:
            logger.info("[ORCH] job_id=%d Live: %d frame sudah punya COG, tidak diunduh ulang",
                        job_id, before - len(kept))
    return kept


def _drop_dates_barely_covering_aoi(
    scenes: list[dict], bbox_wkt: str, job_id: int,
    min_fraction: float = MIN_S1_AOI_COVERAGE,
) -> list[dict]:
    """Buang tanggal S1 yang gabungan footprint-nya menutup kurang dari `min_fraction` AOI."""
    by_date: dict[date | None, list[dict]] = {}
    for scene in scenes:
        by_date.setdefault(_scene_date(scene), []).append(scene)

    kept: list[dict] = []
    for day, members in by_date.items():
        footprints = [m.get("footprint_wkt") for m in members]
        coverage = (
            aoi_coverage([fp for fp in footprints if fp], bbox_wkt)
            if day is not None and all(footprints) else None
        )
        if coverage is not None and coverage < min_fraction:
            logger.warning(
                "[ORCH] job_id=%d tanggal %s dilewati: %d frame S1 cuma menutup "
                "%.1f%% AOI (< %.0f%%): %s",
                job_id, day, len(members), coverage * 100, min_fraction * 100,
                [m["product_identifier"] for m in members],
            )
            continue
        kept.extend(members)
    return kept


def _scene_date(scene_meta: dict) -> date | None:
    """Tanggal akuisisi satu scene S1 hasil discover_scenes, atau None."""
    acq = scene_meta.get("acquisition_datetime")
    if acq is not None and hasattr(acq, "date"):
        return acq.date()

    m = re.search(r"(\d{8})", str(scene_meta.get("product_identifier") or ""))
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d").date()
        except ValueError:
            pass
    logger.warning(
        "[ORCH] scene tanpa tanggal yang bisa dibaca: %r",
        scene_meta.get("product_identifier"),
    )
    return None


def _ingest_aux_days(
    jc: _JobContext, days: list[date], count_as_scenes: bool = True
) -> tuple[int, int]:
    """Unduh + proses MODIS/GPM untuk sekumpulan tanggal. Returns (ok, gagal)."""
    ok_days = 0
    failed_days = 0

    def _count(**kwargs) -> None:
        if count_as_scenes:
            jc.dsmgr.increment_job_counters(jc.job_id, **kwargs)

    already_done = jc.plog.completed_aux_dates(
        jc.dataset_id, [d.strftime("%Y%m%d") for d in days]
    )
    if already_done:
        logger.info(
            "[ORCH] job_id=%d %d/%d tanggal aux sudah selesai di run sebelumnya, dilewati",
            jc.job_id, len(already_done), len(days),
        )

    for day in days:
        jc.pause_event.wait()
        if jc.cancel_event.is_set():
            break
        date_key = day.strftime("%Y%m%d")
        if date_key in already_done:
            ok_days += 1
            _count(processed=1)
            continue
        try:
            produced, missing_sources = ensure_aux_inputs_for_date(
                jc.db, jc.dataset_id, jc.dataset_name, jc.region_id,
                jc.bbox_tuple, day, plog=jc.plog, plan=jc.plan,
            )
            written = sum(len(paths) for paths in produced.values())
            aux_complete = bool(written) and not missing_sources
            if written:
                ok_days += 1
                _count(processed=1)
            else:
                failed_days += 1
                _count(failed=1)
            jc.plog.log_event(
                jc.dataset_id, date_key, "ORCHESTRATOR", "SCENE_PIPELINE",
                "COMPLETED" if written else "FAILED",
                f"Aux {date_key}: {written} file(s) written",
                {"date": day.isoformat(), "files_written": written,
                 "aux_complete": aux_complete,
                 "missing_sources": sorted(missing_sources),
                 "tiers": {tier: len(paths) for tier, paths in produced.items()}},
            )
        except Exception as exc:
            failed_days += 1
            logger.exception("[ORCH] aux gagal tanggal=%s job_id=%d", day, jc.job_id)
            _record_worker_failure(jc, date_key, "SCENE_PIPELINE", exc)
            jc.meta.fail_open_jobs(exc)
            _count(failed=1)
    return ok_days, failed_days


def _run_aux_only(jc: _JobContext, date_from: date, date_to: date) -> None:
    """Jalankan dataset yang TIDAK mengkonfigurasi Sentinel-1."""
    total_days = (date_to - date_from).days + 1
    jc.dsmgr.set_job_status(jc.job_id, "DOWNLOADING")
    logger.info(
        "[ORCH] job_id=%d mode aux-only (tanpa Sentinel-1) sumber=%s hari=%d",
        jc.job_id, list(jc.plan.aux_sources()), total_days,
    )

    days = [date_from + timedelta(days=i) for i in range(total_days)]
    with dataset_log_file(jc.dataset_id, jc.dataset_name) as run_log_path:
        jc.log_path = run_log_path
        ok_days, failed_days = _ingest_aux_days(jc, days)

    total_size = _dir_size_bytes(jc.base_dir)
    jc.dsmgr.set_dataset_size(jc.dataset_id, total_size)

    if jc.cancel_event.is_set():
        jc.dsmgr.set_job_status(jc.job_id, "CANCELLED", completed_at=_now())
        _write_dataset_metadata(jc.dsmgr, jc.dataset_id, total_size)
        logger.info("[ORCH] job_id=%d dibatalkan", jc.job_id)
        return

    final_status = "FAILED" if ok_days == 0 else "COMPLETED"
    jc.dsmgr.set_job_status(jc.job_id, final_status, completed_at=_now())
    _write_dataset_metadata(jc.dsmgr, jc.dataset_id, total_size)
    logger.info(
        "[ORCH] job_id=%d aux-only selesai status=%s hari_ok=%d hari_gagal=%d",
        jc.job_id, final_status, ok_days, failed_days,
    )


def run_dataset_job(db: DatabaseClient, job_id: int) -> None:
    with db.session() as sess:
        job = sess.get(DatasetJob, job_id)
        live = job is not None and job.job_type == LIVE_JOB_TYPE
        ds_id = job.dataset_id if job is not None else None
    low = live and dg.is_low_priority()
    prev_ctx = dg.current_context()
    dg.set_context(ds_id)
    try:
        with dg.low_priority(low):
            _run_dataset_job(db, job_id)
    finally:
        dg.set_context(prev_ctx)


def _run_dataset_job(db: DatabaseClient, job_id: int) -> None:
    with db.session() as sess:
        job = sess.get(DatasetJob, job_id)
        if job is None:
            logger.error("[ORCH] job_id=%d tidak ditemukan", job_id)
            return
        dataset_id = job.dataset_id
        date_range_start = job.date_range_start
        date_range_end = job.date_range_end

    dsmgr = DatasetManager(db)
    meta = MetadataManager(db)
    lineage = LineageTracker(db)
    plog = PipelineLogger(db)

    dataset = dsmgr.get_dataset(dataset_id)
    if dataset is None:
        logger.error("[ORCH] dataset_id=%d tidak ditemukan", dataset_id)
        dsmgr.set_job_status(job_id, "FAILED", completed_at=_now())
        return

    dataset_name = dataset["name"]
    required_tiers = dataset["required_tiers"]
    region_id = dataset["region_id"]
    bbox_wkt = dataset["bbox_wkt"]
    quality_settings = dataset["quality_settings"] or {}
    min_cloud_cover = quality_settings.get("min_cloud_cover")
    orbit_direction = quality_settings.get("orbit_direction")
    fusion_strategy = dataset.get("fusion_strategy")

    plan = load_processing_plan(db, dataset_id)
    if not plan.sources:
        logger.error(
            "[ORCH] job_id=%d dataset_id=%d tidak punya sumber terkonfigurasi",
            job_id, dataset_id,
        )
        dsmgr.set_job_status(job_id, "FAILED", completed_at=_now())
        _write_dataset_metadata(dsmgr, dataset_id)
        return

    skip_stages = compute_skip_stages(required_tiers)
    s1_plan = plan.get(S1_SOURCE_NAME)
    if s1_plan is not None:
        skip_stages |= s1_plan.s1_skip_stages()
    logger.info(
        "[ORCH] job_id=%d rencana sumber=%s strategi_fusi=%r skip=%s",
        job_id, plan.summary(), fusion_strategy, sorted(skip_stages),
    )

    if not dataset.get("generate_preview", True):
        skip_stages.add("PREVIEW")
        logger.info(
            "[ORCH] job_id=%d PREVIEW dilewati: dimatikan di konfigurasi dataset "
            "(generate_preview=false)", job_id,
        )
    elif dataset.get("preview_options") == []:
        skip_stages.add("PREVIEW")
        logger.info(
            "[ORCH] job_id=%d PREVIEW dilewati: preview_options kosong", job_id,
        )

    bbox_tuple = _bbox_tuple_from_wkt(bbox_wkt)
    base_dir = fm.get_dataset_root(dataset_id, dataset_name)
    base_dir.mkdir(parents=True, exist_ok=True)

    pause_event = get_pause_event(job_id)
    cancel_event = get_cancel_event(job_id)

    jc = _JobContext(
        db=db, dsmgr=dsmgr, meta=meta, lineage=lineage, plog=plog,
        job_id=job_id, dataset_id=dataset_id, dataset_name=dataset_name, region_id=region_id,
        bbox_wkt=bbox_wkt, bbox_tuple=bbox_tuple,
        required_tiers=required_tiers, skip_stages=skip_stages,
        base_dir=base_dir, pause_event=pause_event, cancel_event=cancel_event,
        plan=plan, fusion_strategy=fusion_strategy,
        fusion_plan=None,
        preview_options=dataset.get("preview_options"),
        low_priority=dg.is_low_priority(),
    )

    dsmgr.set_job_status(job_id, "PREPARING", started_at=_now())
    dsmgr.begin_job_run(job_id)

    date_from = (
        datetime.combine(date_range_start, datetime.min.time(), tzinfo=timezone.utc)
        if date_range_start else _now() - timedelta(days=30)
    )
    date_to = (
        datetime.combine(date_range_end, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
        if date_range_end else _now()
    )

    if s1_plan is None:
        _run_aux_only(jc, date_from.date(), (date_to - timedelta(days=1)).date())
        return

    try:
        scenes = discover_scenes(bbox_wkt=bbox_wkt, date_from=date_from, date_to=date_to, max_results=200)
    except Exception:
        logger.exception("[ORCH] discovery gagal job_id=%d", job_id)
        dsmgr.set_job_status(job_id, "FAILED", completed_at=_now())
        _write_dataset_metadata(dsmgr, dataset_id)
        return

    if not scenes:
        logger.info("[ORCH] tidak ada scene ditemukan job_id=%d", job_id)
        dsmgr.set_job_status(job_id, "COMPLETED", completed_at=_now())
        _write_dataset_metadata(dsmgr, dataset_id)
        return

    if min_cloud_cover is not None:
        before = len(scenes)
        scenes = [s for s in scenes if (s.get("cloud_cover") or 0) <= min_cloud_cover]
        logger.info("[ORCH] filter cloud_cover<=%.1f job_id=%d: %d -> %d scene",
                    min_cloud_cover, job_id, before, len(scenes))
        if not scenes:
            logger.info("[ORCH] semua scene tersaring cloud_cover job_id=%d", job_id)
            dsmgr.set_job_status(job_id, "COMPLETED", completed_at=_now())
            _write_dataset_metadata(dsmgr, dataset_id)
            return

    if orbit_direction:
        before = len(scenes)
        scenes = [s for s in scenes if (s.get("orbit_direction") or "").upper() == orbit_direction.upper()]
        logger.info("[ORCH] filter orbit_direction=%s job_id=%d: %d -> %d scene",
                    orbit_direction, job_id, before, len(scenes))
        if not scenes:
            dsmgr.set_job_status(job_id, "COMPLETED", completed_at=_now())
            _write_dataset_metadata(dsmgr, dataset_id)
            return

    scenes = _drop_dates_barely_covering_aoi(scenes, bbox_wkt, job_id)
    scenes = _keep_live_target_dates(db, job_id, dataset_id, scenes)
    if not scenes:
        logger.info("[ORCH] semua tanggal S1 cuma menyerempet AOI job_id=%d", job_id)
        dsmgr.set_job_status(job_id, "COMPLETED", completed_at=_now())
        _write_dataset_metadata(dsmgr, dataset_id)
        return

    dsmgr.create_scene_job_states(job_id, [s["product_identifier"] for s in scenes])
    dsmgr.set_job_status(job_id, "DOWNLOADING")

    s1_dates = {d for d in (_scene_date(s) for s in scenes) if d is not None}
    for scene_meta in scenes:
        scene_day = _scene_date(scene_meta)
        if scene_day is None:
            continue
        jc.expected_pids_by_date.setdefault(
            scene_day.strftime("%Y%m%d"), set()
        ).add(scene_meta["product_identifier"])
    if "FUSION" not in skip_stages and jc.plan.fusion_eligible(jc.fusion_strategy):
        jc.fusion_plan = plan_fusion(
            jc.fusion_strategy, s1_dates,
            date_from.date(), (date_to - timedelta(days=1)).date(),
            tolerance_days=dataset.get("s1_match_tolerance_days")
            or DEFAULT_S1_MATCH_TOLERANCE_DAYS,
        )

    if jc.fusion_plan is not None:
        extra_days = [d for d in jc.fusion_plan.aux_dates if d not in s1_dates]
        if extra_days:
            logger.info(
                "[ORCH] job_id=%d strategi=%s: %d tanggal aux tambahan di luar "
                "%d tanggal scene S1",
                job_id, jc.fusion_plan.strategy, len(extra_days), len(s1_dates),
            )
            with dataset_log_file(dataset_id, dataset["name"]) as aux_log_path:
                jc.log_path = aux_log_path
                _ingest_aux_days(jc, extra_days, count_as_scenes=False)

    download_queue: Queue = Queue(maxsize=3)
    cleanup_queue: Queue = Queue()

    with dataset_log_file(dataset_id, dataset["name"]) as run_log_path:
        jc.log_path = run_log_path
        logger.info(
            "[ORCH] job_id=%d start dataset=%r scenes=%d tiers=%s log=%s",
            job_id, dataset["name"], len(scenes), jc.required_tiers, run_log_path,
        )
        t_download = threading.Thread(target=_download_worker, args=(jc, scenes, download_queue), daemon=False)
        t_pipeline = threading.Thread(target=_pipeline_worker, args=(jc, download_queue, cleanup_queue), daemon=False)
        t_cleanup = threading.Thread(target=_cleanup_worker, args=(jc, cleanup_queue), daemon=False)

        t_download.start()
        t_pipeline.start()
        t_cleanup.start()
        t_download.join()
        t_pipeline.join()
        t_cleanup.join()

        extra_fused = _fuse_days_without_s1(jc, s1_dates, scenes)

        _sweep_scratch(jc)

        if dataset.get("fusion_output_only"):
            _apply_fusion_output_only(
                jc,
                fusion_written=bool(
                    extra_fused
                    or list(jc.base_dir.glob("**/fusion/**/*.h5"))
                ),
            )

    total_size = _dir_size_bytes(base_dir)
    dsmgr.set_dataset_size(dataset_id, total_size)

    if cancel_event.is_set():
        dsmgr.set_job_status(job_id, "CANCELLED", completed_at=_now())
        _write_dataset_metadata(dsmgr, dataset_id, total_size)
        logger.info("[ORCH] job_id=%d dibatalkan", job_id)
        return

    with db.session() as sess:
        job = sess.get(DatasetJob, job_id)
        still_paused = job.status == "PAUSED" if job else False
        failed_count = job.failed_count if job else 0

    if still_paused:
        _write_dataset_metadata(dsmgr, dataset_id, total_size)
        logger.info("[ORCH] job_id=%d berhenti dalam status PAUSED", job_id)
        return

    final_status = "FAILED" if failed_count > 0 else "COMPLETED"
    dsmgr.set_job_status(job_id, final_status, completed_at=_now())
    _write_dataset_metadata(dsmgr, dataset_id, total_size)
    logger.info("[ORCH] job_id=%d selesai status=%s failed_count=%d", job_id, final_status, failed_count)
