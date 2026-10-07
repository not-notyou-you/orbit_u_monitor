// js/data-home.js — Data › Ringkasan (#data/ringkasan, INTERFACE.md §2 halaman 6.1, M56).
// GET /api/data/summary: jumlah scene/granule per satelit (aktif/nonaktif),
// rentang tanggal, hari yang sudah punya angka per kecamatan, dan backfill
// yang sedang/baru berjalan. Navigasi ke sub-halaman diambil dari ROUTES.
'use strict';
Pages['data-home'] = (() => {
  const TAB = { s1: 'sentinel-1', modis: 'modis', gpm: 'gpm' };
  const RUN_STATUS = { RUNNING: ['BERJALAN', 'v-cyan'], COMPLETED: ['SELESAI', ''], FAILED: ['GAGAL', 'v-alert'], SKIPPED: ['DILEWATI', 'v-amber'] };
  let st = null;

  async function init(root, ctx) {
    st = { root, ctx, timer: null };
    renderNav();
    await load();
    st.timer = setInterval(load, 15000);
  }
  function destroy() { if (st && st.timer) clearInterval(st.timer); st = null; }

  function renderNav() {
    const route = Shell.ROUTES.find(r => r.hash === 'data');
    UI.$('#dhNav', st.root).innerHTML = Shell.visibleTabs(route).filter(t => t.key !== 'ringkasan').map(t =>
      '<a class="navcard" href="#data/' + t.key + '">' + UI.icon('folder') + '<span class="nc-body"><span class="nc-title">' +
      UI.esc(t.title) + '</span><span class="nc-desc">' + UI.esc(t.lede) + '</span></span></a>').join('');
  }

  async function load() {
    if (!st) return;
    const $ = s => UI.$(s, st.root);
    let r;
    try { r = await API.get('/api/data/summary'); }
    catch (e) { if (st && !st.loaded) { $('#dhCards').innerHTML = UI.emptyHTML('GAGAL MEMUAT'); UI.showError('Data', e); } return; }
    if (!st) return;
    st.loaded = true;
    const total = r.sources.reduce((s, x) => s + x.n_total, 0);
    const invalid = r.sources.reduce((s, x) => s + x.n_invalid, 0);
    const running = r.sources.filter(x => x.backfill_running).length;
    $('#dhReadouts').innerHTML =
      UI.readoutHTML('SCENE + GRANULE', UI.int(total), UI.int(invalid) + ' NONAKTIF', invalid ? 'v-amber' : '') +
      UI.readoutHTML('DATASET', UI.int(r.datasets.n_datasets), UI.int(r.datasets.n_active) + ' SEDANG DIPROSES', r.datasets.n_active ? 'v-cyan' : '') +
      UI.readoutHTML('BACKFILL', running ? 'BERJALAN' : 'DIAM', running ? UI.int(running) + ' SATELIT' : 'TIDAK ADA YANG BERJALAN', running ? 'v-cyan' : '');
    $('#dhCards').innerHTML = r.sources.map(s => '<section class="sat-card raised" aria-label="' + UI.esc(s.label) + '">' +
      '<header><b>' + UI.esc(s.label) + '</b>' + (s.backfill_running ? '<span class="v-cyan">● BACKFILL</span>' : '') + '</header>' +
      '<div class="screen"><div class="screen-inner"><dl class="kv">' +
      '<dt>TOTAL</dt><dd>' + UI.int(s.n_total) + '</dd><dt>AKTIF</dt><dd>' + UI.int(s.n_valid) + '</dd>' +
      '<dt>NONAKTIF</dt><dd class="' + (s.n_invalid ? 'v-amber' : '') + '">' + UI.int(s.n_invalid) + '</dd>' +
      '<dt>RENTANG</dt><dd>' + UI.esc(s.first_date ? UI.date(s.first_date, 'short') + ' – ' + UI.date(s.last_date, 'short') : UI.NA) + '</dd>' +
      '<dt>HARI DATA</dt><dd>' + UI.int(s.n_days) + '</dd>' +
      (s.key !== 's1' ? '<dt>HARI ANGKA KEC.</dt><dd>' + UI.int(s.obs_days) + '</dd>' : '') +
      '<dt>MASUK TERAKHIR</dt><dd>' + UI.esc(s.last_ingested_at ? UI.dateTime(s.last_ingested_at) : UI.NA) + '</dd></dl></div></div>' +
      '<div class="btn-row end"><a class="btn default" href="#data/' + TAB[s.key] + '">Kelola ' + UI.esc(s.label) + ' →</a></div></section>').join('');
    const h = r.hydromet || {};
    const ext = h.external ? '<p class="scr-text v-cyan" style="margin:0 0 6px">● BACKFILL HIDROMET BERJALAN DI PROSES LAIN — sedang mengerjakan ' +
      UI.esc(h.current_date ? UI.date(h.current_date) : 'tanggal berikutnya') + ', ' + UI.int(h.done_last_hour) + ' tanggal selesai dalam 1 jam terakhir. ' +
      '<a href="#data/gpm">Lihat di Data › GPM</a></p>' : '';
    $('#dhRuns').innerHTML = ext + UI.tableHTML([
      { label: '#', key: 'run_id' }, { label: 'Satelit', get: x => x.source.toUpperCase() },
      { label: 'Rentang', get: x => UI.date(x.date_from, 'short') + ' – ' + UI.date(x.date_to, 'short') },
      { label: 'Progres', get: x => x.total ? x.done + '/' + x.total : UI.NA },
      { label: 'Status', html: true, get: x => { const s = RUN_STATUS[x.status] || [x.status, '']; return '<span class="' + s[1] + '">' + s[0] + '</span>'; } },
      { label: 'Mulai', get: x => UI.dateTime(x.started_at) },
    ], r.recent_runs, { empty: h.external ? 'BELUM ADA BACKFILL DARI HALAMAN INI' : 'BELUM ADA BACKFILL SEJAK SERVER DIMULAI', caption: 'Backfill terakhir' });
    st.ctx.setStatus('Siap · diperbarui tiap 15 detik');
  }

  return { init, destroy };
})();
