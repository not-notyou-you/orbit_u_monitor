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

Koneksi PostgreSQL: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` dari `.env` (butuh hak `CREATE DATABASE`
dan ekstensi PostGIS terpasang). Koneksi MySQL:

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
- `environment.json`: versi DBMS dan PostGIS, CPU, RAM, OS, jumlah baris yang dimuat, lama pemuatan.
- `explain_*.txt`: rencana eksekusi aktual (`EXPLAIN ANALYZE`) untuk pembahasan index.

Skor akhir kerangka acuan (DATABASE.md §1: spasial 30%, integritas 25%, keamanan 15%, biaya 15%,
integrasi 15%) disusun di bab evaluasi skripsi dari kedua berkas ini.
