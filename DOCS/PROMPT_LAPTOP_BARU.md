# Prompt untuk Claude Code di laptop baru

Buka Claude Code di dalam folder repo hasil `git clone`, lalu salin seluruh blok
di bawah sebagai pesan pertama. Dokumen acuannya: `DOCS/SETUP_LAPTOP_BARU.md`.

> **Pemasangan perangkat lunak adalah tugas Anda, bukan Claude Code.** Installer
> PostgreSQL dan Python berbentuk GUI dan meminta hak administrator. Selesaikan
> §2 `SETUP_LAPTOP_BARU.md` lebih dulu, dan pastikan `psql --version` menjawab
> 18.x serta `py -3.12 --version` menjawab 3.12.x, sebelum mengirim prompt ini.
> Tanpa itu Claude Code hanya akan berhenti di langkah 1 dan menunggu Anda.

Siapkan dulu sebelum mengirim:

- `roles.sql`, `themonitor.dump`, `manifest_lama.txt` dari laptop lama
- `.env` dari laptop lama
- folder `data/` yang Anda putuskan ikut dibawa
- sandi `postgres` yang Anda tetapkan saat memasang PostgreSQL 18

Ganti teks di dalam `<...>` dengan nilai sebenarnya. Kalau belum memasang
PostgreSQL/Python sama sekali, biarkan saja — prompt sudah memintanya memandu
Anda.

---

## Kalau folder itu clone LAMA, bukan clone baru

Kalau di laptop tujuan sudah ada clone era lama dan Anda tiba di versi ini lewat
`git pull` (bukan `git clone`), tambahkan **LANGKAH 0** di bawah ke dalam prompt,
sebelum langkah 1. Tandanya: output pull memuat penghapusan `old_ref/`,
`database/migrations/0xx`, `docker-compose.yml`, `web/app.js`, atau
`web/style.css`.

```
0. BERSIHKAN SISA CLONE LAMA (sebelum apa pun yang lain)
   Folder ini clone era lama yang baru saya pull ke versi sekarang, bukan clone
   baru. Jangan asumsikan lingkungannya bersih.
   - Pastikan HEAD sudah di commit terbaru origin/main dan working tree bersih.
   - venv yang ada dibangun untuk requirements.txt versi LAMA, dan dengan
     Python yang salah versi. Buat ulang dari nol memakai Python 3.12 secara
     eksplisit — jangan sekadar pip install di atas venv lama, karena paket
     untuk modul yang sudah dihapus (dataset_merge, land_mask,
     water_occurrence, refusion) masih tertinggal di sana. Pastikan PyMySQL
     ikut terpasang. Periksa `python --version` di dalam venv baru sebelum
     lanjut; kalau bukan 3.12.x, berhenti.
   - .env yang ada milik proyek LAIN (DB_NAME=thedatalab, API_PORT=8000).
     GANTI seluruhnya dengan .env yang saya bawa dari laptop lama; jangan
     ditambal sebagian. Tunjukkan dulu ke saya selisih kuncinya terhadap
     .env.example sekarang.
   - run.ps1 dan run.bat adalah launcher saya sendiri — JANGAN dihapus.
     Keduanya sudah memakai port 8001 yang benar, tetapi run.ps1 masih
     memeriksa service `postgresql-x64-14` dan menyebut database
     `orbit_u_monitor` serta "migrasi 001-026" yang sudah tidak ada.
     Perbarui komentar dan nama service-nya ke PostgreSQL 18, lalu usulkan
     ke saya untuk di-commit supaya tidak hilang lagi.
   - venv_broken_bigdata/ boleh dihapus setelah saya setujui. Pastikan dulu
     isinya memang venv, bukan folder proyek.
   - Periksa apakah masih ada database warisan (thedatalab, orbit_u_monitor,
     sentinel1_flood) di instance PostgreSQL yang aktif. Laporkan daftarnya.
     Kalau sudah ada database bernama themonitor, LAPOR DAN BERHENTI — saya
     yang memutuskan. Jangan dropdb sendiri.
   - Laporkan sisa ruang disk sebelum kita bicara restore dan backfill.
```

---

```
Saya baru saja clone repo ini di laptop baru (Windows) dan ingin memindahkan
seluruh proyek ke sini, lalu menyelesaikan pekerjaan yang tersisa.

Baca DOCS/SETUP_LAPTOP_BARU.md lebih dulu dan jadikan itu acuan. Dokumen itu
ditulis khusus untuk perpindahan ini. Kalau ada yang bertentangan antara
dokumen itu dan README.md §9, ikuti SETUP_LAPTOP_BARU.md — §9 adalah jalur
membangun database kosong dari nol, bukan jalur pindah mesin.

BAHAN YANG SUDAH SAYA SIAPKAN
- Dump database   : <D:\pindah\themonitor.dump>
- Dump role       : <D:\pindah\roles.sql>
- Manifest lama   : <D:\pindah\manifest_lama.txt>
- File .env lama  : <D:\pindah\.env>
- Folder data/    : <D:\pindah\data>   (atau tulis "tidak saya bawa")
- Sandi postgres  : akan saya ketik sendiri saat diminta, jangan ditebak

YANG SAYA MINTA, BERURUTAN

1. PERIKSA LINGKUNGAN
   Laporkan versi python, psql, dan apakah PostGIS tersedia. Bandingkan
   dengan tabel versi di SETUP_LAPTOP_BARU.md §0. Kalau PostgreSQL bukan
   18.x atau Python bukan 3.12.x, berhenti dan beri tahu saya apa yang harus
   saya pasang — jangan lanjut, karena dump dari PostgreSQL 18.6 tidak bisa
   di-restore ke versi mayor yang lebih rendah. Pemasangan installer GUI
   adalah tugas saya, bukan Anda.

2. SIAPKAN KODE
   Buat venv, aktifkan, pasang requirements.txt. Laporkan kalau ada paket
   yang gagal dan sebutkan dugaan penyebabnya.

3. SIAPKAN .env
   Salin .env yang saya sediakan ke root repo. Ubah HANYA DB_PASSWORD dan
   bagian sandi di DATABASE_URL, sesuai §4. Jangan ubah JWT_SECRET,
   MONITOR_APP_PASSWORD, MONITOR_ETL_PASSWORD — §5 menjelaskan kenapa.
   Minta sandi postgres ke saya; jangan menebak dan jangan menuliskannya ke
   file lain atau ke ringkasan Anda.

4. RESTORE DATABASE
   Ikuti §5 persis: roles.sql dulu, baru createdb, CREATE EXTENSION, lalu
   pg_restore. Jelaskan ke saya peringatan mana yang wajar dan mana yang
   tidak sebelum Anda lanjut.

5. BUKTIKAN ISINYA IDENTIK
   Jalankan database/db_manifest.sql, bandingkan dengan manifest_lama.txt.
   Tunjukkan hasil perbandingannya ke saya. Kalau ada selisih, pakai tabel
   penafsiran di §6 dan beri tahu saya — jangan menambal database secara
   manual.
   Kalau manifest_lama.txt tidak ada, pakai angka acuan di §6.

6. VERIFIKASI APLIKASI HIDUP
   python database/apply_schema.py --check, lalu jalankan API di port 8001
   dan pastikan halaman depan serta /api/health merespons. Setelah itu
   matikan lagi. Jalankan juga pytest dan laporkan hasilnya apa adanya —
   kalau ada yang gagal, tunjukkan outputnya, jangan disimpulkan "mestinya
   jalan".

7. MYSQL 8 — BENCHMARK M29  (kerjakan SEBELUM backfill)
   Ini satu-satunya hasil yang masih kosong di seluruh proyek;
   IMPLEMENTATION_NOTES.md menandainya MENUNGGU MySQL 8. Ikuti §7b.
   - Periksa apakah MySQL 8.0 sudah terpasang. Kalau belum, beri tahu saya
     apa yang harus saya pasang dan tunggu. MariaDB dari XAMPP TIDAK boleh
     dipakai — benchmark/run.py menolaknya dan itu justru penyebab baris ini
     kosong selama ini.
   - Tambahkan BENCH_MYSQL_* ke .env (polanya sudah ada di .env.example).
   - python benchmark/generate.py lalu python benchmark/run.py --engine all.
   - Tunjukkan isi benchmark/results/ ke saya dan ringkas temuannya:
     mana yang menang di tiap kueri Q1-Q5 dan fitur keamanan F1-F3, dan
     apakah hasilnya mendukung pilihan PostgreSQL+PostGIS yang sudah diambil
     di DATABASE.md §1.
   - Perbarui baris MENUNGGU MySQL 8 di DOCS/IMPLEMENTATION_NOTES.md menjadi
     RESOLVED beserta angka hasilnya. Commit.

8. BACKFILL HIDROMET 3 TAHUN
   python scripts/backfill_hydromet.py --from 2023-01-01 --to 2025-12-31
   - Ini perkiraan 1,5-2 HARI jalan, bukan beberapa jam (§7a, T3-26: ~130
     detik per tanggal). Jalankan di background dan beri tahu saya cara
     memantau serta cara menghentikannya dengan aman.
   - Aman dihentikan: tanggal COMPLETED dilewati saat dijalankan ulang.
   - Sebelum mulai, periksa sisa ruang disk dan masa berlaku
     NASA_EARTHDATA_TOKEN (kedaluwarsa sekitar 3 November 2026). Kalau sisa
     waktunya mepet terhadap durasi backfill, beri tahu saya sekarang supaya
     saya buat token baru.
   - Jangan tunggu sampai selesai di satu sesi. Laporkan progres awal
     (beberapa tanggal pertama sukses, nilainya wajar), lalu serahkan ke saya.

9. SETELAH BACKFILL SELESAI (lain waktu, kalau saya minta)
   - Bangkitkan ulang kamus data: python tools/data_dictionary.py
   - Periksa apakah angka di PIPELINE.md §10 dan IMPLEMENTATION_NOTES perlu
     diperbarui dengan durasi backfill yang sebenarnya.

ATURAN MAIN
- Kerjakan berurutan. Berhenti dan tanya kalau ada langkah yang hasilnya
  tidak sesuai harapan; jangan mengarang jalan pintas.
- Jangan pernah DROP atau TRUNCATE database themonitor tanpa izin saya.
- Jangan commit .env, dump, atau isi data/.
- Laporkan kegagalan apa adanya dengan outputnya. Kalau sebuah langkah
  dilewati, katakan dilewati.
- Di akhir tiap langkah besar, beri satu ringkasan pendek: apa yang
  berhasil, apa yang belum, apa langkah berikutnya.
```
