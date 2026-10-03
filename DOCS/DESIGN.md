# DESIGN.md — Orbital 95

Panduan gaya visual untuk project apa pun. Semua antarmuka di project ini wajib mengikuti dokumen ini. Jika ada konflik antara kebiasaan framework dan dokumen ini, dokumen ini yang menang.

## 1. Konsep

**Orbital 95** = kerangka sistem operasi tahun 1995 + layar telemetri ruang kendali satelit.

- **Kerangka (chrome)**: jendela abu-abu berbingkai timbul, title bar biru tua, tombol kotak, taskbar di bawah. Semua struktur, navigasi, form dan tombol memakai gaya ini.
- **Layar (screen)**: area data seperti peta, grafik, angka utama dan log ditampilkan di dalam "monitor CRT" gelap yang tertanam (sunken) di jendela. Isinya bercahaya hijau fosfor / amber, seperti konsol stasiun bumi.

Aturan emas: **abu-abu untuk mengendalikan, hitam bercahaya untuk melihat data.** Jangan campur keduanya dalam satu elemen.

Nada: serius, teknis, sedikit nostalgia. Bukan parodi. Tidak ada animasi berlebihan, tidak ada gradasi modern, tidak ada sudut membulat.

## 2. Design Tokens

Definisikan sebagai CSS custom properties (atau padanannya di Tailwind config / theme object).

### Warna — Chrome

| Token | Nilai | Pemakaian |
|---|---|---|
| `--desk` | `#0b1e3a` | Latar desktop (langit malam orbit) |
| `--face` | `#c0c0c0` | Permukaan jendela, tombol, panel |
| `--hilite` | `#ffffff` | Sisi terang bevel (atas, kiri) |
| `--light` | `#dfdfdf` | Bevel terang bagian dalam |
| `--shadow` | `#808080` | Bevel gelap bagian dalam |
| `--dark` | `#000000` | Sisi gelap bevel (bawah, kanan) |
| `--title-a` | `#000080` | Title bar aktif, awal gradasi |
| `--title-b` | `#1084d0` | Title bar aktif, akhir gradasi |
| `--title-off` | `#808080` | Title bar tidak aktif |
| `--select` | `#000080` | Latar teks terpilih / item aktif |
| `--text` | `#000000` | Teks di atas chrome |
| `--text-mut` | `#404040` | Teks sekunder di atas chrome |
| `--field` | `#ffffff` | Latar input teks |

### Warna — Screen (telemetri)

| Token | Nilai | Pemakaian |
|---|---|---|
| `--crt` | `#03110a` | Latar layar |
| `--crt-grid` | `#0d3320` | Garis grid tipis |
| `--phos` | `#33ff99` | Data utama, normal |
| `--phos-dim` | `#1a9960` | Label, satuan, data sekunder |
| `--amber` | `#ffb000` | Peringatan, nilai yang berubah |
| `--alert` | `#ff3b3b` | Bahaya / kritis |
| `--cyan` | `#4de1ff` | Data sensor / citra satelit |

Data spasial (peta probabilitas): gradasi dari `--crt` → `--cyan` → `#ffffff`. Peta biner: `--cyan` untuk positif, `#0a2a1e` untuk negatif.

### Tipografi

| Token | Nilai | Pemakaian |
|---|---|---|
| `--font-ui` | `"MS Sans Serif", "Microsoft Sans Serif", Tahoma, Geneva, sans-serif` | Semua chrome |
| `--font-data` | `"Fixedsys", "Lucida Console", "Courier New", monospace` | Semua isi screen |
| Ukuran UI | 12px (body), 11px (status bar), 12px bold (title bar) | |
| Ukuran data | 12px (label), 22–32px (angka utama) | |

- Tidak ada font lain. Tidak ada font weight selain 400 dan 700.
- Label di screen ditulis HURUF KAPITAL, `letter-spacing: .08em`.
- Angka selalu `font-variant-numeric: tabular-nums`.
- Antialiasing boleh dimatikan di chrome (`-webkit-font-smoothing: none`) agar terasa piksel.

### Spasi & bentuk

- Satuan dasar **4px**. Gunakan kelipatan: 4, 8, 12, 16, 24.
- **`border-radius: 0` di semua elemen.** Pengecualian satu-satunya: layar radar / orbit boleh berbentuk lingkaran.
- Tidak ada `box-shadow` blur. Bayangan hanya dari bevel 1–2px.
- Satu-satunya efek cahaya yang diizinkan: `text-shadow: 0 0 4px` pada teks di dalam screen.

## 3. Bevel (inti gaya)

Empat jenis bevel. Semua komponen dibangun dari ini.

```css
.raised {
  background: var(--face);
  box-shadow: inset -1px -1px var(--dark), inset 1px 1px var(--hilite),
              inset -2px -2px var(--shadow), inset 2px 2px var(--light);
}
.pressed {
  box-shadow: inset -1px -1px var(--hilite), inset 1px 1px var(--dark),
              inset -2px -2px var(--light), inset 2px 2px var(--shadow);
}
.sunken {
  box-shadow: inset -1px -1px var(--hilite), inset 1px 1px var(--shadow),
              inset -2px -2px var(--light), inset 2px 2px var(--dark);
}
.groove {
  border: 2px groove var(--hilite);
}
```

- **raised**: jendela, tombol, taskbar.
- **pressed**: tombol saat ditekan / toggle aktif.
- **sunken**: input, screen, status bar field, area daftar.
- **groove**: pengelompokan (fieldset).

## 4. Komponen

### Window
- Bevel `raised`, padding 3px.
- Title bar: tinggi 18–20px, gradasi horizontal `--title-a` → `--title-b`, teks putih bold 12px, ikon 16px di kiri.
- Kanan title bar: tombol kontrol 16×14px (minimize, maximize, close), bevel `raised`, ikon hitam.
- Opsional: menu bar di bawah title bar (`File  View  Orbit  Help`), huruf pertama bergaris bawah.
- Bawah: status bar berisi 2–4 field `sunken`.

### Button
- Bevel `raised`, padding 4px 16px, min-width 75px.
- Saat `:active` → `pressed`, isi bergeser 1px ke kanan-bawah.
- Tombol default/utama: tambah outline hitam 1px di luar.
- Fokus: `outline: 1px dotted #000; outline-offset: -4px`.

### Input
- Text/number/file: latar `--field`, bevel `sunken`, tinggi 22px.
- Slider: track `sunken` setinggi 4px; thumb `raised` 11×21px.
- Checkbox/radio: kotak 13px `sunken` latar putih.
- Group (fieldset): `groove`, legend menimpa garis dengan latar `--face`.

### Screen (telemetri)
- Selalu dibungkus bevel `sunken` 2px, lalu bingkai hitam 4–6px (bezel monitor).
- Latar `--crt` + grid 16px dari `--crt-grid`.
- Opsional: scanline `repeating-linear-gradient` 2px dengan opacity ≤ 0.15.
- Pojok kiri atas: label kanal, mis. `CH-01 · S1 SAR`. Pojok kanan atas: indikator `● REC` atau `● LIVE` (amber/merah).
- Gambar/canvas data: `image-rendering: pixelated`.

### Readout (angka utama)
- Screen kecil. Label `--phos-dim` 11px kapital di atas, nilai `--phos` 24–32px di bawah.
- Nilai berubah dari run sebelumnya → `--amber`. Melewati ambang kritis → `--alert`.

### Status lamp
- Kotak 10×10px (bukan bulat), bevel `sunken`, isi warna status. Hijau = nominal, amber = proses, merah = gagal.

### Taskbar
- Menempel di bawah viewport, tinggi 28px, bevel `raised`.
- Kiri: tombol **Start** bold dengan ikon satelit.
- Tengah: satu tombol per jendela terbuka; jendela aktif memakai `pressed`.
- Kanan: tray `sunken` berisi jam UTC dan status link satelit (mis. `AOS 03:12`).

### Dialog / notifikasi
- Window kecil dengan ikon 32px (info / warning / error), teks, tombol OK di kanan bawah.
- Jangan pakai toast melayang modern.

## 5. Layout

- Halaman = **desktop**. Konten tinggal di dalam satu atau beberapa **window**.
- Aplikasi tunggal: satu window utama memenuhi lebar (max 1200px, margin 16px), di atas taskbar.
- Di dalam window: grid dua kolom.
  - Kiri (240–300px): **Control Panel**, berisi semua input dalam fieldset `groove`, tombol aksi di bawah.
  - Kanan: **Telemetry Deck**, berisi baris readout lalu screen-screen data.
- Jarak antar elemen: 8px. Padding dalam window: 8px.
- Mobile (< 800px): satu kolom, urutan Control Panel → Readout → Screen. Taskbar tetap.
- Ikon desktop (opsional) di kiri atas: 32px + label putih di bawahnya.

## 6. Ikon

- Gaya piksel / garis tegas 16px dan 32px, warna terbatas (hitam, putih, abu, biru tua, kuning, cyan).
- Gunakan **inline SVG**, `shape-rendering: crispEdges` bila memungkinkan.
- Jangan pakai emoji. Jangan pakai icon set modern yang tipis dan membulat.
- Motif yang disarankan: satelit, antena parabola, orbit, globe, tetes air, folder, disket, monitor.

## 7. Bahasa & copy

- Label singkat, gaya sistem: `Jalankan`, `Batal`, `Properti…`, `Status: Siap`.
- Di dalam screen gunakan gaya telemetri: `LUAS GENANGAN`, `Δ VS SCENE T-1`, `SIGNAL OK`, `NO DATA`.
- Pesan error berupa dialog: ikon + kalimat jelas + tombol OK.

## 8. Do & Don't

**Do**
- Bevel di setiap permukaan chrome.
- Kontras tajam, piksel tegas.
- Data selalu di dalam screen gelap.
- Gunakan warna amber/merah hanya untuk arti, bukan dekorasi.

**Don't**
- `border-radius`, blur, glassmorphism, gradasi selain title bar.
- Bayangan lembut, kartu melayang.
- Teks data di atas latar abu-abu, atau kontrol form di dalam screen.
- Lebih dari 3 warna sinyal sekaligus dalam satu screen.

## 9. Penerapan per stack

- **CSS biasa**: salin token bagian 2 ke `:root` dan kelas bevel bagian 3 ke file global.
- **Tailwind**: masukkan token ke `theme.extend.colors` / `fontFamily`, set `borderRadius: { DEFAULT: '0' }`, buat utilitas `@layer components` untuk `.raised`, `.sunken`, `.pressed`, `.groove`, `.window`, `.titlebar`, `.screen`.
- **Komponen (React/Next/Vue)**: buat primitif `Window`, `TitleBar`, `Button`, `Field`, `Fieldset`, `Screen`, `Readout`, `StatusLamp`, `Taskbar`. Semua halaman disusun dari primitif ini.
- **Chart library**: latar transparan di dalam `Screen`, garis `--phos`, grid `--crt-grid`, font `--font-data`, tanpa animasi masuk.

## 10. Checklist sebelum selesai

- [ ] Tidak ada sudut membulat (kecuali radar).
- [ ] Setiap tombol punya keadaan `raised` dan `pressed`.
- [ ] Semua data numerik/visual ada di dalam screen gelap.
- [ ] Semua kontrol ada di chrome abu-abu.
- [ ] Ikon berupa SVG inline, bukan emoji.
- [ ] Layout tetap rapi di lebar 375px.
