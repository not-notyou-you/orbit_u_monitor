-- =============================================================================
-- database/monitor_schema.sql — Orbit-U: The Monitor
-- =============================================================================
-- Satu berkas yang membangun SELURUH skema (warisan DataLab + tabel baru) dari
-- database kosong: tipe, tabel, constraint, index, trigger, VIEW, dan COMMENT
-- untuk setiap tabel dan kolom (DATABASE.md §6, M34). Menggantikan
-- schema.sql + 26 migrasi DataLab.
--
-- Urutan penerapan:
--     psql -v ON_ERROR_STOP=1 -d themonitor -f database/monitor_schema.sql
--     psql -v ON_ERROR_STOP=1 -d themonitor -f database/monitor_security.sql
--     psql -v ON_ERROR_STOP=1 -d themonitor -f database/monitor_seed.sql
-- atau: python database/apply_schema.py
--
-- Berkas ini TIDAK idempoten: ia mengasumsikan database kosong. Nilai enum
-- legacy (BRONZE/SILVER/GOLD/FUSION) dan tabel fitur yang dihapus
-- (dataset_versions, api_access_logs, processing_rules, live_dataset_sources,
-- reference_land_polygons) sengaja tidak dibawa.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- -----------------------------------------------------------------------------
-- TIPE ENUM (warisan, tanpa nilai legacy)
-- -----------------------------------------------------------------------------
CREATE TYPE orbit_direction_enum  AS ENUM ('ASCENDING', 'DESCENDING');
-- WAITING_UPSTREAM: granule hulu belum terbit (PIPELINE §8); SKIPPED_LOCKED:
-- run scheduler dilewati karena advisory lock dipegang worker lain (§7).
CREATE TYPE job_status_enum       AS ENUM ('QUEUED', 'RUNNING', 'SUCCESS', 'FAILED', 'CANCELLED', 'WAITING_UPSTREAM', 'SKIPPED_LOCKED');
-- Kosakata tier D14: dinamai menurut kontrak artefak, bukan medallion.
CREATE TYPE product_tier_enum     AS ENUM ('RAW', 'ALIGNED', 'DESPECKLED', 'INDICES', 'ACCUMULATED', 'COG', 'FUSED');
CREATE TYPE storage_location_enum AS ENUM ('LOCAL', 'S3', 'GCS', 'AZURE_BLOB');
CREATE TYPE alert_severity_enum   AS ENUM ('INFO', 'WARNING', 'CRITICAL');
CREATE TYPE alert_event_type_enum AS ENUM ('DATA_ARRIVAL', 'QUALITY_WARNING', 'PIPELINE_ERROR', 'THRESHOLD_BREACH', 'SYSTEM_ALERT');

COMMENT ON TYPE orbit_direction_enum  IS 'Arah lintasan orbit Sentinel-1.';
COMMENT ON TYPE job_status_enum       IS 'Status eksekusi satu baris processing_jobs (+ WAITING_UPSTREAM, SKIPPED_LOCKED untuk job hidromet dan scheduler).';
COMMENT ON TYPE product_tier_enum     IS 'Tier lineage D14: RAW (format vendor) -> ALIGNED (EPSG:4326 + crop AOI) -> DESPECKLED|INDICES|ACCUMULATED (nilai tambah per sumber) -> COG (analysis-ready) -> FUSED (HDF5 multi-sensor).';
COMMENT ON TYPE storage_location_enum IS 'Lokasi penyimpanan berkas produk. Monitor hanya memakai LOCAL.';
COMMENT ON TYPE alert_severity_enum   IS 'Tingkat keparahan quality_alerts.';
COMMENT ON TYPE alert_event_type_enum IS 'Jenis kejadian quality_alerts (peringatan operasional pipeline).';

-- -----------------------------------------------------------------------------
-- FUNGSI TRIGGER UMUM
-- -----------------------------------------------------------------------------
CREATE FUNCTION fn_set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END $$;
COMMENT ON FUNCTION fn_set_updated_at() IS 'Trigger BEFORE UPDATE: mengisi kolom updated_at dengan now().';

-- =============================================================================
-- TABEL MASTER (DATABASE.md §3)
-- =============================================================================

-- M1 roles --------------------------------------------------------------------
CREATE TABLE roles (
    role_id        SMALLSERIAL  PRIMARY KEY,
    role_code      VARCHAR(20)  NOT NULL UNIQUE,
    role_name      VARCHAR(50)  NOT NULL,
    db_role        VARCHAR(40)  NOT NULL UNIQUE,
    requires_login BOOLEAN      NOT NULL,
    description    TEXT
);
COMMENT ON TABLE  roles IS 'Master role aplikasi (5 role, M13). Setiap role dipetakan ke satu role PostgreSQL yang dipakai lewat SET LOCAL ROLE.';
COMMENT ON COLUMN roles.role_id        IS 'PK surrogate.';
COMMENT ON COLUMN roles.role_code      IS 'Alternate key. PUBLIC | USER | ANALYST | DATA_ENGINEER | ADMIN.';
COMMENT ON COLUMN roles.role_name      IS 'Label role untuk UI (Bahasa Indonesia), mis. "Relawan".';
COMMENT ON COLUMN roles.db_role        IS 'Nama role PostgreSQL padanannya, mis. monitor_analyst (DATABASE.md §8.1).';
COMMENT ON COLUMN roles.requires_login IS 'false hanya untuk PUBLIC (pengunjung tanpa akun).';
COMMENT ON COLUMN roles.description    IS 'Uraian singkat kebutuhan akses role ini.';

-- M2 users --------------------------------------------------------------------
CREATE TABLE users (
    user_id            SERIAL       PRIMARY KEY,
    role_id            SMALLINT     NOT NULL REFERENCES roles (role_id),
    username           VARCHAR(50)  NOT NULL UNIQUE CHECK (username ~ '^[a-z0-9_.]{3,50}$'),
    password_hash      VARCHAR(255) NOT NULL,
    full_name          VARCHAR(100) NOT NULL,
    organization       VARCHAR(100),
    is_active          BOOLEAN      NOT NULL DEFAULT true,
    failed_login_count SMALLINT     NOT NULL DEFAULT 0 CHECK (failed_login_count >= 0),
    locked_until       TIMESTAMPTZ,
    last_login_at      TIMESTAMPTZ,
    created_by         INT          REFERENCES users (user_id),
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_users_role ON users (role_id);
COMMENT ON TABLE  users IS 'Akun pengguna yang login (USER s.d. ADMIN). Akun dinonaktifkan, tidak pernah dihapus.';
COMMENT ON COLUMN users.user_id            IS 'PK surrogate.';
COMMENT ON COLUMN users.role_id            IS 'FK -> roles. Tidak boleh PUBLIC (ditegakkan trg_users_role_not_public).';
COMMENT ON COLUMN users.username           IS 'Alternate key, huruf kecil/angka/_/. 3-50 karakter. Contoh: relawan.bayah';
COMMENT ON COLUMN users.password_hash      IS 'Hash bcrypt (cost 12). Tidak pernah dikirim ke klien; disensor di audit_log.';
COMMENT ON COLUMN users.full_name          IS 'Nama lengkap untuk tampilan.';
COMMENT ON COLUMN users.organization       IS 'Asal organisasi, mis. GMLS, BPBD Lebak, kampus.';
COMMENT ON COLUMN users.is_active          IS 'false = akun dinonaktifkan ADMIN; login ditolak.';
COMMENT ON COLUMN users.failed_login_count IS 'Jumlah gagal login beruntun; 5 kali -> locked_until diisi.';
COMMENT ON COLUMN users.locked_until       IS 'Akun terkunci sementara sampai waktu ini (15 menit setelah 5 kali gagal).';
COMMENT ON COLUMN users.last_login_at      IS 'Waktu login sukses terakhir.';
COMMENT ON COLUMN users.created_by         IS 'FK -> users: ADMIN yang membuat akun ini. NULL untuk admin pertama (create_admin.py).';
COMMENT ON COLUMN users.created_at         IS 'Waktu akun dibuat.';
COMMENT ON COLUMN users.updated_at         IS 'Waktu baris terakhir diubah (trigger).';

CREATE FUNCTION fn_users_role_not_public() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (SELECT role_code FROM roles WHERE role_id = NEW.role_id) = 'PUBLIC' THEN
        RAISE EXCEPTION 'users.role_id must not be the PUBLIC role'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
COMMENT ON FUNCTION fn_users_role_not_public() IS 'Menolak akun dengan role PUBLIC (PUBLIC = pengunjung tanpa login).';
CREATE TRIGGER trg_users_role_not_public BEFORE INSERT OR UPDATE OF role_id ON users
    FOR EACH ROW EXECUTE FUNCTION fn_users_role_not_public();

-- M3 satellite_sources --------------------------------------------------------
CREATE TABLE satellite_sources (
    source_id            SMALLSERIAL  PRIMARY KEY,
    source_code          VARCHAR(20)  NOT NULL UNIQUE,
    source_name          VARCHAR(100) NOT NULL,
    provider             VARCHAR(50),
    sensor_type          VARCHAR(20)  CHECK (sensor_type IN ('SAR', 'OPTICAL', 'PRECIPITATION', 'DERIVED')),
    spatial_resolution_m NUMERIC(8,1),
    nominal_revisit_days NUMERIC(4,1),
    products             TEXT
);
COMMENT ON TABLE  satellite_sources IS 'Master sumber data. Kolom VARCHAR "source" warisan DataLab dihubungkan ke source_code lewat FK.';
COMMENT ON COLUMN satellite_sources.source_id            IS 'PK surrogate.';
COMMENT ON COLUMN satellite_sources.source_code          IS 'Alternate key: SENTINEL1 | MODIS | GPM | FUSION.';
COMMENT ON COLUMN satellite_sources.source_name          IS 'Nama tampilan, mis. "Sentinel-1 SAR".';
COMMENT ON COLUMN satellite_sources.provider             IS 'Penyedia data: ESA/CDSE, NASA LANCE/LAADS, NASA GES DISC.';
COMMENT ON COLUMN satellite_sources.sensor_type          IS 'SAR | OPTICAL | PRECIPITATION | DERIVED (FUSION).';
COMMENT ON COLUMN satellite_sources.spatial_resolution_m IS 'Resolusi spasial nominal (meter): 10 / 250 / 11000.';
COMMENT ON COLUMN satellite_sources.nominal_revisit_days IS 'Revisit nominal (hari). Angka nyata dihitung dari data (v_kelengkapan_data).';
COMMENT ON COLUMN satellite_sources.products             IS 'Produk yang diambil, mis. "GRD IW" atau "GPM_3IMERGDF, DL, DE".';

-- M4 spectral_bands -----------------------------------------------------------
CREATE TABLE spectral_bands (
    band_id     SMALLSERIAL  PRIMARY KEY,
    source_id   SMALLINT     NOT NULL REFERENCES satellite_sources (source_id),
    band_code   VARCHAR(20)  NOT NULL UNIQUE,
    band_name   VARCHAR(100) NOT NULL,
    unit        VARCHAR(20),
    valid_min   NUMERIC,
    valid_max   NUMERIC,
    aggregation VARCHAR(20)  NOT NULL CHECK (aggregation IN ('MEAN', 'FRACTION')),
    CHECK (valid_min IS NULL OR valid_max IS NULL OR valid_min <= valid_max)
);
CREATE INDEX idx_bands_source ON spectral_bands (source_id);
COMMENT ON TABLE  spectral_bands IS 'Master band/variabel yang diamati per sumber; dipakai region_observations, alert_rules, quality_thresholds, live_scene_metrics.';
COMMENT ON COLUMN spectral_bands.band_id     IS 'PK surrogate.';
COMMENT ON COLUMN spectral_bands.source_id   IS 'FK -> satellite_sources.';
COMMENT ON COLUMN spectral_bands.band_code   IS 'Alternate key, mis. VV, NDVI, RAIN_24H, WATER_CHANGE.';
COMMENT ON COLUMN spectral_bands.band_name   IS 'Label UI (Bahasa Indonesia).';
COMMENT ON COLUMN spectral_bands.unit        IS 'Satuan nilai: dB, index, %, mm, km2.';
COMMENT ON COLUMN spectral_bands.valid_min   IS 'Batas bawah nilai sah; region_observations di luar rentang ditolak trg_obs_range. NULL = tanpa batas.';
COMMENT ON COLUMN spectral_bands.valid_max   IS 'Batas atas nilai sah. NULL = tanpa batas.';
COMMENT ON COLUMN spectral_bands.aggregation IS 'Cara agregasi zonal: MEAN (hujan, NDVI, NDWI, backscatter) atau FRACTION (persen piksel kelas air).';

-- M5 administrative_regions ---------------------------------------------------
CREATE TABLE administrative_regions (
    region_id        SERIAL        PRIMARY KEY,
    parent_region_id INT           REFERENCES administrative_regions (region_id),
    pcode            VARCHAR(20)   NOT NULL UNIQUE,
    region_name      VARCHAR(100)  NOT NULL,
    admin_level      SMALLINT      NOT NULL CHECK (admin_level IN (2, 3)),
    in_aoi           BOOLEAN       NOT NULL DEFAULT false,
    geom             GEOMETRY(MultiPolygon, 4326) NOT NULL,
    area_km2         NUMERIC(10,2) GENERATED ALWAYS AS (ST_Area(geom::geography) / 1e6) STORED,
    source_dataset   VARCHAR(100)  NOT NULL,
    CHECK (admin_level = 2 OR parent_region_id IS NOT NULL),
    CHECK (NOT in_aoi OR admin_level = 3)
);
CREATE INDEX idx_admreg_geom   ON administrative_regions USING GIST (geom);
CREATE INDEX idx_admreg_in_aoi ON administrative_regions (region_id) WHERE in_aoi;
CREATE INDEX idx_admreg_parent ON administrative_regions (parent_region_id);
COMMENT ON TABLE  administrative_regions IS 'Batas wilayah resmi COD-AB Indonesia (BPS via OCHA/HDX): Kabupaten Lebak (level 2) dan kecamatannya (level 3). AOI GMLS = kecamatan in_aoi (M8).';
COMMENT ON COLUMN administrative_regions.region_id        IS 'PK surrogate.';
COMMENT ON COLUMN administrative_regions.parent_region_id IS 'FK -> administrative_regions: kabupaten induk. NULL untuk level 2.';
COMMENT ON COLUMN administrative_regions.pcode            IS 'Alternate key: P-code COD-AB, mis. ID3602xxx.';
COMMENT ON COLUMN administrative_regions.region_name      IS 'Nama wilayah (ADM2_EN/ADM3_EN), mis. Bayah.';
COMMENT ON COLUMN administrative_regions.admin_level      IS '2 = kabupaten, 3 = kecamatan.';
COMMENT ON COLUMN administrative_regions.in_aoi           IS 'true = kecamatan termasuk cakupan GMLS (hanya level 3). Diubah ADMIN.';
COMMENT ON COLUMN administrative_regions.geom             IS 'Poligon batas wilayah, MultiPolygon EPSG:4326 (ST_Multi(ST_MakeValid(...))).';
COMMENT ON COLUMN administrative_regions.area_km2         IS 'Luas geodesik (km2), kolom GENERATED dari geom (redundansi terkendali, §9).';
COMMENT ON COLUMN administrative_regions.source_dataset   IS 'Asal data batas, mis. "COD-AB IDN 2020 (BPS/OCHA)".';

-- M6 regions_of_interest [UBAH] -----------------------------------------------
CREATE TABLE regions_of_interest (
    region_id       SERIAL        PRIMARY KEY,
    region_code     VARCHAR(20)   NOT NULL UNIQUE,
    name            VARCHAR(100)  NOT NULL,
    description     TEXT,
    bbox            GEOMETRY(Polygon, 4326) NOT NULL,
    centroid        GEOMETRY(Point, 4326),
    area_km2        NUMERIC(12,4),
    admin_level     SMALLINT      NOT NULL DEFAULT 3,
    country_code    CHAR(2)       NOT NULL DEFAULT 'ID',
    is_active       BOOLEAN       NOT NULL DEFAULT true,
    source          VARCHAR(20)   NOT NULL DEFAULT 'SYSTEM' CHECK (source IN ('SEEDER', 'SYSTEM')),
    admin_region_id INT           REFERENCES administrative_regions (region_id),
    is_monitor_aoi  BOOLEAN       NOT NULL DEFAULT false,
    deleted_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX idx_roi_bbox        ON regions_of_interest USING GIST (bbox);
CREATE INDEX idx_roi_name_lower  ON regions_of_interest (lower(name));
CREATE INDEX idx_roi_not_deleted ON regions_of_interest (deleted_at) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX uq_roi_monitor_aoi ON regions_of_interest (is_monitor_aoi) WHERE is_monitor_aoi;
COMMENT ON TABLE  regions_of_interest IS 'AOI dataset (bbox) warisan DataLab. Baris baru hanya dari kecamatan atau gabungan kecamatan (M27); tepat satu baris adalah AOI GMLS (is_monitor_aoi).';
COMMENT ON COLUMN regions_of_interest.region_id       IS 'PK surrogate. Dirujuk datasets, satellite_scenes, nasa_scenes, fusion_products, live_areas.';
COMMENT ON COLUMN regions_of_interest.region_code     IS 'Alternate key, mis. GMLS_AOI atau ID3602xxx.';
COMMENT ON COLUMN regions_of_interest.name            IS 'Nama tampilan ROI.';
COMMENT ON COLUMN regions_of_interest.description     IS 'Keterangan bebas.';
COMMENT ON COLUMN regions_of_interest.bbox            IS 'Kotak pembatas WGS84 (Polygon EPSG:4326) yang dipakai pencarian scene dan crop.';
COMMENT ON COLUMN regions_of_interest.centroid        IS 'Titik tengah bbox, diisi trg_roi_centroid.';
COMMENT ON COLUMN regions_of_interest.area_km2        IS 'Luas bbox (km2).';
COMMENT ON COLUMN regions_of_interest.admin_level     IS 'Tingkat administratif ROI (warisan): 2 kabupaten, 3 kecamatan.';
COMMENT ON COLUMN regions_of_interest.country_code    IS 'Kode negara ISO 3166-1 alpha-2, selalu ID.';
COMMENT ON COLUMN regions_of_interest.is_active       IS 'false = ROI dinonaktifkan (warisan; penghapusan memakai deleted_at).';
COMMENT ON COLUMN regions_of_interest.source          IS 'Asal baris: SEEDER (seed) | SYSTEM (dibuat sistem/ADMIN dari kecamatan). Wilayah buatan pengguna dihapus (M27).';
COMMENT ON COLUMN regions_of_interest.admin_region_id IS 'FK -> administrative_regions bila ROI = satu kecamatan; NULL untuk gabungan.';
COMMENT ON COLUMN regions_of_interest.is_monitor_aoi  IS 'true = ROI AOI GMLS (bbox = ST_Envelope(ST_Union) kecamatan in_aoi). Paling banyak satu baris.';
COMMENT ON COLUMN regions_of_interest.deleted_at      IS 'Soft delete. NULL = aktif. Baris tidak dihapus fisik karena dirujuk FK.';
COMMENT ON COLUMN regions_of_interest.created_at      IS 'Waktu baris dibuat.';
COMMENT ON COLUMN regions_of_interest.updated_at      IS 'Waktu baris terakhir diubah (trigger).';

CREATE FUNCTION fn_compute_roi_centroid() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.centroid := ST_Centroid(NEW.bbox);
    RETURN NEW;
END $$;
COMMENT ON FUNCTION fn_compute_roi_centroid() IS 'Mengisi regions_of_interest.centroid dari bbox.';
CREATE TRIGGER trg_roi_centroid BEFORE INSERT OR UPDATE OF bbox ON regions_of_interest
    FOR EACH ROW EXECUTE FUNCTION fn_compute_roi_centroid();

-- M7 processing_stages [WARIS] ------------------------------------------------
CREATE TABLE processing_stages (
    stage_id        SERIAL       PRIMARY KEY,
    stage_name      VARCHAR(50)  NOT NULL UNIQUE,
    stage_code      VARCHAR(20)  NOT NULL UNIQUE,
    stage_order     SMALLINT     NOT NULL UNIQUE,
    description     TEXT,
    source_code     VARCHAR(20)  REFERENCES satellite_sources (source_code) ON UPDATE CASCADE,
    timeout_minutes SMALLINT     NOT NULL DEFAULT 60,
    retry_count     SMALLINT     NOT NULL DEFAULT 3,
    retry_delay_sec SMALLINT     NOT NULL DEFAULT 30,
    is_mandatory    BOOLEAN      NOT NULL DEFAULT true,
    is_active       BOOLEAN      NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
COMMENT ON TABLE  processing_stages IS 'Master tahap pipeline (S1/MODIS/GPM/FUSION/PREVIEW + HYDROMET_AGGREGATE, ALERT_CHECK, WATER_CHANGE, REPORT_BUILD).';
COMMENT ON COLUMN processing_stages.stage_id        IS 'PK surrogate.';
COMMENT ON COLUMN processing_stages.stage_name      IS 'Nama tahap yang dipakai kode, mis. LEE_FILTER, GOLD_EXPORT, HYDROMET_AGGREGATE.';
COMMENT ON COLUMN processing_stages.stage_code      IS 'Kode pendek tahap, mis. LF, GE, HA.';
COMMENT ON COLUMN processing_stages.stage_order     IS 'Urutan pendaftaran (unik). Urutan eksekusi nyata ditentukan kode orchestrator.';
COMMENT ON COLUMN processing_stages.description     IS 'Uraian tahap.';
COMMENT ON COLUMN processing_stages.source_code     IS 'FK -> satellite_sources.source_code bila tahap khusus satu sumber; NULL = lintas sumber.';
COMMENT ON COLUMN processing_stages.timeout_minutes IS 'Batas waktu tahap (menit).';
COMMENT ON COLUMN processing_stages.retry_count     IS 'Jumlah percobaan ulang yang diizinkan.';
COMMENT ON COLUMN processing_stages.retry_delay_sec IS 'Jeda antar percobaan ulang (detik).';
COMMENT ON COLUMN processing_stages.is_mandatory    IS 'false = tahap opsional (mis. PREVIEW).';
COMMENT ON COLUMN processing_stages.is_active       IS 'false = tahap tidak dipakai lagi.';
COMMENT ON COLUMN processing_stages.created_at      IS 'Waktu baris dibuat.';
COMMENT ON COLUMN processing_stages.updated_at      IS 'Waktu baris terakhir diubah (trigger).';

-- M8 quality_thresholds -------------------------------------------------------
CREATE TABLE quality_thresholds (
    threshold_id SMALLSERIAL  PRIMARY KEY,
    band_id      SMALLINT     NOT NULL REFERENCES spectral_bands (band_id),
    metric_name  VARCHAR(40)  NOT NULL CHECK (metric_name IN ('quality_score', 'nodata_percent', 'valid_fraction', 'speckle_index')),
    warn_below   NUMERIC,
    fail_below   NUMERIC,
    warn_above   NUMERIC,
    fail_above   NUMERIC,
    reference    VARCHAR(150),
    is_active    BOOLEAN      NOT NULL DEFAULT true,
    UNIQUE (band_id, metric_name),
    CHECK (fail_below IS NULL OR warn_below IS NULL OR fail_below <= warn_below),
    CHECK (fail_above IS NULL OR warn_above IS NULL OR fail_above >= warn_above)
);
COMMENT ON TABLE  quality_thresholds IS 'Ambang kontrol kualitas per band (menggantikan processing_rules). Dibaca module6_analytics; bobot skor 50/30/20 tetap konstanta kode.';
COMMENT ON COLUMN quality_thresholds.threshold_id IS 'PK surrogate.';
COMMENT ON COLUMN quality_thresholds.band_id      IS 'FK -> spectral_bands.';
COMMENT ON COLUMN quality_thresholds.metric_name  IS 'Metrik yang diuji: quality_score | nodata_percent | valid_fraction | speckle_index.';
COMMENT ON COLUMN quality_thresholds.warn_below   IS 'Nilai di bawah ini -> WARNING. NULL = tidak diuji.';
COMMENT ON COLUMN quality_thresholds.fail_below   IS 'Nilai di bawah ini -> FAIL. Contoh: quality_score 60.';
COMMENT ON COLUMN quality_thresholds.warn_above   IS 'Nilai di atas ini -> WARNING. NULL = tidak diuji.';
COMMENT ON COLUMN quality_thresholds.fail_above   IS 'Nilai di atas ini -> FAIL. NULL = tidak diuji.';
COMMENT ON COLUMN quality_thresholds.reference    IS 'Rujukan asal ambang.';
COMMENT ON COLUMN quality_thresholds.is_active    IS 'false = ambang tidak dipakai.';

-- M9 disaster_types -----------------------------------------------------------
CREATE TABLE disaster_types (
    disaster_type_id SMALLSERIAL  PRIMARY KEY,
    type_code        VARCHAR(30)  NOT NULL UNIQUE,
    type_name        VARCHAR(100) NOT NULL,
    category         VARCHAR(30)  NOT NULL DEFAULT 'HIDROMETEOROLOGI',
    indicator_bands  VARCHAR(100),
    is_active        BOOLEAN      NOT NULL DEFAULT true
);
COMMENT ON TABLE  disaster_types IS 'Master jenis bencana. ADMIN dapat menambah jenis tanpa ubah kode (uji adaptability).';
COMMENT ON COLUMN disaster_types.disaster_type_id IS 'PK surrogate.';
COMMENT ON COLUMN disaster_types.type_code        IS 'Alternate key: BANJIR | BANJIR_BANDANG | LONGSOR | KEKERINGAN.';
COMMENT ON COLUMN disaster_types.type_name        IS 'Label UI.';
COMMENT ON COLUMN disaster_types.category         IS 'Kelompok bencana, default HIDROMETEOROLOGI.';
COMMENT ON COLUMN disaster_types.indicator_bands  IS 'Teks informatif band indikator, mis. "RAIN_24H, VH".';
COMMENT ON COLUMN disaster_types.is_active        IS 'false = jenis tidak ditawarkan lagi di form.';

-- M10 alert_rules -------------------------------------------------------------
CREATE TABLE alert_rules (
    rule_id          SERIAL       PRIMARY KEY,
    rule_code        VARCHAR(40)  NOT NULL UNIQUE,
    disaster_type_id SMALLINT     NOT NULL REFERENCES disaster_types (disaster_type_id),
    band_id          SMALLINT     NOT NULL REFERENCES spectral_bands (band_id),
    comparator       VARCHAR(2)   NOT NULL CHECK (comparator IN ('>=', '>', '<=', '<')),
    threshold_value  NUMERIC(8,2),
    severity         VARCHAR(10)  NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL')),
    reference_source VARCHAR(150) NOT NULL,
    is_active        BOOLEAN      NOT NULL DEFAULT true,
    updated_by       INT          REFERENCES users (user_id),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    -- K7 (IMPLEMENTATION_NOTES): ambang longsor belum diketahui, jadi nilai
    -- boleh kosong selama aturannya nonaktif.
    CONSTRAINT chk_rule_active_needs_threshold CHECK (NOT is_active OR threshold_value IS NOT NULL)
);
CREATE INDEX idx_alert_rules_band ON alert_rules (band_id) WHERE is_active;
COMMENT ON TABLE  alert_rules IS 'Aturan alert hujan per jenis bencana (ambang BMKG; longsor nonaktif sampai ambang literatur diisi).';
COMMENT ON COLUMN alert_rules.rule_id          IS 'PK surrogate.';
COMMENT ON COLUMN alert_rules.rule_code        IS 'Alternate key, mis. FLOOD_RAIN24_HEAVY.';
COMMENT ON COLUMN alert_rules.disaster_type_id IS 'FK -> disaster_types.';
COMMENT ON COLUMN alert_rules.band_id          IS 'FK -> spectral_bands: band yang dibandingkan, mis. RAIN_24H.';
COMMENT ON COLUMN alert_rules.comparator       IS 'Operator pembanding nilai terhadap ambang: >= | > | <= | <.';
COMMENT ON COLUMN alert_rules.threshold_value  IS 'Ambang dalam satuan band (mm untuk hujan). Wajib terisi bila is_active (K7).';
COMMENT ON COLUMN alert_rules.severity         IS 'INFO | WARNING | CRITICAL.';
COMMENT ON COLUMN alert_rules.reference_source IS 'Rujukan ambang, mis. "BMKG (hujan lebat)".';
COMMENT ON COLUMN alert_rules.is_active        IS 'false = aturan tidak dievaluasi job hidromet.';
COMMENT ON COLUMN alert_rules.updated_by       IS 'FK -> users: ADMIN yang terakhir mengubah.';
COMMENT ON COLUMN alert_rules.updated_at       IS 'Waktu baris terakhir diubah (trigger).';

-- M11 fusion_strategies -------------------------------------------------------
CREATE TABLE fusion_strategies (
    strategy_id   SMALLSERIAL PRIMARY KEY,
    strategy_code VARCHAR(20) NOT NULL UNIQUE,
    download_axis TEXT        NOT NULL,
    assemble_axis TEXT        NOT NULL,
    description   TEXT
);
COMMENT ON TABLE  fusion_strategies IS 'Master strategi fusion (M9). Dirujuk datasets.fusion_strategy dan fusion_products.fusion_strategy lewat strategy_code.';
COMMENT ON COLUMN fusion_strategies.strategy_id   IS 'PK surrogate.';
COMMENT ON COLUMN fusion_strategies.strategy_code IS 'Alternate key: CO_OCCURRENCE | FULL_COVERAGE | HYBRID.';
COMMENT ON COLUMN fusion_strategies.download_axis IS 'Sumbu unduh: tanggal MODIS/GPM mana yang diambil.';
COMMENT ON COLUMN fusion_strategies.assemble_axis IS 'Sumbu rakit: tanggal mana yang menjadi satu berkas HDF5.';
COMMENT ON COLUMN fusion_strategies.description   IS 'Uraian strategi.';

-- M12 report_types ------------------------------------------------------------
CREATE TABLE report_types (
    report_type_id   SMALLSERIAL  PRIMARY KEY,
    report_code      VARCHAR(30)  NOT NULL UNIQUE,
    report_name      VARCHAR(100) NOT NULL,
    period           VARCHAR(10)  NOT NULL CHECK (period IN ('WEEKLY', 'MONTHLY')),
    audience_role_id SMALLINT     NOT NULL REFERENCES roles (role_id),
    template_version VARCHAR(10)  NOT NULL
);
COMMENT ON TABLE  report_types IS 'Master jenis laporan periodik (M18): Hidromet untuk ANALYST, Kesehatan Data untuk DATA_ENGINEER.';
COMMENT ON COLUMN report_types.report_type_id   IS 'PK surrogate.';
COMMENT ON COLUMN report_types.report_code      IS 'Alternate key: HYDROMET_WEEKLY | HYDROMET_MONTHLY | DATAHEALTH_WEEKLY | DATAHEALTH_MONTHLY.';
COMMENT ON COLUMN report_types.report_name      IS 'Label UI.';
COMMENT ON COLUMN report_types.period           IS 'WEEKLY | MONTHLY.';
COMMENT ON COLUMN report_types.audience_role_id IS 'FK -> roles: role audiens (dipakai RLS generated_reports).';
COMMENT ON COLUMN report_types.template_version IS 'Versi template PDF, mis. 1.0.';

-- app_settings (konfigurasi, bukan master) ------------------------------------
CREATE TABLE app_settings (
    setting_key   VARCHAR(50) PRIMARY KEY,
    setting_value JSONB       NOT NULL,
    description   TEXT,
    updated_by    INT         REFERENCES users (user_id),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE  app_settings IS 'Pengaturan key-value yang boleh diubah ADMIN tanpa restart (PIPELINE.md §11).';
COMMENT ON COLUMN app_settings.setting_key   IS 'PK: nama kunci bertitik, mis. live.max_areas.';
COMMENT ON COLUMN app_settings.setting_value IS 'Nilai JSON, mis. 5, -20, "Asia/Jakarta".';
COMMENT ON COLUMN app_settings.description   IS 'Penjelasan arti dan satuan nilai.';
COMMENT ON COLUMN app_settings.updated_by    IS 'FK -> users: ADMIN yang terakhir mengubah.';
COMMENT ON COLUMN app_settings.updated_at    IS 'Waktu baris terakhir diubah (trigger).';

-- =============================================================================
-- TABEL TRANSAKSI WARISAN (DATABASE.md §4.1)
-- =============================================================================

-- satellite_scenes [UBAH] -----------------------------------------------------
CREATE TABLE satellite_scenes (
    scene_id             SERIAL               PRIMARY KEY,
    scene_uuid           UUID                 NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    product_identifier   VARCHAR(200)         NOT NULL UNIQUE,
    platform             VARCHAR(20)          NOT NULL DEFAULT 'SENTINEL-1',
    instrument_mode      VARCHAR(10)          NOT NULL DEFAULT 'IW',
    polarization_vv      BOOLEAN              NOT NULL DEFAULT true,
    polarization_vh      BOOLEAN              NOT NULL DEFAULT true,
    acquisition_datetime TIMESTAMPTZ          NOT NULL,
    orbit_number         INTEGER,
    orbit_direction      orbit_direction_enum NOT NULL DEFAULT 'ASCENDING',
    relative_orbit       SMALLINT,
    bbox                 GEOMETRY(Polygon, 4326) NOT NULL,
    cloud_cover_percent  NUMERIC(5,2)         CHECK (cloud_cover_percent BETWEEN 0 AND 100),
    incidence_angle_near NUMERIC(6,3),
    incidence_angle_far  NUMERIC(6,3),
    resolution_m         SMALLINT             NOT NULL DEFAULT 10,
    region_id            INTEGER              NOT NULL REFERENCES regions_of_interest (region_id) ON DELETE RESTRICT,
    raw_file_path        TEXT,
    raw_file_size_mb     NUMERIC(12,3),
    download_url         TEXT,
    checksum_md5         VARCHAR(32),
    is_available         BOOLEAN              NOT NULL DEFAULT true,
    is_valid             BOOLEAN              NOT NULL DEFAULT true,
    invalidated_by       INT                  REFERENCES users (user_id),
    invalidated_at       TIMESTAMPTZ,
    invalid_reason       TEXT,
    created_at           TIMESTAMPTZ          NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ          NOT NULL DEFAULT now(),
    CONSTRAINT chk_scene_invalidation CHECK (is_valid OR (invalidated_at IS NOT NULL AND invalid_reason IS NOT NULL))
);
CREATE INDEX idx_scenes_acq_dt      ON satellite_scenes (acquisition_datetime DESC);
CREATE INDEX idx_scenes_bbox        ON satellite_scenes USING GIST (bbox);
CREATE INDEX idx_scenes_region_date ON satellite_scenes (region_id, acquisition_datetime DESC) WHERE is_available;
COMMENT ON TABLE  satellite_scenes IS 'Registri scene Sentinel-1 GRD yang ditemukan/diunduh. Soft delete ADMIN lewat is_valid (M24).';
COMMENT ON COLUMN satellite_scenes.scene_id             IS 'PK surrogate.';
COMMENT ON COLUMN satellite_scenes.scene_uuid           IS 'UUID stabil untuk referensi eksternal.';
COMMENT ON COLUMN satellite_scenes.product_identifier   IS 'Identifier produk ESA (unik global), mis. S1A_IW_GRDH_1SDV_..._B5C2.';
COMMENT ON COLUMN satellite_scenes.platform             IS 'Platform, default SENTINEL-1.';
COMMENT ON COLUMN satellite_scenes.instrument_mode      IS 'Mode akuisisi: IW (Interferometric Wide).';
COMMENT ON COLUMN satellite_scenes.polarization_vv      IS 'true bila produk memuat polarisasi VV.';
COMMENT ON COLUMN satellite_scenes.polarization_vh      IS 'true bila produk memuat polarisasi VH.';
COMMENT ON COLUMN satellite_scenes.acquisition_datetime IS 'Waktu akuisisi (UTC). Sumbu waktu utama.';
COMMENT ON COLUMN satellite_scenes.orbit_number         IS 'Nomor orbit absolut.';
COMMENT ON COLUMN satellite_scenes.orbit_direction      IS 'ASCENDING | DESCENDING.';
COMMENT ON COLUMN satellite_scenes.relative_orbit       IS 'Nomor orbit relatif (track); dipakai menandai perubahan air antar orbit berbeda.';
COMMENT ON COLUMN satellite_scenes.bbox                 IS 'Footprint scene (Polygon EPSG:4326). Keterbatasan warisan: belum akurat (D17).';
COMMENT ON COLUMN satellite_scenes.cloud_cover_percent  IS 'Persen awan (tidak relevan untuk SAR; warisan).';
COMMENT ON COLUMN satellite_scenes.incidence_angle_near IS 'Sudut datang near-range (derajat).';
COMMENT ON COLUMN satellite_scenes.incidence_angle_far  IS 'Sudut datang far-range (derajat).';
COMMENT ON COLUMN satellite_scenes.resolution_m         IS 'Resolusi piksel nominal (meter).';
COMMENT ON COLUMN satellite_scenes.region_id            IS 'FK -> regions_of_interest: ROI pencarian scene.';
COMMENT ON COLUMN satellite_scenes.raw_file_path        IS 'Path berkas unduhan asli (bisa sudah dihapus setelah diproses).';
COMMENT ON COLUMN satellite_scenes.raw_file_size_mb     IS 'Ukuran berkas unduhan (MB).';
COMMENT ON COLUMN satellite_scenes.download_url         IS 'URL unduhan CDSE.';
COMMENT ON COLUMN satellite_scenes.checksum_md5         IS 'Checksum MD5 dari penyedia.';
COMMENT ON COLUMN satellite_scenes.is_available         IS 'false = scene tidak tersedia lagi di penyedia/disk.';
COMMENT ON COLUMN satellite_scenes.is_valid             IS 'false = dinonaktifkan ADMIN (soft delete, M24).';
COMMENT ON COLUMN satellite_scenes.invalidated_by       IS 'FK -> users: ADMIN yang menonaktifkan.';
COMMENT ON COLUMN satellite_scenes.invalidated_at       IS 'Waktu dinonaktifkan.';
COMMENT ON COLUMN satellite_scenes.invalid_reason       IS 'Alasan wajib saat dinonaktifkan.';
COMMENT ON COLUMN satellite_scenes.created_at           IS 'Waktu baris dibuat.';
COMMENT ON COLUMN satellite_scenes.updated_at           IS 'Waktu baris terakhir diubah (trigger).';

-- nasa_scenes [UBAH] ----------------------------------------------------------
CREATE TABLE nasa_scenes (
    nasa_scene_id      BIGSERIAL    PRIMARY KEY,
    source             VARCHAR(20)  NOT NULL REFERENCES satellite_sources (source_code) ON UPDATE CASCADE,
    tile_id            VARCHAR(10)  NOT NULL,
    product_short_name VARCHAR(50)  NOT NULL,
    acquisition_date   DATE         NOT NULL,
    region_id          INTEGER      NOT NULL REFERENCES regions_of_interest (region_id) ON DELETE RESTRICT,
    raw_file_path      TEXT,
    download_url       TEXT,
    run_type           VARCHAR(5)   CHECK (run_type IN ('F', 'L', 'E')),
    is_available       BOOLEAN      NOT NULL DEFAULT true,
    is_valid           BOOLEAN      NOT NULL DEFAULT true,
    invalidated_by     INT          REFERENCES users (user_id),
    invalidated_at     TIMESTAMPTZ,
    invalid_reason     TEXT,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_nasa_scene UNIQUE (source, tile_id, product_short_name, acquisition_date),
    CONSTRAINT chk_nasa_invalidation CHECK (is_valid OR (invalidated_at IS NOT NULL AND invalid_reason IS NOT NULL))
);
CREATE INDEX idx_nasa_scenes_date ON nasa_scenes (acquisition_date DESC);
CREATE INDEX idx_nasa_scenes_source_date ON nasa_scenes (source, acquisition_date DESC);
COMMENT ON TABLE  nasa_scenes IS 'Registri granule MODIS dan GPM (satu baris per sumber/produk/tile/tanggal).';
COMMENT ON COLUMN nasa_scenes.nasa_scene_id      IS 'PK surrogate.';
COMMENT ON COLUMN nasa_scenes.source             IS 'FK -> satellite_sources.source_code: MODIS | GPM.';
COMMENT ON COLUMN nasa_scenes.tile_id            IS 'Tile MODIS (mis. MOSAIC dari h28v09) atau GLOBAL untuk GPM.';
COMMENT ON COLUMN nasa_scenes.product_short_name IS 'Short name produk NASA, mis. MCDWD_L3_F2_NRT, MOD09A1, GPM_3IMERGDF.';
COMMENT ON COLUMN nasa_scenes.acquisition_date   IS 'Tanggal data (hari UTC, M28). Untuk komposit MOD09A1: awal periode.';
COMMENT ON COLUMN nasa_scenes.region_id          IS 'FK -> regions_of_interest: ROI yang memicu unduhan.';
COMMENT ON COLUMN nasa_scenes.raw_file_path      IS 'Path berkas hasil (atau granule) di disk.';
COMMENT ON COLUMN nasa_scenes.download_url       IS 'URL granule di penyedia.';
COMMENT ON COLUMN nasa_scenes.run_type           IS 'GPM IMERG run: F (Final) | L (Late) | E (Early). NULL untuk MODIS (M6).';
COMMENT ON COLUMN nasa_scenes.is_available       IS 'false = granule tidak tersedia lagi.';
COMMENT ON COLUMN nasa_scenes.is_valid           IS 'false = dinonaktifkan ADMIN (soft delete, M24).';
COMMENT ON COLUMN nasa_scenes.invalidated_by     IS 'FK -> users: ADMIN yang menonaktifkan.';
COMMENT ON COLUMN nasa_scenes.invalidated_at     IS 'Waktu dinonaktifkan.';
COMMENT ON COLUMN nasa_scenes.invalid_reason     IS 'Alasan wajib saat dinonaktifkan.';
COMMENT ON COLUMN nasa_scenes.created_at         IS 'Waktu baris dibuat.';

-- datasets [UBAH] -------------------------------------------------------------
CREATE TABLE datasets (
    dataset_id              SERIAL        PRIMARY KEY,
    dataset_uuid            UUID          NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    name                    VARCHAR(255)  NOT NULL,
    description             TEXT,
    location_label          VARCHAR(255),
    region_id               INTEGER       REFERENCES regions_of_interest (region_id) ON DELETE SET NULL,
    bbox                    GEOMETRY(Polygon, 4326) NOT NULL,
    bbox_wkt                TEXT          NOT NULL,
    date_start              DATE          NOT NULL,
    date_end                DATE          NOT NULL,
    required_tiers          TEXT[]        NOT NULL DEFAULT ARRAY['COG']::TEXT[],
    fusion_strategy         VARCHAR(20)   DEFAULT 'FULL_COVERAGE'
                                          REFERENCES fusion_strategies (strategy_code) ON UPDATE CASCADE,
    preview_options         TEXT[]        NOT NULL DEFAULT ARRAY['GRAYSCALE', 'COLORED', 'COMPOSITE']::TEXT[],
    fusion_output_only      BOOLEAN       NOT NULL DEFAULT false,
    s1_match_tolerance_days SMALLINT      NOT NULL DEFAULT 2,
    quality_settings        JSONB         NOT NULL DEFAULT '{}',
    fusion_grid             JSONB,
    dataset_kind            VARCHAR(10)   NOT NULL DEFAULT 'STANDARD',
    is_system               BOOLEAN       NOT NULL DEFAULT false,
    status                  VARCHAR(20)   NOT NULL DEFAULT 'DRAFT',
    total_scenes            INTEGER       NOT NULL DEFAULT 0,
    completed_scenes        INTEGER       NOT NULL DEFAULT 0,
    failed_scenes           INTEGER       NOT NULL DEFAULT 0,
    total_size_bytes        BIGINT        NOT NULL DEFAULT 0,
    is_deletable            BOOLEAN       NOT NULL DEFAULT true,
    generate_preview        BOOLEAN       NOT NULL DEFAULT true,
    created_by              INT           REFERENCES users (user_id) ON DELETE SET NULL,
    created_at              TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ   NOT NULL DEFAULT now(),
    deleted_at              TIMESTAMPTZ,
    CONSTRAINT chk_dataset_kind CHECK (dataset_kind IN ('STANDARD', 'LIVE_AREA')),
    CONSTRAINT chk_dataset_status CHECK (status IN (
        'DRAFT', 'QUEUED', 'PREPARING', 'DOWNLOADING', 'PROCESSING', 'PAUSED',
        'CLEANUP', 'COMPLETED', 'FAILED', 'CANCELLED', 'DELETING', 'DELETED')),
    CONSTRAINT chk_required_tiers CHECK (
        required_tiers <@ ARRAY['RAW', 'ALIGNED', 'DESPECKLED', 'INDICES', 'ACCUMULATED', 'COG', 'FUSED']::TEXT[]
        AND array_length(required_tiers, 1) > 0),
    CONSTRAINT chk_dataset_date_range CHECK (date_end >= date_start),
    CONSTRAINT chk_datasets_s1_tolerance CHECK (s1_match_tolerance_days BETWEEN 0 AND 14),
    CONSTRAINT chk_preview_options CHECK (preview_options <@ ARRAY['GRAYSCALE', 'COLORED', 'COMPOSITE']::TEXT[])
);
CREATE INDEX idx_datasets_status     ON datasets (status) WHERE status <> 'DELETED';
CREATE INDEX idx_datasets_kind       ON datasets (dataset_kind);
CREATE INDEX idx_datasets_bbox       ON datasets USING GIST (bbox);
CREATE INDEX idx_datasets_created_at ON datasets (created_at DESC);
CREATE INDEX idx_datasets_created_by ON datasets (created_by);
COMMENT ON TABLE  datasets IS 'Dataset historis (Katalog, DATA_ENGINEER), dataset Live Area, dan dataset sistem HYDROMET_AOI.';
COMMENT ON COLUMN datasets.dataset_id              IS 'PK surrogate.';
COMMENT ON COLUMN datasets.dataset_uuid            IS 'UUID stabil untuk referensi eksternal.';
COMMENT ON COLUMN datasets.name                    IS 'Nama dataset; juga bagian nama folder data/datasets/{id}_{slug}.';
COMMENT ON COLUMN datasets.description             IS 'Keterangan bebas.';
COMMENT ON COLUMN datasets.location_label          IS 'Label lokasi saat dibuat (salinan nama ROI).';
COMMENT ON COLUMN datasets.region_id               IS 'FK -> regions_of_interest. Hanya ROI sistem (M27).';
COMMENT ON COLUMN datasets.bbox                    IS 'Bbox AOI dataset (Polygon EPSG:4326).';
COMMENT ON COLUMN datasets.bbox_wkt                IS 'Bbox yang sama dalam WKT, dipakai pipeline tanpa PostGIS.';
COMMENT ON COLUMN datasets.date_start              IS 'Awal rentang tanggal data (inklusif).';
COMMENT ON COLUMN datasets.date_end                IS 'Akhir rentang tanggal data (inklusif); maksimal 366 hari (app_settings.dataset.max_days).';
COMMENT ON COLUMN datasets.required_tiers          IS 'Tier D14 yang disimpan, diturunkan dari dataset_source_config (TEXT[] <= 7 elemen, M32). Contoh {RAW,ALIGNED,DESPECKLED,COG}.';
COMMENT ON COLUMN datasets.fusion_strategy         IS 'FK -> fusion_strategies.strategy_code. NULL = dataset satu sumber (tanpa fusi).';
COMMENT ON COLUMN datasets.preview_options         IS 'Varian PNG tahap PREVIEW: GRAYSCALE | COLORED | COMPOSITE. Array kosong = tanpa varian (M32).';
COMMENT ON COLUMN datasets.fusion_output_only      IS 'true = hapus artefak per-satelit setelah stack fusion tanggal itu ditulis.';
COMMENT ON COLUMN datasets.s1_match_tolerance_days IS 'FULL_COVERAGE: jarak hari maksimum meminjam scene S1 (0-14).';
COMMENT ON COLUMN datasets.quality_settings        IS 'Pengaturan kualitas (JSONB, M32), mis. {"min_cloud_cover": 20, "orbit_direction": "ASCENDING"}. Ambang skor kualitas TIDAK di sini: quality_thresholds (K15).';
COMMENT ON COLUMN datasets.fusion_grid             IS 'Grid fusion yang dipaku: {transform, width, height, crs, source_product_id, pinned_at}. NULL = belum pernah fusi.';
COMMENT ON COLUMN datasets.dataset_kind            IS 'STANDARD (Katalog / sistem) | LIVE_AREA (satu Live Area). LIVE lama dihapus.';
COMMENT ON COLUMN datasets.is_system               IS 'true = dataset sistem (HYDROMET_AOI) yang disembunyikan dari Katalog (PIPELINE.md §3.1).';
COMMENT ON COLUMN datasets.status                  IS 'Status siklus: DRAFT, QUEUED, PREPARING, DOWNLOADING, PROCESSING, PAUSED, CLEANUP, COMPLETED, FAILED, CANCELLED, DELETING, DELETED.';
COMMENT ON COLUMN datasets.total_scenes            IS 'Jumlah scene S1 yang ditemukan.';
COMMENT ON COLUMN datasets.completed_scenes        IS 'Jumlah scene S1 yang selesai diproses.';
COMMENT ON COLUMN datasets.failed_scenes           IS 'Jumlah scene S1 yang gagal.';
COMMENT ON COLUMN datasets.total_size_bytes        IS 'Total ukuran berkas dataset di disk (byte).';
COMMENT ON COLUMN datasets.is_deletable            IS 'false = tidak boleh dihapus lewat Katalog (mis. dataset Live Area).';
COMMENT ON COLUMN datasets.generate_preview        IS 'false = lewati tahap PREVIEW.';
COMMENT ON COLUMN datasets.created_by              IS 'FK -> users: pembuat dataset. NULL untuk dataset sistem.';
COMMENT ON COLUMN datasets.created_at              IS 'Waktu baris dibuat.';
COMMENT ON COLUMN datasets.updated_at              IS 'Waktu baris terakhir diubah (trigger).';
COMMENT ON COLUMN datasets.deleted_at              IS 'Waktu dataset dihapus (berkasnya dihapus, barisnya disimpan).';

-- dataset_source_config [UBAH] ------------------------------------------------
CREATE TABLE dataset_source_config (
    config_id         SERIAL       PRIMARY KEY,
    dataset_id        INTEGER      NOT NULL REFERENCES datasets (dataset_id) ON DELETE CASCADE,
    source_name       VARCHAR(20)  NOT NULL REFERENCES satellite_sources (source_code) ON UPDATE CASCADE,
    processing_levels TEXT[]       NOT NULL DEFAULT ARRAY['PROCESSED']::TEXT[],
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_source_config_dataset_source UNIQUE (dataset_id, source_name),
    CONSTRAINT chk_source_config_levels_not_empty CHECK (
        array_length(processing_levels, 1) IS NOT NULL AND array_length(processing_levels, 1) > 0),
    CONSTRAINT chk_source_config_levels_valid CHECK (processing_levels <@ ARRAY['RAW', 'PROCESSED']::TEXT[]),
    CONSTRAINT chk_source_config_source_name CHECK (source_name IN ('SENTINEL1', 'MODIS', 'GPM'))
);
CREATE INDEX idx_source_config_dataset ON dataset_source_config (dataset_id);
COMMENT ON TABLE  dataset_source_config IS 'Konfigurasi pemrosesan per (dataset, sumber). ETL membaca tabel ini untuk memutuskan sumber dan level yang dijalankan.';
COMMENT ON COLUMN dataset_source_config.config_id         IS 'PK surrogate.';
COMMENT ON COLUMN dataset_source_config.dataset_id        IS 'FK -> datasets.';
COMMENT ON COLUMN dataset_source_config.source_name       IS 'FK -> satellite_sources.source_code: SENTINEL1 | MODIS | GPM.';
COMMENT ON COLUMN dataset_source_config.processing_levels IS 'Level yang diminta: {RAW}, {PROCESSED}, atau {RAW,PROCESSED} (TEXT[] <= 2 elemen, M32).';
COMMENT ON COLUMN dataset_source_config.created_at        IS 'Waktu baris dibuat.';
COMMENT ON COLUMN dataset_source_config.updated_at        IS 'Waktu baris terakhir diubah (trigger).';

-- dataset_jobs [WARIS] --------------------------------------------------------
CREATE TABLE dataset_jobs (
    job_id           BIGSERIAL    PRIMARY KEY,
    job_uuid         UUID         NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    dataset_id       INTEGER      NOT NULL REFERENCES datasets (dataset_id) ON DELETE CASCADE,
    job_type         VARCHAR(20)  NOT NULL DEFAULT 'CREATE',
    status           VARCHAR(20)  NOT NULL DEFAULT 'QUEUED',
    paused_at        TIMESTAMPTZ,
    paused_by        VARCHAR(20),
    pause_reason     TEXT,
    resumed_at       TIMESTAMPTZ,
    resume_count     SMALLINT     NOT NULL DEFAULT 0,
    date_range_start DATE,
    date_range_end   DATE,
    total_scenes     INTEGER      NOT NULL DEFAULT 0,
    downloaded_count INTEGER      NOT NULL DEFAULT 0,
    processed_count  INTEGER      NOT NULL DEFAULT 0,
    failed_count     INTEGER      NOT NULL DEFAULT 0,
    cleaned_count    INTEGER      NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    CONSTRAINT chk_dataset_job_type CHECK (job_type IN ('CREATE', 'BACKFILL', 'LIVE_INGEST', 'HYDROMET_DAILY')),
    CONSTRAINT chk_dataset_job_status CHECK (status IN (
        'QUEUED', 'PREPARING', 'DOWNLOADING', 'PROCESSING', 'PAUSED',
        'CLEANUP', 'COMPLETED', 'FAILED', 'CANCELLED', 'WAITING_UPSTREAM'))
);
CREATE INDEX idx_dataset_jobs_dataset ON dataset_jobs (dataset_id, created_at DESC);
CREATE INDEX idx_dataset_jobs_status  ON dataset_jobs (status);
COMMENT ON TABLE  dataset_jobs IS 'Satu eksekusi pekerjaan atas sebuah dataset (buat, backfill, siklus Live, hidromet harian).';
COMMENT ON COLUMN dataset_jobs.job_id           IS 'PK surrogate.';
COMMENT ON COLUMN dataset_jobs.job_uuid         IS 'UUID stabil untuk referensi eksternal.';
COMMENT ON COLUMN dataset_jobs.dataset_id       IS 'FK -> datasets.';
COMMENT ON COLUMN dataset_jobs.job_type         IS 'CREATE | BACKFILL | LIVE_INGEST (siklus Live Area) | HYDROMET_DAILY (job A).';
COMMENT ON COLUMN dataset_jobs.status           IS 'QUEUED, PREPARING, DOWNLOADING, PROCESSING, PAUSED, CLEANUP, COMPLETED, FAILED, CANCELLED, WAITING_UPSTREAM (hidromet: granule GPM hari itu belum terbit, dicoba lagi maks. 3 hari).';
COMMENT ON COLUMN dataset_jobs.paused_at        IS 'Waktu job dijeda.';
COMMENT ON COLUMN dataset_jobs.paused_by        IS 'Penjeda: user | system.';
COMMENT ON COLUMN dataset_jobs.pause_reason     IS 'Alasan jeda.';
COMMENT ON COLUMN dataset_jobs.resumed_at       IS 'Waktu terakhir dilanjutkan.';
COMMENT ON COLUMN dataset_jobs.resume_count     IS 'Berapa kali job dilanjutkan.';
COMMENT ON COLUMN dataset_jobs.date_range_start IS 'Awal rentang tanggal yang dikerjakan job ini.';
COMMENT ON COLUMN dataset_jobs.date_range_end   IS 'Akhir rentang tanggal yang dikerjakan job ini.';
COMMENT ON COLUMN dataset_jobs.total_scenes     IS 'Jumlah unit (scene S1) yang dikerjakan.';
COMMENT ON COLUMN dataset_jobs.downloaded_count IS 'Unit yang selesai diunduh.';
COMMENT ON COLUMN dataset_jobs.processed_count  IS 'Unit yang selesai diproses.';
COMMENT ON COLUMN dataset_jobs.failed_count     IS 'Unit yang gagal.';
COMMENT ON COLUMN dataset_jobs.cleaned_count    IS 'Unit yang selesai dibersihkan (tahap CLEANUP).';
COMMENT ON COLUMN dataset_jobs.created_at       IS 'Waktu job dibuat.';
COMMENT ON COLUMN dataset_jobs.started_at       IS 'Waktu job mulai berjalan.';
COMMENT ON COLUMN dataset_jobs.completed_at     IS 'Waktu job selesai (berhasil atau gagal).';

-- scene_job_state [WARIS] -----------------------------------------------------
CREATE TABLE scene_job_state (
    id                 BIGSERIAL    PRIMARY KEY,
    job_id             BIGINT       NOT NULL REFERENCES dataset_jobs (job_id) ON DELETE CASCADE,
    product_identifier VARCHAR(200) NOT NULL,
    scene_id           INTEGER      REFERENCES satellite_scenes (scene_id) ON DELETE SET NULL,
    current_stage      VARCHAR(30),
    stage_status       VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
    produced_files     JSONB        NOT NULL DEFAULT '{}',
    attempt_number     SMALLINT     NOT NULL DEFAULT 1,
    max_retries        SMALLINT     NOT NULL DEFAULT 3,
    last_error         TEXT,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    started_at         TIMESTAMPTZ,
    completed_at       TIMESTAMPTZ,
    CONSTRAINT uq_job_product UNIQUE (job_id, product_identifier),
    CONSTRAINT chk_scene_job_stage_status CHECK (stage_status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'SKIPPED'))
);
CREATE INDEX idx_scene_job_state_job          ON scene_job_state (job_id);
CREATE INDEX idx_scene_job_state_stage_status ON scene_job_state (stage_status);
CREATE INDEX idx_scene_job_state_scene_id     ON scene_job_state (scene_id) WHERE scene_id IS NOT NULL;
COMMENT ON TABLE  scene_job_state IS 'Status per scene S1 di dalam satu dataset_job; dasar resume setelah proses mati.';
COMMENT ON COLUMN scene_job_state.id                 IS 'PK surrogate.';
COMMENT ON COLUMN scene_job_state.job_id             IS 'FK -> dataset_jobs.';
COMMENT ON COLUMN scene_job_state.product_identifier IS 'Identifier produk ESA scene ini.';
COMMENT ON COLUMN scene_job_state.scene_id           IS 'FK -> satellite_scenes; NULL sebelum scene terdaftar.';
COMMENT ON COLUMN scene_job_state.current_stage      IS 'Tahap terakhir yang dicapai, mis. LEE_FILTER, CLEANUP.';
COMMENT ON COLUMN scene_job_state.stage_status       IS 'PENDING | RUNNING | COMPLETED | FAILED | SKIPPED.';
COMMENT ON COLUMN scene_job_state.produced_files     IS 'Berkas yang dihasilkan per tier (JSONB {tier: [path]}), untuk cleanup.';
COMMENT ON COLUMN scene_job_state.attempt_number     IS 'Percobaan ke berapa.';
COMMENT ON COLUMN scene_job_state.max_retries        IS 'Batas percobaan ulang.';
COMMENT ON COLUMN scene_job_state.last_error         IS 'Pesan galat terakhir.';
COMMENT ON COLUMN scene_job_state.created_at         IS 'Waktu baris dibuat.';
COMMENT ON COLUMN scene_job_state.started_at         IS 'Waktu mulai diproses.';
COMMENT ON COLUMN scene_job_state.completed_at       IS 'Waktu selesai.';

-- cleanup_operations [WARIS] --------------------------------------------------
CREATE TABLE cleanup_operations (
    id             BIGSERIAL    PRIMARY KEY,
    dataset_id     INTEGER      NOT NULL,
    job_id         BIGINT       REFERENCES dataset_jobs (job_id) ON DELETE SET NULL,
    operation_type VARCHAR(20)  NOT NULL CHECK (operation_type IN ('TIER_CLEANUP', 'FULL_DELETE')),
    status         VARCHAR(20)  NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED')),
    total_files    INTEGER      NOT NULL DEFAULT 0,
    deleted_count  INTEGER      NOT NULL DEFAULT 0,
    freed_bytes    BIGINT       NOT NULL DEFAULT 0,
    error_log      TEXT,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    started_at     TIMESTAMPTZ,
    completed_at   TIMESTAMPTZ
);
CREATE INDEX idx_cleanup_ops_dataset ON cleanup_operations (dataset_id, created_at DESC);
CREATE INDEX idx_cleanup_ops_status  ON cleanup_operations (status);
COMMENT ON TABLE  cleanup_operations IS 'Progres penghapusan berkas per dataset (cleanup tier akhir job atau hapus dataset). Sengaja tanpa FK ke datasets agar progres tetap terbaca setelah dataset dihapus.';
COMMENT ON COLUMN cleanup_operations.id             IS 'PK surrogate.';
COMMENT ON COLUMN cleanup_operations.dataset_id     IS 'Dataset yang dibersihkan (tanpa FK, lihat komentar tabel).';
COMMENT ON COLUMN cleanup_operations.job_id         IS 'FK -> dataset_jobs yang memicu cleanup.';
COMMENT ON COLUMN cleanup_operations.operation_type IS 'TIER_CLEANUP | FULL_DELETE.';
COMMENT ON COLUMN cleanup_operations.status         IS 'PENDING | IN_PROGRESS | COMPLETED | FAILED.';
COMMENT ON COLUMN cleanup_operations.total_files    IS 'Jumlah berkas yang akan dihapus.';
COMMENT ON COLUMN cleanup_operations.deleted_count  IS 'Jumlah berkas yang sudah dihapus.';
COMMENT ON COLUMN cleanup_operations.freed_bytes    IS 'Ruang disk yang dibebaskan (byte).';
COMMENT ON COLUMN cleanup_operations.error_log      IS 'Galat selama penghapusan.';
COMMENT ON COLUMN cleanup_operations.created_at     IS 'Waktu baris dibuat.';
COMMENT ON COLUMN cleanup_operations.started_at     IS 'Waktu mulai.';
COMMENT ON COLUMN cleanup_operations.completed_at   IS 'Waktu selesai.';

-- processing_jobs [UBAH] ------------------------------------------------------
CREATE TABLE processing_jobs (
    job_id            BIGSERIAL       PRIMARY KEY,
    job_uuid          UUID            NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    scene_id          INTEGER         REFERENCES satellite_scenes (scene_id) ON DELETE CASCADE,
    nasa_scene_id     BIGINT          REFERENCES nasa_scenes (nasa_scene_id) ON DELETE CASCADE,
    stage_id          INTEGER         NOT NULL REFERENCES processing_stages (stage_id) ON DELETE RESTRICT,
    attempt_number    SMALLINT        NOT NULL DEFAULT 1,
    status            job_status_enum NOT NULL DEFAULT 'QUEUED',
    queued_at         TIMESTAMPTZ     NOT NULL DEFAULT now(),
    started_at        TIMESTAMPTZ,
    completed_at      TIMESTAMPTZ,
    duration_seconds  NUMERIC(10,3)   GENERATED ALWAYS AS (EXTRACT(EPOCH FROM (completed_at - started_at))) STORED,
    worker_hostname   VARCHAR(100),
    cpu_usage_percent NUMERIC(7,2),
    memory_usage_mb   NUMERIC(10,2),
    input_size_mb     NUMERIC(12,3),
    output_size_mb    NUMERIC(12,3),
    error_code        VARCHAR(50),
    error_message     TEXT,
    log_file_path     TEXT,
    parameters_json   JSONB           NOT NULL DEFAULT '{}',
    created_at        TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ     NOT NULL DEFAULT now(),
    CONSTRAINT uq_job_scene_stage_attempt UNIQUE (scene_id, stage_id, attempt_number),
    -- M30/K2: job menempel pada scene S1 ATAU granule NASA, atau tidak pada
    -- keduanya (FUSION, tahap lintas sumber) -- tidak pernah pada keduanya.
    CONSTRAINT chk_pjobs_single_anchor CHECK (scene_id IS NULL OR nasa_scene_id IS NULL)
);
CREATE UNIQUE INDEX uq_job_nasa_stage_attempt ON processing_jobs (nasa_scene_id, stage_id, attempt_number)
    WHERE nasa_scene_id IS NOT NULL;
CREATE INDEX idx_pjobs_scene_id   ON processing_jobs (scene_id) WHERE scene_id IS NOT NULL;
CREATE INDEX idx_pjobs_stage_id   ON processing_jobs (stage_id);
CREATE INDEX idx_pjobs_status     ON processing_jobs (status, queued_at DESC);
CREATE INDEX idx_pjobs_queued_at  ON processing_jobs (queued_at DESC);
CREATE INDEX idx_pjobs_params_gin ON processing_jobs USING GIN (parameters_json);
COMMENT ON TABLE  processing_jobs IS 'Eksekusi satu tahap pipeline (scene/granule x tahap x percobaan). Jangkar: scene S1, granule NASA, atau tidak keduanya untuk FUSION (M30).';
COMMENT ON COLUMN processing_jobs.job_id            IS 'PK surrogate.';
COMMENT ON COLUMN processing_jobs.job_uuid          IS 'UUID stabil untuk referensi eksternal.';
COMMENT ON COLUMN processing_jobs.scene_id          IS 'FK -> satellite_scenes: scene S1 yang diproses. NULL untuk job MODIS/GPM/FUSION.';
COMMENT ON COLUMN processing_jobs.nasa_scene_id     IS 'FK -> nasa_scenes: granule MODIS/GPM yang diproses. NULL untuk job S1/FUSION (M30).';
COMMENT ON COLUMN processing_jobs.stage_id          IS 'FK -> processing_stages.';
COMMENT ON COLUMN processing_jobs.attempt_number    IS 'Percobaan ke berapa untuk (scene, tahap).';
COMMENT ON COLUMN processing_jobs.status            IS 'QUEUED | RUNNING | SUCCESS | FAILED | CANCELLED | WAITING_UPSTREAM (granule hulu belum terbit) | SKIPPED_LOCKED (run scheduler dilewati: advisory lock dipegang worker lain).';
COMMENT ON COLUMN processing_jobs.queued_at         IS 'Waktu masuk antrean.';
COMMENT ON COLUMN processing_jobs.started_at        IS 'Waktu mulai.';
COMMENT ON COLUMN processing_jobs.completed_at      IS 'Waktu selesai.';
COMMENT ON COLUMN processing_jobs.duration_seconds  IS 'Durasi (detik), GENERATED dari completed_at - started_at.';
COMMENT ON COLUMN processing_jobs.worker_hostname   IS 'Host yang menjalankan tahap.';
COMMENT ON COLUMN processing_jobs.cpu_usage_percent IS 'Pemakaian CPU total seluruh core (24 core = sampai 2400%).';
COMMENT ON COLUMN processing_jobs.memory_usage_mb   IS 'Pemakaian memori puncak (MB).';
COMMENT ON COLUMN processing_jobs.input_size_mb     IS 'Ukuran input (MB).';
COMMENT ON COLUMN processing_jobs.output_size_mb    IS 'Ukuran output (MB).';
COMMENT ON COLUMN processing_jobs.error_code        IS 'Kode galat (nama exception), mis. MemoryError.';
COMMENT ON COLUMN processing_jobs.error_message     IS 'Pesan galat.';
COMMENT ON COLUMN processing_jobs.log_file_path     IS 'Path berkas log tahap.';
COMMENT ON COLUMN processing_jobs.parameters_json   IS 'Parameter reproduksibilitas (JSONB, M32): versi software, window Lee, run GPM, ambang. Nama "parameters" di DATABASE.md §4.1 (K8).';
COMMENT ON COLUMN processing_jobs.created_at        IS 'Waktu baris dibuat.';
COMMENT ON COLUMN processing_jobs.updated_at        IS 'Waktu baris terakhir diubah (trigger).';

-- processing_logs [WARIS] -----------------------------------------------------
CREATE TABLE processing_logs (
    log_id     BIGSERIAL    PRIMARY KEY,
    log_uuid   UUID         NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    dataset_id INTEGER      NOT NULL REFERENCES datasets (dataset_id) ON DELETE CASCADE,
    scene_id   VARCHAR(255) NOT NULL,
    module     VARCHAR(50)  NOT NULL,
    stage      VARCHAR(50)  NOT NULL,
    status     VARCHAR(20)  NOT NULL,
    message    TEXT         NOT NULL,
    details    JSONB        NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_processing_logs_dataset_created ON processing_logs (dataset_id, created_at DESC);
CREATE INDEX idx_processing_logs_dataset_scene   ON processing_logs (dataset_id, scene_id, created_at DESC);
CREATE INDEX idx_processing_logs_stage_status    ON processing_logs (stage, status);
COMMENT ON TABLE  processing_logs IS 'Log pipeline terstruktur append-only: satu baris per kejadian tahap (STARTED/RUNNING/COMPLETED/FAILED).';
COMMENT ON COLUMN processing_logs.log_id     IS 'PK surrogate.';
COMMENT ON COLUMN processing_logs.log_uuid   IS 'UUID stabil untuk referensi eksternal.';
COMMENT ON COLUMN processing_logs.dataset_id IS 'FK -> datasets.';
COMMENT ON COLUMN processing_logs.scene_id   IS 'Kunci unit kerja sebagai teks (product identifier S1 atau tanggal aux), bukan FK.';
COMMENT ON COLUMN processing_logs.module     IS 'Modul ETL penulis log, mis. M5_ORCH.';
COMMENT ON COLUMN processing_logs.stage      IS 'Nama tahap, mis. DOWNLOAD, FUSION.';
COMMENT ON COLUMN processing_logs.status     IS 'STARTED | RUNNING | COMPLETED | FAILED | SKIPPED.';
COMMENT ON COLUMN processing_logs.message    IS 'Pesan log (Bahasa Inggris, M21).';
COMMENT ON COLUMN processing_logs.details    IS 'Detail terstruktur (durasi, ukuran, memori, kualitas) dalam JSONB.';
COMMENT ON COLUMN processing_logs.created_at IS 'Waktu kejadian.';

-- data_products [UBAH] --------------------------------------------------------
CREATE TABLE data_products (
    product_id       BIGSERIAL             PRIMARY KEY,
    product_uuid     UUID                  NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    scene_id         INTEGER               REFERENCES satellite_scenes (scene_id) ON DELETE CASCADE,
    nasa_scene_id    BIGINT                REFERENCES nasa_scenes (nasa_scene_id) ON DELETE CASCADE,
    job_id           BIGINT                NOT NULL REFERENCES processing_jobs (job_id) ON DELETE RESTRICT,
    dataset_id       INTEGER               REFERENCES datasets (dataset_id) ON DELETE CASCADE,
    product_tier     product_tier_enum     NOT NULL,
    source           VARCHAR(20)           NOT NULL DEFAULT 'SENTINEL1'
                                           REFERENCES satellite_sources (source_code) ON UPDATE CASCADE,
    processing_level VARCHAR(20)           DEFAULT 'PROCESSED',
    product_type     VARCHAR(50)           NOT NULL,
    band_name        VARCHAR(20)           NOT NULL,
    file_name        VARCHAR(255)          NOT NULL,
    file_path        TEXT                  NOT NULL,
    file_size_mb     NUMERIC(12,3)         NOT NULL,
    file_format      VARCHAR(20)           NOT NULL DEFAULT 'TIFF',
    data_hash_sha256 VARCHAR(64)           NOT NULL,
    crs              VARCHAR(50)           NOT NULL DEFAULT 'EPSG:4326',
    pixel_size_m     NUMERIC(8,3),
    nodata_value     NUMERIC,
    rows             INTEGER,
    cols             INTEGER,
    band_count       SMALLINT              NOT NULL DEFAULT 1,
    storage_location storage_location_enum NOT NULL DEFAULT 'LOCAL',
    is_valid         BOOLEAN               NOT NULL DEFAULT true,
    is_latest        BOOLEAN               NOT NULL DEFAULT true,
    created_at       TIMESTAMPTZ           NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ           NOT NULL DEFAULT now(),
    CONSTRAINT chk_dprods_processing_level CHECK (processing_level IS NULL OR processing_level IN ('RAW', 'PROCESSED')),
    -- M30: tepat satu sumber asal untuk produk satu sumber; FUSION tanpa
    -- keduanya (asal-usulnya di fusion_products + data_lineage).
    CONSTRAINT chk_dprods_single_origin CHECK (
           (source = 'SENTINEL1'       AND scene_id IS NOT NULL AND nasa_scene_id IS NULL)
        OR (source IN ('MODIS', 'GPM') AND scene_id IS NULL     AND nasa_scene_id IS NOT NULL)
        OR (source = 'FUSION'          AND scene_id IS NULL     AND nasa_scene_id IS NULL))
);
CREATE INDEX idx_dprods_scene_id            ON data_products (scene_id);
CREATE INDEX idx_dprods_nasa_scene_id       ON data_products (nasa_scene_id) WHERE nasa_scene_id IS NOT NULL;
CREATE INDEX idx_dprods_job_id              ON data_products (job_id);
CREATE INDEX idx_dprods_hash                ON data_products (data_hash_sha256);
CREATE INDEX idx_dprods_latest              ON data_products (is_latest, product_tier) WHERE is_latest;
CREATE INDEX idx_dprods_created_at          ON data_products (created_at DESC);
CREATE INDEX idx_dprods_tier_source         ON data_products (product_tier, source);
CREATE INDEX idx_dprods_dataset_tier        ON data_products (dataset_id, product_tier);
CREATE INDEX idx_dprods_dataset_tier_source ON data_products (dataset_id, product_tier, source) WHERE is_latest;
CREATE INDEX idx_dprods_dataset_level       ON data_products (dataset_id, processing_level);
CREATE INDEX idx_dprods_scene_band_tier     ON data_products (scene_id, band_name, product_tier, created_at DESC) WHERE is_latest AND is_valid;
COMMENT ON TABLE  data_products IS 'Registri setiap berkas keluaran pipeline (COG, TIFF, HDF5) dengan checksum SHA-256.';
COMMENT ON COLUMN data_products.product_id       IS 'PK surrogate.';
COMMENT ON COLUMN data_products.product_uuid     IS 'UUID stabil untuk referensi eksternal.';
COMMENT ON COLUMN data_products.scene_id         IS 'FK -> satellite_scenes: scene S1 asal. Terisi hanya untuk source SENTINEL1 (chk_dprods_single_origin).';
COMMENT ON COLUMN data_products.nasa_scene_id    IS 'FK -> nasa_scenes: granule MODIS/GPM asal. Terisi hanya untuk source MODIS/GPM; FUSION keduanya NULL (M30).';
COMMENT ON COLUMN data_products.job_id           IS 'FK -> processing_jobs: eksekusi tahap yang menulis berkas ini.';
COMMENT ON COLUMN data_products.dataset_id       IS 'FK -> datasets: dataset pemilik berkas.';
COMMENT ON COLUMN data_products.product_tier     IS 'Posisi di lineage (D14): RAW | ALIGNED | DESPECKLED | INDICES | ACCUMULATED | COG | FUSED.';
COMMENT ON COLUMN data_products.source           IS 'FK -> satellite_sources.source_code: SENTINEL1 | MODIS | GPM | FUSION.';
COMMENT ON COLUMN data_products.processing_level IS 'Level konfigurasi yang menghasilkan berkas: RAW | PROCESSED (beda dari product_tier).';
COMMENT ON COLUMN data_products.product_type     IS 'Jenis artefak, mis. S1_COG, MODIS_FLOOD, GPM_RAINFALL, FUSION_H5.';
COMMENT ON COLUMN data_products.band_name        IS 'Band/lapisan, mis. VV, NDVI, RAIN_24H, FUSION_PROCESSED.';
COMMENT ON COLUMN data_products.file_name        IS 'Nama berkas.';
COMMENT ON COLUMN data_products.file_path        IS 'Path berkas di filesystem data/ (raster tidak disimpan di DB).';
COMMENT ON COLUMN data_products.file_size_mb     IS 'Ukuran berkas (MB).';
COMMENT ON COLUMN data_products.file_format      IS 'Format: TIFF | COG | HDF5.';
COMMENT ON COLUMN data_products.data_hash_sha256 IS 'SHA-256 isi berkas (64 hex) untuk lineage dan verifikasi arsip (RM2).';
COMMENT ON COLUMN data_products.crs              IS 'Sistem koordinat, mis. EPSG:4326.';
COMMENT ON COLUMN data_products.pixel_size_m     IS 'Ukuran piksel (meter).';
COMMENT ON COLUMN data_products.nodata_value     IS 'Nilai NoData raster.';
COMMENT ON COLUMN data_products.rows             IS 'Jumlah baris piksel.';
COMMENT ON COLUMN data_products.cols             IS 'Jumlah kolom piksel.';
COMMENT ON COLUMN data_products.band_count       IS 'Jumlah band dalam berkas.';
COMMENT ON COLUMN data_products.storage_location IS 'Lokasi penyimpanan, selalu LOCAL di Monitor.';
COMMENT ON COLUMN data_products.is_valid         IS 'false = berkas dinyatakan tidak sah/dihapus.';
COMMENT ON COLUMN data_products.is_latest        IS 'true = versi terbaru untuk kunci dedup (COALESCE(scene_id,0), COALESCE(nasa_scene_id,0), band, tier, dataset); FUSION didedup per file_path (K3).';
COMMENT ON COLUMN data_products.created_at       IS 'Waktu baris dibuat.';
COMMENT ON COLUMN data_products.updated_at       IS 'Waktu baris terakhir diubah (trigger).';

-- data_lineage [WARIS] --------------------------------------------------------
CREATE TABLE data_lineage (
    lineage_id            BIGSERIAL    PRIMARY KEY,
    parent_product_id     BIGINT       NOT NULL REFERENCES data_products (product_id) ON DELETE CASCADE,
    child_product_id      BIGINT       NOT NULL REFERENCES data_products (product_id) ON DELETE CASCADE,
    transformation_type   VARCHAR(50)  NOT NULL,
    stage_id              INTEGER      NOT NULL REFERENCES processing_stages (stage_id) ON DELETE RESTRICT,
    job_id                BIGINT       NOT NULL REFERENCES processing_jobs (job_id) ON DELETE RESTRICT,
    transformation_params JSONB        NOT NULL DEFAULT '{}',
    input_checksum        VARCHAR(64),
    output_checksum       VARCHAR(64),
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_lineage_parent_child UNIQUE (parent_product_id, child_product_id),
    CONSTRAINT chk_lineage_no_self_ref CHECK (parent_product_id <> child_product_id)
);
CREATE INDEX idx_lineage_parent_id  ON data_lineage (parent_product_id);
CREATE INDEX idx_lineage_child_id   ON data_lineage (child_product_id);
CREATE INDEX idx_lineage_transform  ON data_lineage (transformation_type, created_at DESC);
CREATE INDEX idx_lineage_job_id     ON data_lineage (job_id);
CREATE INDEX idx_lineage_stage_id   ON data_lineage (stage_id);
COMMENT ON TABLE  data_lineage IS 'Graf asiklik (DAG) transformasi produk: induk -> anak dengan checksum input/output (RM2).';
COMMENT ON COLUMN data_lineage.lineage_id            IS 'PK surrogate.';
COMMENT ON COLUMN data_lineage.parent_product_id     IS 'FK -> data_products: produk input.';
COMMENT ON COLUMN data_lineage.child_product_id      IS 'FK -> data_products: produk output.';
COMMENT ON COLUMN data_lineage.transformation_type   IS 'Jenis transformasi, mis. CROP, LEE_FILTER, GOLD_EXPORT, FUSION.';
COMMENT ON COLUMN data_lineage.stage_id              IS 'FK -> processing_stages.';
COMMENT ON COLUMN data_lineage.job_id                IS 'FK -> processing_jobs: eksekusi yang melakukan transformasi.';
COMMENT ON COLUMN data_lineage.transformation_params IS 'Parameter transformasi (JSONB): bbox crop, window Lee, kompresi COG.';
COMMENT ON COLUMN data_lineage.input_checksum        IS 'SHA-256 induk saat transformasi.';
COMMENT ON COLUMN data_lineage.output_checksum       IS 'SHA-256 anak setelah transformasi.';
COMMENT ON COLUMN data_lineage.created_at            IS 'Waktu baris dibuat.';

-- quality_metrics [WARIS] -----------------------------------------------------
CREATE TABLE quality_metrics (
    metric_id               BIGSERIAL    PRIMARY KEY,
    scene_id                INTEGER      NOT NULL REFERENCES satellite_scenes (scene_id) ON DELETE CASCADE,
    product_id              BIGINT       NOT NULL REFERENCES data_products (product_id) ON DELETE CASCADE,
    band_name               VARCHAR(10)  NOT NULL,
    assessed_at             TIMESTAMPTZ  NOT NULL DEFAULT now(),
    total_pixels            BIGINT       NOT NULL,
    valid_pixels            BIGINT       NOT NULL,
    nodata_pixels           BIGINT       NOT NULL DEFAULT 0,
    nodata_percent          NUMERIC(5,2) GENERATED ALWAYS AS (
                                CASE WHEN total_pixels > 0
                                     THEN round((nodata_pixels::numeric / total_pixels) * 100, 2)
                                     ELSE 0 END) STORED,
    backscatter_mean_db     NUMERIC(8,4),
    backscatter_std_db      NUMERIC(8,4),
    backscatter_min_db      NUMERIC(8,4),
    backscatter_max_db      NUMERIC(8,4),
    cloud_threshold_percent NUMERIC(5,2) NOT NULL DEFAULT 20.0,
    radiometric_consistency BOOLEAN,
    speckle_index           NUMERIC(8,4),
    quality_score           NUMERIC(5,2) NOT NULL CONSTRAINT chk_quality_score_range CHECK (quality_score BETWEEN 0 AND 100),
    quality_flag            VARCHAR(20)  NOT NULL DEFAULT 'UNCHECKED' CHECK (quality_flag IN ('PASS', 'WARNING', 'FAIL', 'UNCHECKED')),
    notes                   TEXT,
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_quality_scene_product_band UNIQUE (scene_id, product_id, band_name)
);
CREATE INDEX idx_qmetrics_scene_id     ON quality_metrics (scene_id);
CREATE INDEX idx_qmetrics_product_id   ON quality_metrics (product_id);
CREATE INDEX idx_qmetrics_quality_flag ON quality_metrics (quality_flag, assessed_at DESC);
CREATE INDEX idx_qmetrics_assessed_at  ON quality_metrics (assessed_at DESC);
COMMENT ON TABLE  quality_metrics IS 'Hasil kontrol kualitas radiometrik per scene S1 per band (tahap QUALITY_ANALYTICS).';
COMMENT ON COLUMN quality_metrics.metric_id               IS 'PK surrogate.';
COMMENT ON COLUMN quality_metrics.scene_id                IS 'FK -> satellite_scenes.';
COMMENT ON COLUMN quality_metrics.product_id              IS 'FK -> data_products: COG yang dinilai.';
COMMENT ON COLUMN quality_metrics.band_name               IS 'VV | VH.';
COMMENT ON COLUMN quality_metrics.assessed_at             IS 'Waktu penilaian.';
COMMENT ON COLUMN quality_metrics.total_pixels            IS 'Jumlah piksel raster.';
COMMENT ON COLUMN quality_metrics.valid_pixels            IS 'Jumlah piksel bernilai sah.';
COMMENT ON COLUMN quality_metrics.nodata_pixels           IS 'Jumlah piksel NoData.';
COMMENT ON COLUMN quality_metrics.nodata_percent          IS 'Persen NoData (%), GENERATED.';
COMMENT ON COLUMN quality_metrics.backscatter_mean_db     IS 'Rata-rata backscatter (dB).';
COMMENT ON COLUMN quality_metrics.backscatter_std_db      IS 'Simpangan baku backscatter (dB).';
COMMENT ON COLUMN quality_metrics.backscatter_min_db      IS 'Backscatter minimum (dB).';
COMMENT ON COLUMN quality_metrics.backscatter_max_db      IS 'Backscatter maksimum (dB).';
COMMENT ON COLUMN quality_metrics.cloud_threshold_percent IS 'Ambang awan (%) warisan; tidak relevan untuk SAR.';
COMMENT ON COLUMN quality_metrics.radiometric_consistency IS 'true bila rata-rata backscatter dalam rentang sah (-35..5 dB).';
COMMENT ON COLUMN quality_metrics.speckle_index           IS 'Indeks speckle (koefisien variasi); makin kecil makin baik.';
COMMENT ON COLUMN quality_metrics.quality_score           IS 'Skor komposit 0-100 (bobot 50 NoData / 30 speckle / 20 radiometrik).';
COMMENT ON COLUMN quality_metrics.quality_flag            IS 'PASS | WARNING | FAIL | UNCHECKED, dari quality_thresholds.';
COMMENT ON COLUMN quality_metrics.notes                   IS 'Catatan bebas.';
COMMENT ON COLUMN quality_metrics.created_at              IS 'Waktu baris dibuat.';

-- quality_alerts (dulu alert_events DataLab) [UBAH] ---------------------------
CREATE TABLE quality_alerts (
    alert_id        BIGSERIAL             PRIMARY KEY,
    alert_uuid      UUID                  NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    event_type      alert_event_type_enum NOT NULL,
    severity        alert_severity_enum   NOT NULL DEFAULT 'INFO',
    scene_id        INTEGER               REFERENCES satellite_scenes (scene_id) ON DELETE SET NULL,
    job_id          BIGINT                REFERENCES processing_jobs (job_id) ON DELETE SET NULL,
    product_id      BIGINT                REFERENCES data_products (product_id) ON DELETE SET NULL,
    title           VARCHAR(200)          NOT NULL,
    message         TEXT                  NOT NULL,
    metadata_json   JSONB                 DEFAULT '{}',
    is_resolved     BOOLEAN               NOT NULL DEFAULT false,
    resolved_at     TIMESTAMPTZ,
    resolved_by     VARCHAR(100),
    resolution_note TEXT,
    triggered_at    TIMESTAMPTZ           NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ           NOT NULL DEFAULT now()
);
CREATE INDEX idx_qalerts_triggered_at ON quality_alerts (triggered_at DESC);
CREATE INDEX idx_qalerts_scene_id     ON quality_alerts (scene_id) WHERE scene_id IS NOT NULL;
CREATE INDEX idx_qalerts_unresolved   ON quality_alerts (severity, triggered_at DESC) WHERE NOT is_resolved;
COMMENT ON TABLE  quality_alerts IS 'Peringatan kualitas/operasional pipeline (mis. skor QA < 60). Tabel alert_events DataLab yang diganti nama; nama alert_events kini untuk alert hujan.';
COMMENT ON COLUMN quality_alerts.alert_id        IS 'PK surrogate.';
COMMENT ON COLUMN quality_alerts.alert_uuid      IS 'UUID stabil untuk referensi eksternal.';
COMMENT ON COLUMN quality_alerts.event_type      IS 'DATA_ARRIVAL | QUALITY_WARNING | PIPELINE_ERROR | THRESHOLD_BREACH | SYSTEM_ALERT.';
COMMENT ON COLUMN quality_alerts.severity        IS 'INFO | WARNING | CRITICAL.';
COMMENT ON COLUMN quality_alerts.scene_id        IS 'FK -> satellite_scenes terkait.';
COMMENT ON COLUMN quality_alerts.job_id          IS 'FK -> processing_jobs terkait.';
COMMENT ON COLUMN quality_alerts.product_id      IS 'FK -> data_products terkait.';
COMMENT ON COLUMN quality_alerts.title           IS 'Judul singkat.';
COMMENT ON COLUMN quality_alerts.message         IS 'Uraian peringatan.';
COMMENT ON COLUMN quality_alerts.metadata_json   IS 'Konteks terstruktur (JSONB): skor, band, ambang.';
COMMENT ON COLUMN quality_alerts.is_resolved     IS 'true = sudah ditangani.';
COMMENT ON COLUMN quality_alerts.resolved_at     IS 'Waktu ditangani.';
COMMENT ON COLUMN quality_alerts.resolved_by     IS 'Penangan (teks bebas, warisan).';
COMMENT ON COLUMN quality_alerts.resolution_note IS 'Catatan penanganan.';
COMMENT ON COLUMN quality_alerts.triggered_at    IS 'Waktu peringatan terpicu.';
COMMENT ON COLUMN quality_alerts.created_at      IS 'Waktu baris dibuat.';

-- fusion_products [UBAH] ------------------------------------------------------
CREATE TABLE fusion_products (
    fusion_id             BIGSERIAL    PRIMARY KEY,
    dataset_id            INTEGER      REFERENCES datasets (dataset_id) ON DELETE CASCADE,
    feature_date          DATE         NOT NULL,
    region_id             INTEGER      NOT NULL REFERENCES regions_of_interest (region_id) ON DELETE RESTRICT,
    s1_scene_id           INTEGER      REFERENCES satellite_scenes (scene_id) ON DELETE SET NULL,
    modis_scene_id        BIGINT       REFERENCES nasa_scenes (nasa_scene_id) ON DELETE SET NULL,
    gpm_scene_id          BIGINT       REFERENCES nasa_scenes (nasa_scene_id) ON DELETE SET NULL,
    days_since_s1         INTEGER      NOT NULL,
    feature_stack_path    TEXT         NOT NULL,
    fusion_strategy       VARCHAR(20)  DEFAULT 'FULL_COVERAGE'
                                       REFERENCES fusion_strategies (strategy_code) ON UPDATE CASCADE,
    processing_level      VARCHAR(20)  NOT NULL DEFAULT 'PROCESSED' CHECK (processing_level IN ('RAW', 'PROCESSED')),
    temporal_offset_modis INTEGER,
    temporal_offset_gpm   INTEGER,
    s1_offset_days        SMALLINT,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_fusion_dataset_date_level UNIQUE (dataset_id, feature_date, processing_level)
);
CREATE INDEX idx_fusion_date              ON fusion_products (feature_date DESC);
CREATE INDEX idx_fusion_region_date_level ON fusion_products (region_id, feature_date, processing_level);
CREATE INDEX idx_fusion_dataset_date      ON fusion_products (dataset_id, feature_date);
COMMENT ON TABLE  fusion_products IS 'Registri stack HDF5 multi-sensor (S1 + MODIS + GPM) per dataset per tanggal per level.';
COMMENT ON COLUMN fusion_products.fusion_id             IS 'PK surrogate.';
COMMENT ON COLUMN fusion_products.dataset_id            IS 'FK -> datasets pemilik stack (bagian kunci unik).';
COMMENT ON COLUMN fusion_products.feature_date          IS 'Tanggal fitur stack (hari UTC).';
COMMENT ON COLUMN fusion_products.region_id             IS 'FK -> regions_of_interest.';
COMMENT ON COLUMN fusion_products.s1_scene_id           IS 'FK -> satellite_scenes: scene S1 yang dipakai; NULL bila hari itu tanpa S1.';
COMMENT ON COLUMN fusion_products.modis_scene_id        IS 'FK -> nasa_scenes: granule MODIS penanda.';
COMMENT ON COLUMN fusion_products.gpm_scene_id          IS 'FK -> nasa_scenes: granule GPM penanda.';
COMMENT ON COLUMN fusion_products.days_since_s1         IS 'Selisih hari terbesar antar sumber terhadap tanggal fitur.';
COMMENT ON COLUMN fusion_products.feature_stack_path    IS 'Path berkas HDF5.';
COMMENT ON COLUMN fusion_products.fusion_strategy       IS 'FK -> fusion_strategies.strategy_code.';
COMMENT ON COLUMN fusion_products.processing_level      IS 'Level input stack: RAW (dari ALIGNED) | PROCESSED (dari COG).';
COMMENT ON COLUMN fusion_products.temporal_offset_modis IS 'Selisih hari MODIS terhadap tanggal fitur. NULL = MODIS tidak ikut.';
COMMENT ON COLUMN fusion_products.temporal_offset_gpm   IS 'Selisih hari GPM terhadap tanggal fitur. NULL = GPM tidak ikut.';
COMMENT ON COLUMN fusion_products.s1_offset_days        IS 'Jarak hari S1 yang dipakai: 0 = same-day, NULL = tanpa S1.';
COMMENT ON COLUMN fusion_products.created_at            IS 'Waktu baris dibuat.';

-- live_areas [UBAH] -----------------------------------------------------------
CREATE TABLE live_areas (
    area_id             SERIAL        PRIMARY KEY,
    dataset_id          INTEGER       REFERENCES datasets (dataset_id) ON DELETE SET NULL,
    name                VARCHAR(255)  NOT NULL,
    region_id           INTEGER       REFERENCES regions_of_interest (region_id) ON DELETE SET NULL,
    location_label      VARCHAR(255),
    bbox_wkt            TEXT          NOT NULL,
    retention           SMALLINT      NOT NULL DEFAULT 6,
    enabled             BOOLEAN       NOT NULL DEFAULT true,
    status              VARCHAR(20)   NOT NULL DEFAULT 'BACKFILLING',
    status_message      TEXT,
    last_checked_at     TIMESTAMPTZ,
    forecast            JSONB         NOT NULL DEFAULT '{}',
    forecast_updated_at TIMESTAMPTZ,
    updated_by          INT           REFERENCES users (user_id),
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ,
    CONSTRAINT chk_live_area_retention CHECK (retention BETWEEN 1 AND 60),
    CONSTRAINT chk_live_area_status CHECK (status IN ('BACKFILLING', 'ACTIVE', 'RUNNING', 'WAITING', 'ERROR', 'DELETED'))
);
CREATE INDEX idx_live_areas_active ON live_areas (area_id) WHERE deleted_at IS NULL;
COMMENT ON TABLE  live_areas IS 'Live Area: satu AOI yang dipantau otomatis per lintasan S1 (maksimal app_settings.live.max_areas).';
COMMENT ON COLUMN live_areas.area_id             IS 'PK surrogate.';
COMMENT ON COLUMN live_areas.dataset_id          IS 'FK -> datasets berjenis LIVE_AREA yang diproses pipeline.';
COMMENT ON COLUMN live_areas.name                IS 'Nama area, mis. "Lebak Selatan".';
COMMENT ON COLUMN live_areas.region_id           IS 'FK -> regions_of_interest.';
COMMENT ON COLUMN live_areas.location_label      IS 'Label lokasi (salinan nama ROI).';
COMMENT ON COLUMN live_areas.bbox_wkt            IS 'Bbox area dalam WKT.';
COMMENT ON COLUMN live_areas.retention           IS 'Jumlah scene yang berkasnya disimpan (1-60, default 6, M11).';
COMMENT ON COLUMN live_areas.enabled             IS 'false = siklus terjadwal dilewati.';
COMMENT ON COLUMN live_areas.status              IS 'BACKFILLING | ACTIVE | RUNNING | WAITING | ERROR | DELETED.';
COMMENT ON COLUMN live_areas.status_message      IS 'Pesan status untuk kartu Live.';
COMMENT ON COLUMN live_areas.last_checked_at     IS 'Waktu siklus terakhir memeriksa scene baru.';
COMMENT ON COLUMN live_areas.forecast            IS 'Prakiraan statistik terakhir (JSONB tampilan, M12).';
COMMENT ON COLUMN live_areas.forecast_updated_at IS 'Waktu prakiraan dihitung.';
COMMENT ON COLUMN live_areas.updated_by          IS 'FK -> users: ADMIN yang terakhir mengubah.';
COMMENT ON COLUMN live_areas.created_at          IS 'Waktu baris dibuat.';
COMMENT ON COLUMN live_areas.updated_at          IS 'Waktu baris terakhir diubah (trigger).';
COMMENT ON COLUMN live_areas.deleted_at          IS 'Waktu area dihapus (log tetap disimpan).';

-- live_scenes [UBAH] ----------------------------------------------------------
CREATE TABLE live_scenes (
    live_scene_id   BIGSERIAL    PRIMARY KEY,
    area_id         INTEGER      NOT NULL,
    dataset_id      INTEGER,
    scene_date      DATE         NOT NULL,
    s1_product_ids  TEXT[]       NOT NULL DEFAULT ARRAY[]::TEXT[],
    status          VARCHAR(20)  NOT NULL DEFAULT 'PROCESSING',
    source_status   JSONB        NOT NULL DEFAULT '{}',
    interpretations JSONB        NOT NULL DEFAULT '{}',
    area_status     JSONB        NOT NULL DEFAULT '{}',
    previews        JSONB        NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,
    delete_reason   TEXT,
    deleted_files   JSONB        NOT NULL DEFAULT '[]',
    freed_bytes     BIGINT       NOT NULL DEFAULT 0,
    CONSTRAINT uq_live_scene_area_date UNIQUE (area_id, scene_date),
    CONSTRAINT chk_live_scene_status CHECK (status IN ('PROCESSING', 'READY', 'PARTIAL', 'FAILED', 'DELETED'))
);
CREATE INDEX idx_live_scenes_area_date ON live_scenes (area_id, scene_date DESC);
COMMENT ON TABLE  live_scenes IS 'Satu scene Live (tanggal lintasan S1) per area. Tidak pernah dihapus: retensi hanya menghapus berkas dan mengisi deleted_at. Sengaja tanpa FK agar hidup lebih lama dari area/dataset.';
COMMENT ON COLUMN live_scenes.live_scene_id   IS 'PK surrogate.';
COMMENT ON COLUMN live_scenes.area_id         IS 'live_areas.area_id (tanpa FK, lihat komentar tabel).';
COMMENT ON COLUMN live_scenes.dataset_id      IS 'datasets.dataset_id (tanpa FK).';
COMMENT ON COLUMN live_scenes.scene_date      IS 'Tanggal akuisisi S1 (hari UTC).';
COMMENT ON COLUMN live_scenes.s1_product_ids  IS 'Identifier produk S1 yang membentuk scene (TEXT[] <= 3 frame, M32).';
COMMENT ON COLUMN live_scenes.status          IS 'PROCESSING | READY | PARTIAL (sumber pendukung gagal) | FAILED | DELETED.';
COMMENT ON COLUMN live_scenes.source_status   IS 'Status per sumber untuk tampilan (JSONB, tidak dikueri), termasuk deskriptor teks metrik di [sumber].meta (run IMERG, periode komposit). Angka metrik ada di live_scene_metrics (M31).';
COMMENT ON COLUMN live_scenes.interpretations IS 'Kalimat kondisi per variabel (JSONB tampilan).';
COMMENT ON COLUMN live_scenes.area_status     IS 'Status area ringkas {level, label, sentence} (JSONB tampilan).';
COMMENT ON COLUMN live_scenes.previews        IS 'Manifest preview PNG per kunci (JSONB tampilan).';
COMMENT ON COLUMN live_scenes.created_at      IS 'Waktu baris dibuat.';
COMMENT ON COLUMN live_scenes.updated_at      IS 'Waktu baris terakhir diubah (trigger).';
COMMENT ON COLUMN live_scenes.deleted_at      IS 'Waktu berkas scene dihapus retensi; baris tetap ada.';
COMMENT ON COLUMN live_scenes.delete_reason   IS 'Alasan penghapusan berkas, mis. retention.';
COMMENT ON COLUMN live_scenes.deleted_files   IS 'Daftar berkas yang dihapus (JSONB array).';
COMMENT ON COLUMN live_scenes.freed_bytes     IS 'Ruang disk yang dibebaskan (byte).';

-- live_scene_metrics [BARU, M31] ----------------------------------------------
CREATE TABLE live_scene_metrics (
    metric_id         BIGSERIAL     PRIMARY KEY,
    live_scene_id     BIGINT        NOT NULL REFERENCES live_scenes (live_scene_id) ON DELETE CASCADE,
    band_id           SMALLINT      NOT NULL REFERENCES spectral_bands (band_id),
    metric_name       VARCHAR(30)   NOT NULL,
    value             NUMERIC(12,4),
    source_date       DATE,
    ref_live_scene_id BIGINT        REFERENCES live_scenes (live_scene_id) ON DELETE SET NULL,
    CONSTRAINT uq_live_scene_metric UNIQUE (live_scene_id, band_id, metric_name)
);
CREATE INDEX idx_lsm_band_metric ON live_scene_metrics (band_id, metric_name);
COMMENT ON TABLE  live_scene_metrics IS 'Metrik numerik scene Live, satu baris per band x metrik (1NF, M31). Tetap ada setelah berkas scene dihapus retensi.';
COMMENT ON COLUMN live_scene_metrics.metric_id         IS 'PK surrogate.';
COMMENT ON COLUMN live_scene_metrics.live_scene_id     IS 'FK -> live_scenes.';
COMMENT ON COLUMN live_scene_metrics.band_id           IS 'FK -> spectral_bands: VV, VH, FLOOD, NDVI, NDWI, RAIN_24H/72H/7D, WATER_CHANGE.';
COMMENT ON COLUMN live_scene_metrics.metric_name       IS 'Nama metrik, mis. mean, pct_below_threshold, valid_pct, new_km2, receded_km2, persistent_km2, same_orbit.';
COMMENT ON COLUMN live_scene_metrics.value             IS 'Nilai dalam satuan metrik (dB, %, mm, km2, indeks). NULL = tidak ada piksel valid.';
COMMENT ON COLUMN live_scene_metrics.source_date       IS 'Tanggal data sumber (MODIS/GPM bisa tanggal terdekat D-1).';
COMMENT ON COLUMN live_scene_metrics.ref_live_scene_id IS 'FK -> live_scenes: scene pembanding untuk WATER_CHANGE.';

-- live_events [WARIS] ---------------------------------------------------------
CREATE TABLE live_events (
    event_id   BIGSERIAL    PRIMARY KEY,
    area_id    INTEGER      NOT NULL,
    scene_date DATE,
    step       VARCHAR(40)  NOT NULL,
    status     VARCHAR(20)  NOT NULL,
    message    TEXT         NOT NULL,
    details    JSONB        NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_live_events_area_time ON live_events (area_id, created_at DESC);
COMMENT ON TABLE  live_events IS 'Log langkah siklus Live per area (append-only, tanpa FK agar bertahan setelah area dihapus).';
COMMENT ON COLUMN live_events.event_id   IS 'PK surrogate.';
COMMENT ON COLUMN live_events.area_id    IS 'live_areas.area_id (tanpa FK).';
COMMENT ON COLUMN live_events.scene_date IS 'Tanggal scene terkait, bila ada.';
COMMENT ON COLUMN live_events.step       IS 'Langkah siklus, mis. DISCOVER, INGEST, PREVIEW, RETENTION.';
COMMENT ON COLUMN live_events.status     IS 'Status langkah, mis. OK, FAILED, SKIPPED.';
COMMENT ON COLUMN live_events.message    IS 'Pesan langkah.';
COMMENT ON COLUMN live_events.details    IS 'Detail terstruktur (JSONB).';
COMMENT ON COLUMN live_events.created_at IS 'Waktu kejadian.';

-- =============================================================================
-- TABEL TRANSAKSI BARU (DATABASE.md §4.2)
-- =============================================================================

-- region_observations (M7) ----------------------------------------------------
CREATE TABLE region_observations (
    obs_id            BIGSERIAL     PRIMARY KEY,
    region_id         INT           NOT NULL REFERENCES administrative_regions (region_id),
    band_id           SMALLINT      NOT NULL REFERENCES spectral_bands (band_id),
    obs_date          DATE          NOT NULL,
    value             NUMERIC(10,4),
    valid_fraction    NUMERIC(5,4)  NOT NULL CHECK (valid_fraction BETWEEN 0 AND 1),
    source_product_id BIGINT        REFERENCES data_products (product_id) ON DELETE SET NULL,
    run_type          VARCHAR(5)    CHECK (run_type IN ('F', 'L', 'E')),
    job_id            BIGINT        REFERENCES dataset_jobs (job_id) ON DELETE SET NULL,
    computed_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT uq_region_obs UNIQUE (region_id, band_id, obs_date)
);
CREATE INDEX idx_obs_date_band ON region_observations (obs_date DESC, band_id);
COMMENT ON TABLE  region_observations IS 'Nilai harian per kecamatan per band dari GPM/MODIS (zonal statistics, M7). Dasar statistik, alert, laporan.';
COMMENT ON COLUMN region_observations.obs_id            IS 'PK surrogate.';
COMMENT ON COLUMN region_observations.region_id         IS 'FK -> administrative_regions (kecamatan level 3).';
COMMENT ON COLUMN region_observations.band_id           IS 'FK -> spectral_bands, mis. RAIN_24H, NDVI, FLOOD.';
COMMENT ON COLUMN region_observations.obs_date          IS 'Tanggal pengamatan = hari UTC (07.00-07.00 WIB, M28).';
COMMENT ON COLUMN region_observations.value             IS 'Nilai agregat (satuan band: mm, indeks, %). NULL bila valid_fraction < 0,1.';
COMMENT ON COLUMN region_observations.valid_fraction    IS 'Bagian poligon yang punya piksel valid (0-1).';
COMMENT ON COLUMN region_observations.source_product_id IS 'FK -> data_products: COG asal nilai (lineage, RM2).';
COMMENT ON COLUMN region_observations.run_type          IS 'Run IMERG untuk band GPM: F | L | E. Final menimpa Late (PIPELINE.md §3.3).';
COMMENT ON COLUMN region_observations.job_id            IS 'FK -> dataset_jobs yang menghitung nilai.';
COMMENT ON COLUMN region_observations.computed_at       IS 'Waktu nilai dihitung.';

CREATE FUNCTION fn_obs_range() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE lo numeric; hi numeric; code text;
BEGIN
    IF NEW.value IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT valid_min, valid_max, band_code INTO lo, hi, code
      FROM spectral_bands WHERE band_id = NEW.band_id;
    IF (lo IS NOT NULL AND NEW.value < lo) OR (hi IS NOT NULL AND NEW.value > hi) THEN
        RAISE EXCEPTION 'region_observations.value % out of range [%, %] for band %',
            NEW.value, lo, hi, code USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
COMMENT ON FUNCTION fn_obs_range() IS 'Menolak region_observations.value di luar spectral_bands.valid_min/valid_max.';
CREATE TRIGGER trg_obs_range BEFORE INSERT OR UPDATE OF value, band_id ON region_observations
    FOR EACH ROW EXECUTE FUNCTION fn_obs_range();

-- alert_events — alert hujan --------------------------------------------------
CREATE TABLE alert_events (
    alert_id         BIGSERIAL     PRIMARY KEY,
    rule_id          INT           NOT NULL REFERENCES alert_rules (rule_id),
    region_id        INT           NOT NULL REFERENCES administrative_regions (region_id),
    obs_id           BIGINT        NOT NULL REFERENCES region_observations (obs_id),
    observation_date DATE          NOT NULL,
    observed_value   NUMERIC(10,4) NOT NULL,
    threshold_value  NUMERIC(8,2)  NOT NULL,
    severity         VARCHAR(10)   NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL')),
    triggered_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    acknowledged_by  INT           REFERENCES users (user_id),
    acknowledged_at  TIMESTAMPTZ,
    ack_note         VARCHAR(500),
    CONSTRAINT uq_alert_rule_region_date UNIQUE (rule_id, region_id, observation_date),
    CONSTRAINT chk_alert_ack_pair CHECK ((acknowledged_by IS NULL) = (acknowledged_at IS NULL))
);
CREATE INDEX idx_alerts_active      ON alert_events (observation_date DESC) WHERE acknowledged_at IS NULL;
CREATE INDEX idx_alerts_region_date ON alert_events (region_id, observation_date);
COMMENT ON TABLE  alert_events IS 'Alert hujan per aturan per kecamatan per hari. observed_value/threshold_value/severity adalah salinan historis (§5.2).';
COMMENT ON COLUMN alert_events.alert_id         IS 'PK surrogate.';
COMMENT ON COLUMN alert_events.rule_id          IS 'FK -> alert_rules yang terpicu.';
COMMENT ON COLUMN alert_events.region_id        IS 'FK -> administrative_regions (kecamatan).';
COMMENT ON COLUMN alert_events.obs_id           IS 'FK -> region_observations: nilai pemicu.';
COMMENT ON COLUMN alert_events.observation_date IS 'Tanggal pengamatan pemicu (hari UTC).';
COMMENT ON COLUMN alert_events.observed_value   IS 'Salinan nilai saat terpicu (mm).';
COMMENT ON COLUMN alert_events.threshold_value  IS 'Salinan ambang saat terpicu (mm).';
COMMENT ON COLUMN alert_events.severity         IS 'Salinan severity aturan: INFO | WARNING | CRITICAL.';
COMMENT ON COLUMN alert_events.triggered_at     IS 'Waktu alert dibuat job.';
COMMENT ON COLUMN alert_events.acknowledged_by  IS 'FK -> users: ANALYST/ADMIN yang menandai sudah dibaca.';
COMMENT ON COLUMN alert_events.acknowledged_at  IS 'Waktu ditandai sudah dibaca. Berpasangan dengan acknowledged_by.';
COMMENT ON COLUMN alert_events.ack_note         IS 'Catatan opsional saat acknowledge.';

-- disaster_events -------------------------------------------------------------
CREATE TABLE disaster_events (
    event_id         BIGSERIAL     PRIMARY KEY,
    disaster_type_id SMALLINT      NOT NULL REFERENCES disaster_types (disaster_type_id),
    region_id        INT           NOT NULL REFERENCES administrative_regions (region_id),
    village_name     VARCHAR(100),
    location         GEOMETRY(Point, 4326),
    event_date       DATE          NOT NULL,
    event_end_date   DATE          CHECK (event_end_date IS NULL OR event_end_date >= event_date),
    description      TEXT          NOT NULL CHECK (length(description) BETWEEN 10 AND 4000),
    impact_summary   VARCHAR(500),
    info_source      VARCHAR(30)   NOT NULL CHECK (info_source IN ('GMLS', 'BPBD_LEBAK', 'BNPB_DIBI', 'MEDIA', 'LAINNYA')),
    source_reference TEXT,
    is_verified      BOOLEAN       NOT NULL DEFAULT false,
    verified_by      INT           REFERENCES users (user_id),
    recorded_by      INT           NOT NULL REFERENCES users (user_id),
    recorded_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    deleted_at       TIMESTAMPTZ
);
CREATE INDEX idx_disasters_date_region ON disaster_events (event_date, region_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_disasters_location    ON disaster_events USING GIST (location);
COMMENT ON TABLE  disaster_events IS 'Catatan kejadian bencana (GMLS, BPBD, input ANALYST). Tanpa data pribadi. Soft delete.';
COMMENT ON COLUMN disaster_events.event_id         IS 'PK surrogate.';
COMMENT ON COLUMN disaster_events.disaster_type_id IS 'FK -> disaster_types.';
COMMENT ON COLUMN disaster_events.region_id        IS 'FK -> administrative_regions (kecamatan).';
COMMENT ON COLUMN disaster_events.village_name     IS 'Nama desa sebagai teks (COD-AB level 4 tidak tersedia).';
COMMENT ON COLUMN disaster_events.location         IS 'Titik kejadian opsional (Point EPSG:4326).';
COMMENT ON COLUMN disaster_events.event_date       IS 'Tanggal mulai kejadian.';
COMMENT ON COLUMN disaster_events.event_end_date   IS 'Tanggal selesai (>= event_date), opsional.';
COMMENT ON COLUMN disaster_events.description      IS 'Uraian kejadian, 10-4000 karakter.';
COMMENT ON COLUMN disaster_events.impact_summary   IS 'Ringkasan dampak (rumah terdampak, akses jalan) tanpa data pribadi.';
COMMENT ON COLUMN disaster_events.info_source      IS 'GMLS | BPBD_LEBAK | BNPB_DIBI | MEDIA | LAINNYA.';
COMMENT ON COLUMN disaster_events.source_reference IS 'URL atau nomor dokumen rujukan.';
COMMENT ON COLUMN disaster_events.is_verified      IS 'true = sudah diverifikasi (dipakai v_evaluasi_alert).';
COMMENT ON COLUMN disaster_events.verified_by      IS 'FK -> users: pemverifikasi.';
COMMENT ON COLUMN disaster_events.recorded_by      IS 'FK -> users: pencatat.';
COMMENT ON COLUMN disaster_events.recorded_at      IS 'Waktu dicatat.';
COMMENT ON COLUMN disaster_events.updated_at       IS 'Waktu baris terakhir diubah (trigger).';
COMMENT ON COLUMN disaster_events.deleted_at       IS 'Soft delete; NULL = aktif.';

-- generated_reports -----------------------------------------------------------
CREATE TABLE generated_reports (
    report_id       BIGSERIAL    PRIMARY KEY,
    report_type_id  SMALLINT     NOT NULL REFERENCES report_types (report_type_id),
    period_start    DATE         NOT NULL,
    period_end      DATE         NOT NULL CHECK (period_end >= period_start),
    file_path       TEXT         NOT NULL,
    file_size_bytes BIGINT       NOT NULL CHECK (file_size_bytes >= 0),
    checksum_sha256 CHAR(64)     NOT NULL,
    status          VARCHAR(10)  NOT NULL CHECK (status IN ('READY', 'FAILED', 'SUPERSEDED')),
    error_message   TEXT,
    generated_by    INT          REFERENCES users (user_id),
    generated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_report_ready ON generated_reports (report_type_id, period_start) WHERE status = 'READY';
CREATE INDEX idx_reports_type_period ON generated_reports (report_type_id, period_start DESC);
COMMENT ON TABLE  generated_reports IS 'Laporan PDF mingguan/bulanan yang dibuat (M18). Akses dibatasi RLS per audiens (tahap keamanan).';
COMMENT ON COLUMN generated_reports.report_id       IS 'PK surrogate.';
COMMENT ON COLUMN generated_reports.report_type_id  IS 'FK -> report_types.';
COMMENT ON COLUMN generated_reports.period_start    IS 'Awal periode (Senin / tanggal 1, WIB).';
COMMENT ON COLUMN generated_reports.period_end      IS 'Akhir periode (Minggu / akhir bulan, WIB).';
COMMENT ON COLUMN generated_reports.file_path       IS 'Path PDF: data/reports/{report_code}/{YYYY}/...pdf.';
COMMENT ON COLUMN generated_reports.file_size_bytes IS 'Ukuran PDF (byte).';
COMMENT ON COLUMN generated_reports.checksum_sha256 IS 'SHA-256 PDF (64 hex).';
COMMENT ON COLUMN generated_reports.status          IS 'READY | FAILED | SUPERSEDED (digantikan regenerasi).';
COMMENT ON COLUMN generated_reports.error_message   IS 'Pesan galat bila FAILED.';
COMMENT ON COLUMN generated_reports.generated_by    IS 'FK -> users: ADMIN yang meregenerasi. NULL = scheduler.';
COMMENT ON COLUMN generated_reports.generated_at    IS 'Waktu laporan dibuat.';

-- user_activity_logs ----------------------------------------------------------
CREATE TABLE user_activity_logs (
    log_id             BIGSERIAL    PRIMARY KEY,
    user_id            INT          REFERENCES users (user_id),
    username_attempted VARCHAR(50),
    action             VARCHAR(30)  NOT NULL,
    target_type        VARCHAR(40),
    target_id          BIGINT,
    bytes_sent         BIGINT       CHECK (bytes_sent IS NULL OR bytes_sent >= 0),
    ip_address         INET,
    user_agent         VARCHAR(255),
    detail             JSONB,
    logged_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_activity_action_time ON user_activity_logs (action, logged_at DESC);
CREATE INDEX idx_activity_user_time   ON user_activity_logs (user_id, logged_at DESC);
COMMENT ON TABLE  user_activity_logs IS 'Log aplikasi append-only: login, logout, unduhan, ekspor, aksi penting (RM4).';
COMMENT ON COLUMN user_activity_logs.log_id             IS 'PK surrogate.';
COMMENT ON COLUMN user_activity_logs.user_id            IS 'FK -> users. NULL untuk login gagal dengan username tak dikenal atau PUBLIC.';
COMMENT ON COLUMN user_activity_logs.username_attempted IS 'Username yang dicoba pada login gagal.';
COMMENT ON COLUMN user_activity_logs.action             IS 'LOGIN_SUCCESS, LOGIN_FAILED, LOGOUT, DOWNLOAD_PRODUCT, DOWNLOAD_DATASET, DOWNLOAD_FUSION, DOWNLOAD_REPORT, EXPORT_CSV, CREATE_DATASET, TRIGGER_INGEST, ...';
COMMENT ON COLUMN user_activity_logs.target_type        IS 'Tabel objek aksi, mis. data_products, datasets, generated_reports.';
COMMENT ON COLUMN user_activity_logs.target_id          IS 'PK objek aksi.';
COMMENT ON COLUMN user_activity_logs.bytes_sent         IS 'Jumlah byte terkirim (unduhan).';
COMMENT ON COLUMN user_activity_logs.ip_address         IS 'Alamat IP klien.';
COMMENT ON COLUMN user_activity_logs.user_agent         IS 'User-Agent klien (dipotong 255).';
COMMENT ON COLUMN user_activity_logs.detail             IS 'Detail tambahan (JSONB), mis. {"auth": "token"}.';
COMMENT ON COLUMN user_activity_logs.logged_at          IS 'Waktu kejadian.';

-- audit_log -------------------------------------------------------------------
CREATE TABLE audit_log (
    audit_id        BIGSERIAL    PRIMARY KEY,
    table_name      VARCHAR(63)  NOT NULL,
    row_pk          TEXT         NOT NULL,
    operation       CHAR(1)      NOT NULL CHECK (operation IN ('I', 'U', 'D')),
    old_data        JSONB,
    new_data        JSONB,
    changed_columns TEXT[],
    app_user_id     INT,
    db_user         NAME         NOT NULL DEFAULT current_user,
    changed_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_table_time ON audit_log (table_name, changed_at DESC);
COMMENT ON TABLE  audit_log IS 'Jejak perubahan data yang diisi trigger audit_row (append-only, M15). Trigger dipasang di monitor_security.sql.';
COMMENT ON COLUMN audit_log.audit_id        IS 'PK surrogate.';
COMMENT ON COLUMN audit_log.table_name      IS 'Nama tabel yang berubah.';
COMMENT ON COLUMN audit_log.row_pk          IS 'Nilai PK baris yang berubah (teks).';
COMMENT ON COLUMN audit_log.operation       IS 'I (INSERT) | U (UPDATE) | D (DELETE).';
COMMENT ON COLUMN audit_log.old_data        IS 'Baris sebelum perubahan (JSONB; password_hash/token_hash disensor).';
COMMENT ON COLUMN audit_log.new_data        IS 'Baris sesudah perubahan (JSONB; password_hash/token_hash disensor).';
COMMENT ON COLUMN audit_log.changed_columns IS 'Kolom yang berubah (untuk U).';
COMMENT ON COLUMN audit_log.app_user_id     IS 'users.user_id dari current_setting(''app.user_id''); NULL bila lewat psql.';
COMMENT ON COLUMN audit_log.db_user         IS 'Role PostgreSQL yang menjalankan perubahan.';
COMMENT ON COLUMN audit_log.changed_at      IS 'Waktu perubahan.';

-- api_tokens (M33) ------------------------------------------------------------
CREATE TABLE api_tokens (
    token_id     SERIAL       PRIMARY KEY,
    user_id      INT          NOT NULL REFERENCES users (user_id),
    token_name   VARCHAR(60)  NOT NULL,
    token_prefix CHAR(8)      NOT NULL UNIQUE,
    token_hash   CHAR(64)     NOT NULL,
    scopes       VARCHAR(20)  NOT NULL CHECK (scopes IN ('READ', 'READ_DOWNLOAD')),
    expires_at   TIMESTAMPTZ  NOT NULL,
    last_used_at TIMESTAMPTZ,
    revoked_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT chk_token_max_lifetime CHECK (expires_at <= created_at + INTERVAL '180 days')
);
CREATE INDEX idx_api_tokens_user ON api_tokens (user_id);
COMMENT ON TABLE  api_tokens IS 'Token API pribadi untuk skrip/sistem lain (M33). Hanya hash yang disimpan; token utuh ditampilkan sekali.';
COMMENT ON COLUMN api_tokens.token_id     IS 'PK surrogate.';
COMMENT ON COLUMN api_tokens.user_id      IS 'FK -> users pemilik; role token = role pemilik saat dipakai.';
COMMENT ON COLUMN api_tokens.token_name   IS 'Nama token, mis. "skrip training".';
COMMENT ON COLUMN api_tokens.token_prefix IS 'Awalan token untuk identifikasi, mis. trn_4f2a (unik).';
COMMENT ON COLUMN api_tokens.token_hash   IS 'SHA-256 token (64 hex).';
COMMENT ON COLUMN api_tokens.scopes       IS 'READ | READ_DOWNLOAD (tanpa scope tulis).';
COMMENT ON COLUMN api_tokens.expires_at   IS 'Kedaluwarsa, maksimal 180 hari sejak dibuat.';
COMMENT ON COLUMN api_tokens.last_used_at IS 'Waktu terakhir dipakai.';
COMMENT ON COLUMN api_tokens.revoked_at   IS 'Waktu dicabut; NULL = aktif.';
COMMENT ON COLUMN api_tokens.created_at   IS 'Waktu token dibuat.';

-- =============================================================================
-- TRIGGER updated_at
-- =============================================================================
DO $$
DECLARE tbl text;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'users', 'regions_of_interest', 'processing_stages', 'alert_rules', 'app_settings',
        'satellite_scenes', 'datasets', 'dataset_source_config', 'processing_jobs',
        'data_products', 'live_areas', 'live_scenes', 'disaster_events'
    ] LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_%1$s_updated_at BEFORE UPDATE ON %1$I '
            'FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at()', tbl);
    END LOOP;
END $$;

-- =============================================================================
-- VIEW (DATABASE.md §7)
-- =============================================================================

-- Scene Live terbaru per area aktif (PUBLIC+).
CREATE VIEW v_public_live_latest AS
SELECT DISTINCT ON (s.area_id)
       s.area_id,
       a.name           AS area_name,
       s.live_scene_id,
       s.scene_date,
       s.status,
       s.area_status,
       s.interpretations,
       s.previews,
       s.source_status
FROM live_scenes s
JOIN live_areas  a ON a.area_id = s.area_id
WHERE a.deleted_at IS NULL
  AND a.enabled
  AND s.deleted_at IS NULL
  AND s.status IN ('READY', 'PARTIAL')
ORDER BY s.area_id, s.scene_date DESC;
COMMENT ON VIEW v_public_live_latest IS 'Scene Live terbaru per area aktif (READY/PARTIAL, berkas belum dihapus): status area, kalimat kondisi, manifest preview. PUBLIC+.';

-- Scene Live 30 hari terakhir (USER+).
CREATE VIEW v_live_scenes_recent AS
SELECT s.live_scene_id,
       s.area_id,
       a.name AS area_name,
       s.scene_date,
       s.status,
       s.area_status,
       s.interpretations,
       s.previews,
       s.source_status
FROM live_scenes s
JOIN live_areas  a ON a.area_id = s.area_id
WHERE a.deleted_at IS NULL
  AND s.deleted_at IS NULL
  AND s.status IN ('READY', 'PARTIAL')
  AND s.scene_date >= CURRENT_DATE - 30;
COMMENT ON VIEW v_live_scenes_recent IS 'Scene Live dalam 30 hari terakhir yang berkasnya masih ada. USER+.';

-- Pivot hujan harian per kecamatan + kategori BMKG 24 jam (USER+).
CREATE VIEW v_hujan_harian_kecamatan AS
SELECT o.obs_date,
       r.region_id,
       r.pcode,
       r.region_name,
       max(o.value)    FILTER (WHERE b.band_code = 'RAIN_24H') AS rain_24h_mm,
       max(o.value)    FILTER (WHERE b.band_code = 'RAIN_72H') AS rain_72h_mm,
       max(o.value)    FILTER (WHERE b.band_code = 'RAIN_7D')  AS rain_7d_mm,
       max(o.value)    FILTER (WHERE b.band_code = 'RAIN_30D') AS rain_30d_mm,
       max(o.run_type) FILTER (WHERE b.band_code = 'RAIN_24H') AS gpm_run,
       CASE
           WHEN max(o.value) FILTER (WHERE b.band_code = 'RAIN_24H') IS NULL THEN NULL
           WHEN max(o.value) FILTER (WHERE b.band_code = 'RAIN_24H') <  20  THEN 'RINGAN'
           WHEN max(o.value) FILTER (WHERE b.band_code = 'RAIN_24H') <  50  THEN 'SEDANG'
           WHEN max(o.value) FILTER (WHERE b.band_code = 'RAIN_24H') < 100  THEN 'LEBAT'
           WHEN max(o.value) FILTER (WHERE b.band_code = 'RAIN_24H') < 150  THEN 'SANGAT_LEBAT'
           ELSE 'EKSTREM'
       END AS bmkg_category
FROM region_observations    o
JOIN spectral_bands         b ON b.band_id = o.band_id
JOIN administrative_regions r ON r.region_id = o.region_id
WHERE b.band_code IN ('RAIN_24H', 'RAIN_72H', 'RAIN_7D', 'RAIN_30D')
GROUP BY o.obs_date, r.region_id, r.pcode, r.region_name;
COMMENT ON VIEW v_hujan_harian_kecamatan IS 'Hujan 24h/72h/7d/30d (mm) per kecamatan per tanggal UTC + run GPM + kategori BMKG hujan 24 jam (RINGAN < 20, SEDANG < 50, LEBAT < 100, SANGAT_LEBAT < 150, EKSTREM). USER+.';

-- Statistik hari ini: tanggal terakhir yang lengkap untuk semua kecamatan AOI (USER+).
CREATE VIEW v_statistik_hari_ini AS
WITH aoi AS (
    SELECT count(*) AS n FROM administrative_regions WHERE in_aoi
),
complete_day AS (
    SELECT max(h.obs_date) AS obs_date
    FROM (
        SELECT obs_date, count(*) AS n
        FROM v_hujan_harian_kecamatan v
        JOIN administrative_regions r ON r.region_id = v.region_id AND r.in_aoi
        WHERE v.rain_24h_mm IS NOT NULL
        GROUP BY obs_date
    ) h, aoi
    WHERE h.n = aoi.n
)
SELECT v.obs_date,
       v.region_id,
       v.pcode,
       v.region_name,
       v.rain_24h_mm,
       v.rain_72h_mm,
       v.rain_7d_mm,
       v.rain_30d_mm,
       v.gpm_run,
       v.bmkg_category,
       ndvi.value  AS ndvi,
       ndvi.obs_date AS ndvi_date,
       ndwi.value  AS ndwi,
       ndwi.obs_date AS ndwi_date,
       flood.value AS modis_flood_pct,
       flood.obs_date AS modis_date
FROM complete_day d
JOIN v_hujan_harian_kecamatan v ON v.obs_date = d.obs_date
JOIN administrative_regions r   ON r.region_id = v.region_id AND r.in_aoi
LEFT JOIN LATERAL (
    SELECT o.value, o.obs_date FROM region_observations o
    JOIN spectral_bands b ON b.band_id = o.band_id AND b.band_code = 'NDVI'
    WHERE o.region_id = v.region_id AND o.obs_date <= d.obs_date AND o.value IS NOT NULL
    ORDER BY o.obs_date DESC LIMIT 1) ndvi ON true
LEFT JOIN LATERAL (
    SELECT o.value, o.obs_date FROM region_observations o
    JOIN spectral_bands b ON b.band_id = o.band_id AND b.band_code = 'NDWI'
    WHERE o.region_id = v.region_id AND o.obs_date <= d.obs_date AND o.value IS NOT NULL
    ORDER BY o.obs_date DESC LIMIT 1) ndwi ON true
LEFT JOIN LATERAL (
    SELECT o.value, o.obs_date FROM region_observations o
    JOIN spectral_bands b ON b.band_id = o.band_id AND b.band_code = 'FLOOD'
    WHERE o.region_id = v.region_id AND o.obs_date <= d.obs_date AND o.value IS NOT NULL
    ORDER BY o.obs_date DESC LIMIT 1) flood ON true;
COMMENT ON VIEW v_statistik_hari_ini IS 'Baris v_hujan_harian_kecamatan untuk tanggal terakhir yang lengkap (semua kecamatan in_aoi punya RAIN_24H) + NDVI/NDWI/FLOOD MODIS terakhir yang tersedia. USER+.';

-- Alert hujan yang belum di-acknowledge (USER+).
CREATE VIEW v_alert_aktif AS
SELECT a.alert_id,
       a.observation_date,
       a.region_id,
       r.pcode,
       r.region_name,
       a.rule_id,
       ru.rule_code,
       dt.type_code AS disaster_type_code,
       b.band_code,
       a.observed_value,
       a.threshold_value,
       a.severity,
       a.triggered_at
FROM alert_events           a
JOIN administrative_regions r  ON r.region_id = a.region_id
JOIN alert_rules            ru ON ru.rule_id = a.rule_id
JOIN disaster_types         dt ON dt.disaster_type_id = ru.disaster_type_id
JOIN spectral_bands         b  ON b.band_id = ru.band_id
WHERE a.acknowledged_at IS NULL;
COMMENT ON VIEW v_alert_aktif IS 'Alert hujan yang belum ditandai dibaca, lengkap dengan nama kecamatan dan aturan. USER+.';

-- Kejadian bencana + hujan H-0, H-1, H-2 (ANALYST, ADMIN).
CREATE VIEW v_kejadian_dan_hujan AS
SELECT e.event_id,
       e.event_date,
       e.event_end_date,
       dt.type_code AS disaster_type_code,
       e.region_id,
       r.region_name,
       e.village_name,
       e.is_verified,
       e.info_source,
       h0.rain_24h_mm AS rain_24h_h0, h0.rain_72h_mm AS rain_72h_h0, h0.rain_7d_mm AS rain_7d_h0,
       h1.rain_24h_mm AS rain_24h_h1, h1.rain_72h_mm AS rain_72h_h1, h1.rain_7d_mm AS rain_7d_h1,
       h2.rain_24h_mm AS rain_24h_h2, h2.rain_72h_mm AS rain_72h_h2, h2.rain_7d_mm AS rain_7d_h2
FROM disaster_events        e
JOIN disaster_types         dt ON dt.disaster_type_id = e.disaster_type_id
JOIN administrative_regions r  ON r.region_id = e.region_id
LEFT JOIN v_hujan_harian_kecamatan h0 ON h0.region_id = e.region_id AND h0.obs_date = e.event_date
LEFT JOIN v_hujan_harian_kecamatan h1 ON h1.region_id = e.region_id AND h1.obs_date = e.event_date - 1
LEFT JOIN v_hujan_harian_kecamatan h2 ON h2.region_id = e.region_id AND h2.obs_date = e.event_date - 2
WHERE e.deleted_at IS NULL;
COMMENT ON VIEW v_kejadian_dan_hujan IS 'Kejadian bencana aktif dengan hujan 24h/72h/7d (mm) pada H-0, H-1, H-2 di kecamatannya. ANALYST, ADMIN.';

-- Evaluasi alert: hit / miss / false alarm (ANALYST, ADMIN) — definisi DATABASE.md §7.
CREATE VIEW v_evaluasi_alert AS
WITH ev AS (
  SELECT e.event_id, e.region_id, e.event_date, dt.disaster_type_id
  FROM disaster_events e JOIN disaster_types dt USING (disaster_type_id)
  WHERE e.deleted_at IS NULL AND e.is_verified
),
al AS (
  SELECT a.alert_id, a.rule_id, a.region_id, a.observation_date, r.disaster_type_id
  FROM alert_events a JOIN alert_rules r USING (rule_id)
  WHERE a.severity IN ('WARNING', 'CRITICAL')
)
SELECT 'HIT' AS outcome, ev.event_id, al.alert_id, ev.region_id, ev.event_date AS ref_date
FROM ev JOIN al ON al.region_id = ev.region_id
               AND al.disaster_type_id = ev.disaster_type_id
               AND al.observation_date BETWEEN ev.event_date - 3 AND ev.event_date
UNION ALL
SELECT 'MISS', ev.event_id, NULL, ev.region_id, ev.event_date
FROM ev WHERE NOT EXISTS (
  SELECT 1 FROM al WHERE al.region_id = ev.region_id
    AND al.disaster_type_id = ev.disaster_type_id
    AND al.observation_date BETWEEN ev.event_date - 3 AND ev.event_date)
UNION ALL
SELECT 'FALSE_ALARM', NULL, al.alert_id, al.region_id, al.observation_date
FROM al WHERE NOT EXISTS (
  SELECT 1 FROM ev WHERE ev.region_id = al.region_id
    AND ev.disaster_type_id = al.disaster_type_id
    AND ev.event_date BETWEEN al.observation_date AND al.observation_date + 3);
COMMENT ON VIEW v_evaluasi_alert IS 'Evaluasi alert WARNING+ terhadap kejadian terverifikasi dengan jendela 0-3 hari: HIT, MISS, FALSE_ALARM. ANALYST, ADMIN.';

-- Ringkasan kualitas per sumber per minggu (DATA_ENGINEER, ADMIN).
CREATE VIEW v_ringkasan_kualitas AS
WITH s1 AS (
    SELECT dp.source AS source_code,
           date_trunc('week', qm.assessed_at)::date AS week_start,
           count(*)                                    AS n_quality_metrics,
           round(avg(qm.quality_score), 2)             AS avg_quality_score,
           count(*) FILTER (WHERE qm.quality_flag = 'FAIL')    AS n_fail,
           count(*) FILTER (WHERE qm.quality_flag = 'WARNING') AS n_warning
    FROM quality_metrics qm
    JOIN data_products   dp ON dp.product_id = qm.product_id
    GROUP BY 1, 2
),
qa AS (
    SELECT COALESCE(dp.source, 'SENTINEL1') AS source_code,
           date_trunc('week', q.triggered_at)::date AS week_start,
           count(*) AS n_quality_alerts
    FROM quality_alerts q
    LEFT JOIN data_products dp ON dp.product_id = q.product_id
    WHERE q.event_type = 'QUALITY_WARNING'
    GROUP BY 1, 2
),
vf AS (
    SELECT s.source_code,
           date_trunc('week', o.obs_date)::date AS week_start,
           count(*)                              AS n_observations,
           round(avg(o.valid_fraction), 4)       AS avg_valid_fraction
    FROM region_observations o
    JOIN spectral_bands      b ON b.band_id = o.band_id
    JOIN satellite_sources   s ON s.source_id = b.source_id
    GROUP BY 1, 2
)
SELECT COALESCE(s1.source_code, qa.source_code, vf.source_code) AS source_code,
       COALESCE(s1.week_start, qa.week_start, vf.week_start)    AS week_start,
       COALESCE(s1.n_quality_metrics, 0) AS n_quality_metrics,
       s1.avg_quality_score,
       COALESCE(s1.n_fail, 0)            AS n_fail,
       COALESCE(s1.n_warning, 0)         AS n_warning,
       COALESCE(qa.n_quality_alerts, 0)  AS n_quality_alerts,
       COALESCE(vf.n_observations, 0)    AS n_observations,
       vf.avg_valid_fraction
FROM s1
FULL JOIN qa ON qa.source_code = s1.source_code AND qa.week_start = s1.week_start
FULL JOIN vf ON vf.source_code = COALESCE(s1.source_code, qa.source_code)
            AND vf.week_start  = COALESCE(s1.week_start, qa.week_start);
COMMENT ON VIEW v_ringkasan_kualitas IS 'Per sumber per minggu (Senin): jumlah & rata-rata skor quality_metrics, FAIL/WARNING, quality_alerts, dan rata-rata valid_fraction region_observations. DATA_ENGINEER, ADMIN.';

-- Kelengkapan data per sumber, gap > 10 hari ditandai (DATA_ENGINEER, ADMIN).
CREATE VIEW v_kelengkapan_data AS
WITH d AS (
    SELECT DISTINCT 'SENTINEL1'::varchar(20) AS source_code,
           (acquisition_datetime AT TIME ZONE 'UTC')::date AS data_date
    FROM satellite_scenes WHERE is_valid
    UNION
    SELECT DISTINCT source, acquisition_date
    FROM nasa_scenes WHERE is_valid
),
g AS (
    SELECT source_code, data_date,
           lag(data_date) OVER (PARTITION BY source_code ORDER BY data_date) AS prev_date
    FROM d
)
SELECT source_code,
       data_date,
       prev_date,
       data_date - prev_date             AS gap_days,
       COALESCE(data_date - prev_date > 10, false) AS is_gap
FROM g;
COMMENT ON VIEW v_kelengkapan_data IS 'Tanggal yang punya data per sumber (S1 dari satellite_scenes, MODIS/GPM dari nasa_scenes) dengan jarak ke tanggal sebelumnya; is_gap = jarak > 10 hari. DATA_ENGINEER, ADMIN.';

-- Pengguna tanpa kolom rahasia.
CREATE VIEW v_users_safe AS
SELECT u.user_id,
       u.role_id,
       r.role_code,
       u.username,
       u.full_name,
       u.organization,
       u.is_active,
       u.last_login_at,
       u.created_by,
       u.created_at,
       u.updated_at
FROM users u
JOIN roles r ON r.role_id = u.role_id;
COMMENT ON VIEW v_users_safe IS 'users tanpa password_hash, failed_login_count, locked_until. ADMIN (UI) dan semua role untuk join nama.';

CREATE VIEW v_log_login AS
SELECT l.log_id, l.logged_at, l.action, l.user_id, u.username,
       l.username_attempted, l.ip_address, l.user_agent, l.detail
FROM user_activity_logs l
LEFT JOIN users u ON u.user_id = l.user_id
WHERE l.action IN ('LOGIN_SUCCESS', 'LOGIN_FAILED', 'LOGOUT');
COMMENT ON VIEW v_log_login IS 'Log masuk/keluar dari user_activity_logs. ADMIN.';

CREATE VIEW v_log_unduhan AS
SELECT l.log_id, l.logged_at, l.action, l.user_id, u.username,
       l.target_type, l.target_id, l.bytes_sent, l.ip_address, l.detail
FROM user_activity_logs l
LEFT JOIN users u ON u.user_id = l.user_id
WHERE l.action LIKE 'DOWNLOAD\_%' OR l.action = 'EXPORT_CSV';
COMMENT ON VIEW v_log_unduhan IS 'Log unduhan dan ekspor CSV dari user_activity_logs. ADMIN.';

-- Volume unduhan per hari, jenis, dan role, TANPA identitas pengguna
-- (Laporan Kesehatan Data §6.3 bagian 8; IMPLEMENTATION_NOTES Tahap 3).
CREATE VIEW v_unduhan_per_role AS
SELECT (l.logged_at AT TIME ZONE 'Asia/Jakarta')::date AS log_date_wib,
       l.action,
       COALESCE(r.role_code, 'PUBLIC')            AS role_code,
       count(*)                                    AS n_downloads,
       COALESCE(sum(l.bytes_sent), 0)::bigint      AS bytes_sent
FROM user_activity_logs l
LEFT JOIN users u ON u.user_id = l.user_id
LEFT JOIN roles r ON r.role_id = u.role_id
WHERE l.action LIKE 'DOWNLOAD\_%' OR l.action = 'EXPORT_CSV'
GROUP BY 1, 2, 3;
COMMENT ON VIEW v_unduhan_per_role IS 'Jumlah dan volume unduhan/ekspor per tanggal WIB, jenis aksi, dan role pengunduh; tanpa nama pengguna. DATA_ENGINEER, ADMIN, ETL (laporan).';

-- =============================================================================
-- END monitor_schema.sql
-- =============================================================================
