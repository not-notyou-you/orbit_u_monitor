# Prompt untuk Claude Code di laptop baru

Buka Claude Code di dalam folder repo hasil `git clone`, lalu salin seluruh blok
di bawah sebagai pesan pertama. Dokumen acuannya: `DOCS/SETUP_LAPTOP_BARU.md`.

Siapkan dulu sebelum mengirim:

- `roles.sql`, `themonitor.dump`, `manifest_lama.txt` dari laptop lama
- `.env` dari laptop lama
- folder `data/` yang Anda putuskan ikut dibawa
- sandi `postgres` yang Anda tetapkan saat memasang PostgreSQL 18

Ganti teks di dalam `<...>` dengan nilai sebenarnya. Kalau belum memasang
PostgreSQL/Python sama sekali, biarkan saja — prompt sudah memintanya memandu
Anda.

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
