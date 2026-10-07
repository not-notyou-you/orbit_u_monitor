// js/about.js — Sistem › Tentang (#sistem/tentang, INTERFACE.md §2 halaman 8.1, M56).
// Teks statis + versi API dan status basis data dari GET /api/health.
'use strict';
Pages['about'] = {
  async init(root, ctx) {
    const box = UI.$('#abInfo', root);
    const rows = [['PERAN ANDA', UI.ROLE_LABEL[Auth.role()] || Auth.role()]];
    try {
      const h = await API.get('/api/health', { noRedirect: true });
      rows.push(['STATUS SERVER', h.db_connected ? 'Terhubung' : 'Basis data tidak terjangkau']);
      if (h.version) rows.push(['VERSI API', h.version]);
    } catch (e) { rows.push(['STATUS SERVER', 'Tidak terjangkau']); }
    rows.push(['DOKUMENTASI API', '/docs']);
    box.innerHTML = rows.map(([k, v]) => '<dt>' + UI.esc(k) + '</dt><dd>' + (v === '/docs'
      ? '<a href="/docs" target="_blank" rel="noopener">/docs (Swagger)</a>' : UI.esc(v)) + '</dd>').join('');
    ctx.setStatus('Siap');
  },
};
