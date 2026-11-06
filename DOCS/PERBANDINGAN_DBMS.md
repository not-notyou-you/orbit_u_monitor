# Perbandingan DBMS: PostgreSQL vs MySQL 8.0

Dokumen ini menjawab tahap **DBMS Selection** di SKRIPSI.txt (langkah a–d) dan hasil akhir **Rekomendasi DBMS**.

Pengujian dijalankan ulang 6 November 2026 dengan **kedua data directory di disk fisik yang sama** (HDD D:), menggantikan pengujian 8 Oktober 2026 yang menaruh PostgreSQL di SSD dan MySQL di HDD (§2.5). Dua skrip yang dipakai:

- `benchmark/run.py`: kueri inti Q1–Q5 dan fitur F1–F3.
- `benchmark/extended.py`: skalabilitas, konkurensi, dan tulis.

Angka mentahnya ada di `benchmark/results/`.

---

## 1. Kenapa yang dibandingkan hanya PostgreSQL dan MySQL?

### 1.1 Kerangka acuan (langkah a)

DBMS dinilai dari apa yang benar-benar dikerjakan sistem ini. Kebutuhan itu diambil dari rumusan masalah (RM1–RM4) dan skema yang sudah berjalan:

| Kode | Kebutuhan | Asal |
|---|---|---|
| K1 | Model relasional dengan FK dan constraint yang ditegakkan DBMS: 43 tabel, 12 master | RM1, prasyarat prodi "database terstruktur" |
| K2 | Kueri spasial: irisan poligon kecamatan dan luas geodesik | AOI = gabungan kecamatan COD-AB |
| K3 | Agregasi deret waktu per kecamatan per band (pivot, tren, rekap bulanan) | Beranda, Forecast, laporan, alert hujan |
| K4 | Kueri rekursif untuk lineage produk | RM2 |
| K5 | Kontrol akses per peran **di dalam database**: ganti role per transaksi, pembatasan baris | RM4 |
| K6 | Audit trail otomatis lewat trigger | RM4 |
| K7 | Penulisan data rutin dari ETL (insert dan upsert harian per kecamatan) | Job Hidromet, backfill |
| K8 | Open source, gratis, jalan di Windows, dan didukung pustaka Python | Kemampuan GMLS sebagai organisasi relawan |

### 1.2 Daftar pendek (langkah b)

Pedoman Connolly & Begg yang dipakai SKRIPSI.txt menyarankan daftar pendek berisi dua atau tiga produk. Penyaringannya:

| Kandidat | Lolos? | Alasan |
|---|---|---|
| **PostgreSQL + PostGIS** | Ya | Memenuhi K1–K8 di atas kertas |
| **MySQL 8.0** | Ya | DBMS relasional open source paling banyak dipakai. Sejak 8.0 sudah punya CTE rekursif, fungsi spasial geografis, dan role. Inilah pesaing nyata PostgreSQL untuk K1–K8 |
| MongoDB 7 (dokumen) | Dinilai dari fitur saja | Tidak ada FK, sehingga K1 gugur sejak awal. Skemanya juga tidak bisa dibuat setara, jadi angka waktunya tidak bisa dibandingkan dengan adil |
| Neo4j (graph) | Tidak | Hanya cocok untuk K4. Itu pun cukup ditangani `WITH RECURSIVE` (6 tingkat). K2, K5, dan K6 tidak terpenuhi |
| Oracle, SQL Server | Tidak | Berbayar, atau versi gratisnya dibatasi kapasitas (melanggar K8) |
| MariaDB, SQLite | Tidak | MariaDB adalah turunan MySQL yang sudah berbeda arah, jadi cukup diwakili MySQL. SQLite tidak punya role maupun akses multi-pengguna (K5) |

### 1.3 Urgensinya

1. **Wajib menurut prodi.** "Rekomendasi DBMS" adalah hasil akhir yang diminta (SKRIPSI.txt bagian D). Langkah c (evaluasi produk) dan langkah d (rekomendasi beserta laporan) harus didukung bukti, bukan sekadar pernyataan bahwa PostgreSQL dipilih.
2. **Pilihan ini paling mahal untuk diubah nanti.** Skema, VIEW per peran, GRANT, trigger audit, kueri spasial, dan ETL semuanya ditulis dalam dialek DBMS tertentu. Kalau pilihannya salah, sebagian besar project harus ditulis ulang.
3. **MySQL adalah pembanding yang paling mungkin diajukan.** Sistem milik GMLS sendiri (SIGAP DESA) memakai PHP/MySQL. Penguji maupun GMLS wajar bertanya kenapa tidak memakai MySQL saja. Benchmark inilah jawabannya.
4. **Perbandingan yang adil hanya bisa antar sesama relasional.** Dengan skema, data, dan kueri yang sama, perbedaan yang muncul benar-benar berasal dari DBMS-nya. Membandingkan dengan MongoDB atau Neo4j berarti membandingkan model data, bukan produk.

---

## 2. Metode evaluasi (langkah c)

### 2.1 Ketentuan umum

| Aspek | Ketentuan |
|---|---|
| Data | Data sintetis deterministik (seed 20260929), dibuat sama persis untuk kedua DBMS: 28 kecamatan, 76.720 observasi (3 tahun × 10 kecamatan × 7 band), 1.076 alert, 150 kejadian, 5.182 produk, 3.982 lineage. **Bukan data produksi** |
| Skema | Setara: tipe, PK/FK, UNIQUE, CHECK, dan index yang sama, termasuk index spasial di kedua DBMS |
| Validasi hasil | Jumlah baris setiap kueri sama di kedua DBMS. Luas Q3 dicocokkan per kecamatan, selisih maksimum 0,1% |
| Lingkungan | Satu mesin, berjalan berurutan (rincian di §2.4). PostgreSQL 18.6 + PostGIS 3.6.2 dan MySQL 8.0.40 Community, **data keduanya di disk yang sama** |
| Konfigurasi | Bawaan, tanpa tuning. Buffer kedua DBMS sama-sama 128 MB (`shared_buffers` dan `innodb_buffer_pool_size`) |
| Driver | psycopg2 2.9 (C) untuk PostgreSQL. Untuk MySQL: pymysql (Python murni) dan mysqlclient 2.3 (C). Lihat §2.3 |

### 2.2 Daftar uji

| Kelompok | Uji | Ukuran | Pengulangan |
|---|---|---|---|
| **A. Kueri inti** | Q1 pivot per kecamatan, Q2 tren 30 hari, Q3 irisan spasial, Q4 evaluasi alert, Q5 lineage rekursif | Median dan p95 latensi (ms) | 5 pemanasan + 30 ukur per kueri, **3 run terpisah** |
| **B. Fitur** | F1 `SET ROLE` per transaksi, F2 row-level security, F3 trigger audit JSON | Didukung / Sebagian / Tidak | Uji fungsional |
| **C. Skalabilitas (E1)** | Q1, Q2, dan Q6 (rekap bulanan seluruh tabel) pada observasi ×1, ×10, ×30 (76 ribu → 2,3 juta baris) | Latensi, ukuran tabel dan index (MB) | 3 pemanasan + 15 ukur per titik |
| **D. Konkurensi (E2)** | 1, 4, 8, 16 klien serentak menjalankan campuran Q1 dan Q2 dengan parameter acak | Throughput (kueri/detik), latensi median dan p95 | 10 detik per titik (setelah 1 detik pemanasan) |
| **E. Tulis/ETL (E3)** | Insert batch 50.000 baris; upsert 20.000 baris (50% konflik). Keduanya INSERT multi-baris per 1.000 baris | Baris/detik | 3 ulangan, median |

Totalnya: 5 kueri inti × 3 run × 30 pengukuran, 3 kueri × 3 skala × 2 driver, 4 tingkat konkurensi × 2 driver, dan 2 uji tulis × 2 driver. Seluruhnya sekitar 700 ribu eksekusi kueri.

### 2.3 Koreksi di tengah pengujian

Tiga hal ditemukan dan dibetulkan supaya perbandingannya adil. Semuanya dicatat di sini karena memengaruhi cara membaca hasil.

1. **Q3 MySQL error 3516** saat ditulis setara secara langsung (lihat §3.2). Kuerinya ditulis ulang khusus untuk MySQL.
2. **Upsert MySQL lewat pymysql semula dikirim per baris.** Sintaks alias `AS new` tidak dikenali pymysql sebagai INSERT multi-baris, sehingga hasil awalnya 5,0 detik. Setelah diganti ke `VALUES(value)`, hasilnya 1,1 detik. Angka 5,0 detik tidak dipakai.
3. **Driver pymysql membuat MySQL tampak jauh lebih lambat di uji konkurensi.** Karena pymysql ditulis murni dalam Python, uji E1, E2, dan E3 diulang dengan driver C (mysqlclient). Hasilnya berbeda besar untuk konkurensi (§3.5), jadi **angka yang dipakai untuk kesimpulan adalah angka dari driver C**.
4. **Disk tidak setara pada pengujian 8 Oktober** (PostgreSQL di SSD, MySQL di HDD). Seluruh pengujian diulang dengan klaster PostgreSQL khusus benchmark di HDD yang sama dengan MySQL (§2.4–§2.5). Angka 8 Oktober tidak dipakai lagi untuk kesimpulan.

### 2.4 Perangkat keras dan lingkungan uji

| Komponen | Spesifikasi |
|---|---|
| Komputer | Dell Inspiron 3668 (desktop) |
| CPU | Intel Core i7-7700 @ 3,60 GHz: 4 core, 8 thread |
| RAM | 32 GB (2 × 16 GB DDR4-2400) |
| Disk 0 (C:) | SK hynix SC311 SSD SATA 128 GB (sistem operasi; **tidak dipakai** untuk data uji) |
| Disk 1 (D:) | Toshiba DT01ACA100 HDD SATA 1 TB (7.200 rpm), **data kedua DBMS** |
| Sistem operasi | Windows 10 Pro 22H2 (10.0.19045) |
| Klien uji | Python 3.10.11 di mesin yang sama; koneksi lewat localhost (TCP) |
| PostgreSQL | 18.6 + PostGIS 3.6.2, klaster benchmark terpisah (`initdb`, port 5433, dijalankan `pg_ctl`), data di **D:\_bench_pg\data (HDD)**. PostgreSQL produksi (port 5432, C:) tidak dipakai |
| MySQL | 8.0.40 Community ZIP portable, port 3307, data di **D:\_bench_mysql\data (HDD)** |
| Konfigurasi | Bawaan kedua DBMS. Buffer 128 MB; PostgreSQL `max_parallel_workers_per_gather` = 2, `synchronous_commit` = on, `fsync` = on; MySQL `innodb_flush_log_at_trx_commit` = 1, `sync_binlog` = 1. Keduanya mem-*flush* log ke disk setiap COMMIT |
| Bukti | `environment.json` mencatat `data_directory`, nama disk fisik, dan jenis media (SSD/HDD) tiap DBMS yang dibaca saat uji; `storage_equal` = true |

> **Kesetaraan penyimpanan.** Kedua data directory berada di HDD yang sama, sehingga selisih pada uji tulis (E3), proses memperbesar tabel, dan Q6 ×30 kini bisa diatribusikan ke DBMS. `run.py` menolak berjalan bila `BENCH_REQUIRE_SAME_DISK=1` dan kedua DBMS tidak di disk yang sama.
>
> HDD dipilih (bukan SSD) karena SSD C: hanya tersisa ±6 GB, tidak cukup untuk dua DBMS pada skala ×30 beserta log-nya. Angka absolut uji tulis karena itu lebih rendah daripada di SSD, tetapi perbandingannya adil.

### 2.5 Pengaruh disk: hasil 8 Oktober (SSD vs HDD) dibanding 6 November (HDD vs HDD)

| Uji | Selisih 8 Okt (PG SSD, MySQL HDD) | Selisih 6 Nov (keduanya HDD) | Terpengaruh disk? |
|---|---|---|---|
| Q3 irisan spasial | 17× | 16× | Tidak |
| Q4 evaluasi alert | 9× | 14× | Tidak |
| Q6 rekap ×30 (driver C) | 8,5× (pymysql) | **2,9×** | **Ya, besar** |
| Waktu memperbesar ×30 | 293 vs 40 detik (7×) | 290 vs 29 detik (10×) | Tidak |
| Insert batch 50.000 baris | 8,2× | **4,4×** | **Ya** |
| Upsert 20.000 baris | 1,9× | **1,3×** | **Ya** |
| Konkurensi (driver C) | PG unggul 13–26% | PG unggul 11–35% | Tidak |
| Fitur F1–F3 | sama | sama | Tidak |

Jadi kecurigaan pada §6 versi lama terbukti: sekitar dua pertiga keunggulan Q6 ×30 dan sekitar separuh keunggulan insert berasal dari SSD, bukan dari PostgreSQL. Arsip hasil lama ada di `benchmark/results/arsip_2026-10-08_pg-ssd_mysql-hdd/`.

---

## 3. Hasil

### 3.1 Kueri inti (milidetik, lebih kecil lebih baik)

Median dari run terakhir. Kolom "rentang 3 run" menunjukkan kestabilan hasil.

| Kueri | Isi | PostgreSQL | rentang 3 run | MySQL | rentang 3 run | MySQL ÷ PG |
|---|---|---|---|---|---|---|
| Q1 | Pivot 5 band per kecamatan, satu tanggal | **0,45** | 0,45–0,47 | 0,87 | 0,87–1,49 | 1,9× |
| Q2 | Tren 30 hari satu kecamatan | **0,31** | 0,30–0,31 | 0,68 | 0,67–0,68 | 2,2× |
| Q3 | Irisan poligon + luas geodesik | **1,15** | 1,14–1,15 | 18,63 | 18,3–18,6 | **16×** |
| Q4 | Evaluasi alert: hit / miss / false alarm | **1,06** | 0,99–1,06 | 15,13 | 14,8–15,1 | **14×** |
| Q5 | Lineage 6 tingkat (`WITH RECURSIVE`) | 0,65 | 0,62–0,66 | **0,45** | 0,45–0,46 | 0,7× (**MySQL lebih cepat**) |

**Cara membaca angka ini:**

- Kueri inti diukur lewat pymysql. Untuk kueri di bawah 1 ms (Q1, Q2), sebagian selisihnya berasal dari driver. Uji konkurensi dengan 1 klien memakai driver C menunjukkan selisih sebenarnya untuk Q1/Q2 hanya sekitar **1,35×** (§3.4).
- Q3 dan Q4 dikonfirmasi lewat `EXPLAIN ANALYZE`: waktu eksekusi di dalam server MySQL sendiri sudah sekitar 17 ms, sedangkan PostgreSQL 0,6–0,8 ms. Jadi selisihnya berasal dari server, bukan dari driver.
- Q5 lebih cepat di MySQL walaupun lewat driver yang lebih lambat. Ini keunggulan nyata MySQL, meskipun keduanya sama-sama di bawah 1 ms.

**Penyebab selisih Q3 dan Q4** (dari `explain_*_Q*.txt`):

- **Q4.** PostgreSQL menghitung CTE `strong`, `ev`, dan `pairs` sekali, lalu memakai hasilnya. MySQL menjalankan `NOT IN (SELECT … FROM pairs)` sebagai *nested loop antijoin* yang menghitung ulang join di dalamnya.
- **Q3.** Kedua DBMS memakai index spasial untuk menyaring 12 kecamatan kandidat. Yang mahal di MySQL adalah menghitung irisan geodesik per baris.

### 3.2 Temuan kompatibilitas spasial (Q3)

Kueri Q3 yang ditulis setara secara langsung **gagal di MySQL** dengan galat 3516: `POLYGON/MULTIPOLYGON value is a geometry of unexpected type GEOMCOLLECTION in st_area`.

Penyebabnya, `ST_Intersection` geografis di MySQL menyisakan titik-titik akibat presisi di tepi irisan pada 6 dari 12 kecamatan, sehingga hasilnya berupa GeometryCollection. `ST_Area` MySQL menolak tipe ini, sedangkan PostGIS menerimanya.

Supaya Q3 tetap bisa dibandingkan, versi MySQL ditulis ulang: hanya luas anggota poligon yang dijumlahkan, memakai deret 1..10 karena MySQL 8.0 tidak punya `ST_CollectionExtract`. Sebagian waktu Q3 MySQL berasal dari penyiasatan ini. Tetapi penyiasatan itu memang **harus** ada di MySQL, termasuk di setiap kueri luas pada kode aplikasi.

### 3.3 Skalabilitas (E1)

Tabel observasi diperbesar 10× dan 30×. Waktu dalam milidetik, MySQL lewat driver C (mysqlclient); hasil lewat pymysql ada di `extended_scaling.csv` dan polanya sama (Q6 ×30: 591 vs 1.636 ms).

| Skala | Baris | Q1 PG | Q1 MySQL | Q2 PG | Q2 MySQL | **Q6 PG** | **Q6 MySQL** | Q6 MySQL ÷ PG |
|---|---|---|---|---|---|---|---|---|
| ×1 | 76.720 | 0,50 | 0,62 | 0,25 | 0,39 | 9 | 33 | 3,6× |
| ×10 | 767.200 | 0,55 | 0,88 | 0,29 | 0,42 | 187 | 334 | 1,8× |
| ×30 | 2.301.600 | 0,50 | 1,63 | 0,27 | 1,28 | **579** | **1.666** | **2,9×** |

| Skala | PG data + index (MB) | MySQL data + index (MB) | Waktu memperbesar PG | Waktu memperbesar MySQL |
|---|---|---|---|---|
| ×1 | 5,0 + 6,3 = 11,3 | 4,5 + 9,0 = 13,5 | – | – |
| ×10 | 47,6 + 62,1 = 109,7 | 38,6 + 68,2 = 106,8 | 12 detik | 74 detik |
| ×30 | 142,7 + 186,5 = 329,2 | 113,7 + 198,4 = 312,1 | 29 detik | 290 detik |

**Temuan:**

- **Kueri ber-index (Q1, Q2) tetap di bawah 2 ms di kedua DBMS** sampai 2,3 juta baris. PostgreSQL datar; MySQL naik sedikit di ×30 (Q1 0,88 → 1,63 ms) karena data + index sudah melebihi buffer 128 MB. Dashboard harian tidak akan melambat di DBMS mana pun.
- **Kueri rekap seluruh tabel (Q6) di ×30**: PostgreSQL 0,58 detik, MySQL 1,67 detik (2,9×). p95 MySQL melonjak sampai 6,0 detik, sedangkan PostgreSQL stabil (0,60 detik). Selisih ini jauh lebih kecil daripada 8,5× pada pengujian SSD vs HDD (§2.5), tetapi tetap ada: PostgreSQL memakai eksekusi paralel (2 worker bawaan) dan cache sistem operasi. Q6 mewakili laporan bulanan dan halaman Forecast untuk rentang panjang.
- **Memperbesar tabel (INSERT … SELECT) 10× lebih cepat di PostgreSQL** walaupun di disk yang sama.
- **Ukuran penyimpanan hampir sama** (selisih sekitar 5%). Data mentah MySQL lebih ringkas, tetapi index-nya lebih besar.

### 3.4 Konkurensi (E2): driver C untuk kedua DBMS

Campuran Q1 dan Q2, durasi 10 detik per titik, tanpa galat di semua titik.

| Klien | PG kueri/detik | PG p95 (ms) | MySQL kueri/detik | MySQL p95 (ms) | PG ÷ MySQL |
|---|---|---|---|---|---|
| 1 | 2.255 | 0,63 | 1.675 | 0,79 | 1,35× |
| 4 | 7.275 | 0,76 | 6.583 | 0,87 | 1,11× |
| 8 | 8.204 | 1,39 | 7.121 | 1,68 | 1,15× |
| 16 | 7.974 | 3,57 | 7.045 | 4,11 | 1,13× |

**Temuan:** keduanya naik hampir linear sampai 4 klien, lalu jenuh di sekitar 8 klien (sesuai 8 thread CPU). PostgreSQL unggul **11–35%** (terbesar pada 1 klien, 11–15% saat serentak). Selisih ini **kecil**, dan kedua DBMS jauh melampaui kebutuhan GMLS (puluhan pengguna, bukan ribuan kueri per detik). Hasil ini praktis sama dengan pengujian 8 Oktober, karena data uji konkurensi sudah di memori.

### 3.5 Efek driver (pymysql vs mysqlclient)

| Uji | MySQL + pymysql | MySQL + mysqlclient | PostgreSQL + psycopg2 |
|---|---|---|---|
| Konkurensi 16 klien (kueri/detik) | 1.374 | 7.045 | 7.974 |
| Insert batch (baris/detik) | 7.638 | 7.516 | 32.940–47.275 |
| Upsert (baris/detik) | 20.350 | 16.070 | 20.312–44.148 |

Driver Python murni memangkas throughput MySQL sampai 5,1×. **Kalau MySQL dipakai dengan Python, mysqlclient wajib dipilih.** Sebaliknya, lambatnya insert MySQL tetap muncul dengan kedua driver, jadi itu berasal dari server.

### 3.6 Tulis/ETL (E3): median 3 ulangan

| Uji | PostgreSQL | MySQL (mysqlclient) | PG ÷ MySQL |
|---|---|---|---|
| Insert batch 50.000 baris | 1,52 detik (**32.940 baris/detik**) | 6,65 detik (7.516 baris/detik) | 4,4× |
| Upsert 20.000 baris, 50% konflik | 0,99 detik (**20.312 baris/detik**) | 1,25 detik (16.070 baris/detik) | 1,3× |

Angka PostgreSQL di HDD bervariasi antar-sesi: pada sesi pymysql, PostgreSQL mencatat 1,06 detik (insert) dan 0,45 detik (upsert), yaitu 6,2× dan 2,2× terhadap MySQL. Jadi rentang yang jujur adalah **insert 4,4–6,2× dan upsert 1,3–2,2×**. Dibanding pengujian SSD vs HDD (8,2× dan 1,9×), keunggulan insert PostgreSQL menyusut kira-kira separuh, tetapi tidak hilang.

Pola yang sama terlihat saat memperbesar tabel di E1: PostgreSQL 29 detik, MySQL 290 detik. Job Hidromet harian hanya menulis ratusan baris, jadi perbedaan ini **terasa di backfill** (bertahun-tahun data sekaligus), bukan di operasi harian.

### 3.7 Fitur keamanan dan audit

| Fitur | PostgreSQL | MySQL 8.0 | MongoDB 7 (fitur saja) |
|---|---|---|---|
| F1: `SET ROLE` per transaksi | **Didukung.** `SET LOCAL ROLE` mempersempit hak (DELETE ditolak) dan otomatis kembali setelah COMMIT/ROLLBACK | **Sebagian.** `SET ROLE` berlaku per sesi. DELETE **tetap diizinkan**, karena hak role ditambahkan ke hak akun, bukan menggantikannya. Role juga tidak kembali setelah ROLLBACK | Tidak didukung |
| F2: Row-level security | **Didukung** (`CREATE POLICY`, terverifikasi 99 dari 150 baris) | **Tidak didukung.** Harus diemulasi lewat VIEW + DEFINER | Tidak didukung |
| F3: Trigger audit OLD/NEW sebagai JSON | **Didukung.** Satu fungsi `to_jsonb(OLD/NEW)` untuk semua tabel | **Sebagian.** `JSON_OBJECT` harus menyebut setiap kolom di setiap tabel | Sebagian (change streams; audit log hanya di edisi Enterprise) |
| Foreign key | Ya | Ya | Tidak ada |

Arsitektur hak akses Orbit-U (`SET LOCAL ROLE monitor_<role>` per request, lihat [INTERFACE.md](INTERFACE.md) §3.2) bergantung pada F1. Hasil F1 di MySQL berarti akun koneksi API harus berhak minimal dan setiap peran butuh koneksi sendiri. Kalau tidak, pembatasan per peran tidak berlaku di level database.

### 3.8 Skor terbobot

Bobot diturunkan dari kerangka acuan §1.1. Skala 1–5. Dibanding pengujian 8 Oktober, skor MySQL untuk analitik dan skala naik dari 2 ke 3 karena selisih Q6 ×30 menyusut dari 8,5× ke 2,9× setelah disk disetarakan; total MySQL naik dari 2,90 ke 3,05. Skor lain tetap.

| Kriteria | Bobot | PostgreSQL | MySQL 8.0 | Dasar |
|---|---|---|---|---|
| Keamanan per peran dan audit (K5, K6) | 25% | 5 | 2 | §3.7 |
| Spasial (K2) | 20% | 5 | 2 | Q3 16×, galat 3516 |
| Analitik dan skala (K3) | 15% | 5 | 3 | Q4 14×, Q6 ×30 2,9× (disk setara) |
| Tulis/ETL (K7) | 10% | 5 | 3 | Insert 4,4–6,2×, upsert 1,3–2,2× |
| Konkurensi baca | 10% | 5 | 4 | Selisih 11–35% |
| Integritas relasional dan rekursif (K1, K4) | 10% | 5 | 5 | Keduanya punya FK; Q5 MySQL lebih cepat, tetapi keduanya < 1 ms |
| Biaya, ekosistem, keakraban pengguna (K8) | 10% | 4 | 5 | Keduanya gratis; MySQL lebih umum di hosting murah dan sudah dipakai GMLS |
| **Total** | 100% | **4,90** | **3,05** | |

---

## 4. Rekomendasi (langkah d)

**Rekomendasi: PostgreSQL + PostGIS**, sesuai dengan yang sudah dipakai project.

Penentunya bukan selisih milidetik di kueri sederhana. Untuk kueri ber-index dan beban baca serentak, kedua DBMS sama-sama memadai. Penentunya ada tiga:

1. Kontrol akses per peran di dalam database (RM4).
2. Kueri spasial.
3. Kueri analitik saat data membesar.

Di ketiganya, MySQL kalah jauh atau butuh penyiasatan.

---

## 5. Kesimpulan

### 5.1 Keunggulan PostgreSQL dibanding MySQL pada project ini

1. **Keamanan berlapis di database (RM4).** Hanya PostgreSQL yang bisa mempersempit hak lewat `SET LOCAL ROLE` dan otomatis memulihkannya di akhir transaksi. PostgreSQL juga punya row-level security dan trigger audit generik satu fungsi untuk semua tabel. Di MySQL, ketiganya tidak ada atau harus ditulis manual per tabel. Ini satu-satunya keunggulan yang **tidak bisa ditutup** dengan menambah hardware.
2. **Spasial.** Irisan kecamatan dan luas geodesik 16× lebih cepat dan tidak perlu penyiasatan. Di MySQL, kueri setara langsung error dan setiap kueri luas harus ditulis ulang.
3. **Kueri analitik.** Evaluasi alert 14× lebih cepat karena CTE dihitung sekali. Rekap bulanan pada 2,3 juta baris 2,9× lebih cepat (0,58 detik vs 1,67 detik) dengan p95 yang jauh lebih stabil (0,60 vs 6,0 detik). Selisihnya membesar seiring bertambahnya data, padahal angka per kecamatan di project ini **disimpan selamanya**.
4. **Penulisan ETL.** Insert batch 4,4–6,2× lebih cepat dan upsert 1,3–2,2× lebih cepat di disk yang sama. Backfill bertahun-tahun data selesai jauh lebih singkat.
5. **Konkurensi baca sedikit lebih tinggi**, 11–35%. Ini keunggulan kecil yang tidak menentukan.

### 5.2 Keunggulan MySQL dibanding PostgreSQL pada project ini

1. **Kueri rekursif lineage (Q5) lebih cepat:** 0,45 ms vs 0,65 ms. Dalam praktik tidak terasa, karena keduanya di bawah 1 ms.
2. **Penyimpanan data mentah lebih ringkas**, sekitar 20% lebih kecil. Tetapi index-nya lebih besar, sehingga totalnya hanya selisih sekitar 5%.
3. **Lebih akrab bagi GMLS.** SIGAP DESA sudah memakai PHP/MySQL, jadi pengelola tidak perlu belajar DBMS baru, dan hosting murah lebih banyak yang menyediakan MySQL.
4. **Kueri ber-index dan baca serentak sama-sama memadai.** Untuk halaman dashboard harian, MySQL tidak menjadi hambatan.

### 5.3 Ringkasan

Keunggulan MySQL bersifat **operasional dan sosial**: akrab, mudah dihosting, dan ringkas. Keunggulan PostgreSQL bersifat **fungsional**: fitur yang diwajibkan rumusan masalah (RM4, spasial, analitik) hanya terpenuhi penuh di PostgreSQL.

Karena itu PostgreSQL direkomendasikan untuk Orbit-U. MySQL tetap tepat untuk SIGAP DESA, yang tidak butuh spasial dan pembatasan akses di level database. Kedua sistem bisa berdampingan.

---

## 6. Keterbatasan

- **Disk setara, tetapi HDD (§2.4).** Kedua DBMS kini di disk yang sama. Karena SSD tidak cukup ruang, pengujian dilakukan di HDD; urutan hasil di SSD diperkirakan sama, tetapi angka absolut uji tulis akan lebih tinggi. Uji tulis PostgreSQL di HDD bervariasi antar-sesi (§3.6), sehingga dilaporkan sebagai rentang.
- PostgreSQL benchmark memakai klaster terpisah (port 5433) dengan binari yang sama dengan produksi, bukan service produksi.
- MySQL bawaan menulis binary log (`sync_binlog` = 1), yang tidak punya padanan langsung di PostgreSQL. Ini bagian dari konfigurasi bawaan yang diuji "apa adanya".
- Data sintetis. Skala terbesar yang diuji 2,3 juta baris; data produksi berisi 72.850 baris `region_observations` (24 Okt 2026).
- Konfigurasi bawaan tanpa tuning. Dengan `innodb_buffer_pool_size` lebih besar, Q1/Q2 dan Q6 MySQL di ×30 kemungkinan membaik. Uji ini mengukur perilaku "apa adanya", sesuai kondisi GMLS yang tidak punya DBA.
- Klien dan server di mesin yang sama. Klien Python ikut memakai CPU saat uji konkurensi.
- Kueri inti untuk MySQL diukur lewat pymysql. Selisih Q1/Q2 di bawah 1 ms sebagian berasal dari driver (§3.1). Q3 dan Q4 didominasi waktu server. E1 diukur dengan kedua driver.
- MongoDB tidak diukur waktunya karena skemanya tidak setara (§1.2).

## 7. Cara mengulang

Kedua DBMS harus memakai disk fisik yang sama. Siapkan klaster PostgreSQL khusus benchmark di disk tempat data MySQL berada (sekali saja):

```
"C:\Program Files\PostgreSQL\18\bin\initdb" -D D:\_bench_pg\data -U postgres -A trust -E UTF8 --locale=C
"C:\Program Files\PostgreSQL\18\bin\pg_ctl" -D D:\_bench_pg\data -o "-p 5433 -c listen_addresses=127.0.0.1" -l D:\_bench_pg\pg.log start
```

MySQL 8.0.40 ZIP portable di `D:\_bench_mysql`, dijalankan manual di port 3307 (bukan service Windows):

```
D:\_bench_mysql\mysql-8.0.40-winx64\bin\mysqld --basedir=D:\_bench_mysql\mysql-8.0.40-winx64 --datadir=D:\_bench_mysql\data --port=3307 --bind-address=127.0.0.1 --console
```

Lalu:

```
venv\Scripts\pip install pymysql mysqlclient
venv\Scripts\python benchmark\generate.py
set BENCH_PG_HOST=127.0.0.1
set BENCH_PG_PORT=5433
set BENCH_PG_PASSWORD=
set BENCH_MYSQL_PORT=3307
set BENCH_REQUIRE_SAME_DISK=1
set PYTHONIOENCODING=utf-8

venv\Scripts\python benchmark\run.py --engine all            :: A, B (ulang 3×; salinan per run di results\run_inti\)
venv\Scripts\python benchmark\extended.py                    :: C, D, E dengan pymysql
venv\Scripts\python benchmark\run.py --engine all            :: kembalikan ke skala ×1
set BENCH_MYSQL_DRIVER=mysqlclient
set BENCH_SUFFIX=_mysqlclient
venv\Scripts\python benchmark\extended.py                    :: C, D, E dengan driver C
venv\Scripts\python benchmark\run.py --engine all            :: kembalikan ke skala ×1
```

Tanpa `BENCH_PG_*`, skrip memakai `DB_*` dari `.env` (PostgreSQL produksi di C:), dan `environment.json` akan mencatat `storage_equal` = false.

Berkas hasil:

| Berkas | Isi |
|---|---|
| `timing.csv`, `features.csv`, `explain_*.txt` | Kueri inti dan fitur |
| `extended_scaling.csv`, `extended_scaling_mysqlclient.csv` | Skalabilitas lewat pymysql dan driver C |
| `extended_concurrency.csv`, `extended_write.csv` | Konkurensi dan tulis lewat pymysql |
| `extended_*_mysqlclient.csv` | Skala, konkurensi, dan tulis lewat driver C (**dipakai untuk kesimpulan**) |
| `run_inti/timing_run1..3.csv` | Kueri inti per run (rentang 3 run) |
| `environment.json` | Versi, konfigurasi, data directory, disk fisik, dan jenis media tiap DBMS |
| `arsip_2026-10-08_pg-ssd_mysql-hdd/` | Hasil lama yang disknya tidak setara (hanya untuk §2.5) |

## 8. Kode pengujian

Kode lengkap ada di folder `benchmark/`:

| Berkas | Baris | Isi |
|---|---|---|
| `generate.py` | 162 | Pembangkit data sintetis (seed tetap) |
| `engines.py` | 317 | Skema setara, pemuat data, kueri Q1–Q5 per dialek, uji fitur F1–F3 |
| `run.py` | 234 | Pengukuran kueri inti dan fitur |
| `extended.py` | 278 | Skalabilitas, konkurensi, tulis |

Saran penempatan di naskah:

- **Badan bab (DBMS Selection):** cukup cuplikan yang menunjukkan perbedaan dialek, yaitu Q3 (spasial) dan Q4 (evaluasi alert) versi PostgreSQL berdampingan dengan versi MySQL, beserta uji F1 (`SET LOCAL ROLE` vs `SET ROLE`). Cuplikan ini yang membuktikan bahwa perbandingannya setara.
- **Lampiran:** keempat berkas di atas secara utuh, atau tautan ke repositori dengan nomor commit, supaya penguji bisa mengulang pengujian.
- **Selalu sertakan:** perintah menjalankan (§7), spesifikasi hardware (§2.4), dan berkas CSV hasil. Kode tanpa data hasil dan lingkungan tidak bisa diverifikasi.
