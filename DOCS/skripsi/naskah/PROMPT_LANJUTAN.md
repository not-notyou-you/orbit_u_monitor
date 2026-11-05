Saya melanjutkan pekerjaan skripsi dari percakapan sebelumnya. Tolong baca konteks berikut, lalu periksa berkas yang disebut sebelum mengerjakan permintaan saya.

## Identitas
- Mahasiswa: Muhammad Faiq Hakim Ulinnuha, NIM 00000110782, Program Studi Sistem Informasi, Fakultas Teknik dan Informatika, Universitas Multimedia Nusantara, 2026.
- Peminatan Database, jalur Design and Implementation (Pedoman Penelitian Skripsi Prodi SI v1.3; ringkasannya di `themonitor/DOCS/skripsi/ketentuan/SKRIPSI.txt`).
- Judul: "Perancangan Sistem Basis Data Monitoring Hidrometeorologi untuk Dukungan Mitigasi Bencana Lebak Selatan Berbasis Satelit Sentinel-1, MODIS, dan GPM". Objek: Gugus Mitigasi Lebak Selatan (GMLS). Nama sistem: Orbit-U: The Monitor.

## Keadaan naskah sekarang
- Naskah final: `themonitor/DOCS/skripsi/naskah/SKRIPSI FINAL.docx` (halaman awal, BAB I–V, Daftar Pustaka 60 entri gaya IEEE). Lampiran sengaja belum disusun.
- Naskah TIDAK disunting manual. Naskah dibangun ulang dari skrip di `themonitor/DOCS/skripsi/bahan_naskah/` (build_skripsi.py, bab4.py, bab5_front.py):
  - `build_skripsi.py` (BAB I–III, daftar pustaka `REF`, sitasi `[@kunci]` dinomori otomatis menurut urutan kemunculan, halaman awal dan BAB V disisipkan dari `bab5_front.py`);
  - `bab4.py` (BAB IV sebagai daftar blok; rujukan gambar/tabel `{G:kunci}`/`{T:kunci}` dinomori otomatis);
  - gambar di `gambar_bab4/`, `alur_penelitian.png`, `peta_wilayah.png` (folder dan berkas gambar ini tidak ada di repo; dibangkitkan ulang dari `DOCS/skripsi/bahan_naskah/` dengan `shot3.py` dan skrip gambar lain); skrip gambar `alur.py`, `peta.py`, `chart_q.py`, `render_mmd.py`, `erdcore.py`, sumber Mermaid di `mermaid/`.
  - Perintah bangun: `python build_skripsi.py "<path>/BACKUP - TEMPLATE SKRIPSI.docx" keluaran.docx <folder berisi alur_penelitian.png & peta_wilayah.png> gambar_bab4`
  - Template bersih: `themonitor/DOCS/skripsi/ketentuan/BACKUP - TEMPLATE SKRIPSI.docx` (jangan diubah). Ringkasan ketentuan prodi: `themonitor/DOCS/skripsi/ketentuan/SKRIPSI.txt`. Status keterpenuhan ketentuan: `themonitor/DOCS/skripsi/AUDIT_SKRIPSI.md`.
- Template berbahasa Indonesia, Times New Roman 12, spasi 1,5, lebar area teks 14 cm (gambar maksimal 14 cm). Word harus "Update fields" (sudah diatur otomatis) agar Daftar Isi/Tabel/Gambar terisi.

## Aturan kerja yang sudah disepakati
1. Tidak boleh berhalusinasi. Setiap informasi harus berasal dari referensi (minimal abstraknya) atau dari proyek (kode, skema, database, dokumen, lampiran). Bila ada konflik antara dokumen dan kode, kode yang benar.
2. Referensi harus punya DOI dan abstrak; artikel baru diutamakan open access, terbit 2022 ke atas, dan sumber kredibel. Pengecualian yang disetujui: dokumen resmi BMKG (buletin, surat peringatan dini, Peraturan BMKG No. 9/2022) dan dataset COD-AB di HDX. Metadata selalu dicek ke Crossref.
3. Pedoman prodi TIDAK boleh disebut, dikutip, atau disitasi di naskah (arahan dosen).
4. Setiap tabel dan gambar harus diikuti paragraf yang menambah informasi, bukan mengulang isinya.
5. Tabel/visualisasi hanya bila memperjelas. Tidak menambah hal yang tidak diminta ketentuan atau tidak didukung proyek.
6. Arahan dosen: jawaban tinjauan kebutuhan GMLS boleh memakai data dummy (`themonitor/DOCS/skripsi/lampiran/user_review_webapp/CONTOH_DUMMY_jawaban_tinjauan_kebutuhan.csv`) seolah asli; data kejadian bencana resmi boleh kosong; syarat 2 jurnal dosen UMN sudah terpenuhi; semua referensi di `DOCS/skripsi/referensi/` disimpan. UAT dummy TIDAK dipakai.
7. Setelah mengubah naskah: bangun ulang, validasi .docx, cek tidak ada rujukan gambar/tabel menggantung, nomor sitasi berurutan, dan tidak ada inkonsistensi antarbab.

## Sumber utama
- Proyek: `themonitor/` (kode `api/`, `etl/`, `database/monitor_schema.sql`, `monitor_security.sql`, `tests/`, `benchmark/`).
- Dokumen: `themonitor/DOCS/` (README.md, DATABASE.md, PIPELINE.md, INTERFACE.md, PERBANDINGAN_DBMS.md), visual di `DOCS/skripsi/bahan_naskah/` (data snapshot DB kampus 24 Okt 2026 di `assets/data.js`), hasil uji di `DOCS/hasil_uji/`.
- Lampiran GMLS (diutamakan untuk BAB III): `DOCS/skripsi/lampiran/` (notulensiGMLS.txt, Notulen Diskusi dengan GMLS.txt, Lembar_Tinjauan_Kebutuhan_GMLS.docx, user_review_webapp/, video_demo/).
- Referensi: `DOCS/skripsi/referensi/abstrak_referensi.csv` (abstrak 60 RIS awal), `DOCS/skripsi/referensi/kandidat_tambahan/` (pilihan_final.ris/csv: 30 referensi tambahan terpilih; daftar kandidat mentah dihapus 29 Okt 2026, ada di riwayat git), `DOCS/skripsi/referensi/pdf/` (PDF artikel; unduh ulang dengan `unduh_pdf.py`). Folder `bmkg/` untuk PDF dokumen BMKG belum ada di repo.
- Database lokal laptop adalah snapshot lama (5 Okt 2026); angka produksi diambil dari `DOCS/skripsi/bahan_naskah/assets/data.js` (snapshot kampus) atau dari database di komputer kampus.

## Fakta kunci yang dipakai di naskah (harus konsisten)
- 43 tabel (12 master), 22 VIEW, 528 kolom, 226 constraint (PK 43, FK 80, UNIQUE 36, CHECK 67), 162 indeks, 29 trigger, 3 policy RLS.
- region_observations 72.850 record (1 Jan 2024–22 Okt 2026), alert_events 210; 17 tabel transaksi ≥ 100 record.
- Wilayah: 10 kecamatan (Banjarsari, Bayah, Cibeber, Cigemblong, Cihara, Cijaku, Cilograng, Malingping, Panggarangan, Wanasalam), ±1.575,8 km².
- DBMS: PostgreSQL 18.6 + PostGIS 3.6.2 vs MySQL 8.0.40, skor 4,90 vs 2,90.
- Pengujian: pytest 1.185 kasus (1.183 lulus, 0 gagal, 2 dilewati); test_rbac_api 165 kasus; grant_matrix 390 sel; backup/restore dan kill-and-resume lulus.
- Ambang hujan BMKG: lebat 50, sangat lebat 100, ekstrem >150 mm/hari; aturan longsor belum aktif.
- Kebutuhan pengguna K1–K6; kuesioner tinjauan lima bagian (formulir web).

## Yang masih terbuka
- Nama/NIDN pembimbing, kaprodi, dekan, rektor, penguji, dan tanggal di halaman awal; centang pernyataan AI dan persetujuan publikasi (diisi mahasiswa).
- Jawaban asli tinjauan kebutuhan GMLS (ganti data dummy di subbab 4.3.4 dan BAB V bila sudah ada).
- Lampiran (ERD semua modul, kamus data lengkap, notulen, hasil uji) belum disusun.
- Tampilan dokumen belum diperiksa visual di Word.

## Permintaan saya kali ini
[tulis revisi atau tugas baru di sini]
