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
