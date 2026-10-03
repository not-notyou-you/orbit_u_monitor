# PIPELINE — Orbit-U: The Monitor

> **STATUS: FINAL v1.0 (1 Oktober 2026).** Mekanisme berlabel **[WARIS]** dijelaskan rinci di DataLab `PIPELINE.md` dan tidak diulang di sini; dokumen ini menulis apa yang dipakai, apa yang diubah, dan apa yang baru.

---

## 1. Prinsip

| Prinsip | Penjelasan | Asal |
|---|---|---|
| Ingestion lewat API resmi | CDSE, LANCE NRT/LAADS DAAC, GES DISC; bukan scraping | [WARIS] D11 |
| Idempoten | Mengulang tanggal yang sama tidak menghasilkan duplikat (UNIQUE + upsert) | [WARIS] + [BARU] |
| Setiap tahap tercatat | `processing_jobs` + `processing_logs`, dengan `parameters` JSONB | [UBAH] |
| Setiap produk tertelusur | `data_lineage` dengan checksum SHA-256 input/output | [WARIS] D9 |
| Sumber pendukung tidak fatal | Gagal MODIS/GPM tidak menggagalkan scene S1 | [WARIS] D10 |
| Satu writer per job/tanggal | OS file lock + atomic write | [WARIS] D22 |
| Satu scheduler aktif | PostgreSQL advisory lock | [BARU] M22 |

---

## 2. Empat Jenis Pekerjaan

| Pekerjaan | Pemicu | Isi | Konsumen |
|---|---|---|---|
| **A. Job Hidromet Harian** [BARU] | Scheduler 02:00 WIB; backfill skrip; Admin | GPM + MODIS untuk AOI → `region_observations` → `alert_events` | Statistik Hari Ini, Analitik, Laporan Hidromet |
| **B. Siklus Live Area** [UBAH] | Scheduler 01/07/13/19 WIB; "Periksa sekarang" | S1 + MODIS + GPM per lintasan S1 → 8 preview + peta perubahan air + kalimat + forecast | Publik, Pengguna |
| **C. Job Dataset** [WARIS] | DATA_ENGINEER/ADMIN lewat wizard | Konfigurasi bebas sumber/level/strategi, rentang historis → COG + fusion HDF5 | Data Engineer |
| **D. Pembuatan Laporan** [BARU] | Senin 03:00 / tanggal 1 03:30 WIB; ADMIN | PDF Hidromet + PDF Kesehatan Data | Analyst, Data Engineer |

Ketiga pekerjaan pertama memakai mesin yang sama (`run_dataset_job`, `download_guard`, modul 1–10). Prioritas slot unduhan: **C (pengguna menunggu) > A > B** — A dan B berjalan di `dg.low_priority()`.

---

## 3. Job Hidromet Harian (A) [BARU]

### 3.1 Bentuk

Satu dataset sistem `HYDROMET_AOI` (`dataset_kind = 'STANDARD'`, `created_by = NULL`, disembunyikan dari Katalog lewat flag `is_system = true`) yang ROI-nya adalah AOI GMLS. Konfigurasi tetap:

| Sumber | Level | Keluaran |
|---|---|---|
| GPM | PROCESSED | `gpm_rain_{24h,72h,7d,30d}_{YYYYMMDD}.tif` |
| MODIS | PROCESSED | `modis_{YYYYMMDD}_{flood,ndvi,ndwi}.tif` |
| Sentinel-1 | — | tidak diambil (dikerjakan siklus Live) |

Tidak memakai `run_dataset_job` penuh (yang berjangkar ke scene S1). Memakai fungsi per-tanggal DataLab `ensure_gpm_inputs_for_date()` dan `ensure_modis_inputs_for_date()` [WARIS], lalu tahap baru di bawah.

### 3.2 Tahap

| # | `stage_code` | Keluaran | Catatan |
|---|---|---|---|
| 1 | `GPM_DOWNLOAD` | granule IMERG di `_granule_cache/gpm/` | fallback F → L → E [WARIS]; `run_type` dicatat |
| 2 | `ACCUMULATE_RAIN` | COG 24h/72h/7d/**30d** | [UBAH] tambah jendela 30 hari (unduh 29 hari sebelumnya; granule di-cache). Hanya untuk dataset `HYDROMET_AOI`; dataset Katalog/Live tetap 24h/72h/7d |
| 3 | `MODIS_DOWNLOAD` + `COMPUTE_NDVI/NDWI` + `EXTRACT_FLOOD` | COG FLOOD/NDVI/NDWI | [WARIS] MCDWD + komposit clear terakhir MOD09A1 |
| 4 | `HYDROMET_AGGREGATE` | baris `region_observations` | zonal statistics, lihat 3.3 |
| 5 | `ALERT_CHECK` | baris `alert_events` | lihat 3.5 |

Tanggal target operasi harian = **kemarin (UTC)**, karena IMERG Late untuk hari H baru tersedia ±14 jam setelah hari H berakhir. GPM diproses lebih dulu daripada MODIS karena alert hanya bergantung pada GPM.

Status per tanggal ada di `dataset_jobs` (`job_type = HYDROMET_DAILY`, satu baris per hari UTC; percobaan ulang memakai baris yang sama): `PROCESSING` → `COMPLETED`, `WAITING_UPSTREAM` (granule belum terbit di run F/L/E mana pun; dicoba lagi job harian berikutnya sampai `app_settings.hydromet.waiting_max_days`), atau `FAILED`. Tiap tahap juga dicatat di `processing_jobs` (tanpa jangkar) dengan parameter §3.7. Backfill (`scripts/backfill_hydromet.py`) melewati tanggal `COMPLETED`, jadi aman dihentikan dan dijalankan ulang.

### 3.3 Zonal statistics (`etl/hydromet_aggregate.py`)

Raster tidak disimpan di DB, jadi agregasi dikerjakan di Python, bukan `ST_Intersects`:

1. Ambil poligon kecamatan `in_aoi` dari `administrative_regions`.
2. Untuk tiap COG dan tiap poligon: `rasterio.features.geometry_mask(..., all_touched=True)` pada grid raster.
3. Nilai:
   - `MEAN`: rata-rata piksel valid berbobot luas piksel (`cos(lat)` untuk grid geografis). Untuk GPM 0,1°, satu kecamatan biasanya hanya 1–6 sel, sehingga **pembobotan fraksi tumpang tindih** dipakai: luas `ST_Intersection(sel, poligon)` dihitung sekali per kecamatan dan di-cache.
   - `FRACTION`: persen piksel valid dengan kelas air (FLOOD kelas 2/3 MCDWD) terhadap piksel valid.
4. `valid_fraction` = piksel valid / piksel dalam poligon. Bila < 0,1, `value = NULL`.
5. Upsert `ON CONFLICT (region_id, band_id, obs_date) DO UPDATE` **hanya bila** run baru lebih baik (`F > L > E`) atau nilai lama NULL. Ini yang membuat Final Run menggantikan Late Run tanpa logika `is_valid` (K7/M6).

### 3.4 Pembaruan Late → Final

Job mingguan (Minggu 04:00 WIB) memeriksa tanggal 4–5 bulan terakhir yang `run_type <> 'F'`. Bila Final sudah terbit di GES DISC, tanggal itu diproses ulang. Alert yang sudah ada **tidak** dihapus walau nilai Final di bawah ambang — alert adalah catatan apa yang diketahui saat itu; `v_evaluasi_alert` memakai nilai alert yang dibekukan.

### 3.5 Pengecekan alert

```
untuk setiap rule aktif:
  untuk setiap baris region_observations (band = rule.band, obs_date = target, value bukan NULL):
    jika value <comparator> threshold:
      INSERT alert_events ... ON CONFLICT (rule_id, region_id, observation_date) DO NOTHING
```

Satu kecamatan bisa memicu INFO, WARNING, dan CRITICAL sekaligus; UI menampilkan severity tertinggi per kecamatan per hari.

### 3.6 Lineage

`region_observations.source_product_id` menunjuk COG asal. Edge `data_lineage` baru tidak dibuat untuk baris observasi (baris DB, bukan berkas); rantai berkasnya sendiri sudah tercatat oleh modul warisan (`EXTRACT_RAINFALL → ACCUMULATE_RAIN → GOLD_EXPORT`).

### 3.7 Parameter tersimpan

```json
{
  "software_version": "orbit-u-monitor 1.0.0",
  "stage": "HYDROMET_AGGREGATE",
  "zonal_method": "area_weighted_overlap",
  "all_touched": true,
  "min_valid_fraction": 0.1,
  "gpm_run": "L",
  "regions": 9
}
```

---

## 4. Siklus Live Area (B) [UBAH]

Mekanisme DataLab D25 dipertahankan: satu `live_areas` + satu dataset `LIVE_AREA`, scene = tanggal akuisisi S1, siklus diserialkan, retensi menghapus berkas tapi menyimpan `live_scenes`. Perubahan:

| Perubahan | Rincian |
|---|---|
| Retensi | 1–60 scene, default 6, diatur ADMIN (M11). Lookback backfill = `min(730, retention × 12 + 14)` hari. Horizon prakiraan `ceil(n/3)` dibatasi maksimal 4 langkah |
| Batas area | dari `app_settings.live.max_areas` (default 5) |
| Area default | Live Area "Lebak Selatan" dibuat saat setup dengan ROI = AOI GMLS |
| Bahasa kalimat | `live_interpret.py` menghasilkan kalimat Bahasa Indonesia (UI); kode kategori tetap Inggris (`normal`, `alert`, `high`, `flood-indicated`, `unavailable`) |
| Ambang | `THRESHOLDS` hujan disinkronkan dengan seed `alert_rules` (BMKG) |
| **Tahap baru `WATER_CHANGE`** | lihat 4.1 |
| Pratinjau tambahan | `s1_water_change.png` (preview ke-9) |

### 4.1 Peta perubahan air (M19) [BARU]

Dijalankan saat finalisasi scene, setelah metrik, bila scene sebelumnya (yang belum dihapus) masih punya COG VH.

1. Baca VH (dB) scene sekarang dan sebelumnya pada grid scene sekarang, diturunkan ke sisi terpanjang 2048 px (rata-rata di ruang linear) [WARIS `live_metrics`].
2. Mask air: `VH < app_settings.water.vh_threshold_db` (default −20 dB, sama dengan ambang `live_interpret`).
   Piksel dalam 1 km dari batas NoData masing-masing scene (tepi swath S1, derau batas yang terbaca "air") dikeluarkan sebelum klasifikasi.
3. Klasifikasi per piksel valid di kedua tanggal:

| Kelas | Kondisi | Warna |
|---|---|---|
| Air tetap | air → air | biru `#2F6FDE` |
| Air baru | darat → air | merah `#E04545` |
| Air surut | air → darat | hijau `#2FA36B` |
| Darat tetap | darat → darat | transparan (latar VH abu) |
| Tidak ada data | NoData di salah satu tanggal | pola kotak-kotak |

4. Peringatan kualitas: orbit relatif diambil dari metadata katalog (`satellite_scenes.relative_orbit`), cadangannya rumus nama produk (`(abs − offset) mod 175 + 1`; S1A 73, S1B 27, S1C 172 sampai 23-06-2026, S1D 42; S1C sejak 24-06-2026 hanya dari metadata). Bila orbit relatif kedua scene berbeda, PNG diberi label "orbit berbeda — perubahan bisa karena geometri pencitraan", karena backscatter dari sudut datang berbeda tidak sepenuhnya sebanding.
5. Metrik disimpan di `live_scene_metrics` (band `WATER_CHANGE`; `new_km2`, `receded_km2`, `persistent_km2`, `valid_km2` (luas teramati di kedua tanggal; penyebut kategori kalimat), dengan `ref_live_scene_id` = scene pembanding; flag orbit sama/berbeda di `metric_name = 'same_orbit'` bernilai 1/0); luas = jumlah piksel × luas piksel geodesik.
6. Scene pertama area tidak punya pembanding → tidak ada baris `WATER_CHANGE`, tile menampilkan "belum ada scene pembanding".

### 4.2 Metrik Live ke tabel (M31) [UBAH]

`live_metrics.py` tetap menghitung angka yang sama seperti DataLab, tetapi menulisnya sebagai baris `live_scene_metrics` (satu baris per band × metrik) alih-alih JSONB. `live_forecast.py` dan endpoint kartu membaca dari tabel ini. Migrasi data tidak diperlukan karena DB Monitor dimulai kosong.

Keterbatasan yang ditulis di skripsi: ambang tetap (bukan Otsu), permukaan halus (jalan, landasan) bisa terbaca air, vegetasi tergenang bisa terbaca darat.

---

## 5. Job Dataset (C) [WARIS]

Wizard, `dataset_source_config`, tiga strategi fusion, RAW/PROCESSED per sumber, antrean `MAX_ACTIVE_JOBS`, pause/resume/cancel, preview opsional, laporan per dataset — semua sesuai DataLab. Perubahan:

| Perubahan | Rincian |
|---|---|
| Region | Hanya ROI sistem: AOI GMLS, kecamatan tunggal, atau gabungan kecamatan yang dibuat ADMIN |
| Pemilik | `datasets.created_by`; DATA_ENGINEER melihat semua dataset non-sistem (tim kecil, tidak perlu isolasi per pengguna) |
| Batas rentang | ≤ 366 hari per dataset (`app_settings.dataset.max_days`) agar satu job tidak memonopoli disk |
| Dataset sistem | `HYDROMET_AOI` dan dataset `LIVE_AREA` tidak tampil di Katalog |
| Unduhan | Setiap unduhan (ZIP dataset, produk, fusion, laporan) mencatat `user_activity_logs` dengan `bytes_sent` |

Tahap S1 [WARIS]: DOWNLOAD → CALIBRATE (LUT σ⁰ linear + reproject GCP) → CROP → LEE_FILTER 7×7 → QUALITY_ANALYTICS → COG_EXPORT; mosaik per tanggal sebelum PREVIEW/FUSION. Perubahan kecil: `module6_analytics` membaca ambang dari `quality_thresholds` (satu-satunya sumber; kolom "Minimum quality score" di wizard dihapus) dan menulis `quality_alerts` (bukan `alert_events`).

### 5.1 Registrasi produk MODIS/GPM (M30) [UBAH]

DataLab mendaftarkan produk MODIS/GPM pada baris palsu `satellite_scenes` (`NASA_AUX_{SOURCE}_{dataset}_{tanggal}`). Di Monitor:

- `MetadataManager.insert_data_product()` dan `insert_processing_job()` menerima `scene_id` **atau** `nasa_scene_id`; `module9_fusion` (tempat produk MODIS/GPM didaftarkan) mengirim `nasa_scene_id` dari baris `nasa_scenes` granule asal (komposit MOD09A1 memakai granule periode terakhir yang dipakai). Job DOWNLOAD/GOLD_EXPORT MODIS/GPM berjangkar granule yang sama; job FUSION tanpa jangkar.
- Produk FUSION mengisi keduanya NULL; asal-usulnya di `fusion_products` + `data_lineage`.
- Kunci dedup `is_latest` produk satu sumber menjadi `(COALESCE(scene_id,0), COALESCE(nasa_scene_id,0), band_name, product_tier, dataset_id)`. Produk FUSION (NULL-NULL) didedup per **`file_path`** — kunci di atas akan menyamakan stack semua tanggal; nama berkas fusion sudah memuat tanggal + strategi + level. Placeholder `NASA_AUX_FUSION_*` diganti `fusion_products.s1_scene_id` NULL pada hari tanpa S1.
- `DeletionManager` tidak lagi membersihkan `NASA_AUX_*`; sebagai gantinya ia menghapus langsung produk MODIS/GPM/FUSION milik dataset (dulu terhapus lewat cascade placeholder) dan job FUSION tanpa jangkar milik dataset itu. Granule `nasa_scenes` dipakai bersama dan tidak dihapus.
- Tes regresi `tests/test_per_satellite_config.py` warisan wajib tetap lulus.

---

## 6. Pembuatan Laporan (D) [BARU]

Dibangun di atas `report_generator.py` DataLab (reportlab, A4, DejaVu, header/footer, chart matplotlib). Dua template baru; template "Dataset Report" 11 bagian DataLab tetap tersedia per dataset di Katalog.

### 6.1 Jadwal dan periode (WIB)

| Laporan | Periode | Dibuat |
|---|---|---|
| Hidromet Mingguan | Senin 00:00 – Minggu 23:59 minggu lalu | Senin 03:00 |
| Hidromet Bulanan | tanggal 1 – akhir bulan lalu | tanggal 1, 03:30 |
| Kesehatan Data Mingguan | idem mingguan | Senin 03:15 |
| Kesehatan Data Bulanan | idem bulanan | tanggal 1, 03:45 |

Data hidromet per tanggal UTC dipetakan ke periode WIB berdasarkan `obs_date`. Laporan dibuat setelah job hidromet 02:00 selesai (job laporan menunggu advisory lock job hidromet maksimal 60 menit, lalu tetap jalan dengan catatan "data hari terakhir belum lengkap").

### 6.2 Isi Laporan Hidromet (ANALYST)

| # | Bagian | Sumber |
|---|---|---|
| 1 | Ringkasan eksekutif: total hujan AOI, hari hujan (≥ 0,1 mm), hari lebat, jumlah alert, jumlah kejadian | `region_observations`, `alert_events`, `disaster_events` |
| 2 | Hujan per kecamatan: tabel harian 24h + peta koroplet total periode | `v_hujan_harian_kecamatan`, `administrative_regions` |
| 3 | Grafik hujan 24h & 72h dengan garis ambang | idem + `alert_rules` |
| 4 | Alert: daftar, severity, status acknowledge, waktu tanggap (triggered → acknowledged) | `alert_events` |
| 5 | Kejadian bencana periode ini + hujan H-0..H-2 | `v_kejadian_dan_hujan` |
| 6 | Evaluasi alert (bulanan saja, kumulatif sejak awal arsip): hit / miss / false alarm | `v_evaluasi_alert` |
| 7 | Vegetasi & genangan: NDVI dan % FLOOD MODIS per kecamatan, indikator kekeringan `RAIN_30D` | `region_observations` |
| 8 | Ringkasan Live: scene S1 dalam periode, luas air baru/surut | `live_scene_metrics` |
| 9 | Catatan keterbatasan (resolusi GPM 10 km, awan MODIS, revisit S1) | statis |

### 6.3 Isi Laporan Kesehatan Data (DATA_ENGINEER)

| # | Bagian | Sumber |
|---|---|---|
| 1 | Skor kesehatan (completeness, kualitas radiometrik S1, cakupan spasial) | adaptasi DataLab REPORT §9.1 |
| 2 | Kelengkapan per sumber: hari ada/tidak ada data, gap > 10 hari, `run_type` GPM (F/L/E) | `v_kelengkapan_data`, `nasa_scenes` |
| 3 | Kualitas: distribusi `quality_flag` S1, `valid_fraction` MODIS/GPM, `quality_alerts` | `v_ringkasan_kualitas` |
| 4 | Pipeline: job per jenis (A/B/C), sukses/gagal, durasi per tahap, error terbanyak | `processing_jobs`, `processing_logs`, `dataset_jobs` |
| 5 | Lineage: jumlah produk per tier, sampel rantai lineage satu produk acak + verifikasi checksum | `data_products`, `data_lineage` |
| 6 | Fusion: stack dibuat per strategi, offset temporal, cakupan S1 (`audit_dataset_coverage`) | `fusion_products` |
| 7 | Penyimpanan per tier dan per jenis pekerjaan; berkas dihapus retensi | storage scanner [WARIS], `live_scenes` |
| 8 | Unduhan: volume per jenis unduhan dan per role (tanpa nama pengguna) | `user_activity_logs` |

### 6.4 Penyimpanan

`data/reports/{report_code}/{YYYY}/{report_code}_{period_start}.pdf`, ditulis via `atomic_path()`, dicatat di `generated_reports` dengan checksum. Regenerasi oleh ADMIN menandai baris lama `SUPERSEDED` (berkasnya dipertahankan). Laporan tidak pernah memuat angka contoh: data kosong → tabel kosong + "—" (DataLab D27).

---

## 7. Penjadwalan

| Job | Cron (Asia/Jakarta) | Kunci advisory |
|---|---|---|
| Hidromet harian | 02:00 setiap hari | `hydromet` |
| Pembaruan Late → Final | Minggu 04:00 | `hydromet` |
| Siklus Live | 01:00, 07:00, 13:00, 19:00 | `live` |
| Laporan mingguan | Senin 03:00 / 03:15 | `report` |
| Laporan bulanan | tanggal 1, 03:30 / 03:45 | `report` |
| Backup `pg_dump` | 01:30 | (di luar APScheduler, cron OS) |

**Advisory lock (M22):** setiap job membuka koneksi dan memanggil `pg_try_advisory_lock(hashtext('orbit-u:' || key))`. Bila gagal, worker lain sedang menjalankannya → job dilewati dan dicatat sebagai baris `processing_jobs` tahap `ORCHESTRATE` berstatus `SKIPPED_LOCKED` (`parameters_json.scheduler_job`, `.lock`). `scripts/backfill_hydromet.py` dan `POST /admin/ingest` memegang kunci `hydromet` yang sama. Kunci dilepas otomatis bila proses mati karena koneksinya putus. Ini melengkapi `job_lock` berkas DataLab (yang menjaga per job/area), bukan menggantikannya.

---

## 8. Penanganan Kegagalan

| Situasi | Tindakan | Asal |
|---|---|---|
| Unduhan putus / 5xx | Retry dengan backoff, resume HTTP Range; S1 sampai 6 kali | [WARIS] |
| 429 / 503 | Hormati `Retry-After` (≤ 300 s); circuit breaker per penyedia | [WARIS] D26 |
| Token NASA 401/403 | Gagal cepat; peringatan di panel Admin dan kartu Live | [WARIS] |
| Granule GPM hari H belum ada | Status `WAITING_UPSTREAM`; dicoba lagi pada jadwal berikutnya (maks. 3 hari) lalu `FAILED` | [BARU] |
| Kecamatan tanpa piksel valid | `value = NULL`, `valid_fraction` dicatat; tidak memicu alert | [BARU] |
| Pipeline mati di tengah | Tahap SUCCESS dilewati saat resume; `.part` S1 dipertahankan | [WARIS] |
| Scheduler ganda | Advisory lock | [BARU] |
| Laporan gagal | `generated_reports.status = FAILED` + pesan; panel Admin menampilkan tombol "Buat ulang" | [BARU] |

---

## 9. Storage

### Tata letak

```
data/
├── datasets/{id}_{slug}/            [WARIS] dataset C, dataset LIVE_AREA, dataset sistem HYDROMET_AOI
│   ├── sentinel-1/{RAW,PROCESSED}/  modis/{…}/  gpm-imerg/{…}/
│   ├── fusion/{co-occurrence,full-coverage,hybrid}/
│   ├── preview/…   live/{YYYYMMDD}/{key}.png   reports/   _granule_cache/   _work/
├── reports/{report_code}/{YYYY}/    [BARU] laporan mingguan/bulanan
└── _job_locks/                      [WARIS]
```

`masks/` dan `merged/` tidak ada (dihapus).

### Retensi

| Data | Retensi | Alasan |
|---|---|---|
| COG GPM AOI (24h/72h/7d/30d) | permanen | kecil (AOI ~±1° → beberapa KB per berkas) |
| COG MODIS AOI | permanen | ±1–3 MB per hari |
| Granule GPM/MODIS mentah (`_granule_cache`) | 45 hari untuk dataset sistem | jendela 30 hari + margin; bisa diunduh ulang dari URL |
| S1 Live | sesuai retensi area | [WARIS] |
| S1 dataset C | sampai dataset dihapus DATA_ENGINEER/ADMIN | |
| Laporan PDF | permanen | |
| Baris DB (`region_observations`, `live_scenes`, log, audit) | permanen | metrik tetap hidup setelah berkas hilang |

### Estimasi disk

| Komponen | Perkiraan |
|---|---|
| Hidromet 3 tahun (GPM + MODIS AOI) | 2–5 GB |
| Live 1 area × 60 scene × ~0,3 GB | ±18 GB maksimum |
| Dataset C (contoh: 1 tahun, S1 PROCESSED + fusion) | 15–40 GB per dataset |
| **Disarankan** | ≥ 100 GB bebas |

---

## 10. Data Conversion & Loading (initial loading)

Orbit-U tidak menggantikan basis data lama, sehingga tahap ini berupa muatan awal.

| # | Sumber | Tujuan | Skrip / cara |
|---|---|---|---|
| 1 | Seed SQL | 12 master + `app_settings` | `monitor_seed.sql` |
| 2 | Shapefile COD-AB IDN adm2 + adm3 (HDX `cod-ab-idn`) | `administrative_regions` (Kab. Lebak + kecamatannya) | `load_regions.py`: filter `ADM2_PCODE` Lebak, `ST_Multi`, `ST_MakeValid` |
| 3 | Daftar kecamatan GMLS: 10 kecamatan wilayah Lebak Selatan (Banjarsari, Wanasalam, Cijaku, Malingping, Cihara, Cigemblong, Panggarangan, Bayah, Cibeber, Cilograng; IMPLEMENTATION_NOTES T3-4) | `in_aoi = true` | ADMIN via UI, impor Excel `kecamatan`, atau `load_regions.py --aoi "…"` (shapefile default `data/external/cod-ab-idn/`) |
| 4 | Turunan | `regions_of_interest` AOI (`is_monitor_aoi`) | otomatis setelah langkah 3 |
| 5 | Akun | admin pertama | `create_admin.py` |
| 6 | API satelit 2023-01-01 – 2025-12-31 | `nasa_scenes`, `data_products`, `region_observations`, `alert_events` | `backfill_hydromet.py` (job A per tanggal, berurutan, resume-aware) |
| 7 | Catatan kejadian GMLS (dokumen/spreadsheet) | `disaster_events` | input ANALYST lewat UI, atau `import_disasters.py` dari CSV terstruktur. Impor BNPB DIBI **opsional** (M36) memakai skrip yang sama |
| 8 | Live Area "Lebak Selatan" | `live_areas` + backfill sesuai retensi | otomatis setelah langkah 4 |

### Pemetaan kolom COD-AB → `administrative_regions`

| Kolom shapefile | Kolom tujuan |
|---|---|
| `ADM3_PCODE` / `ADM2_PCODE` | `pcode` |
| `ADM3_EN` / `ADM2_EN` | `region_name` |
| `ADM2_PCODE` (pada adm3) | `parent_region_id` (lookup) |
| geometri | `geom` (`ST_Multi(ST_MakeValid(...))`, EPSG:4326) |
| konstanta | `admin_level` 2/3, `source_dataset` |

> Batas COD-AB ditetapkan 2020 dari BPS. Bila GMLS memakai batas yang lebih baru, perbedaannya dicatat sebagai keterbatasan; struktur tabel tidak berubah.

### Estimasi waktu backfill hidromet

Rencana awal: ±1.096 hari × (GPM ±5 s + MODIS ±20–40 s) ≈ 10–15 jam. **Terukur (uji 1–7 Januari 2024, Tahap 3):** tanggal pertama ±10 menit (30 granule GPM untuk jendela 30 hari), tanggal berikutnya ±125–165 s, sekitar 60% di antaranya komposit NDVI/NDWI MOD09A1 (module7 membaca ulang 5 granule per band setiap tanggal), diukur saat mesin juga memproses S1. Perkiraan realistis **±1,5–2 hari** untuk 2023–2025; dijalankan bertahap (mis. per bulan atau per tahun) karena backfill bisa dihentikan dan dilanjutkan.

---

## 11. Konfigurasi

Konfigurasi runtime tetap lewat `.env` [WARIS] (`DB_*`, `COPERNICUS_*`, `NASA_EARTHDATA_TOKEN`, `MAX_ACTIVE_JOBS`, batas koneksi, dll.), ditambah:

```bash
DB_NAME=themonitor
DB_APP_USER=monitor_app
DB_ETL_USER=monitor_etl
JWT_SECRET=<acak 32+ byte>
JWT_TTL_HOURS=8
SCHEDULER_ENABLED=true          # false pada worker kedua bila tidak ingin bergantung pada advisory lock
TZ_DISPLAY=Asia/Jakarta
```

Konfigurasi yang boleh diubah ADMIN tanpa restart disimpan di DB: `alert_rules`, `quality_thresholds`, `disaster_types`, `app_settings`, `live_areas.retention`, `administrative_regions.in_aoi`. `config/config.json` DataLab (sebagian besar mati) **dihapus**.

---

## 12. Modul Baru dan yang Diubah

| Berkas | Status | Isi |
|---|---|---|
| `etl/hydromet_job.py` | [BARU] | Job A: orkestrasi per tanggal, Late→Final |
| `etl/hydromet_aggregate.py` | [BARU] | Zonal statistics → `region_observations` |
| `etl/alert_engine.py` | [BARU] | Evaluasi `alert_rules` → `alert_events` |
| `etl/water_change.py` | [BARU] | Peta & metrik perubahan air S1 |
| `etl/report_hydromet.py`, `etl/report_datahealth.py` | [BARU] | Dua template laporan periodik |
| `etl/scheduler.py` | [UBAH] dari `live_scheduler.py` | Semua cron + advisory lock |
| `etl/advisory_lock.py`, `etl/settings.py`, `etl/regions.py` | [BARU] | Kunci advisory; pembaca `app_settings`; wilayah COD-AB, AOI, ROI, dataset `HYDROMET_AOI` |
| `etl/report_periodic.py` | [BARU] | Periode WIB, penyimpanan atomik, `generated_reports` (SUPERSEDED/FAILED) |
| `etl/disasters.py`, `etl/excel_io.py` | [BARU] | Validasi kejadian bersama; ekspor/impor Excel generik (INTERFACE §4.10) |
| `scripts/load_regions.py`, `scripts/backfill_hydromet.py` | [BARU] | Muatan awal wilayah/AOI; backfill hidromet resume-aware |
| `etl/module8_gpm_download.py` | [UBAH] | Jendela `30d` (hanya hidromet), `GranuleNotPublished`, bangun ulang non-Final, tulis atomik |
| `etl/module6_analytics.py` | [UBAH] | Ambang dari `quality_thresholds`; tulis `quality_alerts` |
| `etl/live_interpret.py`, `live_preview.py`, `live_cycle.py` | [UBAH] | Kalimat Indonesia, preview ke-9, retensi 1–60 |
| `etl/dataset_merge.py`, `refusion.py`, `reference_layers.py`, `land_mask.py`, `water_occurrence.py`, `geo_utils.geocode_search` | [HAPUS] | Pembaca frame S1 `refusion.scene_results_for_date` masih dipakai orchestrator, jadi dipindah ke `module5_orchestrator` |
| `etl/folder_manager.py` | [UBAH] | Hapus `masks/`, tambah `data/reports/` |
| `etl/database_client.py`, `metadata_manager.py`, `module9_fusion.py`, `deletion_manager.py`, `dataset_manager.py` | [UBAH] | Registrasi produk via `nasa_scene_id`; hapus placeholder `NASA_AUX_*` (M30). module7/8 tidak perlu diubah |
| `etl/tier_names.py` | [UBAH] | Helper SQL hanya mengeluarkan nama tier D14 |
| `database/apply_schema.py` | [BARU] | Penerap ketiga berkas skema (pengganti `run_migration.py`) |
| `etl/live_metrics.py`, `live_forecast.py` | [UBAH] | Tulis/baca `live_scene_metrics` (M31) |
| `benchmark/` | [BARU] | `load_pg.py`, `load_mysql.py`, `queries/{pg,mysql}/q1–q5.sql`, `features/f1–f3`, `run.py` → `results/` (M29) |
| `tools/data_dictionary.py` | [BARU] | Kamus data + ERD Mermaid dari katalog DB (M34) |
| `scripts/import_disasters.py` | [BARU] | Impor CSV kejadian (GMLS; DIBI opsional); format sama dengan impor Excel `disasters` |

---

## 13. Artefak Pengujian di Repo (M35)

| Berkas | Menguji |
|---|---|
| `tests/test_auth.py` | login, kunci akun, kedaluwarsa JWT, token API (scope, revoke, expiry) |
| `tests/test_rbac_api.py` | setiap endpoint × setiap role → kode yang diharapkan (tabel matriks INTERFACE §3) |
| `tests/security/grant_matrix.sql` | `SET ROLE` per role terhadap setiap tabel/VIEW; hasil dibandingkan dengan matriks DATABASE §8.3 |
| `tests/test_audit.py` | UPDATE lewat aplikasi dan lewat psql sama-sama tercatat; `password_hash`/`token_hash` tersensor |
| `tests/test_hydromet_aggregate.py` | zonal statistics pada raster sintetis dengan jawaban diketahui; Late→Final |
| `tests/test_alert_engine.py` | ambang, idempotensi, severity ganda |
| `tests/test_water_change.py` | klasifikasi 4 kelas pada raster sintetis |
| `tests/test_reports.py` | kedua template menghasilkan PDF valid untuk periode kosong dan berisi (pypdf) |
| `tests/test_schema_comments.py` | semua tabel, kolom, dan VIEW punya `COMMENT ON`; generator kamus data mencakup semua tabel |
| `tests/test_live_scene_metrics.py` | metrik Live tersimpan 1NF dan tersusun ulang tanpa kehilangan (M31) |
| `tests/recovery/kill_and_resume.sh` | matikan proses saat job hidromet/dataset/laporan → jalankan ulang → tidak ada duplikat |
| `tests/recovery/backup_restore.sh` | `pg_dump` → DB kosong → `pg_restore` → hitung baris sama |
| Warisan DataLab | `tests/test_per_satellite_config.py`, `test_pipeline_branching.py`, `test_report_generation.py` tetap lulus |

Versi prototipe ditandai tag git: `v0.1` (iterasi pertama ke GMLS: Beranda, Statistik Hari Ini, Kejadian), `v0.2` (perbaikan dari masukan + Analitik, Laporan), `v1.0` (final). Masukan GMLS tiap iterasi dicatat di `docs/prototype_feedback.md`.
