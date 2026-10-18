# Orbit-U: The Monitor

> **STATUS: FINAL v1.0 (1 Oktober 2026)** — pedoman tunggal pengembangan. Perubahan setelah ini dicatat di Decisions Log (§7) dengan ID baru, bukan dengan menimpa entri lama.

Sistem basis data monitoring hidrometeorologi dan arsip kejadian bencana untuk **Gugus Mitigasi Lebak Selatan (GMLS)**, Kecamatan Bayah, Kabupaten Lebak, Banten. Dibangun dengan meng-*clone* **Orbit-U: The DataLab** dan merombaknya, bukan dari nol.

**Judul skripsi:** Perancangan Sistem Basis Data Monitoring Hidrometeorologi untuk Dukungan Mitigasi Bencana Lebak Selatan Berbasis Satelit Sentinel-1, MODIS, dan GPM.

---

## 1. Ringkasan

| Sumber | Produk | Resolusi | Temporal | Penyedia |
|---|---|---|---|---|
| Sentinel-1 (S1A, S1C, S1D) | GRD IW, VV + VH | ~10 m | per lintasan (6–12 hari, tergantung jumlah satelit aktif) | ESA / CDSE |
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

Susunan halaman M56 (+M63): Beranda (Pantau Lokasi) → Tentang → 3D AOI → Citra Satelit → Forecast (dulu Diagram, M61) → Kejadian → Data → Laporan → Sistem, plus Masuk (`/masuk`) dan Registrasi (`/daftar`).

| Role | Akun | Kebutuhan |
|---|---|---|
| `PUBLIC` | Tanpa akun | Beranda (pilih kecamatan; angka per kecamatan **30 hari terakhir**, M63), Tentang, Citra Satelit **30 hari terakhir** (termasuk PDF), Kejadian **365 hari terakhir** |
| `USER` | Registrasi mandiri `/daftar` | Semua milik PUBLIC + 3D AOI, Citra **365 hari**, seluruh riwayat kejadian, hujan per kecamatan + alert aktif, akun & token API sendiri, Lokasi saya (M63), peringatan email per kecamatan pilihan (opsional, M64) |
| `ANALYST` | Dibuat ADMIN | Semua milik USER + Citra semua tanggal, Forecast (semua band 30 hari + forecast 15 hari, analisa daerah + forecast + PDF, tren & evaluasi alert), kelola kejadian, acknowledge alert, Laporan Keadaan AOI, log halaman Kejadian |
| `DATA_ENGINEER` | Dibuat ADMIN | Semua milik USER + Citra semua tanggal, Data (per satelit + backfill dengan log, unduh/fusion, dataset, proses, EDA), Laporan Kesehatan Data, log halaman Data |
| `ADMIN` | Dibuat ADMIN | Semua akses + Sistem › Manajemen akun, Pengaturan aplikasi, seluruh log (masuk/registrasi, unduhan, audit) |

Matriks rinci per halaman dan endpoint: INTERFACE.md §3. Batas waktu per peran ditegakkan di VIEW (`v_citra_scenes`, `v_public_kejadian`), bukan hanya di menu. Penegakan di basis data: DATABASE.md §8.

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

### Tiga tempat data (M58)

| | Isi | Diisi oleh | Umur |
|---|---|---|---|
| **Dataset utama** (`HYDROMET_AOI` + Live Area AOI) | Satu deret waktu per sumber: GPM & MODIS **harian**, Sentinel-1 **per lintasan** (VV, VH, WATER_PCT), semuanya per kecamatan di `region_observations`; raster COG + gambar scene di filesystem | Backfill dan operasi harian adalah job yang sama: Job Hidromet (GPM/MODIS) dan siklus Live (S1). Live mengambil GPM/MODIS dari Job Hidromet (hardlink), tidak mengunduh ulang | **Raster: 1 tahun bergulir** (`storage.raster_retention_days` = 365), lebih tua dihapus otomatis. **Angka per kecamatan dan metrik scene: disimpan selamanya** |
| **Tampilan Live** | Kartu + prakiraan dari N scene S1 terbaru (`live_areas.retention`, 1–60) | Membaca dataset utama | Tidak menghapus apa pun |
| **Dataset historis** (Katalog Dataset) | Dataset buatan DATA_ENGINEER: rentang, sumber, fusion bebas, termasuk lebih dari 1 tahun ke belakang | Wizard Katalog; granule yang sudah ada di dataset lain dipakai ulang (hardlink), selebihnya diunduh dari arsip resmi | Sampai dihapus pemiliknya |

Grafik, statistik, alert, dan laporan hanya membaca dataset utama, sehingga rentang tanggal di semua halaman sama.

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
| Landing page berbahasa Inggris | Diganti halaman publik berbahasa Indonesia (`/`) |

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
| Middleware / API Database (API Developer) | REST API + token API pribadi + OpenAPI `/docs` |
| Prasyarat master ≥ 10, transaksi ≥ 100 | 12 master; `region_observations` ±79.000 baris |
| Testing 5 kriteria | `tests/`, `tests/security/grant_matrix.sql`, `tests/recovery/` |

---

## 6. Keterlacakan ke Rumusan Masalah

| RM | Dijawab oleh |
|---|---|
| RM1 — basis data relasional terintegrasi untuk ingestion 3 satelit | Skema master/transaksi, `satellite_scenes`/`nasa_scenes`, `region_observations`, `fusion_products`, job hidromet + Live + dataset |
| RM2 — lineage + quality metrics | `data_lineage` (SHA-256 input/output), `processing_jobs.parameters`, `quality_metrics`, `quality_thresholds`, `v_ringkasan_kualitas`, Laporan Kesehatan Data |
| RM3 — dashboard + API user-friendly | Halaman publik, Beranda, Kondisi, Riwayat, Kejadian, Data, Pengaturan, REST API (susunan M53) |
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
| M11 | Live Monitoring diwariskan; retensi scene diatur Admin (1–60, default 6); maksimal 5 Live Area. **Diubah M58:** angka 1–60 kini hanya jumlah scene di kartu & prakiraan; berkas disimpan menurut umur | Pengguna melihat beberapa scene + forecast; batas atas menjaga disk |
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
| M50 | **Design system Orbital 95** (`DESIGN.md`) menggantikan design system DataLab (glassmorphism, navbar pil, toast): jendela berbevel + taskbar dengan menu **Mulai** per role, data di "layar CRT", dialog modal untuk semua pesan; UI tetap vanilla JS + Leaflet tanpa build. Kode error API diterjemahkan di `web/js/ui.js` | Keputusan pemilik proyek Tahap 4; satu bahasa visual "kontrol abu-abu, data di layar gelap" |
| M51 | Tambahan API aditif untuk UI Tahap 4: `scene.water_change` pada kartu Live, `by_rule` pada `/alerts/evaluation`; batas 366 hari dataset ditegakkan juga di API; path preview Live dicari koneksi etl setelah scene terbukti terlihat role pemanggil | INTERFACE §2.2/§2.4/§2.6 butuh angka/aturan yang belum diekspos; USER/ANALYST tidak boleh membaca `datasets` (§8.3) |
| M52 | Uji UI berbasis browser headless (CDP) terhadap DB terpisah `themonitor_dev` dengan akun sintetis `uji_<role>`: `tests/ui/screenshots.py` (3 lebar × 12 halaman × role) dan `tests/ui/flows.py` (alur tulis); bukan bagian pytest | Bukti tahap prototyping/testing DBSDLC tanpa menyentuh DB produksi dan tanpa memicu unduhan |
| M53 | **Susunan halaman dirombak menurut pertanyaan pengguna, bukan pembagian tabel** (INTERFACE.md §2). Sembilan menu → **lima tujuan + Beranda**, diurut menurut waktu (sekarang → masa lalu → arsip → sistem): `#beranda`, `#kondisi` (tab `citra` + `kecamatan`), `#riwayat` (tab `grafik` + `laporan`), `#kejadian`, `#data` (tab `daftar` + `buat`), `#pengaturan`. Dua halaman publik (`/` dan `/kondisi`) jadi satu; `/kondisi` dialihkan 301, dan tile pindah ke bagian terakhir `/` sehingga urutan sambutan → penjelasan → navigasi tetap utuh. Administrasi: 12 tab rata → 5 kelompok dengan tab **Ringkasan** sebagai pintu masuk. Tambahan: menu bar di bawah title bar, satu baris instruksi (`lede`) per tujuan/tab, "Akun Saya" pindah ke tray. Hash lama tetap hidup lewat `Shell.ALIASES`; DESIGN.md tidak berubah | Susunan lama mewarisi pemisahan DataLab: satu pertanyaan ("bagaimana kondisi sekarang?") dijawab dua halaman karena sumber datanya berbeda tabel, daftar dan pembuatnya jadi dua menu, dan alert aktif — informasi terpenting — hanya terlihat bila pengguna kebetulan membuka Statistik Hari Ini. 33 tujuan navigasi untuk organisasi dengan <10 akun; sembilan label dengan sembilan pola penamaan. Perender tiap halaman tidak ditulis ulang (kontrak `Pages[x].init/destroy` dipertahankan), hanya cara masuknya |
| M54 | **Dua halaman publik tetap terpisah**, mengoreksi klausa halaman publik pada M53: `/` adalah Beranda publik (sambutan → penjelasan → navigasi halaman, plus strip satu baris status area) dan `/kondisi` adalah Kondisi Terkini (tile satelit). Pengalihan 301 dibatalkan; `web/kondisi.html`, `pages/home-public.html`, dan `js/home-public.js` dipulihkan. Susunan di dalam aplikasi (lima tujuan + Beranda) tidak berubah | Keputusan pemilik proyek. Pengunjung yang belum tahu apa pun tentang sistem ini perlu pengantar — sambutan, penjelasan, lalu navigasi — sedangkan yang sudah tahu bisa langsung ke `/kondisi`. Menggabung keduanya memaksa satu urutan untuk dua kebutuhan yang berbeda |
| M55 | **Relief 3D**: pratinjau scene Live ditempel sebagai tekstur di atas DEM dengan kamera 3D MapLibre (`pages/terrain3d.html` + `js/terrain3d.js` + `css/terrain3d.css`), sebagai tab `#kondisi/relief` **dan** halaman publik `/relief` — satu fragmen dan satu skrip, mode dipilih dari `body[data-requires-auth]`. DEM dari AWS Terrain Tiles (terrarium, turunan SRTM, ~30 m, tanpa kunci API); MapLibre dimuat dari CDN hanya saat halaman ini dibuka. Georeferensi preview disimpan sebagai **empat sudut lon/lat** di `live_scenes.previews.grid` (`module10.grid_corners_wgs84`) dan diekspos di kartu Live serta `/api/public/live`; scene lama diisi `scripts/backfill_preview_grid.py`, yang menolak menulis kalau ukuran grid tidak cocok dengan PNG di disk. Leaflet tidak dipakai di halaman ini | Relief menjawab "di mana air ini sebenarnya" lebih langsung daripada citra datar, dan Leaflet tidak punya kamera 3D. Empat sudut, bukan bbox: extent grid milik SCENE, bukan AOI — scene satu frame menutupi AOI jauh lebih sempit daripada scene mosaik (area 1: 27 Sep 2026 membentang 105,86–106,17°, 4 Okt 2026 105,86–106,53°), jadi bbox daerah menggeser citra puluhan kilometer. Tinggi berasal dari DEM, **bukan** dari Sentinel-1 — GRD tidak mengukur elevasi, dan itu dikatakan di halamannya supaya tidak dibaca sebagai hasil ukur radar |
| M56 | **Susunan halaman v2 mengikuti rancangan pemilik proyek** (`DOCS/rancangan kasar.txt`, INTERFACE.md). Delapan halaman: Beranda, 3D AOI, Citra Satelit (ringkasan, Sentinel-1, MODIS, GPM, laporan PDF multi-halaman), Diagram (semua band 30 hari, analisa daerah + PDF semua band), Kejadian (lihat, kelola), Data (ringkasan, per satelit dengan backfill + log, unduh, tersimpan, proses, EDA), Laporan (otomatis + rentang bebas), Sistem (tentang, log per peran, akun, manajemen akun, pengaturan) + Masuk dan Registrasi. Aplikasi `/` = `/app` terbuka untuk pengunjung; menu dari `GET /api/auth/session`. **Registrasi mandiri** membuat USER lewat fungsi `auth_register_user` (peran dikunci di DB, `users.email` baru). Batas waktu: PUBLIC 30 hari citra / 365 hari kejadian, USER 365 hari, ANALYST/DATA_ENGINEER/ADMIN semua — ditegakkan di VIEW `v_citra_scenes`/`v_public_kejadian` dengan `pg_has_role(current_user, …)`. Kejadian: baca semua peran, tulis ANALYST (M16 tetap). Log per halaman lewat VIEW `v_log_data` (DATA_ENGINEER) dan `v_log_kejadian` (ANALYST). Soft delete scene pindah dari ADMIN ke DATA_ENGINEER. Hash dan halaman publik lama dialihkan; berkas halaman publik lama (`landing`, `home-public`, `kondisi.html`, `relief.html`, `index.html`) dan `monitoring` tidak lagi dirujuk. Migrasi DB berjalan: `database/migrations/m56_susunan_halaman_v2.sql` | Permintaan pemilik proyek. Batas M49 (selain ADMIN ≤ 30 hari) diganti; M53/M54 (susunan dan halaman publik) digantikan. Batas waktu di VIEW, bukan di API saja, supaya lapis 3 (M14) tetap berlaku untuk aturan baru |
| M57 | **Empat tema tampilan, Orbital 95 tetap bawaan.** Tiga konsep di `DOCS/design tambahan/` dijadikan tema: konsep38 → **Kertas Mint** (`mint`), konsep41 → **Mika Pasir** (`pasir`), konsep44 → **Piksel Marun** (`piksel`). Dipilih di Beranda (bagian *Tema tampilan*, `pages/home.html` + `js/home.js`), diterapkan `web/js/theme.js` sebagai `data-theme` di `<html>` sebelum `<body>` diurai, dan disimpan di `localStorage` (`orbit-u.tema`) per peramban, bukan per akun. CSS ada di `web/css/tema/`: `umum.css` (struktur bersama, tercakup `html.tema-alt`) + satu berkas per tema (tercakup `html[data-theme="…"]`) + `pilihan.css` (kartu pemilih). Hanya bahasa visual konsep yang diambil; struktur halaman, router, dan data tidak berubah, layar CRT menjadi panel terang dengan token `--crt/--phos/--amber/--alert/--cyan` per tema, dan rotasi kartu konsep hanya dipakai di kartu navigasi. Aturan DESIGN.md (siku, tanpa blur) tetap berlaku untuk Orbital 95 dan `css/*.css`; `css/tema/` dikecualikan dan diuji tercakup selektornya (`tests/test_web_ui.py`) | Permintaan pemilik proyek: konsep tambahan dipakai sebagai pilihan, bukan pengganti, dan harus disesuaikan dengan halaman asli. Menyimpan di peramban cukup karena tema tidak memengaruhi data atau akses, dan pengunjung tanpa akun juga bisa memilih |
| M58 | **Satu dataset utama, raster 1 tahun bergulir, angka selamanya** (8 Okt 2026). (1) Deret waktu per kecamatan `region_observations` memuat ketiga satelit: GPM/MODIS harian dari Job Hidromet, Sentinel-1 per lintasan (VV, VH dB rata-rata linear; WATER_PCT = % luas VH < `water.vh_threshold_db`) dari `etl/s1_observations.py` setiap kali scene Live lolos, di grid AOI ~100 m. (2) Siklus Live = backfill S1: discovery selalu melihat seluruh jendela raster (1 tahun), tanggal terbaru dulu, per 3 tanggal; GPM/MODIS tanggal scene diambil dari dataset utama (hardlink `_work`), bukan diunduh ulang. (3) `storage.raster_retention_days` = 365 (semula 730, diturunkan pemilik pada hari yang sama): COG/`_work` dataset utama dan berkas scene Live yang lebih tua dihapus (`etl/raster_retention.py` di akhir job harian, `LiveMonitor.enforce_retention`); `data_products.is_valid = false`, angka & metrik tetap. (4) `live_areas.retention` hanya jumlah scene di kartu & prakiraan. (5) Backfill S1 di halaman Data menjalankan siklus Live terbatas rentang (bukan lagi dataset Katalog); rentang yang seluruhnya > 1 tahun ditolak (`OUTSIDE_RASTER_WINDOW`) → pakai Katalog Dataset. Mempertegas M23: yang dihapus hanya berkas raster yang bisa diunduh ulang dari arsip resmi, bukan data historis. Skrip: `scripts/backfill_s1.py` | Sebelumnya chart (region_observations) berhenti di tanggal lain dari halaman Data (scene Live), S1 tidak punya riwayat, dan dua alur retensi saling tidak tahu. Angka per kecamatan berukuran beberapa MB per tahun, sedangkan raster S1 ±0,35 GB per lintasan |
| M59 | **Tekstur 3D AOI di-pad ke batas tile Mercator** (8 Okt 2026): PNG pratinjau digambar lebih dulu ke kanvas yang extent-nya persis satu tile Mercator yang memuatnya (sisanya transparan, pemetaan piksel→Mercator afin dari tiga sudut agar grid bersudut miring ikut benar), dan kanvas itu — bukan extent citra — yang dipasang sebagai `image` source. `containingTile`/`tileAlignedCanvas` di `web/js/terrain3d.js`, diekspos sebagai `Pages.terrain3d._geo` dan diuji `tests/ui/tile_alignment.html` lewat `chrome --headless=new --dump-dom` (kasus AOI nyata + 400 extent acak, tanpa server/DB/jaringan) | MapLibre menggambar satu `image` source di dalam SATU tile, dipilih `getCoordinatesCenterTileID()`: zoom = `floor(-log2(sisi terpanjang citra))`, lalu tile yang memuat TITIK TENGAH citra. Tile sebesar citra tidak berarti memuat citra — untuk AOI Lebak (105,86–106,53°E) 46,6% lebar sisi barat jatuh di luar tile dan dipotong; dilaporkan pengguna sebagai "AOI hilang setengah saat di-zoom". Masih berlaku di MapLibre `main` (diperiksa Okt 2026) dan `loadTile()` hanya menerima tile itu, jadi bukan bug yang bisa ditunggu perbaikan hulunya. Pindah ke tile server raster juga menyelesaikannya, tapi menuntut backend baru; pad di klien tidak menyentuh PNG yang dipakai tile 2D sama sekali |
| M60 | **DATABASE.md, PIPELINE.md, DESIGN.md ditulis ulang dari kode** (8 Okt 2026). Versi lama sengaja dihapus pemilik proyek karena sudah tidak sesuai kode. Nomor bagian disusun mengikuti rujukan `§` yang sudah ada di kode, supaya rujukan itu tetap benar. Kode adalah sumber kebenaran; bila berbeda, dokumen yang diperbaiki. Dua docstring usang ikut dibetulkan: `etl/raster_retention.py` (730 → 365 hari, sesuai M58) dan `tools/data_dictionary.py` (catatan `docs/generated/`) | Dokumen lama yang tidak sesuai kode membingungkan pengembangan; bagian skripsi butuh artefak tahap DBSDLC |
| M61 | **Halaman Diagram menjadi Forecast** (9 Okt 2026). Semua fitur Diagram dipertahankan; setiap grafik garis (Keadaan terbaru, Analisa daerah, serta CH-01 tren per kecamatan dan CH-03 rerata hujan di Tren & evaluasi alert) kini juga menampilkan forecast 15 hari dengan pita 80%, menyala bawaannya dan bisa dimatikan lewat sakelar di bawah grafik. Forecast dihitung dari **seluruh riwayat** deret di database (bukan hanya 30 hari yang digambar) oleh `etl/band_forecast.py`: lima model numpy (naive, SES, Holt teredam, klimatologi, klimatologi + anomali AR(1)) dipilih per deret lewat backtest rolling-origin setahun. Dipilih atas ARIMA/Prophet karena: tanpa dependensi baru (Prophet sulit dipasang di Windows, statsmodels tidak terpasang), data harian GPM/MODIS sejak Jan 2024 cukup untuk pola musiman, dan backtest membuktikan per deret apakah model mengalahkan "nilai terakhir berlanjut" — hasil uji pada data nyata: model musiman menang untuk akumulasi hujan dan genangan MODIS (skill 0,2–0,3), sedangkan NDVI/NDWI/Sentinel-1 berubah terlalu lambat untuk dikalahkan naive dalam 15 hari, dan UI menyatakannya sebagai keyakinan rendah. Endpoint `GET /api/diagram/forecast` satu deret per request supaya palang progres jujur; grafik data tampil lebih dulu. Hash `#diagram/…` dialihkan ke `#forecast/…`; path API `/api/diagram/*` dan izin `diagram.view` tidak diganti supaya peran, token, dan GRANT yang ada tetap berlaku | Diminta pemilik proyek: fitur Diagram ditingkatkan menjadi forecasting tanpa membuang yang sudah ada |
| M62 | **Forecast dihitung saat data baru masuk dan disimpan** (9 Okt 2026). Sebelumnya (M61) forecast dihitung saat halaman dibuka dan hanya disimpan di memori proses: hilang saat server restart, dihitung ulang per worker, pengunjung pertama menunggu, dan tidak ada jejak model mana yang dipakai kapan. Sekarang `etl/forecast_store.py` menghitung 110 deret (10 band × rerata AOI + 10 kecamatan) di akhir Job Hidromet, backfill, dan setiap siklus Live, plus job `forecast_refresh` tiap 6 jam sebagai jaring pengaman, di bawah advisory lock `forecast`. Deret dilewati bila **cap data** bandnya tidak berubah. Hasil disimpan di tiga tabel 1NF: `band_forecasts`, `band_forecast_points`, `band_forecast_scores` (riwayat 365 hari). API membaca tabel itu dan hanya menghitung di tempat untuk rentang di masa lalu atau rerata beberapa kecamatan. Terukur: hitung penuh 5,6 s, panggilan tanpa data baru 0,1 s, API 2–17 ms per deret (sebelumnya 25–66 ms). Migrasi `database/migrations/m62_band_forecasts.sql`. Rumus lengkap di PIPELINE.md §14 | Diminta pemilik proyek: forecast harus efisien dan bisa ditelusuri, bukan dihitung ulang setiap halaman dibuka |
| M63 | **Beranda menjadi Pantau Lokasi; isi Beranda lama menjadi menu Tentang** (16 Okt 2026). Beranda = landing singkat → Pantau lokasi. **Lokasi saya** hanya untuk pengguna yang sudah masuk: bila izin lokasi diberikan dan titik perangkat jatuh di kecamatan AOI, panel kecamatan itu tampil lebih dulu. Pengunjung, perangkat di luar wilayah, izin ditolak, atau peramban tanpa lokasi langsung ke **Informasi lokasi** (daftar + peta kecamatan berwarna status), dan pilihan di sana mengganti kecamatan yang dipantau. Panel pantau: kalimat kondisi + apa yang tidak normal (`etl/lokasi_interpret.py`, ambang tetap dari `etl/live_interpret.py`; setiap kalimat tidak normal dan alert hujan 7 hari ikut menaikkan status), citra scene Live terbaru **dipotong ke kecamatan** (`etl/region_crop.py`, georeferensi `previews.grid`, cache `data/_lokasi_cache`), angka terbaru + rentang biasa (persentil 2–98 setahun) + tren 30 hari. **Angka per kecamatan dibuka ke PUBLIC** lewat VIEW `v_public_lokasi_obs` (30 hari; dua observasi terakhir per band selalu terlihat), `v_public_lokasi_range`, `v_public_lokasi_alert` (tanpa kolom penanganan); USER tetap 365 hari. Endpoint `/api/public/lokasi…`. Geolokasi di `web/js/geo.js`: koordinat tidak dikirim ke server, izin tidak pernah diminta saat halaman dibuka (otomatis hanya bila sudah `granted`), butuh HTTPS. Tentang (`#tentang`) = sambutan, penjelasan, kartu halaman, tema, peta AOI, info aplikasi, sumber data; tab Sistem › Tentang dihapus dan `#sistem/tentang` dialihkan. Alert hujan aktif tidak lagi di halaman pertama sebagai tabel AOI, tetapi per kecamatan (lencana + kalimat). Migrasi DB berjalan: `database/migrations/m63_pantau_lokasi.sql` | Permintaan pemilik proyek: halaman pertama menjawab "bagaimana kondisi di lokasi saya", bukan menjelaskan aplikasi. Membuka angka per kecamatan ke pengunjung mengubah batas M56 (per kecamatan USER+): yang dibuka hanya 30 hari terakhir, sama dengan batas citra publik, dan ditegakkan di VIEW supaya lapis 3 (M14) tetap berlaku. Pencocokan titik di browser, bukan di server, supaya lokasi pengguna tidak pernah tercatat di log API |
| M64 | **Peringatan email kondisi tidak normal per kecamatan** (19 Okt 2026). **Email dan kecamatan sama-sama opsional**; tanpa salah satunya pengguna tidak menerima peringatan dan tidak ada yang rusak. Email registrasi tidak lagi wajib (mengubah M56). Email disimpan hanya bila lolos pengecekan (`etl/mailer.py`): format, belum dipakai akun lain, domain punya server mail (MX via dnspython), dan email konfirmasi **berhasil dikirim**; gagal = tidak disimpan. Berlaku di Akun saya, registrasi, dan form akun Admin. Kecamatan: tidak ada, beberapa, atau semua (`users.notify_all_regions`, termasuk kecamatan yang ditambahkan kemudian) di `user_notify_regions`. Job `etl/notify.py` jalan setelah Job Hidromet harian dan siklus Live (dan tombol Admin): butir tidak normal dihitung dengan aturan Beranda (`etl/lokasi_data.py`, dipindah dari router agar API dan job memakai pembaca yang sama), dikirim bila tanggal datanya ≤ `notify.max_age_days` (7) hari dan belum ada di `notify_sent` (kunci pengguna × kecamatan × butir × tanggal data) — **setiap data baru yang tidak normal dikirim, data yang sama tidak pernah dua kali**, backfill lampau tidak memicu. Satu email per pengguna per putaran; isi berlapis untuk awam dan analis (Ringkasnya → Bukti: citra dipotong ke kecamatan inline + tabel nilai/ambang/rentang biasa → Detail teknis). `monitor_etl` membaca email hanya lewat `notify_recipients()`. SMTP dari `.env` (`MAIL_*`, standar library `smtplib`); `MAIL_BACKEND=file` menulis `.eml` tanpa mengirim, dan `tests/conftest.py` selalu memakainya. Migrasi DB berjalan: `database/migrations/m64_peringatan_email.sql` | Permintaan pemilik proyek: pengguna perlu tahu tanpa membuka aplikasi bahwa kecamatannya tidak normal, lengkap dengan bukti. Membatalkan butir "notifikasi email" di §8. Pengecekan sengaja sederhana (tanpa tautan verifikasi) atas permintaan pemilik; batasnya — kotak surat yang tidak ada di domain valid baru ketahuan dari pantulan — dicatat di INTERFACE.md. Kunci anti-duplikat per tanggal data, bukan per putaran job, karena siklus Live menghitung ulang semua scene empat kali sehari |
---

## 8. Anti Over-Engineering

Setiap fitur harus lolos salah satu uji: (1) menjawab RM1–RM4, (2) syarat eksplisit tahap DBSDLC, atau (3) requirement role yang disepakati.

**Sengaja tidak dibangun:** prediksi machine learning, OAuth/SSO, refresh token, notifikasi SMS/WhatsApp (email **dibangun** sejak M64: peringatan kondisi tidak normal per kecamatan, opsional per pengguna), mobile app, containerization, caching layer, load balancing, integrasi data warga SIGAP DESA, penggabungan dataset lintas AOI, reference layers.

**Utang teknis warisan yang diterima, tidak diperbaiki:** footprint S1 belum tercatat akurat (DataLab D17), dicatat sebagai keterbatasan. (Baris placeholder `NASA_AUX_*` **diperbaiki**, lihat M30.)

Usulan fitur baru dicatat di sini beserta alasan diterima atau ditolak.

---

## 9. Setup

### Kebutuhan

- Python 3.10+, PostgreSQL 14+ dengan PostGIS 3+
- RAM 8 GB (16 GB disarankan), disk 100 GB+ (raster 1 tahun ±16 GB S1 + <1 GB GPM/MODIS; ruang kerja unduhan S1 ±2 GB per lintasan selama diproses)
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

# 4. Wilayah COD-AB adm2 + adm3 (Kabupaten Lebak, ID3602) → administrative_regions,
#    lalu kecamatan AOI GMLS → ROI AOI, dataset sistem HYDROMET_AOI, Live Area default.
#    Shapefile default: data/external/cod-ab-idn/idn_admin{2,3}.shp
python scripts/load_regions.py --aoi "Banjarsari,Wanasalam,Cijaku,Malingping,Cihara,Cigemblong,Panggarangan,Bayah,Cibeber,Cilograng"

# 5. Admin pertama
python scripts/create_admin.py --username admin

# 5b. DB yang sudah berjalan sebelum M56 (langkah 2 sudah memuatnya untuk DB baru):
#     users.email, VIEW per peran, GRANT baru, fungsi registrasi. Idempoten.
python database/apply_schema.py --migrate m56_susunan_halaman_v2.sql

# 6. Backfill dataset utama 1 tahun terakhir (M58). Keduanya bisa dihentikan
#    dan dijalankan ulang; tanggal yang sudah selesai dilewati.
#    GPM + MODIS harian → region_observations → alert_events:
python scripts/backfill_hydromet.py --from <hari ini - 365> --to <kemarin>
#    Sentinel-1 per lintasan (siklus Live; VV/VH/WATER_PCT per kecamatan):
python scripts/backfill_s1.py

# 6b. (opsional) Catatan kejadian dari CSV terstruktur
python scripts/import_disasters.py kejadian.csv --username <analis>

# 7. Jalankan
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

**Email peringatan (M64).** Isi `MAIL_*` di `.env` (contoh di `.env.example`). Untuk Gmail:
aktifkan Verifikasi 2 Langkah, lalu buat **Sandi aplikasi** di myaccount.google.com/apppasswords. Isi
`MAIL_PASSWORD` dengan sandi aplikasi itu (16 huruf tanpa spasi), bukan sandi akun Google. Kuota Gmail
biasa ±500 penerima per hari. Isi juga `APP_BASE_URL` supaya email memuat tautan ke Beranda dan Akun saya.
Coba tanpa mengirim apa pun:

```
python -m etl.notify --once --to-file        # .eml ke logs/mail
python -m etl.notify --test alamat@anda.id   # satu email uji sungguhan
```

Tanpa `MAIL_*`, email pengguna tidak bisa disimpan dan tidak ada peringatan; bagian lain aplikasi tetap
jalan. Peringatan dimatikan sementara lewat `notify.enabled` di Pengaturan aplikasi.

**HTTPS untuk produksi (M63).** "Lokasi saya" di Beranda memakai Geolocation API,
yang hanya ada di konteks aman: HTTPS, atau `http://localhost` saat
pengembangan. Diakses lewat `http://<IP-LAN>:8000` dari ponsel, peramban
menolak lokasi tanpa bertanya dan Beranda langsung ke Informasi lokasi.
Pasang reverse proxy ber-TLS (nginx, Caddy, atau Cloudflare Tunnel) di depan
uvicorn. Proxy itu **tidak boleh** mengirim `Permissions-Policy: geolocation=()`;
bila header itu diatur, pakai `geolocation=(self)`.

Nama DB `sentinel1_flood` warisan DataLab **diganti** menjadi `themonitor` di `.env.example`, `etl/config.py`, dan `database_client.from_env()`.

---

## 10. Peta Dokumen

| File | Isi |
|---|---|
| `README.md` | Dokumen ini |
| `DATABASE.md` | Perencanaan (mission, user views, 5W1H), ERD konseptual, master & transaksi, normalisasi, index, VIEW, role & GRANT, RLS, audit (M60) |
| `PIPELINE.md` | Tier, Job Hidromet, siklus Live, dataset & fusion, laporan, scheduler & kunci, pemulihan, retensi, setup, `app_settings`, backup (M60) |
| `INTERFACE.md` | Susunan halaman M56, matriks akses per peran, endpoint baru/berubah, kode galat, pengujian |
| `rancangan kasar.txt` | Rancangan halaman dari pemilik proyek (sumber M56) |
| `DESIGN.md` | Design system Orbital 95 (token, bevel, komponen, layout) — sumber kebenaran visual tema bawaan (M50); tiga tema tambahan di `web/css/tema/` (M57) |
| `design tambahan/` | Konsep visual sumber tema Kertas Mint (konsep38), Mika Pasir (konsep41), Piksel Marun (konsep44) — M57 |
| `lampiran/` | Bukti penelitian untuk skripsi. `Instrumen_Lapangan_GMLS.pdf`: pitching, skrip wawancara, skenario UAT, kuesioner SUS (sumber yang bisa diedit: dokumen claude.ai). Hasil kunjungan (notulen, foto, legalitas, lembar terisi) disimpan di sini juga |
