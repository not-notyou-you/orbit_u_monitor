# Benchmark DBMS — Orbit-U: The Monitor

Evaluasi produk untuk rekomendasi DBMS (DATABASE.md §1, keputusan M29):
PostgreSQL + PostGIS dibandingkan dengan MySQL 8.0 pada **data dan kueri yang
sama**; MongoDB 7 dinilai dari fitur saja karena skemanya tidak setara.

## Isi

| Berkas | Fungsi |
|---|---|
| `generate.py` | Data **sintetis** deterministik (seed 20260929): 28 kecamatan (10 AOI), observasi 3 tahun × 10 kecamatan × 7 band, alert BMKG, ±150 kejadian, 1.200 rantai produk/lineage (sebagian 6 tingkat). Bukan data produksi. |
| `engines.py` | Skema setara, pemuat, kueri Q1–Q5 per dialek, uji fitur F1–F3, penilaian fitur MongoDB |
| `run.py` | Membuat DB benchmark, memuat data, 5× pemanasan + 30× ukur per kueri, menyimpan EXPLAIN dan hasil |
| `results/` | `timing.csv`, `features.csv`, `environment.json`, `explain_<engine>_<Q>.txt` |

## Kueri dan fitur

| Kode | Isi | Parameter tetap |
|---|---|---|
| Q1 | Statistik hari ini: pivot 5 band per kecamatan AOI untuk satu tanggal | 2024-12-15 |
| Q2 | Tren 30 hari satu kecamatan, satu band | kecamatan 9, RAIN_24H, 16 Nov – 15 Des 2024 |
| Q3 | Kecamatan yang beririsan poligon + luas irisan geodesik (km²) | poligon 106,00–106,30 BT × 6,95–6,80 LS |
| Q4 | Evaluasi alert hit / miss / false alarm (WARNING+, kejadian terverifikasi 0–3 hari setelah alert) | seluruh periode |
| Q5 | Leluhur satu produk sampai 6 tingkat (`WITH RECURSIVE`) | produk DERIVED pertama |
| F1 | `SET ROLE` per transaksi (hak kembali setelah COMMIT/ROLLBACK) | |
| F2 | Row-level security | |
| F3 | Trigger audit dengan OLD/NEW sebagai JSON tanpa menyebut kolom | |

## Isolasi

- PostgreSQL: database **`themonitor_bench`** (dibuat ulang tiap run), skema `bench`, role uji `bench_reader`.
- MySQL 8.0: database **`themonitor_bench`** (dibuat ulang tiap run).
- Skrip menolak nama `themonitor`. Tidak ada data produksi yang dibaca atau ditulis.
- Jangan jalankan bersamaan dengan suite pytest (memori mesin 14 GB).

## Menjalankan

```bash
python benchmark/generate.py                 # ±15 detik, menulis benchmark/data/
python benchmark/run.py --engine all         # PostgreSQL + MySQL (MySQL dilewati bila tidak tersedia)
python benchmark/run.py --engine pg          # hanya PostgreSQL
```

Koneksi PostgreSQL: `BENCH_PG_HOST`, `BENCH_PG_PORT`, `BENCH_PG_USER`, `BENCH_PG_PASSWORD`; bila tidak diisi,
jatuh ke `DB_*` dari `.env` (butuh hak `CREATE DATABASE` dan ekstensi PostGIS terpasang).

**Perbandingan adil butuh disk yang sama.** Data directory PostgreSQL produksi ada di SSD C:, data MySQL benchmark
di HDD D:. Karena itu pakai klaster PostgreSQL khusus benchmark di disk yang sama dengan MySQL (port 5433), lalu
set `BENCH_PG_PORT=5433` dan `BENCH_REQUIRE_SAME_DISK=1`. `run.py` mencatat data directory, disk fisik, dan jenis
media (SSD/HDD) tiap DBMS di `environment.json` (`storage_equal`) dan menolak berjalan bila disknya berbeda.
Perintah lengkap: `DOCS/PERBANDINGAN_DBMS.md` §7. Koneksi MySQL:

```bash
pip install pymysql
export BENCH_MYSQL_HOST=127.0.0.1 BENCH_MYSQL_PORT=3306 BENCH_MYSQL_USER=root BENCH_MYSQL_PASSWORD=...
```

Bila server MySQL tidak terjangkau, driver belum terpasang, atau server bukan MySQL 8.0 (mis. MariaDB),
baris MySQL di `timing.csv`/`features.csv` ditulis berstatus **"belum dijalankan"** beserta alasannya —
bukan diisi angka perkiraan.

## Membaca hasil

- `timing.csv`: `median_ms` dan `p95_ms` dari 30 eksekusi (waktu eksekusi + pengambilan baris di klien Python,
  koneksi lokal). Bandingkan antar-DBMS per kueri, bukan antar-kueri.
- `features.csv`: `DIDUKUNG` / `SEBAGIAN` / `TIDAK DIDUKUNG` dengan bukti singkat.
- `environment.json`: versi DBMS dan PostGIS, konfigurasi buffer/durabilitas, data directory + disk + media, CPU, RAM, OS, jumlah baris yang dimuat, lama pemuatan.
- `arsip_2026-10-08_pg-ssd_mysql-hdd/`: hasil lama dengan disk tidak setara; jangan dipakai untuk kesimpulan.
- `explain_*.txt`: rencana eksekusi aktual (`EXPLAIN ANALYZE`) untuk pembahasan index.

Skor terbobot akhir (tujuh kriteria: keamanan per peran & audit 25%, spasial 20%, analitik & skala 15%,
tulis/ETL 10%, konkurensi baca 10%, integritas relasional & rekursif 10%, biaya & ekosistem 10%) dan
rekomendasinya ada di `DOCS/PERBANDINGAN_DBMS.md` §3.8–§4 (PostgreSQL 4,90, MySQL 3,05; uji ulang 6 Nov 2026 dengan disk setara).
