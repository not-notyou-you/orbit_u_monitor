# INTERFACE — Orbit-U: The Monitor

> **STATUS: FINAL v1.0 (1 Oktober 2026).** Antarmuka pengguna (web) dan antarmuka program (REST API). Komponen berlabel **[WARIS]** mengikuti DataLab `INTERFACE.md`.

---

## 1. Prinsip

| Prinsip | Penjelasan |
|---|---|
| Bahasa | UI Bahasa Indonesia (label, pesan, tanggal `id-ID`, angka `1.234,5`). Kode, endpoint, field JSON, dan `detail` error API Bahasa Inggris; frontend menerjemahkan kode error ke pesan Indonesia (M21) |
| Teknologi | HTML/CSS/JS vanilla + Leaflet, tanpa build tooling [WARIS] |
| Design system | Palet, glassmorphism, navbar pil, toast, lightbox, ring progres [WARIS] |
| Prioritas informasi | Kondisi terbaru di atas, arsip di bawah |
| Peta latar | Esri World Street Map [WARIS] + poligon kecamatan AOI |
| Satu origin | Frontend disajikan FastAPI yang sama → cookie `SameSite=Strict`, tanpa CORS |

---

## 2. Halaman

| URL | Halaman | Akses minimum | Status |
|---|---|---|---|
| `/` | **Beranda Publik** | PUBLIC | [UBAH] dari landing page DataLab |
| `/masuk` | Masuk | PUBLIC | [BARU] |
| `/app#pantauan` | **Pantauan Live** | USER | [UBAH] dari Live Monitoring |
| `/app#hari-ini` | **Statistik Hari Ini** | USER | [BARU] |
| `/app#analitik` | **Analitik** | ANALYST | [BARU] |
| `/app#kejadian` | **Kejadian Bencana** | ANALYST | [BARU] |
| `/app#katalog` | **Katalog Dataset** | DATA_ENGINEER | [WARIS] Dataset Catalog |
| `/app#buat-dataset` | **Buat Dataset** | DATA_ENGINEER | [WARIS] wizard |
| `/app#laporan` | **Laporan** | ANALYST / DATA_ENGINEER | [BARU] |
| `/app#admin` | **Administrasi** (tab) | ADMIN | [BARU] |
| `/app#akun` | **Akun Saya** (ubah sandi, token API) | USER | [BARU] |
| `/docs` | Dokumentasi API (Swagger) | PUBLIC (baca); "Try it out" butuh token | [WARIS], diperluas |

Navbar hanya menampilkan halaman yang boleh diakses role pengguna; pengguna tidak login hanya melihat Beranda + tombol "Masuk".

### 2.1 Beranda Publik (`/`)

Tanpa login. Satu layar untuk "apa kondisinya sekarang".

```
┌ ORBIT-U · Pantauan Hidrometeorologi Lebak Selatan ─────────── [Masuk] ┐
│ [Status area: WASPADA]  Scene terakhir: 24 Sep 2026 (Sentinel-1)      │
│ "Menunjukkan curah hujan 72 jam dalam kondisi waspada karena …"       │
│ Diperbarui: hujan 30 Sep 2026 · MODIS 30 Sep · Sentinel-1 24 Sep      │
├───────────────────────────────────────────────────────────────────────┤
│ Sentinel-1    [VV] [VH] [Perubahan air]                               │
│ MODIS         [Banjir] [NDVI] [NDWI]                                  │
│ GPM           [24 jam] [72 jam] [7 hari]                              │
├───────────────────────────────────────────────────────────────────────┤
│ Penjelasan singkat tiga satelit · batasan data · kontak GMLS          │
└───────────────────────────────────────────────────────────────────────┘
```

- Sumber: `GET /api/public/live` (scene terbaru tiap Live Area aktif; bila >1 area, pemilih area).
- Tidak ada riwayat, grafik, forecast, unduhan, atau nilai per kecamatan.
- Klik tile → lightbox dengan legenda dan kalimat kondisi [WARIS].
- Catatan tetap di bawah: "Ini bukan peringatan dini resmi. Ikuti informasi BMKG dan BPBD."

### 2.2 Pantauan Live (`#pantauan`) — USER+

Kartu Live DataLab [WARIS] dengan perubahan:

| Komponen | Isi |
|---|---|
| Pemilih area | Live Area aktif |
| Header | Status area, kalimat, tanggal scene, status per sumber |
| Tile | 9 preview (8 warisan + **Perubahan air**) |
| Tanggal tersimpan | Scene dalam **30 hari terakhir** (USER); ADMIN melihat semua scene tersimpan |
| Grafik & prakiraan | S1 mean VH, luas air NDWI MODIS, hujan 72 jam GPM + garis ambang; prakiraan garis putus-putus berlabel "Prakiraan statistik, bukan peringatan" |
| Ringkasan perubahan air | "Air baru 0,42 km² · surut 0,10 km² · tetap 3,8 km² dibanding 12 Sep" + label orbit berbeda bila relevan |
| Aksi ADMIN | Periksa sekarang, ubah retensi, coba ulang sumber gagal, laporan dataset area |

### 2.3 Statistik Hari Ini (`#hari-ini`) — USER+

| Komponen | Isi |
|---|---|
| Spanduk alert | `v_alert_aktif`; severity tertinggi per kecamatan. Tombol **Tandai sudah dibaca** hanya untuk ANALYST/ADMIN (+ catatan opsional) |
| Peta koroplet | Kecamatan AOI diwarnai kategori BMKG hujan 24 jam |
| Kartu per kecamatan | Hujan 24h / 72h / 7d / 30d, NDVI, % banjir MODIS, `run_type` GPM (badge "sementara" untuk Late/Early) |
| Tanggal data | "Data hujan untuk 30 Sep 2026 (07.00–07.00 WIB)" |

**Kategori BMKG (hujan 24 jam):**

| Kategori | Rentang | Warna |
|---|---|---|
| Ringan | < 20 mm | hijau |
| Sedang | 20 – < 50 mm | kuning |
| Lebat | 50 – < 100 mm | oranye |
| Sangat lebat | 100 – < 150 mm | merah |
| Ekstrem | ≥ 150 mm | merah tua |

Warna tidak menjadi satu-satunya pembawa makna: setiap kartu juga menuliskan nama kategori.

### 2.4 Analitik (`#analitik`) — ANALYST, ADMIN

| Komponen | Isi |
|---|---|
| Filter | Rentang tanggal, kecamatan (multi), band |
| Tren | Grafik deret waktu hujan/NDVI/% banjir per kecamatan, garis ambang |
| Heatmap | Hujan harian bulan × hari |
| Korelasi kejadian | Linimasa `disaster_events` ditumpangkan pada hujan 24h & 72h (`v_kejadian_dan_hujan`) |
| Evaluasi alert | Tabel hit / miss / false alarm per aturan (`v_evaluasi_alert`) |
| Riwayat alert | Daftar alert + status acknowledge + waktu tanggap |
| Ekspor | CSV hasil filter (`EXPORT_CSV` dicatat) |

### 2.5 Kejadian Bencana (`#kejadian`) — ANALYST, ADMIN

Tabel + peta titik. Form tambah/ubah: jenis bencana, tanggal mulai/selesai, kecamatan (dropdown AOI), desa (teks), titik di peta (opsional), deskripsi, ringkasan dampak (tanpa data pribadi), sumber informasi + rujukan, status verifikasi. Hapus = soft delete dengan konfirmasi. Setiap perubahan tercatat di `audit_log`.

### 2.6 Katalog Dataset (`#katalog`) dan Buat Dataset (`#buat-dataset`) — DATA_ENGINEER, ADMIN

Diwariskan dari DataLab View 1 dan View 2 dengan perubahan:

| Perubahan | Rincian |
|---|---|
| Panel lokasi | Hanya ROI sistem (AOI GMLS, kecamatan, gabungan kecamatan dari ADMIN); tanpa "Tambah lokasi", tanpa geocoding |
| Wizard | Langkah sama (Wilayah & Tanggal → Satelit → Fusion & Preview → Tinjau); label Indonesia; batas rentang 366 hari |
| Reuse Previous Config | Dipertahankan, per pengguna (`created_by`) |
| Kartu dataset | Menampilkan pembuat; tombol Hapus hanya untuk pembuat atau ADMIN |
| Panel Merge, Reference layers | Dihapus |
| Kolom "Minimum quality score" | Dihapus — ambang QA diatur ADMIN di `quality_thresholds` |
| Detail produk | `scene_id` (S1) atau `nasa_scene_id` (MODIS/GPM); FUSION keduanya kosong |
| Unduhan | ZIP dataset, produk satuan, fusion HDF5, laporan dataset — semua tercatat |
| Lineage | Panel "Asal-usul" pada detail produk (`/products/{id}/lineage`) |

### 2.7 Laporan (`#laporan`) — ANALYST, DATA_ENGINEER, ADMIN

| Komponen | Isi |
|---|---|
| Tab | **Hidromet** (ANALYST, ADMIN) · **Kesehatan Data** (DATA_ENGINEER, ADMIN) |
| Daftar | Periode, jenis (mingguan/bulanan), tanggal dibuat, ukuran, status, tombol **Unduh PDF** |
| Filter | Tahun, jenis periode |
| ADMIN | Tombol **Buat ulang** pada laporan READY/FAILED |

Laporan muncul setelah periodenya berakhir (M18); tidak ada laporan untuk periode berjalan.

### 2.8 Administrasi (`#admin`) — ADMIN

| Tab | Isi |
|---|---|
| Pengguna | Daftar, buat akun, ubah role, nonaktifkan/aktifkan, reset kata sandi, buka kunci |
| Scene | Daftar `satellite_scenes`/`nasa_scenes` (filter sumber, tanggal, status, `is_valid`), **proses ulang**, **nonaktifkan / pulihkan** (alasan wajib), **picu ingestion** rentang tanggal (job hidromet atau Live) |
| Live Area | Tambah (dari ROI sistem), ubah nama/retensi (1–60), aktif/nonaktif, hapus |
| Wilayah | Daftar kecamatan Kab. Lebak; centang `in_aoi`; buat ROI gabungan kecamatan |
| Aturan & ambang | `alert_rules`, `quality_thresholds`, `disaster_types` |
| Pipeline | Status job terakhir per jenis, peringatan token NASA, antrean, log 50 terakhir |
| Arsip | Statistik penyimpanan per tier, verifikasi checksum |
| Log Masuk | `v_log_login`: waktu, pengguna, hasil, IP |
| Log Unduhan | `v_log_unduhan`: waktu, pengguna, jenis, objek, ukuran |
| Audit | `audit_log`: tabel, operasi, pengguna, kolom berubah, nilai lama/baru |
| Pengaturan | `app_settings` |
| Token API | Semua token (pemilik, prefix, scope, kedaluwarsa, terakhir dipakai), cabut token |

### 2.9 Akun Saya (`#akun`) — USER+

| Komponen | Isi |
|---|---|
| Profil | Nama, organisasi, role (baca saja) |
| Ubah kata sandi | |
| Token API | Buat token (nama, scope READ / READ_DOWNLOAD, masa berlaku ≤ 180 hari); token utuh ditampilkan **sekali** dengan tombol salin; daftar token milik sendiri; cabut |
| Panduan singkat | Contoh `curl` dan Python, tautan ke `/docs` |

---

## 3. Hak Akses

### 3.1 Matriks fitur

| Fitur | PUBLIC | USER | ANALYST | DATA_ENGINEER | ADMIN |
|---|---|---|---|---|---|
| Scene Live terbaru | ✓ | ✓ | ✓ | ✓ | ✓ |
| Scene Live ≤ 30 hari + prakiraan | — | ✓ | ✓ | ✓ | ✓ (semua) |
| Statistik hari ini + alert aktif (lihat) | — | ✓ | ✓ | ✓ | ✓ |
| Acknowledge alert | — | — | ✓ | — | ✓ |
| Analitik + ekspor CSV | — | — | ✓ | — | ✓ |
| Kejadian bencana (CRUD) | — | — | ✓ | — | ✓ |
| Laporan Hidromet | — | — | ✓ | — | ✓ |
| Katalog + buat dataset + unduh data/fusion | — | — | — | ✓ | ✓ |
| Laporan Kesehatan Data | — | — | — | ✓ | ✓ |
| Kelola scene, Live Area, wilayah, aturan | — | — | — | — | ✓ |
| Kelola pengguna, log masuk/unduhan, audit | — | — | — | — | ✓ |

### 3.2 Tiga lapis penegakan

1. **UI** menyembunyikan menu (kenyamanan, bukan keamanan).
2. **API** memeriksa role lewat dependency `require_role(...)` → 401 / 403.
3. **Basis data** menjalankan request dengan `SET LOCAL ROLE monitor_<role>` sehingga kueri yang lolos lapis 2 karena bug tetap ditolak GRANT (DATABASE.md §8). Pengujian robustness mencoba memanggil endpoint ANALYST dengan token USER dan memverifikasi penolakan di lapis 2 **dan** 3 (lapis 2 dimatikan sementara di lingkungan uji).

---

## 4. REST API

**Base URL:** `/api`. JSON. Autentikasi: cookie `orbit_u_session` (JWT, untuk browser) **atau** header `Authorization: Bearer <token API>` (untuk skrip/sistem lain, M33). Tanggal `YYYY-MM-DD`; tanggal hidromet adalah hari UTC.

Token API: hanya endpoint `GET` (scope `READ`) dan unduhan (scope `READ_DOWNLOAD`); semua aksi tulis menolak token dengan 403 `TOKEN_WRITE_FORBIDDEN`. Unduhan dengan token ber-scope `READ` ditolak 403 `TOKEN_SCOPE_FORBIDDEN`. Rate limit sederhana: 120 request/menit per token (in-process), 429 `RATE_LIMITED` + `Retry-After: 60` bila terlampaui.

Kolom **Role** = role minimum (hierarki: ADMIN ⊃ ANALYST ⊃ USER, ADMIN ⊃ DATA_ENGINEER ⊃ USER).

### 4.1 Autentikasi [BARU]

| Metode | Endpoint | Role | Kegunaan |
|---|---|---|---|
| POST | `/auth/login` | — | `{username, password}` → set cookie; 401 salah, 423 terkunci |
| POST | `/auth/logout` | USER | Hapus cookie |
| GET | `/auth/me` | USER | `{user_id, username, full_name, role_code, permissions[]}` |
| POST | `/auth/change-password` | USER | `{old_password, new_password}` |
| GET | `/auth/tokens` | USER | Token milik sendiri (tanpa nilai token) |
| POST | `/auth/tokens` | USER (sesi web) | `{name, scope, expires_in_days}` → `201 {token_id, token: "trn_…", prefix, expires_at}`; nilai `token` hanya dikirim sekali |
| DELETE | `/auth/tokens/{id}` | USER (milik sendiri) / ADMIN | Cabut |

### 4.2 Publik [BARU]

| Metode | Endpoint | Role | Kegunaan |
|---|---|---|---|
| GET | `/public/live` | PUBLIC | Scene terbaru per Live Area aktif (tanpa forecast, tanpa riwayat) |
| GET | `/public/live/{area_id}/preview/{key}.png` | PUBLIC | Preview scene terbaru (`key` termasuk `s1_water_change`); `?date=` selain tanggal terbaru → 403 `SCENE_NOT_PUBLIC` |
| GET | `/health` | PUBLIC | Status sistem + DB [WARIS] |

### 4.3 Live [UBAH]

| Metode | Endpoint | Role | Kegunaan |
|---|---|---|---|
| GET | `/live/areas` | USER | Daftar area [WARIS] |
| GET | `/live/areas/{id}/card?date=` | USER | Kartu [WARIS]; selain ADMIN hanya scene ≤ 30 hari + scene terbaru (daftar tanggal disaring; tanggal lain → 403 `SCENE_OUT_OF_RANGE`) |
| GET | `/live/areas/{id}/preview/{date}/{key}.png` | USER | `key` + `s1_water_change`; batas 30 hari sama dengan kartu |
| POST | `/live/areas` | ADMIN | Buat area dari `roi_id` |
| PATCH | `/live/areas/{id}` | ADMIN | `name`, `retention` (1–60), `enabled` |
| DELETE | `/live/areas/{id}` | ADMIN | [WARIS] |
| POST | `/live/areas/{id}/check` | ADMIN | [WARIS] |
| POST | `/live/areas/{id}/scenes/{date}/retry` | ADMIN | [WARIS] |
| GET | `/live/areas/{id}/events`, `/activity`, `/log` | ADMIN | [WARIS] |

### 4.4 Hidromet [BARU]

| Metode | Endpoint | Role | Kegunaan |
|---|---|---|---|
| GET | `/hydromet/today` | USER | `v_statistik_hari_ini` |
| GET | `/hydromet/observations` | USER | `?region_id=&band=&date_from=&date_to=&limit=&offset=`; USER hanya data ≥ hari ini − 30 (selebihnya 403 `DATE_OUT_OF_RANGE`), ANALYST bebas |
| GET | `/hydromet/trend` | USER | `?band=RAIN_24H&days=30` → `{band, dates[], series[{region_id, pcode, name, values[]}]}`; `days` > 30 hanya ANALYST |
| GET | `/hydromet/observations.csv` | ANALYST | Ekspor CSV (dicatat `EXPORT_CSV`) |
| GET | `/regions` | USER | FeatureCollection kecamatan AOI (disederhanakan `ST_SimplifyPreserveTopology`); `?all=true` semua kecamatan Lebak, `?tolerance=` derajat |
| GET | `/rois` | USER | Daftar ROI sistem (AOI GMLS, kecamatan, gabungan) untuk wizard dataset dan Live Area `?q=` |

### 4.5 Alert [BARU]

| Metode | Endpoint | Role | Kegunaan |
|---|---|---|---|
| GET | `/alerts` | USER | `?status=active\|acknowledged&severity=&date_from=` |
| POST | `/alerts/{id}/acknowledge` | ANALYST | `{note?}`; 409 `ALERT_ALREADY_ACKED` bila sudah |
| GET | `/alerts/evaluation` | ANALYST | `{hit, miss, false_alarm, pod, far}` dari `v_evaluasi_alert` (`?date_from=&date_to=`); `pod`/`far` `null` bila penyebut nol |
| GET | `/alert-rules` | USER | Daftar aturan |
| POST / PUT | `/alert-rules`, `/alert-rules/{id}` | ADMIN | Tambah / ubah (tanpa DELETE; nonaktifkan) |

### 4.6 Kejadian Bencana [BARU]

| Metode | Endpoint | Role | Kegunaan |
|---|---|---|---|
| GET | `/disasters` | ANALYST | Filter tanggal, jenis, kecamatan, verifikasi |
| GET | `/disasters/{id}` | ANALYST | Detail + hujan H-0..H-2 |
| POST | `/disasters` | ANALYST | Buat → 201 |
| PUT | `/disasters/{id}` | ANALYST | Ubah |
| DELETE | `/disasters/{id}` | ANALYST | Soft delete |
| GET / POST / PUT | `/disaster-types` | USER (GET) / ADMIN | Master jenis (`?include_inactive=true`) |

Validasi kejadian: jenis aktif dari master, wilayah = kecamatan (level 3), deskripsi 10–4000 karakter, `event_end_date ≥ event_date` (400 `INVALID_DISASTER`). Impor massal lewat Excel (§4.10) atau `scripts/import_disasters.py` (CSV).

### 4.7 Dataset, scene, produk, kualitas, lineage [WARIS]

Endpoint DataLab dipertahankan dengan role minimum **DATA_ENGINEER**: `/datasets` (CRUD, status, pause/resume/cancel, logs, download, preview, storage, report, last-config), `/scenes`, `/products`, `/products/{id}/download`, `/products/{id}/verify`, `/quality/*`, `/metadata/lineage/{product_id}`, `/pipeline/*`.

Perubahan:

| Endpoint | Perubahan |
|---|---|
| `GET /datasets` | Menyaring dataset sistem; menyertakan `created_by` |
| `DELETE /datasets/{id}` | Pembuat atau ADMIN |
| `/scenes` | `?source=S1\|MODIS\|GPM` (default `S1`) memilih `satellite_scenes` atau `nasa_scenes` (K12); item MODIS/GPM berbentuk `{nasa_scene_id, source, tile_id, product_short_name, acquisition_date, run_type, is_valid, …}`; `orbit_direction`/`only_gold` hanya untuk S1. Scene `is_valid = false` disembunyikan; `?include_invalid=true` hanya ADMIN (lainnya 403) |
| `DELETE /datasets/{id}` (lanjutan) | Pembuat lain → 403 `NOT_DATASET_OWNER`. Status `DELETING` diset dengan role pengguna; berkas dan baris dihapus pipeline (`monitor_etl`) setelah commit (DATABASE.md §8.3) |
| `/storage/summary`, `/storage/files/{tier}` | Membaca disk seluruh mesin → **ADMIN** (nama tier D14) |
| `/regions` (tulis), `/regions/geocode`, `/merge/*`, `/datasets/{id}/masks`, `/storage/cleanup*`, `/live` lama | **Dihapus** |
| Semua unduhan | Mencatat `user_activity_logs` |

### 4.8 Laporan periodik [BARU]

| Metode | Endpoint | Role | Kegunaan |
|---|---|---|---|
| GET | `/reports` | ANALYST / DATA_ENGINEER | Daftar sesuai audiens (RLS) `?type=&year=&include_superseded=`; role lain → 403 `REPORT_AUDIENCE` |
| GET | `/reports/{id}/download` | sesuai audiens | PDF; 404 bila bukan audiensnya (tidak membocorkan keberadaan) |
| POST | `/reports/regenerate` | ADMIN | `{report_code, period_start}` → 202 (Senin / tanggal 1, selain itu 400 `INVALID_PERIOD`); baris lama → `SUPERSEDED`, berkas lama dipertahankan |

### 4.9 Administrasi [BARU]

| Metode | Endpoint | Kegunaan |
|---|---|---|
| GET / POST | `/admin/users` | Daftar (`v_users_safe`) / buat |
| PATCH | `/admin/users/{id}` | Role, nama, aktif |
| POST | `/admin/users/{id}/reset-password`, `/unlock` | |
| PATCH | `/admin/scenes/{source}/{id}` | `source` = S1 \| MODIS \| GPM; `{is_valid, reason}` (alasan wajib bila tidak valid, 400 `REASON_REQUIRED`) |
| POST | `/admin/scenes/{source}/{id}/reprocess` | 202. GPM/MODIS: Job Hidromet tanggal itu diulang (COG non-Final dibangun ulang); S1: scene Live tanggal itu dicoba ulang, scene dataset Katalog → 409 `NOT_REPROCESSABLE` |
| POST | `/admin/ingest` | `{job: "HYDROMET"\|"LIVE", date_from, date_to, area_id?}` → 202 (HYDROMET ≤ 366 hari, di bawah kunci `hydromet`) |
| GET | `/admin/regions` | Kecamatan Lebak + `in_aoi` |
| PATCH | `/admin/regions/{id}` | `{in_aoi}`; ROI AOI + dataset `HYDROMET_AOI` dibangun ulang; minimal satu kecamatan (409 `AOI_EMPTY`) |
| POST | `/admin/rois` | `{region_ids[], name, region_code?}` → ROI gabungan (bbox = envelope gabungan) |
| GET / PUT | `/admin/quality-thresholds` | PUT = daftar `{threshold_id, warn_below?, fail_below?, warn_above?, fail_above?, reference?, is_active?}` |
| GET / PUT | `/admin/settings` | PUT `{settings: {kunci: nilai}}`, hanya kunci yang ada, divalidasi rentangnya (400 `INVALID_SETTING`) |
| GET | `/admin/pipeline/status` | Job terakhir per jenis (HYDROMET/LIVE/DATASET), status hidromet (terakhir selesai, WAITING, FAILED), Live Area, laporan terakhir, `SKIPPED_LOCKED` 7 hari, antrean, ada/tidaknya kredensial NASA/Copernicus, jadwal scheduler |
| GET | `/admin/archive/stats`; POST `/admin/archive/verify` | Ukuran produk per sumber/tier + jumlah baris; verifikasi SHA-256 sampel acak `{limit ≤ 500, source?}` → `{checked, ok, missing[], mismatch[]}` |
| GET | `/admin/logs/login`, `/admin/logs/download` | `?user_id=&date_from=&date_to=&page=` |
| GET | `/admin/audit` | `?table=&operation=&user_id=&date_from=&date_to=&page=` |
| GET | `/admin/tokens` | Semua token (`?user_id=&active=`): pemilik, prefix, scope, kedaluwarsa, terakhir dipakai; cabut lewat `DELETE /auth/tokens/{id}` |

### 4.10 Ekspor/impor Excel [BARU, Tahap 3]

| Metode | Endpoint | Role | Kegunaan |
|---|---|---|---|
| GET | `/excel` | USER | Jenis data yang boleh diekspor/diimpor role pemanggil, dengan URL-nya |
| GET | `/excel/{entity}.xlsx` | sesuai jenis data | Sheet `Data` + `Petunjuk`; `?date_from=&date_to=` bila jenisnya bertanggal; dicatat `DOWNLOAD_XLSX` |
| GET | `/excel/{entity}/template.xlsx` | role impor | Templat kosong + arti kolom, wajib/tidak, nilai yang diizinkan |
| POST | `/excel/{entity}/import` | role impor | Body = berkas .xlsx mentah (`Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, ≤ 10 MB); `?dry_run=true`; semua baris atau tidak sama sekali; 422 `IMPORT_ROWS_INVALID` + `errors[]` per nomor baris |

Ekspor (role minimum): `kecamatan`, `alerts`, `alert_rules`, `disaster_types`, `live_scenes` (USER); `observations`, `hujan_harian`, `disasters`, `disaster_rain`, `alert_evaluation` (ANALYST); `datasets`, `s1_scenes`, `nasa_scenes`, `products`, `quality_summary`, `completeness` (DATA_ENGINEER); `downloads`, `audit`, `app_settings` (ADMIN). Impor: `disasters` (ANALYST), `disaster_types`, `alert_rules`, `kecamatan` (status AOI), `app_settings` (ADMIN). Jenis data di luar role → 403 `ENTITY_FORBIDDEN`; impor jenis yang hanya bisa diekspor → 400 `IMPORT_NOT_SUPPORTED`. Ekspor kejadian memakai kolom yang sama dengan impor (bisa diedit lalu diimpor ulang; baris yang sama dilewati sebagai duplikat).

Semua di bawah `/admin` memerlukan ADMIN. Daftar log memakai kontrak `{items, total, limit, offset}`; `page` (mulai 1) setara `offset = (page-1)·limit`. ADMIN tidak dapat menonaktifkan atau menurunkan role akunnya sendiri (409 `CANNOT_MODIFY_SELF`).

---

## 5. Kontrak Respons

Format warisan DataLab dipertahankan agar `app.js` tidak dirombak.

### Daftar

```json
{ "items": [ ... ], "total": 120, "limit": 25, "offset": 0 }
```

### Contoh `GET /api/hydromet/today`

```json
{
  "obs_date": "2026-09-30",
  "window_wib": "2026-09-30T07:00+07:00/2026-10-01T07:00+07:00",
  "regions": [
    {
      "region_id": 12, "pcode": "ID360201", "name": "Bayah",
      "rain_24h_mm": 63.4, "rain_72h_mm": 118.0, "rain_7d_mm": 160.2, "rain_30d_mm": 402.7,
      "bmkg_category": "LEBAT", "gpm_run": "L",
      "ndvi": 0.61, "modis_flood_pct": 0.8, "modis_date": "2026-09-30",
      "active_alert": { "alert_id": 881, "severity": "INFO", "rule_code": "FLOOD_RAIN24_HEAVY" }
    }
  ]
}
```

### Contoh `POST /api/disasters`

```json
{
  "disaster_type_code": "BANJIR",
  "region_id": 12,
  "village_name": "Bayah Barat",
  "location": { "lat": -6.928, "lon": 106.226 },
  "event_date": "2026-09-30",
  "description": "Luapan Sungai Cimadur merendam permukiman tepi sungai.",
  "impact_summary": "± 40 rumah tergenang 30–50 cm",
  "info_source": "GMLS",
  "source_reference": null,
  "is_verified": false
}
```
→ `201 { "event_id": 57, ... }`

### Error

```json
{ "detail": "Alert already acknowledged", "code": "ALERT_ALREADY_ACKED" }
```

DataLab hanya mengirim `detail`; Monitor **menambah** `code` (mesin-baca, selalu ada) agar frontend dapat menampilkan pesan Indonesia dari tabel terjemahan. Klien lama yang hanya membaca `detail` tetap berfungsi.

Kode spesifik: `NOT_AUTHENTICATED`, `SESSION_EXPIRED`, `ACCOUNT_INACTIVE`, `INVALID_CREDENTIALS`, `ACCOUNT_LOCKED`, `ROLE_FORBIDDEN` (lapis API), `DB_PERMISSION_DENIED` (GRANT/RLS PostgreSQL menolak, lapis 3), `CSRF_HEADER_REQUIRED`, `TOKEN_INVALID`, `TOKEN_REVOKED`, `TOKEN_EXPIRED`, `TOKEN_WRITE_FORBIDDEN`, `TOKEN_SCOPE_FORBIDDEN`, `RATE_LIMITED`, `NOT_DATASET_OWNER`, `SCENE_OUT_OF_RANGE`, `PASSWORD_POLICY`, `INVALID_OLD_PASSWORD`, `USERNAME_TAKEN`, `CANNOT_MODIFY_SELF`, `TOKEN_ALREADY_REVOKED`, `INVALID_DATE_RANGE`, `ALERT_ALREADY_ACKED`, dan Tahap 3: `DATE_OUT_OF_RANGE`, `SCENE_NOT_PUBLIC`, `THRESHOLD_REQUIRED`, `RULE_CODE_TAKEN`, `TYPE_CODE_TAKEN`, `UNKNOWN_REFERENCE`, `INVALID_DISASTER`, `NOT_KECAMATAN`, `AOI_EMPTY`, `INVALID_ROI`, `HYDROMET_NOT_READY`, `REPORT_AUDIENCE`, `INVALID_PERIOD`, `FILE_MISSING`, `INVALID_SOURCE`, `REASON_REQUIRED`, `NOT_REPROCESSABLE`, `INVALID_THRESHOLD`, `INVALID_SETTING`, `ENTITY_FORBIDDEN`, `IMPORT_NOT_SUPPORTED`, `INVALID_IMPORT_FILE`, `IMPORT_ROWS_INVALID`, `EMPTY_UPLOAD`, `UPLOAD_TOO_LARGE`. Selain itu dipakai kode bawaan per status: `BAD_REQUEST`, `NOT_FOUND`, `CONFLICT`, `VALIDATION_ERROR`, `INTERNAL_ERROR`, …

| HTTP | Makna |
|---|---|
| 400 | Parameter tidak valid (tanggal terbalik, rentang > batas) |
| 401 | Belum masuk / sesi kedaluwarsa |
| 403 | Role tidak berhak |
| 404 | Tidak ada, atau tidak boleh tahu keberadaannya |
| 409 | Konflik (sudah di-acknowledge, nama dataset ganda, laporan sedang dibuat) |
| 422 | Validasi Pydantic [WARIS, diratakan jadi satu string] |
| 423 | Akun terkunci sementara |
| 500 / 503 | Server / DB [WARIS] |

---

## 6. Autentikasi dan Sesi

- Login → verifikasi bcrypt lewat fungsi `auth_get_user()` → JWT `{sub, role, iat, exp}` (HS256, 8 jam) di cookie `HttpOnly; Secure; SameSite=Strict; Path=/`.
- Tidak ada refresh token; sesi habis → kembali ke `/masuk` dengan pesan.
- Perubahan role/nonaktif berlaku pada request berikutnya: setiap request membaca ulang `users.is_active` dan `role_id` (satu kueri PK).
- Setiap request selain GET/HEAD/OPTIONS yang tidak memakai Bearer (termasuk `/auth/login`) wajib membawa header `X-Requested-With: orbit-u` (403 `CSRF_HEADER_REQUIRED`), sebagai lapis CSRF sederhana tambahan di atas `SameSite=Strict`.
- Cookie yang rusak/kedaluwarsa diperlakukan sebagai pengunjung tanpa login; endpoint yang butuh login menjawab 401 `SESSION_EXPIRED`. Login gagal tetap mencatat log dan menaikkan penghitung kunci (respons dikembalikan, bukan exception, agar ikut ter-commit). Percobaan kelima yang gagal langsung menjawab 423.
- **Token API**: `Bearer trn_<32 byte acak base62>`; server mencari `token_prefix`, membandingkan SHA-256 secara constant-time, memeriksa `revoked_at`, `expires_at`, dan status pemilik, lalu menjalankan request dengan role pemilik (`SET LOCAL ROLE`, `app.user_id`) persis seperti sesi web. Pencarian berdasarkan prefix memakai fungsi `auth_get_token()` (DATABASE.md §8.2) karena RLS `api_tokens` menolaknya sebelum pemilik diketahui. Setiap request bertoken dicatat satu baris `user_activity_logs` (`API_REQUEST`, atau `DOWNLOAD_*` untuk unduhan) setelah respons selesai dikirim; `bytes_sent` unduhan adalah byte yang benar-benar terkirim.

### 6.1 Dokumentasi API untuk developer (hasil akhir "API Developer")

| Artefak | Isi |
|---|---|
| `/docs` (Swagger) dan `/openapi.json` | Seluruh endpoint dengan deskripsi Bahasa Inggris, contoh request/response, skema error, dan role minimum di setiap operasi (`x-min-role`) |
| `docs/api_examples.md` | Alur lengkap: buat token → ambil `/hydromet/observations` → ekspor CSV → daftar dataset → unduh produk/fusion HDF5 → telusuri lineage; contoh `curl` dan Python (`requests`, `h5py`) |
| `examples/client.py` | Klien Python kecil (±100 baris) yang membungkus token, pagination `items/total`, dan unduhan streaming |

```bash
curl -H "Authorization: Bearer $ORBIT_U_TOKEN" \
  "https://<host>/api/hydromet/observations?region_id=12&band=RAIN_24H&date_from=2025-01-01&date_to=2025-12-31"
```

---

## 7. Pemodelan UML

### 7.1 Aktor

PUBLIC (Pengunjung), USER (Relawan), ANALYST, DATA_ENGINEER, ADMIN, dan **Penjadwal** (aktor sistem). Generalisasi: ADMIN → ANALYST, DATA_ENGINEER → USER → PUBLIC.

### 7.2 Use case

| Aktor | Use case |
|---|---|
| Pengunjung | Lihat kondisi terbaru, lihat preview, masuk |
| Relawan | Lihat Pantauan Live 30 hari, lihat prakiraan, lihat statistik hari ini, lihat alert aktif, ubah kata sandi, keluar |
| Analyst | Acknowledge alert, analisis tren, lihat evaluasi alert, ekspor CSV, kelola kejadian bencana, unduh Laporan Hidromet |
| Data Engineer | Buat dataset historis, pantau/jeda/batalkan job, unduh dataset/produk/fusion, telusuri lineage, lihat kualitas, unduh Laporan Kesehatan Data |
| Admin | Kelola pengguna, kelola scene (proses ulang, nonaktifkan, picu ingestion), kelola Live Area, kelola wilayah AOI, kelola aturan & ambang, lihat log masuk/unduhan, lihat audit, buat ulang laporan, verifikasi arsip |
| Penjadwal | Jalankan job hidromet, perbarui Late→Final, jalankan siklus Live, buat laporan periodik |

`«include»`: setiap use case terautentikasi → *Masuk*; *Acknowledge alert*, *Kelola kejadian*, *Kelola …* → *Catat audit*; semua unduhan → *Catat unduhan*. `«extend»`: *Jalankan job hidromet* ← *Picu alert*.

### 7.3 Activity diagram (6)

1. Job hidromet harian: unduh GPM → akumulasi → MODIS → zonal → cek alert → catat log.
2. Alert terpicu sampai di-acknowledge.
3. Siklus Live: temukan scene S1 → ingest → metrik → preview + perubahan air → kalimat → prakiraan → retensi.
4. Pencatatan kejadian bencana (dengan verifikasi).
5. Pembuatan dataset historis dan unduhan fusion oleh Data Engineer.
6. Masuk, pemeriksaan role, `SET LOCAL ROLE`, dan pencatatan log.

Class diagram tidak dibuat; ERD sudah memuat struktur data (ketentuan skripsi: opsional).

---

## 8. Rencana Pengujian

| Kriteria DBSDLC | Cara uji | Target awal |
|---|---|---|
| Learnability | SUS 10 butir ke ±5 relawan GMLS + 4 tugas: "lihat kondisi hari ini", "tandai alert sudah dibaca", "catat banjir kemarin di Bayah", "unduh laporan minggu lalu" | SUS ≥ 68; tugas selesai tanpa bantuan ≥ 80% |
| Performance | Waktu respons `/hydromet/today`, `/public/live`, `/alerts`, `/disasters`, `/alerts/evaluation` (p95, 20 request); `EXPLAIN ANALYZE` sebelum/sesudah index | < 1 s untuk tiga pertama; < 2 s untuk evaluasi |
| Robustness | Black-box: tanggal terbalik, rentang > batas, deskripsi kosong/terlalu panjang/HTML, `region_id` di luar AOI, token USER ke endpoint ANALYST/ADMIN, akses preview publik tanggal lama, 6 kali salah sandi, mengubah `password_hash` lewat role analyst di psql | Semua ditolak dengan kode benar; tidak ada 500 |
| Recoverability | Matikan proses saat job dataset, saat backfill hidromet, dan saat pembuatan laporan → jalankan ulang; restore `pg_dump` ke DB kosong | Tidak ada duplikat; job melanjutkan; restore lengkap |
| Adaptability | Tambah jenis bencana, ubah ambang alert, tambah kecamatan ke AOI, ubah retensi Live — semuanya lewat UI tanpa ubah kode | Berlaku pada siklus berikutnya |
| Keamanan (RM4) | Matriks GRANT diuji dengan `tests/security/grant_matrix.sql` per role; verifikasi baris `audit_log` muncul untuk UPDATE lewat psql; token tidak bisa menulis, token dicabut/kedaluwarsa ditolak | Sesuai matriks §8.3 DATABASE |
| Rekomendasi DBMS | `benchmark/run.py` (DATABASE §1) | Median & p95 Q1–Q5 + tabel fitur F1–F3 |

Artefak uji lengkap: PIPELINE.md §13. Target angka dijelaskan dasarnya di bab pengujian skripsi.
