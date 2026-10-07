// web/js/theme.js — pilihan tema tampilan (M57).
//
// Empat tema: Orbital 95 (bawaan, DESIGN.md) dan tiga tema dari konsep
// DOCS/design tambahan/ (konsep38 → Kertas Mint, konsep41 → Mika Pasir,
// konsep44 → Piksel Marun). Tema hanya mengganti tampilan: struktur halaman,
// router, dan data tidak berubah. CSS-nya ada di css/tema/ dan seluruhnya
// tercakup html[data-theme="…"], jadi Orbital 95 tetap persis seperti dulu.
//
// Dimuat di <head> SEBELUM <body> diurai, supaya atribut data-theme sudah ada
// saat halaman pertama kali digambar (tanpa kedipan tema bawaan). Pilihan
// disimpan di localStorage peramban ini saja — bukan preferensi akun.
'use strict';
(function () {
  const KEY = 'orbit-u.tema';
  const DEFAULT = 'o95';
  const LIST = [
    { key: 'o95', name: 'Orbital 95', note: 'bawaan',
      desc: 'Jendela abu-abu berbevel ala Windows 95; data di layar CRT hijau.' },
    { key: 'mint', name: 'Kertas Mint',
      desc: 'Kertas berpetak mint, garis navy tegas, dan bayangan keras.',
      font: 'Nunito:wght@400;600;700;800' },
    { key: 'pasir', name: 'Mika Pasir',
      desc: 'Krem dan emas, kaca buram ala Windows 11, taskbar mengambang.' },
    { key: 'piksel', name: 'Piksel Marun',
      desc: 'Abu-abu dan marun, huruf piksel, garis tepi tebal ala 8-bit.',
      font: 'Pixelify+Sans:wght@400;600;700' },
  ];
  const known = k => LIST.some(t => t.key === k);

  function get() {
    try { const v = localStorage.getItem(KEY); if (known(v)) return v; } catch (e) { /* mode privat */ }
    return DEFAULT;
  }

  // Font tema dimuat hanya bila tema itu dipakai; tumpukan font di CSS punya
  // cadangan lokal, jadi tanpa jaringan tampilan tetap utuh.
  function loadFont(t) {
    if (!t.font || document.getElementById('temaFont-' + t.key)) return;
    const l = document.createElement('link');
    l.id = 'temaFont-' + t.key; l.rel = 'stylesheet';
    l.href = 'https://fonts.googleapis.com/css2?family=' + t.font + '&display=swap';
    document.head.appendChild(l);
  }

  function apply(key) {
    const t = LIST.find(x => x.key === key) || LIST[0];
    const html = document.documentElement;
    html.dataset.theme = t.key;
    // Satu kelas untuk semua tema non-bawaan: struktur bersama css/tema/umum.css.
    html.classList.toggle('tema-alt', t.key !== DEFAULT);
    loadFont(t);
    return t.key;
  }

  function set(key) {
    const k = apply(known(key) ? key : DEFAULT);
    try { localStorage.setItem(KEY, k); } catch (e) { /* mode privat: pilihan tidak diingat */ }
    document.dispatchEvent(new CustomEvent('orbit-u:tema', { detail: k }));
    return k;
  }

  apply(get());
  // Tab lain mengganti tema → tab ini ikut.
  window.addEventListener('storage', e => {
    if (e.key === KEY) { apply(get()); document.dispatchEvent(new CustomEvent('orbit-u:tema', { detail: get() })); }
  });

  window.Theme = { LIST: LIST, DEFAULT: DEFAULT, get: get, set: set };
})();
