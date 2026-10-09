# Audit Output Project terhadap SKRIPSI.txt

Diperiksa: 8 Oktober 2026. Objek: folder `themonitor/` dan database `themonitor` yang sedang berjalan (localhost:5432).

Yang dinilai adalah **output project**: kode, skema, data di database, hasil uji, dan artefak yang dihasilkan. Naskah skripsi tidak dinilai. Klaim di `DOCS/README.md` hanya dihitung kalau berkasnya benar-benar ada di repo atau datanya benar-benar ada di database.

Status:
- **Terjawab**: ada artefak yang bisa ditunjukkan.
- **Sebagian**: artefaknya ada, tetapi ada bagian yang kosong atau belum dijalankan.
- **Belum**: tidak ada artefaknya di project.

---

## Ringkasan

| Bagian SKRIPSI.txt | Status |
|---|---|
| D. Rancangan Database | Terjawab (8 Okt 2026): skema + DATABASE.md + `DOCS/generated/data_dictionary.md` dan `erd_physical.mmd` (38 tabel, 19 VIEW) |
| D. Rekomendasi DBMS | Terjawab (8 Okt 2026): PostgreSQL dan MySQL 8.0 diuji, rekomendasi di [PERBANDINGAN_DBMS.md](PERBANDINGAN_DBMS.md). Acuan penelitian terdahulu belum ada |
| D. Rancangan Sistem/Aplikasi | Terjawab |
| D. Middleware / API Database | Sebagian: API ada, `docs/api_examples.md` tidak ada |
| C.2 Master ≥ 10, transaksi ≥ 100 | Terjawab |
| C.1 Legalitas objek studi ≥ 2 tahun | Belum ada bukti di project |
| A. Tahap DBSDLC: implementasi, loading, keamanan | Terjawab |
| A. Tahap DBSDLC: perencanaan, analisis, desain konseptual dan logikal, UML | Sebagian (8 Okt 2026): DATABASE.md, PIPELINE.md, DESIGN.md ditulis ulang dari kode (M60). UML di INTERFACE.md §9. Belum: bukti fact-finding GMLS |
| A. Testing 5 kriteria | Sebagian: uji teknis lulus 1.140/1.140 (8 Okt 2026, INTERFACE.md §7.1, `DOCS/hasil_uji/`); uji pengguna (UAT/SUS) belum ada |

---

## 1. Yang sudah terjawab oleh project

### Prasyarat database terstruktur (C.2)

Angka di bawah dihitung langsung dari database:

- **Master table: 12** (≥ 10). Isinya: `roles` 5, `users` 5, `satellite_sources` 4, `spectral_bands` 11, `administrative_regions` 29, `regions_of_interest` 11, `processing_stages` 13, `quality_thresholds` 9, `disaster_types` 4, `alert_rules` 4, `fusion_strategies` 3, `report_types` 4. Semuanya ditandai sebagai master di [monitor_schema.sql](../database/monitor_schema.sql).
- **Transaksi ≥ 100**: `region_observations` 68.120, `data_products` 13.910, `processing_jobs` 7.148, `data_lineage` 7.000, `nasa_scenes` 2.085, `processing_logs` 1.780, `dataset_jobs` 981, `audit_log` 295, `live_scene_metrics` 254, `alert_events` 210, `live_events` 121.
- **Siap tumbuh (C.2.d)**: ada index dan VIEW (97 objek index/VIEW/policy di berkas SQL, 21 VIEW di database). Raster disimpan di filesystem, database hanya menyimpan metadata. Benchmark mencatat waktu kueri Q1–Q5 di bawah 3,2 ms (p95).

### Physical database design (A)

| Tahap | Artefak |
|---|---|
| Menerjemahkan ke DBMS target | [monitor_schema.sql](../database/monitor_schema.sql): 38 tabel, enum, constraint, trigger, COMMENT pada setiap tabel dan kolom |
| Organisasi berkas dan index | Index di skema; raster COG/HDF5 di `data/`, metadata di database |
| Pandangan pengguna | 21 VIEW per peran, misalnya `v_citra_scenes` dan `v_public_kejadian` |
| Mekanisme keamanan | [monitor_security.sql](../database/monitor_security.sql): 5 role PostgreSQL, GRANT, `SET LOCAL ROLE`, trigger audit; diuji oleh [grant_matrix.sql](../tests/security/grant_matrix.sql) |
| Redundansi terkendali | Nilai agregat per kecamatan di `region_observations` |
| Memantau dan menyelaraskan | `processing_logs`, `quality_metrics`, `quality_alerts`, halaman log, Laporan Kesehatan Data |

### Implementation, Data Conversion and Loading (A)

- ETL berjalan untuk tiga satelit (`etl/`) dan dijadwalkan dengan advisory lock.
- Skrip pemuatan tersedia di `scripts/`: `load_regions.py`, `backfill_hydromet.py`, `backfill_s1.py`, `import_disasters.py`, dan `database/apply_schema.py`.
- Datanya benar-benar sudah masuk ke database (lihat angka di atas).

### Rancangan Sistem/Aplikasi dan Desain Antarmuka (D, A)

- Web di [web/](../web/): 26 halaman di `web/pages/`. Halaman-halaman ini mencakup semua bagian di [rancangan kasar.txt](rancangan%20kasar.txt): Beranda, 3D AOI, Citra per satelit beserta PDF, Diagram, Kejadian, Data beserta EDA, Laporan, dan Sistem.
- Matriks akses per peran tercatat di [INTERFACE.md](INTERFACE.md) §3.
- Ada tiga konsep tema di [design tambahan/](design%20tambahan/).
- Karena aplikasinya berjalan, aplikasi ini sekaligus menjadi **Prototyping**.

### Middleware / API Database (D)

- REST API FastAPI di [api/](../api/), dengan OpenAPI `/docs` ([openapi_docs.py](../api/openapi_docs.py)).
- Token API pribadi (tabel `api_tokens`) dan daftar endpoint di [INTERFACE.md](INTERFACE.md) §4.

### DBMS Selection: sebagian (A, D)

- Langkah a–c sudah punya artefak. Kerangka acuan dan daftar pendek (PostgreSQL, MySQL 8, MongoDB 7) ada di [benchmark/README.md](../benchmark/README.md).
- Evaluasi PostgreSQL sudah dijalankan: [timing.csv](../benchmark/results/timing.csv), [features.csv](../benchmark/results/features.csv), dan hasil EXPLAIN untuk Q1–Q5.
- MongoDB dinilai dari fitur saja.

### Testing: sebagian (A)

- Ada 1.142 test pytest (berhasil dikumpulkan; seluruh suite tidak dijalankan pada audit ini).
- Ada uji keamanan GRANT (`tests/security/`).
- **Recoverability** diuji lewat [backup_restore.sh](../tests/recovery/backup_restore.sh), [kill_and_resume.sh](../tests/recovery/kill_and_resume.sh), dan `recovery_backfill.py`.
- **Robustness** diuji lewat test ketahanan unduhan, circuit breaker, dan konkurensi.
- **Performance** diukur oleh benchmark.

---

## 2. Yang belum terjawab atau belum lengkap

### a. Dokumen desain yang dirujuk ternyata tidak ada

> **Pembaruan 8 Okt 2026 (M60):** DATABASE.md, PIPELINE.md, dan DESIGN.md sudah ditulis ulang dari kode. Versi lama sengaja dihapus pemilik proyek, jadi tidak perlu dicari. Dari tabel di bawah, yang masih terbuka: hasil wawancara/observasi GMLS (DATABASE.md §2.4 bertanda *[diisi penulis]*), bukti review model bersama GMLS, dan diagram batas sistem/UML.

README menyatakan bahwa tahap conceptual, logical, physical, DBMS selection, dan perencanaan dijawab oleh dokumen berikut. Kelimanya **tidak ada** di repo:

- `DOCS/DATABASE.md`
- `DOCS/PIPELINE.md`
- `DOCS/DESIGN.md`
- `DOCS/SETUP_LAPTOP_BARU.md`
- `docs/api_examples.md`

Akibatnya, tahap-tahap di bawah ini **tidak punya artefak** di project:

| Tahap SKRIPSI.txt | Yang hilang |
|---|---|
| As-Is System Analysis, Identifikasi Masalah (5W1H) | Tidak ada dokumen analisis sistem berjalan GMLS (SIGAP DESA dan alur kerja manual) maupun tabel 5W1H |
| Database Planning | Mission statement dan mission objective tidak tertulis |
| System Definition | Batas sistem dan user views tertulis di README §3, tetapi tidak dalam bentuk diagram batas sistem |
| Requirement Collection and Analysis | Tidak ada catatan fact-finding: hasil wawancara, observasi, atau pemeriksaan dokumen GMLS |
| Conceptual Design | Tidak ada ERD konseptual, tabel domain atribut, maupun analisis candidate/primary/alternate key |
| Logical Design | Tidak ada langkah normalisasi (UNF→1NF→2NF→3NF) maupun analisis strong/weak entity dan multiplicity |
| Validasi dan tinjauan model bersama pengguna | Tidak ada bukti review oleh GMLS |
| DBMS Selection, langkah d | Tidak ada laporan rekomendasi; yang ada hanya CSV mentah |

### b. ERD dan kamus data belum dibangkitkan

~~Belum dibangkitkan.~~ Selesai 8 Okt 2026: `DOCS/generated/data_dictionary.md` dan `erd_physical.mmd`. Bangkitkan ulang setiap kali skema berubah.

### c. Pemodelan Sistem (UML)

~~Belum ada.~~ Selesai 8 Okt 2026: INTERFACE.md §9 (use case 5 peran + scheduler, activity Job Hidromet → alert, backfill, kelola kejadian; Mermaid). Class diagram diwakili ERD fisik.

### d. Benchmark MySQL belum dijalankan

Semua baris MySQL di `timing.csv` dan `features.csv` berstatus "belum dijalankan" karena driver pymysql belum terpasang. Tanpa angka MySQL, bagian ini belum bisa disebut "komparasi" maupun rekomendasi yang terbukti.

### e. Data yang kosong padahal fiturnya inti

- **`disaster_events` berisi 0 baris.** Halaman Kejadian, evaluasi alert (hit/miss/false alarm), dan RM4 bergantung pada tabel ini. Saat ini evaluasi alert pada data produksi tidak punya pembanding.
- `fusion_products` 0, `api_tokens` 0, `cleanup_operations` 0. Ketiganya masih wajar, tetapi fitur fusion dan token API belum terbukti dengan data nyata.
- README menyebut `region_observations` "±79.000 baris". Isi sebenarnya 68.120. Angka ini perlu diselaraskan.

### f. Testing kriteria pengguna

Kriteria **Learnability** dan **Adaptability** belum punya artefak, misalnya skenario uji pengguna, kuesioner (SUS/UAT), atau hasilnya. Selain itu belum ada laporan hasil pytest yang tersimpan (misalnya file JUnit atau ringkasan lulus/gagal).

### g. Prasyarat objek studi (C.1)

Tidak ada bukti legalitas GMLS atau bukti bahwa GMLS sudah beroperasi ≥ 2 tahun, misalnya SK, akta, atau surat keterangan.

### h. Acuan penelitian terdahulu (E)

Bagian ini hanya wajib kalau memilih jalur "komparasi teknologi database". Tidak ada daftar penelitian terdahulu yang menjadi dasar Q1–Q5 maupun F1–F3.

---

## 3. Langkah untuk menjawab yang belum terjawab

Urutan disusun dari yang paling berdampak dan paling murah.

1. ~~Cari dulu dokumen yang hilang.~~ Selesai dengan cara lain (M60): dokumen lama sengaja dihapus, DATABASE.md, PIPELINE.md, dan DESIGN.md ditulis ulang dari kode.
2. ~~Bangkitkan ERD fisik dan kamus data~~ Selesai 8 Okt 2026. Ulangi bila skema berubah:
   ```
   venv\Scripts\python tools\data_dictionary.py
   ```
   Hasilnya `DOCS/generated/data_dictionary.md` dan `erd_physical.mmd`. Render `.mmd` menjadi gambar dengan Mermaid CLI atau mermaid.live.
3. **Jalankan benchmark MySQL.** Pasang MySQL 8.0 (bukan MariaDB), lalu:
   ```
   venv\Scripts\pip install pymysql
   venv\Scripts\python benchmark\generate.py
   venv\Scripts\python benchmark\run.py --engine all
   ```
   Setelah itu tulis `benchmark/REKOMENDASI.md`: tabel perbandingan Q1–Q5 dan F1–F3, bobot kriteria, skor, rekomendasi akhir, dan acuan penelitian terdahulu. Ini menjawab DBMS Selection langkah d dan bagian E.
4. **`DOCS/DATABASE.md`** sudah ditulis ulang (M60). Yang tersisa: isi baris wawancara/observasi di §2.4 dengan bukti lapangan. Cakupan aslinya:
   - Analisis sistem berjalan GMLS dan tabel 5W1H.
   - Mission statement dan 5–8 mission objective, yang bisa diturunkan dari RM1–RM4.
   - System definition: diagram batas sistem dan user views untuk 5 peran.
   - Fact-finding: ringkasan observasi, studi pustaka, dan pemeriksaan dokumen (sesuai metode di B).
   - Desain konseptual: daftar entitas, relasi, domain atribut, dan kunci kandidat/primer/alternatif.
   - Desain logikal: strong/weak entity, multiplicity, normalisasi sampai 3NF untuk tabel inti (`region_observations`, `alert_events`, `disaster_events`, `data_lineage`), dan daftar constraint.
5. ~~Buat diagram UML~~ Selesai di INTERFACE.md §9 (tanpa folder baru). Cakupan aslinya:
   - Use case untuk 5 peran.
   - Activity diagram untuk alur Job Hidromet → alert, backfill oleh Data Engineer, dan CRUD kejadian.
   - Class diagram (opsional, karena ERD sudah ada).
6. **Isi `disaster_events`** dari catatan kejadian GMLS atau BPBD Lebak:
   ```
   venv\Scripts\python scripts\import_disasters.py <csv>
   ```
   Targetkan minimal sekitar 100 kejadian supaya evaluasi alert Q4 punya data nyata. Buat juga minimal satu produk fusion dan satu token API sebagai bukti fitur berjalan.
7. **Simpan hasil testing sebagai artefak:**
   - Jalankan `pytest --junitxml=DOCS/hasil_uji/pytest.xml` saat suite lain tidak sedang berjalan (memori mesin 14 GB), lalu simpan ringkasannya.
   - Jalankan `tests/recovery/*.sh` dan catat hasilnya.
   - Untuk Learnability dan Adaptability: susun skenario tugas per peran, lakukan UAT/SUS dengan 3–5 orang dari GMLS, dan simpan hasilnya di `DOCS/hasil_uji/`.
8. **Lengkapi bukti dan rapikan dokumen:**
   - Simpan bukti legalitas dan lama operasi GMLS, serta bukti review model bersama GMLS (notulen), di `DOCS/lampiran/`.
   - Selaraskan angka di README (79.000 → angka aktual).
   - Perbaiki Peta Dokumen di README §10 supaya hanya mencantumkan berkas yang memang ada.
