from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from enum import Enum as PyEnum
from collections.abc import Generator
from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    func,
    null,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker
from sqlalchemy.pool import QueuePool

from etl import tier_names as tn

logger = logging.getLogger(__name__)


class OrbitDirectionEnum(str, PyEnum):
    ASCENDING = "ASCENDING"
    DESCENDING = "DESCENDING"


class JobStatusEnum(str, PyEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    WAITING_UPSTREAM = "WAITING_UPSTREAM"
    SKIPPED_LOCKED = "SKIPPED_LOCKED"


class ProductTierEnum(str, PyEnum):
    """Nilai `data_products.product_tier` (kosakata D14)."""
    RAW = "RAW"
    ALIGNED = "ALIGNED"
    DESPECKLED = "DESPECKLED"
    INDICES = "INDICES"
    ACCUMULATED = "ACCUMULATED"
    COG = "COG"
    FUSED = "FUSED"


class ProductSourceEnum(str, PyEnum):
    """Sensor asal sebuah data_product. Dicerminkan oleh level {source}
    di path on-disk (etl/folder_manager.py) — kecuali FUSION, yang lintas
    source dan tinggal di tier fusion/ tanpa folder source sendiri.
    Disimpan sebagai VARCHAR + CHECK constraint, bukan ENUM Postgres:
    menambah source baru nanti cukup ALTER CONSTRAINT, tidak perlu
    ALTER TYPE yang tidak bisa jalan di dalam transaksi."""
    SENTINEL1 = "SENTINEL1"
    MODIS = "MODIS"
    GPM = "GPM"
    FUSION = "FUSION"


class StorageLocationEnum(str, PyEnum):
    LOCAL = "LOCAL"
    S3 = "S3"
    GCS = "GCS"
    AZURE_BLOB = "AZURE_BLOB"


class AlertSeverityEnum(str, PyEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertEventTypeEnum(str, PyEnum):
    DATA_ARRIVAL = "DATA_ARRIVAL"
    QUALITY_WARNING = "QUALITY_WARNING"
    PIPELINE_ERROR = "PIPELINE_ERROR"
    THRESHOLD_BREACH = "THRESHOLD_BREACH"
    SYSTEM_ALERT = "SYSTEM_ALERT"


class ProcessingLevelEnum(str, PyEnum):
    """Level pemrosesan yang diminta user untuk SATU sumber."""
    RAW = "RAW"
    PROCESSED = "PROCESSED"


class FusionStrategyEnum(str, PyEnum):
    CO_OCCURRENCE = "CO_OCCURRENCE"
    FULL_COVERAGE = "FULL_COVERAGE"
    HYBRID = "HYBRID"


class PreviewOptionEnum(str, PyEnum):
    GRAYSCALE = "GRAYSCALE"
    COLORED = "COLORED"
    COMPOSITE = "COMPOSITE"


class DatasetSourceNameEnum(str, PyEnum):
    """Sumber yang bisa dikonfigurasi per dataset."""
    SENTINEL1 = "SENTINEL1"
    MODIS = "MODIS"
    GPM = "GPM"


SOURCE_NAME_ORDER: tuple[str, ...] = (
    DatasetSourceNameEnum.SENTINEL1.value,
    DatasetSourceNameEnum.MODIS.value,
    DatasetSourceNameEnum.GPM.value,
)

API_KEY_TO_SOURCE_NAME: dict[str, str] = {name.lower(): name for name in SOURCE_NAME_ORDER}
SOURCE_NAME_TO_API_KEY: dict[str, str] = {name: name.lower() for name in SOURCE_NAME_ORDER}


def normalize_source_configs(sources: dict) -> dict[str, list[str]]:
    """Ubah objek `sources` gaya API menjadi {SOURCE_NAME: [levels]}."""
    if not isinstance(sources, dict) or not sources:
        raise ValueError("sources must contain at least 1 source")

    valid_levels = {level.value for level in ProcessingLevelEnum}
    normalized: dict[str, list[str]] = {}

    for raw_key, raw_value in sources.items():
        key = str(raw_key).strip()
        source_name = API_KEY_TO_SOURCE_NAME.get(key.lower())
        if source_name is None:
            raise ValueError(
                f"unknown source: {raw_key!r} "
                f"(options: {', '.join(sorted(API_KEY_TO_SOURCE_NAME))})"
            )
        if source_name in normalized:
            raise ValueError(f"duplicate source in payload: {source_name}")

        if isinstance(raw_value, dict):
            levels = raw_value.get("processing")
        else:
            levels = raw_value
        if isinstance(levels, str):
            levels = [levels]
        if not levels:
            raise ValueError(
                f"sources.{SOURCE_NAME_TO_API_KEY[source_name]}.processing "
                "must contain at least one value"
            )

        seen: list[str] = []
        for raw_level in levels:
            level = str(raw_level).strip().upper()
            if level not in valid_levels:
                raise ValueError(
                    f"unknown processing level for "
                    f"{SOURCE_NAME_TO_API_KEY[source_name]}: {raw_level!r} "
                    f"(options: {', '.join(sorted(valid_levels))})"
                )
            if level not in seen:      # duplikat dibuang, bukan ditolak
                seen.append(level)
        normalized[source_name] = [
            lv.value for lv in ProcessingLevelEnum if lv.value in seen
        ]

    return dict(sorted(
        normalized.items(),
        key=lambda item: SOURCE_NAME_ORDER.index(item[0])
        if item[0] in SOURCE_NAME_ORDER else len(SOURCE_NAME_ORDER),
    ))


def source_configs_to_api(configs: list[DatasetSourceConfig]) -> dict[str, dict]:
    """Bentuk objek `sources` gaya API dari baris dataset_source_config."""
    ordered = sorted(
        configs,
        key=lambda c: SOURCE_NAME_ORDER.index(c.source_name)
        if c.source_name in SOURCE_NAME_ORDER else len(SOURCE_NAME_ORDER),
    )
    return {
        SOURCE_NAME_TO_API_KEY.get(c.source_name, c.source_name.lower()):
            {"processing": list(c.processing_levels or [])}
        for c in ordered
    }


def _tiers_for(level: str, source: str) -> tuple[str, ...]:
    """Tier yang dihasilkan satu source pada satu level."""
    if level == ProcessingLevelEnum.RAW.value:
        return (tn.RAW, tn.ALIGNED)
    if level == ProcessingLevelEnum.PROCESSED.value:
        return (tn.RAW, tn.ALIGNED, tn.RANK2_BY_SOURCE[source.upper()], tn.COG)
    return ()


def derive_required_tiers(
    configs: dict[str, list[str]], with_fusion: bool = False
) -> list[str]:
    """Turunkan `datasets.required_tiers` dari konfigurasi per-sumber."""
    tiers: set[str] = set()
    for source, levels in configs.items():
        for level in levels:
            tiers.update(_tiers_for(level, source))
    if with_fusion and tn.COG in tiers:
        tiers.add(tn.FUSED)
    return sorted(tiers, key=tn.sort_key)


def _validate_s1_tolerance(value) -> int | None:
    """Validasi `datasets.s1_match_tolerance_days`. None = pakai default kolom."""
    if value is None:
        return None
    try:
        days = int(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"s1_match_tolerance_days must be a whole number, not {value!r}"
        ) from None
    if not 0 <= days <= 14:
        raise ValueError(
            f"s1_match_tolerance_days out of range: {days} (0-14)"
        )
    return days


def _validate_fusion_output_only(value, fusion_strategy: str | None) -> bool:
    """`fusion_output_only` hanya masuk akal kalau ada fusi."""
    enabled = bool(value)
    if enabled and fusion_strategy is None:
        raise ValueError(
            "fusion_output_only needs fusion_strategy: without fusion, deleting "
            "the per-satellite artefacts would leave no output at all"
        )
    return enabled


def _validate_fusion_strategy(value, source_count: int) -> str | None:
    """Validasi fusion_strategy terhadap jumlah sumber yang dikonfigurasi."""
    strategy = None if value is None else str(value).strip().upper()
    if strategy == "":
        strategy = None

    if source_count > 1:
        if strategy is None:
            raise ValueError("fusion_strategy required when multiple sources configured")
    elif strategy is not None:
        raise ValueError("fusion_strategy must be null when only 1 source configured")

    valid = {s.value for s in FusionStrategyEnum}
    if strategy is not None and strategy not in valid:
        raise ValueError(
            f"unknown fusion_strategy: {value!r} (options: {', '.join(sorted(valid))})"
        )
    return strategy


def _validate_preview_options(value) -> list[str]:
    """Normalkan preview_options. None -> semua varian, [] -> tidak ada."""
    if value is None:
        return [opt.value for opt in PreviewOptionEnum]
    if isinstance(value, str):
        value = [value]

    valid = {opt.value for opt in PreviewOptionEnum}
    seen: list[str] = []
    for raw in value:
        option = str(raw).strip().upper()
        if option not in valid:
            raise ValueError(
                f"unknown preview option: {raw!r} (options: {', '.join(sorted(valid))})"
            )
        if option not in seen:
            seen.append(option)
    return [opt.value for opt in PreviewOptionEnum if opt.value in seen]


class Base(DeclarativeBase):
    pass


class RegionOfInterest(Base):
    __tablename__ = "regions_of_interest"
    region_id = Column(Integer, primary_key=True, autoincrement=True)
    region_code = Column(String(20), nullable=False, unique=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    bbox = Column(Geometry("POLYGON", srid=4326), nullable=False)
    centroid = Column(Geometry("POINT", srid=4326))
    area_km2 = Column(Numeric(12, 4))
    admin_level = Column(SmallInteger, nullable=False, default=2)
    country_code = Column(String(2), nullable=False, default="ID")
    is_active = Column(Boolean, nullable=False, default=True)
    source = Column(String(20), nullable=False, default="SYSTEM", server_default=text("'SYSTEM'"))
    admin_region_id = Column(Integer)
    is_monitor_aoi = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    deleted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    scenes = relationship("SatelliteScene", back_populates="region")
    datasets = relationship("Dataset", back_populates="region")

    def __repr__(self) -> str:
        return f"<RegionOfInterest id={self.region_id} code={self.region_code}>"


class ProcessingStage(Base):
    __tablename__ = "processing_stages"
    __table_args__ = (
        UniqueConstraint("stage_order", name="uq_stage_order"),
    )
    stage_id = Column(Integer, primary_key=True, autoincrement=True)
    stage_name = Column(String(50), nullable=False, unique=True)
    stage_code = Column(String(20), nullable=False, unique=True)
    stage_order = Column(SmallInteger, nullable=False)
    description = Column(Text)
    source_code = Column(String(20))  # FK satellite_sources di DB
    timeout_minutes = Column(SmallInteger, nullable=False, default=60)
    retry_count = Column(SmallInteger, nullable=False, default=3)
    retry_delay_sec = Column(SmallInteger, nullable=False, default=30)
    is_mandatory = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    jobs = relationship("ProcessingJob", back_populates="stage")

    def __repr__(self) -> str:
        return f"<ProcessingStage id={self.stage_id} name={self.stage_name}>"


class SatelliteScene(Base):
    __tablename__ = "satellite_scenes"
    scene_id = Column(Integer, primary_key=True, autoincrement=True)
    scene_uuid = Column(UUID(as_uuid=True), nullable=False, unique=True,
                         server_default=text("gen_random_uuid()"))
    product_identifier = Column(String(200), nullable=False, unique=True)
    platform = Column(String(20), nullable=False, default="SENTINEL-1")
    instrument_mode = Column(String(10), nullable=False, default="IW")
    polarization_vv = Column(Boolean, nullable=False, default=True)
    polarization_vh = Column(Boolean, nullable=False, default=True)
    acquisition_datetime = Column(DateTime(timezone=True), nullable=False, index=True)
    orbit_number = Column(Integer)
    orbit_direction = Column(
        Enum(OrbitDirectionEnum, name="orbit_direction_enum"),
        nullable=False, default=OrbitDirectionEnum.ASCENDING
    )
    relative_orbit = Column(SmallInteger)
    bbox = Column(Geometry("POLYGON", srid=4326), nullable=False)
    cloud_cover_percent = Column(Numeric(5, 2))
    incidence_angle_near = Column(Numeric(6, 3))
    incidence_angle_far = Column(Numeric(6, 3))
    resolution_m = Column(SmallInteger, nullable=False, default=10)
    region_id = Column(Integer, ForeignKey("regions_of_interest.region_id",
                                            ondelete="RESTRICT"), nullable=False)
    raw_file_path = Column(Text)
    raw_file_size_mb = Column(Numeric(12, 3))
    download_url = Column(Text)
    checksum_md5 = Column(String(32))
    is_available = Column(Boolean, nullable=False, default=True)
    is_valid = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    invalidated_by = Column(Integer)  # FK users di DB
    invalidated_at = Column(DateTime(timezone=True))
    invalid_reason = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    region = relationship("RegionOfInterest", back_populates="scenes")
    jobs = relationship("ProcessingJob", back_populates="scene", cascade="all, delete-orphan")
    products = relationship("DataProduct", back_populates="scene", cascade="all, delete-orphan")
    quality_metrics = relationship("QualityMetric", back_populates="scene", cascade="all, delete-orphan")
    quality_alerts = relationship("QualityAlert", back_populates="scene")
    scene_job_states = relationship("SceneJobState", back_populates="scene")

    def __repr__(self) -> str:
        return f"<SatelliteScene id={self.scene_id} pid={self.product_identifier}>"


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        UniqueConstraint("scene_id", "stage_id", "attempt_number",
                          name="uq_job_scene_stage_attempt"),
    )
    job_id = Column(BigInteger, primary_key=True, autoincrement=True)
    job_uuid = Column(UUID(as_uuid=True), nullable=False, unique=True,
                       server_default=text("gen_random_uuid()"))
    scene_id = Column(Integer, ForeignKey("satellite_scenes.scene_id",
                                           ondelete="CASCADE"))
    nasa_scene_id = Column(BigInteger, ForeignKey("nasa_scenes.nasa_scene_id",
                                                  ondelete="CASCADE"))
    stage_id = Column(Integer, ForeignKey("processing_stages.stage_id",
                                           ondelete="RESTRICT"), nullable=False)
    attempt_number = Column(SmallInteger, nullable=False, default=1)
    status = Column(
        Enum(JobStatusEnum, name="job_status_enum"),
        nullable=False, default=JobStatusEnum.QUEUED
    )
    queued_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    worker_hostname = Column(String(100))
    cpu_usage_percent = Column(Numeric(7, 2))
    memory_usage_mb = Column(Numeric(10, 2))
    input_size_mb = Column(Numeric(12, 3))
    output_size_mb = Column(Numeric(12, 3))
    error_code = Column(String(50))
    error_message = Column(Text)
    log_file_path = Column(Text)
    parameters_json = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    scene = relationship("SatelliteScene", back_populates="jobs")
    stage = relationship("ProcessingStage", back_populates="jobs")
    products = relationship("DataProduct", back_populates="job")
    lineages = relationship("DataLineage", back_populates="job",
                             foreign_keys="DataLineage.job_id",
                             passive_deletes=True)

    def __repr__(self) -> str:
        return f"<ProcessingJob id={self.job_id} scene={self.scene_id} stage={self.stage_id} status={self.status}>"


class DataProduct(Base):
    __tablename__ = "data_products"
    __table_args__ = (
        CheckConstraint(
            "processing_level IS NULL OR processing_level IN ('RAW', 'PROCESSED')",
            name="chk_dprods_processing_level",
        ),
        Index("idx_dprods_dataset_level", "dataset_id", "processing_level"),
    )
    product_id = Column(BigInteger, primary_key=True, autoincrement=True)
    product_uuid = Column(UUID(as_uuid=True), nullable=False, unique=True,
                           server_default=text("gen_random_uuid()"))
    scene_id = Column(Integer, ForeignKey("satellite_scenes.scene_id",
                                           ondelete="CASCADE"))
    nasa_scene_id = Column(BigInteger, ForeignKey("nasa_scenes.nasa_scene_id",
                                                  ondelete="CASCADE"))
    job_id = Column(BigInteger, ForeignKey("processing_jobs.job_id",
                                            ondelete="RESTRICT"), nullable=False)
    dataset_id = Column(Integer, ForeignKey("datasets.dataset_id", ondelete="CASCADE"))
    product_tier = Column(
        Enum(ProductTierEnum, name="product_tier_enum"),
        nullable=False
    )
    source = Column(String(20), nullable=False, default=ProductSourceEnum.SENTINEL1.value)
    processing_level = Column(
        String(20), nullable=True,
        server_default=text("'PROCESSED'"),
        default=ProcessingLevelEnum.PROCESSED.value,
    )
    product_type = Column(String(50), nullable=False)
    band_name = Column(String(20), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    file_size_mb = Column(Numeric(12, 3), nullable=False)
    file_format = Column(String(20), nullable=False, default="TIFF")
    data_hash_sha256 = Column(String(64), nullable=False)
    crs = Column(String(50), nullable=False, default="EPSG:4326")
    pixel_size_m = Column(Numeric(8, 3))
    nodata_value = Column(Numeric)
    rows = Column(Integer)
    cols = Column(Integer)
    band_count = Column(SmallInteger, nullable=False, default=1)
    storage_location = Column(
        Enum(StorageLocationEnum, name="storage_location_enum"),
        nullable=False, default=StorageLocationEnum.LOCAL
    )
    is_valid = Column(Boolean, nullable=False, default=True)
    is_latest = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    scene = relationship("SatelliteScene", back_populates="products")
    job = relationship("ProcessingJob", back_populates="products")
    dataset = relationship("Dataset", back_populates="products")
    quality_metrics = relationship("QualityMetric", back_populates="product", cascade="all, delete-orphan")
    lineages_as_parent = relationship("DataLineage", back_populates="parent_product",
                                       foreign_keys="DataLineage.parent_product_id",
                                       passive_deletes=True)
    lineages_as_child = relationship("DataLineage", back_populates="child_product",
                                      foreign_keys="DataLineage.child_product_id",
                                      passive_deletes=True)

    def __repr__(self) -> str:
        return f"<DataProduct id={self.product_id} tier={self.product_tier} band={self.band_name}>"


class QualityMetric(Base):
    __tablename__ = "quality_metrics"
    __table_args__ = (
        UniqueConstraint("scene_id", "product_id", "band_name",
                          name="uq_quality_scene_product_band"),
        CheckConstraint("quality_score BETWEEN 0 AND 100", name="chk_quality_score_range"),
    )
    metric_id = Column(BigInteger, primary_key=True, autoincrement=True)
    scene_id = Column(Integer, ForeignKey("satellite_scenes.scene_id",
                                           ondelete="CASCADE"), nullable=False)
    product_id = Column(BigInteger, ForeignKey("data_products.product_id",
                                                ondelete="CASCADE"), nullable=False)
    band_name = Column(String(10), nullable=False)
    assessed_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    total_pixels = Column(BigInteger, nullable=False)
    valid_pixels = Column(BigInteger, nullable=False)
    nodata_pixels = Column(BigInteger, nullable=False, default=0)
    backscatter_mean_db = Column(Numeric(8, 4))
    backscatter_std_db = Column(Numeric(8, 4))
    backscatter_min_db = Column(Numeric(8, 4))
    backscatter_max_db = Column(Numeric(8, 4))
    cloud_threshold_percent = Column(Numeric(5, 2), nullable=False, default=20.0)
    radiometric_consistency = Column(Boolean)
    speckle_index = Column(Numeric(8, 4))
    quality_score = Column(Numeric(5, 2), nullable=False)
    quality_flag = Column(String(20), nullable=False, default="UNCHECKED")
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    scene = relationship("SatelliteScene", back_populates="quality_metrics")
    product = relationship("DataProduct", back_populates="quality_metrics")

    def __repr__(self) -> str:
        return f"<QualityMetric id={self.metric_id} scene={self.scene_id} band={self.band_name} score={self.quality_score}>"


class DataLineage(Base):
    __tablename__ = "data_lineage"
    __table_args__ = (
        UniqueConstraint("parent_product_id", "child_product_id", name="uq_lineage_parent_child"),
        CheckConstraint("parent_product_id <> child_product_id", name="chk_lineage_no_self_ref"),
    )
    lineage_id = Column(BigInteger, primary_key=True, autoincrement=True)
    parent_product_id = Column(BigInteger, ForeignKey("data_products.product_id",
                                                        ondelete="CASCADE"), nullable=False)
    child_product_id = Column(BigInteger, ForeignKey("data_products.product_id",
                                                       ondelete="CASCADE"), nullable=False)
    transformation_type = Column(String(50), nullable=False)
    stage_id = Column(Integer, ForeignKey("processing_stages.stage_id",
                                           ondelete="RESTRICT"), nullable=False)
    job_id = Column(BigInteger, ForeignKey("processing_jobs.job_id",
                                            ondelete="RESTRICT"), nullable=False)
    transformation_params = Column(JSONB, nullable=False, default={})
    input_checksum = Column(String(64))
    output_checksum = Column(String(64))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    parent_product = relationship("DataProduct", back_populates="lineages_as_parent",
                                   foreign_keys=[parent_product_id])
    child_product = relationship("DataProduct", back_populates="lineages_as_child",
                                  foreign_keys=[child_product_id])
    stage = relationship("ProcessingStage")
    job = relationship("ProcessingJob", back_populates="lineages",
                        foreign_keys=[job_id])

    def __repr__(self) -> str:
        return f"<DataLineage id={self.lineage_id} {self.parent_product_id}->{self.child_product_id}>"


class QualityAlert(Base):
    __tablename__ = "quality_alerts"
    alert_id = Column(BigInteger, primary_key=True, autoincrement=True)
    alert_uuid = Column(UUID(as_uuid=True), nullable=False, unique=True,
                         server_default=text("gen_random_uuid()"))
    event_type = Column(Enum(AlertEventTypeEnum, name="alert_event_type_enum"), nullable=False)
    severity = Column(Enum(AlertSeverityEnum, name="alert_severity_enum"),
                       nullable=False, default=AlertSeverityEnum.INFO)
    scene_id = Column(Integer, ForeignKey("satellite_scenes.scene_id",
                                           ondelete="SET NULL"))
    job_id = Column(BigInteger, ForeignKey("processing_jobs.job_id",
                                            ondelete="SET NULL"))
    product_id = Column(BigInteger, ForeignKey("data_products.product_id",
                                                ondelete="SET NULL"))
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    metadata_json = Column(JSONB, default={})
    is_resolved = Column(Boolean, nullable=False, default=False)
    resolved_at = Column(DateTime(timezone=True))
    resolved_by = Column(String(100))
    resolution_note = Column(Text)
    triggered_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    scene = relationship("SatelliteScene", back_populates="quality_alerts")

    def __repr__(self) -> str:
        return f"<QualityAlert id={self.alert_id} type={self.event_type} severity={self.severity}>"


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        CheckConstraint(
            "fusion_strategy IS NULL OR fusion_strategy IN "
            "('CO_OCCURRENCE', 'FULL_COVERAGE', 'HYBRID')",
            name="chk_datasets_fusion_strategy",
        ),
    )
    dataset_id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_uuid = Column(UUID(as_uuid=True), nullable=False, unique=True,
                           server_default=text("gen_random_uuid()"))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    location_label = Column(String(255))
    region_id = Column(Integer, ForeignKey("regions_of_interest.region_id", ondelete="SET NULL"))
    bbox = Column(Geometry("POLYGON", srid=4326), nullable=False)
    bbox_wkt = Column(Text, nullable=False)
    date_start = Column(Date, nullable=False)
    date_end = Column(Date, nullable=False)
    required_tiers = Column(ARRAY(String), nullable=False)
    fusion_strategy = Column(String(20), server_default=text("'FULL_COVERAGE'"))
    preview_options = Column(
        ARRAY(Text),
        server_default=text("ARRAY['GRAYSCALE', 'COLORED', 'COMPOSITE']::TEXT[]"),
    )
    fusion_output_only = Column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    s1_match_tolerance_days = Column(
        SmallInteger, nullable=False, server_default=text("2")
    )
    quality_settings = Column(JSONB, nullable=False, default={})
    fusion_grid = Column(JSONB)
    dataset_kind = Column(String(10), nullable=False, default="STANDARD")
    is_system = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    status = Column(String(20), nullable=False, default="DRAFT")
    total_scenes = Column(Integer, nullable=False, default=0)
    completed_scenes = Column(Integer, nullable=False, default=0)
    failed_scenes = Column(Integer, nullable=False, default=0)
    total_size_bytes = Column(BigInteger, nullable=False, default=0)
    is_deletable = Column(Boolean, nullable=False, default=True)
    generate_preview = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer)  # FK users di DB
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    deleted_at = Column(DateTime(timezone=True))

    region = relationship("RegionOfInterest", back_populates="datasets")
    jobs = relationship("DatasetJob", back_populates="dataset", cascade="all, delete-orphan")
    products = relationship("DataProduct", back_populates="dataset")
    source_configs = relationship(
        "DatasetSourceConfig",
        back_populates="dataset",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DatasetSourceConfig.config_id",
    )

    def __repr__(self) -> str:
        return f"<Dataset id={self.dataset_id} name={self.name} kind={self.dataset_kind} status={self.status}>"


class DatasetSourceConfig(Base):
    """Konfigurasi pemrosesan per-satelit untuk sebuah dataset."""

    __tablename__ = "dataset_source_config"
    __table_args__ = (
        UniqueConstraint("dataset_id", "source_name",
                          name="uq_source_config_dataset_source"),
        CheckConstraint(
            "array_length(processing_levels, 1) IS NOT NULL "
            "AND array_length(processing_levels, 1) > 0",
            name="chk_source_config_levels_not_empty",
        ),
        CheckConstraint(
            "processing_levels <@ ARRAY['RAW', 'PROCESSED']::TEXT[]",
            name="chk_source_config_levels_valid",
        ),
        CheckConstraint(
            "source_name IN ('SENTINEL1', 'MODIS', 'GPM')",
            name="chk_source_config_source_name",
        ),
        Index("idx_source_config_dataset", "dataset_id"),
    )

    config_id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.dataset_id", ondelete="CASCADE"),
                         nullable=False)
    source_name = Column(String(20), nullable=False)
    processing_levels = Column(
        ARRAY(Text), nullable=False,
        server_default=text("ARRAY['PROCESSED']::TEXT[]"),
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    dataset = relationship("Dataset", back_populates="source_configs")

    @property
    def api_key(self) -> str:
        """Nama sumber dalam ejaan API ("sentinel1"), lihat DOCS/INTERFACE.md."""
        return SOURCE_NAME_TO_API_KEY.get(self.source_name, self.source_name.lower())

    def has_level(self, level: str) -> bool:
        """True kalau sumber ini diminta diproses sampai `level`."""
        return str(level).upper() in set(self.processing_levels or [])

    def to_dict(self) -> dict:
        return {
            "config_id": self.config_id,
            "dataset_id": self.dataset_id,
            "source": self.api_key,
            "source_name": self.source_name,
            "processing": list(self.processing_levels or []),
        }

    def __repr__(self) -> str:
        return (f"<DatasetSourceConfig id={self.config_id} dataset={self.dataset_id} "
                f"source={self.source_name} levels={list(self.processing_levels or [])}>")


class DatasetJob(Base):
    __tablename__ = "dataset_jobs"
    job_id = Column(BigInteger, primary_key=True, autoincrement=True)
    job_uuid = Column(UUID(as_uuid=True), nullable=False, unique=True,
                       server_default=text("gen_random_uuid()"))
    dataset_id = Column(Integer, ForeignKey("datasets.dataset_id", ondelete="CASCADE"), nullable=False)
    job_type = Column(String(20), nullable=False, default="CREATE")
    status = Column(String(20), nullable=False, default="QUEUED")
    paused_at = Column(DateTime(timezone=True))
    paused_by = Column(String(20))
    pause_reason = Column(Text)
    resumed_at = Column(DateTime(timezone=True))
    resume_count = Column(SmallInteger, nullable=False, default=0)
    date_range_start = Column(Date)
    date_range_end = Column(Date)
    total_scenes = Column(Integer, nullable=False, default=0)
    downloaded_count = Column(Integer, nullable=False, default=0)
    processed_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    cleaned_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    dataset = relationship("Dataset", back_populates="jobs")
    scene_states = relationship("SceneJobState", back_populates="job", cascade="all, delete-orphan")
    cleanup_operations = relationship("CleanupOperation", back_populates="job")

    def __repr__(self) -> str:
        return f"<DatasetJob id={self.job_id} dataset={self.dataset_id} type={self.job_type} status={self.status}>"


class SceneJobState(Base):
    __tablename__ = "scene_job_state"
    __table_args__ = (
        UniqueConstraint("job_id", "product_identifier", name="uq_job_product"),
    )
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    job_id = Column(BigInteger, ForeignKey("dataset_jobs.job_id", ondelete="CASCADE"), nullable=False)
    product_identifier = Column(String(200), nullable=False)
    scene_id = Column(Integer, ForeignKey("satellite_scenes.scene_id", ondelete="SET NULL"))
    current_stage = Column(String(30))
    stage_status = Column(String(20), nullable=False, default="PENDING")
    produced_files = Column(JSONB, nullable=False, default={})
    attempt_number = Column(SmallInteger, nullable=False, default=1)
    max_retries = Column(SmallInteger, nullable=False, default=3)
    last_error = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    job = relationship("DatasetJob", back_populates="scene_states")
    scene = relationship("SatelliteScene", back_populates="scene_job_states")

    def __repr__(self) -> str:
        return f"<SceneJobState id={self.id} job={self.job_id} pid={self.product_identifier} stage={self.current_stage}>"


class CleanupOperation(Base):
    __tablename__ = "cleanup_operations"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, nullable=False)
    job_id = Column(BigInteger, ForeignKey("dataset_jobs.job_id", ondelete="SET NULL"))
    operation_type = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING")
    total_files = Column(Integer, nullable=False, default=0)
    deleted_count = Column(Integer, nullable=False, default=0)
    freed_bytes = Column(BigInteger, nullable=False, default=0)
    error_log = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    job = relationship("DatasetJob", back_populates="cleanup_operations")

    def __repr__(self) -> str:
        return f"<CleanupOperation id={self.id} dataset={self.dataset_id} type={self.operation_type} status={self.status}>"


class ProcessingLog(Base):
    __tablename__ = "processing_logs"
    log_id = Column(BigInteger, primary_key=True, autoincrement=True)
    log_uuid = Column(UUID(as_uuid=True), nullable=False, unique=True,
                       server_default=text("gen_random_uuid()"))
    dataset_id = Column(Integer, ForeignKey("datasets.dataset_id", ondelete="CASCADE"), nullable=False)
    scene_id = Column(String(255), nullable=False)
    module = Column(String(50), nullable=False)
    stage = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    details = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    def __repr__(self) -> str:
        return (f"<ProcessingLog id={self.log_id} dataset={self.dataset_id} scene={self.scene_id} "
                f"stage={self.stage} status={self.status}>")


class LiveArea(Base):
    """Daerah Live (migrasi 025, PIPELINE.md §4). Datanya diproses lewat
    satu baris `datasets` berjenis LIVE_AREA; baris ini memegang retensi dan
    forecast, dan tetap ada (deleted_at terisi) setelah daerahnya dihapus."""

    __tablename__ = "live_areas"
    __table_args__ = (
        CheckConstraint("retention BETWEEN 1 AND 60", name="chk_live_area_retention"),
    )
    area_id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.dataset_id", ondelete="SET NULL"))
    name = Column(String(255), nullable=False)
    region_id = Column(Integer, ForeignKey("regions_of_interest.region_id", ondelete="SET NULL"))
    location_label = Column(String(255))
    bbox_wkt = Column(Text, nullable=False)
    retention = Column(SmallInteger, nullable=False, default=6)
    enabled = Column(Boolean, nullable=False, default=True)
    status = Column(String(20), nullable=False, default="BACKFILLING")
    status_message = Column(Text)
    last_checked_at = Column(DateTime(timezone=True))
    forecast = Column(JSONB, nullable=False, default={})
    forecast_updated_at = Column(DateTime(timezone=True))
    updated_by = Column(Integer)  # FK users di DB
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    deleted_at = Column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<LiveArea id={self.area_id} name={self.name} retention={self.retention}>"


class LiveScene(Base):
    """Satu scene (tanggal akuisisi S1) sebuah Daerah Live. Baris ini adalah
    log: tidak pernah dihapus, hanya ditandai deleted_at saat file-nya kena
    retensi. Sengaja tanpa FK supaya hidup lebih lama dari dataset/daerahnya."""

    __tablename__ = "live_scenes"
    __table_args__ = (
        UniqueConstraint("area_id", "scene_date", name="uq_live_scene_area_date"),
    )
    live_scene_id = Column(BigInteger, primary_key=True, autoincrement=True)
    area_id = Column(Integer, nullable=False)
    dataset_id = Column(Integer)
    scene_date = Column(Date, nullable=False)
    s1_product_ids = Column(ARRAY(Text), nullable=False, default=list)
    status = Column(String(20), nullable=False, default="PROCESSING")
    source_status = Column(JSONB, nullable=False, default={})
    interpretations = Column(JSONB, nullable=False, default={})
    area_status = Column(JSONB, nullable=False, default={})
    previews = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    deleted_at = Column(DateTime(timezone=True))
    delete_reason = Column(Text)
    deleted_files = Column(JSONB, nullable=False, default=list)
    freed_bytes = Column(BigInteger, nullable=False, default=0)

    def __repr__(self) -> str:
        return f"<LiveScene area={self.area_id} date={self.scene_date} status={self.status}>"


class SpectralBand(Base):
    """Master band (DATABASE.md §3.4). Dipetakan untuk menerjemahkan
    band_code <-> band_id; tabel diisi monitor_seed.sql."""

    __tablename__ = "spectral_bands"
    band_id = Column(SmallInteger, primary_key=True, autoincrement=True)
    source_id = Column(SmallInteger, nullable=False)  # FK satellite_sources di DB
    band_code = Column(String(20), nullable=False, unique=True)
    band_name = Column(String(100), nullable=False)
    unit = Column(String(20))
    valid_min = Column(Numeric)
    valid_max = Column(Numeric)
    aggregation = Column(String(20), nullable=False)

    def __repr__(self) -> str:
        return f"<SpectralBand id={self.band_id} code={self.band_code}>"


class LiveSceneMetric(Base):
    """Satu metrik numerik satu scene Live: band x metrik (M31, 1NF).
    Menggantikan kolom JSONB live_scenes.metrics."""

    __tablename__ = "live_scene_metrics"
    __table_args__ = (
        UniqueConstraint("live_scene_id", "band_id", "metric_name", name="uq_live_scene_metric"),
    )
    metric_id = Column(BigInteger, primary_key=True, autoincrement=True)
    live_scene_id = Column(BigInteger, ForeignKey("live_scenes.live_scene_id", ondelete="CASCADE"),
                           nullable=False)
    band_id = Column(SmallInteger, ForeignKey("spectral_bands.band_id"), nullable=False)
    metric_name = Column(String(30), nullable=False)
    value = Column(Numeric(12, 4))
    source_date = Column(Date)
    ref_live_scene_id = Column(BigInteger, ForeignKey("live_scenes.live_scene_id", ondelete="SET NULL"))

    def __repr__(self) -> str:
        return (f"<LiveSceneMetric scene={self.live_scene_id} band={self.band_id} "
                f"{self.metric_name}={self.value}>")


class LiveEvent(Base):
    """Log langkah siklus Live Monitoring. Disimpan selamanya."""

    __tablename__ = "live_events"
    event_id = Column(BigInteger, primary_key=True, autoincrement=True)
    area_id = Column(Integer, nullable=False)
    scene_date = Column(Date)
    step = Column(String(40), nullable=False)
    status = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    details = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


class NasaScene(Base):
    __tablename__ = "nasa_scenes"
    __table_args__ = (
        UniqueConstraint("source", "tile_id", "product_short_name", "acquisition_date",
                          name="uq_nasa_scene"),
    )
    nasa_scene_id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String(20), nullable=False)
    tile_id = Column(String(10), nullable=False)
    product_short_name = Column(String(50), nullable=False)
    acquisition_date = Column(Date, nullable=False)
    region_id = Column(Integer, ForeignKey("regions_of_interest.region_id", ondelete="RESTRICT"), nullable=False)
    raw_file_path = Column(Text)
    download_url = Column(Text)
    is_available = Column(Boolean, nullable=False, default=True)
    run_type = Column(String(5))
    is_valid = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    invalidated_by = Column(Integer)  # FK users di DB
    invalidated_at = Column(DateTime(timezone=True))
    invalid_reason = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    region = relationship("RegionOfInterest")

    def __repr__(self) -> str:
        return f"<NasaScene id={self.nasa_scene_id} source={self.source} tile={self.tile_id} date={self.acquisition_date}>"


class DatabaseClient:
    def __init__(self, database_url: str, pool_size: int = 5,
                 max_overflow: int = 10, echo: bool = False) -> None:
        self._database_url = database_url
        self._engine = create_engine(
            database_url,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=echo,
        )
        self._SessionFactory = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        self._register_listeners()
        logger.info("DatabaseClient initialized. Pool size: %d + %d overflow", pool_size, max_overflow)

    LOGINS: dict[str, tuple[str, str]] = {
        "app": ("monitor_app", "MONITOR_APP_PASSWORD"),
        "etl": ("monitor_etl", "MONITOR_ETL_PASSWORD"),
    }

    @classmethod
    def from_env(cls, login: str = "owner") -> DatabaseClient:
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        name = os.getenv("DB_NAME", "themonitor")
        if login == "owner":
            user = os.getenv("DB_USER", "postgres")
            password = os.getenv("DB_PASSWORD", "")
        elif login in cls.LOGINS:
            user, password_env = cls.LOGINS[login]
            password = os.getenv(password_env, "")
            if not password:
                raise RuntimeError(f"{password_env} is not set (needed to connect as {user})")
        else:
            raise ValueError(f"unknown login {login!r}")
        pool = int(os.getenv("DB_POOL_SIZE", "5"))
        overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
        echo = os.getenv("DB_ECHO", "false").lower() == "true"
        url = URL.create("postgresql+psycopg2", username=user, password=password,
                         host=host, port=int(port), database=name)
        return cls(url, pool_size=pool, max_overflow=overflow, echo=echo)

    def _register_listeners(self) -> None:
        @event.listens_for(self._engine, "connect")
        def _on_connect(dbapi_conn, _connection_record):
            logger.debug("New DB connection opened")

        @event.listens_for(self._engine, "checkout")
        def _on_checkout(dbapi_conn, _record, _proxy):
            logger.debug("DB connection checked out from pool")

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        sess: Session = self._SessionFactory()
        try:
            yield sess
            sess.commit()
        except SQLAlchemyError as exc:
            sess.rollback()
            logger.error("Session rolled back due to error: %s", exc)
            raise
        finally:
            sess.close()

    def check_health(self) -> dict:
        pool = self._engine.pool
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return {
                "connected": True,
                "pool_size": pool.size(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
            }
        except Exception as exc:
            logger.error("Health check failed: %s", exc)
            return {"connected": False, "error": str(exc)}

    def get_dataset_source_config(
        self, dataset_id: int, source_name: str
    ) -> DatasetSourceConfig | None:
        """Ambil satu baris konfigurasi untuk (dataset, sumber)."""
        canonical = API_KEY_TO_SOURCE_NAME.get(str(source_name).strip().lower())
        if canonical is None:
            logger.debug("get_dataset_source_config: source tidak dikenal %r", source_name)
            return None
        with self.session() as sess:
            return sess.scalar(
                select(DatasetSourceConfig).where(
                    DatasetSourceConfig.dataset_id == dataset_id,
                    DatasetSourceConfig.source_name == canonical,
                )
            )

    def list_dataset_source_configs(self, dataset_id: int) -> list[DatasetSourceConfig]:
        """Semua konfigurasi sumber sebuah dataset, urut S1 -> MODIS -> GPM."""
        with self.session() as sess:
            rows = list(sess.scalars(
                select(DatasetSourceConfig).where(
                    DatasetSourceConfig.dataset_id == dataset_id
                )
            ))
        return sorted(
            rows,
            key=lambda c: SOURCE_NAME_ORDER.index(c.source_name)
            if c.source_name in SOURCE_NAME_ORDER else len(SOURCE_NAME_ORDER),
        )

    def upsert_dataset_source_config(
        self, dataset_id: int, source_name: str, processing_levels
    ) -> DatasetSourceConfig:
        """Buat atau perbarui konfigurasi satu sumber."""
        normalized = normalize_source_configs({source_name: processing_levels})
        canonical, levels = next(iter(normalized.items()))
        with self.session() as sess:
            row = sess.scalar(
                select(DatasetSourceConfig).where(
                    DatasetSourceConfig.dataset_id == dataset_id,
                    DatasetSourceConfig.source_name == canonical,
                )
            )
            if row is None:
                row = DatasetSourceConfig(
                    dataset_id=dataset_id,
                    source_name=canonical,
                    processing_levels=levels,
                )
                sess.add(row)
            else:
                row.processing_levels = levels
                row.updated_at = func.now()
            sess.flush()
        logger.info("[SOURCE_CONFIG] dataset_id=%s %s -> %s", dataset_id, canonical, levels)
        return row

    def create_dataset_with_sources(
        self, dataset_dict: dict, sources_dict: dict
    ) -> Dataset:
        """Buat dataset beserta konfigurasi per-satelitnya dalam SATU transaksi."""
        configs = normalize_source_configs(sources_dict)

        payload = dict(dataset_dict or {})
        unknown = set(payload) - set(Dataset.__table__.columns.keys())
        if unknown:
            raise ValueError(f"unknown dataset column(s): {sorted(unknown)}")

        fusion_strategy = _validate_fusion_strategy(
            payload.get("fusion_strategy"), source_count=len(configs)
        )
        payload["fusion_strategy"] = fusion_strategy if fusion_strategy is not None else null()
        payload["preview_options"] = _validate_preview_options(
            payload.get("preview_options")
        )
        payload["fusion_output_only"] = _validate_fusion_output_only(
            payload.get("fusion_output_only"), fusion_strategy
        )
        tolerance = _validate_s1_tolerance(payload.get("s1_match_tolerance_days"))
        if tolerance is None:
            payload.pop("s1_match_tolerance_days", None)
        else:
            payload["s1_match_tolerance_days"] = tolerance
        if not payload.get("required_tiers"):
            payload["required_tiers"] = derive_required_tiers(
                configs, with_fusion=fusion_strategy is not None
            )

        with self.session() as sess:
            dataset = Dataset(**payload)
            dataset.source_configs = [
                DatasetSourceConfig(source_name=name, processing_levels=levels)
                for name, levels in configs.items()
            ]
            sess.add(dataset)
            sess.flush()
            sess.refresh(dataset)
            dataset_id = dataset.dataset_id
        logger.info(
            "[DATASET] created dataset_id=%s sources=%s fusion=%s tiers=%s",
            dataset_id, configs, fusion_strategy, payload["required_tiers"],
        )
        return dataset

    def get_last_dataset_config(self, created_by: int | None = None) -> dict:
        """Konfigurasi dataset terakhir yang dibuat, untuk tombol "Pakai Config
        Sebelumnya" (DOCS/DECISIONS.md D13, DOCS/INTERFACE.md GET
        /api/datasets/last-config).
        """
        with self.session() as sess:
            stmt = select(Dataset).where(Dataset.deleted_at.is_(None))
            if created_by is not None:
                stmt = stmt.where(Dataset.created_by == created_by,
                                  Dataset.dataset_kind == "STANDARD",
                                  Dataset.is_system.is_(False))
            dataset = sess.scalar(
                stmt
                .order_by(Dataset.created_at.desc(), Dataset.dataset_id.desc())
                .limit(1)
            )
            if dataset is None:
                return {}
            region_name = None
            if dataset.region_id is not None:
                region_name = sess.scalar(
                    select(RegionOfInterest.name).where(
                        RegionOfInterest.region_id == dataset.region_id
                    )
                )
            return {
                "region_id": dataset.region_id,
                "region_name": region_name,
                "sources": source_configs_to_api(list(dataset.source_configs)),
                "fusion_strategy": dataset.fusion_strategy,
                "fusion_output_only": dataset.fusion_output_only,
                "s1_match_tolerance_days": dataset.s1_match_tolerance_days,
                "preview_options": list(dataset.preview_options or []),
                "date_start": dataset.date_start,
                "date_end": dataset.date_end,
                "created_from_dataset_id": dataset.dataset_id,
                "created_at": dataset.created_at,
            }

    def dispose(self) -> None:
        self._engine.dispose()
        logger.info("DatabaseClient disposed. All connections closed.")


class FusionProduct(Base):
    """Multi-sensor (S1 + MODIS + GPM) feature stack registry for ML training."""

    __tablename__ = "fusion_products"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id", "feature_date", "processing_level",
            name="uq_fusion_dataset_date_level",
        ),
    )

    fusion_id          = Column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id         = Column(Integer, ForeignKey("datasets.dataset_id",
                                                     ondelete="CASCADE"))
    feature_date       = Column(Date, nullable=False)
    region_id          = Column(Integer, ForeignKey("regions_of_interest.region_id",
                                                     ondelete="RESTRICT"), nullable=False)
    s1_scene_id        = Column(Integer, ForeignKey("satellite_scenes.scene_id",
                                                     ondelete="SET NULL"))
    modis_scene_id     = Column(BigInteger, ForeignKey("nasa_scenes.nasa_scene_id",
                                                        ondelete="SET NULL"))
    gpm_scene_id       = Column(BigInteger, ForeignKey("nasa_scenes.nasa_scene_id",
                                                        ondelete="SET NULL"))
    days_since_s1      = Column(Integer, nullable=False)
    feature_stack_path = Column(Text, nullable=False)
    fusion_strategy    = Column(String(20))
    processing_level   = Column(String(20), server_default=text("'PROCESSED'"))
    temporal_offset_modis = Column(Integer)
    temporal_offset_gpm   = Column(Integer)
    s1_offset_days     = Column(SmallInteger)
    created_at         = Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    def __repr__(self) -> str:
        return (
            f"<FusionProduct id={self.fusion_id} date={self.feature_date} "
            f"level={self.processing_level} path={self.feature_stack_path}>"
        )
