# Setup Laptop Baru — Pindah Orbit-U: The Monitor

Dokumen operasional untuk memindahkan proyek dari laptop lama ke laptop baru
dengan **memindahkan isi basis data apa adanya** (`pg_dump` → `pg_restore`),
lalu melanjutkan backfill 3 tahun di laptop baru.

Beda dengan `README.md §9`: §9 membangun database **kosong** dari nol
(`apply_schema.py` → `load_regions.py` → `create_admin.py`). Dokumen ini
melewati ketiga langkah itu karena restore sudah membawa skema, wilayah,
master data, dan akun. Jalankan §9 hanya kalau restore dibatalkan.

---

## 0. Versi yang harus sama

Diambil dari laptop lama per 2026-10-05. Jangan menebak — versi mayor
PostgreSQL yang lebih rendah di laptop baru **tidak bisa** me-restore dump ini.

| Komponen | Versi di laptop lama | Catatan |
|---|---|---|
| Python | 3.12.10 | `requirements.txt` dipin ke wheel yang teruji di 3.12 |
| PostgreSQL | **18.6** | laptop baru harus 18.x atau lebih baru |
| PostGIS | 3.6.2 | ikut installer lewat Stack Builder |
| MySQL | belum ada | 8.0.x, hanya untuk benchmark M29 |

---

## 1. Di laptop LAMA — yang harus dibawa

`git push` hanya memindahkan ±8 MB kode. Yang berikut ini **tidak ada di
repo** dan harus disalin manual lewat drive eksternal.

### 1a. Wajib

| Sumber | Ukuran | Kenapa |
|---|---|---|
| `.env` | 4 KB | kredensial; tidak pernah di-commit |
| dump database | ±puluhan MB | **struktur sekaligus seluruh isi** tabel |
| dump role | 2 KB | role PostgreSQL bersifat **cluster-wide**, tidak ikut dump database |
| manifest | 2 KB | sidik jari untuk membuktikan hasil restore identik |

Hentikan dulu API dan scheduler (`SCHEDULER_ENABLED` menulis tiap 02:00), supaya
dump dan manifest diambil dari keadaan yang sama persis.

```powershell
# Role dulu — tanpa ini, restore gagal di setiap GRANT.
pg_dumpall -U postgres --roles-only > D:\pindah\roles.sql

# Database: -Fc membawa DDL DAN seluruh baris. Tidak perlu --data-only
# atau --schema-only; keduanya justru memecah yang seharusnya utuh.
pg_dump -U postgres -Fc -d themonitor -f D:\pindah\themonitor.dump

# Manifest: jumlah objek + jumlah baris per tabel, untuk dibandingkan di §6.
psql -U postgres -d themonitor -f database/db_manifest.sql > D:\pindah\manifest_lama.txt
```

Ambil manifest **segera setelah** dump, sebelum ada yang menulis lagi ke
database. Kalau tidak, selisih beberapa baris di `audit_log` atau
`processing_logs` akan muncul sebagai "gagal" padahal restore-nya benar.

### 1b. Berdasarkan kebutuhan

| Sumber | Ukuran | Bawa kalau |
|---|---|---|
| `data/datasets/` | **13 GB** | Anda ingin katalog/preview/unduhan produk tetap hidup |
| `data/external/` | 190 MB | Anda mungkin menjalankan ulang `load_regions.py` |
| `data/from_glms/` | 7,2 MB | Anda mungkin menjalankan ulang `import_disasters.py` |
| `data/humdata/` | 844 MB | referensi HDX, jarang dipakai ulang |
| `tests/screenshots/` | 19 MB | bukti UI Tahap 4 untuk lampiran skripsi |

> **Perhatian — ini titik yang paling mudah terlewat.**
> Baris `data_products.file_path` di database menunjuk ke berkas di
> `data/datasets/`. Kalau database di-restore tanpa menyalin folder itu,
> katalog akan menampilkan produk yang berkasnya tidak ada: unduhan dan
> preview gagal meski barisnya utuh. Pilih satu secara sadar — salin 13 GB-nya,
> atau terima tautan berkas yang putus sampai pipeline membangkitkan ulang
> produknya.

Minimal yang masuk akal: `.env` + dua dump + `data/external/` + `data/from_glms/`
(±200 MB). Tambahkan `data/datasets/` kalau drive-nya muat.

---

## 2. Di laptop BARU — pasang perkakas

1. **Python 3.12.x** dari python.org. Centang *Add python.exe to PATH*.
   Hindari Python dari Microsoft Store — venv di laptop lama dibuat dari Store
   dan jalurnya tercatat absolut, sehingga rapuh begitu folder proyek pindah.
2. **PostgreSQL 18.x** dari installer EDB. Di akhir installer, buka
   **Stack Builder** → *Spatial Extensions* → **PostGIS 3.6**. Catat sandi
   `postgres` yang Anda tetapkan; itu yang masuk ke `DB_PASSWORD`.
3. Pastikan perkakas baris perintahnya ada di PATH:
   ```powershell
   psql --version      # harus 18.x
   ```
4. **MySQL 8.0** — tunda sampai §7b. Bukan prasyarat aplikasi.

---

## 3. Ambil kode

```powershell
cd D:\try
git clone https://github.com/not-notyou-you/orbit_u_the_monitor.git themonitor
cd themonitor
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`requirements.txt` sudah memuat semua wheel biner yang sulit di Windows
(`rasterio`, `pyhdf`, `h5py`, `reportlab`) — tidak perlu memasang GDAL sistem
secara terpisah. `pyshp` dipakai menggantikan driver vektor OGR justru supaya
hal itu tidak perlu.

Kalau `pip install` gagal di `pyhdf` atau `rasterio`, hampir selalu penyebabnya
versi Python bukan 3.12 — periksa `python --version` di dalam venv yang sudah
aktif.

---

## 4. Salin `.env`

Salin `.env` dari laptop lama apa adanya, lalu ubah **satu** hal:

```ini
DB_PASSWORD=<sandi postgres yang baru Anda tetapkan di §2>
DATABASE_URL=postgresql+psycopg2://postgres:<sandi baru>@localhost:5432/themonitor
```

Yang **tidak** perlu diubah:

- `JWT_SECRET` — kalau diubah, semua sesi login lama batal. Tidak merusak, tapi
  tidak ada gunanya.
- `MONITOR_APP_PASSWORD` dan `MONITOR_ETL_PASSWORD` — harus **tetap sama**,
  alasannya di §5.
- `NASA_EARTHDATA_TOKEN` — berlaku sampai sekitar 3 November 2026. Kalau
  backfill Anda melewati tanggal itu, buat token baru di
  urs.earthdata.nasa.gov → Generate Token.

---

## 5. Restore database

```powershell
# 1. Role lebih dulu. Peringatan "role postgres already exists" itu normal.
psql -U postgres -f D:\pindah\roles.sql

# 2. Database kosong + ekstensi.
createdb -U postgres themonitor
psql -U postgres -d themonitor -c "CREATE EXTENSION postgis; CREATE EXTENSION pgcrypto;"

# 3. Restore.
pg_restore -U postgres -d themonitor --no-owner --role=postgres -j 4 D:\pindah\themonitor.dump
```

**Peringatan yang wajar muncul dan boleh diabaikan:** `role "postgres" already
exists` pada langkah 1, dan `extension "postgis" already exists` pada langkah 3
(dump memuat `CREATE EXTENSION`, sementara Anda sudah membuatnya di langkah 2 —
itu disengaja, karena PostGIS lebih bersih dipasang lebih dulu). Yang **tidak**
boleh diabaikan: pesan apa pun yang menyebut `permission denied` atau
`relation ... does not exist`. Buktinya ada di manifest §6, bukan di layar.

**Kenapa `roles.sql` harus duluan.** Role PostgreSQL hidup di level cluster,
bukan di dalam database. `pg_dump -d themonitor` tidak memuat `CREATE ROLE`,
padahal isinya penuh `GRANT ... TO monitor_app`. Tanpa role, setiap GRANT gagal
dan Anda mendapat database yang tabelnya lengkap tapi tanpa satu pun izin — API
akan menolak semua request dengan `permission denied`.

`roles.sql` membawa serta hash sandi `monitor_app` dan `monitor_etl`, itulah
sebabnya `MONITOR_*_PASSWORD` di `.env` harus persis sama dengan laptop lama.
Kalau terlanjur berbeda, samakan dari sisi database:

```powershell
psql -U postgres -c "ALTER ROLE monitor_app PASSWORD '<nilai MONITOR_APP_PASSWORD>'"
psql -U postgres -c "ALTER ROLE monitor_etl PASSWORD '<nilai MONITOR_ETL_PASSWORD>'"
```

---

## 6. Verifikasi sebelum lanjut

Jangan mulai backfill sebelum ketiganya hijau.

```powershell
# 1. Koneksi + kredensial .env sejalan dengan DB.
python database/apply_schema.py --check

# 2. Manifest laptop baru.
psql -U postgres -d themonitor -f database/db_manifest.sql > D:\pindah\manifest_baru.txt

# 3. Bandingkan dengan laptop lama. Tidak ada keluaran = identik.
Compare-Object (Get-Content D:\pindah\manifest_lama.txt) (Get-Content D:\pindah\manifest_baru.txt)
```

Inilah bukti "sama persis" yang sebenarnya: `database/db_manifest.sql`
melaporkan jumlah tabel, VIEW, fungsi, trigger, policy RLS, GRANT ke role
`monitor_*`, versi ekstensi, **dan jumlah baris setiap tabel**. Kueri yang sama
dipakai `tests/recovery/backup_restore.sh` langkah 4 untuk menguji
recoverability (`PIPELINE.md §13`); berkas `.sql` ini versi baca-sajanya,
karena skrip uji itu menghapus database target sehingga sengaja menolak
`themonitor`.

Acuan dari laptop lama per 2026-10-05, kalau manifest-nya hilang:

```
objek|ekstensi|pgcrypto 1.4, postgis 3.6.2
objek|tabel|39      objek|view|15      objek|fungsi|824
objek|trigger|29    objek|policy|3     objek|grant|200
```

Baris data terbesar: `spatial_ref_sys` 8.500 (bawaan PostGIS),
`processing_logs` 856, `region_observations` 490, `data_products` 250,
`data_lineage` 144, `live_scene_metrics` 144, `processing_jobs` 105,
`audit_log` 63, `live_events` 44, `administrative_regions` 29,
`nasa_scenes` 27, `quality_metrics` 20, `scene_job_state` 19,
`processing_stages` 13, `regions_of_interest` 11, `app_settings` 10,
`dataset_jobs` 11, `quality_thresholds` 9, `quality_alerts` 8,
`live_scenes` 7, `satellite_scenes` 6, `user_activity_logs` 6, `users` 5,
`roles` 5, `dataset_source_config` 5, `alert_rules` 4, `disaster_types` 4,
`report_types` 4, `satellite_sources` 4, `fusion_strategies` 3,
`spectral_bands` 11, `datasets` 2, `live_areas` 1. Sisanya nol.

Cara membaca selisih yang muncul:

| Selisih | Artinya |
|---|---|
| `objek\|grant\|0` | `roles.sql` tidak dijalankan lebih dulu. Buang database, ulangi §5 dari awal — ini kegagalan yang paling sering lolos tanpa disadari. |
| `objek\|ekstensi` berbeda versi | PostGIS laptop baru bukan 3.6.x. Fungsi spasial bisa beda perilaku; pasang versi yang sama. |
| `spatial_ref_sys` berbeda | Ikut versi PostGIS, bukan data Anda. Abaikan kalau versinya memang beda dan Anda menerimanya. |
| `audit_log`/`processing_logs` lebih banyak di baru | Normal kalau API/scheduler sempat jalan sebelum manifest diambil. Hentikan, ambil ulang manifest. |
| Tabel lain berbeda | Restore tidak lengkap. Jangan ditambal — ulangi §5. |

Lalu nyalakan dan coba login:

```powershell
uvicorn api.main:app --host 0.0.0.0 --port 8001
```

Buka `http://localhost:8001`. Favicon yang muncul sekaligus membuktikan
`web/assets/img/favicon.svg` ikut ter-clone — berkas ini sebelumnya tertelan
pola `*.svg` di `.gitignore` dan sudah diperbaiki.

> `README.md §9` langkah 7 menulis `--port 8000`. Itu keliru terhadap
> `.env.example`, yang menetapkan `API_PORT=8001` supaya tidak bentrok dengan
> API The DataLab. Pakai 8001.

---

## 7. Pekerjaan yang tersisa setelah setup

### 7a. Backfill hidromet 3 tahun

```powershell
python scripts/backfill_hydromet.py --from 2023-01-01 --to 2025-12-31
```

Aman dihentikan kapan saja: tanggal berstatus `COMPLETED` dilewati saat
dijalankan ulang, jadi boleh dicicil per malam.

**Perkirakan ±1,5–2 hari jalan**, bukan beberapa jam. Angka ini berasal dari
uji nyata 1–7 Januari 2024 (`IMPLEMENTATION_NOTES.md` T3-26): ±130 detik per
tanggal, bukan ±25–45 detik seperti estimasi lama `PIPELINE.md §10`.
Penyebabnya komposit MOD09A1 di module7 membaca ulang 5 granule per band
setiap tanggal; optimasi cache antar-tanggal belum dikerjakan dan tercatat
sebagai opsional.

Disk: `prune_granule_cache()` menghapus granule mentah berumur di atas 45 hari
pada akhir setiap tanggal, jadi cache tidak tumbuh tanpa batas — tetap sediakan
≥100 GB bebas (`PIPELINE.md §9`).

Tujuh tanggal Januari 2024 sudah `COMPLETED` di dump yang Anda restore dan akan
dilewati otomatis.

### 7b. Benchmark MySQL 8 (M29)

Satu-satunya baris hasil yang masih kosong di seluruh proyek.
`IMPLEMENTATION_NOTES.md` menandainya `MENUNGGU MySQL 8`.

1. Pasang **MySQL 8.0.x**. Jangan pakai MariaDB dari XAMPP — `benchmark/run.py`
   menolaknya karena hasilnya tidak setara MySQL 8, dan itu persis yang
   memblokir pengerjaan di laptop lama.
2. `pip install -r requirements.txt` sudah membawa `PyMySQL==1.1.1` (baru
   ditambahkan; sebelumnya driver ini tidak ada di mana pun).
3. Isi di `.env` — bloknya sudah tersedia di `.env.example`:
   ```ini
   BENCH_MYSQL_HOST=localhost
   BENCH_MYSQL_PORT=3306
   BENCH_MYSQL_USER=root
   BENCH_MYSQL_PASSWORD=<sandi root mysql>
   ```
4. Jalankan:
   ```powershell
   python benchmark/generate.py
   python benchmark/run.py --engine all
   ```

Skrip memakai database terpisah `themonitor_bench` dan menolak nama
`themonitor`, jadi aman dijalankan berdampingan dengan backfill.

Sisi PostgreSQL sudah pernah dijalankan (18.6 + PostGIS 3.6.2, data sintetis
seed 20260929). `--engine all` akan menulis ulang kedua sisi di atas perangkat
keras yang sama — justru itu yang Anda inginkan, karena membandingkan hasil dua
mesin berbeda tidak sah sebagai dasar rekomendasi DBMS.

### 7c. Akun dev (opsional)

```powershell
python scripts/seed_dev_users.py --i-know-this-is-dev
```

Empat akun, satu per role, sandi `DevPassword!2026`. Jangan dijalankan di
database produksi — sandinya tertulis di dalam skrip.

---

## 8. Urutan ringkas

| # | Langkah | Perkiraan |
|---|---|---|
| 1 | Dump role + database + manifest di laptop lama, salin `.env` + `data/` | 30–60 menit (tergantung 13 GB ikut atau tidak) |
| 2 | Pasang Python 3.12 + PostgreSQL 18 + PostGIS | 45 menit |
| 3 | Clone, venv, `pip install` | 15 menit |
| 4 | `.env`, restore, bandingkan manifest (§6) | 30 menit |
| 5 | MySQL 8 + benchmark (§7b) | 1–2 jam |
| 6 | Backfill 3 tahun (§7a) | **1,5–2 hari jalan** |

Kerjakan §7b sebelum §7a: benchmark hanya butuh 1–2 jam dan menutup satu-satunya
hasil yang masih kosong, sedangkan backfill mengunci mesin berhari-hari.
