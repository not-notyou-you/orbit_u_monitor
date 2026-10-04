# COMPONENT LIBRARY — Orbital 95 di Orbit-U: The Monitor

Panduan memakai komponen UI yang sudah ada di `web/`. Aturan visual (token,
bevel, layout) ada di [`DESIGN.md`](DESIGN.md); dokumen ini menjelaskan **cara
memakainya di kode** supaya halaman baru konsisten tanpa menyalin gaya.

Semua komponen: HTML/CSS/JS vanilla, tanpa build. CSS global di
`web/css/main.css`; helper JS di `web/js/ui.js` (objek global `UI`).

| Berkas | Isi |
|---|---|
| `web/css/main.css` | Token §2, kelas bevel §3, semua komponen di bawah, layout, responsif |
| `web/js/ui.js` | Ikon SVG, format id-ID, dialog, screen/readout/tabel, grafik SVG, kategori BMKG, terjemahan kode error |
| `web/js/api.js` | `API.get/post/put/patch/del/download` — cookie sesi + `X-Requested-With: orbit-u`, error → `API.ApiError` |
| `web/js/auth.js` | `Auth.require/can/role/logout` — izin menu dari `/api/auth/me` |
| `web/js/app.js` | Kerangka: router `/app#…`, jendela halaman, taskbar + menu Mulai |
| `web/js/excel.js` | Kotak ekspor/templat/impor Excel |
| `web/js/maps.js` | Peta Leaflet di dalam screen |
| `web/js/live-tiles.js` | Tile preview Live + legenda + kalimat kondisi |

---

## 1. Halaman baru

1. Tambah rute di `ROUTES` (`web/js/app.js`): `hash`, `file`, `title`, `icon`, `perm` (kunci dari `permissions` `/auth/me`), `css` opsional.
2. Buat fragmen `web/pages/<file>.html` — **isi badan jendela saja** (router membungkusnya dengan jendela, title bar, dan status bar).
3. Buat `web/js/<file>.js`:

```js
'use strict';
Pages['contoh'] = (() => {
  let st = null;
  async function init(root, ctx) {          // ctx = { me, route, setStatus }
    st = { root, ctx };
    ctx.setStatus('Memuat…');
    try { const r = await API.get('/api/…'); /* render */ ctx.setStatus('Siap'); }
    catch (e) { UI.showError('Contoh', e); }
  }
  function destroy() { st = null; }          // hentikan timer, map.remove()
  return { init, destroy };
})();
```

Halaman yang tidak boleh diakses role pemanggil otomatis menampilkan jendela
"Akses ditolak"; sesi habis (401) otomatis kembali ke `/masuk?next=…`.

## 2. Bevel

| Kelas | Pakai untuk |
|---|---|
| `.raised` | jendela, tombol, taskbar, panel tab |
| `.pressed` | tombol saat ditekan / toggle aktif (`aria-pressed="true"`) |
| `.sunken` | input, screen, field status bar, listbox |
| `.groove` | pengelompokan (`fieldset` sudah otomatis groove) |

```html
<div class="raised tabpanel">…</div>
<div class="banner sunken">…</div>
```

## 3. Jendela (Window)

Router membuat jendela halaman. Untuk jendela tambahan:

```js
el.innerHTML = UI.windowHTML({ title: 'Masuk ke Orbit-U', icon: 'key', cls: 'small',
  body: '<p>…</p>', status: '<span>Status: Siap</span><span class="fit">Sesi 8 jam</span>' });
```

`cls`: `small` (420 px), `medium` (720 px), kosong = 1200 px. Ikon: lihat §12.

## 4. Tombol

```html
<button type="button">Batal</button>
<button type="submit" class="default">Simpan</button>   <!-- outline hitam = tombol utama -->
<button type="button" class="small">Ubah…</button>       <!-- aksi baris tabel -->
<a class="btn" href="#katalog">Katalog</a>
```

Tombol sibuk (nonaktif + indikator berkedip) selama request:

```js
btn.addEventListener('click', () => UI.busy(btn, async () => { await API.post(…); }));
```

Label gaya sistem: `Simpan`, `Batal`, `Properti…` (elipsis = membuka dialog).

## 5. Input dan fieldset

```html
<fieldset>
  <legend>Filter</legend>
  <div class="field">
    <label for="fDesc">Deskripsi *</label>
    <textarea id="fDesc" required aria-describedby="fDescErr"></textarea>
    <span class="hint">10–4000 karakter.</span>
    <span class="err" id="fDescErr"></span>
  </div>
  <div class="field-row"> <!-- dua kolom, satu kolom di mobile --> </div>
  <label class="check"><input type="checkbox"> Sudah diverifikasi</label>
</fieldset>
```

Validasi klien: isi `.err` dan set `aria-invalid="true"` (latar kuning muda),
fokus ke field pertama yang salah. Server tetap memvalidasi; pesannya datang
lewat `UI.showError`.

## 6. Screen (layar telemetri)

Semua data (angka, tabel, peta, grafik, log) di dalam screen; **tidak ada input di dalam screen**
(pengecualian yang tercatat: tombol aksi kecil per baris tabel).

```js
UI.screenHTML({ channel: 'CH-01 · DAFTAR KEJADIAN', rec: '12 KEJADIAN', recCls: 'off', body: html });
UI.screenHTML({ channel: 'CH-01 · PETA', flush: true, body: '<div class="map" id="m"></div>' });  // tanpa padding
UI.emptyHTML('BELUM ADA DATA');   // keadaan kosong (wajib dipakai, bukan error)
UI.loadingHTML();                 // MEMUAT DATA…
```

`recCls`: kosong = amber (`● REC`), `live` = merah (`● LIVE`), `off` = hijau redup.
Kelas teks di screen: `.lbl` (label kapital), `.v-amber`, `.v-alert`, `.v-cyan`, `.v-dim`.

## 7. Readout

```js
'<div class="readouts">' +
  UI.readoutHTML('STATUS AREA', 'WASPADA', 'Lebak Selatan', 'v-amber') +
  UI.readoutHTML('AIR BARU', UI.num(20.33, 2), 'km² · Δ VS SCENE T-1') +
'</div>'
```

Nilai berubah → `v-amber`; lewat ambang kritis → `v-alert`. Nilai kosong → `UI.NA` ("—").

## 8. Tabel data

```js
UI.tableHTML([
  { label: 'Tanggal', get: e => UI.date(e.event_date) },
  { label: 'Nilai', cls: 'r', get: e => UI.num(e.value, 1) + ' mm' },
  { label: 'Aksi', html: true, get: e => '<button type="button" class="small" data-open="' + e.id + '">Properti…</button>' },
], rows, { empty: 'BELUM ADA KEJADIAN', caption: 'Daftar kejadian' })
+ UI.pagerHTML(total, limit, offset);   // tombol [data-page]
```

Kolom `html: true` tidak di-escape — escape sendiri dengan `UI.esc`.

## 9. Status lamp, tag, progress, banner

```html
<span class="lamp-row"><i class="lamp ok"></i>S1 OK</span>   <!-- ok | busy | fail; selalu disertai teks -->
<span class="tag v-amber">L · LEBAT</span>
<div class="progress" role="progressbar" aria-valuenow="40" aria-valuemin="0" aria-valuemax="100"><i style="width:40%"></i></div>
<div class="banner raised" role="alert">[ikon 32 px]<div class="b-body">…</div></div>
```

## 10. Dialog (pengganti toast)

```js
await UI.info('Judul', 'Pesan');
await UI.showError('Simpan kejadian', err);        // err = API.ApiError → pesan Indonesia (+ error per baris impor)
if (await UI.confirm('Hapus', 'Yakin?', 'Hapus')) { … }
const v = await UI.dialog({ title, kind: 'question', message, body: '<div class="field">…</div>',
  buttons: [{ label: 'Simpan', value: 'ok', default: true }, { label: 'Batal', value: null, cancel: true }],
  validate: (win, val) => val !== 'ok' || cekField(win),   // false = dialog tetap terbuka
  collect: win => ({ … }) });                               // nilai yang di-resolve
```

Escape = batal, Tab berputar di dalam dialog, fokus kembali ke pemicu.
`UI.lightbox(items, i)` untuk galeri citra (panah kiri/kanan).

## 11. Tab (property sheet) dan listbox

```html
<div class="tabs" role="tablist">
  <button type="button" role="tab" data-tab="a" aria-selected="true">Ringkasan</button>
  <button type="button" role="tab" data-tab="b" aria-selected="false" tabindex="-1">Log</button>
</div>
<div class="raised tabpanel" role="tabpanel">…</div>
```

```js
UI.bindTabs(root, key => render(key));   // klik + panah kiri/kanan
```

Listbox: `<div class="listbox" role="listbox">` berisi `<button role="option" aria-selected>`.

## 12. Ikon

`UI.icon(nama)` → SVG inline piksel. 16 px: `satellite dish globe drop folder disk monitor chart doc key gear alarm user door help`.
32 px: `info32 warn32 error32 question32 sat32`. Tidak ada emoji.

## 13. Format dan bahasa

| Fungsi | Contoh |
|---|---|
| `UI.num(1234.5, 1)` | `1.234,5` |
| `UI.pct(0.07, 2)` | `0,07%` |
| `UI.bytes(1316685204)` | `1,2 GB` |
| `UI.date('2026-09-27')` / `'short'` / `'long'` | `27 Sep 2026` / `27 Sep` / `Minggu, 27 September 2026` |
| `UI.dateTime(iso)` | `3 Okt 2026, 19.53` |
| `UI.errorText(err)` | kode `INVALID_DISASTER` → kalimat Indonesia (tabel `UI.ERROR_TEXT`, INTERFACE §5) |

Kode error baru di API **wajib** ditambahkan ke `UI.ERROR_TEXT` — `tests/test_web_ui.py` memeriksanya.

## 14. Grafik

```js
UI.chartSVG([{ label: 'Hujan 24 jam', points: [{ x: '2024-01-01', y: 3.3 }, …] }],
  { unit: 'mm', zero: true, bar: false, width: 600, height: 200,
    thresholds: { waspada: 50 },                                      // garis merah putus
    forecast: { points: [{ x, mean, lo, hi }] },                      // amber putus + pita, berlabel "PRAKIRAAN STATISTIK, BUKAN PERINGATAN"
    markers: [{ x: '2024-01-05', label: '1', tip: 'Banjir — Bayah' }] });
```

Satu grafik maksimal 3 warna sinyal; banyak kecamatan → *small multiples*.
`width` = lebar kontainer supaya teks tetap 10 px.

## 15. Peta

```js
const map = Maps.create(el);              // Esri + filter fosfor; null bila Leaflet gagal dimuat (pesan di screen)
const geo = await Maps.regions();         // /api/regions (cache)
Maps.ensurePatterns(map);                 // pola arsir #hatch-a / #hatch-b untuk kategori BMKG tertinggi
```

Panggil `map.remove()` di `destroy()`. Kategori BMKG: `UI.BMKG`, `UI.bmkgCategory(mm)`, `UI.bmkgClass(code)` — label selalu tertulis.

## 16. Excel

```html
<div id="xl"></div>
```
```js
Excel.mount(UI.$('#xl', root), ['disasters', 'disaster_rain'], { onImported: reload });
```

Hanya jenis data yang diizinkan role yang tampil; impor selalu uji kering dulu.

## 17. Layout dan responsif

```html
<div class="layout">              <!-- kiri 280 px Control Panel, kanan Telemetry Deck -->
  <div class="control-panel">fieldset…</div>
  <div class="deck">readouts → screens</div>
</div>
```

`wide-left` (300 px), `single`, `cols-2`, `cols-3`. Di bawah 800 px semua jadi satu kolom
(urutan Control Panel → Readout → Screen); di bawah 420 px tombol tugas taskbar disembunyikan,
taskbar tetap tampil.

## 18. Aksesibilitas (wajib)

- Setiap input punya `<label for>`; pesan error lewat `aria-describedby`.
- Warna tidak pernah sendirian: kategori, status, lampu, dan alert selalu ada teksnya.
- Dialog `role="dialog"/"alertdialog"`, `aria-modal`; tab `role="tablist"`; peta punya `aria-label` dan datanya juga ada di tabel/kartu.
- Fokus terlihat: garis titik 1 px (DESIGN §4).
