// js/about.js — Tentang (#tentang, INTERFACE.md §2 halaman 1b, M63, M66).
//
// Halaman ini langsung menjelaskan aplikasinya (logo + "Apa ini", lalu lima
// kartu "Yang perlu diketahui"); isinya statis di pages/about.html. Skrip ini
// hanya mengisi info aplikasi (versi API dan status basis data dari
// GET /api/health) dan membuka tabel akses per peran untuk Administrator.
// Sambutan, strip status area, kartu halaman per peran, dan peta AOI dihapus
// (M66): navigasi sudah ada di menu bar, peta kecamatan di Beranda.
//
// Dokumentasi API (/docs) hanya ditautkan untuk pengguna yang sudah masuk.
'use strict';
Pages['about'] = (() => {
  async function init(root, ctx) {
    UI.$$('[data-icon]', root).forEach(el => { el.innerHTML = UI.icon(el.dataset.icon); });
    // Tabel akses per peran hanya untuk Administrator.
    UI.$('#abRoles', root).hidden = Auth.role() !== 'ADMIN';
    await renderInfo(root, ctx.me);
    ctx.setStatus(ctx.me ? 'Siap · masuk sebagai ' + (ctx.me.full_name || ctx.me.username) : 'Siap · pengunjung');
  }

  // ------------------------------------------------------ info aplikasi
  async function renderInfo(root, me) {
    const box = UI.$('#abInfo', root);
    const rows = [['PERAN ANDA', UI.esc(UI.ROLE_LABEL[Auth.role()] || Auth.role())]];
    try {
      const h = await API.get('/api/health', { noRedirect: true });
      rows.push(['STATUS SERVER', UI.esc(h.db_connected ? 'Terhubung' : 'Basis data tidak terjangkau')]);
      if (h.version) rows.push(['VERSI API', UI.esc(h.version)]);
    } catch (e) { rows.push(['STATUS SERVER', 'Tidak terjangkau']); }
    if (me) rows.push(['DOKUMENTASI API', '<a href="/docs" target="_blank" rel="noopener">/docs (Swagger)</a>']);
    box.innerHTML = rows.map(([k, v]) => '<dt>' + UI.esc(k) + '</dt><dd>' + v + '</dd>').join('');
  }

  return { init };
})();
