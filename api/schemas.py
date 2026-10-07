# api/schemas.py
from __future__ import annotations
from datetime import date, datetime
from typing import Any
from pydantic import BaseModel, Field, field_validator, model_validator


class OkResponse(BaseModel):
    ok: bool = True
    message: str = "Success"


class SceneListItem(BaseModel):
    scene_id: int
    scene_uuid: str
    product_identifier: str
    platform: str
    instrument_mode: str
    polarization_vv: bool
    polarization_vh: bool
    acquisition_datetime: datetime
    orbit_direction: str
    orbit_number: int | None
    relative_orbit: int | None
    cloud_cover_percent: float | None
    resolution_m: int
    region_id: int
    is_available: bool
    created_at: datetime
    source: str = "S1"
    is_valid: bool = True
    invalid_reason: str | None = None
    model_config = {"from_attributes": True}


class NasaSceneListItem(BaseModel):
    """Granule MODIS/GPM (nasa_scenes) di GET /api/scenes?source=MODIS|GPM."""
    nasa_scene_id: int
    source: str
    tile_id: str
    product_short_name: str
    acquisition_date: date
    region_id: int
    run_type: str | None
    is_available: bool
    is_valid: bool
    invalid_reason: str | None
    created_at: datetime


class SceneDetail(SceneListItem):
    raw_file_path: str | None
    raw_file_size_mb: float | None
    download_url: str | None
    checksum_md5: str | None
    incidence_angle_near: float | None
    incidence_angle_far: float | None
    updated_at: datetime


class SceneListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[SceneListItem | NasaSceneListItem]


class ProductItem(BaseModel):
    product_id: int
    product_uuid: str
    # M30: S1 -> scene_id, MODIS/GPM -> nasa_scene_id, FUSION -> keduanya None.
    scene_id: int | None
    nasa_scene_id: int | None = None
    job_id: int
    dataset_id: int | None = None
    product_tier: str
    source: str
    product_type: str
    band_name: str
    file_name: str
    file_path: str
    file_size_mb: float
    file_format: str
    data_hash_sha256: str
    crs: str
    pixel_size_m: float | None
    rows: int | None
    cols: int | None
    band_count: int
    storage_location: str
    is_valid: bool
    is_latest: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ProductItem]


class IntegrityCheckResponse(BaseModel):
    product_id: int
    file_path: str
    stored_hash: str
    computed_hash: str
    integrity_ok: bool
    file_size_mb: float


class QualityMetricItem(BaseModel):
    metric_id: int
    scene_id: int
    product_id: int
    band_name: str
    assessed_at: datetime
    total_pixels: int
    valid_pixels: int
    nodata_pixels: int
    nodata_percent: float | None
    backscatter_mean_db: float | None
    backscatter_std_db: float | None
    backscatter_min_db: float | None
    backscatter_max_db: float | None
    cloud_threshold_percent: float
    radiometric_consistency: bool | None
    speckle_index: float | None
    quality_score: float
    quality_flag: str
    notes: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class QualityResponse(BaseModel):
    scene_id: int
    bands: list[QualityMetricItem]
    overall_quality: str


class LineageStep(BaseModel):
    lineage_id: int
    parent_product_id: int
    child_product_id: int
    transformation_type: str
    stage_id: int
    job_id: int
    transformation_params: dict[str, Any]
    input_checksum: str | None
    output_checksum: str | None
    created_at: datetime
    # Sejak layout tier-source, satu dataset punya rantai paralel per sensor;
    # ketiga field ini yang membuat langkah rantai bisa dibaca per source
    # tanpa menarik tiap product satu per satu.
    source: str | None = None
    parent_tier: str | None = None
    child_tier: str | None = None


class LineageResponse(BaseModel):
    product_id: int
    direction: str
    chain: list[LineageStep]
    total_steps: int


class JobStatusItem(BaseModel):
    job_id: int
    stage_name: str
    stage_order: int
    attempt_number: int
    status: str
    queued_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None


class PipelineStatusResponse(BaseModel):
    scene_id: int
    stages: list[JobStatusItem]
    overall_status: str


class HealthResponse(BaseModel):
    status: str
    db_connected: bool
    pool_size: int | None
    checked_out: int | None
    api_version: str = "1.0.0"
    timestamp: datetime


class DatasetQualitySettings(BaseModel):
    min_cloud_cover: float | None = None
    resolution_m: int | None = None
    # Satu arah orbit S1 saja; None = keduanya. Dibaca orkestrator setelah discovery.
    orbit_direction: str | None = Field(None, pattern="^(ASCENDING|DESCENDING)$")


class DatasetSourceConfigResponse(BaseModel):
    """Satu baris dataset_source_config seperti yang dilihat API.

    `source` memakai key huruf kecil gaya API ("sentinel1"), bukan nama kolom
    database ("SENTINEL1") -- pemetaannya milik database_client, lihat
    SOURCE_NAME_TO_API_KEY di sana.
    """
    source: str
    processing: list[str]


MAX_DATASET_DAYS = 366


class CreateDatasetRequest(BaseModel):
    """Payload POST /api/datasets (DOCS/INTERFACE.md, "Create Dataset").

    Menggantikan model prototipe yang memakai `tiers` + satu processing level
    global. `tiers` sekarang diturunkan internal dari `sources`
    (DOCS/DECISIONS.md, "Changed: Dataset Creation API"), jadi tidak
    lagi diterima di sini.
    """
    # Jalur utama UI: region_id dari tabel lokasi. `location` tetap diterima
    # untuk pemanggil lama/CLI -- di-resolve lewat nama lalu geocoding.
    region_id: int | None = None
    location: str | None = None
    date_start: date
    date_end: date
    name: str
    description: str | None = None
    # {"sentinel1": {"processing": ["RAW", "PROCESSED"]}, ...}
    sources: dict[str, dict[str, list[str]]]
    fusion_strategy: str | None = None
    # Simpan HDF5 fusi saja; artefak per-satelit dihapus SETELAH stack tanggal
    # itu ditulis. Bukan "lewati pemrosesan" -- fusi tetap butuh bahannya.
    fusion_output_only: bool = False
    # Hanya dipakai FULL_COVERAGE, yang merakit satu berkas per hari termasuk
    # hari tanpa scene S1 dan karena itu harus tahu seberapa jauh boleh
    # meminjam scene dari hari lain. None = pakai default kolom (2 hari).
    s1_match_tolerance_days: int | None = Field(default=None, ge=0, le=14)
    preview_options: list[str] | None = None
    quality_settings: DatasetQualitySettings | None = None
    generate_preview: bool = True

    @field_validator("sources")
    @classmethod
    def _validate_sources(
        cls, v: dict[str, dict[str, list[str]]]
    ) -> dict[str, dict[str, list[str]]]:
        # Aturan sumber/level hidup di normalize_source_configs(): satu-satunya
        # definisi "sources yang sah", dipakai juga oleh ETL dan penulis
        # langsung ke database. Menyalinnya ke sini akan membuat dua definisi
        # yang bisa berbeda diam-diam.
        from etl.database_client import normalize_source_configs, SOURCE_NAME_TO_API_KEY

        normalized = normalize_source_configs(v)
        return {
            SOURCE_NAME_TO_API_KEY[name]: {"processing": levels}
            for name, levels in normalized.items()
        }

    @field_validator("preview_options")
    @classmethod
    def _validate_preview_options(cls, v: list[str] | None) -> list[str] | None:
        # None diteruskan apa adanya: "tidak disebutkan" berbeda dari "[] =
        # sengaja tanpa preview", dan pembedaan itu ditangani di layer database.
        if v is None:
            return None
        from etl.database_client import _validate_preview_options

        return _validate_preview_options(v)

    @model_validator(mode="after")
    def _validate_date_range(self) -> "CreateDatasetRequest":
        if self.date_end < self.date_start:
            raise ValueError("date_end must be >= date_start")
        # INTERFACE §2.6: wizard dibatasi 366 hari; ditegakkan juga di API agar
        # klien lain (skrip, Swagger) tidak memicu unduhan bertahun-tahun.
        if (self.date_end - self.date_start).days + 1 > MAX_DATASET_DAYS:
            raise ValueError(f"date range must be at most {MAX_DATASET_DAYS} days")
        return self

    @model_validator(mode="after")
    def _require_location(self) -> "CreateDatasetRequest":
        if self.region_id is None and not (self.location or "").strip():
            raise ValueError("Provide region_id or location")
        return self

    @model_validator(mode="after")
    def _validate_fusion_strategy(self) -> "CreateDatasetRequest":
        # Wajib kalau sumbernya >1, harus null kalau cuma 1 (DOCS/INTERFACE.md,
        # bagian Validation). Aturan ini tidak bisa jadi CHECK constraint --
        # jumlah sumber ada di tabel lain -- jadi ditegakkan di sini dan lagi
        # di database_client untuk penulis non-API.
        from etl.database_client import _validate_fusion_strategy

        self.fusion_strategy = _validate_fusion_strategy(
            self.fusion_strategy, source_count=len(self.sources)
        )
        return self


class DatasetCreateResponse(BaseModel):
    dataset_id: int
    job_id: int
    status: str
    source_configs: list[DatasetSourceConfigResponse] = Field(default_factory=list)


class DatasetLastConfigResponse(BaseModel):
    """GET /api/datasets/last-config.

    Sengaja tanpa `name`: harus diisi ulang user supaya "Pakai Config
    Sebelumnya" tidak diam-diam menduplikasi dataset (DOCS/DECISIONS.md D13).
    Rentang tanggal DIIKUTSERTAKAN (sebagai preset, bukan kunci) supaya user
    tidak perlu mengetik ulang tanggal yang sama setiap kali; field-nya tetap
    bisa diedit di wizard sebelum submit.
    """
    region_id: int | None
    region_name: str | None
    sources: dict[str, dict[str, list[str]]]
    fusion_strategy: str | None
    fusion_output_only: bool = False
    s1_match_tolerance_days: int = 2
    preview_options: list[str]
    date_start: date | None
    date_end: date | None
    created_from_dataset_id: int
    created_at: datetime


class DatasetItem(BaseModel):
    dataset_id: int
    dataset_uuid: str
    name: str
    description: str | None
    location_label: str | None
    date_start: date
    date_end: date
    required_tiers: list[str]
    dataset_kind: str
    status: str
    total_scenes: int
    completed_scenes: int
    failed_scenes: int
    total_size_bytes: int
    is_deletable: bool
    generate_preview: bool
    created_by: int | None = None
    created_by_name: str | None = None
    # Konfigurasi per-satelit ikut di listing, bukan cuma di detail: kartu
    # dataset (Tab 2) menampilkan satelit + level pemrosesan + strategi fusi
    # (DOCS/DECISIONS.md, "Changed: Dataset Cards"), dan kartu itu
    # dirender dari GET /api/datasets tanpa menarik detail satu per satu.
    # Model lama -- selected_satellites + satu processing_level global --
    # digantikan seluruhnya oleh source_configs.
    source_configs: list[DatasetSourceConfigResponse] = Field(default_factory=list)
    # Hitungan scene dan byte per satelit, untuk kartu dataset. Dihitung dari
    # data_products lewat SATU query agregat untuk seluruh halaman -- kartu
    # dirender ulang tiap polling, jadi tidak boleh fan-out per dataset.
    # Hanya berisi source yang benar-benar punya produk; source yang
    # dikonfigurasi tapi belum menghasilkan apa pun tidak muncul.
    scenes_by_source: dict[str, int] = Field(default_factory=dict)
    bytes_by_source: dict[str, int] = Field(default_factory=dict)
    fusion_strategy: str | None = None
    fusion_output_only: bool = False
    s1_match_tolerance_days: int = 2
    # Arah orbit S1 dari quality_settings; None = keduanya. Ditampilkan di kartu.
    s1_orbit_direction: str | None = None
    preview_options: list[str] = Field(default_factory=list)
    # Diisi hanya kalau dataset ini dibuat lewat "Pakai Config Sebelumnya":
    # dataset_id yang config-nya disalin. None untuk dataset yang dikonfigurasi
    # dari nol -- tidak ada kolomnya di database, jadi nilainya berasal dari
    # payload pembuatan.
    last_config_source: int | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# Alias eksplisit: DOCS/INTERFACE.md menyebut skema respons dataset "DatasetResponse".
DatasetResponse = DatasetItem


class DatasetDetail(DatasetItem):
    bbox_wkt: str
    region_id: int | None
    quality_settings: dict[str, Any]
    deleted_at: datetime | None


class DatasetListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[DatasetItem]


class SceneJobStateItem(BaseModel):
    id: int
    job_id: int
    product_identifier: str
    scene_id: int | None
    current_stage: str | None
    stage_status: str
    attempt_number: int
    max_retries: int
    last_error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    model_config = {"from_attributes": True}


class ProgressLayer(BaseModel):
    key: str
    source: str
    phase: str
    ratio: float


class DatasetProgressResponse(BaseModel):
    dataset_id: int
    job_id: int | None
    status: str
    total_scenes: int
    downloaded_count: int
    processed_count: int
    failed_count: int
    cleaned_count: int
    progress_percent: int
    paused: bool
    pause_reason: str | None
    scenes: list[SceneJobStateItem]
    # Lapisan radar progres kartu dataset (lihat DatasetManager._progress_layers).
    layers: list[ProgressLayer] = []
    # Dihitung DatasetManager.get_progress() untuk loading bar kartu. Harus
    # dideklarasikan di sini: field yang tidak ada di model dibuang FastAPI.
    queue_position: int | None = None
    timing: dict[str, Any] | None = None
    waiting: dict[str, Any] | None = None
    alerts: list[dict[str, Any]] = []


class DatasetPauseRequest(BaseModel):
    reason: str = "user_requested"


class DatasetPauseResponse(BaseModel):
    status: str
    reason: str | None


class DatasetResumeResponse(BaseModel):
    status: str
    resume_count: int


class DatasetDeleteResponse(BaseModel):
    status: str
    dataset_id: int


class DatasetCancelRequest(BaseModel):
    cascade_delete: bool = True


class DatasetCancelResponse(BaseModel):
    status: str
    deleted_files: int
    retained_tier: str


class DatasetLogEntry(BaseModel):
    log_id: int
    timestamp: datetime
    module: str
    dataset_id: int
    scene_id: str
    stage: str
    status: str
    message: str
    details: dict


class DatasetLogsResponse(BaseModel):
    total: int
    limit: int
    logs: list[DatasetLogEntry]


class DeletionProgressResponse(BaseModel):
    status: str
    total_files: int
    deleted_count: int
    freed_bytes: int
    progress_percent: int


class SourceStorageItem(BaseModel):
    """Pemakaian disk satu source di dalam satu tier."""
    size_bytes: int
    size_mb: float
    file_count: int
    scene_count: int | None = None


class TierStorageItem(BaseModel):
    """Pemakaian disk satu tier, dipecah per source.

    `sources` kosong untuk tier fusion: isinya gabungan semua source, jadi
    tidak ada pecahan per-source yang bermakna di sana.
    """
    size_bytes: int
    size_mb: float
    file_count: int
    scene_count: int
    sources: dict[str, SourceStorageItem] = Field(default_factory=dict)


class DatasetStorageSummary(BaseModel):
    dataset_id: int
    tiers: dict[str, TierStorageItem]
    sources: dict[str, SourceStorageItem]
    total_size_bytes: int
    total_size_mb: float
    # True kalau dataset ini memakai struktur folder sebelum relayout
    # (folder tanggal + tier di jalur). Berkasnya masih utuh dan tetap bisa
    # diunduh, tapi pohon penyimpanan tidak dirender dengan kosakata yang
    # sudah tidak berlaku -- UI menampilkan pesan "format lama" sebagai gantinya.
    legacy_layout: bool = False


class DatasetFileItem(BaseModel):
    name: str
    path: str
    size_mb: float


class DatasetSceneFiles(BaseModel):
    scene: str
    source: str | None = None
    files: list[DatasetFileItem]


class DatasetTierFilesResponse(BaseModel):
    dataset_id: int
    tier: str
    source: str | None = None
    scenes: list[DatasetSceneFiles]


class SourceQualityItem(BaseModel):
    """Kualitas satu source untuk satu dataset.

    Cuma SENTINEL1 yang punya metrik radiometrik sungguhan (quality_metrics,
    dihitung module6_analytics atas band VV/VH). Untuk MODIS/GPM yang
    dilaporkan adalah *coverage*: berapa band/hari yang benar-benar mendarat
    di disk dibanding yang diharapkan — bukan skor radiometrik, dan sengaja
    dibedakan namanya supaya tidak dibaca sebagai hal yang sama.
    """
    source: str
    kind: str                       # "RADIOMETRIC" | "COVERAGE"
    product_count: int
    scene_count: int
    quality_score: float | None = None
    quality_flag: str | None = None
    bands: dict[str, float] = Field(default_factory=dict)


class DatasetQualityBySourceResponse(BaseModel):
    dataset_id: int
    sources: list[SourceQualityItem]


class RegionItem(BaseModel):
    region_id: int
    region_code: str
    name: str
    description: str | None
    bbox: list[float]          # [min_lon, min_lat, max_lon, max_lat]
    area_km2: float | None
    source: str = "SYSTEM"     # SEEDER | SYSTEM
    created_at: datetime | None = None


class RegionListResponse(BaseModel):
    items: list[RegionItem]
    total: int = 0


# --- Live Monitoring (LIVE_MONITORING.md) -----------------------------------

class LiveAreaCreateRequest(BaseModel):
    region_id: int
    name: str | None = Field(default=None, max_length=200)
    # None = app_settings.live.retention_default
    retention: int | None = Field(default=None, ge=1, le=60)


class LiveAreaUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    retention: int | None = Field(default=None, ge=1, le=60)
    enabled: bool | None = None


# --- Autentikasi & token API (INTERFACE.md §4.1) ----------------------------

USERNAME_PATTERN = r"^[a-z0-9_.]{3,50}$"
ASSIGNABLE_ROLES = ("USER", "ANALYST", "DATA_ENGINEER", "ADMIN")


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class MeResponse(BaseModel):
    user_id: int
    username: str
    full_name: str
    organization: str | None = None
    role_code: str
    auth: str
    permissions: list[str]


EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterRequest(BaseModel):
    """Registrasi mandiri (M56): selalu menjadi USER."""
    email: str = Field(min_length=6, max_length=254, pattern=EMAIL_PATTERN)
    username: str = Field(pattern=USERNAME_PATTERN)
    password: str = Field(min_length=1, max_length=200)
    password_confirm: str = Field(min_length=1, max_length=200)


class SessionInfoResponse(BaseModel):
    """Peran dan izin pemanggil, termasuk pengunjung yang belum masuk (M56)."""
    authenticated: bool
    role_code: str
    permissions: list[str]
    user: MeResponse | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


class TokenCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    scope: str = Field(pattern=r"^(READ|READ_DOWNLOAD)$")
    expires_in_days: int = Field(default=90, ge=1, le=180)


class TokenItem(BaseModel):
    token_id: int
    user_id: int
    username: str | None = None
    name: str
    prefix: str
    scope: str
    expires_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime
    active: bool


class TokenCreateResponse(BaseModel):
    token_id: int
    token: str
    prefix: str
    scope: str
    expires_at: datetime


class TokenListResponse(BaseModel):
    items: list[TokenItem]
    total: int
    limit: int
    offset: int


# --- Administrasi akun & log (INTERFACE.md §4.9) ----------------------------

class AdminUserItem(BaseModel):
    user_id: int
    username: str
    full_name: str
    organization: str | None = None
    email: str | None = None
    role_code: str
    is_active: bool
    is_locked: bool
    locked_until: datetime | None = None
    last_login_at: datetime | None = None
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime


class AdminUserListResponse(BaseModel):
    items: list[AdminUserItem]
    total: int
    limit: int
    offset: int


class AdminUserCreateRequest(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    full_name: str = Field(min_length=1, max_length=100)
    organization: str | None = Field(default=None, max_length=100)
    role_code: str = Field(pattern=r"^(USER|ANALYST|DATA_ENGINEER|ADMIN)$")
    password: str = Field(min_length=1, max_length=200)


class AdminUserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    organization: str | None = Field(default=None, max_length=100)
    role_code: str | None = Field(default=None, pattern=r"^(USER|ANALYST|DATA_ENGINEER|ADMIN)$")
    is_active: bool | None = None


class AdminResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=1, max_length=200)


class LogListResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int
