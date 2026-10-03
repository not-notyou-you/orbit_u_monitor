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
| K12 | Langkah 6 (nama DB `orbit_u_monitor`) sudah dikerjakan di commit `7416ac5`. | Hanya diverifikasi; komentar docker di `.env.example` dirapikan. |

### Detail tambahan (tidak diatur dokumen)

- `config/config_locations.json` (lokasi Jabodetabek DataLab, sudah dipindah ke DB sejak migrasi 012) dihapus bersama `config/config.json`.
- `_refusion_run_46.py` di root dihapus bersama `refusion.py`. Berkas riset lain di root (`_export_s1a_only/`, `_copy_wajo_s1a_by_year.py`, `_s1_coverage_*`, `report/`) tidak disentuh.
- `database/run_migration.py` diganti `database/apply_schema.py` yang menerapkan ketiga berkas skema memakai kredensial `.env`.
