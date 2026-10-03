# DATABASE — Orbit-U: The Monitor

> **STATUS: FINAL v1.0 (1 Oktober 2026).** Tabel berlabel **[WARIS]** mempertahankan skema DataLab (lihat DataLab `ARCHITECTURE.md`); dokumen ini hanya menulis perubahannya. Tabel **[BARU]** ditulis lengkap.

Urutan bab mengikuti DBSDLC: DBMS selection → conceptual → logical (normalisasi) → physical (DDL, index, VIEW, keamanan, redundansi terkendali) → pemantauan.

---

## 1. DBMS Selection

### Kerangka acuan

| Kriteria | Bobot | Alasan |
|---|---|---|
| Dukungan data & kueri spasial | 30% | Agregasi per kecamatan, AOI, footprint |
| Integritas relasional (ACID, FK, CHECK) | 25% | Lineage graph dan audit menuntut referential integrity |
| Keamanan berbasis role (GRANT, VIEW, row-level) | 15% | RM4 |
| Biaya & lisensi | 15% | GMLS organisasi nirlaba |
| Integrasi Python / kode yang sudah ada | 15% | Kode DataLab memakai SQLAlchemy + GeoAlchemy2 + PostGIS |

### Daftar pendek

| DBMS | Catatan |
|---|---|
| PostgreSQL 14 + PostGIS 3 | Spatial index GiST, fungsi spasial lengkap, role/GRANT granular, trigger, JSONB; sudah dipakai DataLab |
| MySQL 8 | Tipe spasial ada, fungsi analisis lebih sempit; tidak ada `SET ROLE` per transaksi yang setara |
| MongoDB 7 | Geo index ada, tetapi tanpa FK — lineage dan audit harus dijaga di aplikasi |

Skor akhir diisi dari hasil benchmark di bawah. **Rekomendasi: PostgreSQL 14+ dengan PostGIS 3+**, tanpa TimescaleDB (M3) — rekomendasi ini harus dibuktikan oleh benchmark, bukan diasumsikan.

### Evaluasi produk (benchmark, M29)

Skrip `benchmark/` di repo, dijalankan di mesin yang sama dengan data yang sama:

| Langkah | Isi |
|---|---|
| Data | Ekspor `administrative_regions` (kecamatan Lebak), `region_observations` (3 tahun), `alert_events`, `disaster_events`, `data_products` + `data_lineage` dari DB Monitor → CSV/GeoJSON → dimuat ke PostgreSQL 14 + PostGIS dan MySQL 8.0 dengan skema setara |
| Q1 Statistik hari ini | Pivot hujan per kecamatan untuk satu tanggal |
| Q2 Tren 30 hari | Deret waktu satu kecamatan, satu band |
| Q3 Spasial | Kecamatan yang beririsan dengan sebuah poligon + luas irisan (`ST_Intersection`, `ST_Area` geodesik) |
| Q4 Evaluasi alert | Kueri `v_evaluasi_alert` |
| Q5 Lineage | `WITH RECURSIVE` leluhur satu produk sampai 6 tingkat |
| F1–F3 Fitur keamanan | `SET ROLE` per transaksi, row-level security, trigger audit dengan `old`/`new` sebagai JSON |
| Metode | 5 kali pemanasan, 30 kali ukur, laporkan median dan p95; `EXPLAIN` disimpan |
| Keluaran | `benchmark/results/timing.csv`, `features.csv`, `environment.json` (versi, CPU, RAM) |

MongoDB 7 dinilai dari fitur saja (FK, transaksi multi-dokumen, `$graphLookup` untuk lineage, RLS), tanpa benchmark, karena skemanya tidak setara.

---

## 2. Model Konseptual

### Kelompok entitas

```
[MASTER]
  roles ──< users
  satellite_sources ──< spectral_bands ──< quality_thresholds
  administrative_regions (self-ref: kabupaten → kecamatan)
  regions_of_interest
  processing_stages
  disaster_types ──< alert_rules >── spectral_bands
  fusion_strategies
  report_types

[TRANSAKSI — ingestion & lineage]              (RM1, RM2)
  datasets ──< dataset_source_config
  datasets ──< dataset_jobs ──< scene_job_state
  satellite_scenes ──< processing_jobs ──< processing_logs
  satellite_scenes ──< data_products ──< data_lineage >── data_products
  data_products ──< quality_metrics
  nasa_scenes
  fusion_products >── datasets, satellite_scenes, nasa_scenes, fusion_strategies

[TRANSAKSI — monitoring]                       (RM1, RM3)
  region_observations >── administrative_regions, spectral_bands, data_products
  alert_events >── alert_rules, administrative_regions, users(ack)
  disaster_events >── disaster_types, administrative_regions, users
  live_areas ──< live_scenes ;  live_events
  generated_reports >── report_types

[TRANSAKSI — keamanan & audit]                 (RM4)
  users ──< user_activity_logs
  audit_log
```

### Relasi utama

| Relasi | Kardinalitas | Catatan |
|---|---|---|
| roles – users | 1 : N | |
| satellite_sources – spectral_bands | 1 : N | |
| administrative_regions – administrative_regions | 1 : N | induk–anak |
| administrative_regions – region_observations | 1 : N | |
| spectral_bands – region_observations | 1 : N | |
| data_products – data_lineage | N : M (via parent/child) | |
| data_products – quality_metrics | 1 : N | |
| alert_rules – alert_events | 1 : N | |
| disaster_types – disaster_events | 1 : N | |
| administrative_regions – disaster_events | 1 : N | |
| report_types – generated_reports | 1 : N | |
| users – user_activity_logs | 1 : N | |

---

## 3. Tabel Master (12 tabel)

Seluruh master memiliki PK surrogate dan **alternate key** berupa kode (`*_code`). Kolom VARCHAR warisan DataLab (mis. `data_products.source`) dihubungkan ke master lewat **FK pada kolom kode**, sehingga kode warisan tidak perlu diubah tipe datanya.

| # | Tabel | Status | Isi seed |
|---|---|---|---|
| M1 | `roles` | [BARU] | PUBLIC, USER, ANALYST, DATA_ENGINEER, ADMIN |
| M2 | `users` | [BARU] | kosong; admin pertama dibuat `scripts/create_admin.py` (hash sandi tidak disimpan di SQL) |
| M3 | `satellite_sources` | [BARU] | SENTINEL1, MODIS, GPM, FUSION |
| M4 | `spectral_bands` | [BARU] | VV, VH, FLOOD, NDVI, NDWI, RAIN_24H, RAIN_72H, RAIN_7D, RAIN_30D, WATER_PCT, WATER_CHANGE |
| M5 | `administrative_regions` | [BARU] | COD-AB level 2–3 Kabupaten Lebak |
| M6 | `regions_of_interest` | [UBAH] | AOI GMLS + region dataset |
| M7 | `processing_stages` | [WARIS] | tahap S1/MODIS/GPM/FUSION/PREVIEW + HYDROMET_AGGREGATE, ALERT_CHECK, WATER_CHANGE |
| M8 | `quality_thresholds` | [BARU] | menggantikan `processing_rules` |
| M9 | `disaster_types` | [BARU] | BANJIR, BANJIR_BANDANG, LONGSOR, KEKERINGAN |
| M10 | `alert_rules` | [BARU] | ambang BMKG + longsor (nonaktif) |
| M11 | `fusion_strategies` | [BARU] | CO_OCCURRENCE, FULL_COVERAGE, HYBRID |
| M12 | `report_types` | [BARU] | HYDROMET_WEEKLY, HYDROMET_MONTHLY, DATAHEALTH_WEEKLY, DATAHEALTH_MONTHLY |

Ditambah satu tabel konfigurasi `app_settings` (key–value, tidak dihitung sebagai master).

### 3.1 `roles`

| Kolom | Tipe | Keterangan |
|---|---|---|
| `role_id` | SMALLSERIAL PK | |
| `role_code` | VARCHAR(20) UNIQUE NOT NULL | AK |
| `role_name` | VARCHAR(50) NOT NULL | Label UI (Indonesia) |
| `db_role` | VARCHAR(40) UNIQUE NOT NULL | `monitor_public` … `monitor_admin` |
| `requires_login` | BOOLEAN NOT NULL | false hanya untuk PUBLIC |
| `description` | TEXT | |

### 3.2 `users`

| Kolom | Tipe | Keterangan |
|---|---|---|
| `user_id` | SERIAL PK | |
| `role_id` | SMALLINT FK → roles NOT NULL | CHECK role ≠ PUBLIC (lewat trigger seed) |
| `username` | VARCHAR(50) UNIQUE NOT NULL | AK, `^[a-z0-9_.]{3,50}$` |
| `password_hash` | VARCHAR(255) NOT NULL | bcrypt, cost 12 |
| `full_name` | VARCHAR(100) NOT NULL | |
| `organization` | VARCHAR(100) | GMLS, BPBD, kampus, … |
| `is_active` | BOOLEAN NOT NULL DEFAULT true | Akun dinonaktifkan, tidak dihapus |
| `failed_login_count` | SMALLINT NOT NULL DEFAULT 0 | Kunci sementara setelah 5 kali |
| `locked_until` | TIMESTAMPTZ | |
| `last_login_at` | TIMESTAMPTZ | |
| `created_by` | INT FK → users | |
| `created_at`, `updated_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |

### 3.3 `satellite_sources`

| Kolom | Tipe | Keterangan |
|---|---|---|
| `source_id` | SMALLSERIAL PK | |
| `source_code` | VARCHAR(20) UNIQUE NOT NULL | dirujuk oleh kolom `source` warisan |
| `source_name` | VARCHAR(100) NOT NULL | |
| `provider` | VARCHAR(50) | ESA/CDSE, NASA LANCE/LAADS, NASA GES DISC |
| `sensor_type` | VARCHAR(20) | SAR, OPTICAL, PRECIPITATION, DERIVED |
| `spatial_resolution_m` | NUMERIC(8,1) | 10 / 250 / 11000 |
| `nominal_revisit_days` | NUMERIC(4,1) | S1 12 (satu satelit) — angka nyata diambil dari kueri |
| `products` | TEXT | GRD IW / MCDWD_L3_NRT, MOD09A1, MOD09GA / GPM_3IMERGDF, DL, DE |

### 3.4 `spectral_bands`

| Kolom | Tipe | Keterangan |
|---|---|---|
| `band_id` | SMALLSERIAL PK | |
| `source_id` | SMALLINT FK → satellite_sources NOT NULL | |
| `band_code` | VARCHAR(20) UNIQUE NOT NULL | AK |
| `band_name` | VARCHAR(100) NOT NULL | Label UI |
| `unit` | VARCHAR(20) | dB, index, %, mm |
| `valid_min`, `valid_max` | NUMERIC | Dipakai validasi `region_observations`. Diisi **batas fisik**, bukan nilai lazim, supaya hanya data rusak yang ditolak: VV/VH −60..30 dB, NDVI/NDWI −1..1, persen 0..100, hujan 24h/72h/7d/30d ≤ 2000/4000/6000/10000 mm (rekor dunia WMO dibulatkan ke atas) |
| `aggregation` | VARCHAR(20) NOT NULL | `MEAN` (hujan, NDVI, NDWI), `FRACTION` (FLOOD, WATER_PCT) |

### 3.5 `administrative_regions`

| Kolom | Tipe | Keterangan |
|---|---|---|
| `region_id` | SERIAL PK | |
| `parent_region_id` | INT FK → administrative_regions | NULL untuk kabupaten |
| `pcode` | VARCHAR(20) UNIQUE NOT NULL | AK, P-code COD-AB (mis. `ID3602xxx`) |
| `region_name` | VARCHAR(100) NOT NULL | |
| `admin_level` | SMALLINT NOT NULL CHECK IN (2,3) | 2 kabupaten, 3 kecamatan |
| `in_aoi` | BOOLEAN NOT NULL DEFAULT false | Kecamatan cakupan GMLS (M8) |
| `geom` | GEOMETRY(MultiPolygon, 4326) NOT NULL | |
| `area_km2` | NUMERIC(10,2) GENERATED ALWAYS AS (ST_Area(geom::geography)/1e6) STORED | |
| `source_dataset` | VARCHAR(100) NOT NULL | `COD-AB IDN 2020 (BPS/OCHA)` |

CHECK: `admin_level = 3` ⇒ `parent_region_id IS NOT NULL`. `in_aoi` hanya boleh true pada level 3.

### 3.6 `regions_of_interest` [UBAH]

Skema DataLab dipertahankan (FK dari `datasets`, `satellite_scenes`, `nasa_scenes`, `fusion_products`). Perubahan:

| Perubahan | Alasan |
|---|---|
| `+ admin_region_id INT FK → administrative_regions NULL` | Bila ROI = satu kecamatan |
| `+ is_monitor_aoi BOOLEAN DEFAULT false`, UNIQUE parsial `WHERE is_monitor_aoi` | Tepat satu ROI = AOI GMLS (bbox dari `ST_Envelope(ST_Union(geom))` kecamatan `in_aoi`) |
| `source` dibatasi `SEEDER` / `SYSTEM` | Wilayah buatan pengguna dihapus (M27) |
| Endpoint geocoding dan `POST /api/regions` dihapus | |

### 3.7 `processing_stages` [WARIS]

Ditambah baris: `HYDROMET_AGGREGATE` (HA), `ALERT_CHECK` (AC), `WATER_CHANGE` (WC), `REPORT_BUILD` (RB) dengan `stage_order` 10–13. Ditambah `source_code FK → satellite_sources NULL` (NULL = lintas sumber).

### 3.8 `quality_thresholds`

| Kolom | Tipe | Keterangan |
|---|---|---|
| `threshold_id` | SMALLSERIAL PK | |
| `band_id` | SMALLINT FK → spectral_bands NOT NULL | |
| `metric_name` | VARCHAR(40) NOT NULL | `quality_score`, `nodata_percent`, `valid_fraction`, `speckle_index` |
| `warn_below`, `fail_below` | NUMERIC | |
| `warn_above`, `fail_above` | NUMERIC | |
| `reference` | VARCHAR(150) | Rujukan |
| `is_active` | BOOLEAN NOT NULL DEFAULT true | |
| UNIQUE | (`band_id`, `metric_name`) | |

Seed: VV/VH `quality_score` fail < 60 (konstanta DataLab), `valid_fraction` MODIS/GPM warn < 0,5, fail < 0,1. Kode `module6_analytics.py` diubah agar membaca tabel ini, bukan konstanta; tabel ini **satu-satunya** sumber ambang — `quality_settings.min_quality_score` per dataset warisan DataLab dihapus. `warn_below` menghasilkan flag `WARNING`. **Bobot skor 50/30/20 tetap konstanta di kode** — bobot bukan ambang.

### 3.9 `disaster_types`

| Kolom | Tipe | Keterangan |
|---|---|---|
| `disaster_type_id` | SMALLSERIAL PK | |
| `type_code` | VARCHAR(30) UNIQUE NOT NULL | |
| `type_name` | VARCHAR(100) NOT NULL | |
| `category` | VARCHAR(30) NOT NULL DEFAULT 'HIDROMETEOROLOGI' | |
| `indicator_bands` | VARCHAR(100) | Teks informatif: `RAIN_24H, VH` |
| `is_active` | BOOLEAN NOT NULL DEFAULT true | Admin bisa menambah jenis (uji adaptability) |

### 3.10 `alert_rules`

| Kolom | Tipe | Keterangan |
|---|---|---|
| `rule_id` | SERIAL PK | |
| `rule_code` | VARCHAR(40) UNIQUE NOT NULL | AK |
| `disaster_type_id` | SMALLINT FK → disaster_types NOT NULL | |
| `band_id` | SMALLINT FK → spectral_bands NOT NULL | |
| `comparator` | VARCHAR(2) NOT NULL CHECK IN ('>=','>','<=','<') | |
| `threshold_value` | NUMERIC(8,2) | Boleh NULL hanya bila aturan nonaktif: `CHECK (NOT is_active OR threshold_value IS NOT NULL)` — ambang longsor belum diketahui |
| `severity` | VARCHAR(10) NOT NULL CHECK IN ('INFO','WARNING','CRITICAL') | |
| `reference_source` | VARCHAR(150) NOT NULL | |
| `is_active` | BOOLEAN NOT NULL DEFAULT true | |
| `updated_by` | INT FK → users | |
| `updated_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |

Seed:

| rule_code | Bencana | Band | Ambang | Severity | Rujukan | Aktif |
|---|---|---|---|---|---|---|
| FLOOD_RAIN24_HEAVY | BANJIR | RAIN_24H | ≥ 50 mm | INFO | BMKG (hujan lebat) | ya |
| FLOOD_RAIN24_VHEAVY | BANJIR | RAIN_24H | ≥ 100 mm | WARNING | BMKG (sangat lebat) | ya |
| FLOOD_RAIN24_EXTREME | BANJIR | RAIN_24H | ≥ 150 mm | CRITICAL | BMKG (ekstrem) | ya |
| LANDSLIDE_RAIN72 | LONGSOR | RAIN_72H | *diisi dari literatur* | WARNING | — | **tidak** |

> Nilai GPM adalah rata-rata sel ~10 km per kecamatan, sehingga lebih rendah dari pembacaan pos hujan. Ambang BMKG di atas adalah titik awal; kalibrasinya dibahas dengan `v_evaluasi_alert` (§7).

### 3.11 `fusion_strategies`

`strategy_id` SMALLSERIAL PK, `strategy_code` VARCHAR(20) UNIQUE, `download_axis` TEXT, `assemble_axis` TEXT, `description` TEXT. CHECK warisan `datasets.fusion_strategy` dan `fusion_products.fusion_strategy` diganti FK ke `strategy_code`.

### 3.12 `report_types`

| Kolom | Tipe | Keterangan |
|---|---|---|
| `report_type_id` | SMALLSERIAL PK | |
| `report_code` | VARCHAR(30) UNIQUE NOT NULL | |
| `report_name` | VARCHAR(100) NOT NULL | |
| `period` | VARCHAR(10) NOT NULL CHECK IN ('WEEKLY','MONTHLY') | |
| `audience_role_id` | SMALLINT FK → roles NOT NULL | ANALYST atau DATA_ENGINEER |
| `template_version` | VARCHAR(10) NOT NULL | |

### `app_settings` (konfigurasi)

`setting_key` VARCHAR(50) PK, `setting_value` JSONB NOT NULL, `description` TEXT, `updated_by` INT FK → users, `updated_at` TIMESTAMPTZ. Kunci: `live.max_areas` (5), `live.retention_max` (60), `report.timezone` (`Asia/Jakarta`), `water.vh_threshold_db` (−20).

---

## 4. Tabel Transaksi

### 4.1 Diwariskan dari DataLab

| Tabel | Status | Perubahan |
|---|---|---|
| `datasets` | [UBAH] | `+ created_by INT FK → users`; `+ is_system BOOLEAN` (dataset sistem disembunyikan dari Katalog); `required_tiers` hanya nama tier D14; CHECK `dataset_kind IN ('STANDARD','LIVE_AREA')` (LIVE dihapus); `fusion_strategy` FK → fusion_strategies |
| `dataset_source_config` | [UBAH] | `source_name` FK → satellite_sources.source_code |
| `dataset_jobs`, `scene_job_state` | [WARIS] | `dataset_jobs.job_type` + nilai `HYDROMET_DAILY` |
| `satellite_scenes` | [UBAH] | `+ is_valid BOOLEAN DEFAULT true`, `+ invalidated_by`, `+ invalidated_at`, `+ invalid_reason` (soft delete Admin, M24) |
| `nasa_scenes` | [UBAH] | `+ run_type VARCHAR(5) CHECK IN ('F','L','E') NULL` (GPM, M6); `+ is_valid` dkk. seperti di atas; `source` FK → satellite_sources.source_code |
| `processing_jobs` | [UBAH] | Kolom warisan `parameters_json JSONB DEFAULT '{}'` dipakai untuk parameter (versi software, window Lee, run GPM, threshold); **`scene_id` jadi NULLABLE, `+ nasa_scene_id BIGINT FK → nasa_scenes`, CHECK paling banyak satu terisi** — job S1 berjangkar scene, job MODIS/GPM berjangkar granule, job FUSION tanpa jangkar (M30) |
| `processing_logs` | [WARIS] | |
| `data_products` | [UBAH] | `source` FK → satellite_sources.source_code; **`scene_id` jadi NULLABLE, `+ nasa_scene_id BIGINT FK → nasa_scenes`, CHECK `chk_dprods_single_origin`: SENTINEL1 → `scene_id`, MODIS/GPM → `nasa_scene_id`, FUSION → keduanya NULL (asalnya di `fusion_products` + `data_lineage`)** (M30). Baris palsu `NASA_AUX_*` di `satellite_scenes` tidak dibuat lagi |
| `data_lineage` | [WARIS] | |
| `quality_metrics` | [WARIS] | |
| `fusion_products` | [UBAH] | `fusion_strategy` FK → fusion_strategies |
| `live_areas` | [UBAH] | CHECK `retention` 1–60 (DataLab 1–12); `+ updated_by` |
| `live_scenes` | [UBAH] | kolom `metrics` **dihapus**, angka dipindah ke `live_scene_metrics` (M31); deskriptor teks metrik (run IMERG, periode komposit, tanggal observasi) disimpan di `source_status[sumber].meta`; `interpretations`, `source_status`, `previews` tetap JSONB (teks tampilan, tidak dikueri) |
| `live_events` | [WARIS] | |
| `cleanup_operations` | [WARIS] | |
| `alert_events` (DataLab) | [UBAH] | **diganti nama** → `quality_alerts` (isi: skor QA < 60). Nama `alert_events` dipakai untuk alert hujan |

### 4.2 Tabel transaksi baru

#### 4.2.1 `region_observations` — nilai harian per kecamatan (M7)

| Kolom | Tipe | Keterangan |
|---|---|---|
| `obs_id` | BIGSERIAL PK | |
| `region_id` | INT FK → administrative_regions NOT NULL | level 3 |
| `band_id` | SMALLINT FK → spectral_bands NOT NULL | |
| `obs_date` | DATE NOT NULL | hari UTC (M28) |
| `value` | NUMERIC(10,4) | NULL bila tidak ada piksel valid |
| `valid_fraction` | NUMERIC(5,4) NOT NULL | 0–1, bagian poligon yang punya piksel valid |
| `source_product_id` | BIGINT FK → data_products | COG asal (lineage, RM2) |
| `run_type` | VARCHAR(5) | GPM: F/L/E |
| `job_id` | BIGINT FK → dataset_jobs | |
| `computed_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| UNIQUE | (`region_id`, `band_id`, `obs_date`) | Upsert idempoten; Final menimpa Late (§PIPELINE 3.4) |

CHECK `value` di antara `spectral_bands.valid_min/max` ditegakkan oleh trigger `trg_obs_range`.

#### 4.2.2 `alert_events` — alert hujan

| Kolom | Tipe | Keterangan |
|---|---|---|
| `alert_id` | BIGSERIAL PK | |
| `rule_id` | INT FK → alert_rules NOT NULL | |
| `region_id` | INT FK → administrative_regions NOT NULL | |
| `obs_id` | BIGINT FK → region_observations NOT NULL | nilai pemicu |
| `observation_date` | DATE NOT NULL | |
| `observed_value` | NUMERIC(10,4) NOT NULL | salinan saat terpicu (aturan bisa berubah kemudian) |
| `threshold_value` | NUMERIC(8,2) NOT NULL | salinan ambang saat terpicu |
| `severity` | VARCHAR(10) NOT NULL | salinan |
| `triggered_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| `acknowledged_by` | INT FK → users | |
| `acknowledged_at` | TIMESTAMPTZ | |
| `ack_note` | VARCHAR(500) | |
| UNIQUE | (`rule_id`, `region_id`, `observation_date`) | idempoten saat job diulang |
| CHECK | `(acknowledged_by IS NULL) = (acknowledged_at IS NULL)` | |

#### 4.2.3 `disaster_events`

| Kolom | Tipe | Keterangan |
|---|---|---|
| `event_id` | BIGSERIAL PK | |
| `disaster_type_id` | SMALLINT FK → disaster_types NOT NULL | |
| `region_id` | INT FK → administrative_regions NOT NULL | kecamatan |
| `village_name` | VARCHAR(100) | desa sebagai teks (COD-AB level 4 tidak tersedia) |
| `location` | GEOMETRY(Point, 4326) | opsional, dipilih di peta |
| `event_date` | DATE NOT NULL | |
| `event_end_date` | DATE | CHECK ≥ `event_date` |
| `description` | TEXT NOT NULL | |
| `impact_summary` | VARCHAR(500) | rumah terdampak, akses jalan, dll. — tanpa data pribadi |
| `info_source` | VARCHAR(30) NOT NULL CHECK IN ('GMLS','BPBD_LEBAK','BNPB_DIBI','MEDIA','LAINNYA') | |
| `source_reference` | TEXT | URL/nomor dokumen |
| `is_verified` | BOOLEAN NOT NULL DEFAULT false | |
| `verified_by` | INT FK → users | |
| `recorded_by` | INT FK → users NOT NULL | |
| `recorded_at`, `updated_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| `deleted_at` | TIMESTAMPTZ | soft delete |

#### 4.2.4 `generated_reports`

| Kolom | Tipe | Keterangan |
|---|---|---|
| `report_id` | BIGSERIAL PK | |
| `report_type_id` | SMALLINT FK → report_types NOT NULL | |
| `period_start`, `period_end` | DATE NOT NULL | Senin–Minggu / tgl 1–akhir bulan (WIB) |
| `file_path` | TEXT NOT NULL | |
| `file_size_bytes` | BIGINT NOT NULL | |
| `checksum_sha256` | CHAR(64) NOT NULL | |
| `status` | VARCHAR(10) NOT NULL CHECK IN ('READY','FAILED','SUPERSEDED') | |
| `error_message` | TEXT | |
| `generated_by` | INT FK → users | NULL = scheduler |
| `generated_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| UNIQUE parsial | (`report_type_id`, `period_start`) WHERE status = 'READY' | regenerasi menandai yang lama SUPERSEDED |

#### 4.2.5 `user_activity_logs` — log aplikasi (login, unduhan, aksi)

| Kolom | Tipe | Keterangan |
|---|---|---|
| `log_id` | BIGSERIAL PK | |
| `user_id` | INT FK → users | NULL untuk login gagal dengan username tak dikenal / PUBLIC |
| `username_attempted` | VARCHAR(50) | untuk login gagal |
| `action` | VARCHAR(30) NOT NULL | `LOGIN_SUCCESS`, `LOGIN_FAILED`, `LOGOUT`, `DOWNLOAD_PRODUCT`, `DOWNLOAD_DATASET`, `DOWNLOAD_FUSION`, `DOWNLOAD_REPORT`, `EXPORT_CSV`, `API_REQUEST` (request bertoken), `CREATE_DATASET`, `TRIGGER_INGEST`, … |
| `target_type` | VARCHAR(40) | `data_products`, `datasets`, `generated_reports`, … |
| `target_id` | BIGINT | |
| `bytes_sent` | BIGINT | unduhan |
| `ip_address` | INET | |
| `user_agent` | VARCHAR(255) | |
| `detail` | JSONB | |
| `logged_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |

Tabel ini **append-only**: tidak ada role yang punya UPDATE/DELETE.

#### 4.2.6 `audit_log` — perubahan data (trigger)

| Kolom | Tipe | Keterangan |
|---|---|---|
| `audit_id` | BIGSERIAL PK | |
| `table_name` | VARCHAR(63) NOT NULL | |
| `row_pk` | TEXT NOT NULL | |
| `operation` | CHAR(1) NOT NULL CHECK IN ('I','U','D') | |
| `old_data`, `new_data` | JSONB | `password_hash` disensor |
| `changed_columns` | TEXT[] | untuk U |
| `app_user_id` | INT | dari `current_setting('app.user_id', true)`; NULL bila lewat psql |
| `db_user` | NAME NOT NULL DEFAULT current_user | |
| `changed_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |

Append-only, sama seperti di atas.

#### 4.2.7 `live_scene_metrics` — metrik scene Live (M31)

| Kolom | Tipe | Keterangan |
|---|---|---|
| `metric_id` | BIGSERIAL PK | |
| `live_scene_id` | BIGINT FK → live_scenes NOT NULL | |
| `band_id` | SMALLINT FK → spectral_bands NOT NULL | VV, VH, WATER_PCT, FLOOD, NDVI, NDWI, RAIN_24H/72H/7D, WATER_CHANGE |
| `metric_name` | VARCHAR(30) NOT NULL | `mean`, `max`, `pct_below_threshold`, `threshold_db`, `valid_pct`, `cloud_pct`, `flood_pct`, `recurring_pct`, `water_pct`, `age_days_median`, `lookback_days`, `frames`, `valid_pixels`, `new_km2`, `receded_km2`, `persistent_km2`, `same_orbit` (pemetaan lengkap: `etl/live_metrics.METRIC_ROWS`) |
| `value` | NUMERIC(12,4) | |
| `source_date` | DATE | tanggal data sumber (MODIS/GPM bisa "terdekat") |
| `ref_live_scene_id` | BIGINT FK → live_scenes | pembanding untuk WATER_CHANGE |
| UNIQUE | (`live_scene_id`, `band_id`, `metric_name`) | |

Baris tetap ada setelah berkas scene dihapus retensi, sehingga grafik dan prakiraan tetap hidup (prinsip DataLab D25 dipertahankan, kini dalam bentuk 1NF).

#### 4.2.8 `api_tokens` — token API pribadi (M33)

| Kolom | Tipe | Keterangan |
|---|---|---|
| `token_id` | SERIAL PK | |
| `user_id` | INT FK → users NOT NULL | role token = role pemilik saat dipakai |
| `token_name` | VARCHAR(60) NOT NULL | "skrip training", "integrasi SIGAP" |
| `token_prefix` | CHAR(8) UNIQUE NOT NULL | ditampilkan untuk identifikasi, mis. `trn_4f2a` |
| `token_hash` | CHAR(64) NOT NULL | SHA-256 dari token; token utuh hanya ditampilkan sekali saat dibuat |
| `scopes` | VARCHAR(20) NOT NULL CHECK IN ('READ','READ_DOWNLOAD') | tanpa scope tulis |
| `expires_at` | TIMESTAMPTZ NOT NULL | maksimal 180 hari |
| `last_used_at` | TIMESTAMPTZ | |
| `revoked_at` | TIMESTAMPTZ | |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |

Hanya USER ke atas yang dapat membuat token, untuk dirinya sendiri. Token tidak bisa melakukan aksi tulis (acknowledge, CRUD kejadian, buat dataset); aksi tulis tetap lewat sesi web. Setiap pemakaian token tercatat di `user_activity_logs`: satu baris per request (`action = 'API_REQUEST'`, `detail = {auth: 'token', token_id, method, path, status}`), atau baris `DOWNLOAD_*` dengan `detail.auth = 'token'` untuk unduhan.

### 4.3 Estimasi volume (backfill 2023–2025, asumsi 9 kecamatan AOI)

| Tabel | Perkiraan baris |
|---|---|
| `region_observations` | 9 kec × 1.096 hari × (5 band GPM + 3 band MODIS) ≈ **79.000** |
| `nasa_scenes` | ±1.096 GPM + ±1.096 MCDWD + ±140 MOD09A1 ≈ 2.300 |
| `alert_events` | puluhan–ratusan (tergantung kalibrasi) |
| `processing_jobs`, `processing_logs`, `data_products`, `data_lineage` | ribuan–puluhan ribu |
| `disaster_events` | sesuai catatan GMLS + input Analyst (impor BNPB DIBI opsional, M36) |
| `satellite_scenes` (S1, dari Live + dataset) | bergantung dataset yang dibuat Data Engineer |

Syarat ≥ 100 record transaksi terpenuhi dengan margin besar oleh `region_observations` saja.

---

## 5. Normalisasi (Logical Design)

Pembuktian dilakukan untuk tiga kelompok; bab skripsi menuliskan tabel UNF → 3NF lengkap.

### 5.1 Observasi hujan

**UNF** — satu baris laporan harian: `{tanggal, kabupaten, kecamatan, pcode, luas, [rain_24h, rain_72h, rain_7d, rain_30d], satuan[], run_type, granule, url, checksum}` (grup berulang per band).

- **1NF:** grup band dipecah menjadi satu baris per (kecamatan, tanggal, band).
- **2NF:** kunci komposit (pcode, tanggal, band). `kecamatan`, `kabupaten`, `luas` hanya bergantung pada `pcode` → `administrative_regions`. `satuan`, `valid_min/max` hanya bergantung pada `band` → `spectral_bands`. `granule`, `url`, `checksum` bergantung pada (tanggal, produk) → `nasa_scenes` / `data_products`.
- **3NF:** `kabupaten` bergantung transitif pada `kecamatan` → self-reference `parent_region_id`. Sensor/penyedia bergantung pada band → `satellite_sources`.

**Hasil:** `region_observations`, `administrative_regions`, `spectral_bands`, `satellite_sources`, `nasa_scenes`, `data_products`.

### 5.2 Alert dan kejadian

**UNF** — catatan GMLS: `{tanggal, jenis bencana, kategori, kecamatan, desa, hujan saat itu, ambang, sumber ambang, status dibaca, dibaca oleh, nama pembaca}`.

- **2NF/3NF:** atribut ambang dan sumbernya bergantung pada aturan → `alert_rules`; kategori bergantung pada jenis → `disaster_types`; nama pembaca bergantung pada `user_id` → `users`; nilai hujan dirujuk lewat `obs_id`.
- **Pengecualian disengaja:** `alert_events.observed_value/threshold_value/severity` adalah **salinan historis**, bukan pelanggaran 3NF — nilainya dibekukan saat alert terpicu sehingga perubahan `alert_rules` kemudian tidak menulis ulang sejarah.

### 5.3 Pengguna dan akses

**UNF** — `{username, nama, role, hak akses[], login terakhir, unduhan[]}` → `users`, `roles`, `user_activity_logs`; hak akses tidak disimpan sebagai data, melainkan sebagai GRANT pada role PostgreSQL (§8).

Kelompok warisan DataLab (scene → product → lineage) setelah perbaikan M30 dan M31:

| Temuan di DataLab | Bentuk normal yang dilanggar | Penyelesaian |
|---|---|---|
| Baris palsu `NASA_AUX_*` agar `data_products.scene_id` terisi | Integritas semantik: fakta MODIS/GPM menempel pada entitas S1 | `nasa_scene_id` + CHECK satu sumber (M30) |
| `live_scenes.metrics` JSONB dikueri untuk grafik | 1NF (atribut bernilai jamak) | `live_scene_metrics` (M31) |
| `dataset_source_config.processing_levels`, `datasets.preview_options`, `required_tiers`, `live_scenes.s1_product_ids` (array) | 1NF di tingkat logikal | **Model logikal**: entitas `DatasetSourceLevel`, `DatasetPreviewOption`, `LiveSceneS1Frame`. **Model fisik**: diterjemahkan ke `TEXT[]` PostgreSQL (M32) — selalu dibaca/ditulis utuh, tidak pernah difilter per elemen, ukurannya ≤ 3 elemen |
| `processing_jobs.parameters`, `datasets.quality_settings`, `datasets.fusion_grid` (JSONB) | 1NF di tingkat logikal | Diperlakukan sebagai atribut komposit konfigurasi; disimpan JSONB karena isinya berbeda per tahap/sumber dan hanya dibaca utuh untuk reproduksibilitas (M32) |

Dengan demikian ERD logikal di skripsi sepenuhnya 3NF; penyimpangan hanya ada di physical design dan masing-masing punya alasan tertulis.

---

## 6. DDL Inti (tabel baru)

```sql
CREATE TABLE roles (
  role_id        SMALLSERIAL PRIMARY KEY,
  role_code      VARCHAR(20) UNIQUE NOT NULL,
  role_name      VARCHAR(50) NOT NULL,
  db_role        VARCHAR(40) UNIQUE NOT NULL,
  requires_login BOOLEAN NOT NULL,
  description    TEXT
);

CREATE TABLE users (
  user_id            SERIAL PRIMARY KEY,
  role_id            SMALLINT NOT NULL REFERENCES roles,
  username           VARCHAR(50) UNIQUE NOT NULL CHECK (username ~ '^[a-z0-9_.]{3,50}$'),
  password_hash      VARCHAR(255) NOT NULL,
  full_name          VARCHAR(100) NOT NULL,
  organization       VARCHAR(100),
  is_active          BOOLEAN NOT NULL DEFAULT true,
  failed_login_count SMALLINT NOT NULL DEFAULT 0,
  locked_until       TIMESTAMPTZ,
  last_login_at      TIMESTAMPTZ,
  created_by         INT REFERENCES users,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE satellite_sources (
  source_id            SMALLSERIAL PRIMARY KEY,
  source_code          VARCHAR(20) UNIQUE NOT NULL,
  source_name          VARCHAR(100) NOT NULL,
  provider             VARCHAR(50),
  sensor_type          VARCHAR(20),
  spatial_resolution_m NUMERIC(8,1),
  nominal_revisit_days NUMERIC(4,1),
  products             TEXT
);

CREATE TABLE spectral_bands (
  band_id     SMALLSERIAL PRIMARY KEY,
  source_id   SMALLINT NOT NULL REFERENCES satellite_sources,
  band_code   VARCHAR(20) UNIQUE NOT NULL,
  band_name   VARCHAR(100) NOT NULL,
  unit        VARCHAR(20),
  valid_min   NUMERIC,
  valid_max   NUMERIC,
  aggregation VARCHAR(20) NOT NULL CHECK (aggregation IN ('MEAN','FRACTION'))
);

CREATE TABLE administrative_regions (
  region_id        SERIAL PRIMARY KEY,
  parent_region_id INT REFERENCES administrative_regions,
  pcode            VARCHAR(20) UNIQUE NOT NULL,
  region_name      VARCHAR(100) NOT NULL,
  admin_level      SMALLINT NOT NULL CHECK (admin_level IN (2,3)),
  in_aoi           BOOLEAN NOT NULL DEFAULT false,
  geom             GEOMETRY(MultiPolygon, 4326) NOT NULL,
  area_km2         NUMERIC(10,2) GENERATED ALWAYS AS (ST_Area(geom::geography) / 1e6) STORED,
  source_dataset   VARCHAR(100) NOT NULL,
  CHECK (admin_level = 2 OR parent_region_id IS NOT NULL),
  CHECK (NOT in_aoi OR admin_level = 3)
);

CREATE TABLE disaster_types (
  disaster_type_id SMALLSERIAL PRIMARY KEY,
  type_code        VARCHAR(30) UNIQUE NOT NULL,
  type_name        VARCHAR(100) NOT NULL,
  category         VARCHAR(30) NOT NULL DEFAULT 'HIDROMETEOROLOGI',
  indicator_bands  VARCHAR(100),
  is_active        BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE alert_rules (
  rule_id          SERIAL PRIMARY KEY,
  rule_code        VARCHAR(40) UNIQUE NOT NULL,
  disaster_type_id SMALLINT NOT NULL REFERENCES disaster_types,
  band_id          SMALLINT NOT NULL REFERENCES spectral_bands,
  comparator       VARCHAR(2) NOT NULL CHECK (comparator IN ('>=','>','<=','<')),
  threshold_value  NUMERIC(8,2),
  severity         VARCHAR(10) NOT NULL CHECK (severity IN ('INFO','WARNING','CRITICAL')),
  reference_source VARCHAR(150) NOT NULL,
  is_active        BOOLEAN NOT NULL DEFAULT true,
  updated_by       INT REFERENCES users,
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (NOT is_active OR threshold_value IS NOT NULL)
);

CREATE TABLE region_observations (
  obs_id            BIGSERIAL PRIMARY KEY,
  region_id         INT NOT NULL REFERENCES administrative_regions,
  band_id           SMALLINT NOT NULL REFERENCES spectral_bands,
  obs_date          DATE NOT NULL,
  value             NUMERIC(10,4),
  valid_fraction    NUMERIC(5,4) NOT NULL CHECK (valid_fraction BETWEEN 0 AND 1),
  source_product_id BIGINT REFERENCES data_products,
  run_type          VARCHAR(5) CHECK (run_type IN ('F','L','E')),
  job_id            BIGINT REFERENCES dataset_jobs,
  computed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (region_id, band_id, obs_date)
);

CREATE TABLE alert_events (
  alert_id         BIGSERIAL PRIMARY KEY,
  rule_id          INT NOT NULL REFERENCES alert_rules,
  region_id        INT NOT NULL REFERENCES administrative_regions,
  obs_id           BIGINT NOT NULL REFERENCES region_observations,
  observation_date DATE NOT NULL,
  observed_value   NUMERIC(10,4) NOT NULL,
  threshold_value  NUMERIC(8,2) NOT NULL,
  severity         VARCHAR(10) NOT NULL,
  triggered_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  acknowledged_by  INT REFERENCES users,
  acknowledged_at  TIMESTAMPTZ,
  ack_note         VARCHAR(500),
  UNIQUE (rule_id, region_id, observation_date),
  CHECK ((acknowledged_by IS NULL) = (acknowledged_at IS NULL))
);

CREATE TABLE disaster_events (
  event_id         BIGSERIAL PRIMARY KEY,
  disaster_type_id SMALLINT NOT NULL REFERENCES disaster_types,
  region_id        INT NOT NULL REFERENCES administrative_regions,
  village_name     VARCHAR(100),
  location         GEOMETRY(Point, 4326),
  event_date       DATE NOT NULL,
  event_end_date   DATE CHECK (event_end_date IS NULL OR event_end_date >= event_date),
  description      TEXT NOT NULL CHECK (length(description) BETWEEN 10 AND 4000),
  impact_summary   VARCHAR(500),
  info_source      VARCHAR(30) NOT NULL
                   CHECK (info_source IN ('GMLS','BPBD_LEBAK','BNPB_DIBI','MEDIA','LAINNYA')),
  source_reference TEXT,
  is_verified      BOOLEAN NOT NULL DEFAULT false,
  verified_by      INT REFERENCES users,
  recorded_by      INT NOT NULL REFERENCES users,
  recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at       TIMESTAMPTZ
);

CREATE TABLE report_types (
  report_type_id   SMALLSERIAL PRIMARY KEY,
  report_code      VARCHAR(30) UNIQUE NOT NULL,
  report_name      VARCHAR(100) NOT NULL,
  period           VARCHAR(10) NOT NULL CHECK (period IN ('WEEKLY','MONTHLY')),
  audience_role_id SMALLINT NOT NULL REFERENCES roles,
  template_version VARCHAR(10) NOT NULL
);

CREATE TABLE generated_reports (
  report_id       BIGSERIAL PRIMARY KEY,
  report_type_id  SMALLINT NOT NULL REFERENCES report_types,
  period_start    DATE NOT NULL,
  period_end      DATE NOT NULL CHECK (period_end >= period_start),
  file_path       TEXT NOT NULL,
  file_size_bytes BIGINT NOT NULL,
  checksum_sha256 CHAR(64) NOT NULL,
  status          VARCHAR(10) NOT NULL CHECK (status IN ('READY','FAILED','SUPERSEDED')),
  error_message   TEXT,
  generated_by    INT REFERENCES users,
  generated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_report_ready ON generated_reports (report_type_id, period_start)
  WHERE status = 'READY';

CREATE TABLE user_activity_logs (
  log_id             BIGSERIAL PRIMARY KEY,
  user_id            INT REFERENCES users,
  username_attempted VARCHAR(50),
  action             VARCHAR(30) NOT NULL,
  target_type        VARCHAR(40),
  target_id          BIGINT,
  bytes_sent         BIGINT,
  ip_address         INET,
  user_agent         VARCHAR(255),
  detail             JSONB,
  logged_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_log (
  audit_id        BIGSERIAL PRIMARY KEY,
  table_name      VARCHAR(63) NOT NULL,
  row_pk          TEXT NOT NULL,
  operation       CHAR(1) NOT NULL CHECK (operation IN ('I','U','D')),
  old_data        JSONB,
  new_data        JSONB,
  changed_columns TEXT[],
  app_user_id     INT,
  db_user         NAME NOT NULL DEFAULT current_user,
  changed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`quality_thresholds`, `fusion_strategies`, `app_settings`, `live_scene_metrics`, `api_tokens` mengikuti §3–§4 secara langsung.

### Aturan berkas skema (M34)

- **Satu berkas** `database/monitor_schema.sql` membangun seluruh skema (warisan + baru) dari DB kosong. Default nama DB: `themonitor`. Di Windows/PowerShell ketiga berkas dapat diterapkan dengan `python database/apply_schema.py` (kredensial dari `.env`). 26 migrasi DataLab tidak diikutkan; nilai enum legacy (`BRONZE`/`SILVER`/`GOLD`/`FUSION`) dan kolom yang hanya dipakai fitur terhapus tidak dibawa.
- **Setiap tabel dan kolom** wajib punya `COMMENT ON` (deskripsi, satuan, domain, contoh). Uji CI `tests/test_schema_comments.py` gagal bila ada kolom tanpa komentar.
- `tools/data_dictionary.py` membaca `information_schema` + `pg_description` + constraint dan menghasilkan:
  - `DOCS/generated/data_dictionary.md` (tabel, kolom, tipe, null, default, PK/FK/UNIQUE/CHECK, komentar);
  - `DOCS/generated/erd_physical.mmd` (Mermaid ER) untuk dirender ke gambar.
- Seed dan keamanan terpisah: `monitor_seed.sql`, `monitor_security.sql`.
- `product_tier_enum` hanya memuat nama D14 (`RAW, ALIGNED, DESPECKLED, INDICES, ACCUMULATED, COG, FUSED`); nama lama tetap diterima kode sebagai input dan dipetakan.
- Database uji (`tests/conftest.py`) dibangun dari ketiga berkas yang sama, jadi setiap run tes juga menguji skema.
- Uji: `psql -v ON_ERROR_STOP=1` ketiga berkas di DB kosong harus sukses (dijalankan di CI).

---

## 7. Index dan VIEW

### Index

| Index | Tabel | Kolom | Alasan |
|---|---|---|---|
| GiST | `administrative_regions` | `geom` | Zonal statistics, peta |
| B-tree parsial | `administrative_regions` | `(region_id) WHERE in_aoi` | Daftar kecamatan AOI |
| B-tree | `region_observations` | `(obs_date DESC, band_id)` | Statistik hari ini, tren 30 hari |
| B-tree | `region_observations` | `(region_id, band_id, obs_date)` | dari UNIQUE |
| B-tree parsial | `alert_events` | `(observation_date DESC) WHERE acknowledged_at IS NULL` | Spanduk alert aktif |
| B-tree | `disaster_events` | `(event_date, region_id) WHERE deleted_at IS NULL` | Korelasi kejadian–hujan |
| B-tree | `user_activity_logs` | `(action, logged_at DESC)` | Log login & unduhan Admin |
| B-tree | `audit_log` | `(table_name, changed_at DESC)` | Penampil audit |
| B-tree | `generated_reports` | `(report_type_id, period_start DESC)` | Daftar laporan |
| Warisan | lihat DataLab "Key Indexes" | | |

`EXPLAIN ANALYZE` lima kueri utama (statistik hari ini, tren 30 hari, alert aktif, `v_evaluasi_alert`, lineage ancestors) dijalankan sebelum dan sesudah index; hasilnya dilampirkan di bab pengujian.

### VIEW

| View | Isi | Dipakai oleh |
|---|---|---|
| `v_public_live_latest` | Scene Live terbaru per area (`status` READY/PARTIAL, belum dihapus): tanggal, `area_status`, kalimat, manifest preview | PUBLIC+ |
| `v_live_scenes_recent` | Scene Live ≤ 30 hari | USER+ |
| `v_hujan_harian_kecamatan` | Pivot `region_observations` RAIN_* per kecamatan per tanggal + kategori BMKG | USER+ |
| `v_statistik_hari_ini` | Baris `v_hujan_harian_kecamatan` untuk tanggal terakhir yang lengkap + NDVI/NDWI/FLOOD terakhir | USER+ |
| `v_alert_aktif` | `alert_events` belum di-acknowledge + nama kecamatan + aturan | USER+ |
| `v_kejadian_dan_hujan` | `disaster_events` + hujan 24h/72h/7d pada H-0, H-1, H-2 | ANALYST, ADMIN |
| `v_evaluasi_alert` | Hit / miss / false alarm per aturan (lihat di bawah) | ANALYST, ADMIN |
| `v_ringkasan_kualitas` | `quality_metrics` + `quality_alerts` + valid_fraction per sumber per minggu | DATA_ENGINEER, ADMIN |
| `v_kelengkapan_data` | Hari dengan/tanpa data per sumber (gap > 10 hari ditandai) | DATA_ENGINEER, ADMIN |
| `v_users_safe` | `users` tanpa `password_hash`, `failed_login_count`, `locked_until` | ADMIN (UI), semua role untuk join nama |
| `v_log_login`, `v_log_unduhan` | Filter `user_activity_logs` | ADMIN |

#### Definisi `v_evaluasi_alert`

```sql
CREATE VIEW v_evaluasi_alert AS
WITH ev AS (           -- kejadian banjir/longsor yang sudah terverifikasi
  SELECT e.event_id, e.region_id, e.event_date, dt.disaster_type_id
  FROM disaster_events e JOIN disaster_types dt USING (disaster_type_id)
  WHERE e.deleted_at IS NULL AND e.is_verified
),
al AS (                -- alert WARNING ke atas
  SELECT a.alert_id, a.rule_id, a.region_id, a.observation_date, r.disaster_type_id
  FROM alert_events a JOIN alert_rules r USING (rule_id)
  WHERE a.severity IN ('WARNING','CRITICAL')
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
```

Jendela 0–3 hari adalah parameter yang dibahas di skripsi. Dengan jumlah kejadian kecil, hasilnya disajikan sebagai indikasi, bukan uji statistik.

---

## 8. Keamanan (Physical Design — RM4)

Implementasi: `database/monitor_security.sql`; diuji `tests/security/grant_matrix.sql` (matriks §8.3 sel per sel) dan `tests/test_audit.py`.

### 8.1 Role PostgreSQL

```sql
-- Role berlaku untuk seluruh cluster: dibuat idempoten (DO ... IF NOT EXISTS),
-- atributnya ditegakkan ulang dengan ALTER ROLE.
CREATE ROLE monitor_app   LOGIN NOINHERIT;   -- dipakai FastAPI
CREATE ROLE monitor_etl   LOGIN;             -- dipakai scheduler/pipeline
CREATE ROLE monitor_public        NOLOGIN;
CREATE ROLE monitor_user          NOLOGIN;   GRANT monitor_public TO monitor_user;
CREATE ROLE monitor_analyst       NOLOGIN;   GRANT monitor_user   TO monitor_analyst;
CREATE ROLE monitor_data_engineer NOLOGIN;   GRANT monitor_user   TO monitor_data_engineer;
CREATE ROLE monitor_admin         NOLOGIN;   GRANT monitor_analyst, monitor_data_engineer TO monitor_admin;

GRANT monitor_public, monitor_user, monitor_analyst,
      monitor_data_engineer, monitor_admin TO monitor_app;  -- hanya boleh SET ROLE
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO monitor_public, monitor_etl;  -- eksplisit, bukan default PUBLIC
GRANT SELECT ON spatial_ref_sys TO PUBLIC;                    -- katalog PostGIS
```

`monitor_app` adalah `NOINHERIT` dan tidak diberi USAGE skema: tanpa `SET ROLE` ia **tidak** punya hak apa pun, bahkan tidak melihat tabel. Aplikasi tidak pernah terkoneksi sebagai superuser; pemilik skema (`DB_USER`) hanya dipakai skrip setup.

Sandi role LOGIN tidak ditulis di SQL. `database/apply_schema.py` (dan `tests/conftest.py`) menjalankan `ALTER ROLE … PASSWORD` dari `MONITOR_APP_PASSWORD` / `MONITOR_ETL_PASSWORD` di `.env`; lewat psql, jalankan dua `ALTER ROLE` itu setelah `monitor_security.sql`.

### 8.2 Penegakan per request

```python
# api/deps.py — satu transaksi per request, koneksi monitor_app
session.execute(text("SET LOCAL ROLE " + ROLE_TO_DB[current.role_code]))   # nama dari whitelist
session.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(current.user_id or "")})
```

`SET LOCAL` dan `set_config(..., true)` berakhir bersama transaksi, sehingga koneksi pool tidak membawa role ke request berikutnya. Transaksi diawali sebagai `monitor_public`; setelah pengguna dikenali, role diganti ke role pengguna (keanggotaan dicek terhadap `session_user` = `monitor_app`). Manager warisan yang membuka `db.session()` berkali-kali berjalan di dalam transaksi yang sama (setiap blok = SAVEPOINT).

Kerja latar yang dipicu request (thread job dataset, penghapusan fisik dataset/Live Area, siklus dan retensi Live) memakai koneksi `monitor_etl` dan baru dimulai **setelah** transaksi request di-commit.

Sebelum role pengguna diketahui, request berjalan sebagai `monitor_public`, yang tidak punya hak atas `users`/`api_tokens`. Satu-satunya jalan adalah fungsi `SECURITY DEFINER` milik `monitor_admin` (`SET search_path = public, pg_temp`, EXECUTE dicabut dari PUBLIC):

| Fungsi | Dipakai | Mengembalikan / mengubah |
|---|---|---|
| `auth_get_user(username)` | login, ganti sandi | hash bcrypt, role, `is_active`, status kunci |
| `auth_record_login(user_id, ok)` | login | sukses: reset penghitung + `last_login_at`; gagal: +1, kelima kali `locked_until = now()+15 menit` |
| `auth_session_user(user_id)` | setiap request | role + `is_active` terkini (tanpa hash) |
| `auth_get_token(prefix)` | autentikasi Bearer | hash token, scope, kedaluwarsa, pencabutan |
| `auth_change_own_password(hash)` | ganti sandi (EXECUTE: `monitor_user`) | `password_hash` baris milik `app.user_id` sesi saja; menolak nilai non-bcrypt |
| `report_audience_db_role(report_type_id)` | policy RLS §8.4 | nama role DB audiens laporan |

### 8.3 Matriks GRANT

Hak diberikan pada role terendah yang membutuhkannya; kolom di bawah adalah hak **efektif** (termasuk warisan hierarki).

| Objek | public | user | analyst | data_engineer | admin | etl |
|---|---|---|---|---|---|---|
| `v_public_live_latest` | S | S | S | S | S | — |
| `live_areas` kolom publik (`area_id, name, location_label, status, enabled, last_checked_at, deleted_at`) | S | S | S | S | S | S |
| `v_live_scenes_recent`, `v_hujan_harian_kecamatan`, `v_statistik_hari_ini`, `v_alert_aktif` | — | S | S | S | S | S |
| master referensi: `satellite_sources`, `spectral_bands`, `processing_stages`, `fusion_strategies`, `report_types` | — | S | S | S | S | S |
| `administrative_regions`, `regions_of_interest` | — | S | S | S | SIU | S |
| `alert_events` | — | S | S + U(ack) | S | SIUD | SI |
| `disaster_events` | — | — | SIU | — | SIU | — |
| `v_kejadian_dan_hujan`, `v_evaluasi_alert` | — | — | S | — | S | — |
| `region_observations` | — | S | S | S | S | SIU |
| `datasets` | — | — | — | SIU | SIUD | SIUD |
| `dataset_source_config`, `dataset_jobs`, `scene_job_state` | — | — | — | SIU | SIUD | SIU |
| `satellite_scenes`, `nasa_scenes` | — | — | — | S | SU (soft delete) | SIU |
| `data_products`, `processing_jobs` | — | — | — | S | S | SIUD |
| `data_lineage`, `quality_metrics`, `quality_alerts`, `fusion_products`, `processing_logs`, `cleanup_operations` | — | — | — | S | S | SIU |
| `v_ringkasan_kualitas`, `v_kelengkapan_data` | — | — | — | S | S | — |
| `generated_reports` | — | — | S (+ RLS) | S (+ RLS) | SIU | SIU |
| `users`, `roles` | — | — | — | — | SIU (tanpa D) | — |
| `v_users_safe` | — | S | S | S | S | — |
| `alert_rules`, `quality_thresholds`, `disaster_types`, `app_settings` | — | S | S | S | SIU | S |
| `live_areas`, `live_scenes`, `live_events`, `live_scene_metrics` | — | S | S | S | SIU | SIU |
| `api_tokens` | — | SIU (milik sendiri, RLS) | SIU (milik sendiri) | SIU (milik sendiri) | SIU | — |
| `user_activity_logs` | I | I | I | I | SI | I |
| `audit_log` | — | — | — | — | S | — (diisi trigger) |
| `v_log_login`, `v_log_unduhan` | — | — | — | — | S | — |

S = SELECT, I = INSERT, U = UPDATE, D = DELETE. "U(ack)" = `GRANT UPDATE (acknowledged_by, acknowledged_at, ack_note)` saja. `USAGE` semua sequence diberikan ke `monitor_public` (diwarisi semua role) dan `monitor_etl`; tanpa INSERT pada tabelnya, USAGE tidak memberi hak menulis apa pun. TRUNCATE tidak diberikan ke role aplikasi mana pun.

Hapus fisik data historis tidak diberikan ke role interaktif selain admin, dan UI tetap memakai soft delete. **D untuk `monitor_etl`** pada `datasets`, `data_products`, `processing_jobs` dipakai penghapusan dataset: API memeriksa bahwa pemanggil adalah pembuat dataset atau ADMIN dan menandai `status = 'DELETING'` dengan role pengguna; pipeline (`monitor_etl`) yang menghapus berkas dan barisnya. Tabel anak lain ikut lewat `ON DELETE CASCADE`, yang dijalankan PostgreSQL dengan hak pemilik tabel.

### 8.4 Row-Level Security

```sql
ALTER TABLE generated_reports ENABLE ROW LEVEL SECURITY;
CREATE POLICY rp_audience ON generated_reports FOR SELECT
  USING (pg_has_role(current_user, report_audience_db_role(report_type_id), 'MEMBER'));
CREATE POLICY rp_writers ON generated_reports FOR ALL TO monitor_admin, monitor_etl
  USING (true) WITH CHECK (true);
```

ANALYST hanya melihat laporan Hidromet, DATA_ENGINEER hanya Kesehatan Data, ADMIN (anggota keduanya) melihat semua. Ekspresi policy dievaluasi dengan hak pemanggil, sedangkan `roles` hanya boleh dibaca ADMIN; karena itu nama role audiens diambil lewat fungsi `report_audience_db_role` (§8.2), bukan subkueri langsung. `rp_writers` diperlukan karena RLS yang hanya punya policy SELECT menolak INSERT/UPDATE untuk semua role selain pemilik tabel.

```sql
ALTER TABLE api_tokens ENABLE ROW LEVEL SECURITY;
CREATE POLICY tok_owner ON api_tokens
  USING (user_id = NULLIF(current_setting('app.user_id', true), '')::int
         OR pg_has_role(current_user, 'monitor_admin', 'MEMBER'));
```

Hanya dua tabel ini yang memakai RLS.

### 8.5 Audit trigger

```sql
CREATE FUNCTION audit_row() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE o_full jsonb; n_full jsonb; changed text[]; ignored text[] := ARRAY['updated_at'];
BEGIN
  IF TG_OP <> 'INSERT' THEN o_full := to_jsonb(OLD); END IF;
  IF TG_OP <> 'DELETE' THEN n_full := to_jsonb(NEW); END IF;
  IF TG_OP = 'UPDATE' THEN
    changed := ARRAY(SELECT k FROM jsonb_each(n_full) e(k,v)
                     WHERE v IS DISTINCT FROM o_full->k AND k <> 'updated_at');
    IF TG_NARGS > 1 THEN ignored := ignored || TG_ARGV[1:TG_NARGS-1]; END IF;
    IF changed <@ ignored THEN RETURN NULL; END IF;     -- hanya kolom pembukuan
  END IF;
  INSERT INTO audit_log(table_name,row_pk,operation,old_data,new_data,changed_columns,app_user_id,db_user)
  VALUES (TG_TABLE_NAME, COALESCE(n_full,o_full) ->> TG_ARGV[0], left(TG_OP,1),
          o_full - 'password_hash' - 'token_hash' - 'geom',
          n_full - 'password_hash' - 'token_hash' - 'geom',
          changed,
          NULLIF(current_setting('app.user_id', true), '')::int,
          COALESCE(NULLIF(current_setting('role'), 'none'), session_user));
  RETURN NULL;
END $$;
```

- `TG_ARGV[0]` = kolom PK; `TG_ARGV[1..]` = kolom "pembukuan" yang perubahannya **saja** tidak dicatat.
- `changed_columns` dihitung dari baris utuh sebelum sensor: perubahan `password_hash` terlihat sebagai nama kolom, nilainya tidak pernah disimpan.
- `db_user` diambil dari GUC `role` (hasil `SET ROLE`), atau `session_user` bila lewat psql; `current_user` di dalam fungsi SECURITY DEFINER selalu pemilik fungsi.

| Tabel | Operasi | Kolom pembukuan yang diabaikan |
|---|---|---|
| `users` | I/U/D | `last_login_at`, `failed_login_count` (perubahan `locked_until` tetap tercatat) |
| `api_tokens` | I/U/D | `last_used_at` (berubah setiap request bertoken) |
| `alert_rules`, `alert_events`, `disaster_events`, `quality_thresholds`, `disaster_types`, `app_settings` | I/U/D | — |
| `administrative_regions` | UPDATE `in_aoi` saja | — |
| `live_areas` | I/U/D | `status`, `status_message`, `last_checked_at`, `forecast`, `forecast_updated_at` (siklus otomatis) |
| `satellite_scenes`, `nasa_scenes` | UPDATE `is_valid` saja | — |
| `datasets` | I/U/D | `total_scenes`, `completed_scenes`, `failed_scenes`, `total_size_bytes` (progres pipeline) |

Tabel bervolume tinggi hasil pipeline (`data_products`, `processing_logs`, `region_observations`) **tidak** di-audit trigger — lineage dan log pipeline sudah menjadi jejaknya. INSERT seed (`monitor_seed.sql` dijalankan setelah berkas keamanan) ikut tercatat dengan `app_user_id` NULL.

### 8.6 Kebijakan kata sandi dan sesi

bcrypt cost 12; minimal 10 karakter (maks. 72 byte, batas bcrypt); 5 kali gagal → `locked_until = now() + 15 menit`; JWT HS256 di cookie `HttpOnly; Secure; SameSite=Strict`, kedaluwarsa 8 jam; setiap login sukses/gagal dicatat di `user_activity_logs`.

---

## 9. Redundansi Terkendali

| Redundansi | Alasan | Penjaga konsistensi |
|---|---|---|
| `RAIN_72H`, `RAIN_7D`, `RAIN_30D` disimpan, bukan dihitung saat kueri | Dashboard dan alert memanggilnya setiap muat halaman | Dihitung sekali di job hidromet dari raster akumulasi; upsert idempoten |
| `alert_events.observed_value/threshold_value/severity` | Membekukan konteks saat terpicu | Diisi sekali oleh pipeline, kolom tidak di-GRANT UPDATE |
| `live_scene_metrics` tidak ikut dihapus retensi | Grafik & forecast tetap hidup setelah berkas dihapus | Ditulis oleh siklus Live (`save_scene_metrics`) |
| `administrative_regions.area_km2` (generated) | Pembobotan dan laporan | `GENERATED ALWAYS` |

---

## 10. Pemantauan dan Pemeliharaan

- `pg_dump -Fc` harian (01:30 WIB) ke disk terpisah, retensi 14 hari; uji restore sebagai pengujian *recoverability*.
- `VACUUM (ANALYZE)` otomatis (autovacuum default) + `ANALYZE` setelah backfill.
- `pg_stat_statements` diaktifkan untuk menemukan kueri lambat; target muat Statistik Hari Ini < 1 detik.
- Checksum produk diverifikasi ulang lewat `POST /api/admin/archive/verify` (warisan `/products/{id}/verify`).
