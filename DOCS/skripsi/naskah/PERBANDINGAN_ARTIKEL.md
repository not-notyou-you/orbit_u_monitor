# Perbandingan Dua Draf Artikel Jurnal

Kedua artikel bersumber dari skripsi yang sama. Pilih **salah satu** untuk dikirim lebih dulu. Mengirim keduanya
bersamaan termasuk pengiriman ganda dan dilarang oleh kedua jurnal.

| | **GaEE** (`ARTIKEL GaEE.docx`) | **Earth Science Informatics** (`ARTIKEL ESI.docx`) |
|---|---|---|
| Penerbit | AGH University of Krakow | Springer Nature |
| Templat | Templat Word resmi GaEE (sudah dicek sama dengan versi terbaru) | Tidak ada templat Word khusus; naskah Word polos mengikuti *submission guidelines* |
| Jenis artikel | Artikel riset | *Software article*, wajib ada bagian "Design and Implementation" dan "Availability and requirements" |
| Sudut pandang | Studi kasus: masalah GMLS, lalu rancangan basis data sebagai solusinya | Geoinformatika: cara data tiga satelit diharmonisasi, disimpan, dan dilacak asal-usulnya |
| Isi utama | Analisis masalah, metode DBSDLC, normalisasi, pemilihan DBMS, evaluasi, uji pengguna | Tier pemrosesan, agregasi zonal (rumus sesuai kode), aturan revisi GPM, model data, *lineage*, penanganan kegagalan, pemilihan DBMS |
| Porsi GMLS dan pengguna | Besar | Kecil (konteks, kebutuhan R1–R6, satu paragraf uji pengguna) |
| Sitasi | Bernomor [1], 33 referensi | Penulis-tahun (Nama 2025), 28 referensi |
| Gambar dan tabel | 4 gambar, 4 tabel | 6 gambar (termasuk *pipeline* dan *lineage*), 5 tabel (termasuk penanganan kegagalan) |

## Kelebihan dan Kekurangan

**GaEE**
- **Kelebihan:**
  - Struktur artikelnya paling dekat dengan skripsi, jadi paling mudah dipertanggungjawabkan di depan dosen.
  - Sisi rekayasa sistem dan manfaat untuk komunitas tersampaikan utuh.
  - Templat resminya tersedia.
- **Kekurangan:**
  - Sisi geoinformatika dibahas lebih dangkal.
  - Pembaca jurnal ini lebih ke rekayasa geomatika dan lingkungan, bukan sistem basis data.

**Earth Science Informatics**
- **Kelebihan:**
  - Ruang lingkupnya paling pas dengan basis data dan sistem informasi untuk data kebumian.
  - Jenis *software article* sesuai dengan jalur *design and implementation*.
  - Kekuatan teknis sistem tampil jelas: *provenance*, idempoten, dan pemulihan.
  - Penerbitnya Springer.
- **Kekurangan:**
  - Lebih selektif.
  - Mewajibkan lisensi terbuka pada repositori, yang saat ini belum ada.
  - Uji pengguna dan peran GMLS hanya dibahas singkat.
  - Reviewer kemungkinan akan menanyakan keterbatasan teknis: ambang tetap −20 dB, pendekatan cos(lintang), dan belum adanya evaluasi ketepatan peringatan.

## Saran Singkat

- **Pilih ESI** kalau ingin menonjolkan kontribusi teknis dan siap menambahkan lisensi pada repositori.
- **Pilih GaEE** kalau ingin artikel yang paling setia pada skripsi, termasuk sisi komunitas dan pengguna.

## Isian yang Masih Kosong di Kedua Draf

- Nama pembimbing, ORCID, e-mail.
- Konfirmasi tidak ada pendanaan.
- Pernyataan persetujuan partisipan uji coba (khusus ESI).
- Lisensi repositori dan spesifikasi server (khusus ESI).
