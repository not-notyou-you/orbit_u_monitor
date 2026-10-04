# Test Results: Tahap 4 Interface & Evidence

Tanggal uji: 4 Oktober 2026. Branch `stage-4-ui-implementation`.
Lingkungan: Windows 11, Chrome headless (CDP), API lokal terhadap DB **`themonitor_dev`**
(salinan data nyata `themonitor` 1–7 Jan 2024 + 2 scene Live 22 & 27 Sep 2026, ditambah data
sintetis berlabel `UJI SINTETIS` / `UJI_SINTETIS_*`), `SCHEDULER_ENABLED=false`,
`AUTO_RESUME_JOBS=false`. Akun uji: `uji_user`, `uji_analyst`, `uji_data_engineer`, `uji_admin`.

Kriteria (INTERFACE §8 + rencana Tahap 4):
**a** fungsional sesuai INTERFACE §1–4 · **b** desain sesuai DESIGN.md · **c** RBAC ·
**d** integrasi API (sesi cookie + `X-Requested-With`) · **e** penanganan error & data kosong.

## Coverage (per halaman)

| Halaman | Fungsional | Design | RBAC | API | Error | Status | Bukti |
|---------|-----------|--------|------|-----|-------|--------|-------|
| Login (`/masuk`) | ✓ | ✓ | ✓ | ✓ | ✓ | PASS | alur auth 1–2; `login-*.png` |
| Beranda Publik (`/`) | ✓ | ✓ | ✓ (tanpa login) | ✓ | ✓ | PASS | `home-public-*.png` |
| Pantauan Live | ✓ | ✓ | ✓ | ✓ | ✓ | PASS | `monitoring-*.png`, 4 role |
| Statistik Hari Ini | ✓ | ✓ | ✓ | ✓ | ✓ | PASS | alur acknowledge; `flow-statistics-after-ack.png` |
| Analitik | ✓ | ✓ | ✓ | ✓ | ✓ | PASS | alur analitik + CSV |
| Kejadian Bencana | ✓ | ✓ | ✓ | ✓ | ✓ | PASS | alur CRUD; `flow-disaster-*.png` |
| Katalog Dataset | ✓ | ✓ | ✓ | ✓ | ✓ | PASS | 6 tab; `flow-catalog-*.png` |
| Buat Dataset | ✓* | ✓ | ✓ | ✓ | ✓ | PASS* | validasi 4 langkah; `flow-wizard-review.png` |
| Laporan | ✓ | ✓ | ✓ | ✓ | ✓ | PASS | unduh PDF, tab per audiens |
| Administrasi (12 tab) | ✓* | ✓ | ✓ | ✓ | ✓ | PASS* | `flow-admin-<tab>.png` |
| Akun Saya | ✓ | ✓ | ✓ | ✓ | ✓ | PASS | alur token (200 → dicabut 401) |

\* Aksi yang memicu unduhan data satelit **sengaja tidak dijalankan** (lihat "Tidak diuji").

### Uji alur browser — `tests/ui/flows.py` (13/13 PASS)

| # | Alur | Hasil |
|---|---|---|
| 1 | Login salah → dialog "Nama pengguna atau kata sandi salah."; validasi field kosong; login benar → `/app#pantauan` | PASS |
| 2 | Tanpa sesi `/app#analitik` → `/masuk?next=…`; Keluar → `/masuk?alasan=keluar`, `/auth/me` 401 | PASS |
| 3 | Menu Mulai per role = `permissions` backend (USER 3, ANALYST 6, DATA_ENGINEER 6, ADMIN 9 halaman); URL terlarang → jendela "Akses ditolak" | PASS |
| 4 | Keyboard: Enter membuka menu Mulai, panah berpindah, Escape menutup dan mengembalikan fokus; tab admin dengan panah | PASS |
| 5 | Token API: dibuat, tampil sekali, dipakai (200), dicabut (401) | PASS |
| 6 | ANALYST "Tandai sudah dibaca" + catatan (alert aktif 3 → 2); USER tanpa tombol | PASS |
| 7 | Kejadian: 4 pesan validasi klien → simpan → ubah (verifikasi) → hapus (soft delete) | PASS |
| 8 | Katalog: 6 tab dataset terbuka tanpa error | PASS |
| 9 | Buat Dataset: lokasi wajib, rentang > 366 hari ditolak, sumber wajib, fusi wajib (> 1 sumber), ringkasan FULL_COVERAGE + toleransi, "Pakai konfigurasi sebelumnya" | PASS |
| 10 | Analitik: rentang terbalik ditolak, band NDVI, ekspor CSV tanpa error | PASS |
| 11 | Laporan: ANALYST hanya tab Hidromet + unduh PDF; DATA_ENGINEER hanya Kesehatan Data | PASS |
| 12 | Admin: 12 tab tanpa error; validasi username; akun baru dibuat; menurunkan peran sendiri → "Anda tidak dapat menonaktifkan atau menurunkan peran akun sendiri." | PASS |
| 13 | 404 → dialog "Data tidak ditemukan."; 500 → "Terjadi kesalahan di server." | PASS |

### Pemeriksaan otomatis per tangkapan — `tests/ui/screenshots.py`

11 halaman × 3 lebar (+ 3 role tambahan di 1920 px) = 60 pemeriksaan: tanpa error JS, tanpa HTTP ≥ 400
tak terduga, tanpa scroll horizontal, tanpa `border-radius` ≠ 0 (di luar kontrol Leaflet), semua input
berlabel, semua `<img>` punya `alt`. Hasil: **59 OK + 1 catatan yang diharapkan** (404
`/api/datasets/last-config` untuk ADMIN yang belum pernah membuat dataset — itulah cara UI mengetahui
tombol "Pakai konfigurasi sebelumnya" disembunyikan). Detail: `tests/screenshots/report.json`.

## Responsive Breakpoints

- [x] 320px (mobile) — satu kolom, urutan Control Panel → Readout → Screen, taskbar tetap, tombol tugas disembunyikan < 420 px
- [x] 768px (tablet) — satu kolom (< 800 px, DESIGN §5), tile 2 kolom
- [x] 1920px (desktop) — jendela maks. 1200 px, grid 2 kolom

Tangkapan: `tests/screenshots/<halaman>-{mobile,tablet,desktop}.png` (33 berkas) + `flow-*.png`.

## Accessibility

- [x] Keyboard navigation (alur 4; dialog: Tab berputar, Escape menutup, fokus kembali ke pemicu)
- [x] ARIA labels (semua input berlabel — diperiksa otomatis; `role` dialog/tablist/listbox/menu; peta punya `aria-label` dan datanya juga di tabel/kartu)
- [~] Color contrast ≥ 4.5:1 — 12 dari 13 pasangan teks lolos; lihat tabel

| Pasangan (teks / latar) | Rasio | |
|---|---|---|
| Teks chrome `#000` / `#c0c0c0` | 11,5 | OK |
| Teks sekunder & hint `#404040` / `#c0c0c0` | 5,7 | OK |
| Pesan error form `#800000` / `#c0c0c0` | 6,0 | OK |
| Input `#000` / `#fff` | 21,0 | OK |
| Pilihan aktif / title bar awal `#fff` / `#000080` | 16,0 | OK |
| Data utama `--phos` / `--crt` | 14,6 | OK |
| Label screen `--phos-dim` / `--crt` | 5,3 | OK |
| Amber / `--crt` | 10,5 | OK |
| Alert `#ff3b3b` / `--crt` | 5,5 | OK |
| Cyan / `--crt` | 12,4 | OK |
| **Title bar ujung kanan `#fff` / `#1084d0`** | **4,0** | KURANG — known issue |
| Teks nonaktif `#808080` / `#c0c0c0` | 2,2 | dikecualikan WCAG 1.4.3 |

- [x] Warna bukan satu-satunya pembawa makna: kategori BMKG (teks + singkatan + arsir), status/alert (teks), lampu status (teks di sampingnya).

## Uji otomatis (pytest, DB `themonitor_test`)

`python -m pytest --ignore=tests/ui` → **1038 passed, 0 failed** (4 menit 25 detik), termasuk tes baru Tahap 4:
`tests/test_web_ui.py` (rute ↔ fragmen/skrip, terjemahan semua kode error, aturan desain statis, tanpa token
di storage), `tests/test_openapi_docs.py`, regresi RBAC Live (`test_live_area_backed_by_dataset_readable_by_user`,
`test_live_preview_readable_by_user_and_analyst`), `test_create_dataset_rejects_range_over_366_days`,
`by_rule` evaluasi alert.

## Recoverability

`SRC_DB=themonitor_dev bash tests/recovery/backup_restore.sh` → **PASS**: 39 tabel, 10.220 baris, 13+ VIEW,
29 trigger, 3 policy RLS, 200 GRANT identik setelah pg_dump → DB kosong → pg_restore.

## Tidak diuji (dengan alasan)

| Hal | Alasan |
|---|---|
| Kirim "Buat dataset", Coba ulang/Lanjutkan dataset | Langsung menjalankan pipeline yang mengunduh data satelit (dilarang di lingkungan ini) |
| Admin: Picu ingestion, Proses ulang scene, Periksa sekarang (Live), Tambah Live Area | Mengunduh data satelit |
| Impor Excel lewat browser (berkas nyata) | Tidak ada berkas GMLS; jalur impor diuji di backend (`tests/test_excel_io.py`); dialog uji-kering UI belum dicoba end-to-end |
| SUS & tugas learnability dengan relawan GMLS | Butuh sesi tatap muka — template `DOCS/prototype_feedback.md` |
| Tampilan dengan arsip penuh (tren 30 hari, heatmap bertahun, evaluasi alert nyata) | Backfill hidromet 2023–2025 masih dijeda |
| Peta tanpa internet | Leaflet dari CDN unpkg; tanpa internet screen menampilkan pesan, halaman lain berjalan |

## Known Issues (from IMPLEMENTATION_NOTES.md)

1. Kontras title bar di ujung gradasi `--title-b` 4,0:1 (token DESIGN.md). Judul panjang di 320 px bisa sampai ujung kanan.
2. Leaflet dan tile Esri dari CDN (disetujui), tidak tersedia luring.
3. Tombol aksi kecil per baris tabel berada di dalam screen (pengecualian DESIGN §8 yang tercatat).
4. Font sistem fallback (Tahoma / Lucida Console) dipakai bila MS Sans Serif / Fixedsys tidak ada.
5. Ekspor CSV observasi hanya untuk satu kecamatan atau seluruh AOI (keterbatasan endpoint).
6. Beranda Publik tidak menampilkan tanggal per sumber (endpoint publik hanya membawa tanggal scene).
