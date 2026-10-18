# DESIGN.md — Orbital 95

Design system bawaan Orbit-U: The Monitor (M50). Ditulis ulang 8 Oktober 2026 dari `web/css/main.css`,
`web/css/pages.css`, dan `web/js/ui.js`. Kalau isi dokumen ini berbeda dengan CSS, **CSS yang benar**.
Dokumen inilah yang diperbaiki.

Nomor bagian dirujuk kode, misalnya `DESIGN §4` di `web/js/ui.js` dan `DESIGN §6` di `main.css`. Jangan
menomori ulang.

Susunan halaman, peran, dan endpoint ada di INTERFACE.md. Dokumen ini hanya membahas bahasa visual.

---

## 1. Prinsip

> **Kontrol abu-abu, data di layar gelap.**

- **Chrome** (jendela, tombol, isian, tab, taskbar) meniru Windows 95: abu-abu `#c0c0c0` dengan tepi
  berbevel. Pengguna langsung tahu mana yang bisa diklik.
- **Data** (angka, tabel, grafik, log) tampil di dalam "layar CRT" hitam dengan teks fosfor hijau. Mata
  langsung tahu mana isi dan mana kontrol.
- Tanpa sudut membulat, tanpa blur, tanpa emoji, tanpa animasi hiasan.
- Warna tidak pernah menjadi satu-satunya pembawa makna (§8).
- UI vanilla HTML/CSS/JS tanpa *build step*.

---

## 2. Token

Didefinisikan di `:root` dalam `main.css`.

**Chrome**

| Token | Nilai | Dipakai untuk |
|---|---|---|
| `--desk` | `#0b1e3a` | Latar desktop |
| `--face` | `#c0c0c0` | Permukaan jendela & tombol |
| `--hilite` / `--light` | `#ffffff` / `#dfdfdf` | Sisi terang bevel |
| `--shadow` / `--dark` | `#808080` / `#000000` | Sisi gelap bevel |
| `--title-a` → `--title-b` | `#000080` → `#1084d0` | Gradasi title bar aktif |
| `--title-off` | `#808080` | Title bar tidak aktif |
| `--select` | `#000080` | Seleksi, menu aktif, tautan |
| `--text` / `--text-mut` | `#000000` / `#404040` | Teks |
| `--field` | `#ffffff` | Isian |

**Layar data**

| Token | Nilai | Arti |
|---|---|---|
| `--crt` | `#000000` | Latar layar |
| `--crt-grid` | `#1f4d35` | Garis tabel & grid grafik |
| `--phos` | `#33ff99` | Nilai normal |
| `--phos-dim` | `#5fd99b` | Label, satuan, keterangan |
| `--amber` | `#ffb000` | Waspada |
| `--alert` | `#ff3b3b` | Bahaya / gagal |
| `--cyan` | `#4de1ff` | Tautan & seleksi di layar |

**Tipografi**

| Token | Nilai |
|---|---|
| `--font-ui` | "MS Sans Serif", Tahoma, sans-serif. Ukuran 12px, tanpa *font smoothing* |
| `--font-data` | Consolas, "Cascadia Mono", "DejaVu Sans Mono", monospace. 14px tebal, angka `tabular-nums` |

Judul (`h1`–`h4`) tetap 12px tebal. Hierarki dibentuk oleh jendela dan title bar, bukan oleh ukuran huruf.

**Bentuk.** `border-radius: 0` berlaku untuk semua elemen. Tidak ada `blur` atau `backdrop-filter`. Aturan ini
diuji `tests/test_web_ui.py`.

---

## 3. Bevel

Empat kelas, semuanya disusun dari dua lapis `box-shadow` inset (1px dan 2px):

| Kelas | Kesan | Dipakai untuk |
|---|---|---|
| `.raised` | Menonjol | Jendela, tombol, taskbar |
| `.pressed` | Ditekan | Tombol `:active`, Mulai yang terbuka |
| `.sunken` | Cekung | Isian, bingkai layar, panel status |
| `.groove` | Alur | Pemisah, `fieldset` |

---

## 4. Komponen

Primitifnya dibangun lewat `web/js/ui.js` supaya markup tetap seragam.

| Komponen | Aturan |
|---|---|
| **Jendela** (`.window`) | Bevel menonjol, lebar maksimal 1200px (`.small` 420, `.medium` 720). Isi di `.window-body` dengan padding 8px |
| **Title bar** | Gradasi biru, teks putih tebal, ikon 16px di kiri, tombol 16×14 di kanan. Jendela tidak aktif: abu-abu |
| **Menu bar** (`.menubar`) | Tepat di bawah title bar. Navigasi utama terlihat tanpa harus membuka Mulai. Halaman aktif ditandai `aria-current="page"` dengan latar `--select` |
| **Lede** (`.page-lede`) | Satu baris instruksi di setiap halaman: untuk apa halaman ini dan apa langkah pertamanya (M53). Diletakkan di chrome, bukan di layar |
| **Status bar** | Panel-panel cekung 11px di dasar jendela |
| **Tombol** | Bevel menonjol, `.default` untuk aksi utama. Saat sibuk, tombol diberi `aria-busy` |
| **Tab** | Gaya *property sheet*: tab aktif menyatu dengan panelnya |
| **Layar** (`.screen` > `.screen-inner`) | Bingkai cekung + tepi hitam 5px + garis pindai tipis. Label kanal di kiri atas (`.scr-ch`), indikator rekam di kanan atas (`.scr-rec`, `.live` merah). Isi kosong ditampilkan `.scr-empty` dalam huruf kapital |
| **Tabel data** (`.scr-table`) | Di dalam layar. Header kapital `--phos-dim`, angka rata kanan (`.r`) |
| **Readout** | Angka besar 30px + label + sub-label, dalam grid otomatis minimal 170px |
| **Lampu status** (`.lamp`) | 10×10, `.ok` hijau, `.busy` amber, `.fail` merah. Selalu didampingi teks |
| **Tag** | Kotak bergaris 1px berisi teks kategori |
| **Taskbar** | Tetap di bawah, tinggi 28px. Isinya: tombol **Mulai** (menu per peran), saklar "Garis wilayah", tombol tugas, dan tray (akun) |
| **Dialog** (`UI.dialog`) | Modal berbentuk jendela: ikon 32px + teks + tombol di kanan bawah. Lebar 420/760/1000. **Escape** menutup dialog dengan nilai *cancel*, dan fokus kembali ke elemen pemicu. Semua pesan memakai dialog. Tidak ada *toast* |
| **Spanduk** (`.banner`) | Pemberitahuan di chrome: ikon 32px + teks |

---

## 5. Layout

- Desktop: grid `.layout`, `.cols-2`, `.cols-3`, dan ubin `.tiles`. Jarak antarjendela 16px.
- **< 800px:** semua kolom menjadi satu, ubin menjadi 2 kolom, peta setinggi 300px, tray tambahan
  disembunyikan.
- **< 420px:** ubin menjadi 1 kolom, readout 24px, tombol tugas taskbar disembunyikan.
- `prefers-reduced-motion`: animasi tombol sibuk dimatikan.
- Badan halaman diberi padding bawah setinggi taskbar supaya isinya tidak tertutup taskbar.

---

## 6. Ikon

- SVG inline dari `ICONS` di `web/js/ui.js`, **dua ukuran saja: 16px** (title bar, tombol, taskbar) **dan
  32px** (dialog, spanduk, ikon desktop). Tombol title bar memakai glyph 8×7.
- `shape-rendering: crispEdges` agar garis ikon tetap tajam di piksel.
- **Tanpa emoji** di fragmen halaman (diuji `tests/test_web_ui.py`).

---

## 7. Bahasa dan Format

- Seluruh UI berbahasa Indonesia. API memakai bahasa Inggris.
- Kode galat API diterjemahkan ke kalimat Indonesia di `web/js/ui.js` (M21). Setiap kode yang dilempar API
  wajib punya terjemahan, dan ini diuji `tests/test_web_ui.py`.
- Angka dan tanggal diformat dengan `id-ID`.
- Label di dalam layar memakai huruf kapital dengan jarak huruf 0,08em.

---

## 8. Warna Sinyal

Hanya **tiga** warna sinyal: `--phos` (normal) → `--amber` (waspada) → `--alert` (bahaya). Makna tidak boleh
bergantung pada warna saja. Setiap sinyal juga punya **teks** dan, kalau perlu, **pola**.

Contoh kategori hujan BMKG (`UI.BMKG`):

| Kategori | Rentang | Warna | Penanda |
|---|---|---|---|
| Ringan | < 20 mm | hijau gelap, transparan | · |
| Sedang | 20–< 50 mm | `--phos` | ▪ |
| Lebat | 50–< 100 mm | `--amber` | ▲ |
| Sangat lebat | 100–< 150 mm | `--alert` + arsir A | ▲▲ |
| Ekstrem | ≥ 150 mm | `--alert` pekat + arsir B | ▲▲▲ |

Nama kategori selalu tertulis.

**Kontras di chrome.** Warna fosfor hanya terbaca di atas hitam. Kalau kelas yang sama (`.v-amber`,
`.v-alert`, `.v-cyan`, `.v-dim`) dipakai di permukaan abu-abu, Orbital 95 memakai versi gelapnya: `#5c3700`,
`#880000`, `#00475f`, dan `#134a28`.

Peta perubahan air memakai palet sendiri yang bermakna geografis (biru = air tetap, merah = air baru, hijau =
surut). Palet ini juga selalu disertai legenda berteks (PIPELINE.md §4.1).

---

## 9. Tema Tambahan (M57)

Orbital 95 adalah tema **bawaan**. Tiga tema lain diambil dari konsep di `DOCS/design tambahan/`:

| Kunci | Nama | Konsep |
|---|---|---|
| `mint` | Kertas Mint | konsep38 |
| `pasir` | Mika Pasir | konsep41 |
| `piksel` | Piksel Marun | konsep44 |

- Tema dipilih di Tentang (sebelum M63 di Beranda), lalu diterapkan `web/js/theme.js` sebagai `data-theme` di `<html>` **sebelum**
  `<body>` diurai, sehingga tidak ada kedipan tema bawaan.
- Pilihan disimpan di `localStorage` (`orbit-u.tema`) per peramban, bukan per akun.
- CSS tema ada di `web/css/tema/`: `umum.css` (struktur bersama, tercakup `html.tema-alt`) ditambah satu
  berkas per tema. Semua aturannya tercakup selektor tema, jadi Orbital 95 tidak tersentuh.
- Tema hanya mengganti tampilan. Struktur halaman, router, dan data tetap sama.
- Larangan radius/blur (§2) **tidak** berlaku untuk CSS tema tambahan, tetapi setiap aturannya wajib tercakup
  selektor temanya sendiri. Larangan emoji (§6) tetap berlaku karena menyangkut fragmen halaman, bukan tema.
  Keduanya diuji `tests/test_web_ui.py`.
