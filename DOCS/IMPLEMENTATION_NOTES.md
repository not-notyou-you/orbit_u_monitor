# IMPLEMENTATION NOTES — Orbit-U: The Monitor

Catatan pelaksanaan per tahap: di mana kode DataLab bertentangan dengan, atau
melampaui, keempat dokumen rancangan, dan keputusan yang diambil. Dokumen
rancangan tetap sumber kebenaran; catatan ini menjelaskan penyimpangan dan
detail yang tidak diatur di sana.

---

## Tahap 1 — Fondasi

Semua keputusan di bawah disetujui pemilik proyek sebelum dikerjakan
(rekomendasi K1–K12 diterima apa adanya).

| # | Temuan | Keputusan |
|---|---|---|
| K1 | `etl/tier_names.tiers_at_rank()` / `equivalent_tiers()` menyisipkan nama legacy (`GOLD`, `SILVER`, …) ke klausa SQL `IN (...)` pada kolom enum `product_tier`. Setelah nilai legacy tidak dibawa ke `product_tier_enum` (DATABASE.md §6, M34), kueri itu akan gagal *invalid input value for enum*. | Helper SQL hanya mengembalikan nama D14. `canonical_tier()` tetap menerima nama legacy sebagai **input** (dipetakan ke nama baru). Anggota legacy `ProductTierEnum` dihapus. Default `datasets.required_tiers` = `{COG}`. |
| K2 | M30 lebih dalam dari yang tertulis: `processing_jobs.scene_id` NOT NULL dengan UNIQUE `(scene_id, stage_id, attempt_number)`, dan setiap job MODIS/GPM/FUSION menempel pada placeholder `NASA_AUX_*`. `fusion_products.s1_scene_id` juga diisi placeholder pada hari tanpa S1. | `processing_jobs.scene_id` nullable, `+ nasa_scene_id` FK → `nasa_scenes`, CHECK paling banyak satu terisi. Job FUSION keduanya NULL. `fusion_products.s1_scene_id` NULL pada hari tanpa S1. |
| K3 | Produk FUSION berbaris NULL-NULL: kunci dedup `is_latest` `(COALESCE(scene_id,0), COALESCE(nasa_scene_id,0), band, tier, dataset)` (PIPELINE §5.1) membuat stack setiap tanggal menandai stack tanggal lain usang. | Untuk FUSION dedup memakai `file_path` (mekanisme `supersede_same_path` warisan; nama berkas fusion memuat tanggal + strategi + level). Produk satu sumber memakai kunci §5.1. |
| K4 | `database_client.register_product()` (PIPELINE §5.1) tidak ada. Registrasi produk ada di `MetadataManager.insert_data_product()`, dipanggil module9 (`_register_aux_products`, `_promote_aux_to_gold`, fusion), bukan module7/8. | `insert_data_product()` menerima `scene_id` **atau** `nasa_scene_id`; module9 mengirim `nasa_scene_id` granule asal. module7 hanya diubah agar granule komposit (periode MOD09A1 terakhir) tersedia. |
| K5 | `module5_orchestrator` mengimpor `refusion.scene_results_for_date` untuk merekonsiliasi frame S1 dari run sebelumnya — jalur aktif, bukan alat perawatan. | `scene_results_for_date` + helpernya dipindah ke `module5_orchestrator`; sisa `refusion.py` (CLI `refuse_date`) dihapus. Tesnya ikut dipindah. |
| K6 | `live_scenes.metrics` memuat juga field non-numerik yang dibaca `live_interpret` (`imerg_runs`, `composite_period`, `observation_date`, `window_*`) dan lebih banyak nama metrik dari contoh DATABASE §4.2.7. | Angka → `live_scene_metrics` dengan pemetaan band × metrik tetap (`etl/live_metrics.py`). Deskriptor teks → `live_scenes.source_status[src].meta` (JSONB tampilan, tidak dikueri). Helper pemuat menyusun ulang dict lama sehingga kalimat, forecast, kartu, dan `app.js` tidak berubah. |
| K7 | `alert_rules.threshold_value` NOT NULL, tetapi `LANDSLIDE_RAIN72` belum punya nilai ("diisi dari literatur"). | `threshold_value` nullable + `CHECK (NOT is_active OR threshold_value IS NOT NULL)`; seed NULL, nonaktif. |
| K8 | DATABASE §4.1 menulis `processing_jobs + parameters JSONB`, padahal kolom `parameters_json` sudah ada. | Kolom `parameters_json` dipertahankan (isi dan maksudnya sama). |
| K9 | Nama di dokumen tidak sama dengan kode: `dataset_jobs.kind` sebenarnya `job_type`; `datasets.is_system` hanya disebut PIPELINE §3.1; seed `users` "1 admin awal" padahal admin pertama dibuat `create_admin.py`; `administrative_regions` diisi `load_regions.py`. | `job_type` + nilai `HYDROMET_DAILY`; `datasets.is_system` ditambahkan. Seed tidak memuat baris `users` (tidak ada hash sandi di SQL), `administrative_regions`, atau `regions_of_interest` — diisi skrip setup tahap berikutnya. |
| K10 | `docs/generated/` (DATABASE §6) vs folder `DOCS/` yang sudah ada — di Windows keduanya folder yang sama. | Keluaran kamus data ditulis ke `DOCS/generated/`. |
| K11 | Tes membangun DB uji dengan ORM `create_all`, bukan dari berkas SQL, sehingga skema final tidak pernah teruji. | `tests/conftest.py` membangun DB uji dari ketiga berkas SQL dan membongkarnya dengan `DROP SCHEMA public CASCADE`. ORM menjadi pemetaan saja. |
| K12 | Langkah 6 (nama DB) sudah dikerjakan di commit `7416ac5`. | Diverifikasi; kemudian diganti menjadi `themonitor` sesuai keputusan K18. |

### Detail tambahan (tidak diatur dokumen)

- `config/config_locations.json` (lokasi Jabodetabek DataLab, sudah dipindah ke DB sejak migrasi 012) dihapus bersama `config/config.json`.
- `_refusion_run_46.py` di root dihapus bersama `refusion.py`. Berkas riset lain di root (`_export_s1a_only/`, `_copy_wajo_s1a_by_year.py`, `_s1_coverage_*`, `report/`) tidak disentuh.
- `database/run_migration.py` diganti `database/apply_schema.py` yang menerapkan ketiga berkas skema memakai kredensial `.env`.

### Temuan saat pengerjaan (setelah rencana disetujui)

| # | Temuan | Penanganan Tahap 1 | Perlu keputusan? |
|---|---|---|---|
| K13 | API/UI Live Area masih membatasi retensi 1–12, sementara DB kini 1–60 (M11). | **Diputuskan: sampai 60.** API, UI, dan `MAX_RETENTION` = 60; lookback 730 hari; prakiraan maks. 4 langkah (M43). | Selesai. |
| K14 | Penghapusan dataset dulu membersihkan produk MODIS/GPM/FUSION lewat cascade scene placeholder. | `DeletionManager` kini menghapus langsung produk non-S1 milik dataset + job FUSION tanpa jangkar; produk S1 diperlakukan seperti dulu (tetap yatim di scene bersama). | Tidak, kecuali produk S1 juga ingin dihapus. |
| K15 | Ambang QA per dataset (`quality_settings.min_quality_score`) vs `quality_thresholds`. | **Diputuskan: dihapus.** Satu-satunya sumber `quality_thresholds`; kolom wizard dihapus; klien lama yang masih mengirimnya diabaikan, tidak error (M40). | Selesai. |
| K16 | Dokumen tidak memberi `valid_min/valid_max` `spectral_bands`. | **Diputuskan: batas fisik** (M42): hujan 24h/72h/7d/30d ≤ 2000/4000/6000/10000 mm (rekor dunia WMO dibulatkan ke atas), VV/VH −60..30 dB, NDVI/NDWI −1..1, persen 0..100. | Selesai. |
| K17 | Constraint tambahan di luar dokumen: FK `nasa_scenes.source` → `satellite_sources`, CHECK `api_tokens` ≤ 180 hari, CHECK domain `quality_flag`, `sensor_type`, `preview_options`, CHECK alasan wajib saat `is_valid = false`. | Ditambahkan karena aturan yang sama sudah tertulis di teks dokumen/kode. | Tidak. |
| K18 | Nama database. | **Diputuskan: `themonitor`** (uji: `themonitor_test`) di kode, `.env.example`, dan dokumen (M44). | Selesai. |

Catatan: satu run tes penuh sempat crash native GDAL (`0xc0000374` di `rasterio.warp.reproject` saat fusion, multi-thread); run ulang lulus 714/714. Intermiten, tidak terkait perubahan Tahap 1.

---

## Tahap 2 — Keamanan & API

Rencana disetujui pemilik proyek sebelum dikerjakan (rekomendasi S1–S7
diterima apa adanya).

### Keputusan rencana (disetujui)

| # | Temuan | Keputusan |
|---|---|---|
| S1 | INTERFACE §4.7 "hapus dataset oleh pembuat" bertentangan dengan §8.3: `data_engineer` tidak punya D pada `datasets`, dan `DeletionManager` juga menghapus baris `data_products`/`processing_jobs`. | API memeriksa pembuat/ADMIN dan menandai `DELETING` di bawah role pengguna. Penghapusan fisik dikerjakan thread pipeline dengan koneksi `monitor_etl` setelah commit. `monitor_etl` mendapat **D** hanya pada `datasets`, `data_products`, `processing_jobs` (tabel anak lain ikut lewat `ON DELETE CASCADE`, yang dijalankan dengan hak pemilik tabel). Hal yang sama berlaku untuk hapus Live Area dan pembersihan tier saat cancel. |
| S2 | `auth_get_user` saja tidak cukup karena role publik/USER tidak bisa menyentuh `users`/`api_tokens`. | Fungsi SECURITY DEFINER milik `monitor_admin`: `auth_get_user`, `auth_record_login`, `auth_session_user`, `auth_get_token` (EXECUTE: `monitor_public` dan turunannya). |
| S3 | `:'app_pw'` (variabel psql) tidak bisa dijalankan `apply_files()` (psycopg2). | Role LOGIN dibuat tanpa sandi; `apply_schema.py` dan `tests/conftest.py` menjalankan `ALTER ROLE … PASSWORD` dari `MONITOR_APP_PASSWORD` / `MONITOR_ETL_PASSWORD`. Bagian role ditulis idempoten (role berlaku untuk seluruh cluster). |
| S4 | Tabel/VIEW yang tidak disebut §8.3. | Master referensi (`satellite_sources`, `spectral_bands`, `administrative_regions`, `regions_of_interest`, `processing_stages`, `fusion_strategies`, `report_types`): S untuk user+ dan etl; ADMIN SIU pada `administrative_regions`/`regions_of_interest`. `quality_alerts` dan `cleanup_operations` mengikuti kelompok `processing_*`. `dataset_source_config` mengikuti `dataset_*`. `v_users_safe`: S untuk user+. `v_log_*`: ADMIN. Matriks lengkap ada di `tests/security/grant_matrix.sql`. |
| S5 | `/live` (warisan) diatur §4.3, bukan §4.7; `/storage/*` tidak diatur dokumen. | `/live`: baca USER (non-ADMIN hanya scene ≤ 30 hari + scene terbaru), tulis dan log ADMIN. `/storage/*` (disk seluruh mesin): ADMIN. `/public/*` belum dibangun (landing hanya memakai `/api/health`). |
| S6 | "Setiap pemakaian token tercatat". | Satu baris per request bertoken: `action = 'API_REQUEST'`, `detail = {auth: 'token', token_id, method, path, status}`. Untuk unduhan cukup baris `DOWNLOAD_*` (dengan `detail.auth = 'token'`), tanpa baris kedua. |
| S7 | Seed berjalan setelah security sehingga INSERT seed masuk `audit_log`. | Dibiarkan (`app_user_id` NULL, `db_user` = pemilik skema). |

### Temuan saat pengerjaan

| # | Temuan | Penanganan | Perlu keputusan? |
|---|---|---|---|
| T1 | Policy `rp_audience` (§8.4) men-JOIN `roles`, padahal ANALYST/DATA_ENGINEER tidak punya SELECT pada `roles` (§8.3), sehingga ekspresi policy gagal *permission denied*. | Subkueri diganti fungsi SECURITY DEFINER `report_audience_db_role(report_type_id)` milik `monitor_admin`. Matriks GRANT tetap utuh. | Tidak. |
| T2 | "Ubah kata sandi" (§4.1) untuk USER, padahal USER tidak punya UPDATE pada `users`. | Fungsi SECURITY DEFINER `auth_change_own_password(hash)` hanya mengubah baris milik `app.user_id` sesi (bukan argumen), dan menolak nilai yang bukan hash bcrypt. | Tidak. |
| T3 | RLS `generated_reports` dengan policy FOR SELECT saja menolak INSERT/UPDATE untuk semua role selain pemilik, padahal §8.3 memberi SIU ke ADMIN dan etl. | Tambahan policy `rp_writers` FOR ALL untuk `monitor_admin` dan `monitor_etl`. | Tidak. |
| T4 | Audit trigger pada `users`, `api_tokens`, `datasets`, `live_areas` akan mencatat setiap login (`last_login_at`), setiap request bertoken (`last_used_at`), setiap progres scene, dan setiap siklus Live. | `audit_row()` menerima daftar kolom "pembukuan" (TG_ARGV[1..]) yang tidak dicatat bila **hanya** kolom itu yang berubah: `last_login_at`, `failed_login_count` (users); `last_used_at` (token); penghitung progres (datasets); status/forecast siklus (live_areas). Perubahan `locked_until` (kunci/buka kunci) tetap tercatat. `changed_columns` dihitung sebelum sensor, jadi perubahan `password_hash` terlihat sebagai nama kolom tanpa nilai; `updated_at` tidak dicantumkan. `geom` juga disensor (poligon besar). `administrative_regions` hanya dicatat untuk UPDATE `in_aoi`, scene hanya untuk UPDATE `is_valid` (§8.5). | Tidak. |
| T5 | `audit_log.db_user DEFAULT current_user` akan selalu berisi pemilik fungsi karena `audit_row` adalah SECURITY DEFINER. | `db_user` diisi dari GUC `role` (hasil `SET ROLE`), atau `session_user` bila tidak ada SET ROLE (psql langsung). | Tidak. |
| T6 | Skema `public` yang dibuat ulang (`CREATE SCHEMA`, dipakai conftest) tidak memberi USAGE ke PUBLIC. | `GRANT USAGE ON SCHEMA public` eksplisit ke `monitor_public` dan `monitor_etl`. `monitor_app` sengaja tidak diberi: tanpa SET ROLE, tabel pun tidak terlihat. | Tidak. |
| T7 | Manager warisan membuka `db.session()` berkali-kali dan menyalakan thread job/penghapusan/siklus dari dalam request. Dengan satu transaksi per request, thread (koneksi lain) bisa membaca dataset yang belum di-commit, dan sesi request sudah tertutup saat thread berjalan. | `RequestDatabaseClient` (api/deps.py) menjadikan setiap `session()` SAVEPOINT di dalam transaksi request. `DatasetManager`/`LiveMonitor` mendapat `runner_db` (monitor_etl) dan menunda start thread lewat `call_after_commit`. Di luar API (CLI, scheduler, tes ETL) perilakunya tidak berubah. | Tidak. |
| T8 | Mengubah retensi Live Area dulu langsung menghapus berkas sebelum respons dikirim. | Baris area diubah di sesi ADMIN; penghapusan kelebihan scene, prakiraan, dan siklus berjalan lewat ETL setelah commit. Respons PATCH dikirim sebelum berkas selesai dihapus. | Tidak. |
| T9 | `/scenes?source=S1\|MODIS\|GPM` + `include_invalid` (§4.7, K12) belum ada di kode warisan. | **Diputuskan: dibuat di Tahap 2.** `source` memilih tabel (`satellite_scenes` atau `nasa_scenes`; default `S1` agar klien lama tidak berubah). Item MODIS/GPM memakai bentuk `NasaSceneListItem` (`nasa_scene_id`, `tile_id`, `product_short_name`, `acquisition_date`, `run_type`). Scene `is_valid = false` disembunyikan kecuali `include_invalid=true`, yang hanya untuk ADMIN (lainnya 403 `ROLE_FORBIDDEN`). `orbit_direction`/`only_gold` hanya berlaku untuk S1. | Selesai. |
| T10 | Exit dependency FastAPI 0.115 berjalan **sebelum** body respons dikirim. | Log unduhan ditulis `ActivityLogMiddleware` setelah body selesai, dalam transaksi pendek terpisah dengan role pemilik request; `bytes_sent` = byte yang benar-benar terkirim, `detail.complete` menandai unduhan yang terputus. | Tidak. |
| T11 | Kolom `ip_address` bertipe INET; host non-IP (mis. TestClient) membuat INSERT gagal. | Nilai yang bukan IP disimpan NULL. | Tidak. |
| T12 | `GET /api/storage/summary` selalu 500 (`KeyError: 'bronze'`): respons masih memakai literal tier lama, sedangkan `folder_manager.TIERS` sudah bernama D14. Baru terungkap karena tes RBAC memanggil setiap endpoint. | Respons dan `StorageTier` disusun dari nama tier D14. | Tidak. |

### Detail tambahan (tidak diatur dokumen)

- `api_client` di tes kini login sebagai ADMIN (JWT langsung), sehingga tes API Tahap 1 sekaligus berjalan di bawah `SET LOCAL ROLE monitor_admin` dengan koneksi `monitor_app`.
- `.env` membutuhkan `MONITOR_APP_PASSWORD`, `MONITOR_ETL_PASSWORD`, `JWT_SECRET` (≥ 32 karakter; aplikasi menolak start tanpanya), dan opsional `COOKIE_SECURE=false` hanya untuk pengembangan lewat http non-localhost.
- CORS `*` dihapus (satu origin, INTERFACE §1).
- `GET /api/admin/tokens` ditambahkan untuk tab Token API (§2.8); pencabutan memakai `DELETE /api/auth/tokens/{id}` yang memang mengizinkan ADMIN.
- Kode error spesifik: `NOT_AUTHENTICATED`, `SESSION_EXPIRED`, `ACCOUNT_INACTIVE`, `INVALID_CREDENTIALS`, `ACCOUNT_LOCKED`, `ROLE_FORBIDDEN`, `DB_PERMISSION_DENIED`, `CSRF_HEADER_REQUIRED`, `TOKEN_INVALID`, `TOKEN_REVOKED`, `TOKEN_EXPIRED`, `TOKEN_WRITE_FORBIDDEN`, `TOKEN_SCOPE_FORBIDDEN`, `RATE_LIMITED`, `NOT_DATASET_OWNER`, `SCENE_OUT_OF_RANGE`, `PASSWORD_POLICY`, `INVALID_OLD_PASSWORD`, `USERNAME_TAKEN`, `CANNOT_MODIFY_SELF`, `TOKEN_ALREADY_REVOKED`, `INVALID_DATE_RANGE`; selebihnya kode bawaan per status (`NOT_FOUND`, `BAD_REQUEST`, `VALIDATION_ERROR`, …).
- UI: `/masuk` + guard sesi di `/app` (alih ke `/masuk` saat 401), tombol Keluar, dan tab disembunyikan sesuai `permissions` dari `/api/auth/me`. Halaman lain belum diterjemahkan atau diubah.

---

## Tahap 3 — Monitoring & Laporan

Rencana disetujui pemilik proyek (semua rekomendasi diterima). Data nyata
yang dipakai: batas COD-AB IDN 2020 (BPS/OCHA) adm2 + adm3, dipindah dari
`data/humdata/` ke `data/external/cod-ab-idn/` (bersama PDF metadatanya dari
`data/from_glms/`). `data/from_glms/` tidak memuat catatan kejadian GMLS
(hanya contoh gempa global dan data demografi desa), jadi `import_disasters.py`
diuji dengan CSV sintetis.

### Keputusan rencana (disetujui)

| # | Temuan | Keputusan |
|---|---|---|
| T3-1 | `job_status_enum` dan `dataset_jobs.status` belum punya `WAITING_UPSTREAM` / `SKIPPED_LOCKED` (PIPELINE §7–8). | Ditambahkan ke skema. Status per tanggal hidromet ada di `dataset_jobs` (`HYDROMET_DAILY`, `date_range_start = date_range_end` = hari UTC); run scheduler yang dilewati dicatat sebagai `processing_jobs` tahap `ORCHESTRATE` berstatus `SKIPPED_LOCKED` (`parameters_json.scheduler_job`, `.lock`). |
| T3-2 | `live_interpret.THRESHOLDS` hujan 24 jam 20/50 mm, sedangkan aturan alert BMKG 50/100/150. | `warn`/`high` = dua ambang aturan `RAIN_24H` aktif terendah (default 50/100), disinkronkan dari `alert_rules` setiap kali kalimat dibuat (`sync_bmkg_thresholds`). 72 jam dan 7 hari tidak punya padanan BMKG → tetap. |
| T3-3 | Angka operasional yang PIPELINE sebut sebagai default tetapi belum ada di `app_settings`. | Kunci baru: `live.retention_default` (6), `live.default_area_name` ("Lebak Selatan"), `hydromet.min_valid_fraction` (0,1), `hydromet.waiting_max_days` (3), `report.wait_hydromet_minutes` (60). `etl/settings.py` membaca dengan default yang sama dengan seed. |

### Temuan saat pengerjaan

| # | Temuan | Penanganan | Perlu keputusan? |
|---|---|---|---|
| T3-4 | Daftar kecamatan AOI GMLS tidak ada di dokumen maupun data; gmls.org hanya menyebut Panggarangan (sekretariat) dan kegiatan di Bayah. | **Diputuskan (pemilik proyek: "cek internet"):** 10 kecamatan wilayah Lebak Selatan sebagaimana dirujuk usulan pemekaran Kabupaten Lebak Selatan: Banjarsari, Wanasalam, Cijaku, Malingping, Cihara, Cigemblong, Panggarangan, Bayah, Cibeber, Cilograng (faktabanten.co.id). Sumber lain lebih sempit: 6 kecamatan pesisir rawan megathrust menurut dokumen GMLS 2022 (Cihara, Malingping, Wanasalam, Panggarangan, Bayah, Cilograng); daftar PMI 2016 memasukkan Gunung Kencana tanpa Banjarsari/Cigemblong. AOI bisa diubah ADMIN kapan saja (PATCH /admin/regions, impor Excel `kecamatan`). Estimasi volume DATABASE §4.3 (9 kecamatan) naik ±11%. | Selesai. |
| T3-5 | INTERFACE §4.4 `GET /regions` = kecamatan + GeoJSON, tetapi `/api/regions` sudah dipakai wizard dataset dan Live Area sebagai daftar ROI. | **Diputuskan: sesuai dokumen.** `GET /api/regions` = FeatureCollection kecamatan AOI (`?all=true` 28 kecamatan, `ST_SimplifyPreserveTopology`); daftar ROI pindah ke `GET /api/rois` dan satu pemanggil di `web/app.js` diganti. Tampilan peta/halaman baru = Tahap 4. | Selesai. |
| T3-6 | Laporan dibuat scheduler (`monitor_etl`), tetapi etl tidak punya SELECT pada `disaster_events`, `v_kejadian_dan_hujan`, `v_evaluasi_alert`, `v_ringkasan_kualitas`, `v_kelengkapan_data`, dan tidak ada sumber "unduhan per role tanpa nama". | GRANT SELECT ke `monitor_etl` pada kelima objek; VIEW baru `v_unduhan_per_role` (agregat per tanggal WIB × aksi × role, tanpa identitas) untuk DATA_ENGINEER, ADMIN, etl. `grant_matrix.sql` diperbarui. | Ya: perluasan GRANT etl (hanya baca). |
| T3-7 | Jendela `rain_30d` (§3.2) bila ditambahkan ke `SourcePlan` akan membuat setiap dataset Katalog/Live mengunduh 30 granule per tanggal, bukan 7. | `WINDOWS["30d"]` ada di module8, tetapi hanya diminta job hidromet (`windows=HYDROMET_WINDOWS`); dataset lain tetap 24h/72h/7d. | Tidak. |
| T3-8 | `ensure_gpm_inputs_for_date` menelan semua exception, sehingga "granule belum terbit" tidak bisa dibedakan dari kegagalan. | `GranuleNotPublished` (module8) + argumen `raise_errors` → `WAITING_UPSTREAM`. Lewat `waiting_max_days` hari → `FAILED`. Job harian mencoba ulang tanggal WAITING sebelum "kemarin". | Tidak. |
| T3-9 | Pembaruan Late → Final: module8 memakai ulang COG yang sudah ada ("output sudah ada, skip"). | `rebuild_non_final=True` membangun ulang berkas yang tag `IMERG_RUNS`-nya bukan F; sebelum itu `final_published()` memeriksa listing GES DISC (di-cache) supaya Late tidak diunduh ulang sia-sia. Jendela pemeriksaan = 153 hari ("4–5 bulan"). | Tidak. |
| T3-10 | `recover_interrupted_jobs` (startup API) akan menjalankan ulang `dataset_jobs` dataset sistem sebagai job Katalog. | Dataset `is_system` dikecualikan; tanggal hidromet yang terputus diulang job harian/backfill (resume-aware). | Tidak. |
| T3-11 | `FRACTION` FLOOD: live_metrics menghitung kelas 3 sebagai banjir, PIPELINE §3.3 menyebut kelas 2/3. | Hidromet mengikuti §3.3 (kelas 2 = air berulang, 3 = banjir); kalimat Live tidak diubah. | Tidak. |
| T3-12 | Kategori kalimat perubahan air tidak diatur dokumen. | Pertambahan bersih (baru − surut) sebagai poin persen luas teramati, dengan ambang yang sama dengan kalimat VH (2 / 5 poin). Metrik tambahan `valid_km2` (penyebutnya) disimpan bersama `new_km2`, `receded_km2`, `persistent_km2`, `same_orbit`. | Tidak. |
| T3-13 | Orbit relatif S1C/S1D. | **Dihitung.** Sumber utama `satellite_scenes.relative_orbit` (atribut `relativeOrbit` katalog CDSE). Cadangan rumus `(abs − offset) mod 175 + 1`: S1A 73, S1B 27, S1C 172 (forum STEP ESA), S1D 42 (forum STEP ESA, menunggu product specification). Sejak 24-06-2026 ESA mengubah pemetaan absolut → relatif S1C (rekonfigurasi konstelasi; N. Miranda, Sentinel-1 Mission Manager) tanpa konstanta baru, jadi akuisisi S1C setelah tanggal itu hanya memakai metadata (tanpa metadata → tidak dibandingkan, bukan ditebak). | Selesai. |
| T3-14 | `generated_reports.file_path` / `checksum_sha256` NOT NULL, padahal laporan FAILED tidak punya berkas. | Baris FAILED: path tujuan, ukuran 0, checksum SHA-256 berkas kosong, `error_message` berisi penyebab. | Tidak. |
| T3-15 | Regenerasi: "berkas lama dipertahankan" bertabrakan dengan nama `{code}_{period_start}.pdf` yang tetap. | Regenerasi menulis `…_v2.pdf`, `…_v3.pdf`; baris lama SUPERSEDED dalam transaksi yang sama dengan INSERT baris READY (indeks unik READY tetap terjaga). | Tidak. |
| T3-16 | `/reports` untuk "ANALYST / DATA_ENGINEER", dua role yang tidak bertingkat. | Router `USER` + pemeriksaan audiens (`403 REPORT_AUDIENCE`); RLS menyaring baris, laporan audiens lain → 404. | Tidak. |
| T3-17 | Batas "USER maks. 30 hari" pada `/hydromet/observations` bisa berarti rentang atau usia data. | Ditafsirkan sama dengan Live: USER hanya data ≥ hari ini − 30 (403 `DATE_OUT_OF_RANGE`); `trend` USER ≤ 30 hari. | Tidak. |
| T3-18 | `/public/live/{area_id}/preview/{key}.png` tidak memuat tanggal, tetapi "tanggal lain → 403". | Opsional `?date=`; selain tanggal scene terbaru → 403 `SCENE_NOT_PUBLIC`. Path berkas dicari dengan koneksi etl setelah `v_public_live_latest` (role PUBLIC) memastikan scene terbaru. | Tidak. |
| T3-19 | Ekspor CSV hidromet: skema `v_log_unduhan` sudah memakai aksi `EXPORT_CSV`. | Dicatat sebagai `EXPORT_CSV` (bukan `DOWNLOAD_*`). | Tidak. |
| T3-20 | Pembaca shapefile: venv tidak punya GDAL/OGR (wheel rasterio tanpa driver vektor), geopandas, fiona. | `pyshp==2.3.1` (pure-Python) ditambahkan ke requirements; geometri dirapikan PostGIS (`ST_MakeValid`, `ST_CollectionExtract`, `ST_Multi`). | Tidak. |

| T3-21 | Data kejadian dan data lain baru akan didapat setelah aplikasi selesai (pemilik proyek). | **Ekspor/impor Excel generik** (`etl/excel_io.py`, `/api/excel`): 19 jenis data bisa diekspor (.xlsx: sheet Data + Petunjuk, filter tanggal, role sama dengan endpoint baca, dicatat `DOWNLOAD_XLSX`); 5 bisa diimpor dengan templat: kejadian bencana (ANALYST), jenis bencana, aturan alert, status AOI kecamatan, `app_settings` (ADMIN). Impor semua-atau-tidak (SAVEPOINT), `?dry_run=true`, error per nomor baris (422). Berkas dikirim sebagai body mentah, tanpa dependensi multipart. Ekspor kejadian = format impor (bisa diedit lalu diimpor ulang; duplikat dilewati). | Tidak. |
| T3-22 | Endpoint ADMIN INTERFACE §4.9 belum ada sejak Tahap 2: `/admin/scenes/{source}/{id}` (+ `reprocess`), `/admin/quality-thresholds`, `/admin/settings`, `/admin/pipeline/status`, `/admin/archive/*`. | Dibuat di Tahap 3 (`api/routes/admin_monitor.py`) supaya Tahap 4 hanya UI. Reprocess GPM/MODIS = Job Hidromet tanggal itu (bangun ulang non-Final); S1 = coba ulang scene Live, scene Katalog → 409 `NOT_REPROCESSABLE`. `pipeline/status` hanya melaporkan ada/tidaknya kredensial, bukan nilainya. Archive verify = SHA-256 sampel acak (≤ 500). | Tidak. |
| T3-23 | Nama yang berbeda dari dokumen: kode `ALREADY_ACKNOWLEDGED` vs INTERFACE §5 `ALERT_ALREADY_ACKED`; env `ENABLE_SCHEDULER` vs PIPELINE §11 `SCHEDULER_ENABLED`. | Kode diikutkan ke dokumen. | Tidak. |
| T3-25 | Retensi 45 hari `_granule_cache` dataset sistem (PIPELINE §9) belum ada. Uji nyata: 2 hari backfill = ±2 GB granule mentah (GPM ±27 MB, MODIS ±45 MB per berkas) vs produk ±1 MB; 3 tahun tanpa pembersihan ≫ ruang D:. | `hydromet_job.prune_granule_cache()` dipanggil di akhir setiap tanggal: granule bertanggal < tanggal − 45 hari dihapus (jendela GPM 30 hari + lookback MOD09A1 32 + 8 hari masih muat). COG dan baris DB tidak disentuh. | Tidak. |
| T3-26 | Uji backfill nyata 1–7 Januari 2024 (DB produksi): 7/7 COMPLETED, run F, 70 observasi per tanggal (10 kecamatan × 7 band), nilai wajar (24 jam 3–20 mm, 30 hari 226–275 mm, NDVI 0,6–0,8; FLOOD kosong karena awan). Waktu ±130 s per tanggal, bukan ±25–45 s seperti estimasi PIPELINE §10. | Estimasi §10 diperbarui (±1,5–2 hari untuk 3 tahun). Penyebab utama: komposit MOD09A1 warisan module7 membaca ulang 5 granule per band setiap tanggal. Optimasi (cache komposit antar-tanggal) belum dikerjakan. | Opsional: optimasi module7 bila backfill terlalu lama. |
| T3-27 | **Bug ditemukan uji nyata siklus Live** (area Lebak Selatan, scene S1D 22 & 27 September 2026): `monitor_etl` hanya SIU pada `live_scene_metrics`, padahal `live_metrics.save_scene_metrics` (Tahap 1) dan `water_change.save_metrics` menghapus baris band × metrik lama sebelum menyisipkan → `permission denied`, siklus gagal setelah scene pertama READY. Tes lama memakai koneksi pemilik skema sehingga tidak menangkapnya. | `GRANT DELETE ON live_scene_metrics TO monitor_etl` (tabel turunan, baris dibuat ulang tiap finalisasi); grant matrix + DATABASE §8.3 diperbarui; tes baru menulis ulang metrik sebagai `monitor_etl`. | Tidak. |
| T3-28 | **Bug warisan ditemukan uji nyata:** `module1_download` membaca atribut CDSE `absoluteOrbit`/`relativeOrbit`, padahal namanya `orbitNumber`/`relativeOrbitNumber`, sehingga `satellite_scenes.orbit_number` dan `relative_orbit` selalu NULL. Selain itu `live_scenes.s1_product_ids` menyimpan nama terpotong (`…T112236_20`) yang tidak memuat orbit absolut. Akibatnya peringatan "orbit berbeda" tidak pernah muncul (uji: 22-09 orbit relatif 98 vs 27-09 orbit 171 dianggap tidak diketahui). | Nama atribut diperbaiki (nama lama tetap cadangan); `orbit_metadata()` mencocokkan nama terpotong ke nama lengkap di `satellite_scenes` lalu memakai metadata atau rumus. Rumus S1D (offset 42) terverifikasi terhadap nilai CDSE (orbit 4762 → 171). Tiga scene uji di DB produksi diisi ulang orbitnya dari CDSE. | Tidak. |
| T3-29 | Uji nyata peta perubahan air (27-09 vs 22-09-2026): pita merah palsu ±1 km di sepanjang tepi swath (derau batas S1 terbaca air; sebagian besar dari 107,7 km² "air baru"), dan "—" pada label orbit tampil sebagai kotak (font bitmap PIL). | Piksel dalam 1 km (`EDGE_BUFFER_M`) dari NoData di tiap scene dikeluarkan (`mask_swath_edges`, erosi biner; bingkai crop AOI tidak dikikis); label memakai DejaVu Sans dari matplotlib. Catatan: perbandingan lintas orbit (98 vs 171) tetap memberi kategori tinggi; dokumen hanya mensyaratkan label peringatan, bukan penurunan kategori. | Ya, bila perbandingan lintas orbit sebaiknya tidak menaikkan kategori. |
| T3-30 | **Tes warisan menulis ke DB produksi:** `tests/test_fusion_product_identity.py` membuat koneksinya sendiri dari `TEST_DATABASE_URL` *atau* `DATABASE_URL`; tanpa `TEST_DATABASE_URL` ia menumpang data DB produksi dan hanya ter-skip karena produksi belum punya scene (3 "skipped" di run sebelumnya). Setelah uji Live mengisi `satellite_scenes` produksi, tes jalan dan gagal (INSERT FUSION dengan `scene_id`, ditolak `chk_dprods_single_origin`), jadi tidak ada data yang berubah (diverifikasi: 0 baris `UJI_%`). | Tes memakai fixture DB uji conftest (`meta`, `sample_dataset`) dan disesuaikan dengan M30 (produk FUSION tanpa scene, identitas = `file_path`); tidak ada tes lain yang membaca `DATABASE_URL` sendiri. Tidak lagi ada tes yang ter-skip. | Tidak. |
| T3-24 | DB produksi `themonitor` masih skema Tahap 2 (isi: seed + akun `admin` + 1 log login). | Dibangun ulang dari ketiga berkas skema; baris `users` (hash sandi tetap) dan log login disalin kembali, cadangan JSON di `../themonitor_prestage3_users.json`. Lalu `load_regions.py` dengan 10 kecamatan AOI: 28 kecamatan + kabupaten, ROI AOI, dataset `HYDROMET_AOI`, Live Area "Lebak Selatan". | Tidak. |

### Detail tambahan (tidak diatur dokumen)

- Live Area default dibuat `load_regions.py` tanpa memulai siklus (status `BACKFILLING`); scheduler melanjutkannya saat API berjalan (`AUTO_RESUME_JOBS`).
- `SCHEDULER_ENABLED=false` mematikan scheduler pada worker API tambahan; advisory lock tetap menjaga bila tidak dimatikan.
- `POST /admin/ingest` (HYDROMET) menjalankan `hydromet_job.backfill` di thread di bawah kunci `hydromet` (dilewati bila backfill/scheduler lain berjalan).
- `etl/live_scheduler.py` dihapus, digantikan `etl/scheduler.py`.
- Kalimat Live kini berbahasa Indonesia dengan desimal koma; label status area: Normal / Waspada / Tinggi / Tidak tersedia. Asersi teks di `tests/test_live_interpret_forecast.py` diterjemahkan (maknanya sama).
- Berkas akumulasi GPM (`_crop_to_aoi`) kini ditulis lewat `atomic_path()`; PNG perubahan air dan PDF laporan juga.
- Laporan: Total hujan AOI = rerata antar kecamatan dari jumlah hujan 24 jam; hari hujan = rerata AOI ≥ 0,1 mm; hari lebat = ≥ 50 mm di ≥ 1 kecamatan. Skor kesehatan = rerata komponen yang tersedia (yang tanpa data ditulis "—", bukan nol).
