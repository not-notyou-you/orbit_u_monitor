# PIPELINE.md — Orbit-U: The Monitor

Alur data dari penyedia satelit sampai ke basis data. Dokumen ini ditulis ulang pada 8 Oktober 2026 dari kode
di `etl/`, `scripts/`, dan `api/`. Kalau isi dokumen ini berbeda dengan kode, **kode yang benar**. Dokumen
inilah yang diperbaiki, lalu perubahannya dicatat di Decisions Log README §7.

Nomor bagian dirujuk langsung oleh kode, misalnya `PIPELINE §3.4` di `etl/hydromet_job.py`. Jangan
menomori ulang.

Tahap DBSDLC yang dijawab: **Implementation** dan **Data Conversion and Loading**. Struktur tabel tujuan
ada di DATABASE.md.

---

## 1. Sumber dan Peran

| Sumber | Produk | Diambil oleh | Peran |
|---|---|---|---|
| GPM IMERG (NASA GES DISC) | `GPM_3IMERGDF` (Final), `…DL` (Late), `…DE` (Early) | `module8_gpm_download` | **Tulang punggung**: hujan harian adalah satu-satunya dasar alert |
| MODIS Terra & Aqua (NASA LANCE/LAADS) | `MCDWD_L3_F2_NRT` (FLOOD), `MOD09A1` / `MOD09GA` (NDVI, NDWI) | `module7_modis_download` | Pendamping, **tidak fatal**: kalau gagal, hari itu tetap selesai tanpa MODIS |
| Sentinel-1 (ESA CDSE) | GRD IW, VV + VH | `module1_download` | Verifikasi pasca-kejadian, per lintasan 6–12 hari |

Semua tanggal data adalah **hari UTC** (M28). Periode laporan dihitung dalam WIB (§6.1).

Kredensial dibaca dari `.env`: `COPERNICUS_*` dan `NASA_EARTHDATA_TOKEN`.

---

## 2. Tier Artefak (D14)

| Tier | Isi | Folder di disk |
|---|---|---|
| RAW | Format vendor | `bronze/` |
| ALIGNED | EPSG:4326 + crop AOI (S1: terkalibrasi, sigma-nought) | `bronze/` |
| DESPECKLED | S1 setelah filter Lee 7×7 | `silver/` |
| INDICES | MODIS NDVI/NDWI | `silver/` |
| ACCUMULATED | GPM 24h/72h/7d(/30d) | `silver/` |
| COG | Cloud-Optimized GeoTIFF per band | `gold/` |
| FUSED | HDF5 multi-sensor | `fusion/` |

Nama folder `bronze/silver/gold` adalah warisan DataLab dan tidak diganti, karena berkas yang sudah ada
bergantung padanya. Di basis data hanya nama D14 yang dipakai (`product_tier_enum`). Penerjemahannya ada di
`etl/tier_names.py`.

Level per sumber (`dataset_source_config.processing_levels`) diterjemahkan menjadi tahap oleh **satu modul**,
yaitu `etl/processing_plan.py`:

| Sumber | RAW | PROCESSED |
|---|---|---|
| SENTINEL1 | calibrate + reproject + crop → ALIGNED | + Lee + QA + COG → DESPECKLED, COG |
| MODIS | peta banjir saja → ALIGNED | + NDVI + NDWI → INDICES, COG |
| GPM | hujan 1 hari → ALIGNED | + akumulasi 24h/72h/7d → ACCUMULATED, COG |

"RAW" untuk SAR tetap berarti terkalibrasi, karena nilai DN mentah tidak punya arti fisik.

---

## 3. Job Hidromet Harian

`etl/hydromet_job.py`. Satu tanggal = satu hari UTC = satu baris `dataset_jobs` (`job_type =
HYDROMET_DAILY`).

```
1  GPM download + akumulasi        COG RAIN 24h/72h/7d/30d   (fallback run F -> L -> E)
2  HYDROMET_AGGREGATE (GPM)        RAIN_* per kecamatan      -> region_observations
3  ALERT_CHECK                     alert_rules x observasi   -> alert_events
4  MODIS + HYDROMET_AGGREGATE      FLOOD/NDVI/NDWI           -> region_observations (tidak fatal)
```

GPM dijalankan lebih dulu karena alert hanya bergantung pada GPM.

### 3.1 Dataset sistem `HYDROMET_AOI`

Job ini berjalan di atas satu dataset sistem (`etl/regions.ensure_hydromet_dataset`): GPM + MODIS
`PROCESSED`, tier `COG`, bbox = ROI AOI GMLS, `is_system = true`, `is_deletable = false`. Dataset ini
disembunyikan dari Katalog dan dibangun ulang oleh `scripts/load_regions.py` setiap kali daftar kecamatan
AOI berubah.

### 3.2 GPM dan jendela akumulasi

`module8_gpm_download.WINDOWS`: 24h = 1 hari, 72h = 3 hari, 7d = 7 hari, **30d = 30 hari**. Jendela 30 hari
hanya diminta Job Hidromet untuk indikator kekeringan (`RAIN_30D`). Dataset Katalog dan Live tetap memakai
24h/72h/7d.

Run dicoba berurutan **Final → Late → Early**. Run yang dipakai dicatat di
`region_observations.run_type`.

Granule mentah di-cache datar di `_granule_cache/gpm/`, karena satu granule harian ikut dipakai jendela
tanggal-tanggal berikutnya.

### 3.3 Agregasi zonal per kecamatan

`etl/hydromet_aggregate.py`. Raster tidak disimpan di basis data, jadi agregasi dikerjakan di Python:

1. Ambil poligon kecamatan `in_aoi`.
2. Ambil sel raster yang tersentuh poligon (`all_touched`).
3. Bobot sel = luas irisan sel ∩ poligon × cos(lintang). Untuk GPM 0,1° satu kecamatan hanya 1–6 sel,
   sehingga sel tepi yang hanya tersentuh sedikit tidak boleh berbobot penuh.
4. `MEAN` = Σ(w·v)/Σw. `FRACTION` = persen bobot sel berkelas air MCDWD (2, 3).
5. `valid_fraction` = Σw sel valid / Σw semua sel. Kalau di bawah `hydromet.min_valid_fraction` (0,1), maka
   `value = NULL`.
6. Upsert `ON CONFLICT (region_id, band_id, obs_date)` hanya kalau run baru tidak lebih buruk
   (F > L > E) atau nilai lama NULL. NULL tidak pernah menimpa nilai yang sudah ada.

Langkah 6 adalah cara **Final menggantikan Late** tanpa perlu menandai baris tidak valid.

### 3.4 Pembaruan Late → Final

IMERG Final terbit sekitar 3,5 bulan setelah hari H. Setiap Minggu pukul 04:00, scheduler memeriksa
tanggal-tanggal dalam `FINAL_REFRESH_DAYS` = 153 hari terakhir yang masih berstatus L/E, lalu membangunnya
ulang. Kalau Final sudah terbit, upsert §3.3 menimpa nilainya.

### 3.5 Evaluasi alert

`etl/alert_engine.py`, satu pernyataan SQL per tanggal:

```
untuk setiap alert_rules aktif:
  untuk setiap observasi (band = rule.band, obs_date = tanggal, value bukan NULL):
    jika value <comparator> threshold:
      INSERT alert_events … ON CONFLICT (rule_id, region_id, observation_date) DO NOTHING
```

- Satu kecamatan bisa memicu INFO, WARNING, dan CRITICAL sekaligus.
- Alert yang sudah ada **tidak diubah** walaupun nilai observasinya kemudian direvisi Final. Alert adalah
  catatan tentang apa yang diketahui pada saat itu. Nilai, ambang, dan severity disalin ke baris alert
  (DATABASE.md §5.2).
- Comparator hanya diambil dari whitelist, yang juga ditegakkan oleh CHECK tabel.

### 3.6 MODIS

FLOOD diambil dari MCDWD harian (komposit 2 hari, 250 m). NDVI dan NDWI dihitung dari reflektansi
`MOD09A1` (komposit 8 hari, 500 m), dengan fallback ke `MOD09GA` harian. Piksel awan, bayangan, dan cirrus
dibuang. NDWI memakai rumus McFeeters (green/NIR) untuk air permukaan.
Kalau reflektansi tidak tersedia tetapi MCDWD ada, hari itu tetap menghasilkan FLOOD.

### 3.7 Jejak per tahap

Setiap tahap menulis satu baris `processing_jobs`. `parameters_json` memuat versi perangkat lunak, run GPM,
jendela, dan ambang yang dipakai, sehingga angka di `region_observations` bisa ditelusuri ke produk sumbernya
(`source_product_id` → `data_products` → `data_lineage`).

---

## 4. Siklus Live dan Sentinel-1

`etl/live_cycle.py`, `etl/live_monitor.py`. Satu Live Area = satu baris `datasets`
(`dataset_kind = LIVE_AREA`) ditambah satu baris `live_areas`. Live Area diproses pipeline biasa dengan
konfigurasi tetap: S1 + MODIS + GPM `PROCESSED`, tier COG saja, strategi CO_OCCURRENCE, dan tanpa HDF5.

```
1  discovery scene S1 baru di seluruh jendela storage.raster_retention_days
2  unduh + proses (run_dataset_job); MODIS/GPM di-hardlink dari dataset utama bila ada
3  gerbang cakupan: < live.min_aoi_coverage (0,90) -> INCOMPLETE, berkas dihapus
4  per scene: metrik -> 8 preview -> peta perubahan air (preview ke-9) -> kalimat kondisi
5  S1 per kecamatan (VV, VH, WATER_PCT) -> region_observations   (etl/s1_observations.py)
6  hitung ulang prakiraan
7  retensi berkas
8  setiap langkah dicatat di live_events
```

**Backfill adalah siklus yang sama** (M58). Tanggal terbaru dikerjakan lebih dulu, per batch, supaya
kemajuannya tersimpan bertahap. Kegagalan satu sumber tidak menggagalkan scene: sumber yang gagal ditandai
FAILED di `source_status`, scene tetap tampil sebagai PARTIAL, dan siklus berikutnya mencoba ulang.

**Kalimat kondisi** (`etl/live_interpret.py`) dibangun dengan aturan, dalam format wajib:

> Menampilkan [apa] dalam kondisi [kategori] karena [angka].

Semua ambang ada di satu tempat, yaitu `THRESHOLDS` di modul itu. Kategori diputuskan dari **perubahan**
terhadap scene sebelumnya, bukan dari persen absolut, karena badan air permanen (laut, sungai) selalu
konstan.

**Prakiraan** (`etl/live_forecast.py`): 1 titik memakai *persistence*, 2–3 titik memakai *simple exponential
smoothing*, dan ≥ 4 titik memakai Holt dengan tren teredam. Parameternya tetap, tidak dioptimasi, karena
deretnya terlalu pendek. Pita ketidakpastian 80% melebar untuk deret pendek.

### 4.1 Peta perubahan air

`etl/water_change.py` (M19):

1. VH scene sekarang dan scene pembanding dibaca di grid scene sekarang, lalu diturunkan resolusinya ke
   sisi terpanjang 2048 px dengan rata-rata di ranah linear.
2. Piksel dianggap air kalau `VH < water.vh_threshold_db` (−20 dB).
3. Kelas: PERSISTENT (biru), NEW (merah), RECEDED (hijau), LAND (transparan), NODATA (kotak-kotak).
4. Kalau orbit relatif berbeda, peta diberi label "orbit berbeda" dan `same_orbit = 0`.
5. Luas dihitung dari piksel × luas piksel geodesik (km²). Hasilnya ditulis ke `live_scene_metrics`
   (`WATER_CHANGE`).

Keterbatasan yang ditulis di skripsi: ambangnya tetap (bukan Otsu), permukaan halus bisa terbaca sebagai
air, dan vegetasi tergenang bisa terbaca sebagai darat.

---

## 5. Dataset Katalog

Dibuat DATA_ENGINEER lewat wizard (`etl/dataset_manager.py`, `etl/module5_orchestrator.py`). Rentang paling
panjang `dataset.max_days` (366 hari). Setiap sumber punya cabang sendiri sesuai levelnya (§2). Sentinel-1
menjadi jangkar tanggal kalau dikonfigurasi. Tanpa S1, sumber pendamping diproses per hari.

**FUSION** hanya berjalan kalau ada lebih dari satu sumber **dan** dataset punya `fusion_strategy`:

| Strategi | Unduh MODIS/GPM | Satu HDF5 per |
|---|---|---|
| CO_OCCURRENCE | Hanya tanggal S1 | Tanggal S1 |
| FULL_COVERAGE | Setiap hari | Hari; S1 dipinjam dari hari terdekat ≤ `s1_match_tolerance_days` |
| HYBRID | Setiap hari | Tanggal S1 |

**Pemakaian ulang granule.** Sebelum mengunduh, `download_guard.find_reusable_file` mencari salinan lengkap di
dataset lain dan membuat *hardlink* (atau menyalin kalau beda volume). Nama berkas adalah identitas
produk.

### 5.1 Fusion

`etl/module9_fusion.py`. Input diambil dari tier COG, bukan tier antara, karena COG adalah kontrak
"analysis-ready". Grid referensi = grid S1 dan **dipaku** di `datasets.fusion_grid` sejak fusi pertama,
sehingga semua tanggal tumpuk di grid yang sama. MODIS/GPM dicocokkan ke tanggal fitur (hari itu atau H-1,
tidak pernah sesudahnya).

Granule asal band MODIS dicatat ke `nasa_scenes`. Untuk FLOOD, granule asalnya adalah tanggal output. Untuk
NDVI/NDWI (komposit "observasi clear terakhir"), granule asalnya adalah **periode terakhir yang dipakai**.

Struktur HDF5 dikelompokkan per sumber (`/sentinel1/VV`, `/modis/NDVI`, `/gpm/rainfall_24h`, …) dan hanya
memuat sumber yang dikonfigurasi. Hasil fusi dicatat di `fusion_products` dan `data_products`
(tier FUSED).

---

## 6. Laporan Periodik

`etl/report_periodic.py` (kerangka) dan dua template di atas generator reportlab warisan.

| Jenis | Audiens | Jadwal (WIB) | Modul |
|---|---|---|---|
| Hidromet mingguan / bulanan | ANALYST | Senin 03:00 / tanggal 1 03:30 | `report_hydromet.py` |
| Kesehatan Data mingguan / bulanan | DATA_ENGINEER | Senin 03:15 / tanggal 1 03:45 | `report_datahealth.py` |

**Tidak ada angka karangan.** Bagian yang tidak punya data menampilkan "—" dan catatan.

### 6.1 Periode

Mingguan berarti Senin–Minggu minggu lalu, bulanan berarti bulan lalu, keduanya dalam WIB. Data hidromet
(tanggal UTC) dipetakan ke periode lewat `obs_date`. Job laporan menunggu kunci `hydromet` paling lama
`report.wait_hydromet_minutes` (60). Kalau kunci belum lepas, laporan tetap dibuat dengan catatan "data hari
terakhir belum lengkap".

### 6.2 Laporan Hidromet

Sembilan bagian. Semua angka dibaca dari `region_observations`, `alert_events`, `disaster_events`,
`v_kejadian_dan_hujan`, dan `v_evaluasi_alert` untuk periode itu.

### 6.3 Laporan Kesehatan Data

Delapan bagian, dari `v_ringkasan_kualitas`, `v_kelengkapan_data`, `v_unduhan_per_role`, serta checksum
berkas untuk sampel lineage. Batas periode kolom `TIMESTAMPTZ` dihitung dari Senin 00:00 sampai Minggu 23:59
WIB.

### 6.4 Penyimpanan dan regenerasi

Berkas laporan disimpan di `data/reports/{report_code}/{YYYY}/{report_code}_{period_start}.pdf` dan ditulis
secara atomik. Regenerasi menulis `…_v2.pdf`, `…_v3.pdf` supaya berkas lama tidak hilang. Dalam transaksi
yang sama, baris READY lama diubah menjadi SUPERSEDED dan baris READY baru disisipkan. Kalau gagal, ditulis
baris FAILED beserta pesannya.

---

## 7. Scheduler dan Penguncian

`etl/scheduler.py` adalah satu-satunya APScheduler. Ia berjalan di dalam proses API dan terkoneksi sebagai
`monitor_etl`.

| Job | Cron (Asia/Jakarta) | Kunci |
|---|---|---|
| Hidromet harian | 02:00 setiap hari | `hydromet` |
| Pembaruan Late → Final | Minggu 04:00 | `hydromet` |
| Siklus Live | 01:00, 07:00, 13:00, 19:00 | `live` |
| Laporan mingguan | Senin 03:00 / 03:15 | `report` |
| Laporan bulanan | tanggal 1, 03:30 / 03:45 | `report` |
| Forecast tersimpan (jaring pengaman, §14.1) | 00:30, 06:30, 12:30, 18:30 | `forecast` |

**Peringatan email (M64).** Ini bukan job tersendiri. `etl/notify.run_quietly` dipanggil di akhir Hidromet
harian dan siklus Live, setelah datanya tersimpan, di bawah kunci `notify`. Galat di dalamnya hanya dicatat
dan tidak pernah menggagalkan job datanya. Pembaruan Late → Final, backfill, dan proses ulang tidak
memanggilnya, sehingga tanggal lampau tidak memicu email.

Ada dua lapis penguncian:

| Lapis | Mekanisme | Melindungi |
|---|---|---|
| Per jenis job | `pg_try_advisory_lock(hashtext('orbit-u:' || key))` di koneksi khusus (`etl/advisory_lock.py`) | Dua worker menjalankan job yang sama. Yang kalah dicatat `SKIPPED_LOCKED` |
| Per dataset/area | Lock berkas tingkat OS (`etl/job_lock.py`) | Dua proses (mis. `uvicorn --reload`) menggarap dataset yang sama |

Kedua kunci **lepas sendiri** kalau prosesnya mati: advisory lock lepas karena koneksinya putus, lock berkas
dilepas oleh kernel.

---

## 8. Kegagalan dan Pemulihan

| Kejadian | Perilaku |
|---|---|
| Granule GPM hari itu belum terbit di run mana pun | Tanggal berstatus `WAITING_UPSTREAM` dan dicoba lagi tiap jadwal sampai `hydromet.waiting_max_days` (3), lalu `FAILED` |
| MODIS gagal | Tidak fatal, hari itu tetap `COMPLETED` dengan GPM |
| Unduhan macet tetapi masih mengalir | `download_guard.StallGuard` membatalkan percobaan kalau laju rata-rata di bawah ambang dalam satu jendela (`DOWNLOAD_STALL_WINDOW_S`, default 90 s). Setelah itu retry dan resume Range mengambil alih |
| Backfill gagal beruntun | `backfill_hydromet.py` berhenti setelah 5 hari `FAILED` berurutan (kode keluar 4), karena penyebabnya hampir selalu jaringan atau kredensial |
| **Pipeline mati di tengah** | Tanggal `COMPLETED` dilewati. Tanggal yang sedang dikerjakan diulang dari awal. Semua penulisan idempoten (upsert / `ON CONFLICT`). Cukup jalankan perintah yang sama lagi |
| Job dataset terputus | `recover_interrupted_jobs()` melanjutkan dari `scene_job_state` |
| Scene S1 hanya menyerempet AOI | Ditandai `INCOMPLETE`, tidak dicoba ulang (tanggal itu memang tidak melintas penuh) |

Uji: `tests/recovery/kill_and_resume.sh` dan `recovery_backfill.py`.

---

## 9. Retensi

| Data | Umur |
|---|---|
| Raster dataset utama (COG GPM/MODIS, berkas scene S1 Live) | `storage.raster_retention_days` = **365 hari**, dihapus `etl/raster_retention.py` dan `LiveMonitor.enforce_retention` |
| Granule mentah dataset sistem (`_granule_cache`) | 45 hari: jendela GPM 30 hari + lookback komposit MOD09A1 masih muat |
| `region_observations`, `live_scene_metrics`, baris `live_scenes` | **Selamanya** |
| Baris `nasa_scenes`, `data_products` | Selamanya. Produk yang berkasnya dihapus ditandai `is_valid = false` supaya lineage tetap terbaca |
| Dataset Katalog | Sampai dihapus pemiliknya |
| `band_forecasts` (+ titik dan skor) | 365 hari, dihapus di akhir `forecast_store.refresh` (§14) |

Retensi hanya menghapus berkas di dalam root dataset miliknya sendiri, sehingga berkas dataset lain tidak
pernah tersentuh.

---

## 10. Setup dan Pemuatan Awal

Urutan untuk mesin baru:

| # | Langkah | Perintah |
|---|---|---|
| 1 | Skema, keamanan, seed master | `python database/apply_schema.py` |
| 2 | Wilayah COD-AB adm2 + adm3 Kabupaten Lebak → `administrative_regions` | `python scripts/load_regions.py` |
| 3 | Tandai kecamatan AOI (`in_aoi`) | `… load_regions.py --aoi "Bayah,Panggarangan,…"` |
| 4 | ROI AOI, ROI per kecamatan, dataset sistem `HYDROMET_AOI` | otomatis oleh langkah 2–3 |
| 5 | Admin pertama | `python scripts/create_admin.py` |
| 6 | Backfill GPM + MODIS | `python scripts/backfill_hydromet.py --from … --to …` |
| 6b | Backfill Sentinel-1 | `python scripts/backfill_s1.py` |
| 7 | Kejadian dari CSV (opsional) | `python scripts/import_disasters.py kejadian.csv --username <analis>` |
| 8 | Live Area default "Lebak Selatan" | otomatis oleh `load_regions.py`; backfill-nya dimulai scheduler saat API jalan |

Daftar kecamatan AOI dikonfirmasi ke GMLS sebelum backfill. Mengubahnya nanti cukup lewat data.

**Impor kejadian.** Format CSV dan aturannya ada di docstring `scripts/import_disasters.py`. Satu berkas =
satu transaksi: kalau ada baris yang salah, tidak ada yang ditulis. Baris yang sudah ada dilewati. Skrip
terkoneksi sebagai `monitor_app` lalu `SET LOCAL ROLE` sesuai peran pengguna, sehingga GRANT dan audit-nya
sama seperti input lewat UI.

**Skrip perawatan** (idempoten):
- `repair_incomplete_scenes.py`: menerapkan gerbang cakupan ke scene lama.
- `backfill_admin_overlay.py`: menambah varian PNG bergaris wilayah.
- `backfill_preview_grid.py`: mengisi georeferensi preview untuk Relief 3D.

Ketiganya tidak berjalan kalau batas wilayah belum dimuat.

---

## 11. `app_settings`

Bisa diubah ADMIN tanpa restart. Kalau sebuah baris hilang, nilai default di `etl/settings.py` dipakai (sama
dengan seed).

| Kunci | Default | Arti |
|---|---|---|
| `live.max_areas` | 5 | Jumlah maksimum Live Area aktif |
| `live.retention_max` | 60 | Batas atas scene di kartu Live/prakiraan |
| `live.retention_default` | 6 | Jumlah scene default Live Area baru |
| `live.default_area_name` | "Lebak Selatan" | Nama Live Area default |
| `live.min_aoi_coverage` | 0,90 | Porsi AOI yang wajib tertutup S1 |
| `water.vh_threshold_db` | −20 | Ambang air VH (dB) |
| `hydromet.min_valid_fraction` | 0,1 | Di bawah ini nilai kecamatan = NULL |
| `hydromet.waiting_max_days` | 3 | Lama `WAITING_UPSTREAM` sebelum `FAILED` |
| `report.timezone` | "Asia/Jakarta" | Zona waktu periode laporan |
| `report.wait_hydromet_minutes` | 60 | Lama laporan menunggu kunci hidromet |
| `dataset.max_days` | 366 | Rentang maksimum satu dataset |
| `storage.raster_retention_days` | 365 | Umur berkas raster dataset utama |

---

## 12. Log

| Tempat | Isi |
|---|---|
| `processing_logs` | Kejadian tahap per dataset (STARTED/RUNNING/COMPLETED/FAILED) |
| `live_events` | Langkah siklus Live per area |
| `dataset_jobs` | Hasil per tanggal Job Hidromet: riwayat yang awet |
| `logs/backfill/backfill_<id>.log` | Log utuh backfill yang dimulai dari halaman Data. 500 baris terakhir juga disimpan di memori untuk polling UI (`etl/backfill_runs.py`) |
| `user_activity_logs`, `audit_log` | Aksi pengguna dan perubahan data (DATABASE.md §4.2.5, §8.5) |

---

## 13. Backup dan Restore

- **Uji restore:** `tests/recovery/backup_restore.sh` menjalankan `pg_dump -Fc` dari database uji, me-restore
  ke database kosong, lalu membandingkan jumlah baris per tabel, jumlah objek, dan GRANT. Skrip ini menolak
  berjalan pada database produksi `themonitor`.
- **Membandingkan dua mesin:** `database/db_manifest.sql` (baca saja, aman untuk produksi).
- **Backup produksi:** `etl/scheduler.py` menyebut `pg_dump` pukul 01:30 lewat cron OS, di luar APScheduler.
  **Skrip dan jadwal cron-nya belum ada di repo.** Ini harus dibuat terpisah, misalnya Task Scheduler
  Windows yang memanggil `pg_dump -Fc`.

---

## 14. Forecast 15 Hari

Halaman Forecast (M61) menampilkan forecast 15 hari di setiap grafik garis. Algoritmanya ada di
`etl/band_forecast.py` (murni numpy, tanpa DB). Penyimpanan dan penjadwalannya ada di
`etl/forecast_store.py` (M62).

### 14.1 Kapan dihitung

Forecast dihitung **saat data baru masuk**, bukan saat halaman dibuka, lalu disimpan di `band_forecasts`
(DATABASE.md §4.2.9). Halaman hanya membacanya.

| Pemicu | Tempat |
|---|---|
| Job Hidromet harian dan Late → Final selesai | `scheduler.job_hydromet_daily`, `job_hydromet_final` |
| Backfill hidromet selesai (skrip atau halaman Data) | akhir `hydromet_job.backfill` |
| Setiap siklus Live (Sentinel-1) selesai, termasuk backfill S1 | akhir `live_cycle.run_cycle` |
| Jaring pengaman | job `forecast_refresh` 00:30, 06:30, 12:30, 18:30 |
| Manual | `python -m etl.forecast_store [--force]` |

Deret yang dihitung: 10 band per kecamatan × (rerata AOI + setiap kecamatan AOI) = 110 deret untuk 10
kecamatan. Supaya pemicu yang sering tetap murah, setiap band punya **cap data**:

```
cap(band) = max( max(region_observations.computed_at  untuk band itu),
                 max(live_scenes.updated_at) )
```

Deret dihitung ulang hanya bila `cap` sekarang berbeda dari `data_stamp` forecast tersimpan terakhirnya.
Band yang datanya tidak berubah dilewati. Satu pekerja sekaligus dijamin oleh advisory lock `forecast`
(§7). Kegagalan forecast tidak pernah menggagalkan job data yang memicunya.

API `GET /api/diagram/forecast` memakai forecast tersimpan bila tiga syarat terpenuhi: horizon = 15, deretnya
rerata AOI atau satu kecamatan, dan `cap` masih sama serta `end` ≥ tanggal observasi terakhir yang dipakai
(artinya `end` tidak memotong data). Selain itu, misalnya rentang di masa lalu atau rerata beberapa
kecamatan, forecast dihitung di tempat lalu disimpan di memori proses sampai `cap` berubah.

Ukuran nyata (data Jan 2024 – Okt 2026, 10 kecamatan, 9 Okt 2026):

| Kegiatan | Waktu |
|---|---|
| Hitung semua 110 deret pertama kali | 5,6 s |
| Panggilan ulang tanpa data baru (110 dilewati) | 0,1 s |
| API, forecast tersimpan | 2–17 ms per deret |
| API, dihitung di tempat | 25–66 ms per deret |

### 14.2 Deret masukan

Notasi: `y_t` = nilai hari `t`, `T` = hari observasi terakhir, `h` = 1…15 langkah ke depan.

- **Satu kecamatan**: `y_t` = `region_observations.value`.
- **Rerata AOI**: `y_t = (1/|R_t|) Σ_{r ∈ R_t} y_{r,t}`, dengan `R_t` = kecamatan AOI yang punya nilai hari `t`.
  Hari tanpa angka harian diisi rerata metrik `mean` scene Live (sumber yang sama dengan grafik).
- **Rerata beberapa kecamatan** (Tren & evaluasi alert, CH-03): rumus yang sama dengan `R_t` terbatas pada
  kecamatan pilihan.
- Seluruh riwayat sampai `end` dipakai. Hari kosong diisi **interpolasi linier** supaya model bekerja pada
  grid harian, tetapi hari hasil interpolasi **tidak ikut dinilai** di backtest.
- **Hujan** (`RAIN_24H`, `RAIN_72H`, `RAIN_7D`, `RAIN_30D`) dimodelkan di ruang log karena distribusinya miring
  dan banyak nol: `z_t = ln(1 + y_t)`, dan hasil dikembalikan dengan `y = e^z − 1`.

### 14.3 Lima model kandidat

| Model | Rumus forecast | Parameter |
|---|---|---|
| **Naive** | `ŷ_{T+h} = y_T` | — |
| **SES** (simple exponential smoothing) | `ℓ_t = ℓ_{t−1} + α (y_t − ℓ_{t−1})`; `ŷ_{T+h} = ℓ_T` | `α ∈ {0,05; 0,10; …; 0,95}` |
| **Holt tren teredam** | lihat di bawah | `α ∈ {0,1; 0,2; 0,3; 0,5; 0,7}`, `β ∈ {0,05; 0,1; 0,2}`, `φ = 0,9` |
| **Musiman (klimatologi)** | `ŷ_{T+h} = c(d_{T+h})` | jendela ±15 hari |
| **Musiman + anomali AR(1)** | `ŷ_{T+h} = c(d_{T+h}) + φ^h · a_T` | `φ` dari data |

**Holt tren teredam**, dengan galat satu langkah `e_t`:

```
ŷ_{t|t−1} = ℓ_{t−1} + φ·b_{t−1}
e_t       = y_t − ŷ_{t|t−1}
ℓ_t       = ŷ_{t|t−1} + α·e_t
b_t       = φ·b_{t−1} + α·β·e_t
ŷ_{T+h}   = ℓ_T + (φ + φ² + … + φ^h)·b_T
```

Redaman `φ` membuat tren melandai, tidak diteruskan lurus tanpa batas.

**Klimatologi.** `d_t` = hari ke berapa dalam tahun (0…365). `S(d)` = jumlah nilai pada hari-dalam-tahun
`d` dari semua tahun, `N(d)` = banyaknya. Rerata dihaluskan jendela melingkar ±15 hari (31 Desember
bertetangga dengan 1 Januari):

```
c(d) = Σ_{|d'−d| ≤ 15} S(d')  /  Σ_{|d'−d| ≤ 15} N(d')
```

**Anomali AR(1).** Anomali = selisih dari klimatologi, `a_t = y_t − c(d_t)`. Koefisien persistensi:

```
φ = corr(a_{t−1}, a_t),  dijepit ke [0; 0,99]
```

Anomali hari terakhir meluruh `φ^h` menuju klimatologi. Artinya, kalau hari ini lebih basah dari biasanya,
beberapa hari ke depan diramal tetap lebih basah tetapi makin mendekati kebiasaan musimnya.

SES dan Holt dilatih pada 365 hari terakhir saja (data lebih tua praktis tidak berpengaruh untuk `α ≥ 0,05`).
Parameter `α`, `β` dipilih dari grid dengan meminimalkan jumlah kuadrat galat satu langkah `Σ e_t²`.
Klimatologi dan AR(1) memakai seluruh riwayat.

### 14.4 Pemilihan model: backtest rolling-origin

Untuk deret dengan `n` hari, titik asal backtest:

```
o_j = n − 15 − 30·j,   j = 0, 1, …, 11,   hanya bila o_j ≥ 30
```

Jadi asalnya tersebar setiap 30 hari sepanjang setahun terakhir (semua musim). Pada setiap asal, setiap
model dilatih dengan `y_1 … y_{o_j}` lalu meramal 15 hari berikutnya. Galatnya dihitung dalam satuan asli,
hanya pada hari yang benar-benar teramati (`O`):

```
MAE_m = (1/|O|) Σ_{(j,h) ∈ O} | y_{o_j+h} − ŷ^{(m)}_{o_j+h} |

model terpilih   m* = argmin_m MAE_m
skill            = 1 − MAE_{m*} / MAE_naive
```

Model musiman hanya ikut bila asal paling awal masih punya ≥ 395 hari riwayat
(`n − 15 − 330 ≥ 395`). Karena itu Sentinel-1, yang riwayatnya kurang dari setahun, hanya memakai naive, SES,
dan Holt. `skill` dibaca sebagai "berapa persen lebih kecil galatnya dibanding menebak nilai terakhir
berlanjut". `skill = 0` berarti naive sendiri yang terbaik.

| Keyakinan | Syarat |
|---|---|
| tinggi | `skill ≥ 0,20` dan ≥ 8 asal backtest |
| sedang | selain itu, `skill ≥ 0,05` dan ≥ 4 asal |
| rendah | `skill < 0,05`, < 4 asal, atau riwayat terlalu pendek untuk backtest (dipakai SES) |

Deret dengan kurang dari 10 hari berdata tidak diramal.

### 14.5 Pita ketidakpastian 80%

Pita diambil dari **galat backtest model terpilih**, bukan dari asumsi distribusi normal. Galat
`e_{j,k} = y − ŷ` dihitung di ruang model (log untuk hujan). Untuk langkah `h`, galat langkah tetangga
`|k − h| ≤ 2` dikumpulkan menjadi `P_h`:

```
bila |P_h| ≥ 8 :  L_h = min(Q_0,10(P_h), 0),   U_h = max(Q_0,90(P_h), 0)
selain itu      :  L_h = −1,2816·σ_h,           U_h = +1,2816·σ_h
```

`Q_p` adalah kuantil ke-`p`. `σ_h` adalah simpangan baku galat dalam sampel model itu:

| Model | `σ_h` |
|---|---|
| Naive | `σ·√h` (σ dari selisih harian) |
| SES | `σ·√(1 + (h−1)·α²)` |
| Holt | `σ·√(1 + (h−1)·α²·(1+β)²)` |
| Musiman | `σ` (tetap) |
| Musiman + AR(1) | `σ_a·√(1 − φ^{2h})` |

Pita dibuat tidak menyempit ke depan (`L_h = min_{k≤h} L_k`, `U_h = max_{k≤h} U_k`), lalu:

```
mean_h = back(ŷ_{T+h}),   lo_h = back(ŷ_{T+h} + L_h),   hi_h = back(ŷ_{T+h} + U_h)
```

`back` adalah `e^z − 1` untuk hujan dan identitas untuk band lain. Hasilnya dijepit ke rentang fisik:

| Band | Rentang |
|---|---|
| Hujan (`RAIN_*`) | ≥ 0 mm |
| `FLOOD`, `WATER_PCT` | 0–100 % |
| `NDVI`, `NDWI` | −1…1 |
| `VV`, `VH` | −40…10 dB |

### 14.6 Hasil pada data nyata

Rerata AOI, backtest setahun (9 Okt 2026):

| Band | Model terpilih | Skill |
|---|---|---|
| Hujan 72 jam | musiman + AR(1) | 0,32 |
| Hujan 7 hari | musiman + AR(1) | 0,29 |
| Genangan MODIS | musiman | 0,24 |
| Hujan 24 jam | musiman + AR(1) | 0,12 |
| NDVI, NDWI | SES | ≈ 0 |
| VV, VH | naive | 0 |

Akumulasi hujan dan genangan punya pola musim yang kuat, jadi model musiman menang jelas. NDVI, NDWI, dan
backscatter Sentinel-1 berubah sangat lambat dalam 15 hari, sehingga "nilai terakhir berlanjut" sulit
dikalahkan. Halaman menampilkannya sebagai keyakinan rendah, bukan menyembunyikannya.
