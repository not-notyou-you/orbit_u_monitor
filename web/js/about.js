'use strict';
Pages['about'] = (() => {
  async function init(root, ctx) {
    UI.$$('[data-icon]', root).forEach(el => { el.innerHTML = UI.icon(el.dataset.icon); });
    UI.$('#abRoles', root).hidden = Auth.role() !== 'ADMIN';
    await renderInfo(root, ctx.me);
    ctx.setStatus(ctx.me ? 'Siap · masuk sebagai ' + (ctx.me.full_name || ctx.me.username) : 'Siap · pengunjung');
  }

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
