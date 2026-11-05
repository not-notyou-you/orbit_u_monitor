'use strict';
(function () {
  const KEY = 'orbit-u.tema';
  const BASE = 'o95';
  const DEFAULT = 'mint';
  const LIST = [
    { key: 'o95', name: 'Orbital 95',
      desc: 'Jendela abu-abu berbevel ala Windows 95; data di layar CRT hijau.' },
    { key: 'mint', name: 'Kertas Mint', note: 'bawaan',
      desc: 'Kertas berpetak mint, garis navy tegas, dan bayangan keras.',
      font: 'Nunito:wght@400;600;700;800' },
    { key: 'pasir', name: 'Mika Pasir',
      desc: 'Krem dan emas, kaca buram ala Windows 11, taskbar mengambang.' },
    { key: 'piksel', name: 'Piksel Marun',
      desc: 'Abu-abu dan marun, garis tepi tebal ala 8-bit.',
      font: 'Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400' },
  ];
  const known = k => LIST.some(t => t.key === k);

  function get() {
    try { const v = localStorage.getItem(KEY); if (known(v)) return v; } catch (e) { /* mode privat */ }
    return DEFAULT;
  }

  function loadFont(t) {
    if (!t.font || document.getElementById('temaFont-' + t.key)) return;
    const l = document.createElement('link');
    l.id = 'temaFont-' + t.key; l.rel = 'stylesheet';
    l.href = 'https://fonts.googleapis.com/css2?family=' + t.font + '&display=swap';
    document.head.appendChild(l);
  }

  function apply(key) {
    const t = LIST.find(x => x.key === key) || LIST.find(x => x.key === DEFAULT);
    const html = document.documentElement;
    html.dataset.theme = t.key;
    html.classList.toggle('tema-alt', t.key !== BASE);
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
  window.addEventListener('storage', e => {
    if (e.key === KEY) { apply(get()); document.dispatchEvent(new CustomEvent('orbit-u:tema', { detail: get() })); }
  });

  window.Theme = { LIST: LIST, DEFAULT: DEFAULT, get: get, set: set };
})();
