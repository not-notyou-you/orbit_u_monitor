# Audit Output Project terhadap SKRIPSI.txt

Acuan: Pedoman Penelitian Skripsi Prodi SI versi 1.3, peminatan Database, jalur Design and Implementation (ringkasannya di SKRIPSI.txt). Ketentuan versi lama yang tidak ada di 1.3 tidak dinilai.

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
| D. Rancangan Database | Terjawab (8 Okt 2026): skema + DATABASE.md + `DOCS/generated/data_dictionary.md` dan `erd_physical.mmd` (38 tabel, 19 VIEW; dibangkitkan ulang 19 Okt 2026 setelah M63/M64: 43 tabel, 22 VIEW) |
| D. Rekomendasi DBMS | Terjawab (8 Okt 2026): PostgreSQL dan MySQL 8.0 diuji, rekomendasi di [PERBANDINGAN_DBMS.md](PERBANDINGAN_DBMS.md). Acuan penelitian terdahulu belum ada |
| D. Rancangan Sistem/Aplikasi | Terjawab |
| D. API / middleware | Tidak wajib: pedoman 1.3 mewajibkannya hanya bila penelitian berfokus pada integrasi. API tetap ada (`api/`, OpenAPI `/docs`) |
| C.2 Master ≥ 10, transaksi ≥ 100 | Terjawab |
| C.1 Legalitas objek studi ≥ 2 tahun | Tidak diperlukan (22 Okt 2026): GMLS mitra resmi UMN (MoU melalui LPPM) dan objek studi sudah disetujui program studi. GMLS berdiri 13 Okt 2020 (`lampiran/profil.jpeg`, notulensi) |
| A. Tahap DBSDLC: implementasi, loading, keamanan | Terjawab |
| A. Tahap DBSDLC: perencanaan, analisis, desain konseptual dan logikal, UML | Sebagian (8 Okt 2026): DATABASE.md, PIPELINE.md, DESIGN.md ditulis ulang dari kode (M60). UML di INTERFACE.md §9. Fact-finding GMLS: wawancara 16 Okt 2026 (`lampiran/notulensiGMLS.txt`, DATABASE.md §2.4). Belum: hasil isian lembar tinjauan kebutuhan dari GMLS (requirement/user review, disiapkan 23 Okt 2026) |
| A. Testing: evaluasi minimum Tabel 4 | Sebagian: integrity, functional, security, query, dan backup/recovery punya bukti (pytest 1.187/1.187 pada 19 Okt 2026, INTERFACE.md §7, `DOCS/hasil_uji/`, `benchmark/`). Requirement/user review belum |

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
- **Backup/recovery** diuji lewat [backup_restore.sh](../tests/recovery/backup_restore.sh), [kill_and_resume.sh](../tests/recovery/kill_and_resume.sh), dan `recovery_backfill.py`. Dijalankan 23 Okt 2026, lulus: restore salinan produksi identik isi, dan backfill pulih setelah `kill -9`. Ini memenuhi evaluasi minimum backup/recovery jalur Design and Implementation (pedoman 1.3, Tabel 4). Rincian di INTERFACE.md §7.2 dan `DOCS/hasil_uji/`. Backup harian terjadwal (M66, PIPELINE.md §13): tugas didaftarkan pemilik 23 Okt 2026, run uji 11:11 berhasil (`LastTaskResult` 0, dump 5 MB), jadwal berikutnya 24 Okt 01:30.
- **Integrity**: PK/FK, CHECK, UNIQUE, dan trigger di skema; diuji `test_database`, `test_schema_comments`, `test_audit`.
- **Functional**: skenario black-box per fitur (`test_*_api`, `test_alert_engine`, `test_notify`, dan lainnya).
- **Security**: matriks GRANT/VIEW/RLS (`tests/security/grant_matrix.sql`), `test_rbac_api`, `test_auth`, `test_credentials`.
- **Query**: benchmark Q1–Q6 (`benchmark/results/`).

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
- ~~`fusion_products` 0, `api_tokens` 0~~ Terbukti 22 Okt 2026: dataset #3 "Fusion AOI GMLS Okt 2026" (S1 + MODIS + GPM PROCESSED, CO_OCCURRENCE, 1–16 Okt 2026, AOI GMLS) selesai `COMPLETED`: 6/6 scene S1, **4 HDF5** (4, 9, 12, 16 Okt), masing-masing berisi grup `sentinel1` (VV, VH), `modis` (FLOOD, NDVI, NDWI + umur data), `gpm` (24h/72h/7d). Tercatat di `fusion_products`, `data_products` (tier FUSED) dan 12 baris `data_lineage` ke produk FUSED. `api_tokens` 1. `cleanup_operations` 0 masih wajar.
- README menyebut `region_observations` "±79.000 baris". Isi sebenarnya 68.120. Angka ini perlu diselaraskan.

### f. Requirement/user review

Evaluasi minimum pertama di Tabel 4. Kebutuhan sudah dikumpulkan lewat wawancara GMLS 16 Okt 2026 (`lampiran/notulensiGMLS.txt`), tetapi belum ada bukti GMLS meninjau kebutuhan dan rancangan yang dihasilkan. Sarana tinjauan: halaman web `lampiran/user_review_webapp/` (kebutuhan, model data konseptual dan logikal dalam bahasa awam, batasan, peran, persetujuan); traceability butir → notulen → objek basis data di DATABASE.md §2.4.

### g. Prasyarat objek studi (C.1)

~~Belum ada bukti.~~ Tidak diperlukan (22 Okt 2026): GMLS bermitra resmi dengan UMN (MoU melalui LPPM) dan objek studi sudah disetujui program studi. Sebagai informasi, profil resmi menyebut GMLS berdiri 13 Oktober 2020.

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
   - Untuk requirement/user review: minta GMLS meninjau kebutuhan dan batasan sistem (lembar tinjauan atau konfirmasi singkat), lalu simpan buktinya di `DOCS/lampiran/`.
8. **Lengkapi bukti dan rapikan dokumen:**
   - Simpan bukti legalitas dan lama operasi GMLS, serta bukti review model bersama GMLS (notulen), di `DOCS/lampiran/`.
   - Selaraskan angka di README (79.000 → angka aktual).
   - Perbaiki Peta Dokumen di README §10 supaya hanya mencantumkan berkas yang memang ada.
