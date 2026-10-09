# Perbandingan DBMS: PostgreSQL vs MySQL 8.0

Dokumen ini menjawab tahap **DBMS Selection** di SKRIPSI.txt (langkah a–d) dan hasil akhir **Rekomendasi DBMS**.

Pengujian dijalankan 8 Oktober 2026 dengan dua skrip:

- `benchmark/run.py`: kueri inti Q1–Q5 dan fitur F1–F3.
- `benchmark/extended.py`: skalabilitas, konkurensi, dan tulis.

Angka mentahnya ada di `benchmark/results/`.

---

## 1. Kenapa yang dibandingkan hanya PostgreSQL dan MySQL?

### 1.1 Kerangka acuan (langkah a)

DBMS dinilai dari apa yang benar-benar dikerjakan sistem ini. Kebutuhan itu diambil dari rumusan masalah (RM1–RM4) dan skema yang sudah berjalan:

| Kode | Kebutuhan | Asal |
|---|---|---|
| K1 | Model relasional dengan FK dan constraint yang ditegakkan DBMS: 38 tabel, 12 master | RM1, prasyarat prodi "database terstruktur" |
| K2 | Kueri spasial: irisan poligon kecamatan dan luas geodesik | AOI = gabungan kecamatan COD-AB |
| K3 | Agregasi deret waktu per kecamatan per band (pivot, tren, rekap bulanan) | Dashboard, Diagram, laporan, alert hujan |
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
| Lingkungan | Satu mesin, berjalan berurutan (rincian di §2.4). PostgreSQL 18.6 + PostGIS 3.6.2 dan MySQL 8.0.40 Community |
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

Totalnya: 5 kueri inti × 3 run × 30 pengukuran, 3 kueri × 3 skala, 4 tingkat konkurensi × 2 driver, dan 2 uji tulis × 2 driver. Seluruhnya sekitar 700 ribu eksekusi kueri.

### 2.3 Koreksi di tengah pengujian

Tiga hal ditemukan dan dibetulkan supaya perbandingannya adil. Semuanya dicatat di sini karena memengaruhi cara membaca hasil.

1. **Q3 MySQL error 3516** saat ditulis setara secara langsung (lihat §3.2). Kuerinya ditulis ulang khusus untuk MySQL.
2. **Upsert MySQL lewat pymysql semula dikirim per baris.** Sintaks alias `AS new` tidak dikenali pymysql sebagai INSERT multi-baris, sehingga hasil awalnya 5,0 detik. Setelah diganti ke `VALUES(value)`, hasilnya 1,1 detik. Angka 5,0 detik tidak dipakai.
3. **Driver pymysql membuat MySQL tampak jauh lebih lambat di uji konkurensi.** Karena pymysql ditulis murni dalam Python, uji E2 dan E3 diulang dengan driver C (mysqlclient). Hasilnya berbeda besar untuk konkurensi (§3.5), jadi **angka yang dipakai untuk kesimpulan adalah angka dari driver C**.

### 2.4 Perangkat keras dan lingkungan uji

| Komponen | Spesifikasi |
|---|---|
| Komputer | Dell Inspiron 3668 (desktop) |
| CPU | Intel Core i7-7700 @ 3,60 GHz: 4 core, 8 thread |
| RAM | 32 GB (2 × 16 GB DDR4-2400) |
| Disk 0 (C:) | SK hynix SC311 SSD SATA 128 GB, sisa ruang ±4 GB saat uji |
| Disk 1 (D:) | Toshiba DT01ACA100 HDD SATA 1 TB (7.200 rpm) |
| Sistem operasi | Windows 10 Pro 22H2 (10.0.19045) |
| Klien uji | Python 3.10.11 di mesin yang sama; koneksi lewat localhost (TCP) |
| PostgreSQL | 18.6 + PostGIS 3.6.2, service Windows, data di **C:\Program Files\PostgreSQL\18\data (SSD)** |
| MySQL | 8.0.40 Community ZIP portable, data di **D:\_bench_mysql\data (HDD)** |
| Konfigurasi | Bawaan kedua DBMS. Buffer 128 MB; PostgreSQL `max_parallel_workers_per_gather` = 2; MySQL `innodb_flush_log_at_trx_commit` = 1 |

> **Ketidaksetaraan penyimpanan.** Data PostgreSQL berada di SSD, sedangkan data MySQL di HDD. Ini memengaruhi uji yang bergantung pada disk, yaitu tulis/ETL (E3), proses memperbesar tabel, dan Q6 di ×30 yang datanya melebihi buffer. Untuk uji-uji ini, selisih pada §3.3 dan §3.6 **belum bisa diatribusikan sepenuhnya ke DBMS**.
>
> Kueri yang datanya sudah di memori (Q1–Q5, E2 konkurensi, E1 ×1 dan ×10 untuk Q1/Q2) dan fitur F1–F3 tidak bergantung pada disk, sehingga tidak terpengaruh. Untuk hasil yang setara, uji tulis dan uji skala perlu diulang dengan kedua data directory di disk yang sama (§6).

---

## 3. Hasil

### 3.1 Kueri inti (milidetik, lebih kecil lebih baik)

Median dari run terakhir. Kolom "rentang 3 run" menunjukkan kestabilan hasil.

| Kueri | Isi | PostgreSQL | rentang 3 run | MySQL | rentang 3 run | MySQL ÷ PG |
|---|---|---|---|---|---|---|
| Q1 | Pivot 5 band per kecamatan, satu tanggal | **0,45** | 0,45–0,50 | 1,14 | 0,94–1,14 | 2,5× |
| Q2 | Tren 30 hari satu kecamatan | **0,29** | 0,27–0,29 | 0,67 | 0,67–0,83 | 2,3× |
| Q3 | Irisan poligon + luas geodesik | **1,34** | 1,09–1,34 | 22,57 | 20,2–24,0 | **17×** |
| Q4 | Evaluasi alert: hit / miss / false alarm | **1,76** | 1,04–1,76 | 16,64 | 16,6–18,6 | **9×** |
| Q5 | Lineage 6 tingkat (`WITH RECURSIVE`) | 0,82 | 0,62–0,82 | **0,43** | 0,42–0,61 | 0,5× (**MySQL lebih cepat**) |

**Cara membaca angka ini:**

- Kueri inti diukur lewat pymysql. Untuk kueri di bawah 1 ms (Q1, Q2), sebagian selisihnya berasal dari driver. Uji konkurensi dengan 1 klien memakai driver C menunjukkan selisih sebenarnya untuk Q1/Q2 hanya sekitar **1,25×** (§3.4).
- Q3 dan Q4 dikonfirmasi lewat `EXPLAIN ANALYZE`: waktu eksekusi di dalam server MySQL sendiri sudah 19–21 ms. Jadi selisihnya berasal dari server, bukan dari driver.
- Q5 lebih cepat di MySQL walaupun lewat driver yang lebih lambat. Ini keunggulan nyata MySQL, meskipun keduanya sama-sama di bawah 1 ms.

**Penyebab selisih Q3 dan Q4** (dari `explain_*_Q*.txt`):

- **Q4.** PostgreSQL menghitung CTE `strong`, `ev`, dan `pairs` sekali, lalu memakai hasilnya. MySQL menjalankan `NOT IN (SELECT … FROM pairs)` sebagai *nested loop antijoin* yang menghitung ulang join di dalamnya.
- **Q3.** Kedua DBMS memakai index spasial untuk menyaring 12 kecamatan kandidat. Yang mahal di MySQL adalah menghitung irisan geodesik per baris.

### 3.2 Temuan kompatibilitas spasial (Q3)

Kueri Q3 yang ditulis setara secara langsung **gagal di MySQL** dengan galat 3516: `POLYGON/MULTIPOLYGON value is a geometry of unexpected type GEOMCOLLECTION in st_area`.

Penyebabnya, `ST_Intersection` geografis di MySQL menyisakan titik-titik akibat presisi di tepi irisan pada 6 dari 12 kecamatan, sehingga hasilnya berupa GeometryCollection. `ST_Area` MySQL menolak tipe ini, sedangkan PostGIS menerimanya.

Supaya Q3 tetap bisa dibandingkan, versi MySQL ditulis ulang: hanya luas anggota poligon yang dijumlahkan, memakai deret 1..10 karena MySQL 8.0 tidak punya `ST_CollectionExtract`. Sebagian waktu Q3 MySQL berasal dari penyiasatan ini. Tetapi penyiasatan itu memang **harus** ada di MySQL, termasuk di setiap kueri luas pada kode aplikasi.

### 3.3 Skalabilitas (E1)

Tabel observasi diperbesar 10× dan 30×. Waktu dalam milidetik.

| Skala | Baris | Q1 PG | Q1 MySQL | Q2 PG | Q2 MySQL | **Q6 PG** | **Q6 MySQL** | Q6 MySQL ÷ PG |
|---|---|---|---|---|---|---|---|---|
| ×1 | 76.720 | 0,52 | 0,79 | 0,29 | 0,64 | 10 | 39 | 3,8× |
| ×10 | 767.200 | 0,52 | 1,90 | 0,30 | 1,15 | 201 | 397 | 2,0× |
| ×30 | 2.301.600 | 0,53 | 0,97 | 0,30 | 0,75 | **654** | **5.577** | **8,5×** |

| Skala | PG data + index (MB) | MySQL data + index (MB) | Waktu memperbesar PG | Waktu memperbesar MySQL |
|---|---|---|---|---|
| ×1 | 5,0 + 6,3 = 11,3 | 4,5 + 9,0 = 13,5 | – | – |
| ×10 | 47,6 + 62,1 = 109,7 | 38,6 + 68,2 = 106,8 | 14 detik | 65 detik |
| ×30 | 142,7 + 186,5 = 329,2 | 113,7 + 198,4 = 312,1 | 40 detik | 293 detik |

**Temuan:**

- **Kueri ber-index (Q1, Q2) tetap stabil di kedua DBMS** sampai 2,3 juta baris. Dashboard harian tidak akan melambat di DBMS mana pun. (Angka MySQL ×10 yang lebih tinggi dari ×30 adalah variasi pengukuran.)
- **Kueri rekap seluruh tabel (Q6) di MySQL anjlok di ×30**: 5,6 detik, dengan p95 9,8 detik. PostgreSQL tumbuh hampir linear (0,65 detik). Penyebabnya, data + index (312 MB) sudah melebihi buffer 128 MB, sementara PostgreSQL juga memanfaatkan cache sistem operasi dan eksekusi paralel (2 worker bawaan). Q6 mewakili laporan bulanan dan halaman Diagram untuk rentang panjang.
- **Ukuran penyimpanan hampir sama** (selisih sekitar 5%). Data mentah MySQL lebih ringkas, tetapi index-nya lebih besar.

### 3.4 Konkurensi (E2): driver C untuk kedua DBMS

Campuran Q1 dan Q2, durasi 10 detik per titik, tanpa galat di semua titik.

| Klien | PG kueri/detik | PG p95 (ms) | MySQL kueri/detik | MySQL p95 (ms) | PG ÷ MySQL |
|---|---|---|---|---|---|
| 1 | 2.397 | 0,60 | 1.907 | 0,77 | 1,26× |
| 4 | 7.396 | 0,80 | 6.339 | 0,94 | 1,17× |
| 8 | 8.523 | 1,37 | 7.026 | 1,70 | 1,21× |
| 16 | 8.126 | 3,58 | 7.161 | 4,01 | 1,13× |

**Temuan:** keduanya naik hampir linear sampai 4 klien, lalu jenuh di sekitar 8 klien (sesuai 8 thread CPU). PostgreSQL unggul **13–26%**. Selisih ini **kecil**, dan kedua DBMS jauh melampaui kebutuhan GMLS (puluhan pengguna, bukan ribuan kueri per detik).

### 3.5 Efek driver (pymysql vs mysqlclient)

| Uji | MySQL + pymysql | MySQL + mysqlclient | PostgreSQL + psycopg2 |
|---|---|---|---|
| Konkurensi 16 klien (kueri/detik) | 1.557 | 7.161 | 8.126 |
| Insert batch (baris/detik) | 7.823 | 6.122 | 50.361 |
| Upsert (baris/detik) | 17.286 | 21.178 | 41.084 |

Driver Python murni memangkas throughput MySQL sampai 4,6×. **Kalau MySQL dipakai dengan Python, mysqlclient wajib dipilih.** Sebaliknya, lambatnya insert MySQL tetap muncul dengan kedua driver, jadi itu berasal dari server.

### 3.6 Tulis/ETL (E3): median 3 ulangan

| Uji | PostgreSQL | MySQL (mysqlclient) | PG ÷ MySQL |
|---|---|---|---|
| Insert batch 50.000 baris | 0,99 detik (**50.361 baris/detik**) | 8,17 detik (6.122 baris/detik) | 8,2× |
| Upsert 20.000 baris, 50% konflik | 0,49 detik (**41.084 baris/detik**) | 0,94 detik (21.178 baris/detik) | 1,9× |

Pola yang sama terlihat saat memperbesar tabel di E1: PostgreSQL 40 detik, MySQL 293 detik. Job Hidromet harian hanya menulis ratusan baris, jadi perbedaan ini **terasa di backfill** (bertahun-tahun data sekaligus), bukan di operasi harian.

### 3.7 Fitur keamanan dan audit

| Fitur | PostgreSQL | MySQL 8.0 | MongoDB 7 (fitur saja) |
|---|---|---|---|
| F1: `SET ROLE` per transaksi | **Didukung.** `SET LOCAL ROLE` mempersempit hak (DELETE ditolak) dan otomatis kembali setelah COMMIT/ROLLBACK | **Sebagian.** `SET ROLE` berlaku per sesi. DELETE **tetap diizinkan**, karena hak role ditambahkan ke hak akun, bukan menggantikannya. Role juga tidak kembali setelah ROLLBACK | Tidak didukung |
| F2: Row-level security | **Didukung** (`CREATE POLICY`, terverifikasi 99 dari 150 baris) | **Tidak didukung.** Harus diemulasi lewat VIEW + DEFINER | Tidak didukung |
| F3: Trigger audit OLD/NEW sebagai JSON | **Didukung.** Satu fungsi `to_jsonb(OLD/NEW)` untuk semua tabel | **Sebagian.** `JSON_OBJECT` harus menyebut setiap kolom di setiap tabel | Sebagian (change streams; audit log hanya di edisi Enterprise) |
| Foreign key | Ya | Ya | Tidak ada |

Arsitektur hak akses Orbit-U (`SET LOCAL ROLE monitor_<role>` per request, lihat [INTERFACE.md](INTERFACE.md) §3.2) bergantung pada F1. Hasil F1 di MySQL berarti akun koneksi API harus berhak minimal dan setiap peran butuh koneksi sendiri. Kalau tidak, pembatasan per peran tidak berlaku di level database.

### 3.8 Skor terbobot

Bobot diturunkan dari kerangka acuan §1.1. Skala 1–5.

| Kriteria | Bobot | PostgreSQL | MySQL 8.0 | Dasar |
|---|---|---|---|---|
| Keamanan per peran dan audit (K5, K6) | 25% | 5 | 2 | §3.7 |
| Spasial (K2) | 20% | 5 | 2 | Q3 17×, galat 3516 |
| Analitik dan skala (K3) | 15% | 5 | 2 | Q4 9×, Q6 ×30 8,5× |
| Tulis/ETL (K7) | 10% | 5 | 3 | Insert 8×, upsert 2× |
| Konkurensi baca | 10% | 5 | 4 | Selisih 13–26% |
| Integritas relasional dan rekursif (K1, K4) | 10% | 5 | 5 | Keduanya punya FK; Q5 MySQL lebih cepat, tetapi keduanya < 1 ms |
| Biaya, ekosistem, keakraban pengguna (K8) | 10% | 4 | 5 | Keduanya gratis; MySQL lebih umum di hosting murah dan sudah dipakai GMLS |
| **Total** | 100% | **4,90** | **2,90** | |

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
2. **Spasial.** Irisan kecamatan dan luas geodesik 17× lebih cepat dan tidak perlu penyiasatan. Di MySQL, kueri setara langsung error dan setiap kueri luas harus ditulis ulang.
3. **Kueri analitik.** Evaluasi alert 9× lebih cepat karena CTE dihitung sekali. Rekap bulanan pada 2,3 juta baris 8,5× lebih cepat (0,65 detik vs 5,6 detik). Selisihnya membesar seiring bertambahnya data, padahal angka per kecamatan di project ini **disimpan selamanya**.
4. **Penulisan ETL.** Insert batch 8× lebih cepat dan upsert 2× lebih cepat. Backfill bertahun-tahun data selesai jauh lebih singkat.
5. **Konkurensi baca sedikit lebih tinggi**, 13–26%. Ini keunggulan kecil yang tidak menentukan.

### 5.2 Keunggulan MySQL dibanding PostgreSQL pada project ini

1. **Kueri rekursif lineage (Q5) lebih cepat:** 0,43 ms vs 0,82 ms. Dalam praktik tidak terasa, karena keduanya di bawah 1 ms.
2. **Penyimpanan data mentah lebih ringkas**, sekitar 20% lebih kecil. Tetapi index-nya lebih besar, sehingga totalnya hanya selisih sekitar 5%.
3. **Lebih akrab bagi GMLS.** SIGAP DESA sudah memakai PHP/MySQL, jadi pengelola tidak perlu belajar DBMS baru, dan hosting murah lebih banyak yang menyediakan MySQL.
4. **Kueri ber-index dan baca serentak sama-sama memadai.** Untuk halaman dashboard harian, MySQL tidak menjadi hambatan.

### 5.3 Ringkasan

Keunggulan MySQL bersifat **operasional dan sosial**: akrab, mudah dihosting, dan ringkas. Keunggulan PostgreSQL bersifat **fungsional**: fitur yang diwajibkan rumusan masalah (RM4, spasial, analitik) hanya terpenuhi penuh di PostgreSQL.

Karena itu PostgreSQL direkomendasikan untuk Orbit-U. MySQL tetap tepat untuk SIGAP DESA, yang tidak butuh spasial dan pembatasan akses di level database. Kedua sistem bisa berdampingan.

---

## 6. Keterbatasan

- **Disk tidak setara (§2.4):** PostgreSQL di SSD, MySQL di HDD. Keunggulan PostgreSQL di tulis/ETL (§3.6) dan Q6 ×30 (§3.3) mungkin lebih kecil kalau kedua DBMS berada di disk yang sama. Keunggulan di keamanan (F1–F3), spasial (Q3), dan evaluasi alert (Q4) tidak terpengaruh, karena data uji tersebut sudah ada di memori.
- Data sintetis. Skala terbesar yang diuji 2,3 juta baris; data produksi saat ini berisi 68.120 baris `region_observations`.
- Konfigurasi bawaan tanpa tuning. Dengan `innodb_buffer_pool_size` lebih besar, Q6 MySQL di ×30 kemungkinan membaik. Uji ini mengukur perilaku "apa adanya", sesuai kondisi GMLS yang tidak punya DBA.
- Klien dan server di mesin yang sama. Klien Python ikut memakai CPU saat uji konkurensi.
- Kueri inti dan E1 untuk MySQL diukur lewat pymysql. Selisih Q1/Q2 di bawah 1 ms sebagian berasal dari driver (§3.1). Q3, Q4, dan Q6 didominasi waktu server.
- MongoDB tidak diukur waktunya karena skemanya tidak setara (§1.2).

## 7. Cara mengulang

```
venv\Scripts\pip install pymysql mysqlclient
venv\Scripts\python benchmark\generate.py
set BENCH_MYSQL_PORT=3307
set PYTHONIOENCODING=utf-8

venv\Scripts\python benchmark\run.py --engine all            :: A, B (kueri inti, fitur)
venv\Scripts\python benchmark\extended.py                    :: C, D, E dengan pymysql
venv\Scripts\python benchmark\run.py --engine all            :: kembalikan ke skala ×1
set BENCH_MYSQL_DRIVER=mysqlclient
set BENCH_TESTS=e3,e2
set BENCH_SUFFIX=_mysqlclient
venv\Scripts\python benchmark\extended.py                    :: D, E dengan driver C
```

MySQL 8.0.40 yang dipakai adalah versi ZIP portable di `D:\_bench_mysql`, dijalankan manual di port 3307 (bukan service Windows):

```
D:\_bench_mysql\mysql-8.0.40-winx64\bin\mysqld --basedir=D:\_bench_mysql\mysql-8.0.40-winx64 --datadir=D:\_bench_mysql\data --port=3307 --bind-address=127.0.0.1 --console
```

Berkas hasil:

| Berkas | Isi |
|---|---|
| `timing.csv`, `features.csv`, `explain_*.txt` | Kueri inti dan fitur |
| `extended_scaling.csv` | Skalabilitas |
| `extended_concurrency.csv`, `extended_write.csv` | Konkurensi dan tulis lewat pymysql |
| `extended_concurrency_mysqlclient.csv`, `extended_write_mysqlclient.csv` | Konkurensi dan tulis lewat driver C (**dipakai untuk kesimpulan**) |

## 8. Kode pengujian

Kode lengkap ada di folder `benchmark/`:

| Berkas | Baris | Isi |
|---|---|---|
| `generate.py` | 178 | Pembangkit data sintetis (seed tetap) |
| `engines.py` | 342 | Skema setara, pemuat data, kueri Q1–Q5 per dialek, uji fitur F1–F3 |
| `run.py` | 226 | Pengukuran kueri inti dan fitur |
| `extended.py` | 307 | Skalabilitas, konkurensi, tulis |

Saran penempatan di naskah:

- **Badan bab (DBMS Selection):** cukup cuplikan yang menunjukkan perbedaan dialek, yaitu Q3 (spasial) dan Q4 (evaluasi alert) versi PostgreSQL berdampingan dengan versi MySQL, beserta uji F1 (`SET LOCAL ROLE` vs `SET ROLE`). Cuplikan ini yang membuktikan bahwa perbandingannya setara.
- **Lampiran:** keempat berkas di atas secara utuh, atau tautan ke repositori dengan nomor commit, supaya penguji bisa mengulang pengujian.
- **Selalu sertakan:** perintah menjalankan (§7), spesifikasi hardware (§2.4), dan berkas CSV hasil. Kode tanpa data hasil dan lingkungan tidak bisa diverifikasi.
