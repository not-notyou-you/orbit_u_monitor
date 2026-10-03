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
| T9 | `/scenes?source=S1\|MODIS\|GPM` + `include_invalid` (§4.7, K12) belum ada di kode warisan; endpoint ini bagian kelola scene ADMIN (§4.9). | Ditunda ke tahap fitur admin scene. Role DATA_ENGINEER sudah terpasang. | Ya, bila ingin dimajukan ke Tahap 2. |
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
