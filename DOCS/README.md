# Orbit-U: The Monitor

> **STATUS: FINAL v1.0 (1 Oktober 2026)** — pedoman tunggal pengembangan. Perubahan setelah ini dicatat di Decisions Log (§7) dengan ID baru, bukan dengan menimpa entri lama.

Sistem basis data monitoring hidrometeorologi dan arsip kejadian bencana untuk **Gugus Mitigasi Lebak Selatan (GMLS)**, Kecamatan Bayah, Kabupaten Lebak, Banten. Dibangun dengan meng-*clone* **Orbit-U: The DataLab** dan merombaknya, bukan dari nol.

**Judul skripsi:** Perancangan Sistem Basis Data Monitoring Hidrometeorologi untuk Dukungan Mitigasi Bencana Lebak Selatan Berbasis Satelit Sentinel-1, MODIS, dan GPM.

---

## 1. Ringkasan

| Sumber | Produk | Resolusi | Temporal | Penyedia |
|---|---|---|---|---|
| Sentinel-1 (S1A, S1C) | GRD IW, VV + VH | ~10 m | per lintasan (6–12 hari, tergantung jumlah satelit aktif) | ESA / CDSE |
| MODIS Terra & Aqua | MCDWD (banjir), MOD09A1/MOD09GA (NDVI, NDWI) | 250–500 m | harian / komposit 8 hari | NASA LANCE NRT + LAADS DAAC |
| GPM IMERG | Daily Final → Late → Early | ~10 km | harian | NASA GES DISC |

**Yang dilakukan:** mengumpulkan data tiga satelit secara otomatis, mengolahnya dengan lineage dan kontrol kualitas, menyajikan kondisi terkini kepada publik dan relawan, memberi peringatan saat hujan melewati ambang, mencatat kejadian bencana, membuat laporan mingguan/bulanan otomatis, dan menyediakan katalog dataset historis bagi data engineer.

**Yang TIDAK dilakukan:** deteksi banjir real-time. Banjir bandang di Bayah surut dalam hitungan jam, sedangkan S1 melintas setiap 6–12 hari. GPM harian adalah tulang punggung monitoring; S1 berperan sebagai verifikasi pasca-kejadian.

---

## 2. Cakupan

### Bencana

| Bencana | Indikator | Alert otomatis? |
|---|---|---|
| Banjir | `rain_24h` (ambang BMKG) + verifikasi S1/MODIS | Ya |
| Longsor | `rain_72h` | Ya, **aktif setelah ambang dari literatur diisi** (seed `is_active = false`) |
| Kekeringan | `rain_30d` + NDVI | Tidak — indikator di dashboard saja (M17) |
| Tsunami, gempa, gelombang tinggi | — | Di luar scope |

### Wilayah

Batas kecamatan dari **COD-AB Indonesia level 3** (BPS via OCHA/HDX, lisensi CC BY-IGO). Seluruh kecamatan Kabupaten Lebak dimuat; kecamatan yang termasuk cakupan GMLS ditandai `in_aoi = true` oleh Admin. AOI = `ST_Union` poligon kecamatan ber-`in_aoi`. Level desa tidak tersedia di COD-AB versi terbaru, sehingga desa hanya dicatat sebagai teks pada `disaster_events`.

> Daftar kecamatan `in_aoi` **dikonfirmasi ke GMLS** sebelum backfill. Mengubahnya kemudian cukup lewat data, bukan kode.

### Hubungan dengan SIGAP DESA

Orbit-U **tidak menggantikan** SIGAP DESA (PHP/MySQL milik GMLS). Data warga, KK, NIK, titik evakuasi, dan KRB tidak diambil alih (privasi dan di luar scope).

---

## 3. Pengguna dan Hak Akses

| Role | Login | Kebutuhan |
|---|---|---|
| `PUBLIC` | Tidak | Scene Live terbaru: 8 preview, kalimat kondisi, status area |
| `USER` | Ya | Scene Live 30 hari terakhir + forecast, statistik hujan hari ini per kecamatan, alert aktif (lihat saja) |
| `ANALYST` | Ya | Semua milik USER + Analitik + acknowledge alert + CRUD kejadian bencana + unduh **Laporan Hidromet** mingguan/bulanan |
| `DATA_ENGINEER` | Ya | Semua milik USER + Katalog Dataset (buat dataset historis, unduh produk & fusion HDF5, lineage, kualitas) + unduh **Laporan Kesehatan Data** mingguan/bulanan |
| `ADMIN` | Ya | Semua akses + kelola scene, Live Area, pengguna, aturan alert, wilayah AOI, pengaturan; lihat log login, log unduhan, audit trail |

Matriks rinci per halaman dan endpoint: INTERFACE.md §3. Penegakan di basis data: DATABASE.md §8.

---

## 4. Arsitektur

```
 API resmi (CDSE / LANCE+LAADS / GES DISC)
            │
            ▼
 ETL Python (warisan DataLab) ─── APScheduler + PostgreSQL advisory lock
   ├─ Job Hidromet Harian   02:00 WIB  → region_observations → alert_events
   ├─ Siklus Live Area      01/07/13/19 WIB → live_scenes (+ peta perubahan air)
   ├─ Job Dataset (on-demand, DATA_ENGINEER) → COG + fusion HDF5
   └─ Laporan               Senin 03:00 / tgl 1 03:30 WIB → PDF
            │
            ├──► Filesystem data/ (COG, HDF5, PNG, PDF)
            ▼
 PostgreSQL 14+ / PostGIS 3+   (metadata, lineage, kualitas, observasi, alert, kejadian, audit)
            │   SET LOCAL ROLE monitor_<role> per request
            ▼
 FastAPI (REST, bahasa Inggris)
            ▼
 Web vanilla HTML/CSS/JS + Leaflet (UI Bahasa Indonesia)
```

**Prinsip pemisahan:** raster disimpan di filesystem; basis data hanya menyimpan metadata, path, checksum, dan nilai agregat per kecamatan. Karena itu sistem tetap tergolong **basis data terstruktur** (peminatan Database).

---

## 5. Peta Warisan dari DataLab

Label yang dipakai di keempat dokumen:

| Label | Arti |
|---|---|
| **[WARIS]** | Dipakai apa adanya dari repo DataLab |
| **[UBAH]** | Ada di DataLab, dimodifikasi |
| **[BARU]** | Dibangun untuk Monitor |
| **[HAPUS]** | Dibuang dari hasil clone |

### Dihapus

| Fitur DataLab | Alasan |
|---|---|
| Merge Datasets (`dataset_merge.py`, `/api/merge/*`) | AOI GMLS cukup satu bbox, tidak perlu dipecah |
| Reference layers (`masks/`, `reference_land_polygons`, JRC) | Tidak menjawab rumusan masalah |
| Wilayah buatan pengguna + geocoding Nominatim | AOI berasal dari kecamatan resmi COD-AB |
| Dataset LIVE lama (`dataset_kind='LIVE'`, `live_dataset_sources`, `/api/live` lama) | Sudah legacy di DataLab |
| `refusion.py` (kecuali pembaca frame S1, dipindah ke orchestrator), `cleanup` tier machine-wide | Alat perawatan riset; tidak dibutuhkan operasional |
| TimescaleDB, `dataset_versions`, `api_access_logs`, `processing_rules`, Docker | Diganti tabel Monitor atau tidak dipakai |
| Landing page berbahasa Inggris | Diganti Beranda Publik berbahasa Indonesia |

### Diwariskan

Pipeline S1/MODIS/GPM, `processing_plan.py`, fusion + 3 strategi, lineage SHA-256, `quality_metrics`, `download_guard`, `job_lock`, `atomic_write`, `s1_mosaic`, aturan aux D/D-1 dan normalisasi UTC, wizard dan Katalog Dataset, Live Monitoring (metrik, 8 preview, kalimat kondisi, forecast, retensi), generator laporan reportlab, design system frontend.

### Baru

Autentikasi + 5 role + GRANT nyata, token API pribadi, audit trigger, log login/unduhan, `administrative_regions` + `region_observations`, `alert_rules`/`alert_events` hujan + acknowledge + evaluasi, `disaster_events`, laporan mingguan/bulanan dua jenis, peta perubahan air S1, job hidromet harian, advisory lock scheduler, tabel master, `live_scene_metrics`, perbaikan `nasa_scene_id`, benchmark DBMS, kamus data otomatis, artefak uji.

### Hasil akhir skripsi ↔ artefak di repo

| Hasil akhir (ketentuan prodi) | Artefak |
|---|---|
| Rancangan Database | `database/monitor_schema.sql`, `monitor_security.sql`, `monitor_seed.sql`; `tools/data_dictionary.py` → kamus data + ERD fisik |
| Rekomendasi DBMS | `benchmark/` (skrip muat data, 5 kueri, 3 uji fitur keamanan) + `benchmark/results/*.csv` |
| Rancangan Sistem/Aplikasi | Web `web/` + FastAPI `api/` |
| Middleware / API Database (API Developer) | REST API + token API pribadi + OpenAPI `/docs` + `docs/api_examples.md` |
| Prasyarat master ≥ 10, transaksi ≥ 100 | 12 master; `region_observations` ±79.000 baris |
| Testing 5 kriteria | `tests/`, `tests/security/grant_matrix.sql`, `tests/recovery/` |

---

## 6. Keterlacakan ke Rumusan Masalah

| RM | Dijawab oleh |
|---|---|
| RM1 — basis data relasional terintegrasi untuk ingestion 3 satelit | Skema master/transaksi, `satellite_scenes`/`nasa_scenes`, `region_observations`, `fusion_products`, job hidromet + Live + dataset |
| RM2 — lineage + quality metrics | `data_lineage` (SHA-256 input/output), `processing_jobs.parameters`, `quality_metrics`, `quality_thresholds`, `v_ringkasan_kualitas`, Laporan Kesehatan Data |
| RM3 — dashboard + API user-friendly | Beranda Publik, Pantauan Live, Statistik Hari Ini, Analitik, Kejadian Bencana, Katalog, Laporan, REST API |
| RM4 — kontrol akses berbasis role + audit trail | 5 role aplikasi ↔ 5 role PostgreSQL, `SET LOCAL ROLE`, VIEW per role, `audit_log` (trigger), `user_activity_logs` |

Tahap DBSDLC yang dipenuhi tiap dokumen: DATABASE.md (conceptual, logical, physical, DBMS selection, data loading), PIPELINE.md (implementation, data conversion & loading), INTERFACE.md (pemodelan sistem, desain antarmuka, prototyping, testing).

---

## 7. Decisions Log

Keputusan rancangan awal (D1–D24) yang masih berlaku dirangkum; keputusan baru diberi awalan **M**.

| ID | Keputusan | Alasan |
|---|---|---|
| M1 | Monitor dibangun dari clone DataLab | Pipeline 3 satelit, lineage, fusion, Live, dan laporan sudah teruji; membangun ulang membuang satu semester |
| M2 | Monitoring hidromet, bukan deteksi banjir real-time (D1) | Revisit S1 tidak menangkap puncak banjir bandang |
| M3 | PostgreSQL 14+ + PostGIS 3+, **tanpa** TimescaleDB (D5, D22) | Volume data tidak membutuhkannya |
| M4 | **Revisi K2**: pipeline S1 DataLab dipakai (kalibrasi LUT + reproject GCP sendiri), bukan Sentinel Hub | Kode sudah ada; tahap lineage lebih kaya untuk RM2 |
| M5 | **Revisi K3**: MODIS mengikuti DataLab (MCDWD + MOD09A1 komposit clear terakhir, fallback MOD09GA NRT) | Kode sudah ada |
| M6 | GPM mengikuti fallback DataLab Final → Late → Early; kolom `run_type` dicatat; tanpa penggantian otomatis (K7) | Backfill historis otomatis memakai Final, operasi harian Late |
| M7 | Tabel `region_observations` (K1) | Satu tempat untuk nilai harian per kecamatan dari ketiga satelit; dasar alert, statistik, laporan |
| M8 | Batas wilayah dari COD-AB level 3; AOI = kecamatan `in_aoi` | Data resmi BPS ber-P-code; cakupan diubah lewat data |
| M9 | Fusion + 3 strategi dipertahankan, dipakai DATA_ENGINEER lewat wizard Katalog (K4.A) | Kode sudah ada; ada konsumen nyata (engineer ML) |
| M10 | Katalog Dataset + wizard DataLab diwariskan untuk DATA_ENGINEER/ADMIN | Konfigurasi data historis adalah kebutuhan role DATA_ENGINEER |
| M11 | Live Monitoring diwariskan; retensi scene diatur Admin (1–60, default 6); maksimal 5 Live Area | Pengguna melihat beberapa scene + forecast; batas atas menjaga disk |
| M12 | Forecast DataLab (SES/Holt teredam, parameter tetap) **diterima** | Bukan ML, kode sudah ada, diminta untuk Pantauan Live. Ditampilkan dengan label "prakiraan statistik, bukan peringatan" |
| M13 | 5 role: PUBLIC, USER, ANALYST, DATA_ENGINEER, ADMIN; masing-masing dipetakan ke role PostgreSQL | Requirement akses + RM4 |
| M14 | `SET LOCAL ROLE` per request (K5) | GRANT/REVOKE benar-benar berlaku, bukan sekadar dokumentasi |
| M15 | Audit trigger JSONB + `user_activity_logs` (K6) | Perubahan lewat aplikasi maupun psql tercatat |
| M16 | Acknowledge alert dan CRUD kejadian bencana: ANALYST + ADMIN | Keputusan Q2 |
| M17 | Kekeringan tanpa alert, hanya indikator (K8) | Defisit butuh normal klimatologis 30 tahun |
| M18 | Laporan mingguan + bulanan PDF, dibuat otomatis oleh scheduler; dua jenis: Hidromet (ANALYST) dan Kesehatan Data (DATA_ENGINEER) | Permintaan pembimbing + Q4 |
| M19 | Peta perubahan air S1 per scene Live (hijau surut, merah baru, biru tetap) | Q7; membaca backscatter mentah sulit bagi relawan |
| M20 | JWT di cookie HttpOnly, kedaluwarsa 8 jam, tanpa refresh token (K11) | Sederhana; frontend satu origin |
| M21 | UI Bahasa Indonesia; kode, API, pesan error API, dan log Bahasa Inggris (Q8) | Pengguna akhir relawan lokal |
| M22 | Scheduler dijaga PostgreSQL advisory lock | Menutup celah D7 DataLab (N worker = N cron) |
| M23 | Soft delete untuk data historis (`is_valid`/`deleted_at`) (D9) | Data historis tidak boleh hilang |
| M24 | Admin "CRUD scene" = lihat, proses ulang, soft delete/pulihkan, picu ingestion rentang tanggal; **tanpa** tambah scene manual | Scene manual merusak lineage |
| M25 | Ingestion hanya lewat API resmi (D14) | Legalitas dan stabilitas |
| M26 | Tile MODIS **h28v09** untuk Banten (D17, koreksi dari h30v08) | Verifikasi sinusoidal: lat −6,8°, lon 106° |
| M27 | `regions_of_interest` DataLab dipertahankan sebagai tabel AOI dataset, tetapi baris baru hanya boleh dibuat dari kecamatan atau gabungan kecamatan | FK di seluruh kode DataLab; refactor penuh terlalu mahal |
| M28 | Hari hujan = hari UTC (07.00–07.00 WIB) | Sesuai granule IMERG harian dan konvensi pengamatan BMKG |
| M29 | **Rekomendasi DBMS berbasis benchmark**: skrip `benchmark/` membandingkan PostgreSQL+PostGIS vs MySQL 8 pada 5 kueri inti + 3 fitur keamanan; MongoDB dinilai dari fitur | Hasil akhir wajib "Rekomendasi DBMS" butuh tahap evaluasi produk yang terukur |
| M30 | **Perbaikan integritas warisan**: `data_products.nasa_scene_id` + CHECK tepat satu sumber; baris palsu `NASA_AUX_*` dihapus | Produk MODIS/GPM tidak boleh tercatat seolah berasal dari scene S1 |
| M31 | **`live_scenes.metrics` dinormalkan** menjadi `live_scene_metrics` | Data yang dikueri untuk grafik/prakiraan harus 1NF |
| M32 | Array/JSONB konfigurasi (`parameters`, `quality_settings`, `fusion_grid`, `preview_options`, `processing_levels`, `s1_product_ids`) dipertahankan; di model logikal digambar sebagai entitas terpisah, di physical design didokumentasikan sebagai penerjemahan ke tipe PostgreSQL | Tahap "menerjemahkan model logikal untuk target DBMS"; refaktor penuh tidak sebanding |
| M33 | **Token API pribadi** (`api_tokens`, header `Authorization: Bearer`) untuk developer/skrip | Hasil akhir "Middleware/API Database (API Developer)" |
| M34 | Skema final satu berkas `monitor_schema.sql` (bukan rantai 26 migrasi DataLab); setiap tabel & kolom punya `COMMENT ON`; kamus data dan ERD fisik dibangkitkan dari katalog DB | Rancangan database selalu sama dengan DB nyata |
| M35 | Artefak uji di repo: pytest fitur baru, skrip matriks GRANT, skrip recoverability; tag prototipe `v0.1` (iterasi GMLS) dan `v1.0` | Bukti tahap prototyping dan testing yang bisa diulang |
| M36 | Impor BNPB DIBI **opsional**; `disaster_events` diisi dari catatan GMLS + input Analyst | Syarat ≥100 record transaksi sudah dipenuhi tabel lain; DIBI hanya memperkuat evaluasi alert |
| M37 | `product_tier_enum` hanya nama D14; nama BRONZE/SILVER/GOLD/FUSION hanya diterima sebagai input | Skema dibangun dari nol; literal lama di klausa SQL akan gagal |
| M38 | M30 diperluas ke `processing_jobs` (jangkar scene **atau** granule **atau** tanpa jangkar untuk FUSION); FUSION didedup per berkas; `DeletionManager` menghapus produk MODIS/GPM/FUSION dataset | Tanpa placeholder, job & produk aux butuh jangkar baru |
| M39 | Deskriptor teks metrik Live disimpan di `live_scenes.source_status[sumber].meta` | Bukan metrik numerik dan tidak dikueri |
| M40 | Ambang QA hanya dari `quality_thresholds`; ambang per dataset di wizard dihapus | Satu sumber kebenaran, diubah ADMIN |
| M41 | `alert_rules.threshold_value` boleh NULL selama aturan nonaktif | Ambang longsor belum tersedia |
| M42 | Rentang `spectral_bands` = batas fisik (rekor dunia), bukan nilai lazim | Trigger rentang hanya menolak data rusak |
| M43 | Prakiraan Live maksimal 4 langkah walau retensi sampai 60 | Ekstrapolasi SES/Holt jauh ke depan tidak bermakna |
| M44 | Nama DB default `themonitor`; database uji dibangun dari ketiga berkas SQL | Keputusan pemilik; skema selalu teruji |
| M45 | Hapus fisik dataset dan Live Area dikerjakan pipeline (`monitor_etl`, D pada `datasets`/`data_products`/`processing_jobs`); API hanya memeriksa pembuat/ADMIN dan menandai `DELETING` | Role interaktif tetap tanpa D sesuai matriks §8.3; kerja berkas memang milik pipeline |
| M46 | Akses `users`/`api_tokens` sebelum role diketahui hanya lewat fungsi SECURITY DEFINER `auth_*`; sandi role LOGIN diisi dari `.env`, tidak ditulis di SQL | Login, cek sesi, token, dan ganti sandi butuh hak yang tidak dimiliki role pemanggil |
| M47 | Audit trigger mengabaikan perubahan yang hanya menyentuh kolom pembukuan (login, `last_used_at` token, progres pipeline, siklus Live) | Tanpa ini `audit_log` dibanjiri baris otomatis dan perubahan bermakna sulit ditemukan |
| M48 | Setiap request bertoken dicatat satu baris (`API_REQUEST` atau `DOWNLOAD_*`); `bytes_sent` = byte yang benar-benar terkirim | M33 "setiap pemakaian token tercatat" + log unduhan RM4 |
| M49 | Scene Live untuk selain ADMIN: ≤ 30 hari + scene terbaru; `/storage/*` ADMIN; `/scenes?source=` default S1 | Melengkapi aturan §3.1 untuk endpoint warisan yang tidak disebut dokumen |

---

## 8. Anti Over-Engineering

Setiap fitur harus lolos salah satu uji: (1) menjawab RM1–RM4, (2) syarat eksplisit tahap DBSDLC, atau (3) requirement role yang disepakati.

**Sengaja tidak dibangun:** prediksi machine learning, OAuth/SSO, refresh token, notifikasi SMS/WhatsApp/email, mobile app, containerization, caching layer, load balancing, integrasi data warga SIGAP DESA, penggabungan dataset lintas AOI, reference layers.

**Utang teknis warisan yang diterima, tidak diperbaiki:** footprint S1 belum tercatat akurat (DataLab D17), dicatat sebagai keterbatasan. (Baris placeholder `NASA_AUX_*` **diperbaiki**, lihat M30.)

Usulan fitur baru dicatat di sini beserta alasan diterima atau ditolak.

---

## 9. Setup

### Kebutuhan

- Python 3.10+, PostgreSQL 14+ dengan PostGIS 3+
- RAM 8 GB (16 GB disarankan), disk 100 GB+ untuk arsip 3 tahun (lihat PIPELINE.md §9)
- Akun Copernicus Data Space + token NASA Earthdata

### Langkah

```bash
# 1. Clone dari DataLab, lalu terapkan perombakan sesuai dokumen ini
git clone <repo-datalab> orbit-u-monitor && cd orbit-u-monitor
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Basis data (skema Monitor menggantikan schema.sql + migrations DataLab)
createdb themonitor
psql themonitor -c "CREATE EXTENSION postgis; CREATE EXTENSION pgcrypto;"
psql themonitor -f database/monitor_schema.sql     # DDL + index + VIEW
psql themonitor -f database/monitor_security.sql   # role, GRANT, trigger audit
psql themonitor -f database/monitor_seed.sql       # master data
psql themonitor -c "ALTER ROLE monitor_app PASSWORD '...'; ALTER ROLE monitor_etl PASSWORD '...';"
# (PowerShell: python database/apply_schema.py — menjalankan ketiga berkas
#  lalu mengisi sandi kedua role dari .env; jadi isi .env dulu, langkah 3)

# 3. .env (salin .env.example, isi DB_* (pemilik skema, hanya untuk setup),
#    MONITOR_APP_PASSWORD, MONITOR_ETL_PASSWORD, JWT_SECRET (>= 32 karakter),
#    COPERNICUS_*, NASA_EARTHDATA_TOKEN). API terkoneksi sebagai monitor_app,
#    scheduler/pipeline sebagai monitor_etl — tidak pernah sebagai superuser.
cp .env.example .env

# 4. Wilayah COD-AB level 3 (Kabupaten Lebak) → administrative_regions
python scripts/load_regions.py --shp idn_admbnda_adm3_bps_20200401.shp --adm2-pcode <pcode Lebak>

# 5. Admin pertama
python scripts/create_admin.py --username admin

# 6. Backfill hidromet harian 2023–2025 (GPM + MODIS → region_observations)
python scripts/backfill_hydromet.py --start 2023-01-01 --end 2025-12-31

# 7. Jalankan
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Nama DB `sentinel1_flood` warisan DataLab **diganti** menjadi `themonitor` di `.env.example`, `etl/config.py`, dan `database_client.from_env()`.

---

## 10. Peta Dokumen

| File | Isi |
|---|---|
| `README.md` | Dokumen ini |
| `DATABASE.md` | DBMS selection, ERD, master & transaksi, DDL, normalisasi, index, VIEW, role & GRANT, audit |
| `PIPELINE.md` | Job hidromet, siklus Live, job dataset, laporan, storage, scheduler, QC, lineage, initial loading |
| `INTERFACE.md` | Halaman per role, endpoint API, kontrak request/response, UML, rencana pengujian |
