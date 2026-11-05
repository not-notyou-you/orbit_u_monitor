# Audit Output Project terhadap SKRIPSI.txt

Acuan: Pedoman Penelitian Skripsi Prodi SI versi 1.3, peminatan Database, jalur Design and Implementation
(ringkasannya di `ketentuan/SKRIPSI.txt`). Ketentuan versi lama yang tidak ada di 1.3 tidak dinilai (M77).

Diperiksa ulang: 29 Oktober 2026 (M80). Yang dinilai adalah **output project**: kode, skema, data, hasil uji, dan
artefak di repo. Angka baris diambil dari snapshot database kampus 24 Okt 2026 18.40
(`bahan_naskah/assets/data.js`), sama dengan yang dipakai naskah. Bagian 4 mencatat ketidaksesuaian antara
naskah dan project yang perlu diputuskan penulis.

Status: **Terjawab** = ada artefak yang bisa ditunjukkan · **Sebagian** = artefak ada, ada bagian yang belum ·
**Belum** = tidak ada artefaknya.

---

## 1. Ringkasan

| Bagian SKRIPSI.txt | Status | Artefak |
|---|---|---|
| A. Database Planning, System Definition | Terjawab | DATABASE.md §2.1–2.3; `bahan_naskah/03-perencanaan.html` |
| A. Requirement Collection and Analysis | Terjawab | Wawancara GMLS 16 Okt 2026 (`lampiran/notulensiGMLS.txt`), DATABASE.md §2.4 (K1–K6 + keterlacakan) |
| A. As-Is, identifikasi masalah (5W1H) | Terjawab | `bahan_naskah/02-analisis-sistem.html`, DATABASE.md §2.4 |
| A. Conceptual, Logical, Physical Design | Terjawab | DATABASE.md §2–§9; `database/monitor_*.sql`; `../generated/` (kamus data + ERD fisik); `bahan_naskah/04–08` |
| A. DBMS Selection (a–d) | Terjawab | `../PERBANDINGAN_DBMS.md`, `benchmark/`, `benchmark/results/` |
| A. Pemodelan Sistem (UML) | Terjawab | INTERFACE.md §9; `bahan_naskah/10–12` (use case, activity, sequence) |
| A. Desain Antarmuka, Prototyping | Terjawab | INTERFACE.md §2–§3, DESIGN.md, `web/`; `bahan_naskah/14-antarmuka.html`; video `lampiran/video_demo/` |
| A. Implementation, Data Conversion and Loading | Terjawab | `etl/`, `api/`, `scripts/`, PIPELINE.md; data 1 Jan 2024–22 Okt 2026 di database |
| A. Testing: evaluasi minimum Tabel 4 | Sebagian | Lima evaluasi teknis lulus (§3). Requirement/user review: jawaban GMLS asli belum masuk |
| C.1 Legalitas objek studi ≥ 2 tahun | Tidak diperlukan | GMLS mitra resmi UMN (MoU melalui LPPM), objek studi disetujui prodi; berdiri 13 Okt 2020 (`lampiran/profil.jpeg`) |
| C.2 Master ≥ 10, transaksi ≥ 100 | Terjawab | §2 |
| D. Hasil akhir | Terjawab | §2 |
| E. Alternatif komparasi teknologi | Tidak dipilih | Jalur yang dipakai Design and Implementation |

---

## 2. Hasil akhir dan prasyarat ↔ artefak

| Hasil akhir (SKRIPSI.txt bagian D) | Artefak |
|---|---|
| Rancangan conceptual, logical, physical; data dictionary; DDL; constraints; indexing; security | `database/monitor_schema.sql`, `monitor_security.sql`, `monitor_seed.sql`; DATABASE.md; `tools/data_dictionary.py` → `../generated/data_dictionary.md` + `erd_physical.mmd` |
| Rekomendasi DBMS | `../PERBANDINGAN_DBMS.md` (PostgreSQL + PostGIS 4,90 vs MySQL 8.0 2,90), `benchmark/results/*.csv` |
| Implementasi / prototype yang dapat diuji | Aplikasi web `web/` + REST API `api/` (OpenAPI `/docs`), berjalan di server produksi (README §9) |
| API / middleware | Tidak wajib (penelitian tidak berfokus integrasi). Tetap ada: REST API + token API pribadi (M33) |
| Benchmark, integrity report, security test, evidence | `benchmark/results/`, `../hasil_uji/`, `tests/security/grant_matrix.sql` |
| Source code, query, konfigurasi, dataset description, README | Seluruh repo; `../README.md`, `.env.example`, `database/db_manifest.sql` |

**Prasyarat database terstruktur (C.2)**, snapshot 24 Okt 2026:

- **12 tabel master**: `administrative_regions` 29, `processing_stages` 13, `spectral_bands` 11,
  `regions_of_interest` 11, `quality_thresholds` 9, `users` 7, `roles` 5, `satellite_sources` 4,
  `disaster_types` 4, `alert_rules` 4, `report_types` 4, `fusion_strategies` 3.
- **17 tabel transaksi ≥ 100 baris**, antara lain `region_observations` 72.850, `band_forecast_points` 18.870,
  `data_products` 15.850, `data_lineage` 8.142, `processing_jobs` 7.958, `processing_logs` 6.361,
  `nasa_scenes` 2.230, `alert_events` 210.
- **Siap tumbuh (C.2.d)**: 162 indeks, 22 VIEW, raster di filesystem; uji skala 2,3 juta baris
  (PERBANDINGAN_DBMS.md §3.3).

---

## 3. Evaluasi minimum (Tabel 4)

| Evaluasi | Bukti | Hasil |
|---|---|---|
| Requirement/user review | Web tinjauan `lampiran/user_review_webapp/`; lembar `lampiran/Lembar_Tinjauan_Kebutuhan_GMLS.*` | **Belum ada jawaban asli.** Naskah memakai `CONTOH_DUMMY_jawaban_tinjauan_kebutuhan.csv` atas arahan pembimbing (24 Okt 2026); ganti begitu ekspor Sheet GMLS masuk |
| Integrity | `tests/test_database.py`, `test_schema_comments.py`, `test_audit.py` | Lulus |
| Functional | Skenario black-box `tests/test_*_api.py`, `test_alert_engine.py`, `test_notify.py`, … | Lulus |
| Security | `tests/test_rbac_api.py` (165 kasus), `tests/security/grant_matrix.sql` | Lulus |
| Query | `benchmark/` Q1–Q6, E1–E3, F1–F3 | Kueri inti PostgreSQL < 2 ms (median) |
| Backup/recovery | `tests/recovery/backup_restore.sh`, `kill_and_resume.sh`; backup harian M76 | Lulus (23 Okt 2026, `../hasil_uji/`) |

Pytest terakhir: 24 Okt 2026, 1.185 kasus: 1.183 lulus, 0 gagal, 2 dilewati, 150 detik (INTERFACE.md §7.1).
Tidak termasuk: `tests/ui/` (browser headless), pengiriman SMTP sungguhan, point-in-time recovery.

**Masih terbuka (bukan kekurangan sistem, arahan pembimbing 24 Okt 2026):** `disaster_events` berisi 18 baris
tetapi kejadian resmi terverifikasi masih terbatas, jadi hasil `v_evaluasi_alert` belum bisa disimpulkan; ditulis
sebagai keterbatasan. Aturan longsor (`LANDSLIDE_RAIN72`) belum aktif karena ambangnya belum ada.

**Belum ada di repo:** lampiran naskah (ERD semua modul, kamus data lengkap, notulen, hasil uji), dan folder
gambar `gambar_bab4/`, `alur_penelitian.png`, `peta_wilayah.png` yang dipakai `naskah/build_skripsi.py`.

---

## 4. Ketidaksesuaian naskah ↔ project (diperbaiki 29 Okt 2026)

Enam ketidaksesuaian ditemukan pada pemeriksaan 29 Okt 2026, lalu diperbaiki mengikuti kode, baik di sumber
(`naskah/bab4.py`) maupun di `naskah/SKRIPSI FINAL.docx`. Docx ditambal langsung (12 paragraf dan gambar
`media/image25.png`) karena folder `gambar_bab4/` tidak ada di repo sehingga naskah belum bisa dibangun ulang.

| # | Letak di naskah | Sebelum | Sesudah (sesuai kode) |
|---|---|---|---|
| 1 | Gambar 4.21 + paragraf sesudahnya | Wireframe susunan lama (panel pantau, citra 9 tile, tema di bawah) | Wireframe dari `bahan_naskah/14-antarmuka.html` (M66): daftar kecamatan → tiga KPI → peta → tema → Detail lokasi; paragraf menyebut tema dan Detail lokasi |
| 2 | Tabel 4.31 skenario 10 | Rentang 400 hari → 400 `INVALID_DATE_RANGE` | 1 Jan 2024–1 Jun 2025 (518 hari) → **422 `VALIDATION_ERROR`** (`tests/test_data_api.py::test_range_limit_and_conflict`) |
| 3 | Tabel 4.31 skenario 9 | 148 mm → WARNING | 49,99 / 100 / 151 mm → tanpa / INFO+WARNING / INFO+WARNING+CRITICAL (`tests/test_alert_engine.py::test_bmkg_levels_fire_cumulatively`) |
| 4 | Tabel 4.32 baris kunci | "Job Hidromet dari dua proses → SKIPPED_LOCKED" | Kunci advisory dipegang lebih dulu → job `SKIPPED_LOCKED` dan backfill 409 `BACKFILL_RUNNING` (`tests/test_monitor_api.py`, `tests/test_data_api.py::TestExternalBackfill`) |
| 5 | Subbab 4.2.2 (kunci dan desain logikal) | "Semua relasi ber-PK surrogate, sehingga hanya band_forecast_* lemah"; "kunci primer berupa surrogate" | 40 dari 43 relasi ber-PK surrogate; tiga berkunci komposit: dua entitas lemah + `user_notify_regions` (asosiatif); "kunci primer umumnya surrogate" |
| 6 | Penjelasan Gambar 4.27 | "ketujuh kejadian belum terverifikasi" | Dijelaskan bahwa tangkapan layar dari video demonstrasi (akun Relawan Demo, tujuh kejadian contoh) berbeda dari 18 catatan basis data per 24 Okt 2026 |

Salinan docx sebelum tambalan tidak disimpan di repo; riwayatnya ada di git (commit `23738c4`).
