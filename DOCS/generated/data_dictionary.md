# Kamus Data — Orbit-U: The Monitor

> Dibangkitkan otomatis oleh `tools/data_dictionary.py` dari katalog PostgreSQL (database `themonitor`, 2026-10-18 20:52 UTC). Jangan disunting manual; ubah `database/monitor_schema.sql` (termasuk `COMMENT ON`) lalu bangkitkan ulang.

Jumlah: **43 tabel**, **22 VIEW**.

## Daftar tabel

| Tabel | Keterangan |
|---|---|
| [`administrative_regions`](#administrative_regions) | Batas wilayah resmi COD-AB Indonesia (BPS via OCHA/HDX): Kabupaten Lebak (level 2) dan kecamatannya (level 3). AOI GMLS = kecamatan in_aoi (M8). |
| [`alert_events`](#alert_events) | Alert hujan per aturan per kecamatan per hari. observed_value/threshold_value/severity adalah salinan historis (§5.2). |
| [`alert_rules`](#alert_rules) | Aturan alert hujan per jenis bencana (ambang BMKG; longsor nonaktif sampai ambang literatur diisi). |
| [`api_tokens`](#api_tokens) | Token API pribadi untuk skrip/sistem lain (M33). Hanya hash yang disimpan; token utuh ditampilkan sekali. |
| [`app_settings`](#app_settings) | Pengaturan key-value yang boleh diubah ADMIN tanpa restart (PIPELINE.md §11). |
| [`audit_log`](#audit_log) | Jejak perubahan data yang diisi trigger audit_row (append-only, M15). Trigger dipasang di monitor_security.sql. |
| [`band_forecast_points`](#band_forecast_points) | Titik forecast harian satu band_forecasts (M62). |
| [`band_forecast_scores`](#band_forecast_scores) | MAE backtest setiap model kandidat untuk satu band_forecasts (M62): bukti kenapa model terpilih menang. |
| [`band_forecasts`](#band_forecasts) | Forecast 15 hari per deret (band × AOI/kecamatan), dihitung saat data baru masuk dari seluruh riwayat region_observations (M62). Riwayat 365 hari disimpan supaya model yang dipakai pada tanggal tertentu bisa dilacak. |
| [`cleanup_operations`](#cleanup_operations) | Progres penghapusan berkas per dataset (cleanup tier akhir job atau hapus dataset). Sengaja tanpa FK ke datasets agar progres tetap terbaca setelah dataset dihapus. |
| [`data_lineage`](#data_lineage) | Graf asiklik (DAG) transformasi produk: induk -> anak dengan checksum input/output (RM2). |
| [`data_products`](#data_products) | Registri setiap berkas keluaran pipeline (COG, TIFF, HDF5) dengan checksum SHA-256. |
| [`dataset_jobs`](#dataset_jobs) | Satu eksekusi pekerjaan atas sebuah dataset (buat, backfill, siklus Live, hidromet harian). |
| [`dataset_source_config`](#dataset_source_config) | Konfigurasi pemrosesan per (dataset, sumber). ETL membaca tabel ini untuk memutuskan sumber dan level yang dijalankan. |
| [`datasets`](#datasets) | Dataset historis (Katalog, DATA_ENGINEER), dataset Live Area, dan dataset sistem HYDROMET_AOI. |
| [`disaster_events`](#disaster_events) | Catatan kejadian bencana (GMLS, BPBD, input ANALYST). Tanpa data pribadi. Soft delete. |
| [`disaster_types`](#disaster_types) | Master jenis bencana. ADMIN dapat menambah jenis tanpa ubah kode (uji adaptability). |
| [`fusion_products`](#fusion_products) | Registri stack HDF5 multi-sensor (S1 + MODIS + GPM) per dataset per tanggal per level. |
| [`fusion_strategies`](#fusion_strategies) | Master strategi fusion (M9). Dirujuk datasets.fusion_strategy dan fusion_products.fusion_strategy lewat strategy_code. |
| [`generated_reports`](#generated_reports) | Laporan PDF mingguan/bulanan yang dibuat (M18). Akses dibatasi RLS per audiens (tahap keamanan). |
| [`live_areas`](#live_areas) | Live Area: satu AOI yang dipantau otomatis per lintasan S1 (maksimal app_settings.live.max_areas). |
| [`live_events`](#live_events) | Log langkah siklus Live per area (append-only, tanpa FK agar bertahan setelah area dihapus). |
| [`live_scene_metrics`](#live_scene_metrics) | Metrik numerik scene Live, satu baris per band x metrik (1NF, M31). Tetap ada setelah berkas scene dihapus retensi. |
| [`live_scenes`](#live_scenes) | Satu scene Live (tanggal lintasan S1) per area. Tidak pernah dihapus: retensi hanya menghapus berkas dan mengisi deleted_at. Sengaja tanpa FK agar hidup lebih lama dari area/dataset. |
| [`nasa_scenes`](#nasa_scenes) | Registri granule MODIS dan GPM (satu baris per sumber/produk/tile/tanggal). |
| [`notify_sent`](#notify_sent) | Butir tidak normal yang sudah dikirim lewat email (M64). Kunci unik (pengguna, kecamatan, butir, tanggal data) mencegah pengiriman ulang data yang sama. |
| [`processing_jobs`](#processing_jobs) | Eksekusi satu tahap pipeline (scene/granule x tahap x percobaan). Jangkar: scene S1, granule NASA, atau tidak keduanya untuk FUSION (M30). |
| [`processing_logs`](#processing_logs) | Log pipeline terstruktur append-only: satu baris per kejadian tahap (STARTED/RUNNING/COMPLETED/FAILED). |
| [`processing_stages`](#processing_stages) | Master tahap pipeline (S1/MODIS/GPM/FUSION/PREVIEW + HYDROMET_AGGREGATE, ALERT_CHECK, WATER_CHANGE, REPORT_BUILD). |
| [`quality_alerts`](#quality_alerts) | Peringatan kualitas/operasional pipeline (mis. skor QA < 60). Tabel alert_events DataLab yang diganti nama; nama alert_events kini untuk alert hujan. |
| [`quality_metrics`](#quality_metrics) | Hasil kontrol kualitas radiometrik per scene S1 per band (tahap QUALITY_ANALYTICS). |
| [`quality_thresholds`](#quality_thresholds) | Ambang kontrol kualitas per band (menggantikan processing_rules). Dibaca module6_analytics; bobot skor 50/30/20 tetap konstanta kode. |
| [`region_observations`](#region_observations) | Deret waktu dataset utama: nilai per kecamatan per band dari GPM/MODIS (harian) dan Sentinel-1 (per lintasan: VV, VH, WATER_PCT) (M7, M58). Tidak pernah dihapus retensi raster. Dasar grafik, statistik, alert, laporan. |
| [`regions_of_interest`](#regions_of_interest) | AOI dataset (bbox) warisan DataLab. Baris baru hanya dari kecamatan atau gabungan kecamatan (M27); tepat satu baris adalah AOI GMLS (is_monitor_aoi). |
| [`report_types`](#report_types) | Master jenis laporan periodik (M18): Hidromet untuk ANALYST, Kesehatan Data untuk DATA_ENGINEER. |
| [`roles`](#roles) | Master role aplikasi (5 role, M13). Setiap role dipetakan ke satu role PostgreSQL yang dipakai lewat SET LOCAL ROLE. |
| [`satellite_scenes`](#satellite_scenes) | Registri scene Sentinel-1 GRD yang ditemukan/diunduh. Soft delete ADMIN lewat is_valid (M24). |
| [`satellite_sources`](#satellite_sources) | Master sumber data. Kolom VARCHAR "source" warisan DataLab dihubungkan ke source_code lewat FK. |
| [`scene_job_state`](#scene_job_state) | Status per scene S1 di dalam satu dataset_job; dasar resume setelah proses mati. |
| [`spectral_bands`](#spectral_bands) | Master band/variabel yang diamati per sumber; dipakai region_observations, alert_rules, quality_thresholds, live_scene_metrics. |
| [`user_activity_logs`](#user_activity_logs) | Log aplikasi append-only: login, logout, unduhan, ekspor, aksi penting (RM4). |
| [`user_notify_regions`](#user_notify_regions) | Langganan peringatan email per kecamatan (M64): tempat tinggal, beberapa, atau tidak sama sekali. Diubah pemiliknya lewat auth_set_own_notify(). |
| [`users`](#users) | Akun pengguna yang login (USER s.d. ADMIN). Akun dinonaktifkan, tidak pernah dihapus. |

## administrative_regions

Batas wilayah resmi COD-AB Indonesia (BPS via OCHA/HDX): Kabupaten Lebak (level 2) dan kecamatannya (level 3). AOI GMLS = kecamatan in_aoi (M8).

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `region_id` | `integer` | NOT NULL | `nextval('administrative_regions_region_id_seq'::regclass)` | PK | PK surrogate. |
| `parent_region_id` | `integer` | NULL |  | FK→administrative_regions | FK -> administrative_regions: kabupaten induk. NULL untuk level 2. |
| `pcode` | `character varying(20)` | NOT NULL |  | UNIQUE | Alternate key: P-code COD-AB, mis. ID3602xxx. |
| `region_name` | `character varying(100)` | NOT NULL |  |  | Nama wilayah (ADM2_EN/ADM3_EN), mis. Bayah. |
| `admin_level` | `smallint` | NOT NULL |  |  | 2 = kabupaten, 3 = kecamatan. |
| `in_aoi` | `boolean` | NOT NULL | `false` |  | true = kecamatan termasuk cakupan GMLS (hanya level 3). Diubah ADMIN. |
| `geom` | `geometry(MultiPolygon,4326)` | NOT NULL |  |  | Poligon batas wilayah, MultiPolygon EPSG:4326 (ST_Multi(ST_MakeValid(...))). |
| `area_km2` | `numeric(10,2)` | NULL | `GENERATED` |  | Luas geodesik (km2), kolom GENERATED dari geom (redundansi terkendali, §9). |
| `source_dataset` | `character varying(100)` | NOT NULL |  |  | Asal data batas, mis. "COD-AB IDN 2020 (BPS/OCHA)". |

**Constraint**

- `administrative_regions_admin_level_check` (CHECK): `CHECK ((admin_level = ANY (ARRAY[2, 3])))`
- `administrative_regions_check` (CHECK): `CHECK (((admin_level = 2) OR (parent_region_id IS NOT NULL)))`
- `administrative_regions_check1` (CHECK): `CHECK (((NOT in_aoi) OR (admin_level = 3)))`
- `administrative_regions_parent_region_id_fkey` (FK): `FOREIGN KEY (parent_region_id) REFERENCES administrative_regions(region_id)`
- `administrative_regions_pkey` (PK): `PRIMARY KEY (region_id)`
- `administrative_regions_pcode_key` (UNIQUE): `UNIQUE (pcode)`

## alert_events

Alert hujan per aturan per kecamatan per hari. observed_value/threshold_value/severity adalah salinan historis (§5.2).

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `alert_id` | `bigint` | NOT NULL | `nextval('alert_events_alert_id_seq'::regclass)` | PK | PK surrogate. |
| `rule_id` | `integer` | NOT NULL |  | FK→alert_rules, UNIQUE | FK -> alert_rules yang terpicu. |
| `region_id` | `integer` | NOT NULL |  | FK→administrative_regions, UNIQUE | FK -> administrative_regions (kecamatan). |
| `obs_id` | `bigint` | NOT NULL |  | FK→region_observations | FK -> region_observations: nilai pemicu. |
| `observation_date` | `date` | NOT NULL |  | UNIQUE | Tanggal pengamatan pemicu (hari UTC). |
| `observed_value` | `numeric(10,4)` | NOT NULL |  |  | Salinan nilai saat terpicu (mm). |
| `threshold_value` | `numeric(8,2)` | NOT NULL |  |  | Salinan ambang saat terpicu (mm). |
| `severity` | `character varying(10)` | NOT NULL |  |  | Salinan severity aturan: INFO \| WARNING \| CRITICAL. |
| `triggered_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu alert dibuat job. |
| `acknowledged_by` | `integer` | NULL |  | FK→users | FK -> users: ANALYST/ADMIN yang menandai sudah dibaca. |
| `acknowledged_at` | `timestamp with time zone` | NULL |  |  | Waktu ditandai sudah dibaca. Berpasangan dengan acknowledged_by. |
| `ack_note` | `character varying(500)` | NULL |  |  | Catatan opsional saat acknowledge. |

**Constraint**

- `alert_events_severity_check` (CHECK): `CHECK (((severity)::text = ANY (ARRAY[('INFO'::character varying)::text, ('WARNING'::character varying)::text, ('CRITICAL'::character varying)::text])))`
- `chk_alert_ack_pair` (CHECK): `CHECK (((acknowledged_by IS NULL) = (acknowledged_at IS NULL)))`
- `alert_events_acknowledged_by_fkey` (FK): `FOREIGN KEY (acknowledged_by) REFERENCES users(user_id)`
- `alert_events_obs_id_fkey` (FK): `FOREIGN KEY (obs_id) REFERENCES region_observations(obs_id)`
- `alert_events_region_id_fkey` (FK): `FOREIGN KEY (region_id) REFERENCES administrative_regions(region_id)`
- `alert_events_rule_id_fkey` (FK): `FOREIGN KEY (rule_id) REFERENCES alert_rules(rule_id)`
- `alert_events_pkey` (PK): `PRIMARY KEY (alert_id)`
- `uq_alert_rule_region_date` (UNIQUE): `UNIQUE (rule_id, region_id, observation_date)`

## alert_rules

Aturan alert hujan per jenis bencana (ambang BMKG; longsor nonaktif sampai ambang literatur diisi).

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `rule_id` | `integer` | NOT NULL | `nextval('alert_rules_rule_id_seq'::regclass)` | PK | PK surrogate. |
| `rule_code` | `character varying(40)` | NOT NULL |  | UNIQUE | Alternate key, mis. FLOOD_RAIN24_HEAVY. |
| `disaster_type_id` | `smallint` | NOT NULL |  | FK→disaster_types | FK -> disaster_types. |
| `band_id` | `smallint` | NOT NULL |  | FK→spectral_bands | FK -> spectral_bands: band yang dibandingkan, mis. RAIN_24H. |
| `comparator` | `character varying(2)` | NOT NULL |  |  | Operator pembanding nilai terhadap ambang: >= \| > \| <= \| <. |
| `threshold_value` | `numeric(8,2)` | NULL |  |  | Ambang dalam satuan band (mm untuk hujan). Wajib terisi bila is_active (K7). |
| `severity` | `character varying(10)` | NOT NULL |  |  | INFO \| WARNING \| CRITICAL. |
| `reference_source` | `character varying(150)` | NOT NULL |  |  | Rujukan ambang, mis. "BMKG (hujan lebat)". |
| `is_active` | `boolean` | NOT NULL | `true` |  | false = aturan tidak dievaluasi job hidromet. |
| `updated_by` | `integer` | NULL |  | FK→users | FK -> users: ADMIN yang terakhir mengubah. |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris terakhir diubah (trigger). |

**Constraint**

- `alert_rules_comparator_check` (CHECK): `CHECK (((comparator)::text = ANY (ARRAY[('>='::character varying)::text, ('>'::character varying)::text, ('<='::character varying)::text, ('<'::character varying)::text])))`
- `alert_rules_severity_check` (CHECK): `CHECK (((severity)::text = ANY (ARRAY[('INFO'::character varying)::text, ('WARNING'::character varying)::text, ('CRITICAL'::character varying)::text])))`
- `chk_rule_active_needs_threshold` (CHECK): `CHECK (((NOT is_active) OR (threshold_value IS NOT NULL)))`
- `alert_rules_band_id_fkey` (FK): `FOREIGN KEY (band_id) REFERENCES spectral_bands(band_id)`
- `alert_rules_disaster_type_id_fkey` (FK): `FOREIGN KEY (disaster_type_id) REFERENCES disaster_types(disaster_type_id)`
- `alert_rules_updated_by_fkey` (FK): `FOREIGN KEY (updated_by) REFERENCES users(user_id)`
- `alert_rules_pkey` (PK): `PRIMARY KEY (rule_id)`
- `alert_rules_rule_code_key` (UNIQUE): `UNIQUE (rule_code)`

## api_tokens

Token API pribadi untuk skrip/sistem lain (M33). Hanya hash yang disimpan; token utuh ditampilkan sekali.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `token_id` | `integer` | NOT NULL | `nextval('api_tokens_token_id_seq'::regclass)` | PK | PK surrogate. |
| `user_id` | `integer` | NOT NULL |  | FK→users | FK -> users pemilik; role token = role pemilik saat dipakai. |
| `token_name` | `character varying(60)` | NOT NULL |  |  | Nama token, mis. "skrip training". |
| `token_prefix` | `character(8)` | NOT NULL |  | UNIQUE | Awalan token untuk identifikasi, mis. trn_4f2a (unik). |
| `token_hash` | `character(64)` | NOT NULL |  |  | SHA-256 token (64 hex). |
| `scopes` | `character varying(20)` | NOT NULL |  |  | READ \| READ_DOWNLOAD (tanpa scope tulis). |
| `expires_at` | `timestamp with time zone` | NOT NULL |  |  | Kedaluwarsa, maksimal 180 hari sejak dibuat. |
| `last_used_at` | `timestamp with time zone` | NULL |  |  | Waktu terakhir dipakai. |
| `revoked_at` | `timestamp with time zone` | NULL |  |  | Waktu dicabut; NULL = aktif. |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu token dibuat. |

**Constraint**

- `api_tokens_scopes_check` (CHECK): `CHECK (((scopes)::text = ANY (ARRAY[('READ'::character varying)::text, ('READ_DOWNLOAD'::character varying)::text])))`
- `chk_token_max_lifetime` (CHECK): `CHECK ((expires_at <= (created_at + '180 days'::interval)))`
- `api_tokens_user_id_fkey` (FK): `FOREIGN KEY (user_id) REFERENCES users(user_id)`
- `api_tokens_pkey` (PK): `PRIMARY KEY (token_id)`
- `api_tokens_token_prefix_key` (UNIQUE): `UNIQUE (token_prefix)`

## app_settings

Pengaturan key-value yang boleh diubah ADMIN tanpa restart (PIPELINE.md §11).

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `setting_key` | `character varying(50)` | NOT NULL |  | PK | PK: nama kunci bertitik, mis. live.max_areas. |
| `setting_value` | `jsonb` | NOT NULL |  |  | Nilai JSON, mis. 5, -20, "Asia/Jakarta". |
| `description` | `text` | NULL |  |  | Penjelasan arti dan satuan nilai. |
| `updated_by` | `integer` | NULL |  | FK→users | FK -> users: ADMIN yang terakhir mengubah. |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris terakhir diubah (trigger). |

**Constraint**

- `app_settings_updated_by_fkey` (FK): `FOREIGN KEY (updated_by) REFERENCES users(user_id)`
- `app_settings_pkey` (PK): `PRIMARY KEY (setting_key)`

## audit_log

Jejak perubahan data yang diisi trigger audit_row (append-only, M15). Trigger dipasang di monitor_security.sql.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `audit_id` | `bigint` | NOT NULL | `nextval('audit_log_audit_id_seq'::regclass)` | PK | PK surrogate. |
| `table_name` | `character varying(63)` | NOT NULL |  |  | Nama tabel yang berubah. |
| `row_pk` | `text` | NOT NULL |  |  | Nilai PK baris yang berubah (teks). |
| `operation` | `character(1)` | NOT NULL |  |  | I (INSERT) \| U (UPDATE) \| D (DELETE). |
| `old_data` | `jsonb` | NULL |  |  | Baris sebelum perubahan (JSONB; password_hash/token_hash disensor). |
| `new_data` | `jsonb` | NULL |  |  | Baris sesudah perubahan (JSONB; password_hash/token_hash disensor). |
| `changed_columns` | `text[]` | NULL |  |  | Kolom yang berubah (untuk U). |
| `app_user_id` | `integer` | NULL |  |  | users.user_id dari current_setting('app.user_id'); NULL bila lewat psql. |
| `db_user` | `name` | NOT NULL | `CURRENT_USER` |  | Role PostgreSQL yang menjalankan perubahan. |
| `changed_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu perubahan. |

**Constraint**

- `audit_log_operation_check` (CHECK): `CHECK ((operation = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])))`
- `audit_log_pkey` (PK): `PRIMARY KEY (audit_id)`

## band_forecast_points

Titik forecast harian satu band_forecasts (M62).

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `forecast_id` | `bigint` | NOT NULL |  | FK→band_forecasts, PK | FK -> band_forecasts. |
| `step` | `smallint` | NOT NULL |  | PK | Langkah ke-k (1 = sehari sesudah last_obs_date). |
| `target_date` | `date` | NOT NULL |  |  | Tanggal yang diramal. |
| `mean` | `numeric(12,4)` | NOT NULL |  |  | Nilai forecast (satuan band). |
| `lo` | `numeric(12,4)` | NOT NULL |  |  | Batas bawah pita 80%. |
| `hi` | `numeric(12,4)` | NOT NULL |  |  | Batas atas pita 80%. |

**Constraint**

- `band_forecast_points_check` (CHECK): `CHECK (((lo <= mean) AND (mean <= hi)))`
- `band_forecast_points_step_check` (CHECK): `CHECK (((step >= 1) AND (step <= 30)))`
- `band_forecast_points_forecast_id_fkey` (FK): `FOREIGN KEY (forecast_id) REFERENCES band_forecasts(forecast_id) ON DELETE CASCADE`
- `band_forecast_points_pkey` (PK): `PRIMARY KEY (forecast_id, step)`

## band_forecast_scores

MAE backtest setiap model kandidat untuk satu band_forecasts (M62): bukti kenapa model terpilih menang.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `forecast_id` | `bigint` | NOT NULL |  | FK→band_forecasts, PK | FK -> band_forecasts. |
| `model` | `character varying(10)` | NOT NULL |  | PK | Model kandidat. |
| `mae` | `numeric(14,6)` | NOT NULL |  |  | MAE backtest model itu (satuan band). |

**Constraint**

- `band_forecast_scores_model_check` (CHECK): `CHECK (((model)::text = ANY ((ARRAY['naive'::character varying, 'ses'::character varying, 'holt'::character varying, 'clim'::character varying, 'clim_ar1'::character varying])::text[])))`
- `band_forecast_scores_forecast_id_fkey` (FK): `FOREIGN KEY (forecast_id) REFERENCES band_forecasts(forecast_id) ON DELETE CASCADE`
- `band_forecast_scores_pkey` (PK): `PRIMARY KEY (forecast_id, model)`

## band_forecasts

Forecast 15 hari per deret (band × AOI/kecamatan), dihitung saat data baru masuk dari seluruh riwayat region_observations (M62). Riwayat 365 hari disimpan supaya model yang dipakai pada tanggal tertentu bisa dilacak.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `forecast_id` | `bigint` | NOT NULL | `nextval('band_forecasts_forecast_id_seq'::regclass)` | PK | PK surrogate. |
| `band_id` | `smallint` | NOT NULL |  | FK→spectral_bands | FK -> spectral_bands: band yang diramal. |
| `region_id` | `integer` | NULL |  | FK→administrative_regions | FK -> administrative_regions (kecamatan). NULL = rerata AOI. |
| `data_stamp` | `timestamp with time zone` | NOT NULL |  |  | Cap data band saat dihitung: max(region_observations.computed_at) band itu dan max(live_scenes.updated_at). Forecast basi bila cap sekarang berbeda. |
| `end_date` | `date` | NOT NULL |  |  | Data dipakai s.d. tanggal ini (hari UTC saat dihitung). |
| `history_from` | `date` | NULL |  |  | Tanggal observasi pertama yang dipakai. |
| `last_obs_date` | `date` | NULL |  |  | Tanggal observasi terakhir; titik forecast mulai sehari sesudahnya. |
| `n_obs` | `integer` | NOT NULL |  |  | Jumlah hari berdata yang dipakai. |
| `horizon` | `smallint` | NOT NULL |  |  | Jumlah hari yang diramal (15). |
| `model` | `character varying(10)` | NULL |  |  | Model terpilih backtest: naive \| ses \| holt \| clim \| clim_ar1. NULL bila data < 10 titik. |
| `confidence` | `character varying(6)` | NULL |  |  | Keyakinan dari skill backtest: rendah \| sedang \| tinggi. |
| `backtest_origins` | `smallint` | NULL |  |  | Jumlah titik asal backtest yang dinilai (maks. 12). NULL bila riwayat terlalu pendek. |
| `mae` | `numeric(14,6)` | NULL |  |  | MAE backtest model terpilih (satuan band). |
| `mae_naive` | `numeric(14,6)` | NULL |  |  | MAE backtest model naive (pembanding). |
| `skill` | `numeric(8,4)` | NULL |  |  | Skill = 1 - mae / mae_naive. |
| `notes` | `text` | NULL |  |  | Catatan untuk pengguna (celah data, tidak mengalahkan naive), satu per baris. |
| `duration_ms` | `integer` | NOT NULL | `0` |  | Lama perhitungan deret ini (ms). |
| `computed_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu dihitung. |

**Constraint**

- `band_forecasts_confidence_check` (CHECK): `CHECK (((confidence)::text = ANY ((ARRAY['rendah'::character varying, 'sedang'::character varying, 'tinggi'::character varying])::text[])))`
- `band_forecasts_horizon_check` (CHECK): `CHECK (((horizon >= 1) AND (horizon <= 30)))`
- `band_forecasts_model_check` (CHECK): `CHECK (((model)::text = ANY ((ARRAY['naive'::character varying, 'ses'::character varying, 'holt'::character varying, 'clim'::character varying, 'clim_ar1'::character varying])::text[])))`
- `band_forecasts_n_obs_check` (CHECK): `CHECK ((n_obs >= 0))`
- `band_forecasts_band_id_fkey` (FK): `FOREIGN KEY (band_id) REFERENCES spectral_bands(band_id)`
- `band_forecasts_region_id_fkey` (FK): `FOREIGN KEY (region_id) REFERENCES administrative_regions(region_id)`
- `band_forecasts_pkey` (PK): `PRIMARY KEY (forecast_id)`

## cleanup_operations

Progres penghapusan berkas per dataset (cleanup tier akhir job atau hapus dataset). Sengaja tanpa FK ke datasets agar progres tetap terbaca setelah dataset dihapus.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `id` | `bigint` | NOT NULL | `nextval('cleanup_operations_id_seq'::regclass)` | PK | PK surrogate. |
| `dataset_id` | `integer` | NOT NULL |  |  | Dataset yang dibersihkan (tanpa FK, lihat komentar tabel). |
| `job_id` | `bigint` | NULL |  | FK→dataset_jobs | FK -> dataset_jobs yang memicu cleanup. |
| `operation_type` | `character varying(20)` | NOT NULL |  |  | TIER_CLEANUP \| FULL_DELETE. |
| `status` | `character varying(20)` | NOT NULL | `'PENDING'::character varying` |  | PENDING \| IN_PROGRESS \| COMPLETED \| FAILED. |
| `total_files` | `integer` | NOT NULL | `0` |  | Jumlah berkas yang akan dihapus. |
| `deleted_count` | `integer` | NOT NULL | `0` |  | Jumlah berkas yang sudah dihapus. |
| `freed_bytes` | `bigint` | NOT NULL | `0` |  | Ruang disk yang dibebaskan (byte). |
| `error_log` | `text` | NULL |  |  | Galat selama penghapusan. |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris dibuat. |
| `started_at` | `timestamp with time zone` | NULL |  |  | Waktu mulai. |
| `completed_at` | `timestamp with time zone` | NULL |  |  | Waktu selesai. |

**Constraint**

- `cleanup_operations_operation_type_check` (CHECK): `CHECK (((operation_type)::text = ANY (ARRAY[('TIER_CLEANUP'::character varying)::text, ('FULL_DELETE'::character varying)::text])))`
- `cleanup_operations_status_check` (CHECK): `CHECK (((status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('IN_PROGRESS'::character varying)::text, ('COMPLETED'::character varying)::text, ('FAILED'::character varying)::text])))`
- `cleanup_operations_job_id_fkey` (FK): `FOREIGN KEY (job_id) REFERENCES dataset_jobs(job_id) ON DELETE SET NULL`
- `cleanup_operations_pkey` (PK): `PRIMARY KEY (id)`

## data_lineage

Graf asiklik (DAG) transformasi produk: induk -> anak dengan checksum input/output (RM2).

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `lineage_id` | `bigint` | NOT NULL | `nextval('data_lineage_lineage_id_seq'::regclass)` | PK | PK surrogate. |
| `parent_product_id` | `bigint` | NOT NULL |  | FK→data_products, UNIQUE | FK -> data_products: produk input. |
| `child_product_id` | `bigint` | NOT NULL |  | FK→data_products, UNIQUE | FK -> data_products: produk output. |
| `transformation_type` | `character varying(50)` | NOT NULL |  |  | Jenis transformasi, mis. CROP, LEE_FILTER, GOLD_EXPORT, FUSION. |
| `stage_id` | `integer` | NOT NULL |  | FK→processing_stages | FK -> processing_stages. |
| `job_id` | `bigint` | NOT NULL |  | FK→processing_jobs | FK -> processing_jobs: eksekusi yang melakukan transformasi. |
| `transformation_params` | `jsonb` | NOT NULL | `'{}'::jsonb` |  | Parameter transformasi (JSONB): bbox crop, window Lee, kompresi COG. |
| `input_checksum` | `character varying(64)` | NULL |  |  | SHA-256 induk saat transformasi. |
| `output_checksum` | `character varying(64)` | NULL |  |  | SHA-256 anak setelah transformasi. |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris dibuat. |

**Constraint**

- `chk_lineage_no_self_ref` (CHECK): `CHECK ((parent_product_id <> child_product_id))`
- `data_lineage_child_product_id_fkey` (FK): `FOREIGN KEY (child_product_id) REFERENCES data_products(product_id) ON DELETE CASCADE`
- `data_lineage_job_id_fkey` (FK): `FOREIGN KEY (job_id) REFERENCES processing_jobs(job_id) ON DELETE RESTRICT`
- `data_lineage_parent_product_id_fkey` (FK): `FOREIGN KEY (parent_product_id) REFERENCES data_products(product_id) ON DELETE CASCADE`
- `data_lineage_stage_id_fkey` (FK): `FOREIGN KEY (stage_id) REFERENCES processing_stages(stage_id) ON DELETE RESTRICT`
- `data_lineage_pkey` (PK): `PRIMARY KEY (lineage_id)`
- `uq_lineage_parent_child` (UNIQUE): `UNIQUE (parent_product_id, child_product_id)`

## data_products

Registri setiap berkas keluaran pipeline (COG, TIFF, HDF5) dengan checksum SHA-256.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `product_id` | `bigint` | NOT NULL | `nextval('data_products_product_id_seq'::regclass)` | PK | PK surrogate. |
| `product_uuid` | `uuid` | NOT NULL | `gen_random_uuid()` | UNIQUE | UUID stabil untuk referensi eksternal. |
| `scene_id` | `integer` | NULL |  | FK→satellite_scenes | FK -> satellite_scenes: scene S1 asal. Terisi hanya untuk source SENTINEL1 (chk_dprods_single_origin). |
| `nasa_scene_id` | `bigint` | NULL |  | FK→nasa_scenes | FK -> nasa_scenes: granule MODIS/GPM asal. Terisi hanya untuk source MODIS/GPM; FUSION keduanya NULL (M30). |
| `job_id` | `bigint` | NOT NULL |  | FK→processing_jobs | FK -> processing_jobs: eksekusi tahap yang menulis berkas ini. |
| `dataset_id` | `integer` | NULL |  | FK→datasets | FK -> datasets: dataset pemilik berkas. |
| `product_tier` | `product_tier_enum` | NOT NULL |  |  | Posisi di lineage (D14): RAW \| ALIGNED \| DESPECKLED \| INDICES \| ACCUMULATED \| COG \| FUSED. |
| `source` | `character varying(20)` | NOT NULL | `'SENTINEL1'::character varying` | FK→satellite_sources | FK -> satellite_sources.source_code: SENTINEL1 \| MODIS \| GPM \| FUSION. |
| `processing_level` | `character varying(20)` | NULL | `'PROCESSED'::character varying` |  | Level konfigurasi yang menghasilkan berkas: RAW \| PROCESSED (beda dari product_tier). |
| `product_type` | `character varying(50)` | NOT NULL |  |  | Jenis artefak, mis. S1_COG, MODIS_FLOOD, GPM_RAINFALL, FUSION_H5. |
| `band_name` | `character varying(20)` | NOT NULL |  |  | Band/lapisan, mis. VV, NDVI, RAIN_24H, FUSION_PROCESSED. |
| `file_name` | `character varying(255)` | NOT NULL |  |  | Nama berkas. |
| `file_path` | `text` | NOT NULL |  |  | Path berkas di filesystem data/ (raster tidak disimpan di DB). |
| `file_size_mb` | `numeric(12,3)` | NOT NULL |  |  | Ukuran berkas (MB). |
| `file_format` | `character varying(20)` | NOT NULL | `'TIFF'::character varying` |  | Format: TIFF \| COG \| HDF5. |
| `data_hash_sha256` | `character varying(64)` | NOT NULL |  |  | SHA-256 isi berkas (64 hex) untuk lineage dan verifikasi arsip (RM2). |
| `crs` | `character varying(50)` | NOT NULL | `'EPSG:4326'::character varying` |  | Sistem koordinat, mis. EPSG:4326. |
| `pixel_size_m` | `numeric(8,3)` | NULL |  |  | Ukuran piksel (meter). |
| `nodata_value` | `numeric` | NULL |  |  | Nilai NoData raster. |
| `rows` | `integer` | NULL |  |  | Jumlah baris piksel. |
| `cols` | `integer` | NULL |  |  | Jumlah kolom piksel. |
| `band_count` | `smallint` | NOT NULL | `1` |  | Jumlah band dalam berkas. |
| `storage_location` | `storage_location_enum` | NOT NULL | `'LOCAL'::storage_location_enum` |  | Lokasi penyimpanan, selalu LOCAL di Monitor. |
| `is_valid` | `boolean` | NOT NULL | `true` |  | false = berkas dinyatakan tidak sah/dihapus. |
| `is_latest` | `boolean` | NOT NULL | `true` |  | true = versi terbaru untuk kunci dedup (COALESCE(scene_id,0), COALESCE(nasa_scene_id,0), band, tier, dataset); FUSION didedup per file_path (K3). |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris dibuat. |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris terakhir diubah (trigger). |

**Constraint**

- `chk_dprods_processing_level` (CHECK): `CHECK (((processing_level IS NULL) OR ((processing_level)::text = ANY (ARRAY[('RAW'::character varying)::text, ('PROCESSED'::character varying)::text]))))`
- `chk_dprods_single_origin` (CHECK): `CHECK (((((source)::text = 'SENTINEL1'::text) AND (scene_id IS NOT NULL) AND (nasa_scene_id IS NULL)) OR (((source)::text = ANY (ARRAY[('MODIS'::character varying)::text, ('GPM'::character varying)::text])) AND (scene_id IS NULL) AND (nasa_scene_id IS NOT NULL)) OR (((source)::text = 'FUSION'::text) AND (scene_id IS NULL) AND (nasa_scene_id IS NULL))))`
- `data_products_dataset_id_fkey` (FK): `FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE`
- `data_products_job_id_fkey` (FK): `FOREIGN KEY (job_id) REFERENCES processing_jobs(job_id) ON DELETE RESTRICT`
- `data_products_nasa_scene_id_fkey` (FK): `FOREIGN KEY (nasa_scene_id) REFERENCES nasa_scenes(nasa_scene_id) ON DELETE CASCADE`
- `data_products_scene_id_fkey` (FK): `FOREIGN KEY (scene_id) REFERENCES satellite_scenes(scene_id) ON DELETE CASCADE`
- `data_products_source_fkey` (FK): `FOREIGN KEY (source) REFERENCES satellite_sources(source_code) ON UPDATE CASCADE`
- `data_products_pkey` (PK): `PRIMARY KEY (product_id)`
- `data_products_product_uuid_key` (UNIQUE): `UNIQUE (product_uuid)`

## dataset_jobs

Satu eksekusi pekerjaan atas sebuah dataset (buat, backfill, siklus Live, hidromet harian).

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `job_id` | `bigint` | NOT NULL | `nextval('dataset_jobs_job_id_seq'::regclass)` | PK | PK surrogate. |
| `job_uuid` | `uuid` | NOT NULL | `gen_random_uuid()` | UNIQUE | UUID stabil untuk referensi eksternal. |
| `dataset_id` | `integer` | NOT NULL |  | FK→datasets | FK -> datasets. |
| `job_type` | `character varying(20)` | NOT NULL | `'CREATE'::character varying` |  | CREATE \| BACKFILL \| LIVE_INGEST (siklus Live Area) \| HYDROMET_DAILY (job A). |
| `status` | `character varying(20)` | NOT NULL | `'QUEUED'::character varying` |  | QUEUED, PREPARING, DOWNLOADING, PROCESSING, PAUSED, CLEANUP, COMPLETED, FAILED, CANCELLED, WAITING_UPSTREAM (hidromet: granule GPM hari itu belum terbit, dicoba lagi maks. 3 hari). |
| `paused_at` | `timestamp with time zone` | NULL |  |  | Waktu job dijeda. |
| `paused_by` | `character varying(20)` | NULL |  |  | Penjeda: user \| system. |
| `pause_reason` | `text` | NULL |  |  | Alasan jeda. |
| `resumed_at` | `timestamp with time zone` | NULL |  |  | Waktu terakhir dilanjutkan. |
| `resume_count` | `smallint` | NOT NULL | `0` |  | Berapa kali job dilanjutkan. |
| `date_range_start` | `date` | NULL |  |  | Awal rentang tanggal yang dikerjakan job ini. |
| `date_range_end` | `date` | NULL |  |  | Akhir rentang tanggal yang dikerjakan job ini. |
| `total_scenes` | `integer` | NOT NULL | `0` |  | Jumlah unit (scene S1) yang dikerjakan. |
| `downloaded_count` | `integer` | NOT NULL | `0` |  | Unit yang selesai diunduh. |
| `processed_count` | `integer` | NOT NULL | `0` |  | Unit yang selesai diproses. |
| `failed_count` | `integer` | NOT NULL | `0` |  | Unit yang gagal. |
| `cleaned_count` | `integer` | NOT NULL | `0` |  | Unit yang selesai dibersihkan (tahap CLEANUP). |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu job dibuat. |
| `started_at` | `timestamp with time zone` | NULL |  |  | Waktu job mulai berjalan. |
| `completed_at` | `timestamp with time zone` | NULL |  |  | Waktu job selesai (berhasil atau gagal). |

**Constraint**

- `chk_dataset_job_status` (CHECK): `CHECK (((status)::text = ANY (ARRAY[('QUEUED'::character varying)::text, ('PREPARING'::character varying)::text, ('DOWNLOADING'::character varying)::text, ('PROCESSING'::character varying)::text, ('PAUSED'::character varying)::text, ('CLEANUP'::character varying)::text, ('COMPLETED'::character varying)::text, ('FAILED'::character varying)::text, ('CANCELLED'::character varying)::text, ('WAITING_UPSTREAM'::character varying)::text])))`
- `chk_dataset_job_type` (CHECK): `CHECK (((job_type)::text = ANY (ARRAY[('CREATE'::character varying)::text, ('BACKFILL'::character varying)::text, ('LIVE_INGEST'::character varying)::text, ('HYDROMET_DAILY'::character varying)::text])))`
- `dataset_jobs_dataset_id_fkey` (FK): `FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE`
- `dataset_jobs_pkey` (PK): `PRIMARY KEY (job_id)`
- `dataset_jobs_job_uuid_key` (UNIQUE): `UNIQUE (job_uuid)`

## dataset_source_config

Konfigurasi pemrosesan per (dataset, sumber). ETL membaca tabel ini untuk memutuskan sumber dan level yang dijalankan.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `config_id` | `integer` | NOT NULL | `nextval('dataset_source_config_config_id_seq'::regclass)` | PK | PK surrogate. |
| `dataset_id` | `integer` | NOT NULL |  | FK→datasets, UNIQUE | FK -> datasets. |
| `source_name` | `character varying(20)` | NOT NULL |  | FK→satellite_sources, UNIQUE | FK -> satellite_sources.source_code: SENTINEL1 \| MODIS \| GPM. |
| `processing_levels` | `text[]` | NOT NULL | `ARRAY['PROCESSED'::text]` |  | Level yang diminta: {RAW}, {PROCESSED}, atau {RAW,PROCESSED} (TEXT[] <= 2 elemen, M32). |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris dibuat. |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris terakhir diubah (trigger). |

**Constraint**

- `chk_source_config_levels_not_empty` (CHECK): `CHECK (((array_length(processing_levels, 1) IS NOT NULL) AND (array_length(processing_levels, 1) > 0)))`
- `chk_source_config_levels_valid` (CHECK): `CHECK ((processing_levels <@ ARRAY['RAW'::text, 'PROCESSED'::text]))`
- `chk_source_config_source_name` (CHECK): `CHECK (((source_name)::text = ANY (ARRAY[('SENTINEL1'::character varying)::text, ('MODIS'::character varying)::text, ('GPM'::character varying)::text])))`
- `dataset_source_config_dataset_id_fkey` (FK): `FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE`
- `dataset_source_config_source_name_fkey` (FK): `FOREIGN KEY (source_name) REFERENCES satellite_sources(source_code) ON UPDATE CASCADE`
- `dataset_source_config_pkey` (PK): `PRIMARY KEY (config_id)`
- `uq_source_config_dataset_source` (UNIQUE): `UNIQUE (dataset_id, source_name)`

## datasets

Dataset historis (Katalog, DATA_ENGINEER), dataset Live Area, dan dataset sistem HYDROMET_AOI.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `dataset_id` | `integer` | NOT NULL | `nextval('datasets_dataset_id_seq'::regclass)` | PK | PK surrogate. |
| `dataset_uuid` | `uuid` | NOT NULL | `gen_random_uuid()` | UNIQUE | UUID stabil untuk referensi eksternal. |
| `name` | `character varying(255)` | NOT NULL |  |  | Nama dataset; juga bagian nama folder data/datasets/{id}_{slug}. |
| `description` | `text` | NULL |  |  | Keterangan bebas. |
| `location_label` | `character varying(255)` | NULL |  |  | Label lokasi saat dibuat (salinan nama ROI). |
| `region_id` | `integer` | NULL |  | FK→regions_of_interest | FK -> regions_of_interest. Hanya ROI sistem (M27). |
| `bbox` | `geometry(Polygon,4326)` | NOT NULL |  |  | Bbox AOI dataset (Polygon EPSG:4326). |
| `bbox_wkt` | `text` | NOT NULL |  |  | Bbox yang sama dalam WKT, dipakai pipeline tanpa PostGIS. |
| `date_start` | `date` | NOT NULL |  |  | Awal rentang tanggal data (inklusif). |
| `date_end` | `date` | NOT NULL |  |  | Akhir rentang tanggal data (inklusif); maksimal 366 hari (app_settings.dataset.max_days). |
| `required_tiers` | `text[]` | NOT NULL | `ARRAY['COG'::text]` |  | Tier D14 yang disimpan, diturunkan dari dataset_source_config (TEXT[] <= 7 elemen, M32). Contoh {RAW,ALIGNED,DESPECKLED,COG}. |
| `fusion_strategy` | `character varying(20)` | NULL | `'FULL_COVERAGE'::character varying` | FK→fusion_strategies | FK -> fusion_strategies.strategy_code. NULL = dataset satu sumber (tanpa fusi). |
| `preview_options` | `text[]` | NOT NULL | `ARRAY['GRAYSCALE'::text, 'COLORED'::text, 'COMPOSITE'::text]` |  | Varian PNG tahap PREVIEW: GRAYSCALE \| COLORED \| COMPOSITE. Array kosong = tanpa varian (M32). |
| `fusion_output_only` | `boolean` | NOT NULL | `false` |  | true = hapus artefak per-satelit setelah stack fusion tanggal itu ditulis. |
| `s1_match_tolerance_days` | `smallint` | NOT NULL | `2` |  | FULL_COVERAGE: jarak hari maksimum meminjam scene S1 (0-14). |
| `quality_settings` | `jsonb` | NOT NULL | `'{}'::jsonb` |  | Pengaturan kualitas (JSONB, M32), mis. {"min_cloud_cover": 20, "orbit_direction": "ASCENDING"}. Ambang skor kualitas TIDAK di sini: quality_thresholds (K15). |
| `fusion_grid` | `jsonb` | NULL |  |  | Grid fusion yang dipaku: {transform, width, height, crs, source_product_id, pinned_at}. NULL = belum pernah fusi. |
| `dataset_kind` | `character varying(10)` | NOT NULL | `'STANDARD'::character varying` |  | STANDARD (Katalog / sistem) \| LIVE_AREA (satu Live Area). LIVE lama dihapus. |
| `is_system` | `boolean` | NOT NULL | `false` |  | true = dataset sistem (HYDROMET_AOI) yang disembunyikan dari Katalog (PIPELINE.md §3.1). |
| `status` | `character varying(20)` | NOT NULL | `'DRAFT'::character varying` |  | Status siklus: DRAFT, QUEUED, PREPARING, DOWNLOADING, PROCESSING, PAUSED, CLEANUP, COMPLETED, FAILED, CANCELLED, DELETING, DELETED. |
| `total_scenes` | `integer` | NOT NULL | `0` |  | Jumlah scene S1 yang ditemukan. |
| `completed_scenes` | `integer` | NOT NULL | `0` |  | Jumlah scene S1 yang selesai diproses. |
| `failed_scenes` | `integer` | NOT NULL | `0` |  | Jumlah scene S1 yang gagal. |
| `total_size_bytes` | `bigint` | NOT NULL | `0` |  | Total ukuran berkas dataset di disk (byte). |
| `is_deletable` | `boolean` | NOT NULL | `true` |  | false = tidak boleh dihapus lewat Katalog (mis. dataset Live Area). |
| `generate_preview` | `boolean` | NOT NULL | `true` |  | false = lewati tahap PREVIEW. |
| `created_by` | `integer` | NULL |  | FK→users | FK -> users: pembuat dataset. NULL untuk dataset sistem. |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris dibuat. |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris terakhir diubah (trigger). |
| `deleted_at` | `timestamp with time zone` | NULL |  |  | Waktu dataset dihapus (berkasnya dihapus, barisnya disimpan). |

**Constraint**

- `chk_dataset_date_range` (CHECK): `CHECK ((date_end >= date_start))`
- `chk_dataset_kind` (CHECK): `CHECK (((dataset_kind)::text = ANY (ARRAY[('STANDARD'::character varying)::text, ('LIVE_AREA'::character varying)::text])))`
- `chk_dataset_status` (CHECK): `CHECK (((status)::text = ANY (ARRAY[('DRAFT'::character varying)::text, ('QUEUED'::character varying)::text, ('PREPARING'::character varying)::text, ('DOWNLOADING'::character varying)::text, ('PROCESSING'::character varying)::text, ('PAUSED'::character varying)::text, ('CLEANUP'::character varying)::text, ('COMPLETED'::character varying)::text, ('FAILED'::character varying)::text, ('CANCELLED'::character varying)::text, ('DELETING'::character varying)::text, ('DELETED'::character varying)::text])))`
- `chk_datasets_s1_tolerance` (CHECK): `CHECK (((s1_match_tolerance_days >= 0) AND (s1_match_tolerance_days <= 14)))`
- `chk_preview_options` (CHECK): `CHECK ((preview_options <@ ARRAY['GRAYSCALE'::text, 'COLORED'::text, 'COMPOSITE'::text]))`
- `chk_required_tiers` (CHECK): `CHECK (((required_tiers <@ ARRAY['RAW'::text, 'ALIGNED'::text, 'DESPECKLED'::text, 'INDICES'::text, 'ACCUMULATED'::text, 'COG'::text, 'FUSED'::text]) AND (array_length(required_tiers, 1) > 0)))`
- `datasets_created_by_fkey` (FK): `FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL`
- `datasets_fusion_strategy_fkey` (FK): `FOREIGN KEY (fusion_strategy) REFERENCES fusion_strategies(strategy_code) ON UPDATE CASCADE`
- `datasets_region_id_fkey` (FK): `FOREIGN KEY (region_id) REFERENCES regions_of_interest(region_id) ON DELETE SET NULL`
- `datasets_pkey` (PK): `PRIMARY KEY (dataset_id)`
- `datasets_dataset_uuid_key` (UNIQUE): `UNIQUE (dataset_uuid)`

## disaster_events

Catatan kejadian bencana (GMLS, BPBD, input ANALYST). Tanpa data pribadi. Soft delete.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `event_id` | `bigint` | NOT NULL | `nextval('disaster_events_event_id_seq'::regclass)` | PK | PK surrogate. |
| `disaster_type_id` | `smallint` | NOT NULL |  | FK→disaster_types | FK -> disaster_types. |
| `region_id` | `integer` | NOT NULL |  | FK→administrative_regions | FK -> administrative_regions (kecamatan). |
| `village_name` | `character varying(100)` | NULL |  |  | Nama desa sebagai teks (COD-AB level 4 tidak tersedia). |
| `location` | `geometry(Point,4326)` | NULL |  |  | Titik kejadian opsional (Point EPSG:4326). |
| `event_date` | `date` | NOT NULL |  |  | Tanggal mulai kejadian. |
| `event_end_date` | `date` | NULL |  |  | Tanggal selesai (>= event_date), opsional. |
| `description` | `text` | NOT NULL |  |  | Uraian kejadian, 10-4000 karakter. |
| `impact_summary` | `character varying(500)` | NULL |  |  | Ringkasan dampak (rumah terdampak, akses jalan) tanpa data pribadi. |
| `info_source` | `character varying(30)` | NOT NULL |  |  | GMLS \| BPBD_LEBAK \| BNPB_DIBI \| MEDIA \| LAINNYA. |
| `source_reference` | `text` | NULL |  |  | URL atau nomor dokumen rujukan. |
| `is_verified` | `boolean` | NOT NULL | `false` |  | true = sudah diverifikasi (dipakai v_evaluasi_alert). |
| `verified_by` | `integer` | NULL |  | FK→users | FK -> users: pemverifikasi. |
| `recorded_by` | `integer` | NOT NULL |  | FK→users | FK -> users: pencatat. |
| `recorded_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu dicatat. |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris terakhir diubah (trigger). |
| `deleted_at` | `timestamp with time zone` | NULL |  |  | Soft delete; NULL = aktif. |

**Constraint**

- `disaster_events_check` (CHECK): `CHECK (((event_end_date IS NULL) OR (event_end_date >= event_date)))`
- `disaster_events_description_check` (CHECK): `CHECK (((length(description) >= 10) AND (length(description) <= 4000)))`
- `disaster_events_info_source_check` (CHECK): `CHECK (((info_source)::text = ANY (ARRAY[('GMLS'::character varying)::text, ('BPBD_LEBAK'::character varying)::text, ('BNPB_DIBI'::character varying)::text, ('MEDIA'::character varying)::text, ('LAINNYA'::character varying)::text])))`
- `disaster_events_disaster_type_id_fkey` (FK): `FOREIGN KEY (disaster_type_id) REFERENCES disaster_types(disaster_type_id)`
- `disaster_events_recorded_by_fkey` (FK): `FOREIGN KEY (recorded_by) REFERENCES users(user_id)`
- `disaster_events_region_id_fkey` (FK): `FOREIGN KEY (region_id) REFERENCES administrative_regions(region_id)`
- `disaster_events_verified_by_fkey` (FK): `FOREIGN KEY (verified_by) REFERENCES users(user_id)`
- `disaster_events_pkey` (PK): `PRIMARY KEY (event_id)`

## disaster_types

Master jenis bencana. ADMIN dapat menambah jenis tanpa ubah kode (uji adaptability).

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `disaster_type_id` | `smallint` | NOT NULL | `nextval('disaster_types_disaster_type_id_seq'::regclass)` | PK | PK surrogate. |
| `type_code` | `character varying(30)` | NOT NULL |  | UNIQUE | Alternate key: BANJIR \| BANJIR_BANDANG \| LONGSOR \| KEKERINGAN. |
| `type_name` | `character varying(100)` | NOT NULL |  |  | Label UI. |
| `category` | `character varying(30)` | NOT NULL | `'HIDROMETEOROLOGI'::character varying` |  | Kelompok bencana, default HIDROMETEOROLOGI. |
| `indicator_bands` | `character varying(100)` | NULL |  |  | Teks informatif band indikator, mis. "RAIN_24H, VH". |
| `is_active` | `boolean` | NOT NULL | `true` |  | false = jenis tidak ditawarkan lagi di form. |

**Constraint**

- `disaster_types_pkey` (PK): `PRIMARY KEY (disaster_type_id)`
- `disaster_types_type_code_key` (UNIQUE): `UNIQUE (type_code)`

## fusion_products

Registri stack HDF5 multi-sensor (S1 + MODIS + GPM) per dataset per tanggal per level.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `fusion_id` | `bigint` | NOT NULL | `nextval('fusion_products_fusion_id_seq'::regclass)` | PK | PK surrogate. |
| `dataset_id` | `integer` | NULL |  | FK→datasets, UNIQUE | FK -> datasets pemilik stack (bagian kunci unik). |
| `feature_date` | `date` | NOT NULL |  | UNIQUE | Tanggal fitur stack (hari UTC). |
| `region_id` | `integer` | NOT NULL |  | FK→regions_of_interest | FK -> regions_of_interest. |
| `s1_scene_id` | `integer` | NULL |  | FK→satellite_scenes | FK -> satellite_scenes: scene S1 yang dipakai; NULL bila hari itu tanpa S1. |
| `modis_scene_id` | `bigint` | NULL |  | FK→nasa_scenes | FK -> nasa_scenes: granule MODIS penanda. |
| `gpm_scene_id` | `bigint` | NULL |  | FK→nasa_scenes | FK -> nasa_scenes: granule GPM penanda. |
| `days_since_s1` | `integer` | NOT NULL |  |  | Selisih hari terbesar antar sumber terhadap tanggal fitur. |
| `feature_stack_path` | `text` | NOT NULL |  |  | Path berkas HDF5. |
| `fusion_strategy` | `character varying(20)` | NULL | `'FULL_COVERAGE'::character varying` | FK→fusion_strategies | FK -> fusion_strategies.strategy_code. |
| `processing_level` | `character varying(20)` | NOT NULL | `'PROCESSED'::character varying` | UNIQUE | Level input stack: RAW (dari ALIGNED) \| PROCESSED (dari COG). |
| `temporal_offset_modis` | `integer` | NULL |  |  | Selisih hari MODIS terhadap tanggal fitur. NULL = MODIS tidak ikut. |
| `temporal_offset_gpm` | `integer` | NULL |  |  | Selisih hari GPM terhadap tanggal fitur. NULL = GPM tidak ikut. |
| `s1_offset_days` | `smallint` | NULL |  |  | Jarak hari S1 yang dipakai: 0 = same-day, NULL = tanpa S1. |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris dibuat. |

**Constraint**

- `fusion_products_processing_level_check` (CHECK): `CHECK (((processing_level)::text = ANY (ARRAY[('RAW'::character varying)::text, ('PROCESSED'::character varying)::text])))`
- `fusion_products_dataset_id_fkey` (FK): `FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE`
- `fusion_products_fusion_strategy_fkey` (FK): `FOREIGN KEY (fusion_strategy) REFERENCES fusion_strategies(strategy_code) ON UPDATE CASCADE`
- `fusion_products_gpm_scene_id_fkey` (FK): `FOREIGN KEY (gpm_scene_id) REFERENCES nasa_scenes(nasa_scene_id) ON DELETE SET NULL`
- `fusion_products_modis_scene_id_fkey` (FK): `FOREIGN KEY (modis_scene_id) REFERENCES nasa_scenes(nasa_scene_id) ON DELETE SET NULL`
- `fusion_products_region_id_fkey` (FK): `FOREIGN KEY (region_id) REFERENCES regions_of_interest(region_id) ON DELETE RESTRICT`
- `fusion_products_s1_scene_id_fkey` (FK): `FOREIGN KEY (s1_scene_id) REFERENCES satellite_scenes(scene_id) ON DELETE SET NULL`
- `fusion_products_pkey` (PK): `PRIMARY KEY (fusion_id)`
- `uq_fusion_dataset_date_level` (UNIQUE): `UNIQUE (dataset_id, feature_date, processing_level)`

## fusion_strategies

Master strategi fusion (M9). Dirujuk datasets.fusion_strategy dan fusion_products.fusion_strategy lewat strategy_code.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `strategy_id` | `smallint` | NOT NULL | `nextval('fusion_strategies_strategy_id_seq'::regclass)` | PK | PK surrogate. |
| `strategy_code` | `character varying(20)` | NOT NULL |  | UNIQUE | Alternate key: CO_OCCURRENCE \| FULL_COVERAGE \| HYBRID. |
| `download_axis` | `text` | NOT NULL |  |  | Sumbu unduh: tanggal MODIS/GPM mana yang diambil. |
| `assemble_axis` | `text` | NOT NULL |  |  | Sumbu rakit: tanggal mana yang menjadi satu berkas HDF5. |
| `description` | `text` | NULL |  |  | Uraian strategi. |

**Constraint**

- `fusion_strategies_pkey` (PK): `PRIMARY KEY (strategy_id)`
- `fusion_strategies_strategy_code_key` (UNIQUE): `UNIQUE (strategy_code)`

## generated_reports

Laporan PDF mingguan/bulanan yang dibuat (M18). Akses dibatasi RLS per audiens (tahap keamanan).

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `report_id` | `bigint` | NOT NULL | `nextval('generated_reports_report_id_seq'::regclass)` | PK | PK surrogate. |
| `report_type_id` | `smallint` | NOT NULL |  | FK→report_types | FK -> report_types. |
| `period_start` | `date` | NOT NULL |  |  | Awal periode (Senin / tanggal 1, WIB). |
| `period_end` | `date` | NOT NULL |  |  | Akhir periode (Minggu / akhir bulan, WIB). |
| `file_path` | `text` | NOT NULL |  |  | Path PDF: data/reports/{report_code}/{YYYY}/...pdf. |
| `file_size_bytes` | `bigint` | NOT NULL |  |  | Ukuran PDF (byte). |
| `checksum_sha256` | `character(64)` | NOT NULL |  |  | SHA-256 PDF (64 hex). |
| `status` | `character varying(10)` | NOT NULL |  |  | READY \| FAILED \| SUPERSEDED (digantikan regenerasi). |
| `error_message` | `text` | NULL |  |  | Pesan galat bila FAILED. |
| `generated_by` | `integer` | NULL |  | FK→users | FK -> users: ADMIN yang meregenerasi. NULL = scheduler. |
| `generated_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu laporan dibuat. |

**Constraint**

- `generated_reports_check` (CHECK): `CHECK ((period_end >= period_start))`
- `generated_reports_file_size_bytes_check` (CHECK): `CHECK ((file_size_bytes >= 0))`
- `generated_reports_status_check` (CHECK): `CHECK (((status)::text = ANY (ARRAY[('READY'::character varying)::text, ('FAILED'::character varying)::text, ('SUPERSEDED'::character varying)::text])))`
- `generated_reports_generated_by_fkey` (FK): `FOREIGN KEY (generated_by) REFERENCES users(user_id)`
- `generated_reports_report_type_id_fkey` (FK): `FOREIGN KEY (report_type_id) REFERENCES report_types(report_type_id)`
- `generated_reports_pkey` (PK): `PRIMARY KEY (report_id)`

## live_areas

Live Area: satu AOI yang dipantau otomatis per lintasan S1 (maksimal app_settings.live.max_areas).

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `area_id` | `integer` | NOT NULL | `nextval('live_areas_area_id_seq'::regclass)` | PK | PK surrogate. |
| `dataset_id` | `integer` | NULL |  | FK→datasets | FK -> datasets berjenis LIVE_AREA yang diproses pipeline. |
| `name` | `character varying(255)` | NOT NULL |  |  | Nama area, mis. "Lebak Selatan". |
| `region_id` | `integer` | NULL |  | FK→regions_of_interest | FK -> regions_of_interest. |
| `location_label` | `character varying(255)` | NULL |  |  | Label lokasi (salinan nama ROI). |
| `bbox_wkt` | `text` | NOT NULL |  |  | Bbox area dalam WKT. |
| `retention` | `smallint` | NOT NULL | `6` |  | Jumlah scene terbaru yang ditampilkan kartu dan dipakai prakiraan (1-60, default 6). Berkas scene disimpan menurut umur: app_settings.storage.raster_retention_days (M58). |
| `enabled` | `boolean` | NOT NULL | `true` |  | false = siklus terjadwal dilewati. |
| `status` | `character varying(20)` | NOT NULL | `'BACKFILLING'::character varying` |  | BACKFILLING \| ACTIVE \| RUNNING \| WAITING \| ERROR \| DELETED. |
| `status_message` | `text` | NULL |  |  | Pesan status untuk kartu Live. |
| `last_checked_at` | `timestamp with time zone` | NULL |  |  | Waktu siklus terakhir memeriksa scene baru. |
| `forecast` | `jsonb` | NOT NULL | `'{}'::jsonb` |  | Prakiraan statistik terakhir (JSONB tampilan, M12). |
| `forecast_updated_at` | `timestamp with time zone` | NULL |  |  | Waktu prakiraan dihitung. |
| `updated_by` | `integer` | NULL |  | FK→users | FK -> users: ADMIN yang terakhir mengubah. |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris dibuat. |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris terakhir diubah (trigger). |
| `deleted_at` | `timestamp with time zone` | NULL |  |  | Waktu area dihapus (log tetap disimpan). |

**Constraint**

- `chk_live_area_retention` (CHECK): `CHECK (((retention >= 1) AND (retention <= 60)))`
- `chk_live_area_status` (CHECK): `CHECK (((status)::text = ANY (ARRAY[('BACKFILLING'::character varying)::text, ('ACTIVE'::character varying)::text, ('RUNNING'::character varying)::text, ('WAITING'::character varying)::text, ('ERROR'::character varying)::text, ('DELETED'::character varying)::text])))`
- `live_areas_dataset_id_fkey` (FK): `FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE SET NULL`
- `live_areas_region_id_fkey` (FK): `FOREIGN KEY (region_id) REFERENCES regions_of_interest(region_id) ON DELETE SET NULL`
- `live_areas_updated_by_fkey` (FK): `FOREIGN KEY (updated_by) REFERENCES users(user_id)`
- `live_areas_pkey` (PK): `PRIMARY KEY (area_id)`

## live_events

Log langkah siklus Live per area (append-only, tanpa FK agar bertahan setelah area dihapus).

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `event_id` | `bigint` | NOT NULL | `nextval('live_events_event_id_seq'::regclass)` | PK | PK surrogate. |
| `area_id` | `integer` | NOT NULL |  |  | live_areas.area_id (tanpa FK). |
| `scene_date` | `date` | NULL |  |  | Tanggal scene terkait, bila ada. |
| `step` | `character varying(40)` | NOT NULL |  |  | Langkah siklus, mis. DISCOVER, INGEST, PREVIEW, RETENTION. |
| `status` | `character varying(20)` | NOT NULL |  |  | Status langkah, mis. OK, FAILED, SKIPPED. |
| `message` | `text` | NOT NULL |  |  | Pesan langkah. |
| `details` | `jsonb` | NOT NULL | `'{}'::jsonb` |  | Detail terstruktur (JSONB). |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu kejadian. |

**Constraint**

- `live_events_pkey` (PK): `PRIMARY KEY (event_id)`

## live_scene_metrics

Metrik numerik scene Live, satu baris per band x metrik (1NF, M31). Tetap ada setelah berkas scene dihapus retensi.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `metric_id` | `bigint` | NOT NULL | `nextval('live_scene_metrics_metric_id_seq'::regclass)` | PK | PK surrogate. |
| `live_scene_id` | `bigint` | NOT NULL |  | FK→live_scenes, UNIQUE | FK -> live_scenes. |
| `band_id` | `smallint` | NOT NULL |  | FK→spectral_bands, UNIQUE | FK -> spectral_bands: VV, VH, FLOOD, NDVI, NDWI, RAIN_24H/72H/7D, WATER_CHANGE. |
| `metric_name` | `character varying(30)` | NOT NULL |  | UNIQUE | Nama metrik, mis. mean, pct_below_threshold, valid_pct, new_km2, receded_km2, persistent_km2, same_orbit. |
| `value` | `numeric(12,4)` | NULL |  |  | Nilai dalam satuan metrik (dB, %, mm, km2, indeks). NULL = tidak ada piksel valid. |
| `source_date` | `date` | NULL |  |  | Tanggal data sumber (MODIS/GPM bisa tanggal terdekat D-1). |
| `ref_live_scene_id` | `bigint` | NULL |  | FK→live_scenes | FK -> live_scenes: scene pembanding untuk WATER_CHANGE. |

**Constraint**

- `live_scene_metrics_band_id_fkey` (FK): `FOREIGN KEY (band_id) REFERENCES spectral_bands(band_id)`
- `live_scene_metrics_live_scene_id_fkey` (FK): `FOREIGN KEY (live_scene_id) REFERENCES live_scenes(live_scene_id) ON DELETE CASCADE`
- `live_scene_metrics_ref_live_scene_id_fkey` (FK): `FOREIGN KEY (ref_live_scene_id) REFERENCES live_scenes(live_scene_id) ON DELETE SET NULL`
- `live_scene_metrics_pkey` (PK): `PRIMARY KEY (metric_id)`
- `uq_live_scene_metric` (UNIQUE): `UNIQUE (live_scene_id, band_id, metric_name)`

## live_scenes

Satu scene Live (tanggal lintasan S1) per area. Tidak pernah dihapus: retensi hanya menghapus berkas dan mengisi deleted_at. Sengaja tanpa FK agar hidup lebih lama dari area/dataset.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `live_scene_id` | `bigint` | NOT NULL | `nextval('live_scenes_live_scene_id_seq'::regclass)` | PK | PK surrogate. |
| `area_id` | `integer` | NOT NULL |  | UNIQUE | live_areas.area_id (tanpa FK, lihat komentar tabel). |
| `dataset_id` | `integer` | NULL |  |  | datasets.dataset_id (tanpa FK). |
| `scene_date` | `date` | NOT NULL |  | UNIQUE | Tanggal akuisisi S1 (hari UTC). |
| `s1_product_ids` | `text[]` | NOT NULL | `ARRAY[]::text[]` |  | Identifier produk S1 yang membentuk scene (TEXT[] <= 3 frame, M32). |
| `status` | `character varying(20)` | NOT NULL | `'PROCESSING'::character varying` |  | PROCESSING \| READY \| PARTIAL (sumber pendukung gagal) \| FAILED \| DELETED. |
| `source_status` | `jsonb` | NOT NULL | `'{}'::jsonb` |  | Status per sumber untuk tampilan (JSONB, tidak dikueri), termasuk deskriptor teks metrik di [sumber].meta (run IMERG, periode komposit). Angka metrik ada di live_scene_metrics (M31). |
| `interpretations` | `jsonb` | NOT NULL | `'{}'::jsonb` |  | Kalimat kondisi per variabel (JSONB tampilan). |
| `area_status` | `jsonb` | NOT NULL | `'{}'::jsonb` |  | Status area ringkas {level, label, sentence} (JSONB tampilan). |
| `previews` | `jsonb` | NOT NULL | `'{}'::jsonb` |  | Manifest preview PNG per kunci (JSONB tampilan). |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris dibuat. |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris terakhir diubah (trigger). |
| `deleted_at` | `timestamp with time zone` | NULL |  |  | Waktu berkas scene dihapus retensi; baris tetap ada. |
| `delete_reason` | `text` | NULL |  |  | Alasan penghapusan berkas, mis. retention. |
| `deleted_files` | `jsonb` | NOT NULL | `'[]'::jsonb` |  | Daftar berkas yang dihapus (JSONB array). |
| `freed_bytes` | `bigint` | NOT NULL | `0` |  | Ruang disk yang dibebaskan (byte). |

**Constraint**

- `chk_live_scene_status` (CHECK): `CHECK (((status)::text = ANY ((ARRAY['PROCESSING'::character varying, 'READY'::character varying, 'PARTIAL'::character varying, 'FAILED'::character varying, 'DELETED'::character varying, 'INCOMPLETE'::character varying])::text[])))`
- `live_scenes_pkey` (PK): `PRIMARY KEY (live_scene_id)`
- `uq_live_scene_area_date` (UNIQUE): `UNIQUE (area_id, scene_date)`

## nasa_scenes

Registri granule MODIS dan GPM (satu baris per sumber/produk/tile/tanggal).

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `nasa_scene_id` | `bigint` | NOT NULL | `nextval('nasa_scenes_nasa_scene_id_seq'::regclass)` | PK | PK surrogate. |
| `source` | `character varying(20)` | NOT NULL |  | FK→satellite_sources, UNIQUE | FK -> satellite_sources.source_code: MODIS \| GPM. |
| `tile_id` | `character varying(10)` | NOT NULL |  | UNIQUE | Tile MODIS (mis. MOSAIC dari h28v09) atau GLOBAL untuk GPM. |
| `product_short_name` | `character varying(50)` | NOT NULL |  | UNIQUE | Short name produk NASA, mis. MCDWD_L3_F2_NRT, MOD09A1, GPM_3IMERGDF. |
| `acquisition_date` | `date` | NOT NULL |  | UNIQUE | Tanggal data (hari UTC, M28). Untuk komposit MOD09A1: awal periode. |
| `region_id` | `integer` | NOT NULL |  | FK→regions_of_interest | FK -> regions_of_interest: ROI yang memicu unduhan. |
| `raw_file_path` | `text` | NULL |  |  | Path berkas hasil (atau granule) di disk. |
| `download_url` | `text` | NULL |  |  | URL granule di penyedia. |
| `run_type` | `character varying(5)` | NULL |  |  | GPM IMERG run: F (Final) \| L (Late) \| E (Early). NULL untuk MODIS (M6). |
| `is_available` | `boolean` | NOT NULL | `true` |  | false = granule tidak tersedia lagi. |
| `is_valid` | `boolean` | NOT NULL | `true` |  | false = dinonaktifkan ADMIN (soft delete, M24). |
| `invalidated_by` | `integer` | NULL |  | FK→users | FK -> users: ADMIN yang menonaktifkan. |
| `invalidated_at` | `timestamp with time zone` | NULL |  |  | Waktu dinonaktifkan. |
| `invalid_reason` | `text` | NULL |  |  | Alasan wajib saat dinonaktifkan. |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris dibuat. |

**Constraint**

- `chk_nasa_invalidation` (CHECK): `CHECK ((is_valid OR ((invalidated_at IS NOT NULL) AND (invalid_reason IS NOT NULL))))`
- `nasa_scenes_run_type_check` (CHECK): `CHECK (((run_type)::text = ANY (ARRAY[('F'::character varying)::text, ('L'::character varying)::text, ('E'::character varying)::text])))`
- `nasa_scenes_invalidated_by_fkey` (FK): `FOREIGN KEY (invalidated_by) REFERENCES users(user_id)`
- `nasa_scenes_region_id_fkey` (FK): `FOREIGN KEY (region_id) REFERENCES regions_of_interest(region_id) ON DELETE RESTRICT`
- `nasa_scenes_source_fkey` (FK): `FOREIGN KEY (source) REFERENCES satellite_sources(source_code) ON UPDATE CASCADE`
- `nasa_scenes_pkey` (PK): `PRIMARY KEY (nasa_scene_id)`
- `uq_nasa_scene` (UNIQUE): `UNIQUE (source, tile_id, product_short_name, acquisition_date)`

## notify_sent

Butir tidak normal yang sudah dikirim lewat email (M64). Kunci unik (pengguna, kecamatan, butir, tanggal data) mencegah pengiriman ulang data yang sama.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `notify_id` | `bigint` | NOT NULL | `nextval('notify_sent_notify_id_seq'::regclass)` | PK | PK surrogate. |
| `user_id` | `integer` | NOT NULL |  | FK→users, UNIQUE | FK -> users penerima. |
| `region_id` | `integer` | NOT NULL |  | FK→administrative_regions, UNIQUE | FK -> administrative_regions (kecamatan). |
| `item_key` | `character varying(20)` | NOT NULL |  | UNIQUE | Butir kalimat kondisi (mis. gpm_rain_7d, s1_vh, modis_flood) atau "alert" untuk alert hujan BMKG. |
| `data_date` | `date` | NOT NULL |  | UNIQUE | Tanggal data yang menunjukkan kondisi tidak normal (tanggal observasi satelit atau alert). |
| `level` | `smallint` | NOT NULL |  |  | Tingkat saat dikirim: 1 Waspada, 2 Tinggi. |
| `sent_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu email terkirim. |

**Constraint**

- `notify_sent_level_check` (CHECK): `CHECK (((level >= 1) AND (level <= 2)))`
- `notify_sent_region_id_fkey` (FK): `FOREIGN KEY (region_id) REFERENCES administrative_regions(region_id)`
- `notify_sent_user_id_fkey` (FK): `FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE`
- `notify_sent_pkey` (PK): `PRIMARY KEY (notify_id)`
- `uq_notify_sent` (UNIQUE): `UNIQUE (user_id, region_id, item_key, data_date)`

## processing_jobs

Eksekusi satu tahap pipeline (scene/granule x tahap x percobaan). Jangkar: scene S1, granule NASA, atau tidak keduanya untuk FUSION (M30).

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `job_id` | `bigint` | NOT NULL | `nextval('processing_jobs_job_id_seq'::regclass)` | PK | PK surrogate. |
| `job_uuid` | `uuid` | NOT NULL | `gen_random_uuid()` | UNIQUE | UUID stabil untuk referensi eksternal. |
| `scene_id` | `integer` | NULL |  | FK→satellite_scenes, UNIQUE | FK -> satellite_scenes: scene S1 yang diproses. NULL untuk job MODIS/GPM/FUSION. |
| `nasa_scene_id` | `bigint` | NULL |  | FK→nasa_scenes | FK -> nasa_scenes: granule MODIS/GPM yang diproses. NULL untuk job S1/FUSION (M30). |
| `stage_id` | `integer` | NOT NULL |  | FK→processing_stages, UNIQUE | FK -> processing_stages. |
| `attempt_number` | `smallint` | NOT NULL | `1` | UNIQUE | Percobaan ke berapa untuk (scene, tahap). |
| `status` | `job_status_enum` | NOT NULL | `'QUEUED'::job_status_enum` |  | QUEUED \| RUNNING \| SUCCESS \| FAILED \| CANCELLED \| WAITING_UPSTREAM (granule hulu belum terbit) \| SKIPPED_LOCKED (run scheduler dilewati: advisory lock dipegang worker lain). |
| `queued_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu masuk antrean. |
| `started_at` | `timestamp with time zone` | NULL |  |  | Waktu mulai. |
| `completed_at` | `timestamp with time zone` | NULL |  |  | Waktu selesai. |
| `duration_seconds` | `numeric(10,3)` | NULL | `GENERATED` |  | Durasi (detik), GENERATED dari completed_at - started_at. |
| `worker_hostname` | `character varying(100)` | NULL |  |  | Host yang menjalankan tahap. |
| `cpu_usage_percent` | `numeric(7,2)` | NULL |  |  | Pemakaian CPU total seluruh core (24 core = sampai 2400%). |
| `memory_usage_mb` | `numeric(10,2)` | NULL |  |  | Pemakaian memori puncak (MB). |
| `input_size_mb` | `numeric(12,3)` | NULL |  |  | Ukuran input (MB). |
| `output_size_mb` | `numeric(12,3)` | NULL |  |  | Ukuran output (MB). |
| `error_code` | `character varying(50)` | NULL |  |  | Kode galat (nama exception), mis. MemoryError. |
| `error_message` | `text` | NULL |  |  | Pesan galat. |
| `log_file_path` | `text` | NULL |  |  | Path berkas log tahap. |
| `parameters_json` | `jsonb` | NOT NULL | `'{}'::jsonb` |  | Parameter reproduksibilitas (JSONB, M32): versi software, window Lee, run GPM, ambang. Nama "parameters" di DATABASE.md §4.1 (K8). |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris dibuat. |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris terakhir diubah (trigger). |

**Constraint**

- `chk_pjobs_single_anchor` (CHECK): `CHECK (((scene_id IS NULL) OR (nasa_scene_id IS NULL)))`
- `processing_jobs_nasa_scene_id_fkey` (FK): `FOREIGN KEY (nasa_scene_id) REFERENCES nasa_scenes(nasa_scene_id) ON DELETE CASCADE`
- `processing_jobs_scene_id_fkey` (FK): `FOREIGN KEY (scene_id) REFERENCES satellite_scenes(scene_id) ON DELETE CASCADE`
- `processing_jobs_stage_id_fkey` (FK): `FOREIGN KEY (stage_id) REFERENCES processing_stages(stage_id) ON DELETE RESTRICT`
- `processing_jobs_pkey` (PK): `PRIMARY KEY (job_id)`
- `processing_jobs_job_uuid_key` (UNIQUE): `UNIQUE (job_uuid)`
- `uq_job_scene_stage_attempt` (UNIQUE): `UNIQUE (scene_id, stage_id, attempt_number)`

## processing_logs

Log pipeline terstruktur append-only: satu baris per kejadian tahap (STARTED/RUNNING/COMPLETED/FAILED).

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `log_id` | `bigint` | NOT NULL | `nextval('processing_logs_log_id_seq'::regclass)` | PK | PK surrogate. |
| `log_uuid` | `uuid` | NOT NULL | `gen_random_uuid()` | UNIQUE | UUID stabil untuk referensi eksternal. |
| `dataset_id` | `integer` | NOT NULL |  | FK→datasets | FK -> datasets. |
| `scene_id` | `character varying(255)` | NOT NULL |  |  | Kunci unit kerja sebagai teks (product identifier S1 atau tanggal aux), bukan FK. |
| `module` | `character varying(50)` | NOT NULL |  |  | Modul ETL penulis log, mis. M5_ORCH. |
| `stage` | `character varying(50)` | NOT NULL |  |  | Nama tahap, mis. DOWNLOAD, FUSION. |
| `status` | `character varying(20)` | NOT NULL |  |  | STARTED \| RUNNING \| COMPLETED \| FAILED \| SKIPPED. |
| `message` | `text` | NOT NULL |  |  | Pesan log (Bahasa Inggris, M21). |
| `details` | `jsonb` | NOT NULL | `'{}'::jsonb` |  | Detail terstruktur (durasi, ukuran, memori, kualitas) dalam JSONB. |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu kejadian. |

**Constraint**

- `processing_logs_dataset_id_fkey` (FK): `FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE`
- `processing_logs_pkey` (PK): `PRIMARY KEY (log_id)`
- `processing_logs_log_uuid_key` (UNIQUE): `UNIQUE (log_uuid)`

## processing_stages

Master tahap pipeline (S1/MODIS/GPM/FUSION/PREVIEW + HYDROMET_AGGREGATE, ALERT_CHECK, WATER_CHANGE, REPORT_BUILD).

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `stage_id` | `integer` | NOT NULL | `nextval('processing_stages_stage_id_seq'::regclass)` | PK | PK surrogate. |
| `stage_name` | `character varying(50)` | NOT NULL |  | UNIQUE | Nama tahap yang dipakai kode, mis. LEE_FILTER, GOLD_EXPORT, HYDROMET_AGGREGATE. |
| `stage_code` | `character varying(20)` | NOT NULL |  | UNIQUE | Kode pendek tahap, mis. LF, GE, HA. |
| `stage_order` | `smallint` | NOT NULL |  | UNIQUE | Urutan pendaftaran (unik). Urutan eksekusi nyata ditentukan kode orchestrator. |
| `description` | `text` | NULL |  |  | Uraian tahap. |
| `source_code` | `character varying(20)` | NULL |  | FK→satellite_sources | FK -> satellite_sources.source_code bila tahap khusus satu sumber; NULL = lintas sumber. |
| `timeout_minutes` | `smallint` | NOT NULL | `60` |  | Batas waktu tahap (menit). |
| `retry_count` | `smallint` | NOT NULL | `3` |  | Jumlah percobaan ulang yang diizinkan. |
| `retry_delay_sec` | `smallint` | NOT NULL | `30` |  | Jeda antar percobaan ulang (detik). |
| `is_mandatory` | `boolean` | NOT NULL | `true` |  | false = tahap opsional (mis. PREVIEW). |
| `is_active` | `boolean` | NOT NULL | `true` |  | false = tahap tidak dipakai lagi. |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris dibuat. |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris terakhir diubah (trigger). |

**Constraint**

- `processing_stages_source_code_fkey` (FK): `FOREIGN KEY (source_code) REFERENCES satellite_sources(source_code) ON UPDATE CASCADE`
- `processing_stages_pkey` (PK): `PRIMARY KEY (stage_id)`
- `processing_stages_stage_code_key` (UNIQUE): `UNIQUE (stage_code)`
- `processing_stages_stage_name_key` (UNIQUE): `UNIQUE (stage_name)`
- `processing_stages_stage_order_key` (UNIQUE): `UNIQUE (stage_order)`

## quality_alerts

Peringatan kualitas/operasional pipeline (mis. skor QA < 60). Tabel alert_events DataLab yang diganti nama; nama alert_events kini untuk alert hujan.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `alert_id` | `bigint` | NOT NULL | `nextval('quality_alerts_alert_id_seq'::regclass)` | PK | PK surrogate. |
| `alert_uuid` | `uuid` | NOT NULL | `gen_random_uuid()` | UNIQUE | UUID stabil untuk referensi eksternal. |
| `event_type` | `alert_event_type_enum` | NOT NULL |  |  | DATA_ARRIVAL \| QUALITY_WARNING \| PIPELINE_ERROR \| THRESHOLD_BREACH \| SYSTEM_ALERT. |
| `severity` | `alert_severity_enum` | NOT NULL | `'INFO'::alert_severity_enum` |  | INFO \| WARNING \| CRITICAL. |
| `scene_id` | `integer` | NULL |  | FK→satellite_scenes | FK -> satellite_scenes terkait. |
| `job_id` | `bigint` | NULL |  | FK→processing_jobs | FK -> processing_jobs terkait. |
| `product_id` | `bigint` | NULL |  | FK→data_products | FK -> data_products terkait. |
| `title` | `character varying(200)` | NOT NULL |  |  | Judul singkat. |
| `message` | `text` | NOT NULL |  |  | Uraian peringatan. |
| `metadata_json` | `jsonb` | NULL | `'{}'::jsonb` |  | Konteks terstruktur (JSONB): skor, band, ambang. |
| `is_resolved` | `boolean` | NOT NULL | `false` |  | true = sudah ditangani. |
| `resolved_at` | `timestamp with time zone` | NULL |  |  | Waktu ditangani. |
| `resolved_by` | `character varying(100)` | NULL |  |  | Penangan (teks bebas, warisan). |
| `resolution_note` | `text` | NULL |  |  | Catatan penanganan. |
| `triggered_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu peringatan terpicu. |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris dibuat. |

**Constraint**

- `quality_alerts_job_id_fkey` (FK): `FOREIGN KEY (job_id) REFERENCES processing_jobs(job_id) ON DELETE SET NULL`
- `quality_alerts_product_id_fkey` (FK): `FOREIGN KEY (product_id) REFERENCES data_products(product_id) ON DELETE SET NULL`
- `quality_alerts_scene_id_fkey` (FK): `FOREIGN KEY (scene_id) REFERENCES satellite_scenes(scene_id) ON DELETE SET NULL`
- `quality_alerts_pkey` (PK): `PRIMARY KEY (alert_id)`
- `quality_alerts_alert_uuid_key` (UNIQUE): `UNIQUE (alert_uuid)`

## quality_metrics

Hasil kontrol kualitas radiometrik per scene S1 per band (tahap QUALITY_ANALYTICS).

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `metric_id` | `bigint` | NOT NULL | `nextval('quality_metrics_metric_id_seq'::regclass)` | PK | PK surrogate. |
| `scene_id` | `integer` | NOT NULL |  | FK→satellite_scenes, UNIQUE | FK -> satellite_scenes. |
| `product_id` | `bigint` | NOT NULL |  | FK→data_products, UNIQUE | FK -> data_products: COG yang dinilai. |
| `band_name` | `character varying(10)` | NOT NULL |  | UNIQUE | VV \| VH. |
| `assessed_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu penilaian. |
| `total_pixels` | `bigint` | NOT NULL |  |  | Jumlah piksel raster. |
| `valid_pixels` | `bigint` | NOT NULL |  |  | Jumlah piksel bernilai sah. |
| `nodata_pixels` | `bigint` | NOT NULL | `0` |  | Jumlah piksel NoData. |
| `nodata_percent` | `numeric(5,2)` | NULL | `GENERATED` |  | Persen NoData (%), GENERATED. |
| `backscatter_mean_db` | `numeric(8,4)` | NULL |  |  | Rata-rata backscatter (dB). |
| `backscatter_std_db` | `numeric(8,4)` | NULL |  |  | Simpangan baku backscatter (dB). |
| `backscatter_min_db` | `numeric(8,4)` | NULL |  |  | Backscatter minimum (dB). |
| `backscatter_max_db` | `numeric(8,4)` | NULL |  |  | Backscatter maksimum (dB). |
| `cloud_threshold_percent` | `numeric(5,2)` | NOT NULL | `20.0` |  | Ambang awan (%) warisan; tidak relevan untuk SAR. |
| `radiometric_consistency` | `boolean` | NULL |  |  | true bila rata-rata backscatter dalam rentang sah (-35..5 dB). |
| `speckle_index` | `numeric(8,4)` | NULL |  |  | Indeks speckle (koefisien variasi); makin kecil makin baik. |
| `quality_score` | `numeric(5,2)` | NOT NULL |  |  | Skor komposit 0-100 (bobot 50 NoData / 30 speckle / 20 radiometrik). |
| `quality_flag` | `character varying(20)` | NOT NULL | `'UNCHECKED'::character varying` |  | PASS \| WARNING \| FAIL \| UNCHECKED, dari quality_thresholds. |
| `notes` | `text` | NULL |  |  | Catatan bebas. |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris dibuat. |

**Constraint**

- `chk_quality_score_range` (CHECK): `CHECK (((quality_score >= (0)::numeric) AND (quality_score <= (100)::numeric)))`
- `quality_metrics_quality_flag_check` (CHECK): `CHECK (((quality_flag)::text = ANY (ARRAY[('PASS'::character varying)::text, ('WARNING'::character varying)::text, ('FAIL'::character varying)::text, ('UNCHECKED'::character varying)::text])))`
- `quality_metrics_product_id_fkey` (FK): `FOREIGN KEY (product_id) REFERENCES data_products(product_id) ON DELETE CASCADE`
- `quality_metrics_scene_id_fkey` (FK): `FOREIGN KEY (scene_id) REFERENCES satellite_scenes(scene_id) ON DELETE CASCADE`
- `quality_metrics_pkey` (PK): `PRIMARY KEY (metric_id)`
- `uq_quality_scene_product_band` (UNIQUE): `UNIQUE (scene_id, product_id, band_name)`

## quality_thresholds

Ambang kontrol kualitas per band (menggantikan processing_rules). Dibaca module6_analytics; bobot skor 50/30/20 tetap konstanta kode.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `threshold_id` | `smallint` | NOT NULL | `nextval('quality_thresholds_threshold_id_seq'::regclass)` | PK | PK surrogate. |
| `band_id` | `smallint` | NOT NULL |  | FK→spectral_bands, UNIQUE | FK -> spectral_bands. |
| `metric_name` | `character varying(40)` | NOT NULL |  | UNIQUE | Metrik yang diuji: quality_score \| nodata_percent \| valid_fraction \| speckle_index. |
| `warn_below` | `numeric` | NULL |  |  | Nilai di bawah ini -> WARNING. NULL = tidak diuji. |
| `fail_below` | `numeric` | NULL |  |  | Nilai di bawah ini -> FAIL. Contoh: quality_score 60. |
| `warn_above` | `numeric` | NULL |  |  | Nilai di atas ini -> WARNING. NULL = tidak diuji. |
| `fail_above` | `numeric` | NULL |  |  | Nilai di atas ini -> FAIL. NULL = tidak diuji. |
| `reference` | `character varying(150)` | NULL |  |  | Rujukan asal ambang. |
| `is_active` | `boolean` | NOT NULL | `true` |  | false = ambang tidak dipakai. |

**Constraint**

- `quality_thresholds_check` (CHECK): `CHECK (((fail_below IS NULL) OR (warn_below IS NULL) OR (fail_below <= warn_below)))`
- `quality_thresholds_check1` (CHECK): `CHECK (((fail_above IS NULL) OR (warn_above IS NULL) OR (fail_above >= warn_above)))`
- `quality_thresholds_metric_name_check` (CHECK): `CHECK (((metric_name)::text = ANY (ARRAY[('quality_score'::character varying)::text, ('nodata_percent'::character varying)::text, ('valid_fraction'::character varying)::text, ('speckle_index'::character varying)::text])))`
- `quality_thresholds_band_id_fkey` (FK): `FOREIGN KEY (band_id) REFERENCES spectral_bands(band_id)`
- `quality_thresholds_pkey` (PK): `PRIMARY KEY (threshold_id)`
- `quality_thresholds_band_id_metric_name_key` (UNIQUE): `UNIQUE (band_id, metric_name)`

## region_observations

Deret waktu dataset utama: nilai per kecamatan per band dari GPM/MODIS (harian) dan Sentinel-1 (per lintasan: VV, VH, WATER_PCT) (M7, M58). Tidak pernah dihapus retensi raster. Dasar grafik, statistik, alert, laporan.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `obs_id` | `bigint` | NOT NULL | `nextval('region_observations_obs_id_seq'::regclass)` | PK | PK surrogate. |
| `region_id` | `integer` | NOT NULL |  | FK→administrative_regions, UNIQUE | FK -> administrative_regions (kecamatan level 3). |
| `band_id` | `smallint` | NOT NULL |  | FK→spectral_bands, UNIQUE | FK -> spectral_bands, mis. RAIN_24H, NDVI, FLOOD, VH, WATER_PCT. |
| `obs_date` | `date` | NOT NULL |  | UNIQUE | Tanggal pengamatan = hari UTC (07.00-07.00 WIB, M28). |
| `value` | `numeric(10,4)` | NULL |  |  | Nilai agregat (satuan band: mm, indeks, %). NULL bila valid_fraction < 0,1. |
| `valid_fraction` | `numeric(5,4)` | NOT NULL |  |  | Bagian poligon yang punya piksel valid (0-1). |
| `source_product_id` | `bigint` | NULL |  | FK→data_products | FK -> data_products: COG asal nilai (lineage, RM2). |
| `run_type` | `character varying(5)` | NULL |  |  | Run IMERG untuk band GPM: F \| L \| E. Final menimpa Late (PIPELINE.md §3.3). |
| `job_id` | `bigint` | NULL |  | FK→dataset_jobs | FK -> dataset_jobs yang menghitung nilai. |
| `computed_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu nilai dihitung. |

**Constraint**

- `region_observations_run_type_check` (CHECK): `CHECK (((run_type)::text = ANY (ARRAY[('F'::character varying)::text, ('L'::character varying)::text, ('E'::character varying)::text])))`
- `region_observations_valid_fraction_check` (CHECK): `CHECK (((valid_fraction >= (0)::numeric) AND (valid_fraction <= (1)::numeric)))`
- `region_observations_band_id_fkey` (FK): `FOREIGN KEY (band_id) REFERENCES spectral_bands(band_id)`
- `region_observations_job_id_fkey` (FK): `FOREIGN KEY (job_id) REFERENCES dataset_jobs(job_id) ON DELETE SET NULL`
- `region_observations_region_id_fkey` (FK): `FOREIGN KEY (region_id) REFERENCES administrative_regions(region_id)`
- `region_observations_source_product_id_fkey` (FK): `FOREIGN KEY (source_product_id) REFERENCES data_products(product_id) ON DELETE SET NULL`
- `region_observations_pkey` (PK): `PRIMARY KEY (obs_id)`
- `uq_region_obs` (UNIQUE): `UNIQUE (region_id, band_id, obs_date)`

## regions_of_interest

AOI dataset (bbox) warisan DataLab. Baris baru hanya dari kecamatan atau gabungan kecamatan (M27); tepat satu baris adalah AOI GMLS (is_monitor_aoi).

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `region_id` | `integer` | NOT NULL | `nextval('regions_of_interest_region_id_seq'::regclass)` | PK | PK surrogate. Dirujuk datasets, satellite_scenes, nasa_scenes, fusion_products, live_areas. |
| `region_code` | `character varying(20)` | NOT NULL |  | UNIQUE | Alternate key, mis. GMLS_AOI atau ID3602xxx. |
| `name` | `character varying(100)` | NOT NULL |  |  | Nama tampilan ROI. |
| `description` | `text` | NULL |  |  | Keterangan bebas. |
| `bbox` | `geometry(Polygon,4326)` | NOT NULL |  |  | Kotak pembatas WGS84 (Polygon EPSG:4326) yang dipakai pencarian scene dan crop. |
| `centroid` | `geometry(Point,4326)` | NULL |  |  | Titik tengah bbox, diisi trg_roi_centroid. |
| `area_km2` | `numeric(12,4)` | NULL |  |  | Luas bbox (km2). |
| `admin_level` | `smallint` | NOT NULL | `3` |  | Tingkat administratif ROI (warisan): 2 kabupaten, 3 kecamatan. |
| `country_code` | `character(2)` | NOT NULL | `'ID'::bpchar` |  | Kode negara ISO 3166-1 alpha-2, selalu ID. |
| `is_active` | `boolean` | NOT NULL | `true` |  | false = ROI dinonaktifkan (warisan; penghapusan memakai deleted_at). |
| `source` | `character varying(20)` | NOT NULL | `'SYSTEM'::character varying` |  | Asal baris: SEEDER (seed) \| SYSTEM (dibuat sistem/ADMIN dari kecamatan). Wilayah buatan pengguna dihapus (M27). |
| `admin_region_id` | `integer` | NULL |  | FK→administrative_regions | FK -> administrative_regions bila ROI = satu kecamatan; NULL untuk gabungan. |
| `is_monitor_aoi` | `boolean` | NOT NULL | `false` |  | true = ROI AOI GMLS (bbox = ST_Envelope(ST_Union) kecamatan in_aoi). Paling banyak satu baris. |
| `deleted_at` | `timestamp with time zone` | NULL |  |  | Soft delete. NULL = aktif. Baris tidak dihapus fisik karena dirujuk FK. |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris dibuat. |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris terakhir diubah (trigger). |

**Constraint**

- `regions_of_interest_source_check` (CHECK): `CHECK (((source)::text = ANY (ARRAY[('SEEDER'::character varying)::text, ('SYSTEM'::character varying)::text])))`
- `regions_of_interest_admin_region_id_fkey` (FK): `FOREIGN KEY (admin_region_id) REFERENCES administrative_regions(region_id)`
- `regions_of_interest_pkey` (PK): `PRIMARY KEY (region_id)`
- `regions_of_interest_region_code_key` (UNIQUE): `UNIQUE (region_code)`

## report_types

Master jenis laporan periodik (M18): Hidromet untuk ANALYST, Kesehatan Data untuk DATA_ENGINEER.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `report_type_id` | `smallint` | NOT NULL | `nextval('report_types_report_type_id_seq'::regclass)` | PK | PK surrogate. |
| `report_code` | `character varying(30)` | NOT NULL |  | UNIQUE | Alternate key: HYDROMET_WEEKLY \| HYDROMET_MONTHLY \| DATAHEALTH_WEEKLY \| DATAHEALTH_MONTHLY. |
| `report_name` | `character varying(100)` | NOT NULL |  |  | Label UI. |
| `period` | `character varying(10)` | NOT NULL |  |  | WEEKLY \| MONTHLY. |
| `audience_role_id` | `smallint` | NOT NULL |  | FK→roles | FK -> roles: role audiens (dipakai RLS generated_reports). |
| `template_version` | `character varying(10)` | NOT NULL |  |  | Versi template PDF, mis. 1.0. |

**Constraint**

- `report_types_period_check` (CHECK): `CHECK (((period)::text = ANY (ARRAY[('WEEKLY'::character varying)::text, ('MONTHLY'::character varying)::text])))`
- `report_types_audience_role_id_fkey` (FK): `FOREIGN KEY (audience_role_id) REFERENCES roles(role_id)`
- `report_types_pkey` (PK): `PRIMARY KEY (report_type_id)`
- `report_types_report_code_key` (UNIQUE): `UNIQUE (report_code)`

## roles

Master role aplikasi (5 role, M13). Setiap role dipetakan ke satu role PostgreSQL yang dipakai lewat SET LOCAL ROLE.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `role_id` | `smallint` | NOT NULL | `nextval('roles_role_id_seq'::regclass)` | PK | PK surrogate. |
| `role_code` | `character varying(20)` | NOT NULL |  | UNIQUE | Alternate key. PUBLIC \| USER \| ANALYST \| DATA_ENGINEER \| ADMIN. |
| `role_name` | `character varying(50)` | NOT NULL |  |  | Label role untuk UI (Bahasa Indonesia), mis. "Relawan". |
| `db_role` | `character varying(40)` | NOT NULL |  | UNIQUE | Nama role PostgreSQL padanannya, mis. monitor_analyst (DATABASE.md §8.1). |
| `requires_login` | `boolean` | NOT NULL |  |  | false hanya untuk PUBLIC (pengunjung tanpa akun). |
| `description` | `text` | NULL |  |  | Uraian singkat kebutuhan akses role ini. |

**Constraint**

- `roles_pkey` (PK): `PRIMARY KEY (role_id)`
- `roles_db_role_key` (UNIQUE): `UNIQUE (db_role)`
- `roles_role_code_key` (UNIQUE): `UNIQUE (role_code)`

## satellite_scenes

Registri scene Sentinel-1 GRD yang ditemukan/diunduh. Soft delete ADMIN lewat is_valid (M24).

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `scene_id` | `integer` | NOT NULL | `nextval('satellite_scenes_scene_id_seq'::regclass)` | PK | PK surrogate. |
| `scene_uuid` | `uuid` | NOT NULL | `gen_random_uuid()` | UNIQUE | UUID stabil untuk referensi eksternal. |
| `product_identifier` | `character varying(200)` | NOT NULL |  | UNIQUE | Identifier produk ESA (unik global), mis. S1A_IW_GRDH_1SDV_..._B5C2. |
| `platform` | `character varying(20)` | NOT NULL | `'SENTINEL-1'::character varying` |  | Platform, default SENTINEL-1. |
| `instrument_mode` | `character varying(10)` | NOT NULL | `'IW'::character varying` |  | Mode akuisisi: IW (Interferometric Wide). |
| `polarization_vv` | `boolean` | NOT NULL | `true` |  | true bila produk memuat polarisasi VV. |
| `polarization_vh` | `boolean` | NOT NULL | `true` |  | true bila produk memuat polarisasi VH. |
| `acquisition_datetime` | `timestamp with time zone` | NOT NULL |  |  | Waktu akuisisi (UTC). Sumbu waktu utama. |
| `orbit_number` | `integer` | NULL |  |  | Nomor orbit absolut. |
| `orbit_direction` | `orbit_direction_enum` | NOT NULL | `'ASCENDING'::orbit_direction_enum` |  | ASCENDING \| DESCENDING. |
| `relative_orbit` | `smallint` | NULL |  |  | Nomor orbit relatif (track); dipakai menandai perubahan air antar orbit berbeda. |
| `bbox` | `geometry(Polygon,4326)` | NOT NULL |  |  | Footprint scene (Polygon EPSG:4326). Keterbatasan warisan: belum akurat (D17). |
| `cloud_cover_percent` | `numeric(5,2)` | NULL |  |  | Persen awan (tidak relevan untuk SAR; warisan). |
| `incidence_angle_near` | `numeric(6,3)` | NULL |  |  | Sudut datang near-range (derajat). |
| `incidence_angle_far` | `numeric(6,3)` | NULL |  |  | Sudut datang far-range (derajat). |
| `resolution_m` | `smallint` | NOT NULL | `10` |  | Resolusi piksel nominal (meter). |
| `region_id` | `integer` | NOT NULL |  | FK→regions_of_interest | FK -> regions_of_interest: ROI pencarian scene. |
| `raw_file_path` | `text` | NULL |  |  | Path berkas unduhan asli (bisa sudah dihapus setelah diproses). |
| `raw_file_size_mb` | `numeric(12,3)` | NULL |  |  | Ukuran berkas unduhan (MB). |
| `download_url` | `text` | NULL |  |  | URL unduhan CDSE. |
| `checksum_md5` | `character varying(32)` | NULL |  |  | Checksum MD5 dari penyedia. |
| `is_available` | `boolean` | NOT NULL | `true` |  | false = scene tidak tersedia lagi di penyedia/disk. |
| `is_valid` | `boolean` | NOT NULL | `true` |  | false = dinonaktifkan ADMIN (soft delete, M24). |
| `invalidated_by` | `integer` | NULL |  | FK→users | FK -> users: ADMIN yang menonaktifkan. |
| `invalidated_at` | `timestamp with time zone` | NULL |  |  | Waktu dinonaktifkan. |
| `invalid_reason` | `text` | NULL |  |  | Alasan wajib saat dinonaktifkan. |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris dibuat. |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris terakhir diubah (trigger). |

**Constraint**

- `chk_scene_invalidation` (CHECK): `CHECK ((is_valid OR ((invalidated_at IS NOT NULL) AND (invalid_reason IS NOT NULL))))`
- `satellite_scenes_cloud_cover_percent_check` (CHECK): `CHECK (((cloud_cover_percent >= (0)::numeric) AND (cloud_cover_percent <= (100)::numeric)))`
- `satellite_scenes_invalidated_by_fkey` (FK): `FOREIGN KEY (invalidated_by) REFERENCES users(user_id)`
- `satellite_scenes_region_id_fkey` (FK): `FOREIGN KEY (region_id) REFERENCES regions_of_interest(region_id) ON DELETE RESTRICT`
- `satellite_scenes_pkey` (PK): `PRIMARY KEY (scene_id)`
- `satellite_scenes_product_identifier_key` (UNIQUE): `UNIQUE (product_identifier)`
- `satellite_scenes_scene_uuid_key` (UNIQUE): `UNIQUE (scene_uuid)`

## satellite_sources

Master sumber data. Kolom VARCHAR "source" warisan DataLab dihubungkan ke source_code lewat FK.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `source_id` | `smallint` | NOT NULL | `nextval('satellite_sources_source_id_seq'::regclass)` | PK | PK surrogate. |
| `source_code` | `character varying(20)` | NOT NULL |  | UNIQUE | Alternate key: SENTINEL1 \| MODIS \| GPM \| FUSION. |
| `source_name` | `character varying(100)` | NOT NULL |  |  | Nama tampilan, mis. "Sentinel-1 SAR". |
| `provider` | `character varying(50)` | NULL |  |  | Penyedia data: ESA/CDSE, NASA LANCE/LAADS, NASA GES DISC. |
| `sensor_type` | `character varying(20)` | NULL |  |  | SAR \| OPTICAL \| PRECIPITATION \| DERIVED (FUSION). |
| `spatial_resolution_m` | `numeric(8,1)` | NULL |  |  | Resolusi spasial nominal (meter): 10 / 250 / 11000. |
| `nominal_revisit_days` | `numeric(4,1)` | NULL |  |  | Revisit nominal (hari). Angka nyata dihitung dari data (v_kelengkapan_data). |
| `products` | `text` | NULL |  |  | Produk yang diambil, mis. "GRD IW" atau "GPM_3IMERGDF, DL, DE". |

**Constraint**

- `satellite_sources_sensor_type_check` (CHECK): `CHECK (((sensor_type)::text = ANY (ARRAY[('SAR'::character varying)::text, ('OPTICAL'::character varying)::text, ('PRECIPITATION'::character varying)::text, ('DERIVED'::character varying)::text])))`
- `satellite_sources_pkey` (PK): `PRIMARY KEY (source_id)`
- `satellite_sources_source_code_key` (UNIQUE): `UNIQUE (source_code)`

## scene_job_state

Status per scene S1 di dalam satu dataset_job; dasar resume setelah proses mati.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `id` | `bigint` | NOT NULL | `nextval('scene_job_state_id_seq'::regclass)` | PK | PK surrogate. |
| `job_id` | `bigint` | NOT NULL |  | FK→dataset_jobs, UNIQUE | FK -> dataset_jobs. |
| `product_identifier` | `character varying(200)` | NOT NULL |  | UNIQUE | Identifier produk ESA scene ini. |
| `scene_id` | `integer` | NULL |  | FK→satellite_scenes | FK -> satellite_scenes; NULL sebelum scene terdaftar. |
| `current_stage` | `character varying(30)` | NULL |  |  | Tahap terakhir yang dicapai, mis. LEE_FILTER, CLEANUP. |
| `stage_status` | `character varying(20)` | NOT NULL | `'PENDING'::character varying` |  | PENDING \| RUNNING \| COMPLETED \| FAILED \| SKIPPED. |
| `produced_files` | `jsonb` | NOT NULL | `'{}'::jsonb` |  | Berkas yang dihasilkan per tier (JSONB {tier: [path]}), untuk cleanup. |
| `attempt_number` | `smallint` | NOT NULL | `1` |  | Percobaan ke berapa. |
| `max_retries` | `smallint` | NOT NULL | `3` |  | Batas percobaan ulang. |
| `last_error` | `text` | NULL |  |  | Pesan galat terakhir. |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris dibuat. |
| `started_at` | `timestamp with time zone` | NULL |  |  | Waktu mulai diproses. |
| `completed_at` | `timestamp with time zone` | NULL |  |  | Waktu selesai. |

**Constraint**

- `chk_scene_job_stage_status` (CHECK): `CHECK (((stage_status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('RUNNING'::character varying)::text, ('COMPLETED'::character varying)::text, ('FAILED'::character varying)::text, ('SKIPPED'::character varying)::text])))`
- `scene_job_state_job_id_fkey` (FK): `FOREIGN KEY (job_id) REFERENCES dataset_jobs(job_id) ON DELETE CASCADE`
- `scene_job_state_scene_id_fkey` (FK): `FOREIGN KEY (scene_id) REFERENCES satellite_scenes(scene_id) ON DELETE SET NULL`
- `scene_job_state_pkey` (PK): `PRIMARY KEY (id)`
- `uq_job_product` (UNIQUE): `UNIQUE (job_id, product_identifier)`

## spectral_bands

Master band/variabel yang diamati per sumber; dipakai region_observations, alert_rules, quality_thresholds, live_scene_metrics.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `band_id` | `smallint` | NOT NULL | `nextval('spectral_bands_band_id_seq'::regclass)` | PK | PK surrogate. |
| `source_id` | `smallint` | NOT NULL |  | FK→satellite_sources | FK -> satellite_sources. |
| `band_code` | `character varying(20)` | NOT NULL |  | UNIQUE | Alternate key, mis. VV, NDVI, RAIN_24H, WATER_CHANGE. |
| `band_name` | `character varying(100)` | NOT NULL |  |  | Label UI (Bahasa Indonesia). |
| `unit` | `character varying(20)` | NULL |  |  | Satuan nilai: dB, index, %, mm, km2. |
| `valid_min` | `numeric` | NULL |  |  | Batas bawah nilai sah; region_observations di luar rentang ditolak trg_obs_range. NULL = tanpa batas. |
| `valid_max` | `numeric` | NULL |  |  | Batas atas nilai sah. NULL = tanpa batas. |
| `aggregation` | `character varying(20)` | NOT NULL |  |  | Cara agregasi zonal: MEAN (hujan, NDVI, NDWI, backscatter) atau FRACTION (persen piksel kelas air). |

**Constraint**

- `spectral_bands_aggregation_check` (CHECK): `CHECK (((aggregation)::text = ANY (ARRAY[('MEAN'::character varying)::text, ('FRACTION'::character varying)::text])))`
- `spectral_bands_check` (CHECK): `CHECK (((valid_min IS NULL) OR (valid_max IS NULL) OR (valid_min <= valid_max)))`
- `spectral_bands_source_id_fkey` (FK): `FOREIGN KEY (source_id) REFERENCES satellite_sources(source_id)`
- `spectral_bands_pkey` (PK): `PRIMARY KEY (band_id)`
- `spectral_bands_band_code_key` (UNIQUE): `UNIQUE (band_code)`

## user_activity_logs

Log aplikasi append-only: login, logout, unduhan, ekspor, aksi penting (RM4).

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `log_id` | `bigint` | NOT NULL | `nextval('user_activity_logs_log_id_seq'::regclass)` | PK | PK surrogate. |
| `user_id` | `integer` | NULL |  | FK→users | FK -> users. NULL untuk login gagal dengan username tak dikenal atau PUBLIC. |
| `username_attempted` | `character varying(50)` | NULL |  |  | Username yang dicoba pada login gagal. |
| `action` | `character varying(30)` | NOT NULL |  |  | LOGIN_SUCCESS, LOGIN_FAILED, LOGOUT, DOWNLOAD_PRODUCT, DOWNLOAD_DATASET, DOWNLOAD_FUSION, DOWNLOAD_REPORT, EXPORT_CSV, CREATE_DATASET, TRIGGER_INGEST, ... |
| `target_type` | `character varying(40)` | NULL |  |  | Tabel objek aksi, mis. data_products, datasets, generated_reports. |
| `target_id` | `bigint` | NULL |  |  | PK objek aksi. |
| `bytes_sent` | `bigint` | NULL |  |  | Jumlah byte terkirim (unduhan). |
| `ip_address` | `inet` | NULL |  |  | Alamat IP klien. |
| `user_agent` | `character varying(255)` | NULL |  |  | User-Agent klien (dipotong 255). |
| `detail` | `jsonb` | NULL |  |  | Detail tambahan (JSONB), mis. {"auth": "token"}. |
| `logged_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu kejadian. |

**Constraint**

- `user_activity_logs_bytes_sent_check` (CHECK): `CHECK (((bytes_sent IS NULL) OR (bytes_sent >= 0)))`
- `user_activity_logs_user_id_fkey` (FK): `FOREIGN KEY (user_id) REFERENCES users(user_id)`
- `user_activity_logs_pkey` (PK): `PRIMARY KEY (log_id)`

## user_notify_regions

Langganan peringatan email per kecamatan (M64): tempat tinggal, beberapa, atau tidak sama sekali. Diubah pemiliknya lewat auth_set_own_notify().

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `user_id` | `integer` | NOT NULL |  | FK→users, PK | FK -> users pelanggan. |
| `region_id` | `integer` | NOT NULL |  | FK→administrative_regions, PK | FK -> administrative_regions (kecamatan AOI). |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu kecamatan dipilih. |

**Constraint**

- `user_notify_regions_region_id_fkey` (FK): `FOREIGN KEY (region_id) REFERENCES administrative_regions(region_id) ON DELETE CASCADE`
- `user_notify_regions_user_id_fkey` (FK): `FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE`
- `user_notify_regions_pkey` (PK): `PRIMARY KEY (user_id, region_id)`

## users

Akun pengguna yang login (USER s.d. ADMIN). Akun dinonaktifkan, tidak pernah dihapus.

| Kolom | Tipe | Null | Default | Kunci | Keterangan |
|---|---|---|---|---|---|
| `user_id` | `integer` | NOT NULL | `nextval('users_user_id_seq'::regclass)` | PK | PK surrogate. |
| `role_id` | `smallint` | NOT NULL |  | FK→roles | FK -> roles. Tidak boleh PUBLIC (ditegakkan trg_users_role_not_public). |
| `username` | `character varying(50)` | NOT NULL |  | UNIQUE | Alternate key, huruf kecil/angka/_/. 3-50 karakter. Contoh: relawan.bayah |
| `password_hash` | `character varying(255)` | NOT NULL |  |  | Hash bcrypt (cost 12). Tidak pernah dikirim ke klien; disensor di audit_log. |
| `full_name` | `character varying(100)` | NOT NULL |  |  | Nama lengkap untuk tampilan. |
| `organization` | `character varying(100)` | NULL |  |  | Asal organisasi, mis. GMLS, BPBD Lebak, kampus. |
| `is_active` | `boolean` | NOT NULL | `true` |  | false = akun dinonaktifkan ADMIN; login ditolak. |
| `failed_login_count` | `smallint` | NOT NULL | `0` |  | Jumlah gagal login beruntun; 5 kali -> locked_until diisi. |
| `locked_until` | `timestamp with time zone` | NULL |  |  | Akun terkunci sementara sampai waktu ini (15 menit setelah 5 kali gagal). |
| `last_login_at` | `timestamp with time zone` | NULL |  |  | Waktu login sukses terakhir. |
| `created_by` | `integer` | NULL |  | FK→users | FK -> users: ADMIN yang membuat akun ini. NULL untuk admin pertama (create_admin.py). |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu akun dibuat. |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  | Waktu baris terakhir diubah (trigger). |
| `email` | `character varying(254)` | NULL |  |  | Alamat email (unik, tanpa membedakan huruf besar). Opsional (M64; wajib saat registrasi pada M56). Hanya disimpan bila lolos pengecekan: format, MX domain, dan email konfirmasi terkirim. |
| `email_verified_at` | `timestamp with time zone` | NULL |  |  | Waktu email lolos pengecekan dan email konfirmasi terkirim (M64). NULL = email lama yang belum dicek; tidak dikirimi peringatan. |
| `notify_all_regions` | `boolean` | NOT NULL | `false` |  | true = berlangganan peringatan email untuk SEMUA kecamatan AOI, termasuk yang ditambahkan kemudian (M64). |

**Constraint**

- `users_email_check` (CHECK): `CHECK (((email IS NULL) OR ((email)::text ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'::text)))`
- `users_failed_login_count_check` (CHECK): `CHECK ((failed_login_count >= 0))`
- `users_username_check` (CHECK): `CHECK (((username)::text ~ '^[a-z0-9_.]{3,50}$'::text))`
- `users_created_by_fkey` (FK): `FOREIGN KEY (created_by) REFERENCES users(user_id)`
- `users_role_id_fkey` (FK): `FOREIGN KEY (role_id) REFERENCES roles(role_id)`
- `users_pkey` (PK): `PRIMARY KEY (user_id)`
- `users_username_key` (UNIQUE): `UNIQUE (username)`

## VIEW

| VIEW | Kolom | Keterangan |
|---|---|---|
| `v_alert_aktif` | `alert_id`, `observation_date`, `region_id`, `pcode`, `region_name`, `rule_id`, `rule_code`, `disaster_type_code`, `band_code`, `observed_value`, `threshold_value`, `severity`, `triggered_at` | Alert hujan yang belum ditandai dibaca, lengkap dengan nama kecamatan dan aturan. USER+. |
| `v_citra_metrics` | `live_scene_id`, `area_id`, `scene_date`, `source_code`, `band_code`, `band_name`, `unit`, `metric_name`, `value`, `source_date` | Metrik numerik per band x metrik untuk scene yang terlihat role pemanggil lewat v_citra_scenes (M56). PUBLIC+. |
| `v_citra_obs_aoi` | `obs_date`, `source_code`, `band_code`, `band_name`, `unit`, `mean_value`, `max_value`, `min_value`, `n_regions`, `valid_fraction`, `run_type` | Angka harian GPM/MODIS (Job Hidromet, termasuk backfill) dirata-rata ke kecamatan AOI, batas waktu per role pemanggil seperti v_citra_scenes; observasi terakhir selalu terlihat (M56). PUBLIC+. |
| `v_citra_scenes` | `live_scene_id`, `area_id`, `area_name`, `scene_date`, `status`, `area_status`, `interpretations`, `previews`, `source_status`, `files_available` | Scene citra (Sentinel-1 + MODIS/GPM pendamping) dengan batas waktu per role pemanggil: PUBLIC 30 hari, USER 365 hari, ANALYST/DATA_ENGINEER/ADMIN semua; scene terbaru tiap area selalu terlihat. files_available = PNG masih ada di disk (M56). PUBLIC+. |
| `v_evaluasi_alert` | `outcome`, `event_id`, `alert_id`, `region_id`, `ref_date` | Evaluasi alert WARNING+ terhadap kejadian terverifikasi dengan jendela 0-3 hari: HIT, MISS, FALSE_ALARM. ANALYST, ADMIN. |
| `v_hujan_harian_kecamatan` | `obs_date`, `region_id`, `pcode`, `region_name`, `rain_24h_mm`, `rain_72h_mm`, `rain_7d_mm`, `rain_30d_mm`, `gpm_run`, `bmkg_category` | Hujan 24h/72h/7d/30d (mm) per kecamatan per tanggal UTC + run GPM + kategori BMKG hujan 24 jam (RINGAN < 20, SEDANG < 50, LEBAT < 100, SANGAT_LEBAT < 150, EKSTREM). USER+. |
| `v_kejadian_dan_hujan` | `event_id`, `event_date`, `event_end_date`, `disaster_type_code`, `region_id`, `region_name`, `village_name`, `is_verified`, `info_source`, `rain_24h_h0`, `rain_72h_h0`, `rain_7d_h0`, `rain_24h_h1`, `rain_72h_h1`, `rain_7d_h1`, `rain_24h_h2`, `rain_72h_h2`, `rain_7d_h2` | Kejadian bencana aktif dengan hujan 24h/72h/7d (mm) pada H-0, H-1, H-2 di kecamatannya. ANALYST, ADMIN. |
| `v_kelengkapan_data` | `source_code`, `data_date`, `prev_date`, `gap_days`, `is_gap` | Tanggal yang punya data per sumber (S1 dari satellite_scenes, MODIS/GPM dari nasa_scenes) dengan jarak ke tanggal sebelumnya; is_gap = jarak > 10 hari. DATA_ENGINEER, ADMIN. |
| `v_live_scenes_recent` | `live_scene_id`, `area_id`, `area_name`, `scene_date`, `status`, `area_status`, `interpretations`, `previews`, `source_status` | Scene Live dalam 30 hari terakhir yang berkasnya masih ada. USER+. |
| `v_log_data` | `log_ref`, `logged_at`, `kind`, `action`, `target_type`, `target_id`, `user_id`, `username`, `detail` | Log yang menyangkut halaman Data: aktivitas unduhan/backfill/ubah scene dan jejak audit tabel katalog & scene (M56). DATA_ENGINEER, ADMIN. |
| `v_log_kejadian` | `log_ref`, `logged_at`, `kind`, `action`, `target_type`, `target_id`, `user_id`, `username`, `detail` | Log yang menyangkut halaman Kejadian: jejak audit disaster_events/disaster_types dan ekspor Excel kejadian (M56). ANALYST, ADMIN. |
| `v_log_login` | `log_id`, `logged_at`, `action`, `user_id`, `username`, `username_attempted`, `ip_address`, `user_agent`, `detail` | Log masuk, keluar, dan registrasi akun mandiri dari user_activity_logs. ADMIN. |
| `v_log_unduhan` | `log_id`, `logged_at`, `action`, `user_id`, `username`, `target_type`, `target_id`, `bytes_sent`, `ip_address`, `detail` | Log unduhan dan ekspor CSV dari user_activity_logs. ADMIN. |
| `v_public_kejadian` | `event_id`, `disaster_type_code`, `disaster_type_name`, `region_id`, `pcode`, `region_name`, `village_name`, `lat`, `lon`, `event_date`, `event_end_date`, `description`, `impact_summary`, `info_source`, `is_verified` | Kejadian bencana 365 hari terakhir untuk PUBLIC, tanpa source_reference/recorded_by/verified_by (M56). Role login membaca disaster_events langsung tanpa batas waktu. |
| `v_public_live_latest` | `area_id`, `area_name`, `live_scene_id`, `scene_date`, `status`, `area_status`, `interpretations`, `previews`, `source_status` | Scene Live terbaru per area aktif (READY/PARTIAL, berkas belum dihapus): status area, kalimat kondisi, manifest preview. PUBLIC+. |
| `v_public_lokasi_alert` | `region_id`, `observation_date`, `severity`, `band_code`, `observed_value`, `threshold_value` | Alert hujan 7 hari terakhir per kecamatan AOI untuk Pantau Lokasi, tanpa kolom penanganan alert (M63). PUBLIC+. |
| `v_public_lokasi_obs` | `region_id`, `pcode`, `region_name`, `obs_date`, `source_code`, `band_code`, `unit`, `value`, `valid_fraction`, `run_type` | Angka harian/per lintasan per kecamatan AOI untuk Pantau Lokasi di Beranda, batas waktu per role pemanggil seperti v_citra_obs_aoi; dua observasi terakhir per kecamatan × band selalu terlihat (M63). PUBLIC+. |
| `v_public_lokasi_range` | `region_id`, `band_code`, `p02`, `p98`, `n_obs` | Rentang biasa (persentil 2–98, 365 hari s.d. observasi terakhir band) per kecamatan AOI × band untuk grafik dan kalimat Pantau Lokasi (M63). PUBLIC+. |
| `v_ringkasan_kualitas` | `source_code`, `week_start`, `n_quality_metrics`, `avg_quality_score`, `n_fail`, `n_warning`, `n_quality_alerts`, `n_observations`, `avg_valid_fraction` | Per sumber per minggu (Senin): jumlah & rata-rata skor quality_metrics, FAIL/WARNING, quality_alerts, dan rata-rata valid_fraction region_observations. DATA_ENGINEER, ADMIN. |
| `v_statistik_hari_ini` | `obs_date`, `region_id`, `pcode`, `region_name`, `rain_24h_mm`, `rain_72h_mm`, `rain_7d_mm`, `rain_30d_mm`, `gpm_run`, `bmkg_category`, `ndvi`, `ndvi_date`, `ndwi`, `ndwi_date`, `modis_flood_pct`, `modis_date` | Baris v_hujan_harian_kecamatan untuk tanggal terakhir yang lengkap (semua kecamatan in_aoi punya RAIN_24H) + NDVI/NDWI/FLOOD MODIS terakhir yang tersedia. USER+. |
| `v_unduhan_per_role` | `log_date_wib`, `action`, `role_code`, `n_downloads`, `bytes_sent` | Jumlah dan volume unduhan/ekspor per tanggal WIB, jenis aksi, dan role pengunduh; tanpa nama pengguna. DATA_ENGINEER, ADMIN, ETL (laporan). |
| `v_users_safe` | `user_id`, `role_id`, `role_code`, `username`, `full_name`, `organization`, `is_active`, `last_login_at`, `created_by`, `created_at`, `updated_at` | users tanpa password_hash, failed_login_count, locked_until. ADMIN (UI) dan semua role untuk join nama. |
